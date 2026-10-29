"""조치 카탈로그. 여기 없는 조치는 어디서도 실행되지 않는다."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import policy

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    impact: str
    revertible: bool
    daily_max: int
    hourly_max: int | None


CATALOG: dict[str, Action] = {
    a.id: a
    for a in (
        Action("trigger_coupon_full", "쿠폰 full 색인 트리거",
               "Standby 클러스터 1대", False, daily_max=1, hourly_max=None),
        Action("restart_indexer_pod", "증분 색인 파드 재기동",
               "파드 1개", True, daily_max=3, hourly_max=1),
    )
}

POD_ALLOWED: dict[str, str] = policy.get("actions.pod_allowed", {})

DAG_ID: str = policy.get("actions.dag_id", "")

FIXED: dict[str, dict] = {
    "trigger_coupon_full": {"env": "prod", "item": False, "coupon": True},
}


def get(action_id: str) -> Action | None:
    return CATALOG.get(action_id)


def fixed_params(action_id: str, now: datetime | None = None) -> dict:
    params = dict(FIXED.get(action_id, {}))
    if action_id == "trigger_coupon_full":
        params["JOB_ID"] = (now or datetime.now(KST)).strftime("%Y%m%d")
    return params


def _day_start(now_ts: int) -> int:
    day = datetime.fromtimestamp(now_ts, KST).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(day.timestamp())


def check_limits(store, action_id: str, now_ts: int) -> str | None:
    action = get(action_id)
    if action is None:
        return f"카탈로그에 없는 조치: {action_id}"
    if action.hourly_max is not None:
        done = store.count_actions(action_id, now_ts - 3600)
        if done >= action.hourly_max:
            return f"상한 — 최근 1시간에 이미 {done}회 (최대 {action.hourly_max}회)"
    done = store.count_actions(action_id, _day_start(now_ts))
    if done >= action.daily_max:
        return f"상한 — 오늘 이미 {done}회 (최대 {action.daily_max}회)"
    return None


def describe(action_id: str) -> str:
    action = get(action_id)
    if action is None:
        return f"(알 수 없는 조치: {action_id})"
    revert = "되돌릴 수 있음" if action.revertible else "되돌릴 수 없음"
    return f"{action.title} · 영향 {action.impact} · {revert} · 하루 최대 {action.daily_max}회"
