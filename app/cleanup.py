"""Cleanup of the public file copies used for >50MB link delivery.
The ORIGINAL download is always deleted in tasks.process_job's finally block,
immediately after sending. Only the public copy must survive — the user still
needs time to download it — so it is swept once it is older than the TTL."""
import os, shutil, time
from pathlib import Path
from .config import PUBLIC_DIR, FILE_TTL_HOURS
def _dir_size(d: Path) -> int:
    total = 0
    for r, _dirs, files in os.walk(d):
        for f in files:
            try: total += os.path.getsize(os.path.join(r, f))
            except OSError: pass
    return total
def sweep_public(ttl_hours: int = FILE_TTL_HOURS) -> int:
    cutoff = time.time() - ttl_hours * 3600
    removed = 0
    dirs = []
    for d in Path(PUBLIC_DIR).glob("*"):
        try:
            if d.is_dir(): dirs.append((d.stat().st_mtime, d))
        except OSError:
            pass
    for mtime, d in dirs:
        if mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True); removed += 1
    # Size budget: with heavy traffic the 24h TTL alone can fill the disk.
    # Keep the public store under MAX_PUBLIC_GB (oldest first) so the
    # service survives launch-night surges; recent links are untouched
    # unless the budget is genuinely exceeded.
    budget = int(os.environ.get("MAX_PUBLIC_GB", "10")) * 1073741824
    live = sorted((m, d) for m, d in dirs if d.exists())
    sizes = {d: _dir_size(d) for _m, d in live}
    total = sum(sizes.values())
    for _m, d in live:
        if total <= budget: break
        total -= sizes[d]
        shutil.rmtree(d, ignore_errors=True); removed += 1
    return removed
