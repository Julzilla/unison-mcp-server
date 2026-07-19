"""Parser for Kimi Code CLI JSONL output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class KimiJSONLParser(BaseParser):
    """Parse stdout produced by ``kimi --prompt ... --output-format stream-json``.

    Kimi emits JSON Lines rather than a single document. Two line shapes matter:

        {"role": "assistant", "content": "..."}
        {"role": "meta", "type": "session.resume_hint", "session_id": "...",
         "command": "kimi -r ...", "content": "To resume this session: ..."}

    Only ``assistant`` lines carry the answer. Note that ``meta`` lines have a
    ``content`` field of their own holding human-readable resume text — keying
    on ``content`` alone would append "To resume this session: kimi -r ..." to
    every answer, so the role check is load-bearing rather than tidiness.

    Observed key set across kimi 0.27.0 runs, including deliberately
    reasoning-heavy prompts, is exactly::

        command, content, role, session_id, type

    In particular there is no ``reasoning_content`` and no ``finish_reason``:
    those belong to the OpenAI-compatible HTTP response shape, not to this
    CLI's stream-json. Both are still read below, defensively, so that a future
    CLI version emitting them degrades into richer metadata instead of a
    misparse — but neither has ever been seen in practice, and nothing here
    should be read as documenting that Kimi produces them.
    """

    name = "kimi_jsonl"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        if not stdout.strip():
            raise ParserError("Kimi CLI returned empty stdout while JSONL output was expected")

        parts: list[str] = []
        reasoning_chars = 0
        session_id: str | None = None
        finish_reason: str | None = None
        saw_json = False

        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            saw_json = True

            if obj.get("session_id") and session_id is None:
                session_id = obj["session_id"]
            if obj.get("finish_reason"):
                finish_reason = obj["finish_reason"]

            if obj.get("role") != "assistant":
                continue

            content = obj.get("content")
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        if block["text"].strip():
                            parts.append(block["text"].strip())

            reasoning = obj.get("reasoning_content")
            if isinstance(reasoning, str):
                reasoning_chars += len(reasoning)

        if not saw_json:
            raise ParserError(
                "Kimi CLI produced no JSON lines. Confirm --output-format stream-json "
                f"was passed. First 200 chars of stdout: {stdout[:200]!r}"
            )

        metadata: dict[str, Any] = {"reasoning_chars": reasoning_chars}
        if session_id:
            metadata["session_id"] = session_id
        if finish_reason:
            metadata["finish_reason"] = finish_reason
        stderr_text = stderr.strip()
        if stderr_text:
            metadata["stderr"] = stderr_text[:2000]

        content_text = "\n".join(parts).strip()
        if content_text:
            return ParsedCLIResponse(content=content_text, metadata=metadata)

        # Defensive: not reachable against kimi 0.27.0, which emits no
        # reasoning_content. Kept so that a future version which thinks without
        # answering reports that fact rather than an empty success.
        if reasoning_chars:
            raise ParserError(
                f"Kimi CLI produced {reasoning_chars} characters of reasoning and no "
                f"answer (finish_reason={finish_reason}). Bound the instruction — "
                f"e.g. 'at most 3 findings, one line each, then stop' — and retry."
            )

        # The reachable empty case: the CLI exited 0 having emitted only session
        # bookkeeping. Raising keeps that from surfacing as a blank success.
        raise ParserError("Kimi CLI response contained no assistant content")
