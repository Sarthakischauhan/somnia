-- Core schema for somnia: devices, sessions, events, chunks, tasks, memories,
-- checkpoints, dream_runs. Embeddings are 1536-d (text-embedding-3-small size).
create extension if not exists vector with schema extensions;

create table public.devices (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    token_hash text not null unique,
    created_at timestamptz not null default now(),
    revoked_at timestamptz
);
create index devices_user_idx on public.devices (user_id);

create table public.sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    device_id uuid not null references public.devices (id),
    repo text not null,
    branch text not null,
    git_ref text,
    status text not null default 'open' check (status in ('open', 'closed')),
    started_at timestamptz not null default now(),
    last_event_at timestamptz,
    ended_at timestamptz,
    dreamed_through_seq integer not null default 0
);
create index sessions_repo_branch_idx on public.sessions (user_id, repo, branch, started_at desc);

create table public.events (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    session_id uuid not null references public.sessions (id),
    seq integer not null check (seq > 0),
    kind text not null check (kind in ('message', 'tool_call', 'files_touched', 'git_ref')),
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    processed_at timestamptz,
    constraint events_session_seq_key unique (session_id, seq)
);
create index events_unprocessed_idx on public.events (id) where processed_at is null;

create table public.chunks (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    session_id uuid not null references public.sessions (id),
    event_id bigint not null references public.events (id),
    ord integer not null,
    content text not null,
    redactions integer not null default 0,
    embedding extensions.vector(1536) not null,
    created_at timestamptz not null default now(),
    constraint chunks_event_ord_key unique (event_id, ord)
);
create index chunks_embedding_idx on public.chunks
    using hnsw (embedding extensions.vector_cosine_ops);

-- Agent-visible task queue (claimed with FOR UPDATE SKIP LOCKED).
create table public.tasks (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    created_by_device uuid not null references public.devices (id),
    session_id uuid references public.sessions (id),
    repo text,
    branch text,
    title text not null,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'queued'
        check (status in ('queued', 'running', 'done', 'failed')),
    priority integer not null default 0,
    attempts integer not null default 0,
    claimed_by_device uuid references public.devices (id),
    locked_until timestamptz,
    result jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index tasks_claim_idx on public.tasks (user_id, priority desc, created_at)
    where status in ('queued', 'running');

create table public.memories (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    type text not null check (type in ('fact', 'decision', 'convention', 'gotcha', 'todo')),
    scope text not null check (scope in ('global', 'repo', 'branch')),
    repo text,
    branch text,
    content text not null,
    embedding extensions.vector(1536) not null,
    confidence real not null default 0.5 check (confidence >= 0 and confidence <= 1),
    use_count integer not null default 0,
    last_used_at timestamptz,
    last_decayed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    superseded_by uuid references public.memories (id),
    source_session_ids uuid[] not null default '{}',
    constraint memories_scope_repo check (scope = 'global' or repo is not null),
    constraint memories_scope_branch check (scope <> 'branch' or branch is not null)
);
create index memories_active_idx on public.memories (user_id, repo, branch)
    where superseded_by is null;
create index memories_embedding_idx on public.memories
    using hnsw (embedding extensions.vector_cosine_ops);

create table public.checkpoints (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    session_id uuid references public.sessions (id),
    repo text not null,
    branch text not null,
    goal text not null,
    state text not null,
    next_steps text[] not null default '{}',
    files_touched text[] not null default '{}',
    git_ref text,
    pushed boolean not null default false,
    status text not null default 'open' check (status in ('open', 'closed')),
    source text not null check (source in ('agent', 'dream')),
    created_at timestamptz not null default now()
);
create index checkpoints_open_idx on public.checkpoints (user_id, repo, branch, created_at desc)
    where status = 'open';

create table public.dream_runs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users (id) on delete cascade,
    trigger text not null check (trigger in ('schedule', 'pg_cron', 'manual')),
    status text not null default 'requested'
        check (status in ('requested', 'running', 'succeeded', 'failed')),
    requested_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz,
    sessions_processed integer not null default 0,
    checkpoints_created integer not null default 0,
    memories_added integer not null default 0,
    memories_merged integer not null default 0,
    memories_superseded integer not null default 0,
    memories_decayed integer not null default 0,
    error text
);
