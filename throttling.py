"""요청 차단(throttling) 제어면.

켤 수 있는 URI 와 켜면 안 되는 URI 는 policy.json 에서 읽는다. 파일이 없으면
어떤 URI 도 켤 수 없다.

제어면 스펙:
    GET    {path}            상태 조회
    POST   {path}            설정 추가/수정  <- 쓰기
    DELETE {path}?uri=...    해제            <- 쓰기
"""

import os
from datetime import datetime, timedelta

import policy

BASE = os.getenv("PRICE_API", "") or policy.get("endpoints.api", "")
PATH = policy.get("throttle.path", "")
FMT = "%Y-%m-%d %H:%M:%S"

ALLOWED = policy.get("throttle.allowed", {})
BLOCKED = policy.get("throttle.blocked", {})

MAX_TTL_MIN = int(policy.get("throttle.max_ttl_min", 240))


def validate(uri: str, rate: int, ttl_minutes: int) -> str | None:
    """문제가 있으면 사유를, 없으면 None 을 돌려준다."""
    if not (BASE and PATH and ALLOWED):
        return "정책이 설정되지 않았다 — policy.json 을 먼저 채워야 한다"
    if uri in BLOCKED:
        return f"{uri} 는 켜면 안 되는 URI 다 — {BLOCKED[uri]}"
    if uri not in ALLOWED:
        return f"알 수 없는 URI: {uri}. 가능한 값: {list(ALLOWED)}"
    if not 0 <= int(rate) <= 100:
        return f"rate 는 0~100 이어야 한다: {rate}"
    if not 1 <= int(ttl_minutes) <= MAX_TTL_MIN:
        return f"ttl_minutes 는 1~{MAX_TTL_MIN} 이어야 한다: {ttl_minutes}"
    return None


def body(uri: str, rate: int, ttl_minutes: int, now: datetime | None = None) -> list[dict]:
    """POST 본문. start 는 서버가 정하므로 보내지 않는다."""
    end = (now or datetime.now()) + timedelta(minutes=int(ttl_minutes))
    return [{"uri": uri, "on": True, "rate": int(rate), "end": end.strftime(FMT)}]


def curl(uri: str, rate: int, ttl_minutes: int) -> str:
    """사람이 직접 실행할 때 쓸 명령."""
    import json
    return (f"curl -s -X POST {BASE}{PATH} -H 'Content-Type: application/json' "
            f"-d '{json.dumps(body(uri, rate, ttl_minutes), ensure_ascii=False)}'")


def revert_curl(uri: str) -> str:
    return f"curl -s -X DELETE '{BASE}{PATH}?uri={uri}'"
