"""yt-dlp wrapper: 1,700+ extractors (YouTube, Instagram, TikTok, X, ...).

YouTube from datacenter IPs often hits "Sign in to confirm you're not a bot".
Mitigations built in, tried in order:
  1. PO Tokens from the bgutil provider sidecar (docker service pot-provider)
     via the bgutil-ytdlp-pot-provider plugin.
  2. Optional cookies file (YTDLP_COOKIES_FILE) — used only if the file exists.
  3. Fallback player clients (tv, web_safari, ios) retried automatically.
"""
from pathlib import Path
import yt_dlp
from .config import DOWNLOAD_DIR, COOKIES_FILE, IG_COOKIES_FILE, X_COOKIES_FILE, JOB_TIMEOUT, POT_BASE_URL, PROXY, MAX_FILE_BYTES
from .utils import format_selector, is_spotify, is_apple_music
class DownloadError(Exception): pass
BOT_WALL_MARKERS = ("not a bot", "sign in to confirm", "po token", "potoken", "needs to be reloaded", "requested format is not available")
FALLBACK_CLIENTS = ["tv", "ios", "web_safari"]
def _build_opts(choice, job_id, on_progress, player_client=None, url: str = ''):
    out = str(DOWNLOAD_DIR / job_id / "%(title).80s.%(ext)s")
    def hook(d):
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            on_progress(d.get("downloaded_bytes", 0), total)
    opts = {
        "format": format_selector(choice), "outtmpl": out, "noplaylist": True,
        "progress_hooks": [hook], "socket_timeout": 30, "retries": 3,
        "merge_output_format": "mp4", "quiet": True, "no_warnings": True, "max_filesize": MAX_FILE_BYTES,
        "extractor_args": {"youtubepot-bgutilhttp": {"base_url": [POT_BASE_URL]}},
    }
    if PROXY:
        opts["proxy"] = PROXY
    if player_client:
        opts["extractor_args"]["youtube"] = {"player_client": [player_client]}
    if "instagram.com" in url and IG_COOKIES_FILE and Path(IG_COOKIES_FILE).exists():
        opts["cookiefile"] = IG_COOKIES_FILE
    elif ("x.com" in url or "twitter.com" in url) and X_COOKIES_FILE and Path(X_COOKIES_FILE).exists():
        opts["cookiefile"] = X_COOKIES_FILE
    elif COOKIES_FILE and Path(COOKIES_FILE).exists():
        opts["cookiefile"] = COOKIES_FILE
    if choice in ("audiohq", "audio", "audiolow"):
        q = {"audiohq": "320", "audio": "192", "audiolow": "48"}[choice]
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": q}]
    return opts
def _aparat_resolve(url: str):
    """yt-dlp's Aparat extractor is broken against Aparat's current pages
    ('Unable to extract og:title' from the embed page). The WATCH page still
    carries og:title and direct .mp4 sources — resolve those ourselves and
    hand yt-dlp the direct file URL."""
    import httpx, re as _re
    html = httpx.get(url, timeout=25, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}).text
    m = _re.search(r'property="og:title" content="([^"]+)"', html)
    title = m.group(1) if m else None
    cands = {}
    for u in _re.findall(r'https://[^"\'\\ ]+?\.mp4[^"\'\\ ]*', html):
        u = u.replace("&amp;", "&")
        q = _re.search(r'(\d{3,4})p', u)
        key = int(q.group(1)) if q else 0
        if key >= cands.get("q", -1):
            cands = {"q": key, "url": u}
    if not cands.get("url"): return None
    return cands["url"], title
def _fetch_subtitles(url, job_id, player_client=None):
    """Best-effort subtitle grab (fa/en incl. auto-captions), isolated from
    the media download: a subtitle 429 must NEVER fail the whole job
    (regression found live 2026-10-22 on the features deploy)."""
    try:
        opts = _build_opts("best", job_id, None, player_client, url)
        opts.update({"skip_download": True, "writesubtitles": True, "writeautomaticsub": True,
                     "subtitleslangs": ["fa.*", "en.*"], "subtitlesformat": "srt/vtt/best",
                     "retries": 1, "socket_timeout": 15})
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception:
        pass

def _extract_once(url, choice, job_id, on_progress, player_client=None):
    opts = _build_opts(choice, job_id, on_progress, player_client, url)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
        if choice in ("audiohq", "audio", "audiolow"): path = path.with_suffix(".mp3")
        if not path.exists():
            files = sorted((f for f in Path(DOWNLOAD_DIR / job_id).glob("*") if f.suffix.lower() not in (".srt", ".vtt")),
                           key=lambda p: p.stat().st_size, reverse=True)
            if not files: raise DownloadError("no output file")
            path = files[0]
        if choice not in ("audiohq", "audio", "audiolow"):
            _fetch_subtitles(url, job_id, player_client)
        subs = sorted((f for f in Path(DOWNLOAD_DIR / job_id).glob("*")
                       if f.suffix.lower() in (".srt", ".vtt") and f != path),
                      key=lambda f: (f.suffix.lower() != ".srt", f.name))[:2]
        return path, {"title": info.get("title", ""), "duration": info.get("duration"),
                      "extractor": info.get("extractor_key", ""),
                      "description": (info.get("description") or "").strip(),
                      "subtitles": [str(s) for s in subs]}
_IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
def _shortcode_id(code: str) -> int:
    n = 0
    for ch in code: n = n * 64 + _IG_ALPHABET.index(ch)
    return n

def _ig_slide_count(url: str) -> int:
    """Slides in an Instagram post via the media-info API; 0 on any error.
    An all-video carousel fools yt-dlp into downloading only slide 1 (no
    'No video formats found' error), so download() checks this FIRST."""
    import httpx, re as _re
    from .ig import _ig_cookie_header, _UA
    m = _re.search(r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url)
    if not m: return 0
    try:
        headers = {**_UA, "X-IG-App-ID": "936619743392459", **_ig_cookie_header()}
        r = httpx.get(f"https://i.instagram.com/api/v1/media/{_shortcode_id(m.group(1))}/info/",
                      headers=headers, timeout=15, follow_redirects=True)
        items = r.json().get("items") or []
        if not items: return 0
        return len(items[0].get("carousel_media") or [])
    except Exception:
        return 0

def _ig_api_download(url: str, choice: str, job_id: str, on_progress=None):
    """Photo posts and carousels: yt-dlp's Instagram extractor only sees
    videos ('No video formats found!'), but the media-info API (with the
    burner session) returns every slide. Downloads all slides as
    originals; audio choices extract from the first video slide."""
    import httpx, re as _re
    from .ig import _ig_cookie_header, _UA
    m = _re.search(r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url)
    if not m: raise DownloadError("could not parse the Instagram link")
    headers = {**_UA, "X-IG-App-ID": "936619743392459", **_ig_cookie_header()}
    r = httpx.get(f"https://i.instagram.com/api/v1/media/{_shortcode_id(m.group(1))}/info/",
                  headers=headers, timeout=30, follow_redirects=True)
    if r.status_code != 200: raise DownloadError(f"Instagram refused the request ({r.status_code})")
    items = r.json().get("items") or []
    if not items: raise DownloadError("post not found (private or deleted?)")
    item = items[0]
    caption = ((item.get("caption") or {}).get("text") or "").strip()
    title = (caption.split("\n")[0][:80] if caption else "") or (item.get("user") or {}).get("username") or "Instagram post"
    media = []
    for s in (item.get("carousel_media") or [item]):
        if s.get("video_versions"):
            vv = max(s["video_versions"], key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))
            media.append(("video", vv["url"]))
        elif (s.get("image_versions2") or {}).get("candidates"):
            media.append(("image", s["image_versions2"]["candidates"][0]["url"]))
    if not media: raise DownloadError("no media found in this post")
    if choice in ("audiohq", "audio", "audiolow"):
        vids = [u for k, u in media if k == "video"]
        if not vids: raise DownloadError("This post has no video to extract audio from.")
        return _extract_once(vids[0], choice, job_id, on_progress, None)
    dest = Path(DOWNLOAD_DIR / job_id); dest.mkdir(parents=True, exist_ok=True)
    files = []
    media = media[:10]
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        for i, (kind, mu) in enumerate(media, 1):
            fp = dest / f"slide_{i:02d}{'.mp4' if kind == 'video' else '.jpg'}"
            with client.stream("GET", mu, headers=_UA) as resp:
                resp.raise_for_status()
                with open(fp, "wb") as f:
                    for chunk in resp.iter_bytes(1 << 16): f.write(chunk)
            files.append(fp)
            if on_progress: on_progress(i, len(media))
    return files[0], {"title": title, "duration": None, "extractor": "InstagramAPI",
                      "description": caption, "subtitles": [], "files": [str(f) for f in files]}

def download(url: str, choice: str, job_id: str, on_progress=None) -> tuple[Path, dict]:
    Path(DOWNLOAD_DIR / job_id).mkdir(parents=True, exist_ok=True)
    if "instagram.com" in url and "/p/" in url and _ig_slide_count(url) > 1:
        return _ig_api_download(url, choice, job_id, on_progress)
    try:
        return _download_ytdlp(url, choice, job_id, on_progress)
    except DownloadError as e:
        if "instagram.com" in url and "No video formats found" in str(e):
            return _ig_api_download(url, choice, job_id, on_progress)
        raise

def _download_ytdlp(url: str, choice: str, job_id: str, on_progress=None) -> tuple[Path, dict]:
    attempts = [None] + FALLBACK_CLIENTS if "youtu" in url else [None]
    last_error = None
    for client in attempts:
        try:
            return _extract_once(url, choice, job_id, on_progress, client)
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            msg = str(e).lower()
            if client is not attempts[-1] and any(m in msg for m in BOT_WALL_MARKERS):
                continue  # bot wall -> try the next player client
            raise DownloadError(str(e)[:500]) from e
    raise DownloadError("This file is larger than the 1 GB limit."
                        if last_error and ("max-filesize" in str(last_error) or "larger than" in str(last_error))
                        else (str(last_error)[:500] if last_error else "download failed"))

def get_direct_url(url: str, choice: str) -> str | None:
    """Best-effort fresh direct stream URL from the source (signed, expiring,
    often bound to THIS server's IP — a convenience link, not a guarantee)."""
    attempts = [None] + FALLBACK_CLIENTS if "youtu" in url else [None]
    for client in attempts:
        try:
            opts = _build_opts(choice, "urlprobe", None, client, url)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info.get("url"): return info["url"]
            for f in info.get("requested_formats") or []:
                if f.get("url") and f.get("vcodec") not in (None, "none"): return f["url"]
            return None
        except yt_dlp.utils.DownloadError as e:
            if client is not attempts[-1] and any(m in str(e).lower() for m in BOT_WALL_MARKERS): continue
            return None
    return None

def _est_size(f: dict, duration: float) -> float:
    if f.get("filesize"): return float(f["filesize"])
    if f.get("filesize_approx"): return float(f["filesize_approx"])
    if f.get("tbr") and duration: return float(f["tbr"]) * 1000 / 8 * duration
    return 0.0

def _aggregate(info, heights: dict) -> None:
    fmts = info.get("formats") or []
    dur = float(info.get("duration") or 0)
    aud = max((_est_size(f, dur) for f in fmts
               if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")), default=0.0)
    for f in fmts:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none", "images"): continue
        if str(f.get("format_id", "")).startswith("sb"): continue
        total = _est_size(f, dur) + (aud if f.get("acodec") in (None, "none") else 0.0)
        if total > heights.get(h, 0): heights[h] = total

def _to_quality_list(heights: dict) -> list[dict]:
    return [{"height": h, "mb": (heights[h] / 1048576) if heights[h] else None}
            for h in sorted(heights, reverse=True)]

def list_qualities_generic(url: str) -> list[dict]:
    """Single quick probe for non-YouTube sources (Instagram, TikTok, X, ...).
    Returns [] when the site will not describe its formats — the caller then
    falls back to the static quality list."""
    opts = _build_opts("best", "probe", None, None, url)
    opts.pop("writesubtitles", None); opts.pop("writeautomaticsub", None)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    heights: dict[int, float] = {}
    _aggregate(info, heights)
    return _to_quality_list(heights)

def list_qualities(url: str) -> list[dict]:
    """Real downloadable resolutions for THIS video (union across the player
    clients that answer), each with an approximate total size in MB."""
    heights: dict[int, float] = {}
    last_err: Exception | None = None
    for client in [None] + FALLBACK_CLIENTS:
        try:
            opts = _build_opts("best", "probe", None, client, url)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            last_err = e; continue
        fmts = info.get("formats") or []
        dur = float(info.get("duration") or 0)
        aud = max((_est_size(f, dur) for f in fmts
                   if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")), default=0.0)
        for f in fmts:
            h = f.get("height")
            if not h or f.get("vcodec") in (None, "none", "images"): continue
            if str(f.get("format_id", "")).startswith("sb"): continue
            total = _est_size(f, dur) + (aud if f.get("acodec") in (None, "none") else 0.0)
            if total > heights.get(h, 0): heights[h] = total
    if not heights and last_err: raise last_err
    return [{"height": h, "mb": (heights[h] / 1048576) if heights[h] else None}
            for h in sorted(heights, reverse=True)]

def _spotify_query(url: str) -> str:
    import httpx
    r = httpx.get("https://open.spotify.com/oembed", params={"url": url}, timeout=20, follow_redirects=True)
    r.raise_for_status(); d = r.json()
    return f"{d.get('title','')} {d.get('author_name','')}".strip()
def _apple_query(url: str) -> str:
    import httpx, json as _json, re as _re
    html = httpx.get(url, timeout=20, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}).text
    for m in _re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, _re.S):
        try: data = _json.loads(m.group(1))
        except Exception: continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("@type") in ("MusicRecording", "MusicAlbum"):
                name = it.get("name", "")
                artist = ((it.get("byArtist") or {}).get("name") if isinstance(it.get("byArtist"), dict) else "") or ""
                if name: return f"{name} {artist}".strip()
    m = _re.search(r"<title>(.*?)</title>", html, _re.S)
    if m:
        title = m.group(1).replace(" – Apple Music", "").replace(" - Apple Music", "").strip()
        title = _re.sub(r"\s+", " ", title)
        if title: return title
    return ""
def resolve_stream_match(url: str) -> str:
    """Spotify / Apple Music links are DRM-locked — no direct download exists.
    Standard bot approach: identify the track, download the same track from YouTube."""
    try:
        q = _spotify_query(url) if is_spotify(url) else _apple_query(url)
    except Exception:
        q = ""
    if not q: raise DownloadError("could not read the track info from that link")
    info, last_err = None, None
    for client in [None] + FALLBACK_CLIENTS:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "extractor_args": {"youtubepot-bgutilhttp": {"base_url": [POT_BASE_URL]}}}
        if PROXY: opts["proxy"] = PROXY
        if COOKIES_FILE and Path(COOKIES_FILE).exists(): opts["cookiefile"] = COOKIES_FILE
        if client: opts["extractor_args"]["youtube"] = {"player_client": [client]}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{q} audio", download=False)
            break
        except Exception as e:
            last_err = e; continue
    if info is None: raise DownloadError(str(last_err)[:200] if last_err else "YouTube search failed")
    entries = info.get("entries") or []
    if not entries: raise DownloadError("no matching track found on YouTube")
    e = entries[0]
    return e.get("webpage_url") or f"https://www.youtube.com/watch?v={e['id']}"
