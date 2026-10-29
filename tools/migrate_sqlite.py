"""SQLite 로 쌓아 둔 기록을 Postgres 로 옮긴다. 한 번만 쓴다."""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.store import Store

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "data/monitor.db")


def main() -> None:
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    dst = Store()
    moved = {}

    rows = src.execute("SELECT ts, metric, labels, value, text FROM samples").fetchall()
    for ts, metric, labels, value, text in rows:
        dst.put(metric, json.loads(labels), value, text, ts=ts)
    moved["samples"] = len(rows)

    rows = src.execute("SELECT id, enabled, severity, title, spec FROM rules").fetchall()
    for rid, enabled, sev, title, spec in rows:
        dst.put_rule(rid, sev, title, json.loads(spec), enabled=bool(enabled))
    moved["rules"] = len(rows)

    rows = src.execute("SELECT ts, rule_id, state, detail FROM findings").fetchall()
    for ts, rid, state, detail in rows:
        dst.put_finding(rid, state, detail, ts=ts)
    moved["findings"] = len(rows)

    try:
        rows = src.execute(
            "SELECT ts, rule_id, action_id, verdict, reason, params, outcome, detail, revert"
            " FROM actions").fetchall()
    except sqlite3.OperationalError:
        rows = []
    for ts, rid, aid, verdict, reason, params, outcome, detail, revert in rows:
        dst.put_action(rid, aid, verdict, reason, json.loads(params) if params else None,
                       outcome, detail, revert, ts=ts)
    moved["actions"] = len(rows)

    src.close()
    dst.close()
    for k, v in moved.items():
        print(f"{k:10} {v:>7,}행")


if __name__ == "__main__":
    main()
