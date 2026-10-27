"""보드 없이 테스트하기: XIAO ESP32S3 펌웨어와 똑같은 요청을 보내는 가짜 보드.

    python tools/fake_board.py --url http://127.0.0.1:8000 --key <대시보드에서 받은 기기 키>

표준 라이브러리만 쓰므로 아무 Python에서나 실행된다. Ctrl+C로 종료.
"""
import argparse
import json
import math
import random
import time
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description="가짜 XIAO ESP32S3")
    parser.add_argument("--url", required=True, help="백엔드 주소 (예: https://esp32-iot-api.onrender.com)")
    parser.add_argument("--key", required=True, help="기기 키")
    args = parser.parse_args()

    endpoint = args.url.rstrip("/") + "/api/board/telemetry"
    led_on, interval_s, t0 = False, 3.0, time.time()
    print(f"가짜 보드 시작 → {endpoint}")
    while True:
        elapsed = time.time() - t0
        body = {
            "temperature": round(38 + 2 * math.sin(elapsed / 30) + random.uniform(-0.3, 0.3), 2),
            "light": max(0, min(4095, int(2000 + 1500 * math.sin(elapsed / 20) + random.randint(-80, 80)))),
            "rssi": random.randint(-68, -52),
            "led_on": led_on,
        }
        req = urllib.request.Request(
            endpoint, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Device-Key": args.key},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                ack = json.load(res)
            if ack["led_on"] != led_on:
                led_on = ack["led_on"]
                print(f"  LED {'켜짐 💡' if led_on else '꺼짐'}")
                interval_s = 0  # 바뀐 상태를 바로 보고
            else:
                interval_s = ack["interval_ms"] / 1000
            print(f"보고: {body}")
        except urllib.error.HTTPError as e:
            print(f"보고 실패: HTTP {e.code} {e.read().decode(errors='replace')}")
            interval_s = 3
        except OSError as e:
            print(f"서버 연결 실패: {e}")
            interval_s = 3
        time.sleep(interval_s)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n종료")
