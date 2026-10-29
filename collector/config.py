"""수집 대상. 환경변수로 덮어쓸 수 있게 두되 기본값은 여기서 읽는다."""

import os

import policy

CLUSTERS = [c for c in os.getenv("MON_CLUSTERS", "").split(",") if c] \
    or policy.get("targets.clusters", [])
ALIASES = [a for a in os.getenv("MON_ALIASES", "").split(",") if a] \
    or policy.get("targets.aliases", [])

# full 색인 토픽 접두사. 날짜는 수집 시점에 붙인다.
FULL_TOPIC_PREFIXES = policy.get("targets.full_topic_prefixes", [])

# 이름이 고정된 증분 토픽.
STATIC_TOPICS = policy.get("targets.static_topics", [])
TOPIC_VERSION = policy.get("targets.topic_version", "1")

INTERVAL_SEC = int(os.getenv("MON_INTERVAL_SEC", "300"))
DSN = os.getenv("MON_DSN", "postgresql://monitor:monitor@postgres:5432/monitor")
