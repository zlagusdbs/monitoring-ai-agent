"""카탈로그 조치의 실제 실행. 꺼져 있으면 보낼 내용만 돌려준다."""

import os
from typing import Any

import catalog
import policy

AIRFLOW = policy.get("actions.airflow", "")
TRIGGER_PATH = policy.get("actions.trigger_path", "/api/v2/dags/{dag_id}/dagRuns")
NAMESPACE = policy.get("actions.namespace", "")
TOKEN = os.getenv("MON_AIRFLOW_TOKEN", "")


def _result(outcome: str, detail: str, revert: str | None = None) -> dict[str, Any]:
    return {"outcome": outcome, "detail": detail, "revert": revert}


def _trigger_url() -> str:
    return f"{AIRFLOW}{TRIGGER_PATH.format(dag_id=catalog.DAG_ID)}"


def _trigger_body(params: dict, dry_run: bool) -> dict:
    conf = dict(params)
    conf.update(catalog.fixed_params("trigger_coupon_full"))
    conf["dryRun"] = dry_run
    return {"conf": conf}


def _restart_command(name: str) -> str:
    return f"oc rollout restart deployment/{name} -n {NAMESPACE}"


async def _trigger(params: dict, *, enabled: bool, client) -> dict[str, Any]:
    if not (AIRFLOW and catalog.DAG_ID):
        return _result("blocked", "트리거 대상이 설정되지 않았다 — policy.json 의 actions 를 채워야 한다")
    body = _trigger_body(params, dry_run=False)
    if not enabled:
        return _result("disabled", f"POST {_trigger_url()} {body}")

    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    try:
        dry = await client.post(_trigger_url(), json=_trigger_body(params, True), headers=headers)
    except Exception as e:
        return _result("failed", f"dryRun 실패 — {type(e).__name__}: {e}")
    if not 200 <= dry.status_code < 300:
        return _result("dry_only", f"dryRun 이 HTTP {dry.status_code} — 본 실행하지 않음")

    try:
        run = await client.post(_trigger_url(), json=body, headers=headers)
    except Exception as e:
        return _result("failed", f"본 실행 실패 — {type(e).__name__}: {e}")
    if not 200 <= run.status_code < 300:
        return _result("failed", f"본 실행이 HTTP {run.status_code}: {run.text[:300]}")
    return _result("sent", f"HTTP {run.status_code} {run.text[:300]}")


async def _restart_pod(params: dict, *, enabled: bool, client) -> dict[str, Any]:
    name = params.get("name", "")
    if name not in catalog.POD_ALLOWED:
        return _result("blocked", f"{name or '(이름 없음)'} 은 화이트리스트에 없다")
    command = _restart_command(name)
    if not enabled:
        return _result("disabled", command)
    import asyncio
    try:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await proc.communicate()
    except Exception as e:
        return _result("failed", f"{type(e).__name__}: {e}")
    text = out.decode(errors="replace")[:300]
    if proc.returncode != 0:
        return _result("failed", f"exit {proc.returncode}: {text}")
    return _result("sent", text)


HANDLERS = {
    "trigger_coupon_full": _trigger,
    "restart_indexer_pod": _restart_pod,
}


async def execute(action_id: str, params: dict, *, enabled: bool, client) -> dict[str, Any]:
    if catalog.get(action_id) is None or action_id not in HANDLERS:
        return _result("blocked", f"카탈로그에 없는 조치: {action_id}")
    return await HANDLERS[action_id](params, enabled=enabled, client=client)
