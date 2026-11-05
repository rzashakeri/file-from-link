import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("BOT_TOKEN", "dummy")
os.environ.setdefault("DOWNLOAD_DIR", "/tmp/ffl-test-downloads")
os.environ.setdefault("PUBLIC_DIR", "/tmp/ffl-test-public")
os.environ.setdefault("DATABASE_PATH", "/tmp/ffl-test-jobs.db")
from app.utils import classify_url, url_extension, format_selector
from app.downloader import _classify_infos, probe_media
from app.github import (parse_github_url, is_github, _safe_filename,
                        _to_direct_download_url)


def test_url_extension():
    assert url_extension("https://cdn.example.com/a/photo.JPG?x=1#y") == "jpg"
    assert url_extension("https://example.com/noext") == ""
    assert url_extension("https://example.com/file.apk") == "apk"


def test_classify_url():
    assert classify_url("https://i.imgur.com/abc.jpg") == "photo"
    assert classify_url("https://cdn.example.com/pic.png?size=large") == "photo"
    assert classify_url("https://example.com/song.mp3") == "audio"
    assert classify_url("https://example.com/track.flac") == "audio"
    assert classify_url("https://github.com/o/r/releases/download/v1/app.apk") == "file"
    assert classify_url("https://example.com/archive.zip") == "file"
    assert classify_url("https://www.youtube.com/watch?v=abc123") is None
    assert classify_url("https://www.instagram.com/p/ABC123/") is None
    assert classify_url("https://github.com/MEH-VPN/MEH-VPN") is None


def test_format_selector_media():
    assert format_selector("img1080") == "best[height<=1080]/best"
    assert format_selector("img720") == "best[height<=720]/best"
    assert format_selector("photo") == "best"
    assert format_selector("audioorig") == "best"
    assert "height<=720" in format_selector("720")
    assert format_selector("720").endswith("/best")
    assert format_selector("???") == format_selector("best")


def _fmt(**kw):
    d = {"format_id": "x", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a",
         "width": 1920, "height": 1080, "filesize": 1000000}
    d.update(kw)
    return d


def test_classify_infos_video():
    info = {"duration": 60, "formats": [
        _fmt(height=1080, filesize=1000000),
        _fmt(height=720, filesize=500000),
        _fmt(vcodec="none", acodec="mp4a", ext="m4a", height=None, width=None, filesize=100000),
    ]}
    r = _classify_infos([info])
    assert r["kind"] == "video"
    assert [q["height"] for q in r["heights"]] == [1080, 720]
    assert r["has_audio"] is True


def test_classify_infos_photo():
    info = {"formats": [
        {"format_id": "0", "ext": "jpg", "vcodec": "images", "acodec": "none",
         "width": 1080, "height": 1080},
        {"format_id": "1", "ext": "jpg", "vcodec": "images", "acodec": "none",
         "width": 640, "height": 640},
    ]}
    r = _classify_infos([info])
    assert r["kind"] == "photo"
    assert r["images"] == [(1080, 1080), (640, 640)]
    assert r["heights"] == []


def test_classify_infos_photo_by_ext():
    info = {"formats": [
        {"format_id": "0", "ext": "jpg", "vcodec": "none", "acodec": "none",
         "width": 2048, "height": 1536},
    ]}
    assert _classify_infos([info])["kind"] == "photo"


def test_classify_infos_audio_and_file():
    audio = {"formats": [
        {"format_id": "0", "ext": "mp3", "vcodec": "none", "acodec": "mp3",
         "abr": 192, "filesize": 5000000},
    ]}
    r = _classify_infos([audio])
    assert r["kind"] == "audio" and r["has_audio"] is True
    onefile = {"formats": [
        {"format_id": "0", "ext": "apk", "vcodec": "none", "acodec": "none"},
    ]}
    assert _classify_infos([onefile])["kind"] == "file"
    assert _classify_infos([{"formats": []}])["kind"] == "unknown"


def test_probe_media_direct_urls_no_network():
    assert probe_media("https://cdn.example.com/a.png")["kind"] == "photo"
    assert probe_media("https://example.com/song.ogg")["kind"] == "audio"
    assert probe_media("https://example.com/app.apk")["kind"] == "file"


def test_is_github():
    assert is_github("https://github.com/o/r") is True
    assert is_github("https://raw.githubusercontent.com/o/r/main/f.txt") is True
    assert is_github("https://www.youtube.com/watch?v=x") is False


def test_parse_github_url():
    assert parse_github_url("https://github.com/MEH-VPN/MEH-VPN")["kind"] == "repo"
    assert parse_github_url("https://github.com/MEH-VPN/MEH-VPN/releases")["kind"] == "releases"
    r = parse_github_url("https://github.com/MEH-VPN/MEH-VPN/releases/tag/v1.3.1")
    assert r["kind"] == "release" and r["tag"] == "v1.3.1"
    a = parse_github_url("https://github.com/o/r/releases/download/v1.0/app.apk")
    assert a["kind"] == "asset" and a["tag"] == "v1.0" and a["asset"] == "app.apk"
    assert parse_github_url("https://github.com/o/r/archive/refs/tags/v1.zip")["kind"] == "archive"
    assert parse_github_url("https://raw.githubusercontent.com/o/r/main/f.txt")["kind"] == "raw"
    b = parse_github_url("https://github.com/o/r/blob/main/README.md")
    assert b["kind"] == "blob" and b["ref"] == "main" and b["path"] == "README.md"
    assert parse_github_url("https://github.com/o/r/issues/1")["kind"] == "other"
    assert parse_github_url("https://example.com/o/r")["kind"] == "other"


def test_github_filename_and_blob_url():
    assert _safe_filename("../../etc/passwd", "fb") == "_.._etc_passwd"
    assert _safe_filename("", "fb") == "fb"
    assert len(_safe_filename("x" * 200, "fb")) == 120
    assert _to_direct_download_url("https://github.com/o/r/blob/main/f.txt") == \
        "https://raw.githubusercontent.com/o/r/main/f.txt"
    asset = "https://github.com/o/r/releases/download/v1/a.apk"
    assert _to_direct_download_url(asset) == asset
