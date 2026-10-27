"""기기 등록·LED 제어·센서값 조회(대시보드)와 센서 보고(보드)."""
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends

from ..config import Settings, get_settings
from ..dependencies import DeviceStoreDep, hash_device_key
from ..exceptions import ForbiddenError, NotFoundError
from ..schemas.device import DeviceOut, DeviceWithKey, ReadingOut, TelemetryAck, TelemetryIn
from .gateways import AuthUser, Row


def _now() -> datetime:
    return datetime.now(UTC)


class DeviceService:
    def __init__(self, store: DeviceStoreDep, settings: Annotated[Settings, Depends(get_settings)]):
        self.store = store
        self.settings = settings

    # ── 대시보드 (로그인한 사용자)
    def _owned(self, user: AuthUser, device_id: str) -> Row:
        device = self.store.get_device(device_id)
        if device is None:
            raise NotFoundError("기기를 찾을 수 없습니다.")
        if device["owner_id"] != user.id:
            raise ForbiddenError("다른 사용자의 기기에는 접근할 수 없습니다.")
        return device

    def _out(self, device: Row, with_latest: bool = True) -> DeviceOut:
        last_seen = device["last_seen_at"]
        online = last_seen is not None and _now() - last_seen < timedelta(seconds=self.settings.online_timeout_s)
        latest = None
        if with_latest and (rows := self.store.list_readings(device["id"], limit=1)):
            latest = ReadingOut.model_validate(rows[0])
        return DeviceOut.model_validate(device | {"online": online, "latest": latest})

    # 메서드 이름을 list로 지으면 Python 3.12(Render)에서 아래 메서드의 list[...] 타입 표기가 이 메서드를 가리켜 오류가 난다.
    def list_devices(self, user: AuthUser) -> list[DeviceOut]:
        return [self._out(d) for d in self.store.list_devices(user.id)]

    def get(self, user: AuthUser, device_id: str) -> DeviceOut:
        return self._out(self._owned(user, device_id))

    def create(self, user: AuthUser, name: str) -> DeviceWithKey:
        device_key = secrets.token_urlsafe(32)
        device = self.store.create_device(user.id, name, hash_device_key(device_key))
        return DeviceWithKey(**self._out(device, with_latest=False).model_dump(), device_key=device_key)

    def regenerate_key(self, user: AuthUser, device_id: str) -> DeviceWithKey:
        """키를 잃어버렸거나 유출됐을 때. 이전 키는 즉시 쓸 수 없게 된다."""
        self._owned(user, device_id)
        device_key = secrets.token_urlsafe(32)
        device = self.store.update_device(device_id, {"key_hash": hash_device_key(device_key)})
        return DeviceWithKey(**self._out(device).model_dump(), device_key=device_key)

    def delete(self, user: AuthUser, device_id: str) -> None:
        self._owned(user, device_id)
        self.store.delete_device(device_id)

    def set_led(self, user: AuthUser, device_id: str, on: bool) -> DeviceOut:
        """원하는 LED 상태를 저장해 둔다. 보드는 다음 보고 때 응답으로 이 값을 받아 적용한다."""
        self._owned(user, device_id)
        device = self.store.update_device(device_id, {"led_on": on, "led_updated_at": _now()})
        return self._out(device)

    def readings(self, user: AuthUser, device_id: str, limit: int, since: datetime | None) -> list[ReadingOut]:
        self._owned(user, device_id)
        if since is not None and since.tzinfo is None:
            since = since.replace(tzinfo=UTC)  # 시간대 없이 오면 UTC로 본다
        rows = self.store.list_readings(device_id, limit=limit, since=since)
        return [ReadingOut.model_validate(r) for r in reversed(rows)]  # 오래된 것부터 (그래프 그리기 쉽게)

    # ── 보드
    def report(self, device: Row, data: TelemetryIn) -> TelemetryAck:
        self.store.add_reading(device["id"], data.model_dump())
        fields: Row = {"last_seen_at": _now()}
        if data.led_on is not None:
            fields["led_reported"] = data.led_on
        device = self.store.update_device(device["id"], fields)
        return TelemetryAck(led_on=device["led_on"], interval_ms=self.settings.device_interval_ms)


DeviceServiceDep = Annotated[DeviceService, Depends()]
