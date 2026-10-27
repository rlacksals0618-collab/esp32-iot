/*
  XIAO ESP32S3 ↔ 백엔드(FastAPI on Render)

  동작
  - 일정 주기(기본 3초)마다 센서값을 HTTP POST로 서버에 보낸다.
  - 서버 응답에 "LED를 켤지/끌지"가 들어 있어 그대로 적용한다.
  - 보드가 먼저 서버에 요청하는 방식이라, 공유기 설정 없이 어떤 WiFi에 있어도 원격 제어가 된다.

  준비
  1. secrets.h.example 을 secrets.h 로 복사하고 WiFi, 서버 주소, 기기 키를 채운다.
  2. 보드: "XIAO_ESP32S3" (esp32 by Espressif 보드 패키지 3.x)
  3. 시리얼 모니터 115200

  센서
  - 온도: ESP32-S3 칩 내부 온도 (주변 온도보다 높게 나온다. 외부 센서로 바꾸려면 readTemperature 수정)
  - 밝기: A0 핀 아날로그 값 0~4095 (조도 센서나 가변저항 연결. 아무것도 없으면 떠 있는 값이 읽힌다)
  - WiFi 신호 세기(RSSI)
*/
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "secrets.h"

// ── 핀
const int LED_PIN = LED_BUILTIN;   // XIAO ESP32S3 내장 사용자 LED (GPIO21)
const bool LED_ACTIVE_LOW = true;  // 내장 LED는 LOW일 때 켜진다. 외부 LED를 HIGH로 켜는 회로면 false로
const int LIGHT_PIN = A0;

// ── 상태
unsigned long intervalMs = 3000;   // 서버가 응답으로 바꿀 수 있다
unsigned long lastReportAt = 0;
bool ledOn = false;
bool reportNow = true;             // 부팅 직후, LED가 바뀐 직후에는 바로 보고

void setLed(bool on) {
  ledOn = on;
  digitalWrite(LED_PIN, (on != LED_ACTIVE_LOW) ? HIGH : LOW);
}

float readTemperature() { return temperatureRead(); }
int readLight() { return analogRead(LIGHT_PIN); }

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("WiFi 연결 중: %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWiFi 연결됨. IP: %s, 신호: %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("\nWiFi 연결 실패. 이름/비밀번호와 2.4GHz 여부를 확인하세요. 다시 시도합니다.");
  }
}

// 응답 JSON에서 "key":true/false 를 찾는다. (ArduinoJson 없이 쓰기 위한 간단한 파서)
bool findBool(const String& json, const char* key, bool& out) {
  int i = json.indexOf(String("\"") + key + "\"");
  if (i < 0) return false;
  i = json.indexOf(':', i);
  if (i < 0) return false;
  while (++i < (int)json.length() && json[i] == ' ') {}
  if (json.startsWith("true", i)) { out = true; return true; }
  if (json.startsWith("false", i)) { out = false; return true; }
  return false;
}

bool findLong(const String& json, const char* key, long& out) {
  int i = json.indexOf(String("\"") + key + "\"");
  if (i < 0) return false;
  i = json.indexOf(':', i);
  if (i < 0) return false;
  out = json.substring(i + 1).toInt();
  return true;
}

void report() {
  String url = String(API_BASE_URL) + "/api/board/telemetry";
  char body[160];
  snprintf(body, sizeof(body), "{\"temperature\":%.2f,\"light\":%d,\"rssi\":%d,\"led_on\":%s}",
           readTemperature(), readLight(), WiFi.RSSI(), ledOn ? "true" : "false");

  WiFiClientSecure secureClient;
  WiFiClient plainClient;
  HTTPClient http;
  if (url.startsWith("https://")) {
    // 인증서 검증을 생략한다 (테스트용으로 간단하게). 통신은 암호화되지만 서버 위장은 막지 못한다.
    // 운영에서는 secureClient.setCACert(루트 인증서)로 검증할 것
    secureClient.setInsecure();
    http.begin(secureClient, url);
  } else {
    http.begin(plainClient, url);  // 로컬 테스트 (http://PC의IP:8000)
  }
  http.setTimeout(20000);  // Render 무료 플랜은 잠들어 있다가 깨는 데 시간이 걸린다
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);

  int code = http.POST((uint8_t*)body, strlen(body));
  if (code == 200) {
    String resp = http.getString();
    bool wantLed;
    if (findBool(resp, "led_on", wantLed) && wantLed != ledOn) {
      setLed(wantLed);
      reportNow = true;  // 바뀐 LED 상태를 바로 알려 대시보드에 빨리 반영되게 한다
      Serial.printf("LED %s\n", wantLed ? "켜짐" : "꺼짐");
    }
    long iv;
    if (findLong(resp, "interval_ms", iv) && iv >= 500 && iv <= 60000) intervalMs = iv;
    Serial.printf("보고 완료: %s\n", body);
  } else if (code == 401) {
    Serial.println("서버가 기기 키를 거부했습니다. 대시보드에서 받은 DEVICE_KEY를 확인하세요.");
  } else if (code > 0) {
    Serial.printf("보고 실패: HTTP %d %s\n", code, http.getString().c_str());
  } else {
    Serial.printf("서버 연결 실패: %s (주소: %s)\n", http.errorToString(code).c_str(), url.c_str());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(LED_PIN, OUTPUT);
  setLed(false);
  analogReadResolution(12);
  Serial.println("\nXIAO ESP32S3 IoT 시작");
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return;
  }
  if (reportNow || millis() - lastReportAt >= intervalMs) {
    reportNow = false;
    lastReportAt = millis();
    report();
  }
  delay(20);
}
