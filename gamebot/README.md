# gamebot

Framework de automatizare pentru jocuri, bazat pe **vedere pe ecran** și **input simulat**.
Botul se uită la aceiași pixeli la care te uiți tu și apasă aceleași taste pe care le-ai apăsa tu.

Partea centrală: **îi arăți tu traseul o dată, apoi îl rulează singur.** Joci, marchezi
reperele cu tastele funcționale, iar botul reține exact ce ai făcut și unde ai fost.

## Ce face și ce nu face

**Face:**
- captură de ecran și interpretare (bare de viață, nameplate-uri, noduri de resurse, iconițe de UI)
- input simulat prin `pydirectinput` (scan codes — funcționează în jocurile DirectX, unde `pyautogui` e ignorat)
- înregistrarea unui traseu jucat de tine și redarea lui, cu verificarea poziției după minimapă
- luptă, cules, întreținere de inventar, click repetitiv — toate declarative, în profil
- oprire de urgență, watchdog pentru blocaje, pauze la intervale neregulate

**Nu face** — și nu e o omisiune, ci o alegere:
- nu citește și nu scrie în memoria jocului
- nu injectează cod și nu se atașează la proces
- nu trimite pachete către server în numele tău
- nu conține nimic care să ocolească un sistem anti-cheat

Variația de temporizare din `core/humanize.py` există ca botul să se comporte firesc și să nu
se blocheze în tipare mecanice, nu ca să ascundă ceva de cineva.

> **Un cuvânt despre riscuri.** Aproape toate jocurile online interzic automatizarea prin
> termenii de utilizare, iar unele au anti-cheat care detectează input sintetic. Consecința
> tipică e banarea contului. Pe single-player, emulator, server privat sau joc open-source nu
> se pune problema. Decizia e a ta — unealta e doar o unealtă.

## Instalare

```bash
pip install -r gamebot/requirements.txt
```

Pe Windows rulează terminalul **ca administrator**: fără asta, input-ul simulat nu ajunge în
jocurile care rulează elevat.

## Cum îl pui pe picioare

Toate valorile din profil sunt specifice jocului **și rezoluției tale**. Nimic nu merge fără
pasul de calibrare — profilul livrat conține valori inventate, pentru formă.

### 1. Copiază profilul de exemplu

```bash
cp gamebot/profiles/exemplu.yaml gamebot/profiles/jocul_meu.yaml
```

### 2. Măsoară regiunile și culorile

Fiecare comandă face o captură după 4 secunde (timp să comuți pe joc), apoi tragi un
dreptunghi cu mouse-ul și primești bucata de YAML gata de lipit.

```bash
python -m gamebot.main calibrate region --name minimap
python -m gamebot.main calibrate region --name health_bar
python -m gamebot.main calibrate region --name target_health_bar
python -m gamebot.main calibrate color  --name health
python -m gamebot.main calibrate color  --name enemy_nameplate
python -m gamebot.main calibrate color  --name resource_node
```

Pentru butoane și iconițe fixe, salvează sabloane:

```bash
python -m gamebot.main calibrate template --name buton_vinde
```

### 3. Verifică ce a înțeles botul

```bash
python -m gamebot.main check --profile gamebot/profiles/jocul_meu.yaml
```

Îți spune ce citește chiar acum de pe ecran: câtă viață ai, dacă vede ținta, câte mob-uri și
câte noduri detectează. Dacă scrie 0% viață când bara ta e plină, profilul e greșit — nu
merge mai departe până nu se potrivesc cifrele.

### 4. Înregistrează traseul

```bash
python -m gamebot.main record --profile gamebot/profiles/jocul_meu.yaml --name padure
```

Intri în joc și mergi traseul normal. În timpul mersului:

| Tastă | Ce face |
|-------|---------|
| `F5`  | reper de drum (colț, cotitură, punct de trecere) |
| `F6`  | reper de luptă (aici botul caută mob-uri) |
| `F7`  | reper de resurse (aici botul caută noduri) |
| `F8`  | reper de vendor/reparat (aici rulează întreținerea) |
| `F9`  | pauză / reluare a înregistrării |
| `F10` | oprește și salvează |

Pune repere des — la fiecare cotitură și la fiecare zonă de farmat. Fiecare reper e un punct
de control după care botul își verifică poziția; cu cât sunt mai multe, cu atât se corectează
mai bine când se abate.

Traseul se salvează în `gamebot/routes/padure/`: `route.json` plus câte o poză de ancoră.

Cât stă botul la fiecare reper de farmat se reglează din `route.json`, câmpul `dwell`
(secunde). Pune de exemplu `dwell: 120` la un reper de luptă și va farma două minute acolo
înainte să meargă mai departe.

### 5. Dă-i drumul

Întâi în gol, ca să vezi deciziile fără ca personajul să se miște:

```bash
python -m gamebot.main run --profile gamebot/profiles/jocul_meu.yaml \
                           --route gamebot/routes/padure --dry-run
```

Apoi pe bune:

```bash
python -m gamebot.main run --profile gamebot/profiles/jocul_meu.yaml \
                           --route gamebot/routes/padure --max-minutes 120
```

**`F12` oprește tot, oricând. `F11` pune pauză.** Ambele funcționează chiar dacă jocul are
focusul.

## Cum decide botul ce să facă

La fiecare ciclu, comportamentele sunt întrebate în ordinea priorității; primul care are ceva
de făcut, îl face:

| Prioritate | Comportament | Când intră |
|-----------:|--------------|------------|
| 100 | `survival`   | viața sub prag: se vindecă, fuge, sau oprește |
|  70 | `combat`     | e o țintă selectată sau se vede un mob, într-o zonă de luptă |
|  60 | `gather`     | se vede un nod de resurse, într-o zonă de resurse |
|  40 | `upkeep`     | a trecut intervalul și ești la un reper de vendor |
|  30 | `idle_click` | staționezi la un reper și ai o secvență de click definită |
|  10 | `travel`     | nimic mai important de făcut: mergi mai departe pe traseu |

De aceea lupta întrerupe mersul, iar vindecarea întrerupe lupta. Când se termină, traseul
continuă de unde a rămas.

Un reper cu `dwell > 0` oprește mersul pe durata respectivă, iar `combat` și `gather` au
ecranul la dispoziție — așa farmează botul pe loc într-o zonă.

## Când se rătăcește

După fiecare reper, botul compară minimapa cu ancora înregistrată. Dacă nu seamănă:

1. se oprește și caută prin toate ancorele rutei care e cea mai apropiată;
2. dacă găsește una convingătoare, sare la reperul acela și continuă de acolo;
3. după trei încercări eșuate, se oprește singur în loc să alerge aiurea pe hartă.

Pragul de potrivire e `thresholds.anchor_match` (implicit 0.72). Mai mare = mai strict, mai
multe opriri false. Mai mic = tolerant, dar riscă să creadă că e altundeva.

## Structura

```
gamebot/
├── main.py               intrarea CLI: record / run / check / calibrate / routes
├── core/
│   ├── capture.py        captura ecranului (mss), plus o sursă falsă pentru teste
│   ├── vision.py         template matching, măști HSV, bare, blob-uri
│   ├── input_ctl.py      taste și mouse, prin pydirectinput
│   ├── humanize.py       variația de temporizare și traiectoriile curbate
│   ├── route.py          modelul de traseu (repere + evenimente)
│   ├── recorder.py       modul de învățare: ascultă cum joci tu
│   ├── navigation.py     localizare după ancore + redarea traseului
│   ├── safety.py         oprire de urgență, watchdog, limite de sesiune
│   ├── config.py         încărcarea profilului YAML
│   └── engine.py         contextul comun și masina de stări
├── behaviors/            supraviețuire, luptă, cules, întreținere, click, mers
├── profiles/exemplu.yaml profil comentat, de copiat
├── templates/            sabloanele PNG salvate de calibrare
└── tests/                80 de teste, rulează fără joc și fără ecran
```

## Teste

```bash
python -m pytest gamebot/tests -q
```

Rulează pe ecrane sintetice și cu input în gol, deci merg pe orice mașină, fără joc pornit.

## Probleme frecvente

**Botul apasă taste dar în joc nu se întâmplă nimic.**
Jocul citește input prin DirectInput. Verifică că `pydirectinput` e instalat (nu doar
`pyautogui`) și pornește terminalul ca administrator.

**`check` arată 0% viață deși bara e plină.**
Regiunea sau culoarea sunt greșite. Rulează din nou `calibrate color --name health`,
selectând o zonă plină din mijlocul barei, nu marginea.

**Detectează noduri peste tot.**
Intervalul HSV e prea larg. Strânge-l, sau mărește `gather.min_area` ca să ignore petele mici.

**Se rătăcește des.**
Prea puține repere, sau minimapa aleasă conține elemente care se schimbă (ceas, chat, buff-uri).
Recalibrează `regions.minimap` pe o zonă care se schimbă doar când te miști tu.

**Se oprește cu „ecranul nu s-a schimbat".**
Personajul e blocat într-un obstacol. Mărește `safety.stuck_seconds` dacă ai zone cu așteptare
lungă, sau reînregistrează traseul ocolind locul problematic.
