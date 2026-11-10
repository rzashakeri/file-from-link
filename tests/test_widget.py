import asyncio, json, os, sys, tempfile, zlib
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "jobs.db")
os.environ["DOWNLOAD_DIR"] = os.path.join(_tmp, "downloads")
os.environ["PUBLIC_DIR"] = os.path.join(_tmp, "public")
os.environ.setdefault("BOT_TOKEN", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# System python has no httpx (it lives in the ytdlp venv); sender only
# needs it at call time, and every test below stubs w.tg anyway.
import types
_fake_httpx = types.ModuleType("httpx")
class _FakeClient:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def post(self, *a, **k): raise RuntimeError("no network in tests")
_fake_httpx.Client = _FakeClient
sys.modules.setdefault("httpx", _fake_httpx)
import app.widget as w
from app import db
import app.position_updates as pu
from app.position_updates import refresh_once

class FakeBot:
    def __init__(self):
        self.edits = []
    async def edit_message_text(self, chat_id, message_id, text):
        self.edits.append((chat_id, message_id, text))

def _reset_db():
    import sqlite3
    con = sqlite3.connect(os.environ["DATABASE_PATH"])
    con.execute("DELETE FROM jobs")
    con.commit(); con.close()

def test_html_size_limits():
    raw, comp = w.html_sizes()
    assert raw <= w.MAX_HTML_BYTES, f"raw {raw}"
    assert comp <= w.MAX_HTML_COMPRESSED, f"compressed {comp}"
    # The server checks the same numbers; a local zlib check guards them.
    assert len(zlib.compress(w.HTML.encode("utf-8"), 9)) == comp
    for needle in ("TelegramWidget", "chatData", "chatDataChanged", "JSON.parse",
                   'id="n"', "padding:12px 14px", 's.s==="done"',
                   'indexOf(": ")', 'indexOf("：")'):
        assert needle in w.HTML, needle

def test_encode_state_roundtrip_and_clamp():
    s = json.loads(w.encode_state("downloading", "downloading 42%", 42))
    assert s == {"s": "downloading", "l": "downloading 42%", "p": 42}
    assert json.loads(w.encode_state("queued", "line")) == {"s": "queued", "l": "line"}
    assert json.loads(w.encode_state("done", "ok", 150))["p"] == 100
    assert json.loads(w.encode_state("done", "ok", -5))["p"] == 0
    try:
        w.encode_state("bogus", "x")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown status must raise")

def test_encode_state_truncates_long_line():
    line = "تست " * 400  # ~2000 bytes of Persian: far over the 1024-byte budget
    s = w.encode_state("done", line)
    assert len(s.encode("utf-8")) <= w.MAX_STATE_BYTES
    d = json.loads(s)
    assert d["s"] == "done" and d["l"] and len(d["l"]) < len(line)

def test_send_widget_success_and_failure():
    calls = []
    def fake_tg(method, **kw):
        calls.append((method, kw))
        return {"result": {"message_id": 777}}
    old = w.tg
    w.tg = fake_tg
    try:
        mid = w.send_widget(123, w.encode_state("adding", "adding..."),
                            caption="https://example.com/x", reply_to=55)
        assert mid == 777
        method, kw = calls[0]
        assert method == "sendWidget"
        assert kw["chat_id"] == 123 and kw["html"] == w.HTML
        assert kw["height"] == 0  # automatic: bubble takes content height
        assert json.loads(kw["chat_data"])["s"] == "adding"
        assert kw["caption"] == "https://example.com/x"
        assert json.loads(kw["reply_parameters"]) == {"message_id": 55}
        assert "allow_queries" not in kw  # omitted = False, display-only
    finally:
        w.tg = old
    def boom(method, **kw):
        raise Exception("old server / not private")
    w.tg = boom
    try:
        assert w.send_widget(123, w.encode_state("adding", "x")) is None
    finally:
        w.tg = old

def test_update_widget_success_and_failure():
    calls = []
    def fake_tg(method, **kw):
        calls.append((method, kw))
        return True
    old = w.tg
    w.tg = fake_tg
    try:
        assert w.update_widget(123, 777, w.encode_state("queued", "pos 3")) is True
        method, kw = calls[0]
        assert method == "editMessageWidgetData"
        assert kw == {"chat_id": 123, "message_id": 777,
                      "chat_data": w.encode_state("queued", "pos 3")}
    finally:
        w.tg = old
    w.tg = lambda method, **kw: (_ for _ in ()).throw(Exception("gone"))
    try:
        assert w.update_widget(123, 777, w.encode_state("queued", "x")) is False
    finally:
        w.tg = old

def test_set_status_routes_by_kind_and_never_raises():
    seen = []
    old_upd, old_edit = w.update_widget, w.edit_text
    w.update_widget = lambda c, m, s: seen.append(("widget", c, m, s))
    w.edit_text = lambda c, m, text, **kw: seen.append(("text", c, m, text))
    try:
        w.set_status(1, 10, "widget", "downloading", "dl 42%", 42)
        w.set_status(1, 11, "text", "downloading", "dl 42%", 42)
        assert seen[0][0] == "widget" and json.loads(seen[0][3])["p"] == 42
        assert seen[1][0] == "text" and seen[1][3] == "dl 42%"
        w.update_widget = lambda c, m, s: (_ for _ in ()).throw(Exception("boom"))
        w.edit_text = lambda c, m, text, **kw: (_ for _ in ()).throw(Exception("boom"))
        w.set_status(1, 10, "widget", "failed", "err")  # must not raise
        w.set_status(1, 11, "text", "failed", "err")
    finally:
        w.update_widget, w.edit_text = old_upd, old_edit

def test_db_status_kind_roundtrip():
    _reset_db()
    a = db.create_job(1, 11, "https://x/1", "best", "en", 100, "widget")
    b = db.create_job(1, 11, "https://x/2", "best", "en", 101)
    assert db.get_job(a)["status_kind"] == "widget"
    assert db.get_job(b)["status_kind"] == "text"  # default
    waiting = db.queued_jobs_with_status_msg()
    by_id = {x["id"]: x for x in waiting}
    assert by_id[a]["status_kind"] == "widget"
    assert by_id[b]["status_kind"] == "text"

def test_position_refresh_routes_widget_jobs():
    _reset_db()
    a = db.create_job(1, 11, "https://x/1", "best", "en", 100, "widget")
    b = db.create_job(1, 11, "https://x/2", "best", "en", 101, "text")
    c = db.create_job(1, 11, "https://x/3", "best", "en", 102, "widget")
    widget_calls = []
    old = pu.update_widget
    pu.update_widget = lambda chat_id, message_id, state: widget_calls.append((chat_id, message_id, state)) or True
    clock_now = [1000000.0]
    old_time = pu.time
    pu.time = type("T", (), {"time": staticmethod(lambda: clock_now[0])})()
    try:
        bot = FakeBot()
        shown = {}
        assert asyncio.run(refresh_once(bot, shown)) == 0  # baselines only
        assert widget_calls == [] and bot.edits == []
        db.update_job(a, status="downloading")  # b: 2->1, c: 3->2
        clock_now[0] += 61
        assert asyncio.run(refresh_once(bot, shown)) == 2
        assert len(widget_calls) == 1  # only the widget job c
        assert widget_calls[0][:2] == (1, 102)
        assert json.loads(widget_calls[0][2])["s"] == "queued"
        assert "position: 2" in json.loads(widget_calls[0][2])["l"]
        assert len(bot.edits) == 1 and bot.edits[0][1] == 101  # only the text job b
    finally:
        pu.update_widget = old
        pu.time = old_time
