"""대시보드 + 채팅 + plan. 호스트에서 돈다 (구독 인증이 호스트에 묶여 있다).

수집기·평가기는 Docker 안에서 돌며 data/monitor.db 에 쓰고, 여기서는 읽기만 한다.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import policy  # noqa: E402
import throttling  # noqa: E402
from agent import ops  # noqa: E402  커스텀 도구 4개가 들어 있는 in-process MCP 서버
from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

DB = ROOT / "data" / "monitor.db"
app = FastAPI(title="index monitor")

# 운영 트래픽을 막는 유일한 경로다. 기본은 꺼져 있고, 켜려면 환경변수를 명시해야 한다.
THROTTLE_ENABLED = os.getenv("MON_THROTTLE_ENABLED", "").lower() in ("1", "true", "yes")

CHAT_SYSTEM = (
    "너는 색인 파이프라인의 모니터링 담당이다.\n"
    "발동 판단은 규칙 평가기가 이미 끝냈다. 너는 그 판정을 다시 내리지 않는다.\n"
    "너의 일은 발동한 것을 설명하고, 맥락을 확인하고, 다음 수를 제안하는 것이다.\n"
    "\n"
    "- 주어진 읽기 전용 도구로만 사실을 확인한다. 추측으로 수치를 만들지 않는다.\n"
    "- 확인하지 못한 것은 '미확인'이라고 분명히 말한다.\n"
    f"- 운영 상식: {policy.get('notes.operating', '(없음)')}\n"
    "- 조치를 제안할 때는 실행할 명령 하나와 되돌리는 법을 같이 적는다. "
    "운영에 영향을 주는 조치는 네가 실행하지 않는다.\n"
    "- 답은 짧게. 화면 폭이 좁다.\n"
    "- 사용자가 '무엇을 감시해 달라'고 하면 propose_rule 로 규칙을 컴파일해 제안한다. "
    "저장은 사용자가 화면에서 승인할 때 일어난다. 네가 저장하지 않는다.\n"
    "답변은 한국어로 한다."
)

OPTIONS = ClaudeAgentOptions(
    model="claude-opus-5-5",
    mcp_servers={"ops": ops},
    allowed_tools=[
        "mcp__ops__propose_rule",
        "mcp__ops__monitor_status",
        "mcp__ops__monitor_series",
        "mcp__ops__prom_query",
        "mcp__ops__admin_get",
    ],
    tools=[],
    setting_sources=[],
    skills=[],
    permission_mode="dontAsk",
    max_budget_usd=2.0,
    system_prompt=CHAT_SYSTEM,
)


def _db() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


@app.get("/api/status")
def status() -> dict:
    if not DB.exists():
        return {"ready": False, "reason": "수집기가 아직 DB 를 만들지 않았다"}
    c = _db()
    rules = []
    for rid, sev, title, spec in c.execute(
        "SELECT id, severity, title, spec FROM rules WHERE enabled=1"
    ):
        row = c.execute(
            "SELECT state, detail, ts FROM findings WHERE rule_id=? ORDER BY ts DESC LIMIT 1",
            (rid,),
        ).fetchone()
        state, detail, ts = row if row else ("-", "", 0)
        rules.append(
            {
                "id": rid, "severity": sev, "title": title, "state": state,
                "detail": detail, "ts": ts, "spec": json.loads(spec),
                "action": json.loads(spec).get("action") or {},
            }
        )
    # 가장 최근 수집 주기의 값만 보여 준다. 수집을 멈춘 항목(예: 범위에서 빠진
    # seller)의 옛 샘플이 "현재값"처럼 남지 않게 하려는 것이다.
    last = c.execute("SELECT MAX(ts) FROM samples").fetchone()[0] or 0
    metrics: dict[str, list] = {}
    for metric in (
        "cluster_status", "alias_index", "index_docs", "topic_offset_latest",
        "es_cpu_percent", "es_heap_percent", "es_search_qps", "price_api_rps",
    ):
        rows = c.execute(
            "SELECT labels, value, text, ts FROM samples WHERE metric=? AND ts=?",
            (metric, last),
        ).fetchall()
        metrics[metric] = [
            {"labels": json.loads(l), "value": v, "text": t, "ts": ts} for l, v, t, ts in rows
        ]
    total = c.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    c.close()
    return {
        "ready": True, "rules": rules, "metrics": metrics,
        "samples": total, "last_collect": last, "now": int(time.time()),
    }


@app.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        async with ClaudeSDKClient(options=OPTIONS) as client:
            while True:
                text = await ws.receive_text()
                await client.query(text)
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if hasattr(block, "text") and block.text:
                                await ws.send_json({"type": "text", "text": block.text})
                            elif hasattr(block, "name"):
                                inp = getattr(block, "input", {}) or {}
                                if block.name.endswith("__propose_rule"):
                                    await ws.send_json({"type": "proposal", "rule": inp})
                                else:
                                    await ws.send_json(
                                        {"type": "tool", "name": block.name, "input": inp}
                                    )
                    elif isinstance(message, ResultMessage):
                        await ws.send_json({"type": "done", "subtype": message.subtype})
    except WebSocketDisconnect:
        return
    except Exception as e:  # 에이전트가 죽어도 소켓은 조용히 닫는다
        try:
            await ws.send_json({"type": "error", "text": f"{type(e).__name__}: {e}"})
        except Exception:
            pass


@app.post("/api/rules")
def add_rule(rule: dict = Body(...)) -> dict:
    """사람이 승인한 규칙만 저장한다. 에이전트는 이 경로에 닿지 못한다."""
    try:
        spec = {
            "check": {"type": rule["check_type"], **json.loads(rule["check_fields"])},
            "guard": json.loads(rule.get("guards") or "[]"),
            "action": json.loads(rule.get("action") or "{}"),
        }
    except (KeyError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)}
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT OR REPLACE INTO rules (id, enabled, severity, title, spec, updated)"
        " VALUES (?,1,?,?,?,?)",
        (rule["rule_id"], rule.get("severity", "medium"), rule["title"],
         json.dumps(spec, ensure_ascii=False), int(time.time())),
    )
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return {"ok": True, "id": rule["rule_id"]}


@app.post("/api/throttle")
def do_throttle(req: dict = Body(...)) -> dict:
    """사람이 화면에서 누를 때만 호출된다. 에이전트는 이 경로에 닿지 못한다."""
    uri = req.get("uri", "")
    rate = req.get("rate", 100)
    ttl = req.get("ttl_minutes", 0)
    why = throttling.validate(uri, rate, ttl)
    if why:
        return {"ok": False, "error": why}
    if not THROTTLE_ENABLED:
        return {
            "ok": False,
            "error": "실행이 꺼져 있다 (MON_THROTTLE_ENABLED 미설정). 아래 명령으로 직접 실행하라.",
            "curl": throttling.curl(uri, rate, ttl),
            "revert": throttling.revert_curl(uri),
        }
    try:
        r = httpx.post(
            f"{throttling.BASE}{throttling.PATH}",
            json=throttling.body(uri, rate, ttl),
            timeout=15,
        )
        return {"ok": r.status_code < 300, "status": r.status_code,
                "body": r.text[:500], "revert": throttling.revert_curl(uri)}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "static" / "index.html")
