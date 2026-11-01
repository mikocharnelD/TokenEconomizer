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

if _os.name == "nt" and not getattr(_subprocess.Popen.__init__, "_te_hidden", False):
    # Hooks and the detached `te` have no console, so every console program they start
    # (`claude -p`, `git`, `powershell`) would get a visible console window of its own.
    # CREATE_NO_WINDOW on every child process of this package keeps them all hidden.
    # The marker is checked first, so a reload never wraps the wrapper; the original initializer
    # is held in the closure. `creationflags` is the 14th positional parameter of Popen.
    def _install(orig, flag=0x08000000, pos=13):
        def _hidden_popen_init(self, *args, **kwargs):
            if len(args) > pos:
                args = args[:pos] + ((args[pos] or 0) | flag,) + args[pos + 1:]
            else:
                kwargs["creationflags"] = (kwargs.get("creationflags") or 0) | flag
            orig(self, *args, **kwargs)

        _hidden_popen_init._te_hidden = True
        return _hidden_popen_init

    _subprocess.Popen.__init__ = _install(_subprocess.Popen.__init__)

from .config import EconomizerConfig, InjectionConfig, SpiralConfig, ToolingConfig
from . import ledger, trace

__all__ = ["EconomizerConfig", "InjectionConfig", "ToolingConfig", "SpiralConfig", "ledger",
           "trace"]
