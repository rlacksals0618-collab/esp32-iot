"""Supabase 구현.

- 인증: Supabase Auth. 가입은 secret 키의 관리자 API로 '이메일 인증 완료' 상태로 만든다.
  (테스트용 프로젝트에서 인증 메일 없이 바로 로그인하기 위해서. 메일 인증이 필요하면 README 참고)
- DB: secret 키로 접근한다. 이 키는 RLS를 우회하므로, 누가 어떤 기기에 접근할 수 있는지는
  백엔드의 DeviceService가 검사한다. 테이블에는 RLS를 켜 두어 publishable 키로는 직접 읽을 수 없다.
"""
from datetime import datetime
from typing import Any

from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthError

from ..config import Settings
from ..exceptions import AppError, ConflictError, InvalidInputError, UnauthorizedError, UpstreamError
from .gateways import AuthSession, AuthUser, Row

_OPTIONS = ClientOptions(auto_refresh_token=False, persist_session=False)
_TIME_FIELDS = ("created_at", "last_seen_at", "led_updated_at")


def _auth_error(e: AuthError) -> AppError:
    code = getattr(e, "code", None)
    if code in ("email_exists", "user_already_exists"):
        return ConflictError("이미 가입된 이메일입니다.")
    if code in ("weak_password", "validation_failed", "email_address_invalid"):
        return InvalidInputError(f"입력값을 확인하세요: {e.message}")
    if code in ("invalid_credentials", "email_not_confirmed"):
        return UnauthorizedError("이메일 또는 비밀번호가 올바르지 않습니다.")
    if code in ("refresh_token_not_found", "refresh_token_already_used", "session_not_found", "session_expired"):
        return UnauthorizedError("로그인이 만료되었습니다. 다시 로그인하세요.")
    if isinstance(e, AuthApiError) and 400 <= e.status < 500:
        return InvalidInputError(e.message)
    return UpstreamError(f"인증 서버 오류: {e.message}")


def _session(session: Any) -> AuthSession:
    return AuthSession(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        user=AuthUser(id=session.user.id, email=session.user.email),
    )


class SupabaseAuth:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._admin = create_client(settings.supabase_url, settings.supabase_secret_key, options=_OPTIONS)

    def _public_client(self) -> Client:
        # 로그인하면 클라이언트 객체에 그 사용자의 세션이 저장된다.
        # 여러 사용자가 한 객체를 공유하면 세션이 섞이므로 요청마다 새로 만든다.
        return create_client(self._settings.supabase_url, self._settings.supabase_publishable_key, options=_OPTIONS)

    def sign_up(self, email: str, password: str) -> None:
        try:
            self._admin.auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
        except AuthError as e:
            raise _auth_error(e) from e

    def sign_in(self, email: str, password: str) -> AuthSession:
        try:
            res = self._public_client().auth.sign_in_with_password({"email": email, "password": password})
        except AuthError as e:
            raise _auth_error(e) from e
        return _session(res.session)

    def refresh(self, refresh_token: str) -> AuthSession:
        try:
            res = self._public_client().auth.refresh_session(refresh_token)
        except AuthError as e:
            raise _auth_error(e) from e
        return _session(res.session)

    def get_user(self, access_token: str) -> AuthUser | None:
        """Supabase Auth에 토큰을 보내 검증한다. (서명·만료·로그아웃 여부를 Supabase가 판단)"""
        try:
            res = self._admin.auth.get_user(access_token)
        except AuthError:
            return None
        if res is None or res.user is None:
            return None
        return AuthUser(id=res.user.id, email=res.user.email or "")


def _from_db(row: Row) -> Row:
    return {k: datetime.fromisoformat(v) if k in _TIME_FIELDS and isinstance(v, str) else v for k, v in row.items()}


def _to_db(fields: Row) -> Row:
    return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in fields.items()}


class SupabaseDeviceStore:
    def __init__(self, settings: Settings):
        self._db = create_client(settings.supabase_url, settings.supabase_secret_key, options=_OPTIONS)

    def _devices(self):
        return self._db.table("devices")

    def create_device(self, owner_id: str, name: str, key_hash: str) -> Row:
        res = self._devices().insert({"owner_id": owner_id, "name": name, "key_hash": key_hash}).execute()
        return _from_db(res.data[0])

    def list_devices(self, owner_id: str) -> list[Row]:
        res = self._devices().select("*").eq("owner_id", owner_id).order("created_at").execute()
        return [_from_db(r) for r in res.data]

    def get_device(self, device_id: str) -> Row | None:
        res = self._devices().select("*").eq("id", device_id).limit(1).execute()
        return _from_db(res.data[0]) if res.data else None

    def get_device_by_key_hash(self, key_hash: str) -> Row | None:
        res = self._devices().select("*").eq("key_hash", key_hash).limit(1).execute()
        return _from_db(res.data[0]) if res.data else None

    def update_device(self, device_id: str, fields: Row) -> Row:
        res = self._devices().update(_to_db(fields)).eq("id", device_id).execute()
        return _from_db(res.data[0])

    def delete_device(self, device_id: str) -> None:
        self._devices().delete().eq("id", device_id).execute()

    def add_reading(self, device_id: str, reading: Row) -> Row:
        res = self._db.table("sensor_readings").insert(_to_db({"device_id": device_id, **reading})).execute()
        return _from_db(res.data[0])

    def list_readings(self, device_id: str, limit: int, since: datetime | None = None) -> list[Row]:
        query = self._db.table("sensor_readings").select("*").eq("device_id", device_id)
        if since is not None:
            query = query.gt("created_at", since.isoformat())
        res = query.order("created_at", desc=True).limit(limit).execute()
        return [_from_db(r) for r in res.data]
