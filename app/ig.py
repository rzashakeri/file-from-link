"""Instagram profile-picture fetch (public data, no login).
Primary: the web_profile_info API (HD url). Fallback: og:image of the profile page."""
import re
import httpx
_UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15"}
def fetch_profile_pic(username: str) -> bytes:
    pic_url = None
    try:
        r = httpx.get("https://i.instagram.com/api/v1/users/web_profile_info/",
                      params={"username": username},
                      headers={**_UA, "X-IG-App-ID": "936619743392459"},
                      timeout=20, follow_redirects=True)
        if r.status_code == 200:
            user = (r.json().get("data") or {}).get("user") or {}
            pic_url = user.get("profile_pic_url_hd") or user.get("profile_pic_url")
    except Exception:
        pic_url = None
    if not pic_url:
        html = httpx.get(f"https://www.instagram.com/{username}/", headers=_UA,
                         timeout=20, follow_redirects=True).text
        m = re.search(r'property="og:image" content="([^"]+)"', html)
        if m: pic_url = m.group(1).replace("&amp;", "&")
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
