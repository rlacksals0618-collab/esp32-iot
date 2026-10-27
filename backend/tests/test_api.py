from fastapi.testclient import TestClient

from app.main import app

from .conftest import PASSWORD


def board(device_key: str) -> TestClient:
    return TestClient(app, headers={"X-Device-Key": device_key})


# ── 회원가입·로그인
def test_signup_login_refresh(client):
    r = client.post("/api/auth/signup", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 201
    tokens = r.json()
    assert tokens["token_type"] == "bearer" and tokens["user"]["email"] == "a@example.com"

    assert client.post("/api/auth/signup", json={"email": "a@example.com", "password": PASSWORD}).status_code == 409
    assert client.post("/api/auth/signup", json={"email": "not-an-email", "password": PASSWORD}).status_code == 422
    assert client.post("/api/auth/signup", json={"email": "b@example.com", "password": "short"}).status_code == 422

    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["email"] == "a@example.com"

    refreshed = client.post("/api/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    assert refreshed.status_code == 200 and refreshed.json()["access_token"] != r.json()["access_token"]
    # 한 번 쓴 refresh token은 다시 쓸 수 없다
    assert client.post("/api/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}).status_code == 401


def test_dashboard_requires_login(client):
    assert client.get("/api/devices").status_code == 401
    r = client.get("/api/devices", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer"


# ── 기기 등록 → 보드 보고 → LED 제어 전체 흐름
def test_device_flow(alice):
    r = alice.post("/api/devices", json={"name": "책상 XIAO"})
    assert r.status_code == 201
    device = r.json()
    key, device_id = device["device_key"], device["id"]
    assert device["online"] is False and device["led_on"] is False and len(key) >= 40
    assert "device_key" not in alice.get(f"/api/devices/{device_id}").json()  # 키는 등록 때만 보여 줌

    # 보드가 센서값을 보고하면 LED 명령(현재 꺼짐)과 보고 주기를 받는다
    ack = board(key).post("/api/board/telemetry", json={"temperature": 31.5, "light": 1200, "rssi": -55, "led_on": False})
    assert ack.status_code == 200 and ack.json() == {"led_on": False, "interval_ms": 3000}

    listed = alice.get("/api/devices").json()[0]
    assert listed["online"] is True and listed["latest"]["temperature"] == 31.5 and listed["latest"]["light"] == 1200

    # 대시보드에서 LED를 켜면, 보드의 다음 보고 응답에 반영된다
    r = alice.put(f"/api/devices/{device_id}/led", json={"on": True})
    assert r.json()["led_on"] is True and r.json()["led_reported"] is False  # 아직 보드는 꺼진 상태
    assert board(key).post("/api/board/telemetry", json={"led_on": False}).json()["led_on"] is True
    board(key).post("/api/board/telemetry", json={"temperature": 32.0, "led_on": True})  # 보드가 켠 뒤 보고
    assert alice.get(f"/api/devices/{device_id}").json()["led_reported"] is True

    readings = alice.get(f"/api/devices/{device_id}/readings").json()
    assert len(readings) == 3 and readings[-1]["temperature"] == 32.0  # 오래된 것부터
    since = readings[1]["created_at"]
    assert len(alice.get(f"/api/devices/{device_id}/readings", params={"since": since}).json()) == 1
    assert len(alice.get(f"/api/devices/{device_id}/readings", params={"limit": 2}).json()) == 2


def test_board_auth_and_validation(alice):
    device = alice.post("/api/devices", json={"name": "보드"}).json()
    assert TestClient(app).post("/api/board/telemetry", json={}).status_code == 401
    assert board("wrong-key").post("/api/board/telemetry", json={}).status_code == 401
    assert board(device["device_key"]).post("/api/board/telemetry", json={"rssi": 10}).status_code == 422
    assert board(device["device_key"]).post("/api/board/telemetry", json={"light": 5000}).status_code == 422


def test_regenerate_key_revokes_old_key(alice):
    device = alice.post("/api/devices", json={"name": "보드"}).json()
    new = alice.post(f"/api/devices/{device['id']}/key").json()
    assert new["device_key"] != device["device_key"]
    assert board(device["device_key"]).post("/api/board/telemetry", json={}).status_code == 401
    assert board(new["device_key"]).post("/api/board/telemetry", json={}).status_code == 200


# ── 권한: 본인 기기만
def test_cannot_access_other_users_device(alice, bob):
    device = alice.post("/api/devices", json={"name": "앨리스 보드"}).json()
    did = device["id"]

    assert bob.get("/api/devices").json() == []
    assert bob.get(f"/api/devices/{did}").status_code == 403
    assert bob.put(f"/api/devices/{did}/led", json={"on": True}).status_code == 403
    assert bob.get(f"/api/devices/{did}/readings").status_code == 403
    assert bob.post(f"/api/devices/{did}/key").status_code == 403
    assert bob.delete(f"/api/devices/{did}").status_code == 403
    assert alice.get(f"/api/devices/{did}").json()["led_on"] is False  # 아무것도 바뀌지 않음


def test_delete_device_and_bad_ids(alice):
    device = alice.post("/api/devices", json={"name": "보드"}).json()
    assert alice.delete(f"/api/devices/{device['id']}").status_code == 204
    assert alice.get(f"/api/devices/{device['id']}").status_code == 404
    assert board(device["device_key"]).post("/api/board/telemetry", json={}).status_code == 401
    assert alice.get("/api/devices/not-a-uuid").status_code == 422
    assert alice.post("/api/devices", json={"name": ""}).status_code == 422


def test_cors_preflight_allowed(client):
    r = client.options(
        "/api/devices",
        headers={"Origin": "https://my-dashboard.vercel.app", "Access-Control-Request-Method": "GET",
                 "Access-Control-Request-Headers": "authorization"},
    )
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] in ("*", "https://my-dashboard.vercel.app")
