#!/usr/bin/env python3
"""Oracle Cloud 가입 화면의 '홈 리전' 목록에 한국(서울/춘천)이 뜨는지 확인한다.

oci_launch_retry.py(이미 계정이 있고 무료 서버 재고를 기다리는 것)와는 완전히 다른 체크다 —
이건 **계정 생성 자체가 안 된 상태**에서, Oracle이 신규 가입자에게 한국을 홈 리전으로
내어주는지를 본다. 인증/캡차가 전혀 필요 없는 signup-api.cloud.oracle.com의 공개 엔드포인트를
그대로 호출한다 (2026-10-24 Chrome 네트워크 탭으로 확인, main.js의 Ka() 함수가 호출하는 바로 그 API).

상태는 저장소의 region_state.json에 "지금 한국이 보이는지"만 기록해서, 뜰 때 딱 1번만 알린다
(매 실행마다 같은 결과를 반복 알리지 않음).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REGION_API = "https://signup-api.cloud.oracle.com/20200828/region?clientId=SignupUI&oracleEmployee=false"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "region_state.json")
KOREA_KEYWORDS = ("seoul", "chuncheon", "kr-")


def fetch_regions():
    req = urllib.request.Request(
        REGION_API,
        headers={
            "Origin": "https://signup.cloud.oracle.com",
            "Referer": "https://signup.cloud.oracle.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def find_korea(data):
    found = []
    for group in data.get("items", []):
        for region in group.get("homeRegions", []):
            rid = (region.get("id") or "").lower()
            name = (region.get("regionName") or "")
            if any(k in rid for k in KOREA_KEYWORDS) or "korea" in name.lower():
                found.append(f"{name} ({region.get('id')})")
    return found


def telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("(텔레그램 미설정 - 콘솔에만 출력)")
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data),
            timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        print(f"텔레그램 전송 실패 (무시): {e}", file=sys.stderr)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"korea_available": False}


def save_state(state):
    text = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            if f.read() == text:
                return
    except FileNotFoundError:
        pass
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="텔레그램 연결 테스트 메시지만 보내고 종료 (상태 변경 없음)")
    args = ap.parse_args()

    if args.test:
        msg = "[오라클-리전] 테스트 메시지입니다. 이게 왔으면 시크릿이 정상 연결된 것입니다."
        print(msg)
        telegram(msg)
        return 0

    try:
        data = fetch_regions()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"[오류] 리전 API 호출 실패: {e}", file=sys.stderr)
        return 0  # 일시적 오류는 실패로 치지 않고 다음 cron에서 재시도

    found = find_korea(data)
    state = load_state()
    was_available = bool(state.get("korea_available"))
    is_available = bool(found)

    if is_available and not was_available:
        msg = "🇰🇷 [오라클-리전] 가입 홈 리전 목록에 한국이 떴습니다!\n" + "\n".join(found) + \
              "\n\nhttps://signup.cloud.oracle.com/ 에서 지금 가입하세요 (한 번 정하면 못 바꿉니다)."
        print(msg)
        telegram(msg)
    elif not is_available and was_available:
        msg = "[오라클-리전] 한국이 다시 목록에서 사라졌습니다."
        print(msg)
        telegram(msg)
    else:
        print(f"변화 없음 (한국 사용 가능: {is_available})")

    save_state({"korea_available": is_available, "found": found})
    return 0


if __name__ == "__main__":
    sys.exit(main())
