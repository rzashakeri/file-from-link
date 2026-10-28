import json, os, subprocess, sys, tempfile
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "jobs.db")
os.environ["DOWNLOAD_DIR"] = os.path.join(_tmp, "downloads")
os.environ["PUBLIC_DIR"] = os.path.join(_tmp, "public")
os.environ.setdefault("BOT_TOKEN", "dummy")
os.environ.pop("MAX_FILE_BYTES", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db
from app.config import MAX_FILE_BYTES, DOWNLOAD_DIR
from app.gif import to_animation, to_gif, probe_video, CONVERT_MAX_SECONDS
from app.utils import FORMATS, format_selector
from pathlib import Path

def _make_video(name, dur, w=320, h=240, fps=30, with_audio=True):
    src = Path(_tmp) / name
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate={fps}:duration={dur}"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}"]
    cmd += ["-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)]
    subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    return src

def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_streams", "-show_format", str(path)],
                         capture_output=True, text=True, timeout=30)
    return json.loads(out.stdout)

def test_config_cap_1_9gb():
    assert MAX_FILE_BYTES == 1900 * 1000 * 1000

def test_db_default_fmt():
    db.set_lang(101, "fa")
    assert db.get_default_fmt(101) is None
    db.set_default_fmt(101, "720")
    assert db.get_default_fmt(101) == "720"
    assert db.get_lang(101) == "fa"  # setting default must not clobber lang
    db.set_lang(101, "en")
    assert db.get_default_fmt(101) == "720"  # setting lang must not clobber default
    db.set_default_fmt(101, None)
    assert db.get_default_fmt(101) is None

def test_format_selector_gif_falls_back_to_best():
    assert format_selector("gif") == FORMATS["best"]

def test_to_animation_muted_480p_no_audio():
    src = _make_video("clip.mp4", 2)
    out = to_animation(src, "job1")
    assert out.exists() and out.stat().st_size > 0
    data = _probe(out)
    kinds = [s["codec_type"] for s in data["streams"]]
    assert "video" in kinds and "audio" not in kinds
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    assert v["width"] == 480

def test_to_animation_caps_duration_at_60s():
    src = _make_video("long.mp4", 65, w=160, h=120, fps=10, with_audio=False)
    out = to_animation(src, "job2")
    dur = float(_probe(out)["format"]["duration"])
    assert dur <= 61

def test_to_animation_rejects_non_video():
    fake = Path(_tmp) / "pic.jpg"
    fake.write_bytes(b"not an image")
    try:
        to_animation(fake, "job3")
        raise AssertionError("should have raised")
    except ValueError:
        pass

def test_format_selector_togif_falls_back_to_best():
    assert format_selector("togif") == FORMATS["best"]

def test_probe_video_reports_stream_and_duration():
    src = _make_video("probe.mp4", 2)
    has_video, dur = probe_video(src)
    assert has_video is True and dur is not None and 1.5 <= dur <= 2.5
    assert probe_video(Path(_tmp) / "missing.mp4") == (False, None)

def test_to_gif_produces_real_gif_no_audio():
    src = _make_video("gifsrc.mp4", 2)
    out = to_gif(src, "jobgif")
    assert out.suffix == ".gif" and out.exists() and out.stat().st_size > 0
    data = _probe(out)
    kinds = [s["codec_type"] for s in data["streams"]]
    assert "video" in kinds and "audio" not in kinds
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    assert v["width"] == 480
    assert v["codec_name"] == "gif"

def test_to_gif_rejects_non_video():
    fake = Path(_tmp) / "pic2.jpg"
    fake.write_bytes(b"not an image")
    try:
        to_gif(fake, "jobgif2")
        raise AssertionError("should have raised")
    except ValueError:
        pass

def test_convert_threshold_is_30s():
    assert CONVERT_MAX_SECONDS == 30
