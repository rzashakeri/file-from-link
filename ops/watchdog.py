#!/usr/bin/env python3
"""File From Link on-box watchdog (host cron, every 3 minutes).

Self-heals the realistic freeze modes without any external dependency:
  1. A compose service is down or the worker pool shrank -> bring the
     stack back up at the pinned scale (worker=3).
  2. Jobs stuck in downloading/uploading beyond the RQ timeout + grace
     (the worker died too hard for the failure callback to run) ->
     reconcile them in the bot container (marks failed, notifies the
     user) and restart the workers.

Stdlib only; logs one line per action to stdout (cron appends to
/var/log/ffl-watchdog.log). Quiet when everything is healthy.
"""
import json
import os
import subprocess
import time

BASE = "/opt/file-from-link"
DOCKER = "/usr/bin/docker"
EXPECTED = {"bot": 1, "api": 1, "redis": 1, "pot-provider": 1, "worker": 3}


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def run(*args, timeout=120):
    r = subprocess.run(args, capture_output=True, text=True, cwd=BASE, timeout=timeout)
    return r.stdout.strip()


def running_counts():
    out = run(DOCKER, "compose", "ps", "--format", "json")
    counts = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            obj = [obj]
        for c in obj:
            if c.get("State") == "running":
                svc = c.get("Service", "")
                counts[svc] = counts.get(svc, 0) + 1
    return counts


def main():
    counts = running_counts()
    short = {s: (counts.get(s, 0), n) for s, n in EXPECTED.items() if counts.get(s, 0) < n}
    if short:
        log(f"services below expected {short} (have {counts}); running compose up")
        run(DOCKER, "compose", "up", "-d", "--scale", "worker=3", timeout=300)
        log(f"after up: {running_counts()}")

    # Stale-job reconcile inside the bot container (has the app + DB path).
    out = run(DOCKER, "compose", "exec", "-T", "bot", "python", "-c",
              "from app.tasks import reconcile_stale; print(reconcile_stale())")
    try:
        stale = int(out.splitlines()[-1])
    except (ValueError, IndexError):
        stale = 0
        log(f"reconcile output unparsable: {out[:120]!r}")
    if stale:
        log(f"reconciled {stale} stale job(s); restarting workers")
        run(DOCKER, "compose", "restart", "worker", timeout=180)
    check_bot()

STATE_PATH = "/opt/file-from-link/.watchdog_state.json"

def _last_bot_restart():
    try:
        return json.loads(open(STATE_PATH).read()).get("bot_restart", 0)
    except Exception:
        return 0

def _note_bot_restart():
    try:
        with open(STATE_PATH, "w") as f:
            json.dump({"bot_restart": time.time()}, f)
    except OSError:
        pass

def restart_bot(reason):
    if time.time() - _last_bot_restart() < 900:
        log(f"bot restart suppressed (rate cap): {reason}")
        return
    log(f"restarting bot: {reason}")
    run(DOCKER, "compose", "restart", "bot", timeout=120)
    _note_bot_restart()

def check_bot():
    """Two independent liveness signals for the bot process:
    (1) heartbeat file touched every 60s by its event loop;
    (2) getUpdates lines in recent logs (traffic-independent proof the
        long-poll is cycling). The 2026-10-22 freeze had (1) fine and
        (2) silently dead for 40+ minutes."""
    hb = run(DOCKER, "compose", "exec", "-T", "bot", "stat", "-c", "%Y", "/data/bot_heartbeat")
    try:
        age = time.time() - int(hb.splitlines()[-1])
        if age > 240:
            restart_bot(f"heartbeat stale ({int(age)}s)")
            return
    except (ValueError, IndexError):
        pass  # heartbeat not deployed yet / unreadable: rely on log check
    logs = run(DOCKER, "compose", "logs", "--since", "12m", "bot")
    if "getUpdates" not in logs:
        restart_bot("no getUpdates activity in 12m of bot logs")


if __name__ == "__main__":
    main()
