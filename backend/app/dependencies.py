"""공통 Depends.

- AuthGatewayDep / DeviceStoreDep : APP_MODE에 맞는 저장소 구현 (테스트에서는 dependency_overrides로 바꾼다)
- CurrentUser   : 대시보드 요청. Authorization: Bearer <Supabase access token> 검증. 실패하면 401
- CurrentDevice : 보드 요청. X-Device-Key 헤더로 기기를 찾는다. 실패하면 401
"""
import hashlib
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .exceptions import UnauthorizedError
from .services.gateways import AuthGateway, AuthUser, DeviceStore, Row


@lru_cache
def get_auth_gateway() -> AuthGateway:
    settings = get_settings()
    if settings.app_mode == "memory":
        from .services.memory_gateway import MemoryAuth

        return MemoryAuth()
    from .services.supabase_gateway import SupabaseAuth

    return SupabaseAuth(settings)


@lru_cache
def get_device_store() -> DeviceStore:
    settings = get_settings()
    if settings.app_mode == "memory":
        from .services.memory_gateway import MemoryDeviceStore

        return MemoryDeviceStore()
    from .services.supabase_gateway import SupabaseDeviceStore

    return SupabaseDeviceStore(settings)


AuthGatewayDep = Annotated[AuthGateway, Depends(get_auth_gateway)]
DeviceStoreDep = Annotated[DeviceStore, Depends(get_device_store)]

# Swagger(/docs)의 Authorize 버튼에 access token을 붙여 넣을 수 있게 된다.
bearer_scheme = HTTPBearer(auto_error=False, description="로그인 응답의 access_token")


def get_current_user(
    auth: AuthGatewayDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthUser:
    if credentials is None:
        raise UnauthorizedError("로그인이 필요합니다.")
    user = auth.get_user(credentials.credentials)
    if user is None:
        raise UnauthorizedError("로그인 정보가 유효하지 않습니다. 다시 로그인하세요.")
    return user


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]


def hash_device_key(device_key: str) -> str:
    # 기기 키는 충분히 긴 무작위 값이라 빠른 해시(SHA-256)로도 안전하다. DB에는 해시만 저장한다.
    return hashlib.sha256(device_key.encode()).hexdigest()


def get_current_device(
    store: DeviceStoreDep,
    x_device_key: Annotated[str | None, Header(description="기기 등록 때 받은 키")] = None,
) -> Row:
    if not x_device_key:
        raise UnauthorizedError("X-Device-Key 헤더가 필요합니다.")
    device = store.get_device_by_key_hash(hash_device_key(x_device_key))
    if device is None:
        raise UnauthorizedError("등록되지 않은 기기 키입니다.")
    return device


CurrentDevice = Annotated[Row, Depends(get_current_device)]
