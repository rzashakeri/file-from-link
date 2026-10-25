"""Cobalt intermediary (imputnet/cobalt) as FIRST route for Cobalt-covered
services; any Cobalt failure falls back to the existing yt-dlp / IG-API paths.

API: POST {COBALT_API_URL}/api/json, headers Accept + Content-Type
application/json, optional `Authorization: Api-Key <key>`.
Response: {status: error|redirect|stream|success|rate-limit|picker,
url, pickerType, picker: [{type, url, thumb}], audio, text}.
Tunnel/stream URLs live only ~90-120s, so the worker downloads them to
disk immediately; user-facing delivery still goes through our own pipeline.
Cobalt returns media only -- no subtitles, no description/caption.
"""
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import (DOWNLOAD_DIR, MAX_FILE_BYTES, COBALT_API_URL,
                     COBALT_API_KEY)


class CobaltError(Exception):
    pass


# Host suffixes Cobalt covers. Deliberately NOT YouTube: yt-dlp's YouTube
# path works (PO-token stack) and keeps subtitles, description and the
# 320/192/48 kbps audio tiers, which Cobalt does not provide. Spotify /
# Apple Music are not Cobalt services at all (they resolve to YouTube
# matching in tasks.py first) and stay on yt-dlp.
COBALT_HOSTS = (
    "instagram.com", "tiktok.com", "twitter.com", "x.com", "reddit.com",
    "facebook.com", "fb.watch", "vimeo.com", "vk.com", "pinterest.com",
    "dailymotion.com", "twitch.tv", "tumblr.com", "bilibili.com",
    "streamable.com", "snapchat.com", "ok.ru", "rutube.ru", "loom.com",
    "newgrounds.com", "soundcloud.com", "xiaohongshu.com", "xhslink.com",
)


def cobalt_supported(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in COBALT_HOSTS)


def _body(url: str, choice: str) -> dict:
    body = {"url": url, "vCodec": "h264", "filenamePattern": "classic"}
    if choice in ("audiohq", "audio", "audiolow"):
        body["isAudioOnly"] = True
        body["aFormat"] = "mp3"
    else:
        m = re.search(r"(\d{3,4})", choice or "")
        body["vQuality"] = m.group(1) if m else "max"
    return body


def _ext_for(url: str, kind: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]{2,5})(?:[?#]|$)", url)
    if m:
        return "." + m.group(1).lower()
    return {"video": ".mp4", "photo": ".jpg", "gif": ".gif"}.get(kind, ".mp4")


def _download_one(client, url: str, dest: Path) -> Path:
    with client.stream("GET", url, timeout=300) as resp:
        resp.raise_for_status()
        size = int(resp.headers.get("content-length") or 0)
        if size and size > MAX_FILE_BYTES:
            raise CobaltError("file larger than the 1 GB limit")
        written = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(1 << 16):
                f.write(chunk)
                written += len(chunk)
                if written > MAX_FILE_BYTES:
                    raise CobaltError("file larger than the 1 GB limit")
    if dest.stat().st_size < 1024:
        raise CobaltError("cobalt returned an unexpectedly small file")
    return dest


def cobalt_download(url: str, choice: str, job_id: str, on_progress=None):
    dest = Path(DOWNLOAD_DIR / job_id)
    dest.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if COBALT_API_KEY:
        headers["Authorization"] = f"Api-Key {COBALT_API_KEY}"
    try:
        with httpx.Client(timeout=180, follow_redirects=True) as client:
            r = client.post(f"{COBALT_API_URL.rstrip('/')}/api/json",
                            json=_body(url, choice), headers=headers)
    except Exception as e:
        raise CobaltError(f"cobalt unreachable: {e}") from e
    if r.status_code in (401, 403):
        raise CobaltError("cobalt requires an API key for this instance")
    try:
        data = r.json()
    except Exception:
        raise CobaltError(f"cobalt bad response ({r.status_code})")
    status = data.get("status")
    if status in ("error", "rate-limit"):
        raise CobaltError(f"cobalt {status}: {(data.get('text') or '')[:200]}")
    audio_choice = choice in ("audiohq", "audio", "audiolow")
    targets = []
    if status == "picker":
        if audio_choice:
            # Picker + audio: let the yt-dlp / IG-API paths extract audio.
            raise CobaltError("cobalt picker with audio request: fall back")
        for it in (data.get("picker") or [])[:20]:
            if it.get("url"):
                targets.append((it.get("type") or "video", it["url"]))
    elif status in ("success", "redirect", "stream"):
        if audio_choice:
            if data.get("audio"):
                targets.append(("video", data["audio"]))
            else:
                raise CobaltError("cobalt returned no audio: fall back")
        elif data.get("url"):
            targets.append(("video", data["url"]))
    if not targets:
        raise CobaltError(f"cobalt returned no file (status={status})")
    files = []
    try:
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            for i, (kind, mu) in enumerate(targets, 1):
                fp = dest / f"cobalt_{i:02d}{_ext_for(mu, kind)}"
                _download_one(client, mu, fp)
                files.append(fp)
                if on_progress:
                    on_progress(i, len(targets))
    except CobaltError:
        raise
    except Exception as e:
        raise CobaltError(f"cobalt download failed: {str(e)[:200]}") from e
    return files[0], {"title": files[0].stem, "duration": None,
                      "extractor": "Cobalt", "description": "",
                      "subtitles": [], "files": [str(f) for f in files]}
