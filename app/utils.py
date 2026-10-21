import re
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
def extract_urls(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in URL_RE.findall(text or "")]
FORMAT_ORDER = ["best", "720", "480", "audio", "audiolow"]
FORMATS = {
  "best": "bv*+ba/best",
  "720": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/best",
  "480": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/best",
  "audio": "ba/bestaudio/best",
  "audiolow": "ba/bestaudio/best",
}
def format_selector(choice: str) -> str:
    if choice in FORMATS: return FORMATS[choice]
    if choice.startswith("h") and choice[1:].isdigit():
        h = int(choice[1:])
        return f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/best"
    return FORMATS["best"]

import re
_IG_RESERVED = {"p", "reel", "reels", "stories", "explore", "accounts", "tv", "highlights", "direct"}
def ig_profile_username(url: str):
    m = re.match(r"https?://(www\.)?instagram\.com/([A-Za-z0-9._]+)/?(\?.*)?(#.*)?$", url.strip())
    if not m: return None
    u = m.group(2)
    return None if u.lower() in _IG_RESERVED else u
def is_ig_story(url: str) -> bool:
    return "instagram.com/stories/" in url or "instagram.com/highlights/" in url
def is_spotify(url: str) -> bool:
    return "spotify.com/" in url
def is_apple_music(url: str) -> bool:
    return "music.apple.com/" in url
