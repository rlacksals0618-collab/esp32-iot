"""환경 변수 설정.

로컬에서는 backend/.env 파일에 적고 `uvicorn app.main:app --env-file .env`로 읽는다.
Render에서는 서비스의 Environment 설정에 같은 이름으로 넣는다.
"""
import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    # supabase: 실제 운영 / memory: Supabase 없이 메모리에 저장 (로컬 테스트용, 서버를 끄면 사라짐)
    app_mode: str = "supabase"
    supabase_url: str = ""
    supabase_publishable_key: str = ""  # 대시보드의 Publishable key (예전 이름: anon key)
    supabase_secret_key: str = ""  # 대시보드의 Secret key (예전 이름: service_role key). 절대 프론트·보드에 넣지 말 것
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    device_interval_ms: int = 3000  # 보드가 서버에 보고하는 주기 = LED 명령이 반영되는 최대 지연
    online_timeout_s: int = 15  # 이 시간 안에 보고가 있으면 '온라인'

    def check(self) -> None:
        if self.app_mode not in ("supabase", "memory"):
            raise RuntimeError(f"APP_MODE는 supabase 또는 memory여야 합니다: {self.app_mode}")
        if self.app_mode == "supabase":
            missing = [
                name for name, value in [
                    ("SUPABASE_URL", self.supabase_url),
                    ("SUPABASE_PUBLISHABLE_KEY", self.supabase_publishable_key),
                    ("SUPABASE_SECRET_KEY", self.supabase_secret_key),
                ] if not value
            ]
            if missing:
                raise RuntimeError(f"환경 변수가 없습니다: {', '.join(missing)} (README의 'Supabase 준비' 참고)")


@lru_cache
def get_settings() -> Settings:
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    return Settings(
        app_mode=os.getenv("APP_MODE", "supabase"),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY", ""),
        supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY", ""),
        cors_origins=origins,
        device_interval_ms=int(os.getenv("DEVICE_INTERVAL_MS", "3000")),
        online_timeout_s=int(os.getenv("ONLINE_TIMEOUT_S", "15")),
    )
