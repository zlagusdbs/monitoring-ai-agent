import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from collector.store import Store
from web import runner

NOW = int(time.time())


def make_store(tmp_path, rules):
    s = Store(tmp_path / "t.db")
    s.set_setting("auto_check", "on")
    for rule_id, spec, state in rules:
        s.put_rule(rule_id, "high", rule_id, spec)
        s.put_finding(rule_id, state, "근거", ts=NOW)
    return s


ACT = {"check": {"type": "topic_offset_zero", "topic_prefix": "x-"},
       "action": {"id": "trigger_coupon_full"}}
NO_ACT = {"check": {"type": "topic_offset_zero", "topic_prefix": "x-"}}


def test_only_ok_to_firing_counts_as_new(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing"), ("r2", ACT, "firing")])
    got = runner.new_firings(s, {"r1": "ok", "r2": "firing"}, NOW)
    assert [r["id"] for r in got] == ["r1"]


def test_unseen_rule_counts_as_new(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])
    assert [r["id"] for r in runner.new_firings(s, {}, NOW)] == ["r1"]


def test_cooldown_blocks_second_wake(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])
    s.put_action("r1", "trigger_coupon_full", "hold", "", ts=NOW - 3600)
    assert "쿨다운" in runner.should_wake(s, {"id": "r1", "severity": "high", "spec": ACT}, NOW)


def test_rule_without_action_is_skipped_by_default(tmp_path):
    s = make_store(tmp_path, [("r1", NO_ACT, "firing")])
    assert "조치" in runner.should_wake(s, {"id": "r1", "severity": "high", "spec": NO_ACT}, NOW)


def test_severity_filter_skips_medium(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])
    assert "심각도" in runner.should_wake(s, {"id": "r1", "severity": "medium", "spec": ACT}, NOW)


def test_paused_rule_is_skipped(tmp_path):
    spec = dict(ACT, guard=[{"type": "paused_until", "ts": NOW + 3600}])
    s = make_store(tmp_path, [("r1", spec, "firing")])
    assert "일시 정지" in runner.should_wake(s, {"id": "r1", "severity": "high", "spec": spec}, NOW)


def test_expired_pause_does_not_skip(tmp_path):
    spec = dict(ACT, guard=[{"type": "paused_until", "ts": NOW - 10}])
    s = make_store(tmp_path, [("r1", spec, "firing")])
    assert runner.should_wake(s, {"id": "r1", "severity": "high", "spec": spec}, NOW) is None


def test_hourly_cap_stops_waking(tmp_path):
    s = make_store(tmp_path, [("r9", ACT, "firing")])
    for i in range(4):
        s.put_action(f"r{i}", "trigger_coupon_full", "hold", "", ts=NOW - 60 * i)
    assert "상한" in runner.should_wake(s, {"id": "r9", "severity": "high", "spec": ACT}, NOW)


async def test_tick_records_no_decision_when_agent_returns_nothing(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])

    async def ask(candidate):
        return {"verdict": None, "reason": ""}

    await runner.tick(s, {}, now_ts=NOW, ask=ask)
    assert s.actions_since(0)[-1]["verdict"] == "no_decision"


async def test_tick_records_hold_on_agent_timeout(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])

    async def ask(candidate):
        raise asyncio.TimeoutError

    await runner.tick(s, {}, now_ts=NOW, ask=ask)
    row = s.actions_since(0)[-1]
    assert row["verdict"] == "hold" and "타임아웃" in row["reason"]


async def test_tick_does_not_raise_when_agent_explodes(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])

    async def ask(candidate):
        raise RuntimeError("boom")

    await runner.tick(s, {}, now_ts=NOW, ask=ask)
    assert s.actions_since(0)[-1]["verdict"] == "hold"


async def test_tick_blocks_execute_over_limit(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])
    s.put_action("old", "trigger_coupon_full", "execute", "", outcome="sent", ts=NOW - 10)

    async def ask(candidate):
        return {"verdict": "execute", "reason": "확인 완료"}

    await runner.tick(s, {}, now_ts=NOW, ask=ask)
    row = s.actions_since(0)[-1]
    assert row["verdict"] == "execute" and row["outcome"] == "blocked"


async def test_tick_updates_seen_so_next_tick_is_quiet(tmp_path):
    s = make_store(tmp_path, [("r1", ACT, "firing")])
    seen = {}

    async def ask(candidate):
        return {"verdict": "hold", "reason": "보류"}

    await runner.tick(s, seen, now_ts=NOW, ask=ask)
    before = len(s.actions_since(0))
    await runner.tick(s, seen, now_ts=NOW, ask=ask)
    assert len(s.actions_since(0)) == before
