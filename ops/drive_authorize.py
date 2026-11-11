#!/usr/bin/env python3
"""One-time Google Drive user-OAuth setup for the backup uploader.

A service account cannot own files in a personal My Drive (Google 403
storageQuotaExceeded), so uploads run as the user instead. Two steps —
the second needs an authorization code from the user:

    drive_authorize.py --auth-url   # prints the Google authorization URL
    drive_authorize.py --code CODE  # exchanges it, writes the token file

- Client config: /opt/ffl-secrets/drive-oauth-client.json
  {"client_id": "...", "client_secret": "..."} (a Desktop-app OAuth client
  in the file-from-link-backup Cloud project; redirect http://localhost:8080).
- Token file: /opt/ffl-secrets/drive-user-token.json (mode 600), the
  authorized-user file ops/drive_upload.py reads (refresh token inside).
- The user opens the URL, signs in as rzashakeri@gmail.com, authorizes the
  drive.file scope, and copies the code from the redirect URL — the
  localhost page itself will not load, the code is in the address bar.
  The code is passed as an argv, never typed at an interactive prompt.
- The OAuth consent screen must be PUBLISHED (production), not in Testing,
  or the refresh token expires after 7 days. Owner-only use needs no
  verification.

Requires google-auth-oauthlib in /opt/ffl-drive/venv.
"""
import json
import os
import sys
from pathlib import Path

CLIENT_PATH = Path(os.environ.get(
    "FFL_DRIVE_OAUTH_CLIENT", "/opt/ffl-secrets/drive-oauth-client.json"))
TOKEN_PATH = Path(os.environ.get(
    "FFL_DRIVE_USER_TOKEN", "/opt/ffl-secrets/drive-user-token.json"))
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
REDIRECT_URI = "http://localhost:8080/"


def load_client_config():
    if not CLIENT_PATH.exists():
        raise FileNotFoundError(f"oauth client config not found: {CLIENT_PATH}")
    cfg = json.loads(CLIENT_PATH.read_text())
    return cfg


def make_flow(cfg):
    from google_auth_oauthlib.flow import InstalledAppFlow
    client_config = {"installed": {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "auth_uri": cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
        "token_uri": cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        "redirect_uris": [REDIRECT_URI]}}
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    flow.redirect_uri = REDIRECT_URI
    return flow


def auth_url() -> str:
    flow = make_flow(load_client_config())
    url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return url


def exchange(code: str) -> Path:
    cfg = load_client_config()
    flow = make_flow(cfg)
    flow.fetch_token(code=code)
    creds = flow.credentials
    token = {"client_id": cfg["client_id"],
             "client_secret": cfg["client_secret"],
             "refresh_token": creds.refresh_token,
             "type": "authorized_user"}
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token))
    os.chmod(TOKEN_PATH, 0o600)
    return TOKEN_PATH


def main(argv) -> int:
    if len(argv) == 2 and argv[1] == "--auth-url":
        try:
            print(auth_url())
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 2
        return 0
    if len(argv) == 3 and argv[1] == "--code":
        try:
            path = exchange(argv[2])
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"TOKEN_SAVED={path}")
        return 0
    print("usage: drive_authorize.py --auth-url | --code CODE", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
