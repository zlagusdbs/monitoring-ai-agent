"""기본 규칙. 에이전트가 자연어로 만든 규칙도 같은 테이블에 들어간다."""

import policy

from . import config
from .store import Store

DEFAULTS = [
    (
        "coupon_full_not_indexed_today", "high",
        "쿠폰 full 색인이 오늘 돌지 않았다",
        {
            "check": {"type": "topic_offset_zero",
                      "topic_prefix": f"indexed{config.TOPIC_VERSION}_"
                                      f"{(config.FULL_TOPIC_PREFIXES or [''])[0]}-"},
            # 운영 DAG 는 03:00 에 돈다. 그 전에는 0건이 정상이다.
            "guard": [{"type": "after_hour", "hour": 6}],
        },
    ),
    (
        "coupon_alias_stale", "medium",
        "Active 클러스터의 coupon alias 가 오래됐다",
        {
            "check": {"type": "alias_age_days",
                      "alias": (config.ALIASES or [""])[0], "max_days": 3},
            # standby 는 전환 시에만 갱신되므로 Active 만 본다.
            "guard": [{"type": "active_cluster_known"}],
        },
    ),
    (
        "coupon_incr_stalled", "medium",
        "쿠폰 증분 토픽이 멈췄다",
        {
            "check": {
                "type": "offset_stalled",
                "topic": (config.STATIC_TOPICS or [""])[0],
                "window_min": 30,
            },
        },
    ),
]


def seed(store: Store) -> int:
    for rule_id, sev, title, spec in DEFAULTS:
        store.put_rule(rule_id, sev, title, spec)
    return len(DEFAULTS)
