#!/usr/bin/env python3
"""Daily File From Link backup (host cron, 00:00 Tehran).

Builds the same package as the one-off migration backup of 2026-11-02:
an online-safe SQLite copy of jobs.db, the deployed code at HEAD,
docker-compose.yml, the ops scripts, plus MANIFEST.txt and RESTORE.md —
tarred to the shared volume's backups dir, where the bot container sees
it as /data/backups/<file> (the send step lives in ops/daily_backup.sh).

Stdlib only. Prints machine-readable lines for the wrapper:
    ARCHIVE=<path>  SHA256=<hex>  SIZE=<bytes>  JOBS=<n>  USERS=<n>
    HEAD=<sha>  CAPTION=<one-line Persian caption for Telegram>
The archive's own sha256/size are in the stdout + caption (a manifest
inside the tar cannot contain the hash of the tar that holds it).

Secrets are never included: .env, cookie files and downloads/public
are excluded from the tar (see should_include).
"""
import hashlib
import io
import os
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TEHRAN = ZoneInfo("Asia/Tehran")
except Exception:  # minimal hosts without tzdata: Tehran is +3:30, no DST
    TEHRAN = timezone(timedelta(hours=3, minutes=30))

REPO_DIR = Path(os.environ.get("FFL_REPO_DIR", "/opt/file-from-link"))
DB_PATH = Path(os.environ.get(
    "FFL_DB_PATH",
    "/var/lib/docker/volumes/file-from-link_shared-data/_data/jobs.db"))
BACKUP_DIR = Path(os.environ.get(
    "FFL_BACKUP_DIR",
    "/var/lib/docker/volumes/file-from-link_shared-data/_data/backups"))
RETENTION_DAYS = int(os.environ.get("FFL_RETENTION_DAYS", "7"))

EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "downloads", "public",
                "bot-api-data", ".mypy_cache"}
EXCLUDE_FILES = {".env"}


def tehran_now():
    return datetime.now(TEHRAN)


def should_include(rel: Path) -> bool:
    """True unless any path part is an excluded dir/file or a .pyc."""
    for part in rel.parts:
        if part in EXCLUDE_DIRS or part in EXCLUDE_FILES:
            return False
    return rel.suffix != ".pyc"


def sqlite_backup(src: Path, dst: Path) -> dict:
    """Online-safe copy via the sqlite3 backup API, then verify it."""
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        dst_con = sqlite3.connect(dst)
        try:
            src_con.backup(dst_con)
        finally:
            dst_con.close()
    finally:
        src_con.close()
    con = sqlite3.connect(dst)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        jobs = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        con.close()
    if not ok:
        raise RuntimeError("jobs.db backup failed integrity_check")
    return {"jobs": jobs, "users": users}


def git_head(repo: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=repo, capture_output=True, text=True,
                           timeout=15)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def build_manifest(stamp: str, head: str, counts: dict, members: int) -> str:
    return "\n".join([
        "File From Link — daily backup",
        f"date (Tehran): {stamp}",
        f"code HEAD: {head}",
        f"jobs.db: {counts['jobs']} jobs, {counts['users']} users",
        f"archive members: {members}",
        "restore: see RESTORE.md in this archive",
        "",
    ])


RESTORE_TEXT = """# Restore — File From Link backup

1. Unpack this archive on the server (or a fresh Ubuntu 24.04 box).
2. Copy `jobs-*.db` to the shared volume as `jobs.db`:
   /var/lib/docker/volumes/file-from-link_shared-data/_data/jobs.db
3. Copy the `file-from-link/` tree to /opt/file-from-link.
4. Recreate /opt/file-from-link/.env from `.env.template` (names only) —
   the real secrets (bot token, cookies, API keys) are NEVER in a backup.
5. Start the stack:
   sudo docker compose --profile local-api up -d --build --scale worker=6
6. Check: sudo docker compose ps (12 containers Up) and the bot log.
"""


def _tar_filter(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
    rel = Path(ti.name)
    # ti.name starts with the "file-from-link/" arcname prefix.
    parts = rel.parts[1:] if len(rel.parts) > 1 else ()
    if not should_include(Path(*parts) if parts else Path(".")):
        return None
    return ti


def prune(backups: Path, days: int) -> list[str]:
    """Delete daily archives older than `days`; keep at least the newest.
    Never touches anything outside the file-from-link-backup-* pattern
    (e.g. the one-off 20261102 full backup stays)."""
    cutoff = time.time() - days * 86400
    files = sorted(backups.glob("file-from-link-backup-*.tar.gz"),
                   key=lambda p: p.stat().st_mtime)
    removed = []
    for p in files[:-1]:  # never delete the newest one
        if p.stat().st_mtime < cutoff:
            p.unlink()
            removed.append(p.name)
    return removed


def build(repo: Path, db: Path, out_dir: Path, retention_days: int = 7) -> dict:
    now = tehran_now()
    stamp = now.strftime("%Y%m%d-%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)
    head = git_head(repo)
    archive = out_dir / f"file-from-link-backup-{stamp}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / f"jobs-{stamp}.db"
        counts = sqlite_backup(db, db_copy)
        members = [0]

        def counting_filter(ti):
            ti = _tar_filter(ti)
            if ti is not None:
                members[0] += 1
            return ti

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(repo, arcname="file-from-link", recursive=True,
                    filter=counting_filter)
            members[0] += 1
            tar.add(db_copy, arcname=f"file-from-link/jobs-{stamp}.db")
            info = tarfile.TarInfo("file-from-link/RESTORE.md")
            data = RESTORE_TEXT.encode("utf-8")
            info.size = len(data)
            members[0] += 1
            tar.addfile(info, io.BytesIO(data))
            manifest = build_manifest(stamp, head, counts, members[0] + 1)
            info = tarfile.TarInfo("file-from-link/MANIFEST.txt")
            data = manifest.encode("utf-8")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    h = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    removed = prune(out_dir, retention_days)
    return {"archive": str(archive), "sha256": h.hexdigest(),
            "size": archive.stat().st_size,
            "jobs": counts["jobs"], "users": counts["users"], "head": head,
            "stamp": stamp, "pruned": removed}


def main():
    res = build(REPO_DIR, DB_PATH, BACKUP_DIR, RETENTION_DAYS)
    mb = res["size"] / 1048576
    d = res["stamp"]
    caption = (f"📦 بکاپ روزانه File From Link — {d[:4]}-{d[4:6]}-{d[6:8]}"
               f" — {res['jobs']} سفارش، {res['users']} کاربر"
               f" — {mb:.1f} MB — sha256: {res['sha256'][:12]}…")
    print(f"ARCHIVE={res['archive']}")
    print(f"SHA256={res['sha256']}")
    print(f"SIZE={res['size']}")
    print(f"JOBS={res['jobs']}")
    print(f"USERS={res['users']}")
    print(f"HEAD={res['head']}")
    print(f"CAPTION={caption}")
    if res["pruned"]:
        print(f"PRUNED={','.join(res['pruned'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
