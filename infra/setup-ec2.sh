#!/bin/bash
# Run ON the EC2 instance, inside the cloned repo.
set -eux
cd "$(dirname "$0")/.."
[ -f .env ] || { cp .env.example .env; echo ">> .env ساخته شد — BOT_TOKEN و API_SECRET رو ویرایش کن و دوباره اجرا کن"; exit 1; }
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=50 bot worker api
