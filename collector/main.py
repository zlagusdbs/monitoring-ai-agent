"""수집 루프. LLM 을 쓰지 않는다 — 한도와 무관하게 계속 돈다."""

import asyncio
import logging
import time

import httpx
import net

from . import config, sources
from .evaluator import evaluate
from .seed_rules import seed
from .store import Store

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger("collector")


async def collect_once(client: httpx.AsyncClient, store: Store) -> int:
    ts = int(time.time())
    rows: list[dict] = []

    rows += await sources.clusters(client)
    alias_rows = await sources.aliases(client, config.CLUSTERS, config.ALIASES)
    rows += alias_rows

    # alias 가 가리키는 인덱스만 문서 수를 센다. 전수 조회는 하지 않는다.
    pairs = [(r["labels"]["cluster"], r["text"]) for r in alias_rows]
    rows += await sources.index_docs(client, pairs)

    topics = sources.today_topics(config.FULL_TOPIC_PREFIXES) + config.STATIC_TOPICS
    rows += await sources.topic_offsets(client, topics)

    # CPU·메모리·검색량은 Prometheus 가 이미 갖고 있다. 복사하지 않고 현재값만 찍는다.
    rows += await sources.prometheus(client)

    # Datadog 은 키가 있을 때만. 없으면 빈 목록이 온다.
    rows += await sources.datadog(client)

    for r in rows:
        store.put(r["metric"], r["labels"], r["value"], r["text"], ts=ts)
    return len(rows)


async def main() -> None:
    store = Store(config.DSN)
    n_rules = seed(store)
    log.info("수집기 시작 — 주기 %ds, 기본 규칙 %d개", config.INTERVAL_SEC, n_rules)
    async with net.async_client(timeout=30) as client:
        while True:
            started = time.monotonic()
            try:
                n = await collect_once(client, store)
                results = evaluate(store)
                firing = [r for r in results if r["state"] == "firing"]
                log.info("수집 %d건 (총 %d행) · 규칙 %d개 평가, 발동 %d건",
                         n, store.count(), len(results), len(firing))
                for r in firing:
                    log.warning("[%s] %s — %s", r["severity"].upper(), r["title"], r["detail"])
            except Exception:
                log.exception("수집 중 오류 — 다음 주기에 다시 시도한다")
            await asyncio.sleep(max(0, config.INTERVAL_SEC - (time.monotonic() - started)))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("종료")
