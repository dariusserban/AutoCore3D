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

## Două stiluri de joc

Jocurile se împart în două tipare, iar botul le tratează diferit. Se alege din profil.

| | `combat.mode: target` | `combat.mode: aim` |
|---|---|---|
| Tipar | MMO clasic (WoW-like) | ARPG izometric (Diablo-like, **Drakensang Online**) |
| Selectare | Tab sau click pe mob, ai bară de viață a țintei | nu există țintă; lovești în zona de sub cursor |
| Mișcare | `input.movement: keyboard` (WASD) | `input.movement: click` (click-to-move) |
| Cum știe că a murit | bara țintei a dispărut | au scăzut petele de dușman de pe ecran |
| Ținteste | un mob | centrul grămezii, ca abilitățile în zonă să prindă mai mulți |

Pentru Drakensang Online există un profil de pornire: `profiles/drakensang.yaml`.
E configurat pe `aim` + `click`, dar **cifrele din el sunt placeholdere** — regiunile și
culorile se măsoară pe ecranul tău, ca la orice profil.

DSO rulează în client nativ (Thin Client), nu în browser, deci fereastra e o aplicație
obișnuită: fără offset de viewport, fără zoom de pagină, iar tastele funcționale nu sunt
furate de browser (`F5` = refresh, `F12` = devtools).

## Instalare pe Windows

**1. Python.** Dacă nu-l ai, ia-l de la [python.org/downloads](https://www.python.org/downloads/)
și la instalare **bifează „Add python.exe to PATH"**. E nevoie de 3.10 sau mai nou.

**2. Codul.** Îl iei din GitHub, într-un folder al tău:

```
git clone -b claude/game-farming-bot-oi4pi0 https://github.com/dariusserban/AutoCore3D.git
```

Fără git: pe pagina repo-ului alegi branch-ul `claude/game-farming-bot-oi4pi0`, apoi
**Code → Download ZIP**, și dezarhivezi.

**3. Instalarea.** Dublu-click pe `gamebot\instalare.bat`. Creează un mediu virtual
și trage bibliotecile. Se rulează o singură dată.

**4. Pornirea.** Click **dreapta** pe `gamebot\bot.bat` → **Run as administrator**.
Se deschide fereastra aplicației, cu taburi: AUTOPILOT, LUPTĂ, CALIBRARE, JURNAL.

Dacă fereastra nu pornește (lipsește tkinter), `meniu.bat` face aceleași lucruri dintr-un
meniu în consolă.

Administrator nu e moft: clientul DSO rulează elevat, iar Windows nu lasă un proces
neprivilegiat să trimită input către unul privilegiat. Fără asta botul pare că merge, dar în
joc nu se întâmplă nimic.

### Două setări în joc, obligatorii

**Fereastră sau „fullscreen fără margini", nu fullscreen exclusiv.** În fullscreen exclusiv
DirectX preia ecranul și captura iese complet neagră. Botul detectează asta și îți spune, dar
mai bine o eviți din start.

**Aceeași rezoluție la înregistrare și la rulare.** Ruta reține coordonate; dacă schimbi
rezoluția între timp, botul le scalează, dar interfața nu se scalează la fel și regiunile
calibrate ies pe lângă.

Scalarea Windows (125%, 150%) e tratată automat — procesul se declară DPI-aware la pornire.
Fără asta, capturile ar veni la rezoluția fizică iar clicurile ar pleca în coordonate scalate,
și ar cădea din ce în ce mai alături cu cât cobori pe ecran.

## Fereastra

Aplicația nu conține logica botului. Fiecare buton pornește `gamebot.main` ca proces separat
și îi arată ieșirea în tabul JURNAL — adică exact codul rulat și de linia de comandă, cu
aceleași teste în spate. Motivul e practic: captura de ecran, ascultătorii de tastatură și
ferestrele OpenCV de calibrare se poartă prost când împart firul de execuție cu bucla de
evenimente Tk.

**OPREȘTE nu omoară procesul.** Îi lasă un fișier-semnal (`gamebot/.stop`) pe care botul îl
verifică și iese pe drumul normal, eliberând tastele. Un proces omorât brutal poate rămâne cu
o tastă apăsată, iar personajul aleargă în perete după ce tu ai închis tot. Dacă nu răspunde
în 8 secunde, abia atunci e închis forțat.

`F12` oprește oricum, oriunde, fără să atingi fereastra.

Tabul LUPTĂ scrie direct în profil, **păstrând comentariile** — ele sunt documentația
fiecărui reglaj, ar fi o pierdere să dispară la prima bifă apăsată.

### Din linia de comandă (dacă preferi)

```bash
pip install -r gamebot/requirements.txt
python -m gamebot.main check --profile gamebot/profiles/drakensang.yaml
```

## Cum îl pornești

**Nu e nimic de calibrat.** Botul își găsește singur fereastra jocului (după titlu), o
măsoară, și își calculează regiunile de interfață ca **procente din ea** — merge la orice
rezoluție și dacă muți fereastra.

Singurul pas pe care îl faci tu e să-i arăți traseul o dată.

### 1. Înregistrează traseul

Tabul **AUTOPILOT** → scrii un nume → **Înregistrează**. Din secunda aia se salvează tot:
fiecare mișcare de mouse, fiecare click, fiecare tastă, cu temporizarea reală. Joci normal.

`F10` când ai terminat tura. Atât — restul e opțional:

| Tastă | Ce marchezi |
|-------|-------------|
| `F10` | **oprește și salvează** — singura obligatorie |
| `F6`  | marchează zonă de luptă (aici caută mob-uri) |
| `F4`  | marchează portal — apeși F4, apoi dai click pe portal |
| `F5`  | marchează un colț important (ajută la corectarea poziției) |
| `F8`  | marchează vendor / reparat |
| `F9`  | pauză / reluare

Bate-te de-adevăratelea în zonele marcate cu `F6` — de acolo se învață rotația de abilități.

### 2. Învață abilitățile

**Învață din rută** → îți arată ce a dedus. **Scrie în profil** → le și salvează.

### 3. Pornește

**PORNEȘTE**. Prima linie din JURNAL îți spune ce viață citește și câți dușmani vede —
dacă acolo scrie ceva care nu se potrivește cu ecranul tău, ăla e singurul lucru de corectat.

`F12` oprește imediat, oriunde. `F11` pauză.

### Ancorele de traseu, fără minimapă

Profilul de DSO nu definește `regions.minimap`, intenționat. Fără ea, reperele se rețin ca
**poze cu tot ecranul jocului**, micșorate la 240px. Forma terenului și așezarea clădirilor
identifică locul la fel de bine ca o minimapă, iar micșorarea șterge jucătorii care trec prin
cadru — devin câteva puncte, nu o diferență care strică potrivirea. Și nu trebuie calibrat
nimic.

Dacă vrei totuși precizie maximă, calibrezi `minimap` din tabul REGLAJ FIN și de atunci se
folosește doar ea.

## Modul de fundal — și de ce nu e garantat

Bifa **„Rulează în fundal"** încearcă două lucruri: să citească fereastra jocului prin
`PrintWindow` (în loc să fotografieze ecranul) și să trimită tastele și clicurile ca mesaje
direct către fereastră (în loc să miște mouse-ul real).

Când merge, poți lucra pe calculator în timp ce botul farmează.

**Nu merge la toate jocurile, și motivul e tehnic, nu de configurare.** Jocurile 3D desenează
adesea direct prin DirectX — atunci `PrintWindow` întoarce o imagine complet neagră — și își
citesc input-ul prin DirectInput sau Raw Input, care ocolesc complet mesajele trimise de noi.

Testează înainte: butonul **Testează modul de fundal** (sau `python -m gamebot.main bgtest`).
Îți spune în câteva secunde dacă imaginea se poate citi. Partea de input **nu poate fi
verificată automat** — n-avem cum ști ce ar trebui să se schimbe în joc după o apăsare — deci
aia rămâne de văzut pe viu: pornești cu bifa pusă și te uiți dacă personajul chiar se mișcă.

Dacă testul iese negativ, botul îți spune și continuă în modul obișnuit. Mai bine un bot care
ocupă ecranul decât unul care apasă în gol și pare că merge.

**Minimizat în bara de start nu funcționează în niciun caz.** O fereastră minimizată nu mai
desenează nimic, deci nu are ce fi citit. Dacă vrei calculatorul complet liber, singura
soluție care chiar merge e o mașină virtuală sau un al doilea calculator.

### Adunarea obiectelor

Comportamentul `loot` caută etichetele colorate ale obiectelor căzute (verde, albastru,
violet, auriu — albul și griul lipsesc intenționat, ar prinde jumătate din textul interfeței)
și dă click pe ele, sub etichetă, acolo unde e obiectul.

Nu insistă pe același obiect: dacă unul e în spatele unui gard și clicul nu face nimic, îl
ține minte și trece mai departe — altfel ar rămâne blocat acolo până la capătul sesiunii.
`pickup_radius` îl împiedică să traverseze harta după un obiect din colțul ecranului.

## Cum decide botul ce să facă

La fiecare ciclu, comportamentele sunt întrebate în ordinea priorității; primul care are ceva
de făcut, îl face:

| Prioritate | Comportament | Când intră |
|-----------:|--------------|------------|
| 100 | `survival`   | viața sub prag: se vindecă, fuge, sau oprește |
|  70 | `combat`     | e o țintă selectată sau se vede un mob, într-o zonă de luptă |
|  65 | `loot`       | se văd etichete de obiect căzut pe jos |
|  60 | `gather`     | *(oprit implicit)* se vede un nod de resurse |
|  40 | `upkeep`     | a trecut intervalul și ești la un reper de vendor |
|  20 | `mount`      | ești pe drum, n-ai dușmani lângă, și nu pari călare |
|  30 | `idle_click` | staționezi la un reper și ai o secvență de click definită |
|  10 | `travel`     | nimic mai important de făcut: mergi mai departe pe traseu |

De aceea lupta întrerupe mersul, iar vindecarea întrerupe lupta.

Un reper cu `dwell > 0` (secunde, se reglează în `route.json`) oprește mersul pe durata
respectivă, iar `combat` are ecranul la dispoziție — așa se bate botul pe loc într-o zonă.

### „Trece prin" — se bate doar cu ce-i iese în cale

`combat.only_when_blocking: true` face botul să ignore dușmanii mai depărtați de
`engage_radius` pixeli față de personaj (care e mereu în centrul ecranului). Fără filtrul
ăsta se ia după primul mob zărit în colțul ecranului și nu mai termină traseul niciodată.
Cu el, drumul contează și ce apare în cale se rezolvă pe loc.

Pentru farmat pe loc într-o zonă, lași `only_when_blocking: false` și pui `dwell` pe reper.

### Montura

`mount: true` în `behaviors` plus `keys.mount` — apasă tasta când e pe drum, nu are dușmani
lângă și nu staționează. Din pixeli nu se poate ști sigur dacă ești deja călare, așa că
implicit reîncearcă din când în când (`mount.retry_seconds`). Dacă vrei să știe sigur,
calibrează un sablon cu o iconiță care apare doar când ești călare:

```bash
python -m gamebot.main calibrate template --name mounted
```

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
│   ├── window.py         găsirea ferestrei jocului, regiuni în procente
│   ├── background.py     captură și input țintite pe fereastră (experimental)
│   └── engine.py         contextul comun și mașina de stări
├── ui/app.py             fereastra aplicației (tkinter)
├── behaviors/            supraviețuire, luptă, cules, întreținere, montură, click, mers
├── profiles/
│   ├── exemplu.yaml      profil generic, comentat
│   └── drakensang.yaml   profil de pornire pentru DSO (aim + click-to-move)
├── templates/            sabloanele PNG salvate de calibrare
└── tests/                186 de teste, rulează fără joc și fără ecran
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

**În modul `aim` nu vede niciun mob.**
`colors.enemy_nameplate` e cel mai important reglaj din profil. Calibrează-l pe o bucată
plină dintr-o bară de viață de mob, nu pe conturul ei, și verifică numărul detectat cu
`check`. Dacă vede mob-uri și pe ecran gol, strânge intervalul sau mărește
`combat.enemy_min_area`.

**Se oprește cu „ecranul nu s-a schimbat".**
Personajul e blocat într-un obstacol. Mărește `safety.stuck_seconds` dacă ai zone cu așteptare
lungă, sau reînregistrează traseul ocolind locul problematic.
