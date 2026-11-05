"""GitHub releases: repo links -> release picker -> asset picker -> file.

No token: the public REST API (60 req/hour per IP, unauthenticated) with
a short in-memory cache, and the public releases HTML pages as fallback
when the API is rate-limited. Downloads use the asset's
browser_download_url (a plain redirect to the release object store),
so no API quota is spent on the file itself. yt-dlp is never involved:
it has no GitHub-releases extractor, which is exactly why release links
used to fall back to the meaningless video-quality picker.
"""
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .config import DOWNLOAD_DIR, MAX_FILE_BYTES


class GitHubError(Exception):
    pass


API = "https://api.github.com"
UA = {"User-Agent": "FileFromLinkBot", "Accept": "application/vnd.github+json"}
_CACHE: dict[tuple[str, str], tuple[float, list]] = {}
_CACHE_TTL = 600  # seconds: releases change rarely, quota is precious

_RELEASE_RE = re.compile(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/(.*))?$", re.I)
_RAW_RE = re.compile(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)$", re.I)


def is_github(url: str) -> bool:
    return "github.com/" in (url or "") or "raw.githubusercontent.com/" in (url or "")


def parse_github_url(url: str) -> dict:
    """Kinds: repo | releases | release | asset | archive | raw | blob | other.
    'other' (issues, PRs, blob-list pages...) falls through to the normal
    yt-dlp flow, which fails with its own error as before."""
    u = (url or "").strip()
    m = _RAW_RE.match(u)
    if m:
        return {"kind": "raw", "owner": m.group(1), "repo": m.group(2),
                "ref": m.group(3), "path": m.group(4)}
    m = _RELEASE_RE.match(u)
    if not m:
        return {"kind": "other"}
    owner, repo = m.group(1), m.group(2)
    rest = (m.group(3) or "").strip("/")
    if not rest:
        return {"kind": "repo", "owner": owner, "repo": repo}
    parts = rest.split("/")
    if parts[0] == "releases":
        if len(parts) == 1:
            return {"kind": "releases", "owner": owner, "repo": repo}
        if len(parts) >= 3 and parts[1] == "tag":
            return {"kind": "release", "owner": owner, "repo": repo, "tag": parts[2]}
        if len(parts) >= 4 and parts[1] == "download":
            return {"kind": "asset", "owner": owner, "repo": repo,
                    "tag": parts[2], "asset": "/".join(parts[3:])}
        return {"kind": "releases", "owner": owner, "repo": repo}
    if parts[0] == "archive":
        return {"kind": "archive", "owner": owner, "repo": repo}
    if parts[0] == "blob" and len(parts) >= 3:
        return {"kind": "blob", "owner": owner, "repo": repo,
                "ref": parts[1], "path": "/".join(parts[2:])}
    return {"kind": "other", "owner": owner, "repo": repo}


def _api_get(path: str):
    with httpx.Client(timeout=20, follow_redirects=True, headers=UA) as client:
        r = client.get(f"{API}{path}")
    if r.status_code == 404:
        raise GitHubError("repo not found")
    if r.status_code == 403:
        raise GitHubError("rate limited")
    if r.status_code != 200:
        raise GitHubError("github unavailable")
    return r.json()


def _rel(d: dict) -> dict:
    return {"tag": d.get("tag_name") or "", "name": d.get("name") or d.get("tag_name") or "",
            "published_at": d.get("published_at"),
            "assets": [{"name": a.get("name") or "", "size": a.get("size") or 0,
                        "url": a.get("browser_download_url") or ""}
                       for a in (d.get("assets") or []) if a.get("browser_download_url")]}


def _html_tags(owner: str, repo: str) -> list:
    """Fallback when the API is rate-limited: the public releases page
    lists every release as a /releases/tag/<tag> link, newest first."""
    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = client.get(f"https://github.com/{owner}/{repo}/releases")
    if r.status_code == 404:
        raise GitHubError("repo not found")
    if r.status_code != 200:
        raise GitHubError("github unavailable")
    seen, tags = set(), []
    for tag in re.findall(r"/%s/%s/releases/tag/([^\"'/?#]+)" % (re.escape(owner), re.escape(repo)), r.text):
        tag = unquote(tag)
        if tag not in seen:
            seen.add(tag); tags.append(tag)
    return [{"tag": t, "name": t, "published_at": None, "assets": []} for t in tags]


def _html_assets(owner: str, repo: str, tag: str) -> list:
    """Fallback for one release's assets: the tag page carries every
    asset as a /releases/download/<tag>/<file> link."""
    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = client.get(f"https://github.com/{owner}/{repo}/releases/tag/{tag}")
    if r.status_code == 404:
        raise GitHubError("repo not found")
    if r.status_code != 200:
        raise GitHubError("github unavailable")
    seen, assets = set(), []
    pat = r"/%s/%s/releases/download/%s/([^\"'/?#]+)" % (
        re.escape(owner), re.escape(repo), re.escape(tag))
    for name in re.findall(pat, r.text):
        name = unquote(name)
        if name not in seen:
            seen.add(name)
            assets.append({"name": name, "size": 0,
                           "url": f"https://github.com/{owner}/{repo}/releases/download/{tag}/{name}"})
    return assets


def list_releases(owner: str, repo: str) -> list:
    """Newest first. API first (cached 10 min); the public releases HTML
    page as fallback when the API is rate-limited or down."""
    key = (owner.lower(), repo.lower())
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        rels = [_rel(d) for d in _api_get(f"/repos/{owner}/{repo}/releases?per_page=10")]
    except GitHubError as e:
        if str(e) in ("rate limited", "github unavailable"):
            rels = _html_tags(owner, repo)
        else:
            raise
    _CACHE[key] = (time.time(), rels)
    return rels


def get_release(owner: str, repo: str, tag: str) -> dict:
    """One release with its assets. Prefers the cached list; the tag
    page HTML is the fallback when the API is rate-limited."""
    for rel in list_releases(owner, repo):
        if rel["tag"] == tag:
            if rel["assets"]:
                return rel
            break
    try:
        rel = _rel(_api_get(f"/repos/{owner}/{repo}/releases/tags/{tag}"))
        if rel["assets"]:
            return rel
    except GitHubError as e:
        if str(e) not in ("rate limited", "github unavailable"):
            raise
    assets = _html_assets(owner, repo, tag)
    return {"tag": tag, "name": tag, "published_at": None, "assets": assets}


def _to_direct_download_url(url: str) -> str:
    """Blob pages are not files — rewrite them to the raw file URL.
    Asset / archive / raw URLs already point at the file itself."""
    parsed = parse_github_url(url)
    if parsed.get("kind") == "blob":
        return ("https://raw.githubusercontent.com/%s/%s/%s/%s"
                % (parsed["owner"], parsed["repo"], parsed["ref"], parsed["path"]))
    return url


def _safe_filename(name: str, fallback: str) -> str:
    name = (name or "").strip().replace("/", "_").replace("\\", "_").strip(".")
    if not name or name in (".", ".."):
        return fallback
    return name[:120]


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    return unquote(path.rsplit("/", 1)[-1]) if "/" in path else ""


def download_asset(url: str, job_id: str, on_progress=None):
    """Plain streaming HTTP download of a release asset (or archive/raw
    file). The browser_download_url redirects to the release object
    store, so follow_redirects is essential. Returns (path, meta) like
    the yt-dlp download path, so tasks.py delivers it unchanged."""
    url = _to_direct_download_url(url)
    dest = Path(DOWNLOAD_DIR / job_id)
    dest.mkdir(parents=True, exist_ok=True)
    name = _safe_filename(_filename_from_url(url), "github-file")
    fp = dest / name
    with httpx.Client(timeout=300, follow_redirects=True,
                      headers={"User-Agent": "FileFromLinkBot"}) as client:
        with client.stream("GET", url) as r:
            if r.status_code == 404:
                raise GitHubError("file not found (the release asset was removed?)")
            if r.status_code in (401, 403):
                raise GitHubError("github refused the download")
            r.raise_for_status()
            size = int(r.headers.get("content-length") or 0)
            if size and size > MAX_FILE_BYTES:
                raise GitHubError("file larger than the 1.9 GB limit")
            cd = r.headers.get("content-disposition") or ""
            m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", cd)
            if m:
                fp = dest / _safe_filename(unquote(m.group(1)), name)
            written = 0
            with open(fp, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
                    written += len(chunk)
                    if written > MAX_FILE_BYTES:
                        raise GitHubError("file larger than the 1.9 GB limit")
                    if on_progress and size:
                        on_progress(written, size)
    if fp.stat().st_size < 1:
        raise GitHubError("downloaded an empty file")
    return fp, {"title": fp.name, "duration": None, "extractor": "GitHub",
                "description": "", "subtitles": [], "files": [str(fp)]}
