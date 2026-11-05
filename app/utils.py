import re
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
def extract_urls(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in URL_RE.findall(text or "")]
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "avif", "bmp", "heic", "heif", "tif", "tiff"}
AUDIO_EXTS = {"mp3", "m4a", "aac", "ogg", "oga", "opus", "flac", "wav", "wma", "aiff"}
# Direct downloadable files that are neither photo nor audio: no quality
# picker applies to them at all (the bot just downloads the file).
FILE_EXTS = {"apk", "zip", "tar", "gz", "tgz", "bz2", "xz", "rar", "7z",
             "pdf", "epub", "mobi", "exe", "msi", "dmg", "pkg", "iso", "img",
             "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "json",
             "csv", "ttf", "otf", "torrent"}
def url_extension(url: str) -> str:
    from urllib.parse import urlparse
    name = (urlparse(url or "").path or "").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""
def classify_url(url: str) -> str | None:
    """Media kind of a direct file link, from its extension only.
    Returns 'photo' | 'audio' | 'file', or None when the URL carries no
    telling extension (page links need a probe instead)."""
    ext = url_extension(url)
    if ext in IMAGE_EXTS: return "photo"
    if ext in AUDIO_EXTS: return "audio"
    if ext in FILE_EXTS: return "file"
    return None
FORMAT_ORDER = ["best", "720", "480", "audiohq", "audio", "audiolow"]
FORMATS = {
  "best": "bv*+ba/best",
  # Trailing /best: on photo-only media the video alternatives match
  # nothing, so the picker/download degrades to the best image instead
  # of failing with "requested format is not available".
  "720": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/best/best",
  "480": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/best/best",
  "audiohq": "ba/bestaudio/best",
  "audio": "ba/bestaudio/best",
  "audiolow": "ba/bestaudio/best",
  "photo": "best",
  "audioorig": "best",
}
def format_selector(choice: str) -> str:
    if choice in FORMATS: return FORMATS[choice]
    if choice.startswith("h") and choice[1:].isdigit():
        h = int(choice[1:])
        return f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/best"
    if choice.startswith("img") and choice[3:].isdigit():
        # Photo size row: best image at or below this height, else the
        # largest image the source offers.
        h = int(choice[3:])
        return f"best[height<={h}]/best"
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
