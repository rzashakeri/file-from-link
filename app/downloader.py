"""yt-dlp wrapper: 1700+ extractors (YouTube, Instagram, TikTok, X, ...)."""
from pathlib import Path
import yt_dlp
from .config import DOWNLOAD_DIR, COOKIES_FILE, JOB_TIMEOUT
from .utils import format_selector
class DownloadError(Exception): pass
def download(url: str, choice: str, job_id: str, on_progress=None) -> tuple[Path, dict]:
    out = str(DOWNLOAD_DIR / job_id / "%(title).80s.%(ext)s")
    Path(DOWNLOAD_DIR / job_id).mkdir(parents=True, exist_ok=True)
    def hook(d):
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            on_progress(d.get("downloaded_bytes",0), total)
    opts = {
        "format": format_selector(choice), "outtmpl": out, "noplaylist": True,
        "progress_hooks": [hook], "socket_timeout": 30, "retries": 3,
        "merge_output_format": "mp4", "quiet": True, "no_warnings": True,
    }
    if COOKIES_FILE: opts["cookiefile"] = COOKIES_FILE
    if choice == "audio":
        opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
            if choice == "audio": path = path.with_suffix(".mp3")
            if not path.exists():
                files = sorted(Path(DOWNLOAD_DIR/job_id).glob("*"), key=lambda p: p.stat().st_size, reverse=True)
                if not files: raise DownloadError("no output file")
                path = files[0]
            return path, {"title": info.get("title",""), "duration": info.get("duration"), "extractor": info.get("extractor_key","")}
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(str(e)[:500]) from e
