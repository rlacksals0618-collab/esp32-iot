"""대시보드용: 내 기기 관리, LED 제어, 센서값 조회. 모두 로그인 필요, 본인 기기만."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, status

from ..dependencies import CurrentUser
from ..schemas.device import DeviceCreate, DeviceOut, DeviceWithKey, LedUpdate, ReadingOut
from ..services.device_service import DeviceServiceDep

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(user: CurrentUser, service: DeviceServiceDep):
    """내 기기 목록. 각 기기의 온라인 여부와 최신 센서값이 함께 온다."""
    return service.list_devices(user)


@router.post("", response_model=DeviceWithKey, status_code=status.HTTP_201_CREATED)
def create_device(data: DeviceCreate, user: CurrentUser, service: DeviceServiceDep):
    """기기 등록. 응답의 device_key를 보드 펌웨어(secrets.h)에 넣는다. 키는 이때 한 번만 보여 준다."""
    return service.create(user, data.name)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: UUID, user: CurrentUser, service: DeviceServiceDep):
    return service.get(user, str(device_id))


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: UUID, user: CurrentUser, service: DeviceServiceDep):
    service.delete(user, str(device_id))


@router.post("/{device_id}/key", response_model=DeviceWithKey)
def regenerate_key(device_id: UUID, user: CurrentUser, service: DeviceServiceDep):
    """기기 키 재발급. 이전 키로는 더 이상 보고할 수 없다."""
    return service.regenerate_key(user, str(device_id))


@router.put("/{device_id}/led", response_model=DeviceOut)
def set_led(device_id: UUID, data: LedUpdate, user: CurrentUser, service: DeviceServiceDep):
    """LED 켜기/끄기. 보드가 다음 보고(기본 3초 이내) 때 받아서 적용한다."""
    return service.set_led(user, str(device_id), data.on)


@router.get("/{device_id}/readings", response_model=list[ReadingOut])
def list_readings(
    device_id: UUID,
    user: CurrentUser,
    service: DeviceServiceDep,
    limit: int = Query(60, ge=1, le=500),
    since: datetime | None = Query(None, description="이 시각 이후 값만 (그래프 이어 그리기용)"),
):
    """센서값 기록 (오래된 것부터)."""
    return service.readings(user, str(device_id), limit, since)
