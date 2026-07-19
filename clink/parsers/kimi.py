"""Parser for Kimi Code CLI JSONL output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class KimiJSONLParser(BaseParser):
    """Parse stdout produced by ``kimi --prompt ... --output-format stream-json``.

    Kimi emits JSON Lines rather than a single document. Two line shapes matter:

        {"role": "assistant", "content": "..."}
        {"role": "meta", "type": "session.resume_hint", "session_id": "..."}

    Only ``assistant`` lines carry the answer; ``meta`` lines are session
    bookkeeping and are skipped.

    Kimi is a reasoning model and can emit a large volume of
    ``reasoning_content`` before (or instead of) any ``content``. Reasoning is
    deliberately NOT accumulated into the response — it is the model's working,
    not its answer — but it IS counted, because a run that produces reasoning
    and no content is the signature of a call that will not converge, and the
    caller deserves to be told that rather than handed an empty string.
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

        # Reasoning with no content is a real, reproducible outcome on large or
        # open-ended prompts: the model thinks until it stops and never answers.
        # Say so explicitly instead of returning an empty response that reads as
        # success to the caller.
        if reasoning_chars:
            raise ParserError(
                f"Kimi CLI produced {reasoning_chars} characters of reasoning and no "
                f"answer (finish_reason={finish_reason}). This usually means the prompt "
                f"was too open-ended or the input too large; a bounded instruction such "
                f"as 'at most 3 findings, one line each, then stop' reliably converges."
            )

        raise ParserError("Kimi CLI response contained no assistant content")
