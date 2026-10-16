-- Project profiles, event-triggered (debounced) repo dreams, and contradiction tracking.

-- ---------------------------------------------------------------- project profiles
-- One profile per (user, repo). Entries are the sections' contents, each with provenance.
create table public.project_profiles (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    repo text not null,
    -- incremental rebuild watermarks (null = never built): newest memories.updated_at /
    -- checkpoints.created_at already folded into the profile
    memories_through timestamptz,
    checkpoints_through timestamptz,
    version integer not null default 0,
    updated_at timestamptz not null default now(),
    constraint project_profiles_user_repo_key unique (user_id, repo)
);

create table public.project_profile_entries (
    id uuid primary key default gen_random_uuid(),
    profile_id uuid not null references public.project_profiles (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    section text not null check (section in
        ('stack', 'conventions', 'architecture', 'decisions', 'open_work', 'pitfalls')),
    content text not null,
    confidence real not null check (confidence >= 0 and confidence <= 1),
    source_memory_id uuid references public.memories (id),
    source_checkpoint_id uuid references public.checkpoints (id),
    source_branch text,
    source_session_ids uuid[] not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    retired_at timestamptz,
    constraint profile_entry_has_source check (
        (source_memory_id is not null) <> (source_checkpoint_id is not null)
    )
);
create unique index profile_entries_memory_key on public.project_profile_entries
    (profile_id, source_memory_id) where source_memory_id is not null;
create index profile_entries_active_idx on public.project_profile_entries (profile_id, section)
    where retired_at is null;

alter table public.project_profiles enable row level security;
alter table public.project_profile_entries enable row level security;
grant select on public.project_profiles, public.project_profile_entries to authenticated;
create policy project_profiles_owner_read on public.project_profiles for select
    to authenticated using (user_id = (select auth.uid()));
create policy profile_entries_owner_read on public.project_profile_entries for select
    to authenticated using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------- conflicts
-- A candidate memory that contradicted an existing one. Both rows are kept; nothing is
-- deleted. outcome is the reconciler's decision; flagged conflicts wait for a human.
create table public.memory_conflicts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    repo text,
    existing_memory_id uuid not null references public.memories (id),
    candidate_memory_id uuid not null references public.memories (id),
    outcome text not null check (outcome in ('superseded', 'coexist', 'flagged')),
    rationale text not null default '',
    session_id uuid references public.sessions (id),
    status text not null check (status in ('open', 'resolved')),
    resolution text check (resolution in ('keep_existing', 'keep_candidate', 'keep_both')),
    created_at timestamptz not null default now(),
    resolved_at timestamptz,
    constraint conflict_resolution_when_resolved check (
        outcome <> 'flagged' or (status = 'resolved') = (resolution is not null)
    )
);
create index memory_conflicts_open_idx on public.memory_conflicts (user_id, created_at desc)
    where status = 'open';

alter table public.memory_conflicts enable row level security;
grant select on public.memory_conflicts to authenticated;
create policy memory_conflicts_owner_read on public.memory_conflicts for select
    to authenticated using (user_id = (select auth.uid()));

-- Resolving touches memories.superseded_by, which the API role may not update directly,
-- so resolution goes through one owner-checked SECURITY DEFINER function.
create function public.somnia_resolve_conflict(p_conflict_id uuid, p_resolution text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    c public.memory_conflicts%rowtype;
begin
    if p_resolution not in ('keep_existing', 'keep_candidate', 'keep_both') then
        raise exception 'invalid resolution %', p_resolution using errcode = '22023';
    end if;
    select * into c from public.memory_conflicts
        where id = p_conflict_id and user_id = (select auth.uid()) for update;
    if not found then
        return null;
    end if;
    if c.status <> 'open' then
        raise exception 'conflict already resolved' using errcode = '55000';
    end if;
    if p_resolution = 'keep_existing' then
        update public.memories set superseded_by = c.existing_memory_id, updated_at = now()
            where id = c.candidate_memory_id and superseded_by is null;
    elsif p_resolution = 'keep_candidate' then
        update public.memories set superseded_by = c.candidate_memory_id, updated_at = now()
            where id = c.existing_memory_id and superseded_by is null;
    end if;
    update public.memory_conflicts
        set status = 'resolved', resolution = p_resolution, resolved_at = now()
        where id = c.id;
    return c.id;
end
$$;
revoke all on function public.somnia_resolve_conflict(uuid, text) from public;
grant execute on function public.somnia_resolve_conflict(uuid, text) to authenticated;

-- ---------------------------------------------------------------- dream runs
alter table public.dream_runs
    add column repo text,
    add column coalesced integer not null default 0,
    add column conflicts_flagged integer not null default 0,
    add column memories_coexisting integer not null default 0,
    add column profile_entries_changed integer not null default 0;
alter table public.dream_runs drop constraint dream_runs_trigger_check;
alter table public.dream_runs add constraint dream_runs_trigger_check check (trigger in
    ('schedule', 'pg_cron', 'manual', 'session_end', 'idle', 'chunk_threshold'));
-- Debounce: at most one pending dream per (user, repo); later triggers coalesce into it.
create unique index dream_runs_pending_repo_key on public.dream_runs (user_id, repo)
    where status = 'requested' and repo is not null;

create function public.somnia_enqueue_repo_dream(p_user_id uuid, p_repo text, p_trigger text)
returns uuid
language sql
security definer
set search_path = ''
as $$
    insert into public.dream_runs (user_id, repo, trigger, status)
    values (p_user_id, p_repo, p_trigger, 'requested')
    on conflict (user_id, repo) where status = 'requested' and repo is not null
    do update set coalesced = public.dream_runs.coalesced + 1
    returning id
$$;
revoke all on function public.somnia_enqueue_repo_dream(uuid, text, text) from public;

-- Session end -> repo dream. A trigger keeps the API role free of dream_runs writes.
create function public.somnia_session_closed_dream()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    perform public.somnia_enqueue_repo_dream(new.user_id, new.repo, 'session_end');
    return new;
end
$$;
create trigger sessions_closed_enqueue_dream
    after update of status on public.sessions
    for each row when (old.status = 'open' and new.status = 'closed')
    execute function public.somnia_session_closed_dream();
