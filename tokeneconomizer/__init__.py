"""TokenEconomizer: experience-driven black-box cost control for coding agents.

The agent stays as it is (Claude Code, Codex, Copilot CLI, Pi). Three mechanisms read its
finished sessions and change what the next ones pay for:

  * `microskills` -- micro-skill synthesis and injection: short repository facts learned from
                     recurring failures, stated at the start of the next session;
  * `toolprune`   -- tool pruning: tool definitions a repository never uses, proposed for the
                     agent's deny list;
  * `loopguard`   -- failure-loop intervention: a turn stuck repeating the same failure is
                     redirected once, then stopped or flagged.

They share one trace reader (`trace`), one cost ledger (`ledger`, `pricing`) and one domain
interface (`domain.DomainAdapter`). `plugin` runs them inside real sessions through each agent's
hooks; the mechanisms never import it. Stdlib only.
"""
import os as _os
import subprocess as _subprocess

if _os.name == "nt":
    # Hooks and the detached `te` have no console, so every console program they start
    # (`claude -p`, `git`, `powershell`) would get a visible console window of its own.
    # CREATE_NO_WINDOW on every child process of this package keeps them all hidden.
    _CREATE_NO_WINDOW = 0x08000000
    _popen_init = _subprocess.Popen.__init__

    def _hidden_popen_init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        _popen_init(self, *args, **kwargs)

    if not getattr(_subprocess.Popen.__init__, "_te_hidden", False):
        _hidden_popen_init._te_hidden = True
        _subprocess.Popen.__init__ = _hidden_popen_init

from .config import EconomizerConfig, InjectionConfig, SpiralConfig, ToolingConfig
from . import ledger, trace

__all__ = ["EconomizerConfig", "InjectionConfig", "ToolingConfig", "SpiralConfig", "ledger",
           "trace"]
