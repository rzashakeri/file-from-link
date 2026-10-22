"""Deliver a finished file to a Telegram chat.
<=49MB: direct sendVideo/sendDocument. >49MB: S3 presigned link if configured,
otherwise a public link served by app.api (/files/<token>/<name>, TTL-bound)."""
import json, secrets, shutil, subprocess, time, urllib.parse
from pathlib import Path
import httpx
from .config import BOT_TOKEN, TELEGRAM_LIMIT, PUBLIC_DIR, PUBLIC_BASE_URL, S3_BUCKET, AWS_REGION, FILE_TTL_HOURS
from .i18n import t as tr
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
def _probe_video(path: Path) -> dict:
    """Real width/height/duration via ffprobe — without these Telegram
    guesses the aspect ratio and clips look stretched or boxed."""
    try:
        out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                              "-show_streams", "-show_format", str(path)],
                             capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout)
        v = next(s for s in data.get("streams", []) if s.get("codec_type") == "video")
        meta = {}
        if v.get("width") and v.get("height"): meta.update(width=int(v["width"]), height=int(v["height"]))
        d = (data.get("format") or {}).get("duration") or v.get("duration")
        if d: meta["duration"] = int(float(d))
        return meta
    except Exception:
        return {}
def send_document_file(chat_id, path: Path, caption: str = ""):
    with path.open("rb") as f:
        return tg("sendDocument", chat_id=chat_id, caption=caption[:1000], document=(path.name, f))
def deliver(chat_id, path: Path, title: str, lang: str = 'en', direct_url: str | None = None) -> str:
    size = path.stat().st_size
    footer = tr(lang, "footer")
    if size <= TELEGRAM_LIMIT:
        suffix = path.suffix.lower()
        is_video = suffix in {".mp4",".mkv",".webm",".mov"}
        is_audio = suffix in {".mp3",".m4a",".ogg",".opus",".flac"}
        method = "sendVideo" if is_video else ("sendAudio" if is_audio else "sendDocument")
        field = {"sendVideo": "video", "sendAudio": "audio", "sendDocument": "document"}[method]
        extra = _probe_video(path) if is_video else {}
        if extra: extra["supports_streaming"] = True
        caption = f"{title or path.name}\n{footer}"[:1000]
        with path.open("rb") as f:
            tg(method, chat_id=chat_id, caption=caption, **extra, **{field:(path.name, f)})
        return "file"
    if S3_BUCKET:
        import boto3
        key = f"{int(time.time())}-{secrets.token_hex(4)}/{path.name}"
        boto3.client("s3", region_name=AWS_REGION).upload_file(str(path), S3_BUCKET, key)
        url = boto3.client("s3", region_name=AWS_REGION).generate_presigned_url(
            "get_object", Params={"Bucket":S3_BUCKET,"Key":key}, ExpiresIn=FILE_TTL_HOURS*3600)
        msg = tr(lang, "too_big", title=title, mb=size//1048576, hours=FILE_TTL_HOURS, url=url)
        if direct_url: msg += "\n" + tr(lang, "direct_link", url=direct_url)
        send_text(chat_id, msg + "\n" + footer)
        return "s3-link"
    token = secrets.token_hex(8); dest = PUBLIC_DIR/token; dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest/path.name)
    enc = urllib.parse.quote(path.name)
    url = f"{PUBLIC_BASE_URL}/files/{token}/{enc}" if PUBLIC_BASE_URL else f"/files/{token}/{enc}"
    msg = tr(lang, "too_big", title=title, mb=size//1048576, hours=FILE_TTL_HOURS, url=url)
    if direct_url: msg += "\n" + tr(lang, "direct_link", url=direct_url)
    send_text(chat_id, msg + "\n" + footer)
    return "link"
