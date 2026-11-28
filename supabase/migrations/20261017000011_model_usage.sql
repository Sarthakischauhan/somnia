-- Provider usage recorded by the worker. Costs use published catalog rates;
-- historical calls made before this table existed cannot be reconstructed.

create table public.model_usage (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    provider text not null,
    model text not null,
    operation text not null check (operation in ('chat', 'embedding')),
    requests integer not null default 1 check (requests > 0),
    input_tokens integer not null default 0 check (input_tokens >= 0),
    output_tokens integer not null default 0 check (output_tokens >= 0),
    reasoning_tokens integer not null default 0 check (reasoning_tokens >= 0),
    cache_read_tokens integer not null default 0 check (cache_read_tokens >= 0),
    cache_write_tokens integer not null default 0 check (cache_write_tokens >= 0),
    cost_usd numeric(14, 8) not null check (cost_usd >= 0),
    created_at timestamptz not null default now()
);
create index model_usage_user_time_idx on public.model_usage (user_id, created_at desc);

alter table public.model_usage enable row level security;
grant select on public.model_usage to authenticated;
create policy model_usage_owner_read on public.model_usage for select to authenticated
    using (user_id = (select auth.uid()));

create function public.somnia_usage_summary(p_since timestamptz)
returns table (
    provider text,
    model text,
    operation text,
    requests bigint,
    input_tokens bigint,
    output_tokens bigint,
    reasoning_tokens bigint,
    cache_read_tokens bigint,
    cache_write_tokens bigint,
    cost_usd numeric
)
language sql
stable
security invoker
set search_path = ''
as $$
    select provider, model, operation, count(*)::bigint, coalesce(sum(input_tokens), 0)::bigint,
        coalesce(sum(output_tokens), 0)::bigint, coalesce(sum(reasoning_tokens), 0)::bigint,
        coalesce(sum(cache_read_tokens), 0)::bigint, coalesce(sum(cache_write_tokens), 0)::bigint,
        coalesce(sum(cost_usd), 0)
    from public.model_usage
    where created_at >= p_since
    group by provider, model, operation
$$;
revoke all on function public.somnia_usage_summary(timestamptz) from public;
grant execute on function public.somnia_usage_summary(timestamptz) to authenticated;
