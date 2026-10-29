import time
from datetime import datetime
from zoneinfo import ZoneInfo

import catalog

KST = ZoneInfo("Asia/Seoul")


def test_unknown_action_is_not_in_catalog():
    assert catalog.get("drop_index") is None


def test_fixed_params_pin_item_false():
    p = catalog.fixed_params("trigger_coupon_full", datetime(2026, 10, 30, 3, 0))
    assert p["item"] is False and p["coupon"] is True and p["env"] == "prod"
    assert p["JOB_ID"] == "20261030"


def test_daily_limit_blocks_second_trigger(store):
    now = int(datetime(2026, 10, 30, 23, 0, tzinfo=KST).timestamp())
    store.put_action("r", "trigger_coupon_full", "execute", "", outcome="sent", ts=now - 3600)
    assert catalog.check_limits(store, "trigger_coupon_full", now) is not None


def test_yesterdays_run_does_not_block_today(store):
    store.put_action("r", "trigger_coupon_full", "execute", "", outcome="sent",
                 ts=int(datetime(2026, 10, 29, 23, 30, tzinfo=KST).timestamp()))
    now = int(datetime(2026, 10, 30, 0, 30, tzinfo=KST).timestamp())
    assert catalog.check_limits(store, "trigger_coupon_full", now) is None


def test_hourly_limit_blocks_pod_restart(store):
    now = int(time.time())
    store.put_action("r", "restart_indexer_pod", "execute", "", outcome="sent", ts=now - 600)
    assert catalog.check_limits(store, "restart_indexer_pod", now) is not None


def test_unknown_action_has_no_limit_answer(store):
    assert "카탈로그" in catalog.check_limits(store, "drop_index", int(time.time()))
