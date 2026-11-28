"""Create and revoke the signed-in user's agent devices."""

from datetime import datetime
from uuid import UUID

from psycopg import errors
from psycopg.rows import class_row
from pydantic import BaseModel, Field

from somnia.api.auth import generate_device_token, hash_device_token
from somnia.db.client import Conn


class DeviceRecord(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    revoked_at: datetime | None


class CreatedDevice(BaseModel):
    device: DeviceRecord
    token: str


class DeviceName(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def list_devices(conn: Conn) -> list[DeviceRecord]:
    with conn.cursor(row_factory=class_row(DeviceRecord)) as cur:
        cur.execute(
            "select id, name, created_at, revoked_at from public.devices order by created_at desc"
        )
        return cur.fetchall()


def create_device(conn: Conn, name: str) -> CreatedDevice:
    token = generate_device_token()
    try:
        row = conn.execute(
            "select public.somnia_create_device(%s, %s)", (name, hash_device_token(token))
        ).fetchone()
    except errors.CheckViolation as exc:
        raise ValueError("invalid device") from exc
    if row is None:
        raise RuntimeError("device creation returned no id")
    device = next(item for item in list_devices(conn) if item.id == row[0])
    return CreatedDevice(device=device, token=token)


def revoke_device(conn: Conn, device_id: UUID) -> DeviceRecord | None:
    row = conn.execute(
        "update public.devices set revoked_at = now() where id = %s and revoked_at is null"
        " returning id",
        (device_id,),
    ).fetchone()
    if row is None:
        return next((item for item in list_devices(conn) if item.id == device_id), None)
    return next(item for item in list_devices(conn) if item.id == device_id)
