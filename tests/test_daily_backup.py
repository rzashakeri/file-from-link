import importlib.util, os, sqlite3, sys, tarfile, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("BOT_TOKEN", "dummy")
# System python has no httpx (it lives in the ytdlp venv); sender only
# needs it at call time, and the send test below stubs send_document_file.
import types
_fake_httpx = types.ModuleType("httpx")
class _FakeClient:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def post(self, *a, **k): raise RuntimeError("no network in tests")
_fake_httpx.Client = _FakeClient
sys.modules.setdefault("httpx", _fake_httpx)
sys.path.insert(0, str(REPO))

def _load_daily_backup():
    spec = importlib.util.spec_from_file_location(
        "daily_backup", REPO / "ops" / "daily_backup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_should_include():
    db = _load_daily_backup()
    assert db.should_include(Path("app/bot.py"))
    assert db.should_include(Path("docker-compose.yml"))
    assert db.should_include(Path("ops/watchdog.py"))
    assert not db.should_include(Path(".env"))
    assert not db.should_include(Path(".git/config"))
    assert not db.should_include(Path("app/__pycache__/x.pyc"))
    assert not db.should_include(Path("app/x.pyc"))
    assert not db.should_include(Path("downloads/f.mp4"))
    assert not db.should_include(Path("public/tok/f.mp4"))
    assert not db.should_include(Path("bot-api-data/x"))

def _fake_repo(tmp):
    repo = Path(tmp) / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "bot.py").write_text("# bot\n")
    (repo / "docker-compose.yml").write_text("services: {}\n")
    (repo / ".env").write_text("BOT_TOKEN=secret-must-not-ship\n")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("x")
    (repo / "app" / "__pycache__").mkdir()
    (repo / "app" / "__pycache__" / "bot.cpython-312.pyc").write_bytes(b"\0")
    dbp = Path(tmp) / "jobs.db"
    con = sqlite3.connect(dbp)
    con.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO jobs (id) VALUES (?)", [(i,) for i in range(5)])
    con.executemany("INSERT INTO users (user_id) VALUES (?)", [(i,) for i in range(3)])
    con.commit(); con.close()
    return repo, dbp

def test_build_end_to_end():
    db = _load_daily_backup()
    with tempfile.TemporaryDirectory() as tmp:
        repo, dbp = _fake_repo(tmp)
        out = Path(tmp) / "backups"
        res = db.build(repo, dbp, out, retention_days=7)
        arc = Path(res["archive"])
        assert arc.exists() and res["size"] > 0 and len(res["sha256"]) == 64
        assert res["jobs"] == 5 and res["users"] == 3
        with tarfile.open(arc, "r:gz") as tar:
            names = tar.getnames()
        assert "file-from-link/app/bot.py" in names
        assert "file-from-link/docker-compose.yml" in names
        assert "file-from-link/RESTORE.md" in names
        assert "file-from-link/MANIFEST.txt" in names
        assert any(n.startswith("file-from-link/jobs-") and n.endswith(".db")
                   for n in names)
        assert not any(".env" in n for n in names)
        assert not any(".git" in n for n in names)
        assert not any("__pycache__" in n for n in names)
        assert not any(n.endswith(".pyc") for n in names)
        # the db copy inside the tar is intact and holds the rows
        with tarfile.open(arc, "r:gz") as tar:
            member = next(m for m in tar.getmembers() if m.name.endswith(".db"))
            probe = Path(tmp) / "probe.db"
            probe.write_bytes(tar.extractfile(member).read())
        con = sqlite3.connect(probe)
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 5
        con.close()

def test_prune_keeps_newest_week():
    db = _load_daily_backup()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        now = time.time()
        ages_days = [10, 9, 8, 6.5, 6, 5, 4, 3, 2, 1]  # 3 older than 7d
        for i, age in enumerate(ages_days):
            p = out / f"file-from-link-backup-2026110{i}-0030.tar.gz"
            p.write_bytes(b"x")
            os.utime(p, (now - age * 86400, now - age * 86400))
        keep = out / "file-from-link-full-backup-20261102.tar.gz"
        keep.write_bytes(b"x")
        os.utime(keep, (now - 30 * 86400, now - 30 * 86400))
        removed = db.prune(out, 7)
        remaining = sorted(p.name for p in out.iterdir())
        assert len([n for n in remaining
                    if n.startswith("file-from-link-backup-")]) == 7
        assert keep.name in remaining  # one-off full backup untouched
        assert len(removed) == 3

def test_send_backup_calls_owner():
    import app.send_backup as sb
    seen = []
    old = sb.send_document_file
    sb.send_document_file = lambda chat_id, path, caption: (
        seen.append((chat_id, str(path), caption))
        or {"result": {"message_id": 42}})
    try:
        assert sb.main(["send_backup.py", "/data/backups/x.tar.gz",
                        "cap here"]) == 0
        assert seen == [(7688899559, "/data/backups/x.tar.gz", "cap here")]
        assert sb.main(["send_backup.py"]) == 2
    finally:
        sb.send_document_file = old
