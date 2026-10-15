-- Local development seed (supabase db reset). NEVER use these credentials in production.
-- Dev device token: smn_dev_local_token_change_me
alter role somnia_api login password 'somnia_api_local';

insert into auth.users (id, email)
values ('00000000-0000-0000-0000-00000000d0e5', 'dev@somnia.local')
on conflict (id) do nothing;

insert into public.devices (id, user_id, name, token_hash)
values (
    '00000000-0000-0000-0000-0000000de71c',
    '00000000-0000-0000-0000-00000000d0e5',
    'local-dev',
    encode(sha256('smn_dev_local_token_change_me'::bytea), 'hex')
)
on conflict (id) do nothing;
