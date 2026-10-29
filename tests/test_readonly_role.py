import os

import psycopg
import pytest

RO_DSN = os.getenv("MON_DSN_RO", "postgresql://monitor_ro:monitor_ro@127.0.0.1:5433/monitor")


@pytest.fixture
def ro():
    try:
        c = psycopg.connect(RO_DSN, connect_timeout=2, autocommit=True)
    except psycopg.Error:
        pytest.skip("읽기 전용 역할로 붙지 못했다 — docker compose up -d postgres")
    yield c
    c.close()


def test_agent_role_can_read(ro):
    assert ro.execute("SELECT COUNT(*) FROM samples").fetchone()[0] >= 0


def test_agent_role_cannot_insert(ro):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        ro.execute("INSERT INTO findings (ts, rule_id, state) VALUES (1, 'x', 'firing')")


def test_agent_role_cannot_delete(ro):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        ro.execute("DELETE FROM rules")
