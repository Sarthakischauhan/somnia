-- Minimal stand-in for the Supabase platform objects the migrations rely on,
-- so the migrations can run against a plain postgres + pgvector server (tests/CI).
-- Everything is idempotent; on a real Supabase database it is a no-op.
create schema if not exists extensions;
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key, email text);

create or replace function auth.uid() returns uuid
language sql stable as $$
    select nullif(
        nullif(current_setting('request.jwt.claims', true), '')::json ->> 'sub', ''
    )::uuid
$$;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin bypassrls;
    end if;
end
$$;
grant usage on schema auth to authenticated, anon;
grant execute on function auth.uid() to authenticated, anon;
