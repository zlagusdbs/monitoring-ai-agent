import time

import pytest
from fastapi.testclient import TestClient

from tests.conftest import dsn_for
from web import server

NOW = int(time.time())


@pytest.fixture
def client(store, schema, monkeypatch):
    monkeypatch.setattr(server, "DSN", dsn_for(schema))
    monkeypatch.setattr(server, "DSN_RO", dsn_for(schema))
    monkeypatch.setattr(server, "STARTED", NOW)
    return TestClient(server.app)


def test_report_is_scoped_to_session(client, store):
    store.put_action("r", "trigger_coupon_full", "hold", "오래된 것", ts=NOW - 100)
    store.put_action("r", "trigger_coupon_full", "hold", "이번 것", ts=NOW + 10)
    items = client.get("/api/report").json()["items"]
    assert [i["reason"] for i in items] == ["이번 것"]


def test_action_endpoint_rejects_unknown_id(client, store):
    r = client.post("/api/action", json={"action_id": "drop_index"}).json()
    assert r["ok"] is False and "카탈로그" in r["error"]


def test_action_endpoint_rechecks_limit(client, store):
    store.put_action("r", "trigger_coupon_full", "execute", "", outcome="sent", ts=NOW)
    r = client.post("/api/action", json={"action_id": "trigger_coupon_full"}).json()
    assert r["ok"] is False and "상한" in r["error"]


def test_settings_roundtrip(client, store):
    client.post("/api/settings", json={"auto_check": "on"})
    assert client.get("/api/settings").json()["auto_check"] == "on"


def test_report_shows_action_written_in_same_request(client, store):
    client.post("/api/action", json={"action_id": "trigger_coupon_full"})
    assert len(client.get("/api/report").json()["items"]) == 1


def test_todo_mentions_unresolved_escalation(client, store):
    store.put_action("r1", "restart_indexer_pod", "escalate", "사람이 봐야 함", ts=NOW + 5)
    todo = client.get("/api/report").json()["todo"]
    assert any("사람" in t for t in todo)
