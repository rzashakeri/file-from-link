"""Error-fix round (2026-11-11): Telegram 429 retry, yt-dlp impersonation /
retries, 'no output file' retry with the most permissive format, and the
t.me 'setdefault' crash turned into a clear failure message."""
import os, sys, tempfile, time, types
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "jobs.db")
os.environ["DOWNLOAD_DIR"] = os.path.join(_tmp, "downloads")
os.environ["PUBLIC_DIR"] = os.path.join(_tmp, "public")
os.environ.setdefault("BOT_TOKEN", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Fake httpx (no network in tests): scripted responses per post() call.
class _FakeHTTPStatusError(Exception):
    def __init__(self, response):
        super().__init__(f"HTTP {response.status_code}")
        self.response = response

class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload
    def raise_for_status(self):
        if self.status_code >= 400:
            raise _FakeHTTPStatusError(self)

class _FakeClient:
    """responses: list of (status, payload); post() pops from the front."""
    responses = []
    calls = []
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def post(self, url, data=None, files=None):
        _FakeClient.calls.append((url, data, files))
        status, payload = _FakeClient.responses.pop(0)
        return _FakeResponse(status, payload)

_fake_httpx = types.ModuleType("httpx")
_fake_httpx.Client = _FakeClient
_fake_httpx.HTTPStatusError = _FakeHTTPStatusError
sys.modules["httpx"] = _fake_httpx

import app.sender as sender
import app.downloader as dl
from app.downloader import DownloadError
import yt_dlp


def test_build_opts_impersonation_and_retries():
    opts = dl._build_opts("720", "j1", None, url="https://example.com/v")
    assert opts["impersonate"] == "chrome", opts
    assert opts["retries"] == 10, opts
    assert opts["fragment_retries"] == 10, opts
    assert opts["format"] == "bv*[height<=720]+ba/b[height<=720]/bv*+ba/best/best", opts
    # force_best: most permissive format, same choice semantics
    assert dl._build_opts("720", "j1", None, force_best=True)["format"] == "bv*+ba/best"
    assert dl._build_opts("audio", "j1", None, force_best=True)["format"] == "ba/bestaudio/best"


def test_build_opts_without_curl_cffi():
    prev = sys.modules.get("curl_cffi")
    sys.modules["curl_cffi"] = None  # 'import curl_cffi' now raises ImportError
    try:
        opts = dl._build_opts("best", "j1", None, url="https://example.com/v")
        assert "impersonate" not in opts, opts
    finally:
        if prev is None:
            del sys.modules["curl_cffi"]
        else:
            sys.modules["curl_cffi"] = prev


def _reset_fake(responses):
    _FakeClient.responses = list(responses)
    _FakeClient.calls = []


def test_sender_429_retries_once_with_retry_after():
    _reset_fake([
        (429, {"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 2",
               "parameters": {"retry_after": 2}}),
        (200, {"ok": True, "result": {"message_id": 1}}),
    ])
    sleeps = []
    orig_sleep = time.sleep
    time.sleep = lambda s: sleeps.append(s)
    try:
        out = sender.tg("sendMessage", chat_id=1, text="hi")
    finally:
        time.sleep = orig_sleep
    assert out == {"ok": True, "result": {"message_id": 1}}, out
    assert sleeps == [2], sleeps
    assert len(_FakeClient.calls) == 2, _FakeClient.calls


def test_sender_429_without_retry_after_defaults_to_5s():
    _reset_fake([
        (429, {"ok": False, "error_code": 429, "description": "Too Many Requests"}),
        (200, {"ok": True, "result": {}}),
    ])
    sleeps = []
    orig_sleep = time.sleep
    time.sleep = lambda s: sleeps.append(s)
    try:
        sender.tg("sendMessage", chat_id=1, text="hi")
    finally:
        time.sleep = orig_sleep
    assert sleeps == [5], sleeps
    assert len(_FakeClient.calls) == 2


def test_sender_non_429_raises_immediately():
    _reset_fake([(400, {"ok": False, "description": "Bad Request"})])
    sleeps = []
    orig_sleep = time.sleep
    time.sleep = lambda s: sleeps.append(s)
    try:
        try:
            sender.tg("sendMessage", chat_id=1, text="hi")
            raise AssertionError("should have raised")
        except _FakeHTTPStatusError:
            pass
    finally:
        time.sleep = orig_sleep
    assert sleeps == [], sleeps
    assert len(_FakeClient.calls) == 1


def test_no_output_file_retries_with_best_format():
    calls = []
    def fake_extract(url, choice, job_id, on_progress, client=None, force_best=False):
        calls.append((choice, force_best))
        if len(calls) == 1:
            raise DownloadError("no output file")
        from pathlib import Path
        return Path("/tmp/x.mp4"), {"title": "t"}
    orig = dl._extract_once
    dl._extract_once = fake_extract
    try:
        path, meta = dl._download_ytdlp("https://example.com/v", "720", "j1")
    finally:
        dl._extract_once = orig
    assert str(path) == "/tmp/x.mp4", path
    assert calls == [("720", False), ("720", True)], calls


def test_other_download_errors_are_not_retried():
    calls = []
    def fake_extract(url, choice, job_id, on_progress, client=None, force_best=False):
        calls.append(force_best)
        raise DownloadError("boom")
    orig = dl._extract_once
    dl._extract_once = fake_extract
    try:
        try:
            dl._download_ytdlp("https://example.com/v", "720", "j1")
            raise AssertionError("should have raised")
        except DownloadError as e:
            assert str(e) == "boom", e
    finally:
        dl._extract_once = orig
    assert calls == [False], calls


def test_setdefault_crash_becomes_clear_error():
    class FakeYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download=True):
            raise AttributeError("'NoneType' object has no attribute 'setdefault'")
    orig = yt_dlp.YoutubeDL
    yt_dlp.YoutubeDL = FakeYDL
    try:
        try:
            dl._extract_once("https://t.me/somechannel/123", "best", "j1", None)
            raise AssertionError("should have raised")
        except DownloadError as e:
            assert "Telegram post" in str(e), e
        try:
            dl._extract_once("https://example.com/v", "best", "j1", None)
            raise AssertionError("should have raised")
        except DownloadError as e:
            assert "no downloadable media" in str(e), e
    finally:
        yt_dlp.YoutubeDL = orig


def test_job_timeout_default_3600():
    import importlib
    from app import config
    prev = os.environ.pop("JOB_TIMEOUT_SECONDS", None)
    try:
        importlib.reload(config)
        assert config.JOB_TIMEOUT == 3600, config.JOB_TIMEOUT
    finally:
        if prev is not None:
            os.environ["JOB_TIMEOUT_SECONDS"] = prev
        importlib.reload(config)
