import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import catalog
from collector.store import Store

KST = ZoneInfo("Asia/Seoul")


def test_unknown_action_is_not_in_catalog():
    assert catalog.get("drop_index") is None


def test_fixed_params_pin_item_false():
    p = catalog.fixed_params("trigger_coupon_full", datetime(2026, 10, 30, 3, 0))
    assert p["item"] is False and p["coupon"] is True and p["env"] == "prod"
    assert p["JOB_ID"] == "20261030"


def test_daily_limit_blocks_second_trigger(tmp_path):
    s = Store(tmp_path / "t.db")
    now = int(datetime(2026, 10, 30, 23, 0, tzinfo=KST).timestamp())
    s.put_action("r", "trigger_coupon_full", "execute", "", outcome="sent", ts=now - 3600)
    assert catalog.check_limits(s, "trigger_coupon_full", now) is not None


def test_yesterdays_run_does_not_block_today(tmp_path):
    s = Store(tmp_path / "t.db")
    s.put_action("r", "trigger_coupon_full", "execute", "", outcome="sent",
                 ts=int(datetime(2026, 10, 29, 23, 30, tzinfo=KST).timestamp()))
    now = int(datetime(2026, 10, 30, 0, 30, tzinfo=KST).timestamp())
    assert catalog.check_limits(s, "trigger_coupon_full", now) is None


def test_hourly_limit_blocks_pod_restart(tmp_path):
    s = Store(tmp_path / "t.db")
    now = int(time.time())
    s.put_action("r", "restart_indexer_pod", "execute", "", outcome="sent", ts=now - 600)
    assert catalog.check_limits(s, "restart_indexer_pod", now) is not None


def test_unknown_action_has_no_limit_answer(tmp_path):
    s = Store(tmp_path / "t.db")
    assert "카탈로그" in catalog.check_limits(s, "drop_index", int(time.time()))
