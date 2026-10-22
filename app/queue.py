from redis import Redis
from rq import Queue
from .config import REDIS_URL, JOB_TIMEOUT, MAX_JOBS_PER_USER
from . import db
_q = None
def q():
    global _q
    if _q is None: _q = Queue("downloads", connection=Redis.from_url(REDIS_URL))
    return _q
class QueueFull(Exception): pass
def enqueue(chat_id, user_id, url, fmt, status_message_id=None, lang='en') -> tuple[str, int]:
    if db.active_jobs_for_user(user_id) >= MAX_JOBS_PER_USER:
        raise QueueFull(f"limit {MAX_JOBS_PER_USER} active jobs per user")
    jid = db.create_job(chat_id, user_id, url, fmt, lang)
    from .tasks import on_job_failure
    q().enqueue("app.tasks.process_job", jid, status_message_id, job_timeout=JOB_TIMEOUT, result_ttl=3600, failure_ttl=86400, on_failure=on_job_failure)
    return jid, (db.queue_position(jid) or 1)

def enqueue_broadcast(owner_chat_id, from_chat_id, message_id, status_message_id, lang="en"):
    return q().enqueue("app.tasks.broadcast_job", owner_chat_id, from_chat_id,
                       message_id, status_message_id, lang,
                       job_timeout=7200, result_ttl=3600, failure_ttl=86400)
