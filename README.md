# XIAO ESP32S3 IoT 대시보드

XIAO ESP32S3의 센서값을 웹에서 보고, LED를 원격으로 켜고 끈다.

```
 [XIAO ESP32S3] ──HTTPS POST (3초마다)──▶ [FastAPI 백엔드 · Render] ◀──HTTPS──▶ [웹 대시보드 · Vercel]
   센서값 보고                 응답: LED 켜/꺼          │  인증·DB
                                                      ▼
                                                [Supabase]
```

**다른 WiFi에서도 제어되는 이유**: 보드가 먼저 클라우드 서버에 요청을 보내고, 응답으로 LED 명령을 받아 간다. 서버가 보드에 직접 접속하지 않으므로 보드는 인터넷만 되면 어느 네트워크에 있어도 된다. (포트포워딩 불필요) 대신 LED 명령은 다음 보고 때 반영되므로 최대 3초 정도 늦다.

## 폴더

```
esp32-iot/
├─ backend/        FastAPI (routers / schemas / services)
├─ frontend/       웹 대시보드 (HTML·CSS·JS, 빌드 없음)
├─ firmware/       XIAO ESP32S3 Arduino 스케치
├─ supabase/       DB 테이블 SQL
├─ tools/          fake_board.py: 보드 없이 테스트하는 가짜 보드
└─ render.yaml     Render 배포 설정
```

## 1. 로컬에서 먼저 해 보기 (Supabase 없이)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
$env:APP_MODE="memory"; .venv\Scripts\python -m uvicorn app.main:app --reload     # 터미널 1

cd ..\frontend; python -m http.server 5500                                          # 터미널 2
```

1. http://127.0.0.1:5500 에서 회원가입 → 기기 등록 → 나오는 기기 키 복사
2. 보드 대신 가짜 보드 실행 (터미널 3): `python tools\fake_board.py --url http://127.0.0.1:8000 --key <기기 키>`
3. 대시보드에 센서값이 들어오고, LED 버튼을 누르면 가짜 보드 터미널에 `LED 켜짐`이 찍힌다

memory 모드는 서버를 끄면 데이터가 사라진다. 테스트: `.venv\Scripts\python -m pytest`

## 2. Supabase 준비

1. https://supabase.com 에서 새 프로젝트 만들기 (Region: Northeast Asia (Seoul) 추천)
2. **SQL Editor** → `supabase/schema.sql` 내용을 붙여 넣고 Run
3. **Project Settings → API Keys**에서 키 확인
   - Publishable key (`sb_publishable_...`, 예전 이름 anon)
   - Secret key (`sb_secret_...`, 예전 이름 service_role) — **모든 데이터 접근 가능. 서버에만 둔다**
   - Project URL: **Project Settings → Data API** (`https://xxxx.supabase.co`)
4. 로컬에서 실제 Supabase로 실행하려면 `backend/.env.example`을 `backend/.env`로 복사해 채우고:
   `.venv\Scripts\python -m uvicorn app.main:app --reload --env-file .env`

회원가입은 백엔드가 Supabase 관리자 API로 **이메일 인증 없이 바로 사용 가능한 계정**을 만든다 (테스트 편의). 가입한 사용자는 Supabase 대시보드 **Authentication → Users**에서 볼 수 있다.

## 3. 백엔드 배포 (Render)

Render는 GitHub 저장소에서 코드를 가져가 배포한다.

1. 이 폴더를 GitHub 저장소로 올린다 (비공개 저장소 가능)
2. `render login` (브라우저에서 로그인)
3. Render 대시보드 → **New → Blueprint** → 저장소 선택 → `render.yaml`대로 `esp32-iot-api` 서비스가 만들어진다
4. 이때 `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`를 입력하라고 나온다
5. 배포가 끝나면 `https://esp32-iot-api.onrender.com/health` 가 `{"status":"ok"}`면 성공
   (이름이 이미 쓰이고 있으면 주소 뒤에 글자가 붙는다. 서비스 페이지에서 실제 주소 확인)

CLI로 확인: `render services` (서비스 목록), `render logs` (로그), `render deploys create` (다시 배포)

**무료 플랜 주의**: 15분 동안 요청이 없으면 서버가 잠들고, 다음 요청 때 깨어나는 데 1분 가까이 걸린다. 보드가 3초마다 보고하는 동안에는 잠들지 않는다.

## 4. 프론트엔드 배포 (Vercel)

1. `frontend/config.js`의 `API_BASE_URL`을 Render 주소로 바꾼다
2. 배포:
   ```powershell
   cd frontend
   vercel deploy --prod
   ```
   처음에는 프로젝트 이름 등을 물어본다. 끝나면 `https://<이름>.vercel.app` 주소가 나온다
3. (선택) Render의 `CORS_ORIGINS` 환경 변수를 `*`에서 Vercel 주소로 바꾸면 그 사이트에서만 API를 호출할 수 있다

대시보드 아래 **서버 주소 변경**으로 브라우저별로 다른 백엔드를 가리키게 할 수도 있다.

## 5. 보드 (XIAO ESP32S3)

1. Arduino IDE → 보드 매니저에서 **esp32 by Espressif** (3.x) 설치 → 보드 **XIAO_ESP32S3** 선택
2. `firmware/esp32_iot/secrets.h.example`을 `secrets.h`로 복사하고 채운다
   - WiFi 이름·비밀번호 (**2.4GHz만** 연결됨)
   - 대시보드에서 기기 등록 때 나온 `API_BASE_URL`, `DEVICE_KEY` 두 줄
3. 업로드 후 시리얼 모니터(115200)에서 `보고 완료`가 찍히면 대시보드에 온라인으로 표시된다

CLI로 업로드:
```powershell
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 firmware\esp32_iot
arduino-cli upload  --fqbn esp32:esp32:XIAO_ESP32S3 -p COM5 firmware\esp32_iot   # 포트는 arduino-cli board list 로 확인
```

센서:
- **온도**: ESP32-S3 칩 내부 온도라 실제 기온보다 높게 나온다
- **밝기**: A0 핀 아날로그 값. 조도 센서(또는 가변저항)를 연결한다. 아무것도 없으면 의미 없는 값이 나온다
- **WiFi 신호 세기**

다른 센서(DHT22 등)를 쓰려면 `readTemperature()`를 바꾸면 된다.

## API

| 메서드 | 경로 | 인증 | 동작 |
|---|---|---|---|
| POST | `/api/auth/signup` | | 회원가입 + 바로 로그인 `{email, password}` |
| POST | `/api/auth/login` | | 로그인 → `access_token`, `refresh_token` |
| POST | `/api/auth/refresh` | | 토큰 갱신 `{refresh_token}` |
| GET | `/api/auth/me` | 사용자 | 내 정보 |
| GET / POST | `/api/devices` | 사용자 | 내 기기 목록 / 기기 등록 (응답에 기기 키, 한 번만) |
| GET / DELETE | `/api/devices/{id}` | 사용자 | 기기 조회 / 삭제 |
| PUT | `/api/devices/{id}/led` | 사용자 | LED `{on: true}` |
| GET | `/api/devices/{id}/readings` | 사용자 | 센서 기록 `?limit=60&since=` |
| POST | `/api/devices/{id}/key` | 사용자 | 기기 키 재발급 |
| POST | `/api/board/telemetry` | 기기 키 | 보드 → 센서값 보고, 응답으로 `{led_on, interval_ms}` |

- 사용자 인증: `Authorization: Bearer <access_token>` (Supabase Auth 토큰)
- 기기 인증: `X-Device-Key: <기기 키>`. 서버에는 키의 해시만 저장된다
- 다른 사용자의 기기는 403. API 문서와 직접 호출: `<백엔드 주소>/docs`

## 보안 메모

- Secret 키는 백엔드 환경 변수에만 둔다. 프론트엔드·펌웨어·GitHub에 넣지 않는다 (`.env`, `secrets.h`는 `.gitignore`에 포함)
- DB 테이블은 RLS가 켜져 있고 정책이 없어서, publishable 키로는 직접 읽을 수 없다
- 펌웨어는 테스트 편의를 위해 HTTPS 인증서 검증을 생략한다(`setInsecure`). 통신은 암호화되지만 서버 위장은 막지 못한다
- 센서값이 3초마다 쌓인다 (보드 1대당 하루 약 2.9만 행). 오래된 값 정리 SQL은 `supabase/schema.sql` 맨 아래
