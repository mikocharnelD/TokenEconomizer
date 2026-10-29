"""Seed a Claude repository's local state from its existing session transcripts.

Only finished, recent sessions with a verifiable repository identity are folded. The
transcripts remain in Claude's local directory; this module never uploads or copies
them into the repository. The ordinary fold's session-id ledger makes retries safe.
"""
import os
import time

from . import fold, repos
from .paths import repo_identity

HISTORY_DAYS = 30
SCHEDULE_RETRY_S = 3600
STATE_FILE = "history-import.json"


def _history_root(env):
    config = env.get("CLAUDE_CONFIG_DIR") or os.path.join(
        env.get("HOME") or os.path.expanduser("~"), ".claude")
    return os.path.join(os.path.abspath(config), "projects")


def candidates(ctx, now=None, exclude=()):
    """Yield (mtime, session_id, path) oldest first for this exact repository."""
    now = time.time() if now is None else now
    cutoff = now - HISTORY_DAYS * 86400
    root = _history_root(ctx.env)
    found = []
    excluded = set(exclude)
    try:
        projects = os.scandir(root)
    except OSError:
        return []
    with projects:
        for project in projects:
            if not project.is_dir(follow_symlinks=False):
                continue
            try:
                files = os.scandir(project.path)
            except OSError:
                continue
            with files:
                for entry in files:
                    if not entry.name.endswith(".jsonl") or not entry.is_file(follow_symlinks=False):
                        continue
                    sid = entry.name[:-6]
                    if sid in excluded:
                        continue
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if not (cutoff <= stat.st_mtime <= now - fold.STALE_S) or not stat.st_size:
                        continue
                    cwd = repos._transcript_cwd(entry.path)
                    if not cwd or not os.path.isdir(cwd):
                        continue
                    if repo_identity(cwd, ctx.env).key == ctx.repo.key:
                        found.append((stat.st_mtime, sid, entry.path))
    return sorted(found)


def import_history(ctx, exclude=()):
    """Import once, retrying safely after a crash or an incomplete prior run."""
    if ctx.host.name != "claude":
        return {"imported": 0, "skipped": 0}
    with ctx.store.locked("history-import", timeout=0.1) as got:
        if not got:
            return {"busy": True}
        state = ctx.store.read(STATE_FILE) or {}
        if state.get("complete"):
            return state
        rows = candidates(ctx, exclude=exclude)
        imported = 0
        skipped = 0
        # Historical import must not make a burst of optional model calls. Free
        # environment facts and tool-use evidence are still learned. Future live
        # folds use the person's configured microskills profile unchanged.
        profile = ctx.config.microskills
        if "distiller" in profile:
            ctx.config.microskills = "envfacts"
        try:
            for _, sid, path in rows:
                try:
                    if fold.fold_session(ctx, sid, transcript_path=path) is None:
                        skipped += 1
                    else:
                        imported += 1
                except (OSError, ValueError, TypeError):
                    skipped += 1
            result = {"complete": True, "at": time.time(), "imported": imported,
                      "skipped": skipped, "scanned": len(rows),
                      "history_days": HISTORY_DAYS}
            ctx.store.write(STATE_FILE, result)
            return result
        finally:
            ctx.config.microskills = profile


def schedule(ctx, exclude=()):
    """Start one detached import from SessionStart without delaying the agent."""
    if ctx.host.name != "claude":
        return False
    with ctx.store.locked("history-schedule", timeout=0.1) as got:
        if not got:
            return False
        state = ctx.store.read(STATE_FILE) or {}
        now = time.time()
        if state.get("complete") or now - state.get("scheduled_at", 0) < SCHEDULE_RETRY_S:
            return False
        ctx.store.write(STATE_FILE, {"scheduled_at": now, "complete": False})
    try:
        args = ["fold", "--bootstrap-history"]
        for sid in exclude:
            args.extend(("--exclude-session", sid))
        if ctx.env.get("TE_FOLD_SYNC") == "1":
            import_history(ctx, exclude=exclude)
        else:
            ctx.spawn(args, "history-import.log")
        return True
    except OSError:
        with ctx.store.locked("history-schedule") as got:
            if got:
                ctx.store.write(STATE_FILE, {"scheduled_at": 0, "complete": False})
        return False
