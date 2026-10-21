"""HTTP API for the Serverless front (and health checks).
Auth: header  X-API-Secret: <API_SECRET>  on every /jobs call."""
import secrets
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from . import db
from .config import API_SECRET, PUBLIC_DIR
from .queue import enqueue, QueueFull
app = FastAPI(title="ytdlp-downloader-api")
class JobIn(BaseModel):
    chat_id: int; user_id: int; url: str; fmt: str = "best"; status_message_id: int | None = None; lang: str = "en"
def auth(secret: str | None):
    if not secret or not secrets.compare_digest(secret, API_SECRET): raise HTTPException(401, "bad secret")
@app.get("/health")
def health(): return {"ok": True}
@app.post("/jobs")
def create(job: JobIn, x_api_secret: str | None = Header(None)):
    auth(x_api_secret)
    try: jid, pos = enqueue(job.chat_id, job.user_id, job.url, job.fmt, job.status_message_id, job.lang)
    except QueueFull as e: raise HTTPException(429, str(e))
    return {"job_id": jid, "position": pos, "status": "queued"}
@app.get("/jobs/{jid}")
def status(jid: str, x_api_secret: str | None = Header(None)):
    auth(x_api_secret); j = db.get_job(jid)
    if not j: raise HTTPException(404, "not found")
    return j
@app.get("/files/{token}/{name}")
def files(token: str, name: str):
    p = (PUBLIC_DIR/token/name).resolve()
    if PUBLIC_DIR.resolve() not in p.parents or not p.exists(): raise HTTPException(404)
    return FileResponse(p, filename=name)
