from collector import sources


def test_scope_labels_splits_tags():
    got = sources.scope_labels("resource_name:POST /a/b,service:svc")
    assert got == {"resource_name": "POST /a/b", "service": "svc"}


def test_scope_labels_ignores_wildcard_scope():
    assert sources.scope_labels("*") == {}


def test_scope_labels_keeps_value_with_colon():
    got = sources.scope_labels("resource_name:GET http://x:8080/a")
    assert got == {"resource_name": "GET http://x:8080/a"}


def test_scale_converts_seconds_to_ms(monkeypatch):
    monkeypatch.setattr(sources, "DD_SCALE", {"api_latency_p99_ms": 1000})
    assert sources.scaled("api_latency_p99_ms", 0.0663) == 66.3


def test_scale_leaves_other_metrics_alone(monkeypatch):
    monkeypatch.setattr(sources, "DD_SCALE", {"api_latency_p99_ms": 1000})
    assert sources.scaled("endpoint_rps", 761.2) == 761.2
