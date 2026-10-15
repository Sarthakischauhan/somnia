-- Every dream_runs row with stats belongs to exactly one user. A scheduled or
-- pg_cron run writes one row per user it processed; a global request row
-- (user_id null, from somnia_request_dream) is only a marker and carries no stats.
-- started_at/finished_at are wall-clock; logical_now is the time used for decay.
alter table public.dream_runs
    add column parent_run_id uuid references public.dream_runs (id),
    add column logical_now timestamptz;
create index dream_runs_user_idx on public.dream_runs (user_id, requested_at desc);

alter table public.dream_runs
    add constraint dream_runs_stats_need_user check (
        user_id is not null
        or (sessions_processed = 0 and checkpoints_created = 0 and memories_added = 0
            and memories_merged = 0 and memories_superseded = 0 and memories_decayed = 0)
    ) not valid;

drop policy dream_runs_read on public.dream_runs;
create policy dream_runs_owner_read on public.dream_runs for select to authenticated
    using (user_id = (select auth.uid()));
