"""Pure Instagram profile-picture URL helpers (no network, unit-testable).

Instagram serves profile pictures through its CDN with a size segment in
the path (e.g. .../s320x320/...). The HD variant is the same object at
s1080x1080 — when an API only hands us the small URL, rewriting the
segment is the cheapest upgrade. It does not always work (some pictures
were only ever stored small, and Instagram has retired the trick for
some endpoints), so callers must treat the rewritten URL as a candidate
to try, not a guarantee."""
import re
_HD_SIZE = "s1080x1080"
_SIZE_RE = re.compile(r"s\d+x\d+")
def upscale_cdn_url(url: str) -> str:
    """Rewrite every CDN size token to s1080x1080; unchanged when absent."""
    if not url: return url
    return _SIZE_RE.sub(_HD_SIZE, url)
def pick_pic_url(user: dict) -> str | None:
    """web_profile_info user object -> best pic URL (HD preferred)."""
    if not isinstance(user, dict): return None
    return user.get("profile_pic_url_hd") or user.get("profile_pic_url")
def hd_info_url(user: dict) -> str | None:
    """users/{id}/info user object -> HD pic URL."""
    if not isinstance(user, dict): return None
    hd = user.get("hd_profile_pic_url_info")
    if isinstance(hd, dict) and hd.get("url"): return hd["url"]
    return user.get("profile_pic_url")
