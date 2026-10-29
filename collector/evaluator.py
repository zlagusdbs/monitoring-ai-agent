"""규칙 평가기 — LLM 을 쓰지 않는다.

에이전트는 규칙을 만들어 rules 테이블에 넣기만 하고, 발동 판단은 여기서
결정론적으로 한다. 같은 데이터면 항상 같은 결론이 나와야 감사가 가능하다.
"""

import datetime as dt
import logging
import re
import time
from typing import Any

from .store import Store

log = logging.getLogger("evaluator")

_DATE_SUFFIX = re.compile(r"(\d{8})$")


def _active_cluster(store: Store) -> str | None:
    for r in store.latest("cluster_status"):
        if r["text"] == "Active":
            return r["labels"].get("cluster")
    return None


# --- guard ----------------------------------------------------------------

def _guard_ok(guards: list[dict], store: Store, now: dt.datetime) -> tuple[bool, str]:
    for g in guards or []:
        kind = g.get("type")
        if kind == "after_hour":
            if now.hour < int(g["hour"]):
                return False, f"아직 {g['hour']}시 이전"
        elif kind == "paused_until":
            continue
        elif kind == "active_cluster_known":
            if _active_cluster(store) is None:
                return False, "Active 클러스터를 모름"
        else:
            return False, f"알 수 없는 guard: {kind}"
    return True, ""


# --- check ----------------------------------------------------------------

def _check_topic_offset_zero(spec: dict, store: Store, now: dt.datetime):
    prefix = spec["topic_prefix"]
    today = now.strftime("%Y%m%d")
    target = f"{prefix}{today}"
    for r in store.latest("topic_offset_latest"):
        if r["labels"].get("topic") == target:
            if (r["value"] or 0) == 0:
                return True, f"{target} 의 produce 가 0건"
            return False, f"{target} = {r['value']:,.0f}건"
    return False, f"{target} 을 아직 수집하지 못함"


def _check_alias_age(spec: dict, store: Store, now: dt.datetime):
    """Active 클러스터의 alias 인덱스 이름에서 날짜를 읽어 경과일을 본다."""
    alias = spec["alias"]
    if spec.get("max_days") in (None, ""):
        return False, "max_days 가 정해지지 않았다 — 값을 정해야 켤 수 있다"
    max_days = int(spec["max_days"])
    active = _active_cluster(store)
    for r in store.latest("alias_index"):
        lab = r["labels"]
        if lab.get("alias") != alias or lab.get("cluster") != active:
            continue
        m = _DATE_SUFFIX.search(r["text"] or "")
        if not m:
            return False, f"{r['text']} 에 날짜가 없음"
        age = (now.date() - dt.datetime.strptime(m.group(1), "%Y%m%d").date()).days
        if age > max_days:
            return True, f"{active} 의 {alias} alias 가 {r['text']} ({age}일 전)"
        return False, f"{r['text']} ({age}일 전)"
    return False, f"{active} 의 {alias} alias 를 아직 수집하지 못함"


def _check_offset_stalled(spec: dict, store: Store, now: dt.datetime):
    """일정 시간 동안 offset 이 전혀 늘지 않았는지. 시계열이 있어야 판단된다."""
    topic, window = spec["topic"], int(spec["window_min"])
    since = int(time.time()) - window * 60
    pts = store.series("topic_offset_latest", {"topic": topic}, since)
    if len(pts) < 2:
        return False, f"표본 부족 ({len(pts)}개) — {window}분치가 쌓여야 판단 가능"
    delta = pts[-1][1] - pts[0][1]
    if delta == 0:
        return True, f"{topic} 이 {window}분간 증가 없음"
    return False, f"{topic} {window}분간 +{delta:,.0f}"


def _check_metric_threshold(spec: dict, store: Store, now: dt.datetime):
    """숫자 지표를 임계값과 비교한다. CPU·heap·검색량처럼 범용으로 쓴다."""
    metric, op, value = spec["metric"], spec["op"], float(spec["value"])
    want = spec.get("labels") or {}
    seen = []
    for r in store.latest(metric):
        if any(r["labels"].get(k) != v for k, v in want.items()):
            continue
        v = r["value"]
        if v is None:
            continue
        lab = ",".join(f"{k}={x}" for k, x in r["labels"].items())
        seen.append(f"{lab}={v:,.1f}")
        hit = (v > value) if op == ">" else (v < value) if op == "<" else (v == value)
        if hit:
            return True, f"{metric} {lab} = {v:,.1f} ({op} {value})"
    if not seen:
        return False, f"{metric} 표본 없음"
    return False, f"{metric} 조건 미충족 ({'; '.join(seen)})"


CHECKS = {
    "topic_offset_zero": _check_topic_offset_zero,
    "alias_age_days": _check_alias_age,
    "offset_stalled": _check_offset_stalled,
    "metric_threshold": _check_metric_threshold,
}


# --- 평가 -----------------------------------------------------------------

def evaluate(store: Store, now: dt.datetime | None = None) -> list[dict[str, Any]]:
    now = now or dt.datetime.now()
    ts = int(time.time())
    results = []
    for rule in store.rules():
        spec = rule["spec"]
        ok, why = _guard_ok(spec.get("guard", []), store, now)
        if not ok:
            store.put_finding(rule["id"], "skipped", why, ts=ts)
            results.append({**rule, "state": "skipped", "detail": why})
            continue
        fn = CHECKS.get(spec["check"]["type"])
        if fn is None:
            store.put_finding(rule["id"], "skipped", f"알 수 없는 check: {spec['check']['type']}", ts=ts)
            continue
        firing, detail = fn(spec["check"], store, now)
        state = "firing" if firing else "ok"
        store.put_finding(rule["id"], state, detail, ts=ts)
        results.append({**rule, "state": state, "detail": detail})
    return results
