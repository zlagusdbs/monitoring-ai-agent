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
    return TestClient(server.app)


def test_series_groups_points_by_label_set(client, store):
    store.put("api_latency_p99_ms", {"resource_name": "a"}, 10.0, ts=NOW - 60)
    store.put("api_latency_p99_ms", {"resource_name": "a"}, 12.0, ts=NOW - 30)
    store.put("api_latency_p99_ms", {"resource_name": "b"}, 99.0, ts=NOW - 30)
    lines = client.get("/api/series", params={"metric": "api_latency_p99_ms"}).json()["lines"]
    by_name = {l["labels"]["resource_name"]: l["points"] for l in lines}
    assert [p["value"] for p in by_name["a"]] == [10.0, 12.0]
    assert len(by_name["b"]) == 1


def test_series_respects_the_window(client, store):
    store.put("m", {}, 1.0, ts=NOW - 7200)
    store.put("m", {}, 2.0, ts=NOW - 60)
    lines = client.get("/api/series", params={"metric": "m", "minutes": 30}).json()["lines"]
    assert [p["value"] for p in lines[0]["points"]] == [2.0]


def test_series_skips_rows_without_a_value(client, store):
    store.put("m", {}, None, text="Active", ts=NOW - 60)
    assert client.get("/api/series", params={"metric": "m"}).json()["lines"] == []
