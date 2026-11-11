#!/usr/bin/env python3
"""Upload a backup archive to Google Drive.

Runs on the EC2 host after ops/daily_backup.py builds the archive:
    /opt/ffl-drive/venv/bin/python3 ops/drive_upload.py <archive> <sha256>

Credentials — user OAuth FIRST (a service account cannot own files in a
personal My Drive; Google returns 403 storageQuotaExceeded):
- User token: /opt/ffl-secrets/drive-user-token.json (authorized-user file
  with client_id, client_secret, refresh_token), created once by
  ops/drive_authorize.py. Files are owned by the user, in the user's quota.
- Fallback: a Google service account key at /opt/ffl-secrets/drive-sa.json
  (only works with a Shared Drive / Workspace).
- Destination folder: /opt/ffl-secrets/drive-folder-id.txt (one line).
- Sets the Drive file description to the sha256 so the download side can
  verify integrity. Trashes folder files older than 7 days (keeps the
  newest), so Drive holds the same 7-day window as the server.
- Exits 0 on success and prints FILE_ID=<id>; exits 2 when no credentials
  or the folder config is missing. Google library imports are lazy, so the
  module imports (and its config checks run) without the libs installed.

Requires google-api-python-client + google-auth in a venv:
    python3 -m venv /opt/ffl-drive/venv
    /opt/ffl-drive/venv/bin/pip install google-api-python-client
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEY_PATH = Path(os.environ.get("FFL_DRIVE_SA_KEY", "/opt/ffl-secrets/drive-sa.json"))
USER_TOKEN_PATH = Path(os.environ.get("FFL_DRIVE_USER_TOKEN", "/opt/ffl-secrets/drive-user-token.json"))
FOLDER_ID_PATH = Path(os.environ.get("FFL_DRIVE_FOLDER_ID_FILE", "/opt/ffl-secrets/drive-folder-id.txt"))
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
RETENTION_DAYS = int(os.environ.get("FFL_RETENTION_DAYS", "7"))


def read_folder_id() -> str:
    if os.environ.get("FFL_DRIVE_FOLDER_ID"):
        return os.environ["FFL_DRIVE_FOLDER_ID"].strip()
    if FOLDER_ID_PATH.exists():
        return FOLDER_ID_PATH.read_text().strip()
    return ""


def parse_time(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def select_prune(files: list, days: int, now: datetime | None = None) -> list:
    """Files (dicts with id/name/modifiedTime) to trash: older than `days`,
    never the newest one. Pure function, unit-tested."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    ordered = sorted(files, key=lambda f: parse_time(f["modifiedTime"]))
    return [f for f in ordered[:-1]
            if parse_time(f["modifiedTime"]) < cutoff]


def load_credentials():
    """User OAuth token first, service-account key as fallback.
    Raises FileNotFoundError when neither exists."""
    if USER_TOKEN_PATH.exists():
        from google.oauth2.credentials import Credentials
        return Credentials.from_authorized_user_file(
            str(USER_TOKEN_PATH), SCOPES)
    if KEY_PATH.exists():
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_file(
            str(KEY_PATH), scopes=SCOPES)
    raise FileNotFoundError(
        f"no drive credentials: {USER_TOKEN_PATH} or {KEY_PATH}")


def build_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=load_credentials())


def upload_archive(service, folder_id: str, archive: Path, sha256: str) -> str:
    from googleapiclient.http import MediaFileUpload
    body = {"name": archive.name, "parents": [folder_id],
            "description": f"sha256:{sha256}"}
    media = MediaFileUpload(str(archive), mimetype="application/gzip",
                            resumable=True)
    res = service.files().create(body=body, media_body=media,
                                 fields="id").execute()
    return res["id"]


def prune_folder(service, folder_id: str, days: int) -> list:
    res = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id,name,modifiedTime)", pageSize=50).execute()
    doomed = select_prune(res.get("files", []), days)
    for f in doomed:
        service.files().update(fileId=f["id"],
                               body={"trashed": True}).execute()
    return [f["name"] for f in doomed]


def main(argv) -> int:
    if len(argv) < 3:
        print("usage: drive_upload.py <archive> <sha256>", file=sys.stderr)
        return 2
    archive, sha256 = Path(argv[1]), argv[2]
    if not USER_TOKEN_PATH.exists() and not KEY_PATH.exists():
        print(f"drive credentials not found: {USER_TOKEN_PATH} or {KEY_PATH}",
              file=sys.stderr)
        return 2
    folder_id = read_folder_id()
    if not folder_id:
        print("drive folder id not configured (FFL_DRIVE_FOLDER_ID or "
              f"{FOLDER_ID_PATH})", file=sys.stderr)
        return 2
    if not archive.exists():
        print(f"archive not found: {archive}", file=sys.stderr)
        return 2
    service = build_service()
    file_id = upload_archive(service, folder_id, archive, sha256)
    print(f"FILE_ID={file_id}")
    pruned = prune_folder(service, folder_id, RETENTION_DAYS)
    if pruned:
        print(f"PRUNED={','.join(pruned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
