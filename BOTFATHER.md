# BotFather setup — @FileFromLinkBot

## 1. Create the bot (do this FIRST — the username was free on 2026-10-21, that can change)
/newbot
Name:     File From Link 📥
Username: FileFromLinkBot
→ Save the token in .env as BOT_TOKEN (never in git/chat).

## 2. Paste-ready settings (BotFather → @FileFromLinkBot)
/setdescription  (shown before the user starts the bot):
Send me any video link — YouTube, Instagram, TikTok, X and 1,700+ sites.
Pick a quality, I queue it, download it and send the file right here. 📥
Free. No sign-up.

/setabouttext  (profile About):
📥 File From Link — send a link, get a file. Downloads videos & audio from 1,700+ sites.
Send a link → pick quality → get the file. Powered by yt-dlp.

/setuserpic → use a simple bold icon: white ⬇ arrow on a solid blue/green square (legible at 40px).

## 3. Commands list (/setcommands):
start - Send a link, get a file
help - How it works

## 4. If you use Serverless mode (Mode B):
BotFather → @FileFromLinkBot → Serverless → ON → CLI Access → copy the CLI token for `npx tgcloud login`.
