-- Sequence numbers can arrive out of order. Preserve existing progress, then track
-- which events were actually consolidated rather than inferring it from their sequence.
alter table public.events add column dreamed boolean not null default false;

update public.events e set dreamed = true
from public.sessions s
where e.session_id = s.id and e.seq <= s.dreamed_through_seq;

create index events_undreamt_session_seq_idx on public.events (session_id, seq)
where not dreamed;

-- Only service workers can set ingestion and consolidation state.
revoke insert on public.events from authenticated;
grant insert (user_id, session_id, seq, kind, payload) on public.events to authenticated;
