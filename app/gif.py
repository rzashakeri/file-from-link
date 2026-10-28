"""X/Twitter GIF: convert a downloaded video into the muted looping MP4
Telegram displays as a GIF (sendAnimation). A real .gif file would be many
times bigger for the same clip, so the animation is the format users mean
when they say 'GIF' in Telegram. Kept free of telegram/yt-dlp imports so
it stays unit-testable: only pathlib + subprocess + config."""
import subprocess
from pathlib import Path
from .config import DOWNLOAD_DIR
GIF_MAX_SECONDS = 60
GIF_WIDTH = 480
GIF_FPS = 15
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov"}
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
