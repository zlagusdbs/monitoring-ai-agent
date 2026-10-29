"""체크리스트. 채팅에 `/check <이름> <무엇을 확인할지>` 로 항목을 만든다."""

import re

COMMAND = re.compile(r"^/check\s+(?P<name>\S+)\s*(?P<question>.*)$", re.DOTALL)

DEFAULT_QUESTION = "상태 확인"

PROMPT = (
    "체크리스트 항목 '{name}' 을 확인해라.\n"
    "확인할 것: {question}\n\n"
    "읽기 전용 도구로 사실만 확인하고, 두 줄 안쪽으로 답해라.\n"
    "- 언제 마지막으로 돌았는지(시각)와 지금 상태를 함께 적는다.\n"
    "- 확인하지 못한 것은 '미확인'이라고 분명히 말한다.\n"
    "- 숫자는 근거가 되는 값을 그대로 적는다. 추측하지 않는다."
)


def parse_command(text: str) -> tuple[str, str] | None:
    """`/check 이름 질문` 을 (이름, 질문) 으로 나눈다. 아니면 None."""
    m = COMMAND.match(text.strip())
    if not m:
        return None
    name = m.group("name")
    question = m.group("question").strip() or DEFAULT_QUESTION
    return name, question


def prompt_for(name: str, question: str) -> str:
    return PROMPT.format(name=name, question=question)
