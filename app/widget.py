"""Live status widget (Telegram Bot API 10.4).

A job's status message is a small HTML widget instead of a plain text
message — in private chats only (widgets are production-gated to private
chats). The widget is fixed HTML plus a changeable chat state, written
only by the bot:

- send: ``sendWidget`` with the HTML and an initial chat state
  ("adding…"), caption = the URL so clients that cannot render widgets
  still see which link is queued.
- updates: ``editMessageWidgetData`` with a new chat state (queue
  position, download %, uploading, done, failed). The widget redraws
  in place — no message edits, no "edited" spam, no edit-rate limits.

PTB 22.8 (latest on PyPI, 2026-11-10) has no widget support at all, so
everything here goes through the raw Bot API calls in ``sender.tg``
(httpx -> the local Bot API server, which must be 10.4+). The widget
is display-only: ``allow_queries`` is False, so no WidgetQuery updates
ever arrive and PTB never has to parse them.

Limits enforced by Telegram (and asserted in tests):
- HTML: 1-32768 bytes raw, <= 4096 bytes zlib-compressed at level 9.
- chat state: 0-1024 bytes UTF-8. The state is a compact JSON object:
  {"s": status, "l": line, "p": pct?} where status is one of
  adding|queued|downloading|uploading|done|failed, ``line`` is the
  pre-rendered i18n text (all localisation stays in Python) and ``p``
  is a 0-100 progress percent (bar hidden when absent).

Layout notes (2026-11-10, from the Telegram widgets guide):
- The widget fills the bubble; ``body{margin:0}`` goes edge to edge,
  so the body carries its own padding (12px 14px) and the bar never
  touches the bubble edges.
- Height is automatic (sendWidget ``height: 0``): the bubble takes the
  content height, so nothing clips. A fixed height would clip it.
- Done state (2026-11-10, owner's call): the widget is a styled header
  ("done_widget" line, bold 17px green) over a thick green bar — no
  status line, no filename, and the bot clears the URL caption at done
  (the caption stays while the job runs, so the user can tell which
  link a widget belongs to). Direct style writes are used for the
  done look: the sandbox profile already allows style.* writes.
  Old widget messages keep the old layout — HTML is fixed at send.
"""
import json, zlib

from .sender import tg, edit_text

MAX_HTML_BYTES = 32768
MAX_HTML_COMPRESSED = 4096
MAX_STATE_BYTES = 1024

HTML = """<style>
body{margin:0;padding:12px 14px}
#l{white-space:pre-line}
#b{height:16px;border-radius:8px;background:var(--tg-theme-secondary-bg-color);overflow:hidden;margin-top:10px;display:none}
#f{height:100%;width:0;background:var(--tg-theme-button-color)}
</style>
<div id="l"></div>
<div id="b"><div id="f"></div></div>
<script>
var W=window.TelegramWidget||{chatData:null,onEvent:function(){}};
if(typeof W.ready==="function")W.ready();
function r(){
  var s={};
  try{s=JSON.parse(W.chatData||"{}")}catch(e){}
  var l=document.getElementById("l"),b=document.getElementById("b"),f=document.getElementById("f");
  l.textContent=s.l||"";
  var done=s.s==="done";
  if(done){l.style.fontWeight="700";l.style.fontSize="17px";l.style.color="#34c759";f.style.background="#34c759"}
  else{l.style.fontWeight="";l.style.fontSize="";l.style.color="";f.style.background=""}
  if(s.p==null){b.style.display="none"}
  else{b.style.display="block";f.style.width=Math.max(0,Math.min(100,s.p))+"%"}
}
W.onEvent("chatDataChanged",r);
r();
</script>"""

STATUSES = {"adding", "queued", "downloading", "uploading", "done", "failed"}


def html_sizes(html: str = HTML) -> tuple[int, int]:
    """(raw bytes, zlib-level-9 compressed bytes) of the widget HTML."""
    raw = html.encode("utf-8")
    return len(raw), len(zlib.compress(raw, 9))


def check_html(html: str = HTML) -> None:
    raw, comp = html_sizes(html)
    if raw > MAX_HTML_BYTES or comp > MAX_HTML_COMPRESSED:
        raise ValueError(f"widget HTML too big: {raw} raw / {comp} compressed bytes")


def encode_state(status: str, line: str, pct: int | None = None) -> str:
    """Compact chat-state JSON, truncated to fit the 1024-byte budget."""
    if status not in STATUSES:
        raise ValueError(f"unknown widget status {status!r}")
    line = (line or "").strip()
    while True:
        d = {"s": status, "l": line}
        if pct is not None:
            d["p"] = max(0, min(100, int(pct)))
        s = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        if len(s.encode("utf-8")) <= MAX_STATE_BYTES or not line:
            return s
        line = line[:-10].rstrip()


def send_widget(chat_id: int, state: str, caption: str = "", reply_to: int | None = None) -> int | None:
    """Send the status widget. Returns the message id, or None on any
    failure — the caller falls back to the plain text status message."""
    try:
        check_html()
        kw: dict = {"chat_id": chat_id, "html": HTML, "height": 0,
                    "chat_data": state}  # height 0 = automatic: the bubble
        # takes the content height, so the filename box never clips when
        # it wraps; allow_queries omitted (= False): v1 is display-only
        if caption:
            kw["caption"] = caption[:200]
        if reply_to:
            kw["reply_parameters"] = json.dumps({"message_id": reply_to})
        res = tg("sendWidget", **kw)
        return (res.get("result") or {}).get("message_id")
    except Exception:
        return None


def update_widget(chat_id: int, message_id: int, state: str) -> bool:
    """Push a new chat state into a sent widget. False on any failure
    (deleted message, old server, ...) — never raises."""
    try:
        tg("editMessageWidgetData", chat_id=chat_id, message_id=message_id,
           chat_data=state)
        return True
    except Exception:
        return False


def set_status(chat_id: int, message_id: int, kind: str, status: str,
               line: str, pct: int | None = None) -> None:
    """Route one status display update to the right channel: a widget's
    chat state for widget jobs, a plain message edit for text jobs.
    Never raises — a failed update must not fail the download."""
    try:
        if kind == "widget":
            update_widget(chat_id, message_id, encode_state(status, line, pct))
        else:
            edit_text(chat_id, message_id, line)
    except Exception:
        pass
