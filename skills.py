"""에이전트에게 덧붙일 지시문 조각(md).

구역은 두 개다.
  rules  — 늘 지킬 것 (말투, 금지, 보고 형식)
  skills — 무엇을 어떻게 보는지 (조사 순서, 런북)

사람이 화면에서 쓰고, 에이전트는 읽기만 한다. 도구를 늘리지는 못한다 —
무엇을 조사하고 어떻게 말할지만 바뀐다.
"""

import os
import re
from pathlib import Path

DIR = Path(os.getenv("MON_SKILLS_DIR", Path(__file__).parent / "skills"))

GROUPS = ("rules", "skills")

HEAD = {
    "rules": "규칙 — 늘 지킨다",
    "skills": "스킬 — 무엇을 어떻게 보는지",
}

# 디렉터리 밖으로 나가지 못하게 이름을 아예 제한한다.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

MAX_BYTES = 64 * 1024


def _dir(group: str) -> Path | None:
    return DIR / group if group in GROUPS else None


def _path(group: str, name: str) -> Path | None:
    base = _dir(group)
    if base is None or not NAME.match(name):
        return None
    return base / f"{name}.md"


def names(group: str) -> list[str]:
    base = _dir(group)
    if base is None or not base.is_dir():
        return []
    return sorted(p.stem for p in base.glob("*.md") if NAME.match(p.stem))


def listing() -> dict[str, list[str]]:
    return {g: names(g) for g in GROUPS}


def read(group: str, name: str) -> str | None:
    path = _path(group, name)
    if path is None or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def write(group: str, name: str, text: str) -> str | None:
    """저장하고 None 을 돌려준다. 못 하면 사유를 돌려준다."""
    path = _path(group, name)
    if path is None:
        if group not in GROUPS:
            return f"없는 구역: {group}"
        return "이름은 영소문자·숫자·하이픈만, 40자 이내"
    if len(text.encode("utf-8")) > MAX_BYTES:
        return f"{MAX_BYTES // 1024}KB 를 넘는다"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return None


def delete(group: str, name: str) -> bool:
    path = _path(group, name)
    if path is None or not path.is_file():
        return False
    path.unlink()
    return True


def as_prompt() -> str:
    """시스템 프롬프트 뒤에 덧붙일 글. 없으면 빈 문자열."""
    blocks = []
    for group in GROUPS:
        parts = []
        for name in names(group):
            body = (read(group, name) or "").strip()
            if body:
                parts.append(f"### {name}\n{body}")
        if parts:
            blocks.append(f"## {HEAD[group]}\n\n" + "\n\n".join(parts))
    if not blocks:
        return ""
    return (
        "\n\n# 추가 지시\n"
        "아래는 사람이 화면에서 적어 둔 것이다. 도구와 권한은 바뀌지 않는다.\n\n"
        + "\n\n".join(blocks)
    )
