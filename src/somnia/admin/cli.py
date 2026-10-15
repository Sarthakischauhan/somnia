"""`somnia-admin create-device`: mint a per-device token (printed once, stored hashed)."""

import argparse
from uuid import UUID

import psycopg

from somnia.auth.tokens import generate_device_token, hash_device_token
from somnia.config import WorkerSettings


def main() -> None:
    parser = argparse.ArgumentParser(prog="somnia-admin")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-device", help="register a device for a user")
    create.add_argument("--user-id", type=UUID, required=True)
    create.add_argument("--name", required=True)
    args = parser.parse_args()

    settings = WorkerSettings()  # values come from the environment
    token = generate_device_token()
    with psycopg.connect(settings.service_database_url.get_secret_value()) as conn:
        row = conn.execute(
            "insert into public.devices (user_id, name, token_hash) values (%s, %s, %s)"
            " returning id",
            (args.user_id, args.name, hash_device_token(token)),
        ).fetchone()
    print(f"device_id={row[0] if row else '?'}")
    print(f"token={token}  (shown once; store it in the agent's SOMNIA_TOKEN)")
