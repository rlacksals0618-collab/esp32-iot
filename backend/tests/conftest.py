"""테스트는 Supabase 대신 메모리 저장소를 쓴다. (dependency_overrides로 교체)"""
import os

os.environ["APP_MODE"] = "memory"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import get_auth_gateway, get_device_store  # noqa: E402
from app.main import app  # noqa: E402
from app.services.memory_gateway import MemoryAuth, MemoryDeviceStore  # noqa: E402

PASSWORD = "password123"


@pytest.fixture
def client():
    auth, store = MemoryAuth(), MemoryDeviceStore()  # 테스트마다 빈 저장소
    app.dependency_overrides[get_auth_gateway] = lambda: auth
    app.dependency_overrides[get_device_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signup(client: TestClient, email: str) -> TestClient:
    """가입하고, 그 사용자의 토큰이 기본 헤더로 붙은 클라이언트를 돌려준다."""
    r = client.post("/api/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return TestClient(app, headers={"Authorization": f"Bearer {r.json()['access_token']}"})


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return signup(client, "bob@example.com")
