"""Instagram profile-picture fetch: a fallback chain, HD-first.

Order (first success wins):
1. web_profile_info API -> profile_pic_url_hd (else profile_pic_url).
2. users/{id}/info API (needs the session cookie + the numeric id from
   step 1) -> hd_profile_pic_url_info.url.
3. Profile page og:image, ONLY with a session cookie (logged out,
   Instagram serves the same generic login-page image for every profile,
   which once made the bot send one identical wrong photo for all users).
4. CDN size rewrite: whatever URL we got, try its s1080x1080 variant
   first, then the original.
Without a session the API rate-limits datacenter IPs (429); the burner
session that made this work died 2026-10-23, so a fresh cookie export is
the only durable fix for reliability — the chain only maximizes what is
reachable without one."""
import os
import re
from pathlib import Path
import httpx
from .ig_urls import upscale_cdn_url, pick_pic_url, hd_info_url
_UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15"}
def _ig_cookie_header() -> dict:
    path = os.environ.get("IG_COOKIES_FILE", "")
    if not path or not Path(path).exists(): return {}
    jar = {}
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split("	")
            if len(parts) >= 7 and "instagram" in parts[0]:
                jar[parts[5]] = parts[6]
    except OSError:
        return {}
    if "sessionid" not in jar: return {}
    h = {"Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())}
    if jar.get("csrftoken"): h["X-CSRFToken"] = jar["csrftoken"]
    return h
def _get_json(url, params, headers):
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=20, follow_redirects=True)
        if r.status_code == 200: return r.json()
    except Exception:
        pass
    return None
def _fetch_pic_bytes(candidates):
    """Try candidate URLs in order; return the first successful download."""
    seen = set()
    for url in candidates:
        if not url or url in seen: continue
        seen.add(url)
        try:
            img = httpx.get(url, headers=_UA, timeout=30, follow_redirects=True)
            if img.status_code == 200 and img.content: return img.content
        except Exception:
            continue
    return None
def fetch_profile_pic(username: str) -> bytes:
    cookies = _ig_cookie_header()
    headers = {**_UA, "X-IG-App-ID": "936619743392459", **cookies}
    pic_url = None
    user_id = None
    data = _get_json("https://i.instagram.com/api/v1/users/web_profile_info/",
                     {"username": username}, headers)
    user = (data.get("data") or {}).get("user") or {} if data else {}
    pic_url = pick_pic_url(user)
    user_id = user.get("id") or user.get("pk")
    if not pic_url and cookies and user_id:
        data2 = _get_json(f"https://i.instagram.com/api/v1/users/{user_id}/info/",
                          None, headers)
        user2 = (data2.get("user") or {}) if data2 else {}
        pic_url = hd_info_url(user2)
    if not pic_url and cookies:
        try:
            html = httpx.get(f"https://www.instagram.com/{username}/",
                             headers={**_UA, **cookies}, timeout=20, follow_redirects=True).text
            m = re.search(r'property="og:image" content="([^"]+)"', html)
            if m: pic_url = m.group(1).replace("&amp;", "&")
        except Exception:
            pass
    if not pic_url: raise RuntimeError("profile picture not found")
    data_bytes = _fetch_pic_bytes([upscale_cdn_url(pic_url), pic_url])
    if not data_bytes: raise RuntimeError("profile picture not found")
    return _as_jpeg(data_bytes)
def _as_jpeg(data: bytes) -> bytes:
    """Telegram photos: JPEG/PNG pass through; WebP gets converted via ffmpeg."""
    if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
        return data
    try:
        import subprocess
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-frames:v", "1",
                              "-f", "mjpeg", "pipe:1"], input=data, capture_output=True, timeout=30)
        if out.returncode == 0 and out.stdout[:3] == b"\xff\xd8\xff":
            return out.stdout
    except Exception:
        pass
    return data
