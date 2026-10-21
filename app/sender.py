"""Deliver a finished file to a Telegram chat.
<=49MB: direct sendVideo/sendDocument. >49MB: S3 presigned link if configured,
otherwise a public link served by app.api (/files/<token>/<name>, TTL-bound)."""
import secrets, shutil, time
from pathlib import Path
import httpx
from .config import BOT_TOKEN, TELEGRAM_LIMIT, PUBLIC_DIR, PUBLIC_BASE_URL, S3_BUCKET, AWS_REGION, FILE_TTL_HOURS
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
def tg(method, **kw):
    with httpx.Client(timeout=600) as c:
        r = c.post(f"{API}/{method}", data={k:v for k,v in kw.items() if not isinstance(v, tuple)},
                   files={k:v for k,v in kw.items() if isinstance(v, tuple)})
        r.raise_for_status(); return r.json()
def send_text(chat_id, text, **kw): return tg("sendMessage", chat_id=chat_id, text=text, **kw)
def edit_text(chat_id, message_id, text):
    try: return tg("editMessageText", chat_id=chat_id, message_id=message_id, text=text)
    except Exception: return None
def deliver(chat_id, path: Path, title: str) -> str:
    size = path.stat().st_size
    if size <= TELEGRAM_LIMIT:
        method = "sendVideo" if path.suffix.lower() in {".mp4",".mkv",".webm",".mov"} else "sendDocument"
        field = "video" if method=="sendVideo" else "document"
        with path.open("rb") as f:
            tg(method, chat_id=chat_id, caption=(title or path.name)[:1000], **{field:(path.name, f)})
        return "file"
    if S3_BUCKET:
        import boto3
        key = f"{int(time.time())}-{secrets.token_hex(4)}/{path.name}"
        boto3.client("s3", region_name=AWS_REGION).upload_file(str(path), S3_BUCKET, key)
        url = boto3.client("s3", region_name=AWS_REGION).generate_presigned_url(
            "get_object", Params={"Bucket":S3_BUCKET,"Key":key}, ExpiresIn=FILE_TTL_HOURS*3600)
        send_text(chat_id, f"📦 «{title}» بزرگ‌تر از سقف ۵۰MB تلگرام است ({size//1048576}MB).\nلینک دانلود ({FILE_TTL_HOURS} ساعت معتبر):\n{url}")
        return "s3-link"
    token = secrets.token_hex(8); dest = PUBLIC_DIR/token; dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest/path.name)
    url = f"{PUBLIC_BASE_URL}/files/{token}/{path.name}" if PUBLIC_BASE_URL else f"/files/{token}/{path.name}"
    send_text(chat_id, f"📦 «{title}» بزرگ‌تر از سقف ۵۰MB تلگرام است ({size//1048576}MB).\nلینک دانلود ({FILE_TTL_HOURS} ساعت معتبر):\n{url}")
    return "link"
