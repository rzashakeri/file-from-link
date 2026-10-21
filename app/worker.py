"""RQ worker entrypoint:  python -m app.worker   (scale with docker compose)"""
from redis import Redis
from rq import Worker, Queue
from .config import REDIS_URL
def main():
    conn = Redis.from_url(REDIS_URL)
    Worker([Queue("downloads", connection=conn)], connection=conn).work(with_scheduler=False)
if __name__ == "__main__": main()
