"""수집한 관측값을 SQLite 에 시계열로 쌓는다.

숫자값(value)과 문자값(text)을 한 테이블에 담는다. alias 가 가리키는
인덱스 이름처럼 숫자가 아닌 관측도 "언제 무엇이었나"를 봐야 하기 때문이다.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts     INTEGER NOT NULL,
    metric TEXT    NOT NULL,
    labels TEXT    NOT NULL,
    value  REAL,
    text   TEXT
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_ts ON samples(metric, ts);

-- 규칙. 에이전트가 자연어를 컴파일해 여기에 넣고, 평가기는 읽기만 한다.
CREATE TABLE IF NOT EXISTS rules (
    id       TEXT PRIMARY KEY,
    enabled  INTEGER NOT NULL DEFAULT 1,
    severity TEXT    NOT NULL,
    title    TEXT    NOT NULL,
    spec     TEXT    NOT NULL,   -- JSON: check / guard
    updated  INTEGER NOT NULL
);

-- 규칙이 발동한 기록.
CREATE TABLE IF NOT EXISTS findings (
    ts      INTEGER NOT NULL,
    rule_id TEXT    NOT NULL,
    state   TEXT    NOT NULL,   -- firing | ok | skipped
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_rule_ts ON findings(rule_id, ts);

CREATE TABLE IF NOT EXISTS actions (
    ts        INTEGER NOT NULL,
    rule_id   TEXT    NOT NULL,
    action_id TEXT    NOT NULL,
    verdict   TEXT    NOT NULL,
    reason    TEXT,
    params    TEXT,
    outcome   TEXT,
    detail    TEXT,
    revert    TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT    NOT NULL,
    updated INTEGER NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def put(
        self,
        metric: str,
        labels: dict[str, str],
        value: float | None = None,
        text: str | None = None,
        ts: int | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO samples (ts, metric, labels, value, text) VALUES (?,?,?,?,?)",
            (ts or int(time.time()), metric, json.dumps(labels, sort_keys=True), value, text),
        )

    def latest(self, metric: str) -> list[dict[str, Any]]:
        """metric 의 labels 조합마다 가장 최근 샘플 하나씩."""
        rows = self.conn.execute(
            """
            SELECT labels, ts, value, text FROM samples s
            WHERE metric = ? AND ts = (
                SELECT MAX(ts) FROM samples WHERE metric = s.metric AND labels = s.labels
            )
            """,
            (metric,),
        ).fetchall()
        return [
            {"labels": json.loads(l), "ts": ts, "value": v, "text": t}
            for l, ts, v, t in rows
        ]

    def series(self, metric: str, labels: dict[str, str], since: int) -> list[tuple[int, float]]:
        """한 labels 조합의 since 이후 (ts, value) 목록. 시간에 걸친 판단에 쓴다."""
        rows = self.conn.execute(
            "SELECT ts, value FROM samples WHERE metric=? AND labels=? AND ts>=? ORDER BY ts",
            (metric, json.dumps(labels, sort_keys=True), since),
        ).fetchall()
        return [(ts, v) for ts, v in rows if v is not None]

    def put_rule(self, rule_id: str, severity: str, title: str, spec: dict, enabled: bool = True):
        self.conn.execute(
            "INSERT OR REPLACE INTO rules (id, enabled, severity, title, spec, updated)"
            " VALUES (?,?,?,?,?,?)",
            (rule_id, int(enabled), severity, title, json.dumps(spec, ensure_ascii=False),
             int(time.time())),
        )

    def rules(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, severity, title, spec FROM rules WHERE enabled=1"
        ).fetchall()
        return [
            {"id": i, "severity": sev, "title": t, "spec": json.loads(sp)}
            for i, sev, t, sp in rows
        ]

    def put_finding(self, rule_id: str, state: str, detail: str | None = None,
                    ts: int | None = None):
        self.conn.execute(
            "INSERT INTO findings (ts, rule_id, state, detail) VALUES (?,?,?,?)",
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
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (ts or int(time.time()), rule_id, action_id, verdict, reason,
             json.dumps(params, ensure_ascii=False) if params is not None else None,
             outcome, detail, revert),
        )

    def actions_since(self, since: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT ts, rule_id, action_id, verdict, reason, params, outcome, detail, revert"
            " FROM actions WHERE ts >= ? ORDER BY ts",
            (since,),
        ).fetchall()
        return [
            {
                "ts": ts, "rule_id": rid, "action_id": aid, "verdict": v, "reason": reason,
                "params": json.loads(params) if params else None,
                "outcome": outcome, "detail": detail, "revert": revert,
            }
            for ts, rid, aid, v, reason, params, outcome, detail, revert in rows
        ]

    def count_actions(
        self,
        action_id: str,
        since: int,
        outcomes: tuple[str, ...] = ("sent", "dry_only"),
    ) -> int:
        marks = ",".join("?" * len(outcomes))
        return self.conn.execute(
            f"SELECT COUNT(*) FROM actions WHERE action_id=? AND ts>=? AND outcome IN ({marks})",
            (action_id, since, *outcomes),
        ).fetchone()[0]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated) VALUES (?,?,?)",
            (key, value, int(time.time())),
        )

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]

    def checkpoint(self) -> None:
        """WAL 내용을 본체 파일로 넘긴다.

        읽는 쪽(웹 서버·에이전트)은 mode=ro 로 여는데, 읽기 전용 연결은 WAL 을
        따라가지 못해 본체 파일만 본다. 주기마다 넘겨 줘야 최신값이 보인다.
        """
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self) -> None:
        self.conn.close()
