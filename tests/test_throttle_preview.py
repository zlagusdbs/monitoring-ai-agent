import agent
import throttling


def text_of(result):
    return result["content"][0]["text"]


async def test_blocked_uri_is_refused_with_a_reason():
    uri = next(iter(throttling.BLOCKED), None)
    if uri is None:
        return
    r = await agent.throttle_preview.handler({"uri": uri, "rate": 50, "ttl_minutes": 10})
    assert "쓸 수 없다" in text_of(r)


async def test_unknown_uri_is_refused():
    r = await agent.throttle_preview.handler({"uri": "NOPE", "rate": 50, "ttl_minutes": 10})
    assert "쓸 수 없다" in text_of(r)


async def test_rate_out_of_range_is_refused():
    uri = next(iter(throttling.ALLOWED), None)
    if uri is None:
        return
    r = await agent.throttle_preview.handler({"uri": uri, "rate": 150, "ttl_minutes": 10})
    assert "쓸 수 없다" in text_of(r)


async def test_allowed_uri_gets_command_and_revert():
    uri = next(iter(throttling.ALLOWED), None)
    if uri is None:
        return
    r = await agent.throttle_preview.handler({"uri": uri, "rate": 30, "ttl_minutes": 30})
    out = text_of(r)
    assert "거는 명령" in out and "되돌리는 명령" in out
    assert "curl" in out and uri in out
    assert "30분이 지나면" in out


async def test_metric_list_comes_from_policy():
    assert "index_docs" in agent.METRICS
    assert agent.CHECK_TYPES["metric_threshold"].endswith(".")
    for name in agent.METRICS:
        assert name in agent.CHECK_TYPES["metric_threshold"]
