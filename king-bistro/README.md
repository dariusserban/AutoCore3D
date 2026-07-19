# 👑 King Bistro — Meniu online + Comandă cu ridicare

Site complet într-un singur fișier: **`index.html`**. Nu are nevoie de server, bază de date sau instalări — se deschide direct în browser, pe telefon sau pe calculator.

## Cum îl vezi

- **Pe calculator:** dublu-click pe `index.html` (se deschide în Chrome/Edge/Safari/Firefox).
- **Pe telefon:** trimite-ți fișierul (WhatsApp/e-mail/Drive), deschide-l cu Chrome (Android) sau Safari (iOS).
- Site-ul este gândit *mobile-first* — arată și funcționează ca o aplicație pe Android și iOS.

## Ce conține

### Pentru clienți (prima pagină)
- Meniul complet, pe categorii (Meniuri / Sandwich / Băuturi), cu prețuri, descrieri, **ingrediente și gramaje**.
- Buton **„Comandă acum"** la fiecare produs → se deschide comanda cu **Prenume, Nume, Telefon** → buton final **„Comandă cu ridicare"**.
- Variante **Picant / Ne picant** la Crispy și Aripioare.
- Coș persistent cu bară fixă jos, sugestii „se potrivește cu…", confirmare cu număr de comandă.
- Temă negru + galben, accente roșu-portocaliu (culori care stimulează apetitul).

### Pentru tine (panou de administrare)
- Intrare: link-ul **„Administrare"** din josul paginii (sau adaugă `#admin` la adresă).
- **Parola: `kingbistro2026`** (o schimbi în `index.html`, caută `ADMIN_PASS`).
- **Comenzi:** apar instant, cu statusuri (Nouă → În pregătire → Ridicată / Anulată), telefonul clientului cu apel direct, totaluri pe ziua curentă.
- **Meniu:** adaugi/editezi/ștergi produse — nume, categorie, preț, descriere, **ingrediente cu gramaje**, etichete (⭐ Cel mai vândut / 🔥 Nou / % Promoție), variantă picantă, disponibil/indisponibil și **poză** (se optimizează automat la max. 900px).
- **Setări:** adresă, telefon, program, timp de pregătire, banner promoțional, comutator **Deschis/Închis**, politici (Termeni + Confidențialitate), export/import date (JSON), resetare meniu.

## Important de știut (versiunea demo)

1. **Datele se salvează local în browser** (localStorage). Meniul, pozele și comenzile rămân salvate pe dispozitivul respectiv, chiar și după închiderea browserului.
2. **Limitare:** o comandă plasată de un client de pe telefonul LUI ajunge doar în admin-ul deschis pe ACELAȘI dispozitiv/browser. Pentru comenzi reale de la clienți e nevoie de un mic backend (ex. Firebase/Supabase) — acesta e pasul următor firesc înainte de lansare; site-ul e pregătit pentru asta.
3. Gramajele din meniul demo sunt **orientative** — trece-le pe cele reale din Admin → Meniu.
4. Parola de admin e doar o barieră de acces în pagină, nu securitate reală (oricine citește codul sursă o poate vedea). Suficient pentru demo, de înlocuit la lansare.
5. Spațiul de stocare din browser e ~5 MB — pozele se comprimă automat, iar în Admin → Setări vezi cât spațiu s-a folosit.

## Când vrei să apară pe Google la „King Bistro"

Site-ul are deja titlul, descrierea și datele structurate (schema.org `FastFoodRestaurant`) pregătite pentru Google. Ca să apară primul la căutare, la lansare mai trebuie:
1. **Un domeniu propriu** (ex. `kingbistro.ro`) + găzduire (merge și gratuit pe GitHub Pages, fișierul e static).
2. **Profil Google Business** (gratuit) cu adresa, programul și link către site — asta aduce afișarea pe harta și în dreapta căutării.
3. Completate în Admin: adresa reală, telefonul, programul și politicile.

## Structură

```
king-bistro/
├── index.html   ← tot site-ul (pagina publică + panoul admin + logică)
└── README.md    ← acest fișier
```
