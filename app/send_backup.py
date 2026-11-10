"""Send a file to the bot owner (daily backup delivery).

Runs inside the bot container, where the local Bot API server and the
BOT_TOKEN env are available:

    python -m app.send_backup <path> [caption]

Uses sender.send_document_file (local Bot API: no 50MB cloud cap).
Exits 0 only when Telegram returns a message id.
"""
import sys
from pathlib import Path

from .sender import send_document_file

OWNER_ID = 7688899559


def main(argv):
    if len(argv) < 2:
        print("usage: python -m app.send_backup <path> [caption]", file=sys.stderr)
        return 2
    path = Path(argv[1])
    caption = argv[2] if len(argv) > 2 else path.name
    res = send_document_file(OWNER_ID, path, caption)
    mid = (res.get("result") or {}).get("message_id")
    print(f"sent {path.name} -> message_id {mid}")
    return 0 if mid else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
