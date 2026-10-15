-- Row level security by user_id. The API connects as `somnia_api` and runs every
-- request as `authenticated` with request.jwt.claims.sub = the device's user_id.
-- The worker uses the service connection (table owner / service_role, bypasses RLS).
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'somnia_api') then
        create role somnia_api nologin noinherit;
    end if;
end
$$;
grant authenticated to somnia_api;
grant usage on schema public, extensions to authenticated;

alter table public.devices enable row level security;
alter table public.sessions enable row level security;
alter table public.events enable row level security;
alter table public.chunks enable row level security;
alter table public.tasks enable row level security;
alter table public.memories enable row level security;
alter table public.checkpoints enable row level security;
alter table public.dream_runs enable row level security;

revoke all on all tables in schema public from anon, authenticated;

-- devices: owners can list their devices but never read token hashes.
grant select (id, user_id, name, created_at, revoked_at) on public.devices to authenticated;
create policy devices_owner_read on public.devices for select to authenticated
    using (user_id = (select auth.uid()));

grant select, insert on public.sessions to authenticated;
grant update (git_ref, status, last_event_at, ended_at) on public.sessions to authenticated;
create policy sessions_owner_read on public.sessions for select to authenticated
    using (user_id = (select auth.uid()));
create policy sessions_owner_insert on public.sessions for insert to authenticated
    with check (
        user_id = (select auth.uid())
        and exists (select 1 from public.devices d
                    where d.id = device_id and d.user_id = (select auth.uid()))
    );
create policy sessions_owner_update on public.sessions for update to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert on public.events to authenticated;
create policy events_owner_read on public.events for select to authenticated
    using (user_id = (select auth.uid()));
create policy events_owner_insert on public.events for insert to authenticated
    with check (
        user_id = (select auth.uid())
        and exists (select 1 from public.sessions s where s.id = session_id)
    );

grant select on public.chunks to authenticated;
create policy chunks_owner_read on public.chunks for select to authenticated
    using (user_id = (select auth.uid()));

grant select, insert on public.tasks to authenticated;
grant update (status, attempts, claimed_by_device, locked_until, result, updated_at)
    on public.tasks to authenticated;
create policy tasks_owner_read on public.tasks for select to authenticated
    using (user_id = (select auth.uid()));
create policy tasks_owner_insert on public.tasks for insert to authenticated
    with check (user_id = (select auth.uid()));
create policy tasks_owner_update on public.tasks for update to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select on public.memories to authenticated;
grant update (last_used_at, use_count) on public.memories to authenticated;
create policy memories_owner_read on public.memories for select to authenticated
    using (user_id = (select auth.uid()));
create policy memories_owner_touch on public.memories for update to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert on public.checkpoints to authenticated;
grant update (status) on public.checkpoints to authenticated;
create policy checkpoints_owner_read on public.checkpoints for select to authenticated
    using (user_id = (select auth.uid()));
create policy checkpoints_owner_insert on public.checkpoints for insert to authenticated
    with check (user_id = (select auth.uid()));
create policy checkpoints_owner_update on public.checkpoints for update to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select on public.dream_runs to authenticated;
create policy dream_runs_owner_read on public.dream_runs for select to authenticated
    using (user_id = (select auth.uid()));

-- Token -> user resolution. SECURITY DEFINER so the API never needs to read
-- devices.token_hash directly; only somnia_api may call it.
create function public.somnia_resolve_device(p_token_hash text)
returns table (device_id uuid, user_id uuid)
language sql
stable
security definer
set search_path = ''
as $$
    select d.id, d.user_id
    from public.devices d
    where d.token_hash = p_token_hash and d.revoked_at is null
$$;
revoke all on function public.somnia_resolve_device(text) from public;
grant execute on function public.somnia_resolve_device(text) to somnia_api;
