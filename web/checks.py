"""체크리스트. 채팅에 `/check <이름> <무엇을 확인할지>` 로 항목을 만든다."""

import re

COMMAND = re.compile(r"^/check\s+(?P<name>\S+)\s*(?P<question>.*)$", re.DOTALL)

DEFAULT_QUESTION = "상태 확인"

# 에이전트가 판정과 한 줄 요약을 같이 내도록 형식을 고정한다.
VERDICTS = {"OK": "ok", "FAIL": "fail", "UNKNOWN": "unknown"}

ANSWER = re.compile(r"^\s*\**\s*(OK|FAIL|UNKNOWN)\s*\**\s*\|\s*(?P<summary>.+)", re.IGNORECASE)

PROMPT = (
    "체크리스트 항목 '{name}' 을 확인해라.\n"
    "확인할 것: {question}\n\n"
    "읽기 전용 도구로 사실을 확인한 뒤, 아래 형식으로 **한 줄만** 답해라.\n"
    "다른 말은 쓰지 마라.\n\n"
    "    <판정> | <요약>\n\n"
    "판정은 셋 중 하나다.\n"
    "  OK      — 정상이다\n"
    "  FAIL    — 이상이다. 사람이 봐야 한다\n"
    "  UNKNOWN — 확인하지 못했다\n\n"
    "요약은 100자 이내로, 근거가 되는 숫자와 시각을 넣는다. 추측하지 않는다.\n"
    "예: FAIL | 3일 연속 produce 0건, alias coupon-20261012 (17일 전)"
)


def parse_command(text: str) -> tuple[str, str] | None:
    """`/check 이름 질문` 을 (이름, 질문) 으로 나눈다. 아니면 None."""
    m = COMMAND.match(text.strip())
    if not m:
        return None
    name = m.group("name")
    question = m.group("question").strip() or DEFAULT_QUESTION
    return name, question


HANGUL_TAIL = re.compile(r"[가-힣]+$")


def resolve_name(typed: str, existing: list[str]) -> str:
    """`indexer-coupon-all은` 처럼 조사가 붙어 와도 같은 항목으로 본다."""
    if typed in existing:
        return typed
    for name in existing:
        rest = typed[len(name):]
        if typed.startswith(name) and rest and HANGUL_TAIL.fullmatch(rest):
            return name
    # 영문·숫자 뒤에 한글이 붙었으면 그 한글은 조사로 본다.
    stripped = HANGUL_TAIL.sub("", typed)
    if stripped and stripped != typed and re.search(r"[^가-힣]", stripped):
        return stripped
    return typed


def parse_answer(text: str) -> tuple[str, str]:
    """에이전트의 답에서 판정과 요약을 뽑는다. 형식을 안 지키면 unknown."""
    for line in (text or "").strip().splitlines():
        m = ANSWER.match(line)
        if m:
            return VERDICTS[m.group(1).upper()], m.group("summary").strip()
    first = next((l.strip() for l in (text or "").splitlines() if l.strip()), "")
    return "unknown", first[:200] or "에이전트가 답하지 않았다"


def prompt_for(name: str, question: str) -> str:
    return PROMPT.format(name=name, question=question)
