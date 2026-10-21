"""yt-dlp wrapper: 1,700+ extractors (YouTube, Instagram, TikTok, X, ...).

YouTube from datacenter IPs often hits "Sign in to confirm you're not a bot".
Mitigations built in, tried in order:
  1. PO Tokens from the bgutil provider sidecar (docker service pot-provider)
     via the bgutil-ytdlp-pot-provider plugin.
  2. Optional cookies file (YTDLP_COOKIES_FILE) — used only if the file exists.
  3. Fallback player clients (tv, web_safari, ios) retried automatically.
"""
from pathlib import Path
import yt_dlp
from .config import DOWNLOAD_DIR, COOKIES_FILE, JOB_TIMEOUT, POT_BASE_URL, PROXY
from .utils import format_selector
class DownloadError(Exception): pass
BOT_WALL_MARKERS = ("not a bot", "sign in to confirm", "po token", "potoken")
FALLBACK_CLIENTS = ["tv", "web_safari", "ios"]
def _build_opts(choice, job_id, on_progress, player_client=None):
    out = str(DOWNLOAD_DIR / job_id / "%(title).80s.%(ext)s")
    def hook(d):
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            on_progress(d.get("downloaded_bytes", 0), total)
    opts = {
        "format": format_selector(choice), "outtmpl": out, "noplaylist": True,
        "progress_hooks": [hook], "socket_timeout": 30, "retries": 3,
        "merge_output_format": "mp4", "quiet": True, "no_warnings": True,
        "extractor_args": {"youtubepot-bgutilhttp": {"base_url": [POT_BASE_URL]}},
    }
    if PROXY:
        opts["proxy"] = PROXY
    if player_client:
        opts["extractor_args"]["youtube"] = {"player_client": [player_client]}
    if COOKIES_FILE and Path(COOKIES_FILE).exists():
        opts["cookiefile"] = COOKIES_FILE
    if choice == "audio":
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    return opts
def _extract_once(url, choice, job_id, on_progress, player_client=None):
    opts = _build_opts(choice, job_id, on_progress, player_client)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
        if choice == "audio": path = path.with_suffix(".mp3")
        if not path.exists():
            files = sorted(Path(DOWNLOAD_DIR / job_id).glob("*"), key=lambda p: p.stat().st_size, reverse=True)
            if not files: raise DownloadError("no output file")
            path = files[0]
        return path, {"title": info.get("title", ""), "duration": info.get("duration"), "extractor": info.get("extractor_key", "")}
def download(url: str, choice: str, job_id: str, on_progress=None) -> tuple[Path, dict]:
    Path(DOWNLOAD_DIR / job_id).mkdir(parents=True, exist_ok=True)
    attempts = [None] + FALLBACK_CLIENTS if "youtu" in url else [None]
    last_error = None
    for client in attempts:
        try:
            return _extract_once(url, choice, job_id, on_progress, client)
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            msg = str(e).lower()
            if client is not attempts[-1] and any(m in msg for m in BOT_WALL_MARKERS):
                continue  # bot wall -> try the next player client
            raise DownloadError(str(e)[:500]) from e
    raise DownloadError(str(last_error)[:500] if last_error else "download failed")
