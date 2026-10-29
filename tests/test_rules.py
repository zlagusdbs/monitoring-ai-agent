import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from collector import evaluator, seed_rules
from collector.store import Store
from web import server

NOW = int(time.time())


@pytest.fixture
def aliases(monkeypatch):
    from collector import config
    monkeypatch.setattr(config, "ALIASES", ["coupon", "item"])
    monkeypatch.setattr(config, "FULL_TOPIC_PREFIXES", ["coupon-full", "item-full"])
    monkeypatch.setattr(config, "STATIC_TOPICS", ["indexed1_coupon-incr-1"])
    monkeypatch.setattr(config, "TOPIC_VERSION", "1")


def all_rule_ids(s):
    return {r[0] for r in s.conn.execute("SELECT id FROM rules")}


def test_seeded_rules_are_all_disabled(tmp_path, aliases):
    s = Store(tmp_path / "t.db")
    seed_rules.seed(s)
    assert s.rules() == []
    assert all_rule_ids(s)


def test_seed_covers_aliases_symmetrically(tmp_path, aliases):
    s = Store(tmp_path / "t.db")
    seed_rules.seed(s)
    assert {"coupon_price_stale", "item_price_stale"} <= all_rule_ids(s)
    assert {"coupon_full_missing", "item_full_missing"} <= all_rule_ids(s)


def test_seed_does_not_reenable_a_rule_the_user_turned_off(tmp_path, aliases):
    s = Store(tmp_path / "t.db")
    seed_rules.seed(s)
    s.conn.execute("UPDATE rules SET enabled=1 WHERE id='coupon_price_stale'")
    seed_rules.seed(s)
    assert s.conn.execute(
        "SELECT enabled FROM rules WHERE id='coupon_price_stale'").fetchone()[0] == 1


def test_paused_until_does_not_skip_evaluation(tmp_path):
    s = Store(tmp_path / "t.db")
    s.put_rule("r1", "high", "제목", {
        "check": {"type": "topic_offset_zero", "topic_prefix": "t-"},
        "guard": [{"type": "paused_until", "ts": NOW + 3600}],
    })
    assert evaluator.evaluate(s)[0]["state"] != "skipped"


def test_alias_age_without_threshold_does_not_crash(tmp_path):
    s = Store(tmp_path / "t.db")
    s.put_rule("r1", "high", "제목", {"check": {"type": "alias_age_days", "alias": "a"}})
    assert "max_days" in evaluator.evaluate(s)[0]["detail"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    s = Store(db)
    s.put_rule("r1", "high", "제목", {"check": {"type": "topic_offset_zero", "topic_prefix": "t-"}})
    s.checkpoint()
    monkeypatch.setattr(server, "DB", db)
    return TestClient(server.app)


def test_rule_can_be_turned_off_and_on(client):
    assert client.post("/api/rules/r1/enabled", json={"enabled": False}).json()["ok"] is True
    assert client.get("/api/status").json()["rules"] == []
    client.post("/api/rules/r1/enabled", json={"enabled": True})
    assert len(client.get("/api/status").json()["rules"]) == 1


def test_rule_can_be_deleted(client):
    assert client.delete("/api/rules/r1").json()["ok"] is True
    assert client.get("/api/status").json()["rules"] == []
