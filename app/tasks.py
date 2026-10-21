import shutil
from pathlib import Path
from . import db
from .downloader import download, DownloadError
from .sender import deliver, send_text, edit_text
from .config import DOWNLOAD_DIR
from .i18n import t as tr
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
        path, meta = download(job["url"], fmt, job_id, prog)
        db.update_job(job_id, status="uploading", title=meta.get("title",""), filepath=str(path), filesize=path.stat().st_size)
        if status_message_id: edit_text(chat_id, status_message_id, tr(lang, "uploading"))
        deliver(chat_id, path, meta.get("title",""), lang)
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
