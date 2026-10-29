"""Cold-start import uses only synthetic local Claude transcripts."""
import json
import os
import time

from tokeneconomizer.plugin import history, hosts
from tokeneconomizer.plugin.context import LiveContext


def _repo(path, remote):
    (path / ".git").mkdir(parents=True)
    (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (path / ".git" / "config").write_text(
        f'[remote "origin"]\n\turl = {remote}\n')
    return path


def _transcript(path, cwd):
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {"type": "user", "cwd": str(cwd),
         "message": {"role": "user", "content": "synthetic task"}},
        {"type": "assistant", "cwd": str(cwd),
         "message": {"id": "msg_" + path.stem, "role": "assistant",
                     "model": "claude-sonnet-5-5",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [{"type": "text", "text": "done"}]}}
    ]
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    old = time.time() - history.fold.STALE_S - 20
    os.utime(path, (old, old))
    return path


def test_import_matches_repository_and_is_idempotent(tmp_path):
    repo = _repo(tmp_path / "repo", "https://github.com/example/project.git")
    clone = _repo(tmp_path / "clone", "git@github.com:example/project.git")
    other = _repo(tmp_path / "other", "https://github.com/example/other.git")
    config = tmp_path / "claude"
    logs = config / "projects" / "encoded-project"
    _transcript(logs / "a.jsonl", repo)
    _transcript(logs / "b.jsonl", clone)
    _transcript(logs / "wrong.jsonl", other)
    _transcript(logs / "current.jsonl", repo)
    env = {"CLAUDE_CONFIG_DIR": str(config), "TOKENECONOMIZER_HOME": str(tmp_path / "state"),
           "GIT_CEILING_DIRECTORIES": str(tmp_path)}
    ctx = LiveContext.build(hosts.ClaudeCode(), str(repo), env)
    ctx.config.toolprune = "off"
    result = history.import_history(ctx, exclude=("current",))
    assert result["imported"] == result["scanned"] == 2
    assert {row["session_id"] for row in ctx.store.read_lines("ledger.jsonl")} == {"a", "b"}
    assert history.import_history(ctx) == result
    assert len(ctx.store.read_lines("ledger.jsonl")) == 2


def test_startup_seeds_without_optional_model_calls(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo", "https://github.com/example/project.git")
    config = tmp_path / "claude"
    _transcript(config / "projects" / "project" / "old.jsonl", repo)
    env = {"CLAUDE_CONFIG_DIR": str(config), "TOKENECONOMIZER_HOME": str(tmp_path / "state"),
           "GIT_CEILING_DIRECTORIES": str(tmp_path), "TE_FOLD_SYNC": "1"}
    ctx = LiveContext.build(hosts.ClaudeCode(), str(repo), env)
    ctx.config.microskills = "envfacts+distiller"
    ctx.config.toolprune = "off"
    from tokeneconomizer.plugin import sidecall
    monkeypatch.setattr(sidecall, "runner_for", lambda *a, **kw: 1 / 0)
    assert history.schedule(ctx, exclude=("current",))
    assert ctx.store.read(history.STATE_FILE)["imported"] == 1
    assert ctx.config.microskills == "envfacts+distiller"
    assert not history.schedule(ctx)
