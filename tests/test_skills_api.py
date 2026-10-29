import pytest
from fastapi.testclient import TestClient

import skills
from tests.conftest import dsn_for
from web import server


@pytest.fixture
def client(store, schema, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DSN", dsn_for(schema))
    monkeypatch.setattr(server, "DSN_RO", dsn_for(schema))
    monkeypatch.setattr(skills, "DIR", tmp_path / "skills")
    return TestClient(server.app)


def files(client, group: str) -> list[str]:
    groups = client.get("/api/skills").json()["groups"]
    return next(g["files"] for g in groups if g["id"] == group)


def test_write_read_list_delete(client):
    assert client.put("/api/skills/skills/runbook", json={"body": "# 런북"}).json()["ok"] is True
    assert files(client, "skills") == ["runbook"]
    assert client.get("/api/skills/skills/runbook").json()["body"] == "# 런북"
    assert client.delete("/api/skills/skills/runbook").json()["ok"] is True
    assert files(client, "skills") == []


def test_groups_are_listed_in_order(client):
    assert [g["id"] for g in client.get("/api/skills").json()["groups"]] == [
        "root",
        "rules",
        "skills",
    ]


def test_root_is_read_only(client):
    r = client.get("/api/skills/root/base").json()
    assert r["fixed"] is True
    assert "모니터링 담당" in r["body"]
    assert client.put("/api/skills/root/base", json={"body": "x"}).json()["ok"] is False
    assert client.delete("/api/skills/root/base").json()["ok"] is False


def test_bad_name_is_refused(client):
    r = client.put("/api/skills/skills/..%2Fetc%2Fpasswd", json={"body": "x"})
    assert r.status_code == 404 or r.json()["ok"] is False


def test_unknown_group_is_refused(client):
    assert client.put("/api/skills/nope/a", json={"body": "x"}).json()["ok"] is False


def test_missing_file_reports_it(client):
    assert client.get("/api/skills/skills/nope").json()["ok"] is False


def test_changes_are_logged(client):
    client.put("/api/skills/rules/a", json={"body": "hello"})
    client.delete("/api/skills/rules/a")
    log = client.get("/api/skills").json()["log"]
    assert [row["what"] for row in log] == ["삭제", "저장"]
    assert [row["name"] for row in log] == ["rules/a", "rules/a"]
    assert log[1]["bytes"] == 5


def test_skills_reach_the_system_prompt(client):
    client.put("/api/skills/rules/tone", json={"body": "짧게 답한다"})
    client.put("/api/skills/skills/coupon", json={"body": "쿠폰부터 본다"})
    prompt = server._options().system_prompt
    assert "짧게 답한다" in prompt and "쿠폰부터 본다" in prompt
