"""Kimi Code CLI agent hooks."""

from __future__ import annotations

from collections.abc import Sequence

from clink.models import ResolvedCLIClient

from .base import BaseCLIAgent, InvocationPlan


class KimiAgent(BaseCLIAgent):
    """Kimi Code CLI (``kimi``).

    Kimi does not read prompts from stdin. Its non-interactive mode is
    ``--prompt <text>``, and passing ``--output-format`` without it fails with
    "Output format is only supported in prompt mode", so the prompt has to
    travel on argv.
    """

    def __init__(self, client: ResolvedCLIClient):
        super().__init__(client)

    def prepare_invocation(
        self,
        prompt: str,
        files: Sequence[str],
        images: Sequence[str],
    ) -> InvocationPlan:
        """Deliver the prompt via ``--prompt`` on argv.

        Note for large prompts: Windows caps a command line near 32767
        characters, and ``subprocess.list2cmdline`` escaping expands quote-dense
        text well beyond its raw length, so a prompt that measures under the cap
        can still exceed it once escaped. The tool layer embeds files into the
        prompt before ``run`` is called, which is what makes that reachable.
        """
        _ = (files, images)
        return InvocationPlan(kind="argv", flag="--prompt")

    def get_read_only_args(self) -> list[str]:
        """Kimi has no read-only flag.

        ``--prompt`` runs in ``auto`` permission mode and cannot be combined
        with ``--yolo``, ``--auto`` or ``--plan`` (the CLI rejects all three), so
        an unconstrained run WILL write files. Constrain it with static
        ``[[permission.rules]]`` in ``$KIMI_CODE_HOME/config.toml`` instead:
        deny ``Write`` and ``Edit`` at minimum. Note that a deny is absolute
        regardless of rule order, and argument-pattern globs such as
        ``Bash(*>*)`` do not reliably block what they appear to.
        """
        return []

    def render_model_args(self, model: str) -> list[str]:
        """Kimi selects the model with ``-m``.

        Use ``k3[1m]`` rather than ``k3`` for the 1M context window; plain
        ``k3`` resolves to the tier default, which is 256K below Allegretto.
        """
        return ["-m", model]
