-- Task references must belong to the same actor even with direct Supabase access.
alter policy tasks_owner_insert on public.tasks with check (
    user_id = (select auth.uid())
    and (session_id is null or exists (
        select 1 from public.sessions s
        where s.id = tasks.session_id and s.user_id = tasks.user_id
    ))
    and exists (
        select 1 from public.devices d
        where d.id = tasks.created_by_device and d.user_id = tasks.user_id
    )
);

create index tasks_open_context_idx on public.tasks (user_id, repo, branch, session_id)
    where status in ('queued', 'running');

alter table public.dream_runs
    add column attempts integer not null default 0,
    add column available_at timestamptz not null default now();

-- Recover old claims after stopping the old worker. An existing pending repo job
-- covers the same work, so leave it queued and record overlapping claims as failed.
with stranded as (
    select r.id, r.repo, row_number() over (
        partition by r.user_id, r.repo order by r.requested_at, r.id
    ) as position,
    exists (
        select 1 from public.dream_runs pending
        where pending.status = 'requested' and pending.user_id = r.user_id
            and pending.repo = r.repo
    ) as has_pending
    from public.dream_runs r where r.status = 'running'
)
update public.dream_runs r
set status = case when s.repo is not null and (s.has_pending or s.position > 1)
                  then 'failed' else 'requested' end,
    error = 'Recovered during worker upgrade'
from stranded s where r.id = s.id;
