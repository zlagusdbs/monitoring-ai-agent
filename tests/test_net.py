import ssl

import certifi

import net


def test_no_bundle_means_default_verification(monkeypatch):
    monkeypatch.setattr(net, "CA_BUNDLE", "")
    assert net.verify() is True


def test_missing_file_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(net, "CA_BUNDLE", "/nonexistent/ca.pem")
    assert net.verify() is True


def test_bundle_keeps_verification_but_drops_strict(monkeypatch, tmp_path):
    bundle = tmp_path / "ca.pem"
    bundle.write_text(open(certifi.where(), encoding="utf-8").read())
    monkeypatch.setattr(net, "CA_BUNDLE", str(bundle))
    ctx = net.verify()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert not (ctx.verify_flags & ssl.VERIFY_X509_STRICT)
