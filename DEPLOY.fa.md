# راهنمای کامل دیپلوی — ربات دانلودر تلگرام (yt-dlp + صف + EC2 + Serverless)

## ۰) معماری نهایی (اول این را بفهم)

| بخش | کجا اجرا می‌شود | چرا |
|---|---|---|
| گرفتن لینک + دکمه کیفیت | **یا** خود EC2 (حالت A، پیش‌فرض) **یا** Telegram Serverless (حالت B) | انتخابی است، هر دو در ریپو هست |
| صف درخواست‌ها | EC2 — Redis + RQ | درخواست همزمان = صف، نوبت به کاربر نشان داده می‌شود |
| دانلود واقعی | EC2 — yt-dlp + ffmpeg | **روی Serverless ممکن نیست**: سرورلس فقط JS روی V8 isolate است، نه Python دارد، نه ffmpeg، نه npm، و پاسخ fetch سقف ۳۰MB دارد ([مستندات رسمی](https://core.telegram.org/bots/serverless)) |
| تحویل فایل | مستقیم در تلگرام تا ۴۹MB؛ بالاتر: لینک S3 یا لینک موقت روی خود EC2 | سقف آپلود بات تلگرام ۵۰MB است — محدودیت تلگرام است، نه کد |

yt-dlp در حال حاضر **۱۷۵۲ extractor** دارد؛ یعنی YouTube, Instagram, TikTok, X, SoundCloud, Vimeo, Twitch و ۱۰۰۰+ سایت دیگر.

---

## ۱) ساخت بات در BotFather
1. در تلگرام `@BotFather` → `/newbot` → اسم و یوزرنیم.
2. **توکن بات** را نگه دار (در قدم ۵ داخل `.env` می‌رود — هرگز داخل گیت/چت نفرست).
3. اگر حالت B (سرورلس) را می‌خواهی: BotFather → بات تو → **Serverless → ON** → **CLI Access → Access token** را هم نگه دار.

## ۲) ساخت EC2 در AWS
1. کنسول AWS → EC2 → **Launch instance**
2. تنظیمات پیشنهادی:
   - **AMI:** Ubuntu Server 24.04 LTS
   - **Instance type:** `t3.small` (شروع، ۲GB رم) — برای چند کاربر همزمان: `t3.medium` (۴GB)
   - **Storage:** ۳۰GB gp3 (ویدیوها موقت‌اند ولی صف شلوغ فضا می‌خواهد)
   - **Region:** `eu-central-1` (فرانکفورت) یا `me-central-1`؛ هرچه به مخاطب و سایت‌های مبدأ نزدیک‌تر بهتر
   - **Key pair:** بساز و فایل `.pem` را امن نگه دار
3. **Security Group (فایروال):**
   - `22/TCP` از IP خودت (SSH)
   - `80/TCP` و `443/TCP` از همه (فقط اگر API/لینک فایل عمومی می‌خواهی — برای حالت B و لینک‌های >۵۰MB لازم است)
   - پورت ۸۰۰۰ را **عمومی نکن**؛ پشت Caddy/nginx روی ۴۴۳ می‌نشیند. در حالت A حتی ۸۰/۴۴۳ هم لازم نیست، مگر برای لینک فایل‌های بزرگ.
4. Launch → **Public IPv4** را یادداشت کن.

> هزینه تقریبی: t3.small همیشه‌روشن ≈ ماهی ۱۵–۱۸ دلار + حجم؛ t3.medium ≈ ۳۰ دلار. (قیمت ریجن‌به‌ریجن فرق می‌کند؛ قبل از لانچ در کنسول چک کن.)

## ۳) نصب Docker روی EC2 (خودکار)
در کنسول، موقع ساخت اینستنس، فایل `infra/ec2-user-data.sh` همین ریپو را در بخش **User data** پیست کن — Docker بعد از اولین بوت نصب است.
یا دستی بعد از SSH:
```bash
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
bash infra/ec2-user-data.sh   # بعد از clone کردن ریپو در قدم بعد، یا خطوطش را دستی اجرا کن
```

## ۴) آوردن کد و تنظیم `.env`
```bash
git clone https://github.com/rzashakeri/file-from-link.git
cd file-from-link
cp .env.example .env
nano .env
```
حتماً این‌ها را پر کن:
```ini
BOT_TOKEN=توکن BotFather
API_SECRET=یک رشته تصادفی بلند (مثلاً خروجی: openssl rand -hex 32)
PUBLIC_BASE_URL=https://dl.example.com   # دامنه‌ات روی EC2 (قدم ۶) — برای لینک فایل‌های بزرگ
```
سقف‌ها (اختیاری): `MAX_JOBS_PER_USER=3` ، `JOB_TIMEOUT_SECONDS=1800` ، `FILE_TTL_HOURS=24`

## ۵) اجرا (حالت A — بات روی خود EC2)
```bash
bash infra/setup-ec2.sh
# یا دستی:
docker compose up -d --build
docker compose ps          # redis, api, bot, worker×2 باید Up باشند
docker compose logs -f bot worker
```
تمام. بات را در تلگرام باز کن، لینک بفرست، کیفیت را انتخاب کن → می‌رود در صف → فایل همینجا می‌آید.
مقیاس صف: ورکر بیشتر = دانلود همزمان بیشتر:
```bash
docker compose up -d --scale worker=4
```

## ۶) HTTPS برای API و لینک‌های بزرگ (لازم برای حالت B و فایل >۵۰MB)
1. در DNS دامنه‌ات یک رکورد **A** به اسم `dl` به IP عمومی EC2 بده.
2. Caddy (ساده‌ترین راه — گواهی خودکار):
```bash
sudo apt install -y caddy   # یا کانتینر Caddy
sudo cp infra/Caddyfile /etc/caddy/Caddyfile   # dl.example.com را با دامنه‌ات عوض کن
sudo systemctl reload caddy
curl https://dl.example.com/health   # باید {"ok":true} بدهد
```

## ۷) تحویل فایل‌های >۵۰MB با S3 (اختیاری ولی تمیزتر از لینک EC2)
1. AWS → S3 → ساخت باکت (خصوصی، همان ریجن EC2).
2. برای EC2 یک **IAM Role** با دسترسی فقط به همان باکت بساز و به اینستنس وصل کن (کلید ثابت لازم نیست).
3. در `.env`: `S3_BUCKET=اسم-باکت` و `AWS_REGION=...` → `docker compose up -d`
   فایل بزرگ که آماده شود، لینک امضاشده (presigned) با اعتبار `FILE_TTL_HOURS` ساعت برای کاربر می‌رود.

## ۸) حالت B — فرانت Serverless (اختیاری، وقتی EC2 از قدم ۵ و HTTPS از قدم ۶ آماده است)
> در این حالت سرویس `bot` در compose را خاموش کن (`docker compose stop bot`) — بات فقط یک مصرف‌کننده آپدیت می‌خواهد. دانلود و صف همچنان روی EC2 است؛ سرورلس فقط لینک را می‌گیرد و کار را با `POST /jobs` به EC2 پاس می‌دهد.

```bash
cd serverless
cp tgcloud/lib/config.example.js tgcloud/lib/config.js
# در config.js: ‏EC2_API_URL = https://dl.example.com و API_SECRET = همان مقدار .env EC2
npm create @tgcloud/bot .   # یا: npm i و npx tgcloud init — فایل‌های tgcloud/ این ریپو را نگه دار
npx tgcloud login           # توکن CLI از BotFather → Serverless → CLI Access
npx tgcloud push
npx tgcloud migrate         # ساخت جدول pending
```
تست بدون دیپلوی واقعی: `npx tgcloud run handlers/message '{ chat:{id:1}, text:"https://youtu.be/..." }'`

## ۹) یوتیوب ارور «Sign in to confirm you're not a bot» داد؟
IP دیتاسنترها را یوتیوب گاهی بلاک می‌کند. راه رسمیِ yt-dlp: کوکی مرورگر خودت.
1. روی مرورگرت (لاگین در یوتیوب) با افزونه «Get cookies.txt LOCALLY» فایل `cookies.txt` بگیر.
2. فایل را **امن** (نه با گیت!) روی EC2 بگذار: `scp -i key.pem cookies.txt ubuntu@<IP>:~/file-from-link/data-cookies.txt` و آن را به `/data/cookies.txt` داخل حجم مشترک کپی کن.
3. در `.env`: ‏`YTDLP_COOKIES_FILE=/data/cookies.txt` → `docker compose restart worker bot api`
4. کوکی منقضی می‌شود؛ هر چند هفته تازه‌اش کن. فایل کوکی یعنی دسترسی اکانت — مثل پسورد نگهش دار.

## ۱۰) نگهداری و عیب‌یابی
```bash
docker compose logs -f worker     # خطای دانلودها اینجا دیده می‌شود
docker compose exec redis redis-cli LLEN rq:queue:downloads   # طول صف
curl -s -H "X-API-Secret: $API_SECRET" https://dl.example.com/health
```
- **آپدیت yt-dlp** (سایت‌ها مدام عوض می‌شوند): `docker compose build --no-cache worker bot api && docker compose up -d` — داخل Dockerfile عمداً آخرین yt-dlp نصب می‌شود.
- **دیسک پر شد؟** فایل‌ها بعد از ارسال پاک می‌شوند و لینک‌های عمومی TTL دارند؛ اگر صف منفجر شد حجم `shared-data` را چک و `DOWNLOAD_DIR` را خالی کن.
- **بات جواب نمی‌دهد:** اول `docker compose logs bot`؛ شایع‌ترین علت: توکن اشتباه، یا فعال‌بودن همزمان حالت B (سرورلس) و سرویس bot.
- **امنیت:** `.env` و `cookies.txt` و `serverless/tgcloud/lib/config.js` هر سه در `.gitignore` هستند — توکن/سکرت را هرگز کامیت نکن. `API_SECRET` ضعیف = هرکس می‌تواند روی سرورت دانلود صف کند.

## ۱۱) خلاصه جریان یک درخواست
```
کاربر لینک می‌فرستد → فرانت دکمه کیفیت نشان می‌دهد → POST /jobs به EC2
→ Redis/RQ صف (نوبت اعلام می‌شود) → ورکر: yt-dlp دانلود + ffmpeg مرج
→ ≤49MB: ارسال مستقیم فایل | >49MB: لینک S3 یا لینک موقت EC2
→ پیام وضعیت: ✅ انجام شد (+ عنوان ویدیو)
```
