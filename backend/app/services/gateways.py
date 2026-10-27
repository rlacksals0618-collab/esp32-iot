"""외부 저장소(Supabase)와의 경계.

서비스는 이 인터페이스에만 의존한다. 구현은 두 가지다.
- supabase_gateway.py : 실제 Supabase (Auth + Postgres)
- memory_gateway.py   : 메모리 저장 (테스트, Supabase 없이 로컬 실행)
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthUser


class AuthGateway(Protocol):
    def sign_up(self, email: str, password: str) -> None: ...
    def sign_in(self, email: str, password: str) -> AuthSession: ...
    def refresh(self, refresh_token: str) -> AuthSession: ...
    def get_user(self, access_token: str) -> AuthUser | None: ...


# devices 행: id, owner_id, name, key_hash, led_on, led_reported, led_updated_at, last_seen_at, created_at
# sensor_readings 행: id, device_id, temperature, light, rssi, led_on, created_at
# 시간 값은 항상 timezone 있는 datetime으로 주고받는다.
Row = dict[str, Any]


class DeviceStore(Protocol):
    def create_device(self, owner_id: str, name: str, key_hash: str) -> Row: ...
    def list_devices(self, owner_id: str) -> list[Row]: ...
    def get_device(self, device_id: str) -> Row | None: ...
    def get_device_by_key_hash(self, key_hash: str) -> Row | None: ...
    def update_device(self, device_id: str, fields: Row) -> Row: ...
    def delete_device(self, device_id: str) -> None: ...
    def add_reading(self, device_id: str, reading: Row) -> Row: ...
    def list_readings(self, device_id: str, limit: int, since: datetime | None = None) -> list[Row]: ...
