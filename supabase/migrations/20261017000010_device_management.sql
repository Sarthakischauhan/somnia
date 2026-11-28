-- Dashboard users can create and revoke their own devices. Token hashes stay
-- inaccessible: creation returns the raw token once through a security definer.

grant update (revoked_at) on public.devices to authenticated;
create policy devices_owner_revoke on public.devices for update to authenticated
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));

create function public.somnia_create_device(p_name text, p_token_hash text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    created uuid;
begin
    if (select auth.uid()) is null then
        raise exception 'sign-in required' using errcode = '42501';
    end if;
    if char_length(btrim(p_name)) not between 1 and 80
        or char_length(p_token_hash) <> 64 then
        raise exception 'invalid device' using errcode = '22023';
    end if;
    insert into public.devices (user_id, name, token_hash)
    values ((select auth.uid()), btrim(p_name), p_token_hash)
    returning id into created;
    return created;
end
$$;
revoke all on function public.somnia_create_device(text, text) from public;
grant execute on function public.somnia_create_device(text, text) to authenticated;
