-- Dream scheduling hook. The worker polls dream_runs for status = 'requested'.
-- If pg_cron is enabled (Supabase: Database > Extensions), schedule a request
-- every 6 hours. Without pg_cron the worker's own interval timer still runs.
create function public.somnia_request_dream(p_trigger text default 'pg_cron')
returns uuid
language sql
security definer
set search_path = ''
as $$
    insert into public.dream_runs (trigger, status)
    values (p_trigger, 'requested')
    returning id
$$;
revoke all on function public.somnia_request_dream(text) from public;

do $$
begin
    if exists (select 1 from pg_extension where extname = 'pg_cron') then
        perform cron.schedule(
            'somnia-dream',
            '0 */6 * * *',
            $cron$select public.somnia_request_dream('pg_cron')$cron$
        );
    end if;
end
$$;
