"""Live queue-position updates.

The 'queued' message is written once at enqueue time and otherwise never
changes, so a user at position 120 stares at 120 until their download
starts — which feels exactly like a freeze. This loop re-reads positions
every 60s and edits the message when the position has dropped meaningfully.

Policy (keeps Telegram edit-rate limits far away):
- First sight of a job only baselines it (no edit): the enqueue message
  already shows a position, and re-editing the same text errors.
- Edit only when the position dropped by >= MIN_DROP, or dropped to
  PRECISE_BELOW or under (endgame precision), and at least a tick passed
  since the last edit of that message.
- Only jobs still status='queued' are touched: once process_job starts,
  it owns the message (downloading/uploading/done).
- Deleted-message and not-modified errors are swallowed, never crash the
  loop; a deleted message is dropped from tracking.

Deliberately free of any telegram import so it stays unit-testable: the
bot object only needs an async edit_message_text(chat_id, message_id,
text) method, which the real PTB Bot provides.
"""
import asyncio, logging, time
from . import db
from .i18n import t as tr

TICK_SECONDS = 60
MIN_DROP = 5
PRECISE_BELOW = 10
log = logging.getLogger(__name__)

def should_edit(shown_pos, last_edit_ts, new_pos, now):
    if new_pos >= shown_pos:
        return False
    if now - last_edit_ts < TICK_SECONDS:
        return False
    return (shown_pos - new_pos >= MIN_DROP) or (new_pos <= PRECISE_BELOW)

async def refresh_once(bot, shown):
    """One tick. `shown` maps jid -> (pos, last_edit_ts); mutated in place.
    Returns the number of messages edited."""
    try:
        waiting = db.queued_jobs_with_status_msg()
    except Exception:
        log.exception("position refresh: db read failed")
        return 0
    waiting_ids = {j["id"] for j in waiting}
    for jid in list(shown):
        if jid not in waiting_ids:
            del shown[jid]
    edited = 0
    for job in waiting:
        jid = job["id"]
        try:
            pos = db.queue_position(jid)
        except Exception:
            continue
        if pos is None:
            continue
        now = time.time()
        prev = shown.get(jid)
        if prev is None:
            shown[jid] = (pos, now)
            continue
        shown_pos, last_ts = prev
        if not should_edit(shown_pos, last_ts, pos, now):
            continue
        text = tr(job.get("lang") or "en", "queued", pos=pos, jid=jid)
        try:
            await bot.edit_message_text(chat_id=job["chat_id"], message_id=job["status_message_id"], text=text)
            shown[jid] = (pos, now)
            edited += 1
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg:
                shown.pop(jid, None)
            elif "not modified" in msg:
                shown[jid] = (pos, now)
            else:
                log.info("position refresh: edit failed for %s: %s", jid, e)
    return edited

async def position_loop(bot):
    shown = {}
    while True:
        try:
            await refresh_once(bot, shown)
        except Exception:
            log.exception("position refresh tick failed")
        await asyncio.sleep(TICK_SECONDS)
