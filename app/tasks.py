import shutil
from pathlib import Path
from . import db
from .downloader import download, DownloadError, get_direct_url, resolve_stream_match
from .sender import deliver, send_text, edit_text
from .config import DOWNLOAD_DIR, TELEGRAM_LIMIT
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
