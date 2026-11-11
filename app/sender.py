"""Deliver a finished file to a Telegram chat.
<=TELEGRAM_LIMIT: direct sendVideo/sendDocument (49MB on the cloud API,
2000MB via a local Bot API server). Above it: S3 presigned link if
configured, otherwise a public link served by app.api
(/files/<token>/<name>, TTL-bound)."""
import json, re, secrets, shutil, subprocess, time, urllib.parse
from pathlib import Path
import httpx
from .config import BOT_TOKEN, TELEGRAM_LIMIT, PUBLIC_DIR, PUBLIC_BASE_URL, S3_BUCKET, AWS_REGION, FILE_TTL_HOURS, BOT_API_BASE_URL
from .i18n import t as tr
API = f"{BOT_API_BASE_URL or 'https://api.telegram.org/bot'}{BOT_TOKEN}"
FILE_SEND_TIMEOUT = 1800  # a 1GB upload to Telegram DCs takes minutes
def _retry_after_seconds(resp) -> int | None:
    """Seconds Telegram asks us to wait after a 429, if it says so.
    Prefers parameters.retry_after; falls back to the description text
    ('Too Many Requests: retry after 5'). Capped at 60s."""
    try:
        p = (resp.json() or {}).get("parameters") or {}
        if p.get("retry_after") is not None:
            return max(0, min(60, int(p["retry_after"])))
    except Exception:
        pass
    try:
        m = re.search(r"retry after (\d+)", (resp.json() or {}).get("description") or "", re.I)
        if m: return max(0, min(60, int(m.group(1))))
    except Exception:
        pass
    return None

def tg(method, **kw):
    """One Bot API call. On a 429 (Telegram flood limit) waits out the
    retry_after Telegram reports (default 5s) and retries ONCE — a burst
    of status edits/sends must not fail the whole job. File uploads are
    rewound before the retry so the second attempt sends the full file."""
    timeout = kw.pop("timeout", 600)
    data = {k: v for k, v in kw.items() if not isinstance(v, tuple)}
    files = {k: v for k, v in kw.items() if isinstance(v, tuple)}
    for attempt in (1, 2):
        try:
            with httpx.Client(timeout=timeout) as c:
                r = c.post(f"{API}/{method}", data=data, files=files)
                r.raise_for_status(); return r.json()
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 429 and attempt == 1:
                wait = _retry_after_seconds(e.response)
                time.sleep(wait if wait is not None else 5)
                for _, f in files.values():
                    try: f.seek(0)
                    except Exception: pass
                continue
            raise
def send_text(chat_id, text, **kw): return tg("sendMessage", chat_id=chat_id, text=text, **kw)
def copy_message(chat_id, from_chat_id, message_id):
    return tg("copyMessage", chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)
def edit_text(chat_id, message_id, text, reply_markup=None):
    kw = {}
    if reply_markup is not None: kw["reply_markup"] = json.dumps(reply_markup)
    try: return tg("editMessageText", chat_id=chat_id, message_id=message_id, text=text, **kw)
    except Exception: return None
def edit_caption(chat_id, message_id, caption=""):
    """Replace a message caption (empty string clears it). Used to drop
    the URL caption off a done widget — the done view is header + bar
    only. Never raises."""
    try: return tg("editMessageCaption", chat_id=chat_id, message_id=message_id, caption=caption)
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
def send_animation(chat_id, path: Path, caption: str = ""):
    """Animation send: a muted looping MP4 or a real .gif file (sendAnimation)."""
    extra = _probe_video(path)
    with path.open("rb") as f:
        return tg("sendAnimation", chat_id=chat_id, caption=caption[:1000], timeout=FILE_SEND_TIMEOUT, animation=(path.name, f), **extra)
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
            tg(method, chat_id=chat_id, caption=caption, timeout=FILE_SEND_TIMEOUT, **extra, **{field:(path.name, f)})
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
