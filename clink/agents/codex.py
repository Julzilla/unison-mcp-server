"""Codex-specific CLI agent hooks."""

from __future__ import annotations

from clink.models import ResolvedCLIClient
from clink.parsers.base import ParserError

from .base import AgentOutput, BaseCLIAgent


class CodexAgent(BaseCLIAgent):
    """Codex CLI agent with JSONL recovery support."""

    model_flag_aliases: tuple[str, ...] = ("-m",)

    #: Bare (valueless) flags that must be removed in read-only mode because they
    #: disable Codex's sandbox and/or approval prompt.
    _READ_ONLY_STRIP_BARE: tuple[str, ...] = (
        "--dangerously-bypass-approvals-and-sandbox",
        "--full-auto",
    )
    #: Value-carrying flags (flag + following token) that must be removed so the
    #: read-only sandbox we append is authoritative.
    _READ_ONLY_STRIP_VALUED: tuple[str, ...] = ("--sandbox", "-s")

    def __init__(self, client: ResolvedCLIClient):
        super().__init__(client)

    def get_read_only_args(self) -> list[str]:
        """Run Codex in its native read-only sandbox.

        Codex ``exec`` supports ``--sandbox read-only``, which enforces read-only
        filesystem access at the OS level. This is the layer-1 restriction that
        makes ``read_only=True`` meaningful for Codex.
        """
        return ["--sandbox", "read-only"]

    def _apply_read_only(self, command: list[str]) -> list[str]:
        """Strip sandbox-disabling flags before appending the read-only sandbox.

        The shipped Codex manifest hard-codes
        ``--dangerously-bypass-approvals-and-sandbox`` (which turns OFF both the
        filesystem sandbox and the shell-command approval prompt). If left in
        place, ``read_only=True`` would run Codex fully unsandboxed — a prompt
        injection in a reviewed file could execute arbitrary commands. Remove it
        (and any conflicting ``--sandbox``/``-s`` pair or ``--full-auto``) first,
        then let the base implementation append ``get_read_only_args()``.
        """
        cleaned: list[str] = []
        i = 0
        while i < len(command):
            token = command[i]
            if token in self._READ_ONLY_STRIP_BARE:
                i += 1
                continue
            if token in self._READ_ONLY_STRIP_VALUED:
                i += 2  # drop the flag and its immediately-following value
                continue
            cleaned.append(token)
            i += 1
        return super()._apply_read_only(cleaned)

    def render_model_args(self, model: str) -> list[str]:
        return ["-m", model]

    def _recover_from_error(
        self,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        sanitized_command: list[str],
        duration_seconds: float,
        output_file_content: str | None,
    ) -> AgentOutput | None:
        try:
            parsed = self._parser.parse(stdout, stderr)
        except ParserError:
            return None

        return AgentOutput(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            parser_name=self._parser.name,
            output_file_content=output_file_content,
        )
