"""X/Twitter GIF: two conversions for two buttons.

- to_animation: the picker 🎞 button — a muted looping MP4 Telegram
  displays as a GIF (sendAnimation). Small and fast.
- to_gif: the done-message 'Convert to GIF' button — a REAL .gif file
  (palette two-pass inside one filtergraph), so the user can save it as
  a GIF. Bigger than the MP4, so the button only appears on videos
  under CONVERT_MAX_SECONDS.
probe_video reports (has_video_stream, duration) for that button's
eligibility check. Kept free of telegram/yt-dlp imports so it stays
unit-testable: only pathlib + subprocess + config."""
import json
import subprocess
from pathlib import Path
from .config import DOWNLOAD_DIR
GIF_MAX_SECONDS = 60
GIF_WIDTH = 480
GIF_FPS = 15
CONVERT_MAX_SECONDS = 30
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov"}
def probe_video(path: Path) -> tuple[bool, float | None]:
    """(has_video_stream, duration_seconds). Never raises — (False, None)
    on any failure, so a probe problem can only hide the button, never
    break a delivery."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                              "-show_entries", "format=duration", "-of", "json", str(path)],
                             capture_output=True, text=True, timeout=30, check=True).stdout
        info = json.loads(out)
        has_video = any(s.get("codec_type") == "video" for s in info.get("streams", []))
        dur = (info.get("format") or {}).get("duration")
        return has_video, float(dur) if dur else None
    except Exception:
        return False, None
def to_animation(src: Path, job_id: str) -> Path:
    if src.suffix.lower() not in VIDEO_SUFFIXES:
        raise ValueError(f"not a video: {src.suffix}")
    dst = DOWNLOAD_DIR / job_id / "animation.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(src), "-t", str(GIF_MAX_SECONDS),
           "-vf", f"scale={GIF_WIDTH}:-2,fps={GIF_FPS}",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, capture_output=True, timeout=300, check=True)
    return dst
def to_gif(src: Path, job_id: str) -> Path:
    """Real .gif file: 480px wide, 15fps, palette two-pass. No audio by
    construction (GIF has no audio track). Raises on failure — a failed
    conversion must fail the convert job, never silently deliver a video."""
    if src.suffix.lower() not in VIDEO_SUFFIXES:
        raise ValueError(f"not a video: {src.suffix}")
    dst = DOWNLOAD_DIR / job_id / "converted.gif"
    dst.parent.mkdir(parents=True, exist_ok=True)
    filt = f"scale={GIF_WIDTH}:-2,fps={GIF_FPS},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    cmd = ["ffmpeg", "-y", "-i", str(src), "-t", str(GIF_MAX_SECONDS),
           "-vf", filt, str(dst)]
    subprocess.run(cmd, capture_output=True, timeout=600, check=True)
    return dst
