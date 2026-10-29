"""수집한 관측값을 Postgres 에 시계열로 쌓는다.

숫자값(value)과 문자값(text)을 한 테이블에 담는다. alias 가 가리키는
인덱스 이름처럼 숫자가 아닌 관측도 "언제 무엇이었나"를 봐야 하기 때문이다.
"""

import os
import time
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

DSN = os.getenv("MON_DSN", "postgresql://monitor:monitor@127.0.0.1:5433/monitor")

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts     BIGINT NOT NULL,
    metric TEXT   NOT NULL,
    labels JSONB  NOT NULL,
    value  DOUBLE PRECISION,
    text   TEXT
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_ts ON samples(metric, ts);

-- 규칙. 에이전트가 자연어를 컴파일해 여기에 넣고, 평가기는 읽기만 한다.
CREATE TABLE IF NOT EXISTS rules (
    id       TEXT PRIMARY KEY,
    enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    severity TEXT    NOT NULL,
    title    TEXT    NOT NULL,
    spec     JSONB   NOT NULL,
    updated  BIGINT  NOT NULL
);

-- 규칙이 발동한 기록.
CREATE TABLE IF NOT EXISTS findings (
    ts      BIGINT NOT NULL,
    rule_id TEXT   NOT NULL,
    state   TEXT   NOT NULL,
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_rule_ts ON findings(rule_id, ts);

CREATE TABLE IF NOT EXISTS actions (
    ts        BIGINT NOT NULL,
    rule_id   TEXT   NOT NULL,
    action_id TEXT   NOT NULL,
    verdict   TEXT   NOT NULL,
    reason    TEXT,
    params    JSONB,
    outcome   TEXT,
    detail    TEXT,
    revert    TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT   NOT NULL,
    updated BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS checks (
    name       TEXT PRIMARY KEY,
    question   TEXT   NOT NULL,
    result     TEXT,
    state      TEXT   NOT NULL,
    checked_at BIGINT,
    created    BIGINT NOT NULL
);
"""


class Store:
    def __init__(self, dsn: str | None = None, schema: str = "public") -> None:
        self.dsn = dsn or DSN
        self.schema = schema
        self.conn = psycopg.connect(self.dsn, autocommit=True)
        if schema != "public":
            self.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            self.conn.execute(f'SET search_path TO "{schema}"')
        self.conn.execute(SCHEMA)

    def put(
        self,
        metric: str,
        labels: dict[str, str],
        value: float | None = None,
        text: str | None = None,
        ts: int | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO samples (ts, metric, labels, value, text) VALUES (%s,%s,%s,%s,%s)",
            (ts or int(time.time()), metric, Jsonb(labels), value, text),
        )

    def latest(self, metric: str) -> list[dict[str, Any]]:
        """metric 의 labels 조합마다 가장 최근 샘플 하나씩."""
        rows = self.conn.execute(
            """
            SELECT DISTINCT ON (labels) labels, ts, value, text
            FROM samples WHERE metric = %s
            ORDER BY labels, ts DESC
            """,
            (metric,),
        ).fetchall()
        return [{"labels": l, "ts": ts, "value": v, "text": t} for l, ts, v, t in rows]

    def series(self, metric: str, labels: dict[str, str], since: int) -> list[tuple[int, float]]:
        """한 labels 조합의 since 이후 (ts, value) 목록. 시간에 걸친 판단에 쓴다."""
        rows = self.conn.execute(
            "SELECT ts, value FROM samples"
            " WHERE metric=%s AND labels=%s AND ts>=%s ORDER BY ts",
            (metric, Jsonb(labels), since),
        ).fetchall()
        return [(ts, v) for ts, v in rows if v is not None]

    def put_rule(self, rule_id: str, severity: str, title: str, spec: dict,
                 enabled: bool = True) -> None:
        self.conn.execute(
            "INSERT INTO rules (id, enabled, severity, title, spec, updated)"
            " VALUES (%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (id) DO UPDATE SET enabled=EXCLUDED.enabled,"
            " severity=EXCLUDED.severity, title=EXCLUDED.title, spec=EXCLUDED.spec,"
            " updated=EXCLUDED.updated",
            (rule_id, enabled, severity, title, Jsonb(spec), int(time.time())),
        )

    def put_rule_if_absent(self, rule_id: str, severity: str, title: str,
                           spec: dict, enabled: bool = False) -> bool:
        cur = self.conn.execute(
            "INSERT INTO rules (id, enabled, severity, title, spec, updated)"
            " VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (rule_id, enabled, severity, title, Jsonb(spec), int(time.time())),
        )
        return cur.rowcount > 0

    def set_rule_enabled(self, rule_id: str, enabled: bool) -> None:
        self.conn.execute("UPDATE rules SET enabled=%s, updated=%s WHERE id=%s",
                          (enabled, int(time.time()), rule_id))

    def delete_rule(self, rule_id: str) -> None:
        self.conn.execute("DELETE FROM rules WHERE id=%s", (rule_id,))

    def rules(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, severity, title, spec FROM rules WHERE enabled ORDER BY id"
        ).fetchall()
        return [{"id": i, "severity": sev, "title": t, "spec": sp} for i, sev, t, sp in rows]

    def put_finding(self, rule_id: str, state: str, detail: str | None = None,
                    ts: int | None = None) -> None:
        self.conn.execute(
            "INSERT INTO findings (ts, rule_id, state, detail) VALUES (%s,%s,%s,%s)",
            (ts or int(time.time()), rule_id, state, detail),
        )

    def put_action(
        self,
        rule_id: str,
        action_id: str,
        verdict: str,
        reason: str,
        params: dict | None = None,
        outcome: str | None = None,
        detail: str | None = None,
        revert: str | None = None,
        ts: int | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO actions"
            " (ts, rule_id, action_id, verdict, reason, params, outcome, detail, revert)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (ts or int(time.time()), rule_id, action_id, verdict, reason,
             Jsonb(params) if params is not None else None, outcome, detail, revert),
        )

    def actions_since(self, since: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT ts, rule_id, action_id, verdict, reason, params, outcome, detail, revert"
            " FROM actions WHERE ts >= %s ORDER BY ts",
            (since,),
        ).fetchall()
        return [
            {"ts": ts, "rule_id": rid, "action_id": aid, "verdict": v, "reason": reason,
             "params": params, "outcome": outcome, "detail": detail, "revert": revert}
            for ts, rid, aid, v, reason, params, outcome, detail, revert in rows
        ]

    def count_actions(
        self,
        action_id: str,
        since: int,
        outcomes: tuple[str, ...] = ("sent", "dry_only"),
    ) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM actions"
            " WHERE action_id=%s AND ts>=%s AND outcome = ANY(%s)",
            (action_id, since, list(outcomes)),
        ).fetchone()[0]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key=%s", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value, updated) VALUES (%s,%s,%s)"
            " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated=EXCLUDED.updated",
            (key, value, int(time.time())),
        )

    def put_check(self, name: str, question: str) -> None:
        self.conn.execute(
            "INSERT INTO checks (name, question, state, created) VALUES (%s,%s,'pending',%s)"
            " ON CONFLICT (name) DO UPDATE SET question=EXCLUDED.question, state='pending'",
            (name, question, int(time.time())),
        )

    def set_check_result(self, name: str, state: str, result: str,
                         ts: int | None = None) -> None:
        self.conn.execute(
            "UPDATE checks SET state=%s, result=%s, checked_at=%s WHERE name=%s",
            (state, result, ts or int(time.time()), name),
        )

    def checks(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT name, question, result, state, checked_at, created"
            " FROM checks ORDER BY created"
        ).fetchall()
        return [
            {"name": n, "question": q, "result": r, "state": s,
             "checked_at": at, "created": c}
            for n, q, r, s, at, c in rows
        ]

    def rename_check(self, name: str, new_name: str) -> bool:
        cur = self.conn.execute(
            "UPDATE checks SET name=%s WHERE name=%s AND NOT EXISTS"
            " (SELECT 1 FROM checks WHERE name=%s)",
            (new_name, name, new_name),
        )
        return cur.rowcount > 0

    def delete_check(self, name: str) -> None:
        self.conn.execute("DELETE FROM checks WHERE name=%s", (name,))

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
