def test_put_action_and_read_back(store):
    store.put_action("r1", "trigger_coupon_full", "execute", "증분 정상",
                     params={"coupon": True}, outcome="sent", ts=1000)
    rows = store.actions_since(0)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "execute"
    assert rows[0]["params"] == {"coupon": True}


def test_count_actions_filters_by_outcome_and_window(store):
    store.put_action("r1", "a", "execute", "", outcome="sent", ts=1000)
    store.put_action("r1", "a", "execute", "", outcome="disabled", ts=1100)
    store.put_action("r1", "a", "execute", "", outcome="sent", ts=500)
    assert store.count_actions("a", since=900) == 1


def test_concurrent_writers_do_not_lose_an_action(store, store2):
    store.put_action("r1", "x", "hold", "a", ts=1000)
    store2.put_action("r2", "x", "hold", "b", ts=1001)
    assert len(store.actions_since(0)) == 2


def test_setting_roundtrip_and_default(store):
    assert store.get_setting("auto_check", "off") == "off"
    store.set_setting("auto_check", "on")
    assert store.get_setting("auto_check") == "on"


def test_latest_returns_one_row_per_label_set(store):
    store.put("m", {"c": "a"}, 1.0, ts=100)
    store.put("m", {"c": "a"}, 2.0, ts=200)
    store.put("m", {"c": "b"}, 3.0, ts=150)
    latest = {r["labels"]["c"]: r["value"] for r in store.latest("m")}
    assert latest == {"a": 2.0, "b": 3.0}


def test_series_filters_by_label_set(store):
    store.put("m", {"c": "a"}, 1.0, ts=100)
    store.put("m", {"c": "b"}, 9.0, ts=110)
    store.put("m", {"c": "a"}, 4.0, ts=120)
    assert store.series("m", {"c": "a"}, 0) == [(100, 1.0), (120, 4.0)]
