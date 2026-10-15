-- Admin surface: soft archive for memories, user-editable confidence, user-scoped
-- dream requests and a schedule probe. Still RLS: users only see/modify their rows.
alter table public.memories add column archived_at timestamptz;
drop index if exists public.memories_active_idx;
create index memories_active_idx on public.memories (user_id, repo, branch)
    where superseded_by is null and archived_at is null;

grant update (confidence, archived_at, updated_at) on public.memories to authenticated;

-- Scheduled/global runs (user_id null) are visible to every user; per-user runs to their owner.
drop policy dream_runs_owner_read on public.dream_runs;
create policy dream_runs_read on public.dream_runs for select to authenticated
    using (user_id is null or user_id = (select auth.uid()));

create function public.somnia_request_user_dream()
returns uuid
language sql
security definer
set search_path = ''
as $$
    insert into public.dream_runs (user_id, trigger, status)
    values ((select auth.uid()), 'manual', 'requested')
    returning id
$$;
revoke all on function public.somnia_request_user_dream() from public;
grant execute on function public.somnia_request_user_dream() to authenticated;

-- pg_cron job for the dream hook, if pg_cron is installed (cron.job is not user-readable).
create function public.somnia_dream_cron_schedule()
returns text
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    result text;
begin
    if not exists (select 1 from pg_extension where extname = 'pg_cron') then
        return null;
    end if;
    execute 'select schedule from cron.job where jobname = $1 limit 1'
        into result using 'somnia-dream';
    return result;
end
$$;
revoke all on function public.somnia_dream_cron_schedule() from public;
grant execute on function public.somnia_dream_cron_schedule() to authenticated;
