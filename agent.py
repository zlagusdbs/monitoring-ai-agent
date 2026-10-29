"""색인 파이프라인 모니터링 에이전트 — 읽기 전용.

역할 분담이 핵심이다.
  - 발동 판단: 수집기 안의 규칙 평가기가 결정론적으로 한다 (LLM 아님)
  - 이 에이전트: 발동한 것을 설명하고, 맥락을 확인하고, 다음 수를 제안한다

내장 도구(Bash/Write/Edit/Read/...)는 전부 막혀 있다. 아래 네 개의
읽기 전용 도구가 이 에이전트가 할 수 있는 일의 전부다.

인증은 Claude Code 에 로그인된 구독 자격을 그대로 쓴다. API 키를 넣지 않는다
(ANTHROPIC_API_KEY 가 설정돼 있으면 그쪽이 우선하므로 비워 둬야 한다).

실행:
    pip install -r requirements-agent.txt
    python agent.py          # 한 번 점검하고 끝
    uvicorn web.server:app   # 대시보드 + 채팅
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import throttling

import httpx
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolAnnotations,
    create_sdk_mcp_server,
    query,
    tool,
)

import catalog
import policy

PROM = policy.get("endpoints.prometheus", "")
ADMIN = policy.get("endpoints.admin", "")
DB = Path(__file__).parent / "data" / "monitor.db"


@tool(
    "prom_query",
    "Prometheus 에 PromQL 즉시 쿼리를 보낸다. 읽기 전용.",
    {"promql": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def prom_query(args: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{PROM}/api/v1/query", params={"query": args["promql"]})
    return {"content": [{"type": "text", "text": r.text[:4000]}]}


@tool(
    "admin_get",
    "admin API 의 읽기 전용 GET 을 호출한다. path 는 슬래시로 시작한다. "
    "쓸 수 있는 경로: " + policy.get("admin_paths.doc", "(policy.json 에 없음)"),
    {"path": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def admin_get(args: dict[str, Any]) -> dict[str, Any]:
    path = args["path"]
    if not path.startswith("/"):
        return {"content": [{"type": "text", "text": "path 는 '/' 로 시작해야 한다"}]}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{ADMIN}{path}")
    return {"content": [{"type": "text", "text": f"HTTP {r.status_code}\n{r.text[:4000]}"}]}


def _db() -> sqlite3.Connection:
    """수집기가 쓰는 DB 를 읽기 전용으로 연다. 쓰기는 절대 하지 않는다."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


@tool(
    "monitor_status",
    "수집기와 규칙 평가기의 현재 상태를 돌려준다. 규칙별 최신 판정(firing/ok/skipped)과 "
    "마지막으로 수집된 관측값이 들어 있다. 조사의 출발점으로 항상 먼저 호출한다.",
    {},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def monitor_status(args: dict[str, Any]) -> dict[str, Any]:
    c = _db()
    out: list[str] = ["## 규칙 판정"]
    for rid, sev, title in c.execute("SELECT id, severity, title FROM rules WHERE enabled=1"):
        row = c.execute(
            "SELECT state, detail, ts FROM findings WHERE rule_id=? ORDER BY ts DESC LIMIT 1",
            (rid,),
        ).fetchone()
        state, detail, ts = row if row else ("-", "-", 0)
        age = int(time.time()) - (ts or 0)
        out.append(f"- [{state}] {sev} / {rid} — {title}\n  {detail} ({age}초 전 판정)")
    out.append("\n## 최신 관측값")
    for metric in ("cluster_status", "alias_index", "index_docs", "topic_offset_latest"):
        rows = c.execute(
            """SELECT labels, value, text FROM samples s WHERE metric=? AND ts=(
                   SELECT MAX(ts) FROM samples WHERE metric=s.metric AND labels=s.labels)""",
            (metric,),
        ).fetchall()
        for labels, value, text in rows:
            v = text if text is not None else (f"{value:,.0f}" if value is not None else "-")
            out.append(f"- {metric} {labels} = {v}")
    c.close()
    return {"content": [{"type": "text", "text": "\n".join(out)}]}


@tool(
    "monitor_series",
    "수집기가 쌓은 시계열을 돌려준다. metric 은 topic_offset_latest / index_docs / "
    "alias_index / cluster_status 중 하나. minutes 는 조회할 과거 범위(분). "
    "추이를 봐야 판단되는 것(증가가 멈췄는지 등)에 쓴다.",
    {"metric": str, "minutes": int},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def monitor_series(args: dict[str, Any]) -> dict[str, Any]:
    since = int(time.time()) - int(args["minutes"]) * 60
    c = _db()
    rows = c.execute(
        "SELECT ts, labels, value, text FROM samples WHERE metric=? AND ts>=? ORDER BY ts",
        (args["metric"], since),
    ).fetchall()
    c.close()
    if not rows:
        return {"content": [{"type": "text", "text": "해당 범위에 표본이 없다. 수집기가 더 돌아야 한다."}]}
    lines = [
        f"{time.strftime('%H:%M:%S', time.localtime(ts))} {labels} "
        f"{text if text is not None else value}"
        for ts, labels, value, text in rows[-80:]
    ]
    return {"content": [{"type": "text", "text": f"{len(rows)}개 표본\n" + "\n".join(lines)}]}


CHECK_TYPES = {
    "topic_offset_zero": "오늘자 full 색인 토픽에 produce 가 0건인지. 필드: topic_prefix "
                         "(예 'indexed1_<접두사>-'). 날짜는 평가 시점에 붙는다.",
    "alias_age_days": "Active 클러스터의 alias 가 가리키는 인덱스 이름의 날짜가 "
                      "며칠 이상 지났는지. 필드: alias (coupon|item), max_days (정수).",
    "offset_stalled": "토픽 offset 이 일정 시간 동안 전혀 늘지 않았는지. "
                      "필드: topic (전체 이름), window_min (정수, 분).",
    "metric_threshold": "숫자 지표를 임계값과 비교. 필드: metric, op ('>'|'<'|'=='), "
                        "value (숫자), labels (선택, 예 {'cluster':'<클러스터명>'}). "
                        "쓸 수 있는 metric: index_docs, topic_offset_latest 와 "
                        "policy.json 에 정의된 지표들.",
}
GUARD_TYPES = {
    "after_hour": "지정한 시(0-23) 이전이면 평가를 건너뛴다. 필드: hour.",
    "active_cluster_known": "Active 클러스터를 아직 모르면 건너뛴다. 필드 없음.",
}


@tool(
    "propose_rule",
    "사용자의 자연어 요구를 감시 규칙으로 컴파일해 제안한다. 이 도구는 규칙을 저장하지 "
    "않는다 — 화면에 제안으로 띄울 뿐이고, 사람이 승인해야 적용된다.\n"
    "rule_id 는 영문 snake_case, title 은 한국어 한 줄, severity 는 high|medium|low.\n"
    "check_type 은 다음 중 하나: " + ", ".join(CHECK_TYPES) + "\n"
    + "\n".join(f"  - {k}: {v}" for k, v in CHECK_TYPES.items()) + "\n"
    "check_fields 는 그 check 가 요구하는 필드를 담은 JSON 문자열.\n"
    "guards 는 guard 목록을 담은 JSON 문자열(없으면 '[]'). 쓸 수 있는 guard:\n"
    + "\n".join(f"  - {k}: {v}" for k, v in GUARD_TYPES.items()) + "\n"
    "action 은 발동했을 때 할 일을 담은 JSON 문자열. 없으면 '{}' (알림만).\n"
    "  throttle: {\"type\":\"throttle\",\"uri\":...,\"rate\":0~100,\"ttl_minutes\":1~240}\n"
    "  켤 수 있는 uri 는 셋뿐이다:\n"
    + "\n".join(f"    - {k}: {v}" for k, v in throttling.ALLOWED.items()) + "\n"
    "  아래 uri 는 켜면 틀린 값이 나가거나 500 이 난다. 제안하지 마라:\n"
    + "\n".join(f"    - {k}: {v}" for k, v in throttling.BLOCKED.items()) + "\n"
    "  throttle 을 붙인 규칙도 자동 실행되지 않는다. 화면에 실행 버튼이 뜨고 사람이 누른다.\n"
    "요구가 모호하면 제안하지 말고 무엇이 모호한지 되물어라.",
    {
        "rule_id": str,
        "title": str,
        "severity": str,
        "check_type": str,
        "check_fields": str,
        "guards": str,
        "action": str,
    },
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def propose_rule(args: dict[str, Any]) -> dict[str, Any]:
    if args["check_type"] not in CHECK_TYPES:
        return {"content": [{"type": "text",
                             "text": f"알 수 없는 check_type. 가능한 값: {list(CHECK_TYPES)}"}]}
    try:
        fields = json.loads(args["check_fields"])
        guards = json.loads(args["guards"] or "[]")
    except json.JSONDecodeError as e:
        return {"content": [{"type": "text", "text": f"JSON 파싱 실패: {e}"}]}
    bad = [g.get("type") for g in guards if g.get("type") not in GUARD_TYPES]
    if bad:
        return {"content": [{"type": "text", "text": f"알 수 없는 guard: {bad}"}]}
    try:
        action = json.loads(args.get("action") or "{}")
    except json.JSONDecodeError as e:
        return {"content": [{"type": "text", "text": f"action JSON 파싱 실패: {e}"}]}
    if action.get("type") == "throttle":
        why = throttling.validate(
            action.get("uri", ""), action.get("rate", 100), action.get("ttl_minutes", 0)
        )
        if why:
            return {"content": [{"type": "text", "text": f"이 action 은 쓸 수 없다 — {why}"}]}
    elif action:
        return {"content": [{"type": "text", "text": f"알 수 없는 action type: {action.get('type')}"}]}
    return {"content": [{"type": "text", "text":
        f"규칙 '{args['rule_id']}' 을 제안했다. 화면에 승인 버튼이 떴으니 "
        "사용자가 누르면 적용된다. 저장은 아직 되지 않았다."}]}


VERDICTS = ("execute", "hold", "escalate")


@tool(
    "decide_action",
    "발동한 규칙에 달린 후보 조치를 실행할지 정한다. 이 도구는 실행하지 않는다 — "
    "판단만 돌려주고, 실행과 기록은 서버가 한다.\n"
    "verdict 는 " + " | ".join(VERDICTS) + " 중 하나다.\n"
    "  execute: 사전 확인을 모두 통과했다. 지금 해도 된다\n"
    "  hold: 지금은 하지 않는다 (중복 실행, 상한, 최근 이력 등)\n"
    "  escalate: 이 조치로는 풀리지 않는다. 사람이 봐야 한다\n"
    "reason 은 무엇을 확인해서 그렇게 정했는지 한국어로 적는다. 아침에 볼 유일한 근거이므로 "
    "비워 두면 받지 않는다.\n"
    "쓸 수 있는 action_id: " + ", ".join(catalog.CATALOG),
    {"action_id": str, "verdict": str, "reason": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def decide_action(args: dict[str, Any]) -> dict[str, Any]:
    action = catalog.get(args.get("action_id", ""))
    if action is None:
        return {"content": [{"type": "text", "text":
            f"카탈로그에 없는 조치다: {args.get('action_id')!r}. "
            f"쓸 수 있는 값: {list(catalog.CATALOG)}"}]}
    verdict = args.get("verdict", "")
    if verdict not in VERDICTS:
        return {"content": [{"type": "text", "text":
            f"알 수 없는 verdict: {verdict!r}. 가능한 값: {list(VERDICTS)}"}]}
    if not (args.get("reason") or "").strip():
        return {"content": [{"type": "text", "text": "사유(reason)를 비워 둘 수 없다"}]}
    return {"content": [{"type": "text", "text":
        f"{action.id} 에 대해 {verdict} 로 판단했다. 실행과 기록은 서버가 한다."}]}


ops = create_sdk_mcp_server(
    name="ops",
    version="2.0.0",
    tools=[monitor_status, monitor_series, prom_query, admin_get, propose_rule,
           decide_action],
)

# 에이전트를 내 개인 환경에서 격리한다. 이걸 빼면 ~/.claude 의 규칙·스킬을
# 그대로 물려받아, 사람용으로 쓴 규칙 때문에 조회를 스스로 거부한다.
OPTIONS = ClaudeAgentOptions(
    model="claude-opus-5-5",
    mcp_servers={"ops": ops},
    allowed_tools=[
        "mcp__ops__monitor_status",
        "mcp__ops__monitor_series",
        "mcp__ops__prom_query",
        "mcp__ops__admin_get",
        "mcp__ops__propose_rule",
        "mcp__ops__decide_action",
    ],
    tools=[],                    # 내장 도구 전부 끔 (Skill, ToolSearch 포함)
    setting_sources=[],          # ~/.claude 설정·CLAUDE.md 를 읽지 않음
    skills=[],                   # 스킬 전부 끔 (None 은 끄는 게 아니다)
    permission_mode="dontAsk",   # 승인이 필요한 호출은 묻지 않고 거부
    max_budget_usd=1.0,          # 체험용 상한
    system_prompt=(
        "너는 색인 파이프라인의 모니터링 담당이다.\n"
        "발동 판단은 규칙 평가기가 이미 끝냈다. 너는 그 판정을 다시 내리지 않는다.\n"
        "너의 일은 발동한 것을 설명하고, 맥락을 확인하고, 다음 수를 제안하는 것이다.\n"
        "\n"
        "지켜야 할 것:\n"
        "- 주어진 읽기 전용 도구로만 사실을 확인한다. 추측으로 수치를 만들지 않는다.\n"
        "- 확인하지 못한 것은 '미확인'이라고 분명히 말한다.\n"
        f"- 운영 상식: {policy.get('notes.operating', '(없음)')}\n"
        "- 조치를 제안할 때는 실행할 명령 하나와 되돌리는 법을 같이 적는다. "
        "운영에 영향을 주는 조치는 네가 실행하지 않는다.\n"
        "답변은 한국어로 한다."
    ),
)

PROMPT = """monitor_status 로 현재 상태를 먼저 확인해라.

발동(firing) 중인 규칙이 있으면 각각에 대해 다음을 정리해라.
1. 무엇이 관측됐나 — 값과 시각
2. 왜 문제인가, 또는 왜 문제가 아닐 수 있나
3. 다음에 무엇을 확인해야 하나

필요하면 monitor_series 로 추이를 보거나 prom_query / admin_get 으로 직접 확인해라.
발동한 규칙이 없으면 그렇게만 말하고, 최신 관측값을 표로 요약해라."""


async def main() -> None:
    async for message in query(prompt=PROMPT, options=OPTIONS):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print(block.text)
                elif hasattr(block, "name"):
                    print(f"  [도구] {block.name}")
        elif isinstance(message, ResultMessage):
            print(f"\n--- 종료: {message.subtype} ---")


if __name__ == "__main__":
    asyncio.run(main())
