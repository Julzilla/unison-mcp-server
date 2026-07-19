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
        """Kimi selects the model with ``-m``, but only under config.toml auth.

        ``-m`` resolves the value against ``[models."..."]`` keys in the user's
        own ``config.toml`` and fails closed if there is no match::

            config.invalid: Model "k3" is not configured in config.toml.

        Two consequences worth knowing before passing a model at all:

        1. **The keys are namespaced by provider.** A default ``kimi /login``
           install writes the provider ``managed:kimi-code``, so the keys are
           ``kimi-code/k3``, ``kimi-code/kimi-for-coding`` and
           ``kimi-code/kimi-for-coding-highspeed`` — not the bare model names.
           ``kimi-code/k3`` already carries ``max_context_size = 1048576``, so
           no context-window suffix is needed or accepted.

        2. **Under ``KIMI_MODEL_*`` env auth, every ``-m`` value fails**,
           including one that matches ``KIMI_MODEL_NAME`` exactly. Those vars
           synthesize a provider in memory and write nothing to ``config.toml``,
           so there is no model table to resolve against. Omit the model and
           select it with ``KIMI_MODEL_NAME`` instead, where the API model
           strings (``k3``, or ``k3[1m]`` for the 1M window) do apply.

        Because valid keys are per-user, the manifest ships no
        ``supported_models`` allowlist — a fixed list would reject working
        models and admit broken ones.
        """
        return ["-m", model]
