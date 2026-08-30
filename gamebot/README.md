# gamebot

Framework de automatizare pentru jocuri, bazat pe **vedere pe ecran** și **input simulat**.
Botul se uită la aceiași pixeli la care te uiți tu și apasă aceleași taste pe care le-ai apăsa tu.

Ideea de bază: **îl plimbi tu o dată, te lupți tu o dată, restul face el.**
Traseul, portalele și rotația de abilități se învață din sesiunea ta de joc — nu se scriu de mână.

## Ce face și ce nu face

**Face:**
- înregistrează traseul jucat de tine și îl reia, verificându-și poziția după minimapă
- trece portalele: click, așteaptă încărcarea hărții, confirmă că a ajuns dincolo
- se luptă, cu rotația de abilități **dedusă din felul în care te-ai luptat tu**
- se întoarce pe traseu după o luptă care l-a tras din drum
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
> tipică e banarea contului. Decizia e a ta — unealta e doar o unealtă.

Culesul de resurse (`behaviors/gather.py`) există, dar e **oprit implicit** în profil. Dacă
îți trebuie vreodată, pui `gather: true`.

## Instalare

```bash
pip install -r gamebot/requirements.txt
```

Pe Windows rulează terminalul **ca administrator**: fără asta, input-ul simulat nu ajunge în
jocurile care rulează elevat.

## Cum îl pui pe picioare

### 1. Copiază profilul de exemplu

```bash
cp gamebot/profiles/exemplu.yaml gamebot/profiles/jocul_meu.yaml
```

### 2. Măsoară regiunile și culorile

Valorile din exemplu sunt inventate. Fiecare comandă face o captură după 4 secunde (timp să
comuți pe joc), tragi un dreptunghi cu mouse-ul și primești bucata de YAML gata de lipit.

```bash
python -m gamebot.main calibrate region --name minimap
python -m gamebot.main calibrate region --name health_bar
python -m gamebot.main calibrate region --name target_health_bar
python -m gamebot.main calibrate color  --name health
python -m gamebot.main calibrate color  --name enemy_nameplate
```

Verifică ce a înțeles:

```bash
python -m gamebot.main check --profile gamebot/profiles/jocul_meu.yaml
```

Îți spune ce citește chiar acum de pe ecran — câtă viață ai, dacă vede ținta, câte mob-uri
detectează. Dacă scrie 0% viață când bara ta e plină, profilul e greșit; nu merge mai departe
până nu se potrivesc cifrele.

### 3. Înregistrează traseul — și luptă-te pe el

```bash
python -m gamebot.main record --profile gamebot/profiles/jocul_meu.yaml --name harta1
```

Mergi traseul normal. În timpul mersului:

| Tastă | Ce face |
|-------|---------|
| `F4`  | **portal** — apeși F4, apoi dai click pe portal |
| `F5`  | reper de drum (colț, cotitură, punct de trecere) |
| `F6`  | reper de luptă — aici botul va căuta mob-uri |
| `F7`  | reper de resurse (dacă folosești culesul) |
| `F8`  | reper de vendor/reparat |
| `F9`  | pauză / reluare a înregistrării |
| `F10` | oprește și salvează |

Două lucruri contează aici:

**Pune repere des.** Fiecare reper e un punct de control după care botul își verifică poziția.
Cu cât sunt mai multe, cu atât se corectează mai bine când se abate.

**Bate-te de-adevăratelea în zonele marcate cu `F6`.** Câteva minute de luptă normală, cu
abilitățile pe care le folosești tu, sunt exact materialul din care se învață rotația la pasul
următor. Cu cât te bați mai mult, cu atât estimarea cooldown-urilor e mai bună.

### 4. Învață rotația de abilități

```bash
python -m gamebot.main learn --route gamebot/routes/harta1
```

Se uită la segmentele de luptă și îți dă ceva de forma:

```
Analizate 3 segmente de lupta, 6.2 minute.
Timp intre doua abilitati (global cooldown): 1.63s

  tasta     apasari   cooldown   pondere
  3              26      12.3s      9.6%
  2              51       6.3s     18.9%
  1             193       1.7s     71.5%
```

Cum deduce cooldown-ul: nu-l poate citi din joc, dar are ceva aproape la fel de bun — **cel mai
scurt interval la care ai reușit tu să reapeși tasta**. Dacă ai apăsat `3` de 26 de ori și cel
mai devreme ai reușit după 12.3 secunde, ăla e cooldown-ul. Ia percentila 15 a intervalelor,
nu minimul absolut, ca o apăsare dublă din greșeală să nu strice estimarea.

Tastele de mers (`w`, `a`, `s`, `d`, `space`) și cele cu rost cunoscut din profil (vindecare,
loot, selectare țintă) sunt excluse automat.

Copiază blocul în profil, sub `combat:`, sau rulează cu `--write` (rescrie profilul și
păstrează o copie `.bak` — dar pierde comentariile).

Ordinea din listă e ordinea de prioritate: abilitățile cu cooldown mare stau primele, ca
lovitura grea să plece imediat ce e disponibilă, iar cele scurte umplu golurile.

### 5. Dă-i drumul

Întâi în gol, ca să vezi deciziile fără ca personajul să se miște:

```bash
python -m gamebot.main run --profile gamebot/profiles/jocul_meu.yaml \
                           --route gamebot/routes/harta1 --dry-run
```

Apoi pe bune:

```bash
python -m gamebot.main run --profile gamebot/profiles/jocul_meu.yaml \
                           --route gamebot/routes/harta1 --max-minutes 120
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
|  60 | `gather`     | *(oprit implicit)* se vede un nod de resurse |
|  40 | `upkeep`     | a trecut intervalul și ești la un reper de vendor |
|  30 | `idle_click` | staționezi la un reper și ai o secvență de click definită |
|  10 | `travel`     | nimic mai important de făcut: mergi mai departe pe traseu |

De aceea lupta întrerupe mersul, iar vindecarea întrerupe lupta.

Un reper cu `dwell > 0` (secunde, se reglează în `route.json`) oprește mersul pe durata
respectivă, iar `combat` are ecranul la dispoziție — așa se bate botul pe loc într-o zonă.

## Portalele

Un portal nu poate fi redat ca un click obișnuit, fiindcă între click și harta nouă e o
încărcare a cărei durată variază de fiecare dată. Un replay orb ar apăsa taste în ecranul de
loading și ar ajunge complet desincronizat.

De aceea, când marchezi un portal cu `F4`:

1. recorder-ul reține unde ai dat click, dar **scoate clicul din secvența redată**;
2. așteaptă să se schimbe ecranul (a început încărcarea), apoi să se liniștească (s-a terminat);
3. salvează o poză cu harta nouă, imediat după sosire.

La rulare, botul dă click, așteaptă la fel, apoi compară cu poza aia. Dacă nu seamănă:
- dacă încă e pe harta veche → clicul a ratat portalul, reîncearcă o dată;
- dacă nu recunoaște nici harta veche, nici pe cea nouă → se oprește, în loc să apese aiurea.

Dacă portalul se mișcă pe ecran (camera se rotește, personajul se oprește cu un pas mai
încolo), poți salva un sablon și-l pui în `route.json`, la portalul respectiv:

```bash
python -m gamebot.main calibrate template --name portal_oras
```
```json
"portal": {"click": [960, 540], "template": "portal_oras", "dest_anchor": "..."}
```

Atunci botul caută întâi portalul pe ecran și dă click pe el; poziția înregistrată rămâne
rezervă.

## Când se rătăcește

După fiecare reper, botul compară minimapa cu ancora înregistrată. Dacă nu seamănă:

1. caută printre reperele **din vecinătate** (±8) care e cel mai apropiat;
2. dacă nu iese nimic convingător, lărgește căutarea la tot traseul;
3. dacă găsește o potrivire sigură, sare la reperul acela și continuă de acolo;
4. după trei încercări eșuate, se oprește singur în loc să alerge aiurea pe hartă.

Căutarea începe în vecinătate tocmai din cauza portalelor: când traseul acoperă mai multe hărți,
o căutare oarbă pe tot traseul poate „găsi" un reper de pe altă hartă doar pentru că minimapa
are colțuri asemănătoare.

**După fiecare luptă** se face aceeași verificare, chiar dacă botul n-a ajuns încă la reperul
următor. O luptă te scoate din traseu — fugi după mob, te întorci din altă parte, cu camera
rotită — și dacă ar relua secvența înregistrată de acolo, ar merge în cu totul altă direcție.

Pragul de potrivire e `thresholds.anchor_match` (implicit 0.72). Mai mare = mai strict, mai
multe opriri false. Mai mic = tolerant, dar riscă să creadă că e altundeva.

## Structura

```
gamebot/
├── main.py               CLI: record / learn / run / check / calibrate / routes
├── core/
│   ├── capture.py        captura ecranului (mss), plus o sursă falsă pentru teste
│   ├── vision.py         template matching, măști HSV, bare, blob-uri
│   ├── input_ctl.py      taste și mouse, prin pydirectinput
│   ├── humanize.py       variația de temporizare și traiectoriile curbate
│   ├── route.py          modelul de traseu: repere, evenimente, portale
│   ├── recorder.py       modul de învățare: ascultă cum joci tu
│   ├── learning.py       deduce rotația de abilități din luptele înregistrate
│   ├── navigation.py     localizare după ancore, redarea traseului, portale
│   ├── safety.py         oprire de urgență, watchdog, limite de sesiune
│   ├── config.py         încărcarea profilului YAML
│   └── engine.py         contextul comun și mașina de stări
├── behaviors/            supraviețuire, luptă, cules, întreținere, click, mers
├── profiles/exemplu.yaml profil comentat, de copiat
├── templates/            sabloanele PNG salvate de calibrare
└── tests/                101 de teste, rulează fără joc și fără ecran
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

**`learn` nu găsește nicio abilitate.**
N-ai marcat zone de luptă cu `F6` la înregistrare, sau nu te-ai bătut destul în ele. Are nevoie
de cel puțin 3 apăsări per tastă ca s-o considere abilitate (`--min-presses` schimbă pragul).

**Se rătăcește des.**
Prea puține repere, sau minimapa aleasă conține elemente care se schimbă (ceas, chat, buff-uri).
Recalibrează `regions.minimap` pe o zonă care se schimbă doar când te miști tu.

**Ratează portalul.**
Personajul se oprește cu un pas mai încolo decât la înregistrare, deci clicul cade alături.
Salvează un sablon cu portalul și pune-l în `route.json` (vezi secțiunea Portalele).

**Se oprește cu „ecranul nu s-a schimbat".**
Personajul e blocat într-un obstacol. Mărește `safety.stuck_seconds` dacă ai zone cu așteptare
lungă, sau reînregistrează traseul ocolind locul problematic.
