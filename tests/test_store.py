import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.store import Store


def test_put_action_and_read_back(tmp_path):
    s = Store(tmp_path / "t.db")
    s.put_action("r1", "trigger_coupon_full", "execute", "증분 정상",
                 params={"coupon": True}, outcome="sent", ts=1000)
    rows = s.actions_since(0)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "execute"
    assert rows[0]["params"] == {"coupon": True}


def test_count_actions_filters_by_outcome_and_window(tmp_path):
    s = Store(tmp_path / "t.db")
    s.put_action("r1", "a", "execute", "", outcome="sent", ts=1000)
    s.put_action("r1", "a", "execute", "", outcome="disabled", ts=1100)
    s.put_action("r1", "a", "execute", "", outcome="sent", ts=500)
    assert s.count_actions("a", since=900) == 1


def test_concurrent_writers_do_not_lose_an_action(tmp_path):
    db = tmp_path / "t.db"
    a, b = Store(db), Store(db)
    a.put_action("r1", "x", "hold", "a", ts=1000)
    b.put_action("r2", "x", "hold", "b", ts=1001)
    a.checkpoint()
    assert len(Store(db).actions_since(0)) == 2


def test_setting_roundtrip_and_default(tmp_path):
    s = Store(tmp_path / "t.db")
    assert s.get_setting("auto_check", "off") == "off"
    s.set_setting("auto_check", "on")
    assert s.get_setting("auto_check") == "on"
