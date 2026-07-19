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

## Conectare Supabase (comenzi reale + poze partajate)

Fără Supabase, site-ul merge, dar comenzile și pozele rămân doar pe dispozitivul curent. Cu Supabase conectat, comenzile clienților ajung la tine pe orice dispozitiv, iar pozele se văd de toată lumea. Pași:

1. Cont gratuit pe [supabase.com](https://supabase.com) → **New project** (ține minte parola de bază de date).
2. În proiect: **SQL Editor → New query** → lipește tot conținutul din **[`supabase-setup.sql`](./supabase-setup.sql)** → **Run**. (creează tabelele, regulile de securitate și bucket-ul de poze `menu-photos`.)
3. **Project Settings → API** → copiază **Project URL** și cheia **`anon` / `public`** (NU `service_role`).
4. În `index.html`, la începutul scriptului, completează:
   ```js
   const SB_URL = 'https://xxxxxxxx.supabase.co';   // Project URL
   const SB_KEY = 'eyJhbGciOi...';                   // cheia anon / public
   ```
5. `git push` (sau lasă-l pe Claude să pună cheile) → Vercel reface deploy-ul. În **Admin → Setări** vei vedea „🟢 Conectat la Supabase".

**Cum e protejat:** clientul poate DOAR să trimită comenzi; citirea, schimbarea de status și ștergerea comenzilor se fac doar cu parola ta (verificată în Supabase), deci telefoanele clienților nu pot fi citite de cineva care are doar cheia publică. Ștergi comenzile executate din panou, cu butonul **Șterge**.

## Important de știut

1. **Fără Supabase**, datele se salvează local în browser (localStorage) — bune pentru test, dar o comandă de pe telefonul unui client ajunge doar în admin-ul de pe ACELAȘI dispozitiv. De aceea conectezi Supabase înainte de lansarea reală (pași mai sus).
2. Parola de admin (`kingbistro2026`) e o barieră de acces, nu securitate militară — e vizibilă pentru cine citește codul. Dacă o schimbi în `index.html` (`ADMIN_PASS`), schimb-o și în `supabase-setup.sql` (în cele 3 funcții `kb_orders_*`).
3. Gramajele din meniul demo sunt **orientative** — trece-le pe cele reale din Admin → Meniu.
4. Fără Supabase, spațiul local din browser e ~5 MB — pozele se comprimă automat. Cu Supabase, pozele stau în cloud, nu în acest spațiu.

## Când vrei să apară pe Google la „King Bistro"

Site-ul are deja titlul, descrierea și datele structurate (schema.org `FastFoodRestaurant`) pregătite pentru Google. Ca să apară primul la căutare, la lansare mai trebuie:
1. **Un domeniu propriu** (ex. `kingbistro.ro`) + găzduire (merge și gratuit pe GitHub Pages, fișierul e static).
2. **Profil Google Business** (gratuit) cu adresa, programul și link către site — asta aduce afișarea pe harta și în dreapta căutării.
3. Completate în Admin: adresa reală, telefonul, programul și politicile.

## Structură

```
kingbistro/
├── index.html          ← tot site-ul (pagina publică + panoul admin + logică)
├── supabase-setup.sql  ← se lipește o dată în Supabase (tabele + securitate + poze)
├── vercel.json         ← configurare de deploy pentru Vercel
└── README.md           ← acest fișier
```

## Deploy pe Vercel

`index.html` stă în rădăcina repo-ului, deci Vercel îl servește automat, fără build.

1. Cont gratuit pe [vercel.com](https://vercel.com) (login cu GitHub).
2. **Add New Project** → alegi repo-ul `dariusserban/kingbistro` → Framework Preset **Other** → **Deploy** (fără build command).
3. Primești un link `…vercel.app` pentru test.
4. **Project Settings → Domains** → adaugi domeniul cumpărat; Vercel îți dă înregistrările DNS de pus la registrator, iar HTTPS vine automat.

Orice `git push` pe branch-ul `main` declanșează un deploy nou.
