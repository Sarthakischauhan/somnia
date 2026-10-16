-- Compound (timestamp, id) rebuild cursor: rows sharing the last timestamp are no longer skipped.
alter table public.project_profiles
    add column memories_through_id uuid,
    add column checkpoints_through_id uuid;
