"""Instagram profile-picture fetch via the web_profile_info API (HD url).
NOTE: there is deliberately NO og:image fallback — logged out, Instagram
serves the same generic login-page image for every profile, which made the
bot send one identical (wrong) photo for all users. Without a login the API
rate-limits datacenter IPs (429); with IG_COOKIES_FILE set (a burner
account's session) the same call succeeds — that is also what stories need."""
import os
from pathlib import Path
import httpx
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
def fetch_profile_pic(username: str) -> bytes:
    headers = {**_UA, "X-IG-App-ID": "936619743392459", **_ig_cookie_header()}
    r = httpx.get("https://i.instagram.com/api/v1/users/web_profile_info/",
                  params={"username": username}, headers=headers,
                  timeout=20, follow_redirects=True)
    if r.status_code != 200: raise RuntimeError(f"instagram api {r.status_code}")
    user = (r.json().get("data") or {}).get("user") or {}
    pic_url = user.get("profile_pic_url_hd") or user.get("profile_pic_url")
    if not pic_url: raise RuntimeError("profile picture not found")
    img = httpx.get(pic_url, headers=_UA, timeout=30, follow_redirects=True)
    img.raise_for_status()
    return _as_jpeg(img.content)
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
