import sqlite3, time, uuid, json
from .config import DATABASE_PATH
def _c():
    con = sqlite3.connect(DATABASE_PATH); con.row_factory = sqlite3.Row; return con
def init():
    with _c() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY, chat_id INTEGER, user_id INTEGER, url TEXT,
          fmt TEXT, status TEXT, title TEXT, filepath TEXT, filesize INTEGER,
          error TEXT, created REAL, updated REAL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS users(
          user_id INTEGER PRIMARY KEY, lang TEXT, updated REAL)""")
        cols = [r[1] for r in con.execute("PRAGMA table_info(jobs)")]
        if "lang" not in cols:
            con.execute("ALTER TABLE jobs ADD COLUMN lang TEXT DEFAULT 'en'")
init()
def create_job(chat_id, user_id, url, fmt, lang="en"):
    jid = uuid.uuid4().hex[:12]; now = time.time()
    with _c() as con:
        con.execute("INSERT INTO jobs (id,chat_id,user_id,url,fmt,status,created,updated,lang) VALUES (?,?,?,?,?,'queued',?,?,?)",
                    (jid, chat_id, user_id, url, fmt, now, now, lang))
    return jid
def get_lang(user_id):
    with _c() as con:
        r = con.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    return r["lang"] if r and r["lang"] else None
def set_lang(user_id, lang):
    with _c() as con:
        con.execute("INSERT INTO users (user_id, lang, updated) VALUES (?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang, updated=excluded.updated",
                    (user_id, lang, time.time()))
def update_job(jid, **kw):
    kw["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in kw)
    with _c() as con: con.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*kw.values(), jid))
def get_job(jid):
    with _c() as con:
        r = con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    return dict(r) if r else None
def active_jobs_for_user(user_id):
    with _c() as con:
        return con.execute("SELECT COUNT(*) c FROM jobs WHERE user_id=? AND status IN ('queued','downloading','uploading')",
                           (user_id,)).fetchone()["c"]
def queue_position(jid):
    with _c() as con:
        r = con.execute("SELECT created FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r: return None
        return con.execute("SELECT COUNT(*) c FROM jobs WHERE status='queued' AND created<=?", (r["created"],)).fetchone()["c"]
def stale_active_jobs(max_age_seconds):
    """Jobs stuck in downloading/uploading whose last update is older than max_age."""
    cutoff = time.time() - max_age_seconds
    with _c() as con:
        rows = con.execute("SELECT * FROM jobs WHERE status IN ('downloading','uploading') AND updated<?",
                           (cutoff,)).fetchall()
    return [dict(r) for r in rows]
def stats():
    import time as _t
    day_start = _t.time() - (_t.time() % 86400)
    with _c() as con:
        users = con.execute("SELECT COUNT(DISTINCT user_id) c FROM (SELECT user_id FROM users UNION SELECT user_id FROM jobs)").fetchone()["c"]
        jobs = con.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
        done = con.execute("SELECT COUNT(*) c FROM jobs WHERE status='done'").fetchone()["c"]
        failed = con.execute("SELECT COUNT(*) c FROM jobs WHERE status='failed'").fetchone()["c"]
        today = con.execute("SELECT COUNT(*) c FROM jobs WHERE created>=?", (day_start,)).fetchone()["c"]
    return {"users": users, "jobs": jobs, "done": done, "failed": failed, "today": today}
def first_user_id():
    with _c() as con:
        r = con.execute("SELECT user_id FROM jobs ORDER BY created ASC LIMIT 1").fetchone()
    return r["user_id"] if r else None
