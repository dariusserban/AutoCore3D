-- ============================================================
--  KING BISTRO — PARTEA 1 (ESENȚIALĂ): comenzi, meniu, setări
--  Supabase → SQL Editor → New query → lipește TOT → RUN
--  Se poate rula de câte ori vrei (nu strică datele existente).
--  ⚠️ Rulează ÎNTÂI acest fișier. Pozele sunt în „supabase-poze.sql", separat,
--     ca o eventuală eroare la poze să NU anuleze partea asta.
-- ============================================================

-- 1) TABELE ---------------------------------------------------
create table if not exists kb_settings (
  id   int primary key default 1,
  data jsonb not null,
  constraint kb_settings_one_row check (id = 1)
);
create table if not exists kb_categories (
  id text primary key, name text not null, note text default '', pos int default 0
);
create table if not exists kb_items (
  id text primary key, cat text not null, name text not null,
  price numeric not null default 0, emoji text default '🍽️', img text,
  badge text default '', spicy boolean default false, available boolean default true,
  descr text default '', ing jsonb default '[]'::jsonb, pos int default 0
);
create table if not exists kb_orders (
  id text primary key, ts bigint not null, items jsonb not null,
  total numeric not null, client jsonb not null, note text default '',
  status text not null default 'noua'
);

-- 2) SECURITATE (Row Level Security) --------------------------
alter table kb_settings   enable row level security;
alter table kb_categories enable row level security;
alter table kb_items      enable row level security;
alter table kb_orders     enable row level security;

-- Meniul + setările: citire publică
drop policy if exists kb_pub_read_settings on kb_settings;
drop policy if exists kb_pub_read_cats     on kb_categories;
drop policy if exists kb_pub_read_items    on kb_items;
create policy kb_pub_read_settings on kb_settings   for select using (true);
create policy kb_pub_read_cats     on kb_categories for select using (true);
create policy kb_pub_read_items    on kb_items      for select using (true);

-- Meniul + setările: scriere permisă (în panou o protejează parola)
drop policy if exists kb_write_settings on kb_settings;
drop policy if exists kb_write_cats     on kb_categories;
drop policy if exists kb_write_items    on kb_items;
create policy kb_write_settings on kb_settings   for all using (true) with check (true);
create policy kb_write_cats     on kb_categories for all using (true) with check (true);
create policy kb_write_items    on kb_items      for all using (true) with check (true);

-- Comenzi: clientul poate DOAR să insereze (nu poate citi comenzile altora)
drop policy if exists kb_insert_orders on kb_orders;
create policy kb_insert_orders on kb_orders for insert with check (true);

-- 3) CITIREA / ADMINISTRAREA COMENZILOR — doar cu parola -------
create or replace function kb_orders_list(pw text)
  returns setof kb_orders language plpgsql security definer set search_path = public as $$
begin
  if pw is distinct from 'kingbistro2026' then raise exception 'Parolă greșită'; end if;
  return query select * from kb_orders order by ts desc;
end $$;
create or replace function kb_orders_status(pw text, oid text, st text)
  returns void language plpgsql security definer set search_path = public as $$
begin
  if pw is distinct from 'kingbistro2026' then raise exception 'Parolă greșită'; end if;
  update kb_orders set status = st where id = oid;
end $$;
create or replace function kb_orders_delete(pw text, oid text)
  returns void language plpgsql security definer set search_path = public as $$
begin
  if pw is distinct from 'kingbistro2026' then raise exception 'Parolă greșită'; end if;
  delete from kb_orders where id = oid;
end $$;
grant execute on function kb_orders_list(text)             to anon;
grant execute on function kb_orders_status(text,text,text) to anon;
grant execute on function kb_orders_delete(text,text)      to anon;

-- ============================================================
--  Gata PARTEA 1. Ar trebui să scrie „Success". Acum, în panou →
--  Setări → „Testează conexiunea": testele 1–4 trebuie să fie verzi.
--  Pentru poze (testul 5), rulează separat „supabase-poze.sql".
-- ============================================================
