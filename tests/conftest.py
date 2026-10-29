import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
import pytest

from collector.store import DSN, Store

TEST_DSN = os.getenv("MON_DSN_TEST", DSN)


def _reachable() -> bool:
    try:
        psycopg.connect(TEST_DSN, connect_timeout=2).close()
        return True
    except psycopg.Error:
        return False


REACHABLE = _reachable()


def dsn_for(schema: str) -> str:
    sep = "&" if "?" in TEST_DSN else "?"
    return f"{TEST_DSN}{sep}options=-c%20search_path%3D{schema}"


@pytest.fixture
def schema():
    if not REACHABLE:
        pytest.skip("Postgres 에 붙지 못했다 — docker compose up -d postgres")
    name = "t_" + uuid.uuid4().hex[:12]
    admin = psycopg.connect(TEST_DSN, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{name}"')
    yield name
    admin.execute(f'DROP SCHEMA "{name}" CASCADE')
    admin.close()


@pytest.fixture
def store(schema):
    s = Store(dsn_for(schema))
    yield s
    s.close()


@pytest.fixture
def store2(schema):
    s = Store(dsn_for(schema))
    yield s
    s.close()
