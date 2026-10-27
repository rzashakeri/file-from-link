import asyncio, os, sys, tempfile
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "jobs.db")
os.environ["DOWNLOAD_DIR"] = os.path.join(_tmp, "downloads")
os.environ["PUBLIC_DIR"] = os.path.join(_tmp, "public")
os.environ.setdefault("BOT_TOKEN", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import time as _real_time
from app import db
import app.position_updates as pu
from app.position_updates import should_edit, refresh_once

class FakeClock:
    def __init__(self): self.now = 1000000.0
    def time(self): return self.now

class FakeBot:
    def __init__(self, fail=None):
        self.edits = []
        self.fail = fail or {}
    async def edit_message_text(self, chat_id, message_id, text):
        if message_id in self.fail:
            raise Exception(self.fail[message_id])
        self.edits.append((chat_id, message_id, text))

def _reset_db():
    import sqlite3
    con = sqlite3.connect(os.environ["DATABASE_PATH"])
    con.execute("DELETE FROM jobs")
    con.commit(); con.close()

def test_should_edit_policy():
    now = 1000000.0
    assert not should_edit(120, now - 61, 120, now)      # unchanged
    assert not should_edit(120, now - 61, 125, now)      # moved back
    assert not should_edit(120, now - 30, 100, now)      # big drop but too soon
    assert should_edit(120, now - 61, 115, now)          # drop >= 5
    assert should_edit(10, now - 61, 9, now)            # small drop, precise zone
    assert should_edit(11, now - 61, 10, now)            # reaching 10 edits
    assert not should_edit(12, now - 61, 11, now)        # small drop above 10: no edit
    assert not should_edit(20, now - 61, 17, now)        # drop 3 above 10: no edit

def test_db_round_trip():
    _reset_db()
    a = db.create_job(1, 11, "https://x/1", "best", "en", 100)
    b = db.create_job(1, 11, "https://x/2", "best", "en", 101)
    c = db.create_job(2, 22, "https://x/3", "best", "en", None)
    assert db.queue_position(a) == 1
    assert db.queue_position(b) == 2
    waiting = db.queued_jobs_with_status_msg()
    assert {w["id"] for w in waiting} == {a, b}
    assert {w["status_message_id"] for w in waiting} == {100, 101}
    db.update_job(a, status="downloading")
    assert db.queue_position(b) == 1
    assert [w["id"] for w in db.queued_jobs_with_status_msg()] == [b]

def test_refresh_once_edits_drops_baselines_first():
    _reset_db()
    clock = FakeClock()
    old_time = pu.time
    pu.time = clock
    try:
        a = db.create_job(1, 11, "https://x/1", "best", "en", 100)
        b = db.create_job(1, 11, "https://x/2", "best", "en", 101)
        c = db.create_job(1, 11, "https://x/3", "best", "en", 102)
        bot = FakeBot()
        shown = {}
        assert asyncio.run(refresh_once(bot, shown)) == 0
        assert bot.edits == []  # first sight only baselines
        db.update_job(a, status="downloading")  # b: 2->1, c: 3->2
        clock.now += 61
        assert asyncio.run(refresh_once(bot, shown)) == 2
        texts = {mid: txt for _, mid, txt in bot.edits}
        assert "position: 1" in texts[101]
        assert "position: 2" in texts[102]
        assert shown[b][0] == 1 and shown[c][0] == 2
    finally:
        pu.time = old_time

def test_refresh_once_handles_deleted_and_unmodified():
    _reset_db()
    clock = FakeClock()
    old_time = pu.time
    pu.time = clock
    try:
        a = db.create_job(1, 11, "https://x/1", "best", "en", 100)
        b = db.create_job(1, 11, "https://x/2", "best", "en", 101)
        c = db.create_job(1, 11, "https://x/3", "best", "en", 102)
        bot = FakeBot(fail={101: "Message to edit not found", 102: "Message is not modified"})
        shown = {}
        asyncio.run(refresh_once(bot, shown))  # baseline
        db.update_job(a, status="downloading")
        clock.now += 61
        asyncio.run(refresh_once(bot, shown))
        assert b not in shown  # deleted message dropped from tracking
        assert shown[c][0] == 2  # not-modified treated as shown
        assert bot.edits == []
    finally:
        pu.time = old_time
