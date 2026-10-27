-- Supabase 대시보드 → SQL Editor → New query 에 붙여 넣고 Run.
-- 여러 번 실행해도 안전하다 (if not exists).

-- 기기: 사용자(auth.users)마다 여러 대. 사용자가 탈퇴하면 기기도 삭제된다.
create table if not exists public.devices (
  id             uuid primary key default gen_random_uuid(),
  owner_id       uuid not null references auth.users(id) on delete cascade,
  name           text not null check (char_length(name) between 1 and 50),
  key_hash       text not null unique,          -- 기기 키의 SHA-256. 키 원문은 저장하지 않는다
  led_on         boolean not null default false, -- 대시보드가 요청한 LED 상태
  led_reported   boolean,                        -- 보드가 마지막으로 알려 준 실제 LED 상태
  led_updated_at timestamptz,
  last_seen_at   timestamptz,                    -- 보드의 마지막 보고 시각
  created_at     timestamptz not null default now()
);
create index if not exists devices_owner_idx on public.devices (owner_id);

-- 센서값: 보드가 보고할 때마다 한 행 (기본 3초마다)
create table if not exists public.sensor_readings (
  id          bigint generated always as identity primary key,
  device_id   uuid not null references public.devices(id) on delete cascade,
  temperature real,
  light       integer,
  rssi        integer,
  led_on      boolean,
  created_at  timestamptz not null default now()
);
create index if not exists sensor_readings_device_time_idx on public.sensor_readings (device_id, created_at desc);

-- RLS를 켜고 정책은 만들지 않는다.
-- → publishable(anon) 키로는 이 테이블들을 직접 읽거나 쓸 수 없다.
-- → 백엔드(FastAPI)만 secret 키로 접근하고, 권한 검사는 백엔드가 한다.
alter table public.devices enable row level security;
alter table public.sensor_readings enable row level security;

-- (선택) 측정값이 계속 쌓이므로, 가끔 오래된 값을 지운다. 필요할 때 직접 실행:
-- delete from public.sensor_readings where created_at < now() - interval '7 days';
