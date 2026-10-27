"""메모리 구현. 테스트와 Supabase 없이 로컬에서 실행할 때(APP_MODE=memory) 쓴다.

서버를 다시 켜면 모든 데이터가 사라진다. 실제 배포에는 쓰지 않는다.
"""
import hashlib
import secrets
import threading
import uuid
from datetime import UTC, datetime

from ..exceptions import ConflictError, UnauthorizedError
from .gateways import AuthSession, AuthUser, Row


def _now() -> datetime:
    return datetime.now(UTC)


class MemoryAuth:
    def __init__(self, token_ttl_s: int = 3600):
        self._users: dict[str, dict] = {}  # email -> {id, email, password_hash}
        self._access: dict[str, str] = {}  # access_token -> user_id
        self._refresh: dict[str, str] = {}  # refresh_token -> user_id
        self._ttl = token_ttl_s
        self._lock = threading.Lock()

    @staticmethod
    def _hash(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()

    def sign_up(self, email: str, password: str) -> None:
        with self._lock:
            if email in self._users:
                raise ConflictError("이미 가입된 이메일입니다.")
            salt = secrets.token_hex(16)
            self._users[email] = {"id": str(uuid.uuid4()), "email": email, "salt": salt, "hash": self._hash(password, salt)}

    def _issue(self, user: dict) -> AuthSession:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._access[access] = user["id"]
        self._refresh[refresh] = user["id"]
        return AuthSession(access, refresh, self._ttl, AuthUser(user["id"], user["email"]))

    def sign_in(self, email: str, password: str) -> AuthSession:
        with self._lock:
            user = self._users.get(email)
            if user is None or not secrets.compare_digest(user["hash"], self._hash(password, user["salt"])):
                raise UnauthorizedError("이메일 또는 비밀번호가 올바르지 않습니다.")
            return self._issue(user)

    def refresh(self, refresh_token: str) -> AuthSession:
        with self._lock:
            user_id = self._refresh.pop(refresh_token, None)  # 한 번 쓴 refresh token은 폐기
            user = next((u for u in self._users.values() if u["id"] == user_id), None)
            if user is None:
                raise UnauthorizedError("로그인이 만료되었습니다. 다시 로그인하세요.")
            return self._issue(user)

    def get_user(self, access_token: str) -> AuthUser | None:
        user_id = self._access.get(access_token)
        user = next((u for u in self._users.values() if u["id"] == user_id), None)
        return AuthUser(user["id"], user["email"]) if user else None


class MemoryDeviceStore:
    def __init__(self):
        self._devices: dict[str, Row] = {}
        self._readings: list[Row] = []
        self._lock = threading.Lock()

    def create_device(self, owner_id: str, name: str, key_hash: str) -> Row:
        with self._lock:
            if any(d["key_hash"] == key_hash for d in self._devices.values()):
                raise ConflictError("기기 키가 중복되었습니다.")
            device = {
                "id": str(uuid.uuid4()), "owner_id": owner_id, "name": name, "key_hash": key_hash,
                "led_on": False, "led_reported": None, "led_updated_at": None, "last_seen_at": None,
                "created_at": _now(),
            }
            self._devices[device["id"]] = device
            return dict(device)

    def list_devices(self, owner_id: str) -> list[Row]:
        rows = [dict(d) for d in self._devices.values() if d["owner_id"] == owner_id]
        return sorted(rows, key=lambda d: d["created_at"])

    def get_device(self, device_id: str) -> Row | None:
        device = self._devices.get(device_id)
        return dict(device) if device else None

    def get_device_by_key_hash(self, key_hash: str) -> Row | None:
        return next((dict(d) for d in self._devices.values() if d["key_hash"] == key_hash), None)

    def update_device(self, device_id: str, fields: Row) -> Row:
        with self._lock:
            self._devices[device_id].update(fields)
            return dict(self._devices[device_id])

    def delete_device(self, device_id: str) -> None:
        with self._lock:
            self._devices.pop(device_id, None)
            self._readings = [r for r in self._readings if r["device_id"] != device_id]

    def add_reading(self, device_id: str, reading: Row) -> Row:
        with self._lock:
            row = {"id": len(self._readings) + 1, "device_id": device_id, "created_at": _now(), **reading}
            self._readings.append(row)
            return dict(row)

    def list_readings(self, device_id: str, limit: int, since: datetime | None = None) -> list[Row]:
        rows = [r for r in self._readings if r["device_id"] == device_id and (since is None or r["created_at"] > since)]
        return [dict(r) for r in sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]]
