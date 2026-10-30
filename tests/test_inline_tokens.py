import os, sqlite3, sys, tempfile, time
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "jobs.db")
os.environ["DOWNLOAD_DIR"] = os.path.join(_tmp, "downloads")
os.environ["PUBLIC_DIR"] = os.path.join(_tmp, "public")
os.environ.setdefault("BOT_TOKEN", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db

def test_token_round_trip_and_single_use():
    db.save_inline_token("aabbccddeeff0011", "https://x.com/example/status/1")
    assert db.take_inline_token("aabbccddeeff0011") == "https://x.com/example/status/1"
    assert db.take_inline_token("aabbccddeeff0011") is None
    assert db.take_inline_token("nonexistent") is None

def test_expired_tokens_swept_on_save():
    con = sqlite3.connect(os.environ["DATABASE_PATH"])
    con.execute("INSERT INTO inline_tokens (token, url, created) VALUES (?,?,?)",
                ("oldtoken12345678", "https://example.com/old", time.time() - 7200))
    con.commit(); con.close()
    db.save_inline_token("newtoken12345678", "https://example.com/new")
    assert db.take_inline_token("oldtoken12345678") is None
    assert db.take_inline_token("newtoken12345678") == "https://example.com/new"
