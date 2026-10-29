import executors


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = f"status {status_code}"


class FakeClient:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.responses.pop(0) if self.responses else 200)


async def test_disabled_does_not_call_http():
    client = FakeClient()
    r = await executors.execute("trigger_coupon_full", {"JOB_ID": "20261030"},
                                enabled=False, client=client)
    assert r["outcome"] == "disabled"
    assert client.calls == []


async def test_dry_run_first_then_real():
    client = FakeClient(responses=[200, 200])
    r = await executors.execute("trigger_coupon_full", {"JOB_ID": "20261030"},
                                enabled=True, client=client)
    assert [c["json"]["conf"]["dryRun"] for c in client.calls] == [True, False]
    assert r["outcome"] == "sent"


async def test_dry_run_failure_stops_before_real_run():
    client = FakeClient(responses=[500])
    r = await executors.execute("trigger_coupon_full", {"JOB_ID": "20261030"},
                                enabled=True, client=client)
    assert len(client.calls) == 1
    assert r["outcome"] == "dry_only"


async def test_caller_cannot_override_fixed_params():
    client = FakeClient(responses=[200, 200])
    await executors.execute("trigger_coupon_full", {"item": True, "env": "dev"},
                            enabled=True, client=client)
    conf = client.calls[-1]["json"]["conf"]
    assert conf["item"] is False and conf["env"] == "prod"


async def test_unknown_action_is_refused():
    r = await executors.execute("drop_index", {}, enabled=True, client=FakeClient())
    assert r["outcome"] == "blocked"


async def test_pod_not_in_whitelist_is_blocked():
    r = await executors.execute("restart_indexer_pod", {"name": "some-other-pod"},
                                enabled=True, client=FakeClient())
    assert r["outcome"] == "blocked"
    assert "화이트리스트" in r["detail"]


async def test_pod_restart_disabled_records_command_only(monkeypatch):
    import catalog
    monkeypatch.setitem(catalog.POD_ALLOWED, "indexer-incr", "증분 색인")
    r = await executors.execute("restart_indexer_pod", {"name": "indexer-incr"},
                                enabled=False, client=FakeClient())
    assert r["outcome"] == "disabled"
    assert "rollout restart" in r["detail"]
