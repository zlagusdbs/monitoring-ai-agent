"""자동 점검 실행기. 새로 발동한 규칙이 있을 때만 에이전트를 1회 깨운다."""

import asyncio
import logging
from typing import Any, Awaitable, Callable

import catalog

log = logging.getLogger("runner")

TIMEOUT_SEC = 180

DEFAULTS = {
    "auto_check": "off",
    "wake_severity": "high",
    "cooldown_hours": "6",
    "hourly_max": "4",
    "daily_max": "20",
    "wake_without_action": "off",
    "auto_every_min": "1",
    "checklist_auto": "off",
    "checklist_every_min": "30",
}

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def setting(store, key: str) -> str:
    return store.get_setting(key, DEFAULTS.get(key, "")) or DEFAULTS.get(key, "")


def _latest_states(store) -> dict[str, str]:
    rows = store.conn.execute(
        """SELECT rule_id, state FROM findings f WHERE ts = (
               SELECT MAX(ts) FROM findings WHERE rule_id = f.rule_id)"""
    ).fetchall()
    return {rid: state for rid, state in rows}


def new_firings(store, seen: dict[str, str], now_ts: int) -> list[dict[str, Any]]:
    states = _latest_states(store)
    out = []
    for rule in store.rules():
        state = states.get(rule["id"])
        if state == "firing" and seen.get(rule["id"]) != "firing":
            out.append(rule)
    seen.update(states)
    return out


def _paused_until(rule: dict) -> int:
    for g in rule["spec"].get("guard") or []:
        if g.get("type") == "paused_until":
            return int(g.get("ts") or 0)
    return 0


def _action_id(rule: dict) -> str:
    return (rule["spec"].get("action") or {}).get("id", "")


def should_wake(store, rule: dict, now_ts: int) -> str | None:
    if setting(store, "auto_check") != "on":
        return "자동 점검이 꺼져 있다"
    if _paused_until(rule) > now_ts:
        return "일시 정지 중인 규칙이다"
    if not _action_id(rule) and setting(store, "wake_without_action") != "on":
        return "달린 조치가 없다"
    want = SEVERITY_ORDER.get(setting(store, "wake_severity"), 2)
    if SEVERITY_ORDER.get(rule.get("severity", "low"), 0) < want:
        return "심각도가 기준보다 낮다"

    cooldown = int(setting(store, "cooldown_hours")) * 3600
    recent = [a for a in store.actions_since(now_ts - cooldown) if a["rule_id"] == rule["id"]]
    if recent:
        return f"쿨다운 중 — 마지막 판단이 {(now_ts - recent[-1]['ts']) // 60}분 전"

    if len(store.actions_since(now_ts - 3600)) >= int(setting(store, "hourly_max")):
        return "상한 — 최근 1시간 호출이 가득 찼다"
    if len(store.actions_since(now_ts - 86400)) >= int(setting(store, "daily_max")):
        return "상한 — 오늘 호출이 가득 찼다"
    return None


def candidate(store, rule: dict, now_ts: int) -> dict[str, Any]:
    action_id = _action_id(rule)
    return {
        "rule_id": rule["id"],
        "severity": rule.get("severity", ""),
        "title": rule.get("title", ""),
        "action_id": action_id,
        "action": catalog.describe(action_id) if action_id else "",
        "limit": catalog.check_limits(store, action_id, now_ts) if action_id else None,
        "history": [a for a in store.actions_since(now_ts - 86400) if a["rule_id"] == rule["id"]],
    }


async def tick(
    store,
    seen: dict[str, str],
    *,
    now_ts: int,
    ask: Callable[[dict], Awaitable[dict]],
    act: Callable[..., Awaitable[dict]] | None = None,
) -> list[dict[str, Any]]:
    done = []
    for rule in new_firings(store, seen, now_ts):
        skip = should_wake(store, rule, now_ts)
        if skip:
            log.info("건너뜀 %s — %s", rule["id"], skip)
            continue
        done.append(await _handle(store, rule, now_ts, ask, act))
    return done


async def _handle(store, rule, now_ts, ask, act) -> dict[str, Any]:
    action_id = _action_id(rule)
    try:
        answer = await asyncio.wait_for(ask(candidate(store, rule, now_ts)), TIMEOUT_SEC)
    except asyncio.TimeoutError:
        store.put_action(rule["id"], action_id, "hold", f"에이전트 타임아웃 ({TIMEOUT_SEC}초)",
                         ts=now_ts)
        return {"rule_id": rule["id"], "verdict": "hold"}
    except Exception as e:
        store.put_action(rule["id"], action_id, "hold", f"에이전트 오류 — {type(e).__name__}: {e}",
                         ts=now_ts)
        return {"rule_id": rule["id"], "verdict": "hold"}

    verdict = (answer or {}).get("verdict")
    reason = (answer or {}).get("reason") or ""
    if verdict not in ("execute", "hold", "escalate"):
        store.put_action(rule["id"], action_id, "no_decision",
                         reason or "판단을 돌려주지 않았다", ts=now_ts)
        return {"rule_id": rule["id"], "verdict": "no_decision"}

    if verdict != "execute":
        store.put_action(rule["id"], action_id, verdict, reason, ts=now_ts)
        return {"rule_id": rule["id"], "verdict": verdict}

    why = catalog.check_limits(store, action_id, now_ts)
    if why:
        store.put_action(rule["id"], action_id, verdict, reason,
                         outcome="blocked", detail=why, ts=now_ts)
        return {"rule_id": rule["id"], "verdict": verdict, "outcome": "blocked"}

    if act is None:
        store.put_action(rule["id"], action_id, verdict, reason,
                         outcome="disabled", detail="실행기가 연결되지 않았다", ts=now_ts)
        return {"rule_id": rule["id"], "verdict": verdict, "outcome": "disabled"}

    result = await act(action_id, catalog.fixed_params(action_id))
    store.put_action(rule["id"], action_id, verdict, reason,
                     params=catalog.fixed_params(action_id),
                     outcome=result["outcome"], detail=result["detail"],
                     revert=result.get("revert"), ts=now_ts)
    return {"rule_id": rule["id"], "verdict": verdict, "outcome": result["outcome"]}
