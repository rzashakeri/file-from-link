import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("BOT_TOKEN", "dummy")
os.environ.setdefault("DOWNLOAD_DIR", "/tmp/ffl-test-downloads")
os.environ.setdefault("PUBLIC_DIR", "/tmp/ffl-test-public")
os.environ.setdefault("DATABASE_PATH", "/tmp/ffl-test-jobs.db")
from pathlib import Path
from types import SimpleNamespace as NS

from app.gplay import (is_play_store, extract_package, _order_files,
                       _specs_for, download_play_apk, GooglePlayError)


def test_play_url_parsing():
    assert is_play_store("https://play.google.com/store/apps/details?id=com.whatsapp")
    assert is_play_store("https://play.google.com/store/apps/details?id=com.whatsapp&hl=fa&pcampaignid=web_share")
    assert is_play_store("https://www.play.google.com/store/apps/details?id=org.telegram.messenger")
    assert is_play_store("market://details?id=com.whatsapp")
    assert extract_package("https://play.google.com/store/apps/details?id=com.whatsapp") == "com.whatsapp"
    assert extract_package("https://play.google.com/store/apps/details?id=org.telegram.messenger&hl=en") == "org.telegram.messenger"
    assert extract_package("market://details?id=com.example.app") == "com.example.app"
    assert not is_play_store("https://play.google.com/store/apps")
    assert not is_play_store("https://play.google.com/store/apps/details")
    assert extract_package("https://play.google.com/store/apps/details") is None
    assert extract_package("https://play.google.com/store/apps/details?id=notapackage") is None
    assert extract_package("https://play.google.com/store/apps/details?id=com.") is None
    assert not is_play_store("https://example.com/store/apps/details?id=com.whatsapp")
    assert extract_package("https://www.youtube.com/watch?v=abc123") is None


def test_order_files():
    p = lambda n: Path("/tmp") / n
    files = _order_files([
        p("main.123.com.game.obb"), p("com.app-123-config.fa.apk"),
        p("com.app-123.apk"), p("com.app-123-asset.apk"),
        p("com.app-123-config.arm64_v8a.apk")])
    assert [f.name for f in files] == [
        "com.app-123.apk", "com.app-123-config.arm64_v8a.apk",
        "com.app-123-config.fa.apk", "com.app-123-asset.apk",
        "main.123.com.game.obb"]


def _fake_delivery(**kw):
    d = NS(download_url="https://cdn.example.com/base.apk", download_size=1000,
           gzipped_url="", gzipped_size=0, sha1="a", sha256="b", cookies=[],
           splits=[], additional_files=[])
    d.__dict__.update(kw)
    return d


def test_specs_naming():
    delivery = _fake_delivery(
        gzipped_url="https://cdn.example.com/base.apk.gz", gzipped_size=700,
        splits=[NS(name="config.arm64_v8a", url="https://cdn.example.com/s1.apk",
                   size=500, sha256="s1", gzipped_url="", gzipped_size=0)],
        additional_files=[
            NS(is_asset_pack=True, type_label="asset", version_code=123,
               size=300, url="https://cdn.example.com/asset.apk", gzipped=False,
               cookies=[], extension=".apk"),
            NS(is_asset_pack=False, type_label="main", version_code=123,
               size=200, url="https://cdn.example.com/main.obb", gzipped=False,
               cookies=[], extension=".obb")])
    specs = _specs_for(delivery, "com.app", 123, Path("/tmp/ffl-test-downloads/x"))
    names = [s.dest.name for s in specs]
    assert names == ["com.app-123.apk", "com.app-123-config.arm64_v8a.apk",
                     "com.app-123-asset.apk", "main.123.com.app.obb"]
    # gzipped transfer preferred for the base APK when Play offers it
    assert specs[0].url == "https://cdn.example.com/base.apk.gz"
    assert specs[0].gzipped is True


# --- stubbing gplaydl -------------------------------------------------------
# Module-level stand-ins for gplaydl's exception classes, so the fake
# implementations can raise them without reaching into the fake modules.
class PlayAPIError(Exception): pass
class AuthExpiredError(PlayAPIError): pass
class AppNotAvailableError(PlayAPIError): pass
class AppNotPurchasedError(PlayAPIError): pass
class AppNotSupportedError(PlayAPIError): pass


class _FakeGplay:
    """Fake gplaydl modules installed into sys.modules for one test."""
    def __init__(self, auth_impl, details_impl, purchase_impl, delivery_impl, batch_impl):
        api = types.ModuleType("gplaydl.api")
        api.PlayAPIError = PlayAPIError
        api.AuthExpiredError = AuthExpiredError
        api.AppNotAvailableError = AppNotAvailableError
        api.AppNotPurchasedError = AppNotPurchasedError
        api.AppNotSupportedError = AppNotSupportedError
        api.get_details = details_impl
        api.purchase = purchase_impl
        api.get_delivery = delivery_impl
        auth = types.ModuleType("gplaydl.auth")
        auth.ensure_auth = auth_impl
        dl = types.ModuleType("gplaydl.download")
        class DownloadError(Exception): pass
        class DownloadSpec:
            def __init__(self, url, dest, cookies=None, label="", gzipped=False, sha256="", sha1=""):
                self.url, self.dest, self.cookies, self.label = url, dest, cookies or [], label
                self.gzipped, self.sha256, self.sha1 = gzipped, sha256, sha1
        dl.DownloadError = DownloadError
        dl.DownloadSpec = DownloadSpec
        dl.download_batch = batch_impl
        pkg = types.ModuleType("gplaydl")
        pkg.__path__ = []
        self.modules = {"gplaydl": pkg, "gplaydl.api": api,
                        "gplaydl.auth": auth, "gplaydl.download": dl}
        self._saved = {}

    def __enter__(self):
        for k, v in self.modules.items():
            self._saved[k] = sys.modules.get(k)
            sys.modules[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        return False


def _never_batch(specs):
    raise AssertionError("download_batch must not be called")


def _write_batch(specs):
    for s in specs:
        Path(s.dest).parent.mkdir(parents=True, exist_ok=True)
        Path(s.dest).write_bytes(b"x" * 10)


def test_download_not_linked():
    with _FakeGplay(lambda **kw: None, None, None, None, _never_batch):
        try:
            download_play_apk("com.app", "gplay-t1", "fa")
            raise AssertionError("expected GooglePlayError")
        except GooglePlayError as e:
            assert "وصل نشده" in str(e)


def test_download_not_found():
    def details(package, auth):
        raise AppNotAvailableError("App not found or unavailable")
    with _FakeGplay(lambda **kw: {"authToken": "x"}, details, None, None, _never_batch):
        try:
            download_play_apk("com.nope", "gplay-t2", "fa")
            raise AssertionError("expected GooglePlayError")
        except GooglePlayError as e:
            assert "پیدا نشد" in str(e)


def test_download_paid():
    delivery_calls = {}
    def delivery(package, vc, auth, token, locales=None):
        delivery_calls["locales"] = locales
        raise AppNotPurchasedError("not purchased")
    details = NS(title="PaidApp", version_string="1.0", version_code=7)
    with _FakeGplay(lambda **kw: {"authToken": "x"},
                    lambda package, auth: details,
                    lambda package, vc, auth: "tok", delivery, _never_batch):
        try:
            download_play_apk("com.paid", "gplay-t3", "fa")
            raise AssertionError("expected GooglePlayError")
        except GooglePlayError as e:
            assert "پولیه" in str(e)


def test_download_too_big():
    big = _fake_delivery(download_size=2_000_000_000)
    details = NS(title="Big", version_string="1.0", version_code=1)
    with _FakeGplay(lambda **kw: {"authToken": "x"},
                    lambda package, auth: details,
                    lambda package, vc, auth: "tok",
                    lambda package, vc, auth, token, locales=None: big,
                    _never_batch):
        try:
            download_play_apk("com.big", "gplay-t4", "fa")
            raise AssertionError("expected GooglePlayError")
        except GooglePlayError as e:
            assert "بزرگه" in str(e)


def test_download_happy_path():
    calls = {"delivery_kwargs": None, "refresh": []}
    def ensure_auth(**kw):
        calls["refresh"].append(kw.get("force_refresh", False))
        return {"authToken": "x"}
    state = {"n": 0}
    def details(package, auth):
        state["n"] += 1
        if state["n"] == 1:
            raise AuthExpiredError("expired")
        return NS(title="TestApp", version_string="1.2.3", version_code=42)
    def delivery(package, vc, auth, token, locales=None):
        calls["delivery_kwargs"] = {"vc": vc, "token": token, "locales": locales}
        return _fake_delivery(
            download_size=1000,
            splits=[NS(name="config.arm64_v8a", url="https://cdn/s1.apk", size=500,
                       sha256="s1", gzipped_url="", gzipped_size=0),
                    NS(name="config.fa", url="https://cdn/s2.apk", size=100,
                       sha256="s2", gzipped_url="", gzipped_size=0)],
            additional_files=[NS(is_asset_pack=False, type_label="main",
                                 version_code=42, size=200,
                                 url="https://cdn/main.obb", gzipped=False,
                                 cookies=[], extension=".obb")])
    progress = []
    with _FakeGplay(ensure_auth, details,
                    lambda package, vc, auth: "tok", delivery, _write_batch):
        base, meta = download_play_apk("com.app", "gplay-t5", "fa",
                                       on_progress=lambda d, t: progress.append((d, t)))
    # expired token retried once with a forced refresh
    assert calls["refresh"] == [False, True]
    # Persian language split requested
    assert calls["delivery_kwargs"]["locales"] == ["fa"]
    assert calls["delivery_kwargs"]["vc"] == 42
    assert base.name == "com.app-42.apk"
    assert meta["title"] == "TestApp 1.2.3"
    assert meta["extractor"] == "GooglePlay"
    assert "SAI" in meta["description"]
    assert [Path(f).name for f in meta["files"]] == [
        "com.app-42.apk", "com.app-42-config.arm64_v8a.apk",
        "com.app-42-config.fa.apk", "main.42.com.app.obb"]
    # progress: starts at 0, ends at the bytes actually written, monotonic
    assert progress[0] == (0, 1800)
    assert progress[-1] == (40, 1800)
    assert all(progress[i][0] <= progress[i + 1][0] for i in range(len(progress) - 1))
    for f in meta["files"]:
        assert Path(f).exists()
