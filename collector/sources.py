"""admin-api 에서 Prometheus 에 없는 값을 긁어 온다. 전부 읽기 전용 GET 이다."""

import datetime as dt
from typing import Any

import httpx

import policy

ADMIN = policy.get("endpoints.admin", "")
PREFIX = policy.get("admin_paths.prefix", "")
ES = f"{ADMIN}{PREFIX}"


async def _get(client: httpx.AsyncClient, path: str) -> Any | None:
    """실패를 예외로 올리지 않는다. 수집기는 한 항목이 죽어도 계속 돌아야 한다."""
    if not ADMIN:
        return None
    try:
        r = await client.get(f"{ADMIN}{path}")
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or not r.text.strip():
        return None
    try:
        return r.json()
    except ValueError:
        return None


async def clusters(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """[{metric, labels, value, text}] 형태로 돌려준다."""
    data = await _get(client, f"{PREFIX}/cluster")
    if not isinstance(data, list):
        return []
    out = []
    for c in data:
        name, status = c.get("name"), c.get("status")
        if not name:
            continue
        out.append(
            {
                "metric": "cluster_status",
                "labels": {"cluster": name},
                "value": float(c.get("weight") or 0),
                "text": status,
            }
        )
    return out


async def aliases(client: httpx.AsyncClient, clusters_: list[str], names: list[str]):
    out = []
    for cl in clusters_:
        for alias in names:
            data = await _get(client, f"{PREFIX}/{cl}/alias/{alias}")
            idx = (data or {}).get("index")
            if idx:
                out.append(
                    {
                        "metric": "alias_index",
                        "labels": {"cluster": cl, "alias": alias},
                        "value": None,
                        "text": idx,
                    }
                )
    return out


async def index_docs(client: httpx.AsyncClient, pairs: list[tuple[str, str]]):
    """pairs: [(cluster, index)] — alias 가 가리키는 인덱스의 문서 수."""
    out = []
    for cl, idx in pairs:
        data = await _get(client, f"{PREFIX}/{cl}/index/{idx}")
        if isinstance(data, dict) and "count" in data:
            out.append(
                {
                    "metric": "index_docs",
                    "labels": {"cluster": cl, "index": idx},
                    "value": float(data["count"]),
                    "text": None,
                }
            )
    return out


def today_topics(prefixes: list[str], version: str = "1") -> list[str]:
    """full 색인 토픽 이름은 날짜를 포함한다: indexed{version}_{접두사}-YYYYMMDD"""
    day = dt.datetime.now().strftime("%Y%m%d")
    return [f"indexed{version}_{p}-{day}" for p in prefixes]


async def topic_offsets(client: httpx.AsyncClient, topics: list[str]):
    out = []
    for t in topics:
        data = await _get(client, f"/kafka/topic/{t}")
        parts = (data or {}).get("partitions")
        if not parts:
            continue
        out.append(
            {
                "metric": "topic_offset_latest",
                "labels": {"topic": t},
                "value": float(sum(p.get("offsetLatest") or 0 for p in parts)),
                "text": None,
            }
        )
    return out


# --- Prometheus -----------------------------------------------------------

PROM = policy.get("endpoints.prometheus", "")

# 클러스터 단위로 하나의 값만 남긴다. 노드 48개를 다 쌓으면 화면에 못 쓴다.
PROM_QUERIES = policy.get("prometheus_queries", {})


async def prometheus(client: httpx.AsyncClient):
    if not PROM:
        return []
    out = []
    for metric, promql in PROM_QUERIES.items():
        try:
            r = await client.get(f"{PROM}/api/v1/query", params={"query": promql})
            res = r.json()["data"]["result"]
        except (httpx.HTTPError, ValueError, KeyError):
            continue
        for item in res:
            cluster = item["metric"].get("cluster")
            if not cluster:
                continue
            out.append(
                {
                    "metric": metric,
                    "labels": {"cluster": cluster},
                    "value": float(item["value"][1]),
                    "text": None,
                }
            )
    return out


# --- Datadog --------------------------------------------------------------
# 키가 없으면 조용히 건너뛴다. 대시보드에는 "미연결"로 보인다.

import os  # noqa: E402

DD_SITE = os.getenv("DD_SITE", "datadoghq.com")
DD_API_KEY = os.getenv("DD_API_KEY", "")
DD_APP_KEY = os.getenv("DD_APP_KEY", "")

DD_QUERIES = policy.get("datadog_queries", {})


async def datadog(client: httpx.AsyncClient):
    if not (DD_API_KEY and DD_APP_KEY):
        return []
    now = int(__import__("time").time())
    headers = {"DD-API-KEY": DD_API_KEY, "DD-APPLICATION-KEY": DD_APP_KEY}
    out = []
    for metric, q in DD_QUERIES.items():
        try:
            r = await client.get(
                f"https://api.{DD_SITE}/api/v1/query",
                params={"from": now - 300, "to": now, "query": q},
                headers=headers,
            )
            series = r.json().get("series") or []
        except (httpx.HTTPError, ValueError):
            continue
        for s in series:
            pts = [p for p in (s.get("pointlist") or []) if p[1] is not None]
            if not pts:
                continue
            out.append(
                {
                    "metric": metric,
                    "labels": {"scope": s.get("scope", "all")},
                    "value": float(pts[-1][1]),
                    "text": None,
                }
            )
    return out
