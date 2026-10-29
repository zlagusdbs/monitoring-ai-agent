"""레포 밖에 두는 설정을 읽는다. 파일이 없으면 빈 설정으로 동작한다."""

import json
import os
from pathlib import Path
from typing import Any

PATH = Path(os.getenv("MON_POLICY", Path(__file__).parent / "policy.json"))

_cache: dict[str, Any] | None = None


def load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def get(key: str, default: Any = None) -> Any:
    cur: Any = load()
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def configured() -> bool:
    return bool(load())
