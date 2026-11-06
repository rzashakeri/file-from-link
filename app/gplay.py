"""Google Play downloads via gplaydl (unofficial Play protobuf API).

Flow: Play link -> package name -> gplaydl library (ensure_auth,
get_details, purchase, get_delivery, download_batch) -> base APK +
split APKs + OBB/asset packs, all SHA-verified by gplaydl itself.

Auth: the server must be linked once (gplaydl link with a code from the
Authenticator app) or carry GPLAYDL_API_KEY in the environment. Until
then every Play download fails with a clear 'not linked' error — the
bot code ships first, the link lands second.

Split APKs are the norm for App Bundle apps: the base APK alone will
not run (native libraries live in the config.<abi> split), so the bot
delivers base + splits together and tells the user to install them as
one session (e.g. with SAI). The install note travels as the job
description, which tasks.py sends after the files.
"""
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .config import DOWNLOAD_DIR, MAX_FILE_BYTES
from .i18n import t as tr


class GooglePlayError(Exception):
    pass


_PKG_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$", re.I)


def is_play_store(url: str) -> bool:
    return extract_package(url) is not None


def extract_package(url: str) -> str | None:
    """Package name of a Play app link, else None. A details page without
    a valid ?id= is not an app link (and neither is an id= on some other
    host)."""
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return None
    if parsed.scheme == "market":
        if (parsed.hostname or "") != "details":
            return None
    else:
        host = (parsed.hostname or "").lower()
        if host not in ("play.google.com", "www.play.google.com"):
            return None
        if "/store/apps/details" not in parsed.path:
            return None
    qs = parse_qs(parsed.query)
    pkg = (qs.get("id") or [None])[0]
    return pkg if pkg and _PKG_RE.match(pkg) else None


def _order_files(paths):
    """Base APK first, then splits, then asset packs, then OBBs last."""
    def key(p):
        n = p.name
        if n.endswith(".obb"):
            return (3, n)
        if "-asset.apk" in n:
            return (2, n)
        if n.count("-") >= 2:
            return (1, n)
        return (0, n)
    return sorted(paths, key=key)


def _specs_for(delivery, package, vc, dest):
    """Mirror the gplaydl CLI naming: base, splits, asset packs, OBBs.
    The .dm metadata file is skipped (not needed to install)."""
    from gplaydl.download import DownloadSpec
    specs = []
    base_name = f"{package}-{vc}.apk"
    use_gzip = bool(delivery.gzipped_url and delivery.gzipped_size)
    specs.append(DownloadSpec(
        url=delivery.gzipped_url if use_gzip else delivery.download_url,
        dest=dest / base_name, cookies=delivery.cookies, label=base_name,
        gzipped=use_gzip, sha256=delivery.sha256, sha1=delivery.sha1))
    for split in (delivery.splits or []):
        name = f"{package}-{vc}-{split.name}.apk"
        use_gzip = bool(split.gzipped_url and split.gzipped_size)
        specs.append(DownloadSpec(
            url=split.gzipped_url if use_gzip else split.url,
            dest=dest / name, label=name, gzipped=use_gzip, sha256=split.sha256))
    for af in (delivery.additional_files or []):
        if af.is_asset_pack:
            name = f"{package}-{vc}-{af.type_label}{af.extension}"
        else:
            name = f"{af.type_label}.{af.version_code}.{package}{af.extension}"
        specs.append(DownloadSpec(
            url=af.url, dest=dest / name, cookies=af.cookies,
            label=name, gzipped=af.gzipped))
    return specs


def _expected_total(delivery) -> int:
    total = delivery.download_size or 0
    total += sum(s.size or 0 for s in (delivery.splits or []))
    total += sum(a.size or 0 for a in (delivery.additional_files or []))
    return total


def download_play_apk(package: str, job_id: str, lang: str = "en", on_progress=None):
    """Download a Play app (base + splits + extras) into the job dir.
    Returns (base_path, meta) like the yt-dlp download path."""
    dest = Path(DOWNLOAD_DIR / job_id)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        import gplaydl.api as _api
        import gplaydl.auth as _auth
        from gplaydl.download import download_batch, DownloadError as _DlErr
    except ImportError:
        raise GooglePlayError("gplaydl is not installed on the server yet")
    auth = _auth.ensure_auth()
    if not auth:
        raise GooglePlayError(tr(lang, "gplay_not_linked"))
    try:
        details = _api.get_details(package, auth)
    except _api.AuthExpiredError:
        auth = _auth.ensure_auth(force_refresh=True)
        if not auth:
            raise GooglePlayError(tr(lang, "gplay_not_linked"))
        details = _api.get_details(package, auth)
    except (_api.AppNotAvailableError, _api.PlayAPIError) as e:
        if "not found" in str(e).lower():
            raise GooglePlayError(tr(lang, "gplay_not_found"))
        raise GooglePlayError(str(e)[:200])
    vc = details.version_code
    try:
        token = _api.purchase(package, vc, auth)
        delivery = _api.get_delivery(package, vc, auth, token, locales=["fa"])
    except _api.AuthExpiredError:
        auth = _auth.ensure_auth(force_refresh=True)
        if not auth:
            raise GooglePlayError(tr(lang, "gplay_not_linked"))
        token = _api.purchase(package, vc, auth)
        delivery = _api.get_delivery(package, vc, auth, token, locales=["fa"])
    except _api.AppNotPurchasedError:
        raise GooglePlayError(tr(lang, "gplay_paid"))
    except _api.AppNotSupportedError:
        raise GooglePlayError(tr(lang, "gplay_not_found"))
    except _api.PlayAPIError as e:
        raise GooglePlayError(str(e)[:200])
    total = _expected_total(delivery)
    if total and total > MAX_FILE_BYTES:
        raise GooglePlayError(tr(lang, "gplay_too_big", mb=total // 1048576))
    specs = _specs_for(delivery, package, vc, dest)
    if not specs:
        raise GooglePlayError(tr(lang, "gplay_not_found"))
    done = 0
    if on_progress and total:
        on_progress(0, total)
    try:
        for spec in specs:
            download_batch([spec])
            if spec.dest.exists():
                done += spec.dest.stat().st_size
            if on_progress and total:
                on_progress(done, total)
    except _DlErr as e:
        raise GooglePlayError(str(e)[:200])
    files = _order_files([s.dest for s in specs if s.dest.exists()])
    if not files:
        raise GooglePlayError(tr(lang, "gplay_not_found"))
    total_on_disk = sum(f.stat().st_size for f in files)
    if total_on_disk > MAX_FILE_BYTES:
        raise GooglePlayError(tr(lang, "gplay_too_big", mb=total_on_disk // 1048576))
    title = (details.title or package) + (f" {details.version_string}" if details.version_string else "")
    return files[0], {"title": title, "duration": None, "extractor": "GooglePlay",
                      "description": tr(lang, "gplay_install_note"),
                      "subtitles": [], "files": [str(f) for f in files]}
