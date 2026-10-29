import agent


def text_of(result):
    return result["content"][0]["text"]


async def test_decide_action_rejects_unknown_verdict():
    r = await agent.decide_action.handler(
        {"action_id": "trigger_coupon_full", "verdict": "run", "reason": "x"})
    assert "verdict" in text_of(r)


async def test_decide_action_rejects_unknown_action():
    r = await agent.decide_action.handler(
        {"action_id": "drop_index", "verdict": "execute", "reason": "x"})
    assert "카탈로그" in text_of(r)


async def test_decide_action_requires_reason():
    r = await agent.decide_action.handler(
        {"action_id": "trigger_coupon_full", "verdict": "execute", "reason": "  "})
    assert "사유" in text_of(r)


async def test_decide_action_accepts_valid_input():
    r = await agent.decide_action.handler(
        {"action_id": "trigger_coupon_full", "verdict": "hold",
         "reason": "40분 전 재기동 이력이 있다"})
    assert "hold" in text_of(r)


async def test_decide_action_is_registered():
    assert "mcp__ops__decide_action" in agent.OPTIONS.allowed_tools
