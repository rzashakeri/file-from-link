"""Cleanup of the public file copies used for >50MB link delivery.
The ORIGINAL download is always deleted in tasks.process_job's finally block,
immediately after sending. Only the public copy must survive — the user still
needs time to download it — so it is swept once it is older than the TTL."""
import shutil, time
from pathlib import Path
from .config import PUBLIC_DIR, FILE_TTL_HOURS
def sweep_public(ttl_hours: int = FILE_TTL_HOURS) -> int:
    cutoff = time.time() - ttl_hours * 3600
    removed = 0
    for d in Path(PUBLIC_DIR).glob("*"):
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True); removed += 1
        except OSError:
            pass
    return removed
