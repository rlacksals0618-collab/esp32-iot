from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

DeviceName = Annotated[str, Field(min_length=1, max_length=50, examples=["거실 XIAO"])]


class DeviceCreate(BaseModel):
    name: DeviceName


class LedUpdate(BaseModel):
    on: bool


class ReadingOut(BaseModel):
    temperature: float | None
    light: int | None
    rssi: int | None
    led_on: bool | None
    created_at: datetime


class DeviceOut(BaseModel):
    id: str
    name: str
    led_on: bool = Field(description="대시보드가 요청한 LED 상태")
    led_reported: bool | None = Field(description="보드가 마지막으로 알려 준 실제 LED 상태")
    led_updated_at: datetime | None
    last_seen_at: datetime | None
    online: bool = Field(description="최근 몇 초 안에 보드의 보고가 있었는지")
    created_at: datetime
    latest: ReadingOut | None = None


class DeviceWithKey(DeviceOut):
    device_key: str = Field(description="보드 펌웨어에 넣을 키. 이 응답에서 한 번만 보여 준다")


# ── 보드(ESP32) ↔ 서버
class TelemetryIn(BaseModel):
    temperature: Annotated[float, Field(ge=-50, le=150, description="°C")] | None = None
    light: Annotated[int, Field(ge=0, le=4095, description="아날로그 값 (12bit)")] | None = None
    rssi: Annotated[int, Field(ge=-127, le=0, description="WiFi 신호 세기 dBm")] | None = None
    led_on: bool | None = Field(None, description="보드의 현재 실제 LED 상태")


class TelemetryAck(BaseModel):
    led_on: bool = Field(description="보드가 적용해야 할 LED 상태")
    interval_ms: int = Field(description="다음 보고까지 기다릴 시간")
