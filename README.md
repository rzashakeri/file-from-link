# File From Link — Telegram Downloader Bot (@FileFromLinkBot)

Download videos/audio from **1,700+ sites** (YouTube, Instagram, TikTok, X, SoundCloud, Vimeo, … — everything [yt-dlp](https://github.com/yt-dlp/yt-dlp) supports) through a Telegram bot, with a proper **job queue**, running on **AWS EC2**.

**فارسی:** راهنمای کامل دیپلوی قدم‌به‌قدم → [DEPLOY.fa.md](DEPLOY.fa.md)

## Architecture

```
                 ┌──────────────────────────────────────────────┐
 Link in chat ──►│ Front (pick ONE)                             │
                 │  A) app/bot.py on EC2 (long-polling) [default]│
                 │  B) serverless/ Telegram Serverless (V8)     │
                 └───────────────┬──────────────────────────────┘
                                 │ POST /jobs  (X-API-Secret)
                                 ▼
                 ┌──────────────────────────────────────────────┐
                 │ EC2 engine                                   │
                 │  FastAPI (app/api.py) ─► Redis queue (RQ)    │
                 │  Workers (app/worker.py, scalable)           │
                 │    └► yt-dlp + ffmpeg ─► file                │
                 │         ├─ ≤49MB ─► sendVideo/sendDocument   │
                 │         └─ >49MB ─► S3 presigned link         │
                 │                    or /files/<token>/ link   │
                 └──────────────────────────────────────────────┘
```

**Why not Serverless-only?** Telegram Serverless runs plain JS in a V8 isolate:
no Python, no npm packages, no ffmpeg, fetch responses capped at 30 MB
([docs](https://core.telegram.org/bots/serverless)). yt-dlp *cannot* run there.
Serverless is used here only as an optional instant front-end; all downloading
happens on EC2.

## Quick start (EC2, Mode A)

```bash
git clone https://github.com/rzashakeri/file-from-link.git
cd file-from-link
cp .env.example .env   # fill BOT_TOKEN + API_SECRET
docker compose up -d --build
docker compose logs -f bot worker
```

Full guide (AWS account → EC2 → Security Group → HTTPS → Serverless mode):
[DEPLOY.fa.md](DEPLOY.fa.md)

## Features
- Quality picker: Best / 720p / 480p / Audio-MP3 (inline keyboard)
- Redis + RQ queue: concurrent jobs are queued, position shown to the user
- Per-user limit (default 3 active jobs), job timeout (default 30 min)
- Progress edits on the status message (download %)
- >50 MB handling: S3 presigned URL or self-hosted expiring link
- YouTube cookie support (`YTDLP_COOKIES_FILE`) for "confirm you're not a bot"
- Two fronts, one engine: EC2 bot **or** Telegram Serverless, same `/jobs` API

## Limits (Telegram, not this code)
- Bots upload max **50 MB** per file — larger results are delivered as links.
- Some sites (esp. YouTube from datacenter IPs) require cookies / may rate-limit.
