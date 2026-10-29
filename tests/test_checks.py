import time

import pytest
from fastapi.testclient import TestClient

from tests.conftest import dsn_for
from web import checks, server


def test_parses_name_and_question():
    assert checks.parse_command("/check indexer-coupon-all 상태확인") == (
        "indexer-coupon-all",
        "상태확인",
    )


def test_question_defaults_when_omitted():
    assert checks.parse_command("/check indexer-coupon-all") == (
        "indexer-coupon-all",
        checks.DEFAULT_QUESTION,
    )


def test_keeps_the_whole_question():
    _, question = checks.parse_command("/check a 언제 돌았고 상태는 어땠는지")
    assert question == "언제 돌았고 상태는 어땠는지"


@pytest.mark.parametrize("text", ["안녕", "/checks a", "/check", "/check   "])
def test_other_text_is_not_a_command(text):
    assert checks.parse_command(text) is None


def test_prompt_carries_both():
    p = checks.prompt_for("indexer-coupon-all", "상태확인")
    assert "indexer-coupon-all" in p and "상태확인" in p


@pytest.fixture
def client(store, schema, monkeypatch):
    monkeypatch.setattr(server, "DSN", dsn_for(schema))
    monkeypatch.setattr(server, "DSN_RO", dsn_for(schema))
    return TestClient(server.app)


def test_check_survives_a_restart(client, store):
    store.put_check("indexer-coupon-all", "상태확인")
    store.set_check_result("indexer-coupon-all", "ok", "마지막 produce 10-26 04:12")
    rows = client.get("/api/checks").json()["checks"]
    assert rows[0]["name"] == "indexer-coupon-all"
    assert rows[0]["result"].startswith("마지막 produce")
    assert rows[0]["state"] == "ok"


def test_check_can_be_deleted(client, store):
    store.put_check("a", "상태확인")
    client.delete("/api/checks/a")
    assert client.get("/api/checks").json()["checks"] == []


def test_adding_the_same_name_replaces_the_question(store):
    store.put_check("a", "첫 질문")
    store.set_check_result("a", "ok", "결과")
    store.put_check("a", "두 번째 질문")
    row = store.checks()[0]
    assert row["question"] == "두 번째 질문" and row["state"] == "pending"


def test_checked_at_is_recorded(store):
    store.put_check("a", "q")
    store.set_check_result("a", "ok", "r", ts=1000)
    assert store.checks()[0]["checked_at"] == 1000
    assert store.checks()[0]["created"] <= int(time.time())


def test_stale_check_is_none_while_auto_is_off(store):
    store.put_check("a", "q")
    assert server._stale_check(store) is None


def test_stale_check_picks_the_oldest_overdue_one(store):
    store.set_setting("checklist_auto", "on")
    store.set_setting("checklist_every_min", "30")
    now = int(time.time())
    store.put_check("fresh", "q")
    store.set_check_result("fresh", "ok", "r", ts=now - 60)
    store.put_check("old", "q")
    store.set_check_result("old", "ok", "r", ts=now - 7200)
    store.put_check("older", "q")
    store.set_check_result("older", "ok", "r", ts=now - 9000)
    assert server._stale_check(store)["name"] == "older"


def test_never_checked_items_count_as_overdue(store):
    store.set_setting("checklist_auto", "on")
    store.put_check("new", "q")
    assert server._stale_check(store)["name"] == "new"


def test_verdict_is_parsed_from_the_answer():
    assert checks.parse_answer("FAIL | 3일 연속 0건") == ("fail", "3일 연속 0건")
    assert checks.parse_answer("OK | 정상")[0] == "ok"
    assert checks.parse_answer("UNKNOWN | 못 봄")[0] == "unknown"


def test_bold_and_lowercase_verdicts_still_parse():
    assert checks.parse_answer("**fail** | 0건")[0] == "fail"


def test_answer_without_the_format_is_unknown():
    state, summary = checks.parse_answer("마지막 실행은 어제였습니다")
    assert state == "unknown" and summary.startswith("마지막")


def test_empty_answer_is_unknown():
    assert checks.parse_answer("")[0] == "unknown"


def test_particle_after_an_ascii_name_is_dropped():
    assert checks.resolve_name("indexer-coupon-all은", []) == "indexer-coupon-all"


def test_existing_name_wins_over_stripping():
    assert checks.resolve_name("indexer-coupon-all은", ["indexer-coupon-all"]) == "indexer-coupon-all"


def test_pure_hangul_name_is_left_alone():
    assert checks.resolve_name("쿠폰색인", []) == "쿠폰색인"


def test_exact_name_is_unchanged():
    assert checks.resolve_name("indexer-coupon-all", ["indexer-coupon-all"]) == "indexer-coupon-all"
