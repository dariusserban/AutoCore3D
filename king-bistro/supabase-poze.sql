-- ============================================================
--  KING BISTRO — PARTEA 2: POZE (Supabase Storage)
--  Rulează DUPĂ „supabase-setup.sql", ca interogare SEPARATĂ.
--  (Ține separat, ca o eroare aici să nu anuleze partea esențială.)
-- ============================================================

-- Bucket public pentru pozele produselor
insert into storage.buckets (id, name, public)
values ('menu-photos', 'menu-photos', true)
on conflict (id) do update set public = true;

-- Oricine poate VEDEA pozele (sunt afișate pe site)
drop policy if exists kb_photos_read on storage.objects;
create policy kb_photos_read on storage.objects
  for select using (bucket_id = 'menu-photos');

-- Încărcarea de poze din panoul admin
drop policy if exists kb_photos_write on storage.objects;
create policy kb_photos_write on storage.objects
  for insert with check (bucket_id = 'menu-photos');

-- ============================================================
--  Dacă linia cu „create policy ... on storage.objects" dă eroare
--  („must be owner of table objects"), NU-i nimic: fă bucket-ul din
--  interfață — Storage → New bucket → nume „menu-photos" → bifează
--  „Public bucket" → Save. Apoi Storage → Policies → New policy →
--  „For full customization" → permite INSERT pentru rolul „anon".
-- ============================================================
