import shutil
from pathlib import Path
from . import db
from .downloader import download, DownloadError, get_direct_url, resolve_stream_match
from .sender import deliver, send_text, edit_text, send_document_file
from .config import DOWNLOAD_DIR, TELEGRAM_LIMIT, JOB_TIMEOUT
from .i18n import t as tr
from .utils import is_spotify, is_apple_music
from .cleanup import sweep_public
def process_job(job_id: str, status_message_id: int | None = None):
    sweep_public()
    job = db.get_job(job_id)
    if not job: return
    chat_id, fmt = job["chat_id"], job["fmt"]; lang = job.get("lang") or "en"
    try:
        db.update_job(job_id, status="downloading")
        last = {"pct": -10}
        def prog(done, total):
            if total:
                pct = int(done*100/total)
                if pct - last["pct"] >= 10:
                    last["pct"] = pct
                    if status_message_id: edit_text(chat_id, status_message_id, tr(lang, "downloading", pct=pct))
        url = job["url"]
        if is_spotify(url) or is_apple_music(url):
            if status_message_id: edit_text(chat_id, status_message_id, tr(lang, "matching"))
            url = resolve_stream_match(url)
        path, meta = download(url, fmt, job_id, prog)
        db.update_job(job_id, status="uploading", title=meta.get("title",""), filepath=str(path), filesize=path.stat().st_size)
        if status_message_id: edit_text(chat_id, status_message_id, tr(lang, "uploading"))
        direct = None
        if path.stat().st_size > TELEGRAM_LIMIT:
            try: direct = get_direct_url(job["url"], fmt)
            except Exception: direct = None
        deliver(chat_id, path, meta.get("title",""), lang, direct)
        _deliver_extras(chat_id, job_id, meta, lang)
        db.update_job(job_id, status="done")
        if status_message_id: edit_text(chat_id, status_message_id, tr(lang, "done", title=meta.get("title","")))
    except DownloadError as e:
        db.update_job(job_id, status="failed", error=str(e))
        send_text(chat_id, tr(lang, "failed", error=str(e)))
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e)[:500])
        send_text(chat_id, tr(lang, "failed_generic"))
    finally:
        shutil.rmtree(DOWNLOAD_DIR/job_id, ignore_errors=True)

def _fail_and_notify(job, reason):
    try: db.update_job(job["id"], status="failed", error=reason[:500])
    except Exception: pass
    try: send_text(job["chat_id"], tr(job.get("lang") or "en", "failed_generic"))
    except Exception: pass
    shutil.rmtree(DOWNLOAD_DIR/job["id"], ignore_errors=True)

def on_job_failure(rq_job, connection, exc_type, exc_value, tb):
    """RQ failure callback: fires when a job crashes or hits JOB_TIMEOUT.
    Without it, a timeout-killed job left the DB row in 'downloading'
    forever and the user was never told — the bot looked frozen."""
    try:
        jid = rq_job.args[0]
        job = db.get_job(jid)
        if job and job["status"] not in ("done", "failed"):
            reason = "timeout" if exc_type and "Timeout" in getattr(exc_type, "__name__", "") else str(exc_value)
            _fail_and_notify(job, reason or "worker error")
    except Exception:
        pass

def reconcile_stale() -> int:
    """Watchdog entrypoint: fail jobs stuck active beyond timeout + grace."""
    stale = db.stale_active_jobs(JOB_TIMEOUT + 300)
    for job in stale:
        _fail_and_notify(job, "timeout (watchdog)")
    return len(stale)

def _deliver_extras(chat_id, job_id, meta, lang):
    """User-requested extras: the video's full description and its
    subtitles (fa/en incl. auto-captions), sent after the file itself.
    Best-effort only — a failure here never fails the job."""
    footer = tr(lang, "footer")
    desc = (meta.get("description") or "").strip()
    if len(desc) > 30:
        try:
            header = tr(lang, "description")
            if len(desc) <= 3500:
                send_text(chat_id, f"{header}\n\n{desc}\n\n{footer}")
            else:
                f = Path(DOWNLOAD_DIR) / job_id / "description.txt"
                f.write_text(desc, encoding="utf-8")
                send_document_file(chat_id, f, f"{header}\n{footer}")
        except Exception:
            pass
    for sub in meta.get("subtitles") or []:
        try:
            send_document_file(chat_id, Path(sub), footer)
        except Exception:
            pass
