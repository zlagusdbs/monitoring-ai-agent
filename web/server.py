"""대시보드 + 채팅 + plan. 호스트에서 돈다 (구독 인증이 호스트에 묶여 있다).

수집기·평가기는 Docker 안에서 돌며 Postgres 에 쓰고, 여기서는 주로 읽는다.
"""

import json
import os
import sys
import time
from pathlib import Path

import asyncio
import contextlib
import logging

import httpx
import net
import psycopg
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import catalog  # noqa: E402
import executors  # noqa: E402
import policy  # noqa: E402
import throttling  # noqa: E402
from collector.evaluator import evaluate  # noqa: E402
from collector.store import Store  # noqa: E402
from web import checks, runner  # noqa: E402
from agent import ops  # noqa: E402  커스텀 도구 4개가 들어 있는 in-process MCP 서버
from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

DSN = os.getenv("MON_DSN", "postgresql://monitor:monitor@127.0.0.1:5433/monitor")
DSN_RO = os.getenv("MON_DSN_RO", "postgresql://monitor_ro:monitor_ro@127.0.0.1:5433/monitor")
STARTED = int(time.time())
TICK_SEC = 60

log = logging.getLogger("server")

# 조치는 기본으로 나가지 않는다. 켜도 상한과 화이트리스트를 서버가 다시 본다.
ACTION_ENABLED = os.getenv("MON_ACTION_ENABLED", "").lower() in ("1", "true", "yes")


async def _ask(candidate: dict) -> dict:
    """후보 하나를 에이전트에게 넘기고 decide_action 호출을 받아 온다."""
    prompt = (
        f"규칙 {candidate['rule_id']} ({candidate['severity']}) 이 발동했다.\n"
        f"제목: {candidate['title']}\n"
        f"후보 조치: {candidate['action_id']} — {candidate['action']}\n"
        f"상한 상태: {candidate['limit'] or '여유 있음'}\n"
        f"최근 24시간 이 규칙의 조치 기록: {candidate['history']}\n\n"
        "읽기 전용 도구로 확인한 뒤 decide_action 을 정확히 한 번 호출해라."
    )
    async with ClaudeSDKClient(options=OPTIONS) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if getattr(block, "name", "").endswith("__decide_action"):
                        return getattr(block, "input", {}) or {}
    return {}


async def _act(action_id: str, params: dict) -> dict:
    async with net.async_client(timeout=30) as client:
        return await executors.execute(action_id, params,
                                       enabled=ACTION_ENABLED, client=client)


# 다음 자동 점검까지 남은 시간을 화면에 보여 주려고 마지막 시각을 들고 있는다.
AUTO = {"last_tick": time.time()}


async def _loop() -> None:
    seen: dict[str, str] = {}
    while True:
        await asyncio.sleep(TICK_SEC)
        try:
            store = Store(DSN)
            try:
                stale = _stale_check(store)
                every = int(runner.setting(store, "auto_every_min")) * 60
                if (
                    runner.setting(store, "auto_check") == "on"
                    and time.time() - AUTO["last_tick"] >= every
                ):
                    AUTO["last_tick"] = time.time()
                    await runner.tick(store, seen, now_ts=int(time.time()),
                                      ask=_ask, act=_act)
            finally:
                store.close()
            # 한 주기에 한 건만 — 항목이 많아도 한꺼번에 몰리지 않는다.
            if stale:
                await run_check(stale["name"], stale["question"])
        except Exception:
            log.exception("자동 점검 중 오류 — 다음 주기에 다시 시도한다")


def _stale_check(store: Store) -> dict | None:
    """자동 갱신이 켜져 있을 때, 가장 오래된 항목 하나를 고른다."""
    if runner.setting(store, "checklist_auto") != "on":
        return None
    every = int(runner.setting(store, "checklist_every_min")) * 60
    cutoff = int(time.time()) - every
    stale = [c for c in store.checks() if (c["checked_at"] or 0) < cutoff]
    return min(stale, key=lambda c: c["checked_at"] or 0) if stale else None


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="index monitor", lifespan=lifespan)

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
        "mcp__ops__throttle_preview",
    ],
    tools=[],
    setting_sources=[],
    skills=[],
    permission_mode="dontAsk",
    max_budget_usd=2.0,
    system_prompt=CHAT_SYSTEM,
)


def _db() -> psycopg.Connection:
    return psycopg.connect(DSN_RO)


def _write_db() -> Store:
    return Store(DSN)


def _evaluate_now() -> None:
    """규칙을 바꾸면 바로 다시 판정한다. 5분을 기다리면 옛 판정이 그대로 보인다."""
    store = _write_db()
    try:
        evaluate(store)
    except Exception:
        log.exception("즉시 평가 실패 — 다음 수집 주기에 다시 한다")
    finally:
        store.close()


def _ready() -> bool:
    try:
        _db().close()
        return True
    except psycopg.Error:
        return False


@app.get("/api/status")
def status() -> dict:
    if not _ready():
        return {"ready": False, "reason": "Postgres 에 붙지 못했다 — docker compose up -d"}
    c = _db()
    rules = []
    for rid, sev, title, spec, updated in c.execute(
        "SELECT id, severity, title, spec, updated FROM rules WHERE enabled ORDER BY id"
    ).fetchall():
        row = c.execute(
            "SELECT state, detail, ts FROM findings WHERE rule_id=%s ORDER BY ts DESC LIMIT 1",
            (rid,),
        ).fetchone()
        state, detail, ts = row if row else ("-", "", 0)
        rules.append(
            {
                "id": rid, "severity": sev, "title": title, "state": state,
                "detail": detail, "ts": ts, "updated": updated, "spec": spec,
                "action": spec.get("action") or {},
            }
        )
    # 가장 최근 수집 주기의 값만 보여 준다. 수집을 멈춘 항목(예: 범위에서 빠진
    # seller)의 옛 샘플이 "현재값"처럼 남지 않게 하려는 것이다.
    last = c.execute("SELECT MAX(ts) FROM samples").fetchone()[0] or 0
    metrics: dict[str, list] = {}
    rows = c.execute(
        "SELECT metric, labels, value, text, ts FROM samples WHERE ts=%s", (last,)
    ).fetchall()
    for metric, l, v, t, ts in rows:
        metrics.setdefault(metric, []).append(
            {"labels": l, "value": v, "text": t, "ts": ts}
        )
    total = c.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    c.close()
    return {
        "ready": True, "rules": rules, "metrics": metrics,
        "labels": policy.get("labels", {}),
        "samples": total, "last_collect": last, "now": int(time.time()),
    }


IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _unpack(raw: str) -> tuple[str, list[dict]]:
    """채팅 프레임을 (글, 이미지들) 로 나눈다. 옛 형식(글자만)도 그대로 받는다."""
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw, []
    if not isinstance(payload, dict):
        return raw, []
    images = [
        im for im in (payload.get("images") or [])
        if im.get("media_type") in IMAGE_TYPES
        and len(im.get("data") or "") <= MAX_IMAGE_BYTES * 4 // 3
    ]
    return str(payload.get("text") or ""), images[:3]


async def _as_message(text: str, images: list[dict]):
    """이미지는 content block 으로 넣어야 한다. 문자열로는 못 보낸다."""
    content: list[dict] = [
        {"type": "image",
         "source": {"type": "base64", "media_type": im["media_type"], "data": im["data"]}}
        for im in images
    ]
    if text:
        content.append({"type": "text", "text": text})
    yield {
        "type": "user",
        "message": {"role": "user", "content": content},
        "parent_tool_use_id": None,
        "session_id": "default",
    }


@app.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        async with ClaudeSDKClient(options=OPTIONS) as client:
            while True:
                raw = await ws.receive_text()
                text, images = _unpack(raw)
                command = checks.parse_command(text)
                if command:
                    name, question = command
                    await ws.send_json({"type": "text", "text": f"체크리스트에 '{name}' 추가. 확인 중…"})
                    await run_check(name, question)
                    await ws.send_json({"type": "checks"})
                    await ws.send_json({"type": "done", "subtype": "check"})
                    continue
                await client.query(_as_message(text, images) if images else text)
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
    store = _write_db()
    try:
        store.put_rule(rule["rule_id"], rule.get("severity", "medium"), rule["title"], spec)
    finally:
        store.close()
    _evaluate_now()
    return {"ok": True, "id": rule["rule_id"]}


@app.get("/api/report")
def report() -> dict:
    if not _ready():
        return {"started": STARTED, "items": [], "todo": []}
    store = Store(DSN)
    try:
        items = store.actions_since(STARTED)
        findings = store.conn.execute(
            "SELECT ts, rule_id, state, detail FROM findings WHERE ts >= %s ORDER BY ts",
            (STARTED,),
        ).fetchall()
    finally:
        store.close()
    return {
        "started": STARTED,
        "now": int(time.time()),
        "items": items,
        "findings": [
            {"ts": ts, "rule_id": rid, "state": st, "detail": d}
            for ts, rid, st, d in findings
        ],
        "todo": _todo(items),
    }


def _todo(items: list[dict]) -> list[str]:
    out = []
    for a in items:
        if a["verdict"] == "escalate":
            out.append(f"{a['rule_id']} — 사람이 봐야 함: {a['reason']}")
        elif a["outcome"] == "blocked":
            out.append(f"{a['rule_id']} — 상한에 걸려 못 함: {a['detail']}")
        elif a["outcome"] == "disabled":
            out.append(f"{a['rule_id']} — 실행이 꺼져 있어 기록만 남았다")
        elif a["outcome"] == "sent" and a["action_id"] == "trigger_coupon_full":
            out.append(f"{a['rule_id']} — 색인 결과를 확인하고 Active 전환이 필요한지 본다")
    return out


@app.get("/api/settings")
def get_settings() -> dict:
    if not _ready():
        return dict(runner.DEFAULTS)
    store = Store(DSN)
    try:
        out = {k: runner.setting(store, k) for k in runner.DEFAULTS}
    finally:
        store.close()
    out["action_enabled"] = ACTION_ENABLED
    out["auto_next_in"] = _next_tick_in(out)
    return out


def _next_tick_in(settings: dict) -> int:
    """다음 자동 점검까지 남은 초. 꺼져 있으면 -1."""
    if settings.get("auto_check") != "on":
        return -1
    every = int(settings.get("auto_every_min", 1)) * 60
    left = AUTO["last_tick"] + every - time.time()
    return max(0, min(every, int(round(left))))


async def _investigate(name: str, question: str) -> tuple[str, str]:
    """에이전트에게 한 번 물어보고 판정과 한 줄 요약을 받는다."""
    said: list[str] = []
    async with ClaudeSDKClient(options=OPTIONS) as client:
        await client.query(checks.prompt_for(name, question))
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        said.append(block.text)
    return checks.parse_answer("\n".join(said))


async def run_check(name: str, question: str) -> dict:
    store = _write_db()
    try:
        name = checks.resolve_name(name, [c["name"] for c in store.checks()])
        store.put_check(name, question)
        try:
            state, answer = await asyncio.wait_for(_investigate(name, question), 180)
        except asyncio.TimeoutError:
            state, answer = "unknown", "타임아웃 (180초)"
        except Exception as e:  # 에이전트가 죽어도 항목은 남는다
            state, answer = "unknown", f"{type(e).__name__}: {e}"
        store.set_check_result(name, state, answer)
    finally:
        store.close()
    return {"name": name, "state": state, "result": answer}


@app.get("/api/checks")
def list_checks() -> dict:
    if not _ready():
        return {"checks": []}
    store = Store(DSN)
    try:
        return {"checks": store.checks()}
    finally:
        store.close()


@app.post("/api/checks/{name}/run")
async def rerun_check(name: str) -> dict:
    store = Store(DSN)
    try:
        row = next((c for c in store.checks() if c["name"] == name), None)
    finally:
        store.close()
    if row is None:
        return {"ok": False, "error": f"없는 항목: {name}"}
    result = await run_check(name, row["question"])
    return {"ok": result["state"] == "ok", **result}


@app.post("/api/checks/{name}/rename")
def rename_check(name: str, req: dict = Body(...)) -> dict:
    new_name = (req.get("name") or "").strip()
    if not new_name:
        return {"ok": False, "error": "새 이름이 비어 있다"}
    store = _write_db()
    try:
        ok = store.rename_check(name, new_name)
    finally:
        store.close()
    return {"ok": ok, "name": new_name} if ok else {
        "ok": False, "error": f"이미 있는 이름이거나 없는 항목: {new_name}"}


@app.delete("/api/checks/{name}")
def remove_check(name: str) -> dict:
    store = _write_db()
    try:
        store.delete_check(name)
    finally:
        store.close()
    return {"ok": True, "name": name}


@app.get("/api/series")
def series(metric: str, minutes: int = 120) -> dict:
    """그래프용 시계열. labels 조합마다 한 줄로 묶어 돌려준다."""
    if not _ready():
        return {"metric": metric, "lines": []}
    since = int(time.time()) - max(1, minutes) * 60
    store = Store(DSN)
    try:
        rows = store.conn.execute(
            "SELECT ts, labels, value FROM samples"
            " WHERE metric=%s AND ts>=%s AND value IS NOT NULL ORDER BY ts",
            (metric, since),
        ).fetchall()
    finally:
        store.close()
    lines: dict[str, dict] = {}
    for ts, labels, value in rows:
        key = json.dumps(labels, sort_keys=True, ensure_ascii=False)
        line = lines.setdefault(key, {"labels": labels, "points": []})
        line["points"].append({"ts": ts, "value": value})
    return {"metric": metric, "lines": list(lines.values())}


@app.post("/api/settings")
def set_settings(values: dict = Body(...)) -> dict:
    store = _write_db()
    try:
        for k, v in values.items():
            if k in runner.DEFAULTS:
                store.set_setting(k, str(v))
    finally:
        store.close()
    return {"ok": True}


@app.post("/api/action")
async def run_action(req: dict = Body(...)) -> dict:
    """사람이 화면에서 누르는 실행. 에이전트는 이 경로에 닿지 못한다."""
    action_id = req.get("action_id", "")
    if catalog.get(action_id) is None:
        return {"ok": False, "error": f"카탈로그에 없는 조치: {action_id}"}
    store = _write_db()
    try:
        now = int(time.time())
        why = catalog.check_limits(store, action_id, now)
        if why:
            return {"ok": False, "error": why}
        params = catalog.fixed_params(action_id) | (req.get("params") or {})
        result = await _act(action_id, params)
        store.put_action(req.get("rule_id", "manual"), action_id, "execute",
                         req.get("reason") or "화면에서 사람이 실행", params=params,
                         outcome=result["outcome"], detail=result["detail"],
                         revert=result.get("revert"), ts=now)
    finally:
        store.close()
    return {"ok": result["outcome"] in ("sent", "dry_only"), **result}


@app.post("/api/rules/{rule_id}/enabled")
def set_rule_enabled(rule_id: str, req: dict = Body(...)) -> dict:
    store = _write_db()
    try:
        ok = store.set_rule_enabled(rule_id, bool(req.get("enabled")))
    finally:
        store.close()
    if not ok:
        return {"ok": False, "error": f"없는 규칙: {rule_id}"}
    _evaluate_now()
    return {"ok": True, "id": rule_id}


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: str) -> dict:
    store = _write_db()
    try:
        store.delete_rule(rule_id)
    finally:
        store.close()
    return {"ok": True, "id": rule_id}


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
        r = net.post(
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
