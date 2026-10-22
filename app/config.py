import os
from pathlib import Path
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_SECRET = os.environ.get("API_SECRET","change-me")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL","").rstrip("/")
REDIS_URL = os.environ.get("REDIS_URL","redis://localhost:6379/0")
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH","./jobs.db"))
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR","./downloads"))
PUBLIC_DIR = Path(os.environ.get("PUBLIC_DIR","./public"))
TELEGRAM_LIMIT = int(os.environ.get("TELEGRAM_UPLOAD_LIMIT_MB","49"))*1024*1024
MAX_JOBS_PER_USER = int(os.environ.get("MAX_JOBS_PER_USER","3"))
JOB_TIMEOUT = int(os.environ.get("JOB_TIMEOUT_SECONDS","1200"))
FILE_TTL_HOURS = int(os.environ.get("FILE_TTL_HOURS","24"))
S3_BUCKET = os.environ.get("S3_BUCKET","")
AWS_REGION = os.environ.get("AWS_REGION","eu-central-1")
COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE","")
IG_COOKIES_FILE = os.environ.get("IG_COOKIES_FILE","")
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", str(1024*1024*1024)))  # 1 GiB cap (Reza, 2026-10-21)
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # only this Telegram user may use /stats
POT_BASE_URL = os.environ.get("POT_BASE_URL", "http://pot-provider:4416")
PROXY = os.environ.get("YTDLP_PROXY", "")
for d in (DOWNLOAD_DIR, PUBLIC_DIR): d.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
