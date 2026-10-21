import shutil
from pathlib import Path
from . import db
from .downloader import download, DownloadError
from .sender import deliver, send_text, edit_text
from .config import DOWNLOAD_DIR
def process_job(job_id: str, status_message_id: int | None = None):
    job = db.get_job(job_id)
    if not job: return
    chat_id, fmt = job["chat_id"], job["fmt"]
    try:
        db.update_job(job_id, status="downloading")
        last = {"pct": -10}
        def prog(done, total):
            if total:
                pct = int(done*100/total)
                if pct - last["pct"] >= 10:
                    last["pct"] = pct
                    if status_message_id: edit_text(chat_id, status_message_id, f"⬇️ در حال دانلود… {pct}%")
        path, meta = download(job["url"], fmt, job_id, prog)
        db.update_job(job_id, status="uploading", title=meta.get("title",""), filepath=str(path), filesize=path.stat().st_size)
        if status_message_id: edit_text(chat_id, status_message_id, "⬆️ در حال ارسال به تلگرام…")
        deliver(chat_id, path, meta.get("title",""))
        db.update_job(job_id, status="done")
        if status_message_id: edit_text(chat_id, status_message_id, f"✅ انجام شد: {meta.get('title','')}")
    except DownloadError as e:
        db.update_job(job_id, status="failed", error=str(e))
        send_text(chat_id, f"❌ دانلود ناموفق بود:\n{e}")
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e)[:500])
        send_text(chat_id, "❌ خطای غیرمنتظره هنگام دانلود. دوباره تلاش کن.")
    finally:
        shutil.rmtree(DOWNLOAD_DIR/job_id, ignore_errors=True)
