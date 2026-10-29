"""기본 규칙. 꺼진 채로 들어간다 — 임계값을 정해야 켤 수 있다."""

from . import config
from .store import Store


def _rules() -> list[tuple[str, str, str, dict]]:
    out: list[tuple[str, str, str, dict]] = []
    for alias in config.ALIASES:
        out.append((
            f"{alias}_price_stale", "high",
            f"Active 클러스터의 {alias} alias 가 오래됐다",
            {
                "check": {"type": "alias_age_days", "alias": alias, "max_days": None},
                "guard": [{"type": "active_cluster_known"}],
            },
        ))
        if f"{alias}-full" in config.FULL_TOPIC_PREFIXES:
            out.append((
                f"{alias}_full_missing", "high",
                f"{alias} full 색인이 오늘 돌지 않았다",
                {
                    "check": {
                        "type": "topic_offset_zero",
                        "topic_prefix": f"indexed{config.TOPIC_VERSION}_{alias}-full-",
                    },
                },
            ))
        for topic in config.STATIC_TOPICS:
            if f"{alias}-incr" in topic:
                out.append((
                    f"{alias}_incr_stalled", "medium",
                    f"{alias} 증분 토픽이 멈췄다",
                    {"check": {"type": "offset_stalled", "topic": topic, "window_min": 30}},
                ))
    return out


def seed(store: Store) -> int:
    added = 0
    for rule_id, sev, title, spec in _rules():
        if store.put_rule_if_absent(rule_id, sev, title, spec, enabled=False):
            added += 1
    return added
