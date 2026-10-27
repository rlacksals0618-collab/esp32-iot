"""보드(XIAO ESP32S3)용 엔드포인트.

보드는 공유기 뒤(NAT)에 있어서 서버가 먼저 보드에 접속할 수 없다.
그래서 보드가 주기적으로 센서값을 보내고(HTTP POST), 응답으로 LED 명령을 받아 간다.
보드가 인터넷에만 연결되어 있으면 어떤 WiFi에 있든 제어할 수 있다.
"""
from fastapi import APIRouter

from ..dependencies import CurrentDevice
from ..schemas.device import TelemetryAck, TelemetryIn
from ..services.device_service import DeviceServiceDep

router = APIRouter(prefix="/api/board", tags=["board"])


@router.post("/telemetry", response_model=TelemetryAck)
def report(data: TelemetryIn, device: CurrentDevice, service: DeviceServiceDep):
    """센서값 보고 + LED 명령 받기. 헤더: X-Device-Key"""
    return service.report(device, data)
