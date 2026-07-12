"""Regression tests for the security & correctness audit remediation.

Each test pins a specific fixed finding so a future change cannot silently
reintroduce it. Kept dependency-light and offline (no real API/network calls).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# D-1: pseudo-filesystems are blocked by the path sandbox
# ---------------------------------------------------------------------------
class TestD1PseudoFilesystemBlocked:
    def test_proc_sys_dev_run_are_dangerous(self):
        from utils.security_config import is_dangerous_path

        for p in ("/proc/self/environ", "/sys/kernel", "/dev/zero", "/run/secret"):
            assert is_dangerous_path(Path(p)) is True, p

    def test_project_file_is_not_dangerous(self):
        from utils.security_config import is_dangerous_path

        here = Path(__file__).resolve()
        assert is_dangerous_path(here) is False


# ---------------------------------------------------------------------------
# D-2: image validation rejects non-regular files before an unbounded read
# ---------------------------------------------------------------------------
class TestD2ImageValidation:
    def test_non_regular_file_rejected(self):
        from utils.image_utils import validate_image

        # /dev/zero exists on Unix and is a character device, not a regular file.
        if not os.path.exists("/dev/zero"):
            pytest.skip("no /dev/zero on this platform")
        with pytest.raises(ValueError):
            validate_image("/dev/zero")


# ---------------------------------------------------------------------------
# D-3: chat artifact writer refuses to follow a planted symlink
# ---------------------------------------------------------------------------
class TestD3ChatSymlinkRefused:
    def test_symlinked_artifact_is_not_followed(self):
        from tools.chat import ChatTool

        tool = ChatTool()
        d = tempfile.mkdtemp()
        secret = Path(d) / "secret.txt"
        secret.write_text("SECRET", encoding="utf-8")
        link = Path(d) / "pal_generated.code"
        os.symlink(secret, link)

        with pytest.raises(OSError):
            tool._persist_generated_code_block("<GENERATED-CODE>x</GENERATED-CODE>", d)
        # The symlink target must be untouched.
        assert secret.read_text(encoding="utf-8") == "SECRET"

    def test_regular_file_is_replaced(self):
        from tools.chat import ChatTool

        tool = ChatTool()
        d = tempfile.mkdtemp()
        pre = Path(d) / "pal_generated.code"
        pre.write_text("stale", encoding="utf-8")
        out = tool._persist_generated_code_block("<GENERATED-CODE>new</GENERATED-CODE>", d)
        assert "stale" not in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A-1: Codex read-only strips the dangerous bypass flag and adds a real sandbox
# ---------------------------------------------------------------------------
class TestA1CodexReadOnly:
    def _agent(self):
        from unittest.mock import MagicMock

        from clink.agents.codex import CodexAgent

        client = MagicMock()
        client.name = "codex"
        client.parser = "codex_jsonl"
        return CodexAgent(client)

    def test_read_only_args(self):
        assert self._agent().get_read_only_args() == ["--sandbox", "read-only"]

    def test_bypass_flag_stripped(self):
        agent = self._agent()
        cmd = ["codex", "exec", "--json", "--dangerously-bypass-approvals-and-sandbox"]
        result = agent._apply_read_only(cmd)
        assert "--dangerously-bypass-approvals-and-sandbox" not in result
        assert result[-2:] == ["--sandbox", "read-only"]


# ---------------------------------------------------------------------------
# A-9/A-10/A-11: clink parsers tolerate malformed/adversarial CLI output
# ---------------------------------------------------------------------------
class TestClinkParserHardening:
    def test_gemini_non_object_payload(self):
        from clink.parsers.base import ParserError
        from clink.parsers.gemini import GeminiJSONParser

        with pytest.raises(ParserError):
            GeminiJSONParser().parse("[1, 2, 3]", "")

    def test_codex_non_dict_item(self):
        from clink.parsers.base import ParserError
        from clink.parsers.codex import CodexJSONLParser

        # A truthy non-dict "item" must not raise AttributeError; with no usable
        # agent_message the parser raises the structured ParserError instead.
        stdout = '{"type":"item.completed","item":"not-a-dict"}'
        with pytest.raises(ParserError):
            CodexJSONLParser().parse(stdout, "")

    def test_amp_non_dict_message(self):
        from clink.parsers.amp import AmpJSONLParser
        from clink.parsers.base import ParserError

        stdout = '{"type":"assistant","message":"not-a-dict"}'
        with pytest.raises(ParserError):
            AmpJSONLParser().parse(stdout, "")


# ---------------------------------------------------------------------------
# C-6: circuit breaker HALF_OPEN reclaims a leaked probe slot after timeout
# ---------------------------------------------------------------------------
class TestC6HalfOpenEscape:
    def test_leaked_half_open_slot_is_reclaimed(self, monkeypatch):
        import utils.circuit_breaker as cb

        breaker = cb.CircuitBreaker(failure_threshold=1, reset_timeout_seconds=5.0, half_open_max_calls=1)

        clock = {"t": 1000.0}
        monkeypatch.setattr(cb.time, "monotonic", lambda: clock["t"])

        # Trip OPEN.
        breaker.record_failure()
        assert breaker.allow_request() is False

        # After the reset timeout -> HALF_OPEN, one probe admitted, slot taken.
        clock["t"] += 6.0
        assert breaker.allow_request() is True  # probe admitted
        assert breaker.allow_request() is False  # slot in flight, none left

        # Caller never resolved the probe (leak). After another reset timeout the
        # slot is reclaimed and a fresh probe is admitted.
        clock["t"] += 6.0
        assert breaker.allow_request() is True


# ---------------------------------------------------------------------------
# C-7: caller-fault 4xx does not trip the breaker
# ---------------------------------------------------------------------------
class TestC7BreakerIgnores4xx:
    def test_provider_unhealthy_classification(self):
        from providers.base import ModelProvider

        class _Err(Exception):
            def __init__(self, status_code):
                super().__init__(f"status {status_code}")
                self.status_code = status_code

        # Use any concrete provider method via the unbound function on the class.
        is_unhealthy = ModelProvider._is_provider_unhealthy_error

        class _Dummy:
            def _extract_status_code(self, e):
                return getattr(e, "status_code", None)

        dummy = _Dummy()
        assert is_unhealthy(dummy, _Err(400)) is False
        assert is_unhealthy(dummy, _Err(404)) is False
        assert is_unhealthy(dummy, _Err(422)) is False
        assert is_unhealthy(dummy, _Err(500)) is True
        assert is_unhealthy(dummy, _Err(503)) is True
        assert is_unhealthy(dummy, _Err(429)) is True  # rate limit counts


# ---------------------------------------------------------------------------
# F-4: log-injection sanitization
# ---------------------------------------------------------------------------
class TestF4LogSanitization:
    def test_control_chars_escaped(self):
        from handlers.tool_handlers import _sanitize_for_log

        out = _sanitize_for_log("evil\r\nFORGED: line")
        assert "\n" not in out and "\r" not in out
        assert "\\n" in out

    def test_length_capped(self):
        from handlers.tool_handlers import _sanitize_for_log

        out = _sanitize_for_log("A" * 500, max_len=32)
        assert len(out) <= 32 + len("...(truncated)")


# ---------------------------------------------------------------------------
# F-2: redaction filter scrubs credential-shaped substrings
# ---------------------------------------------------------------------------
class TestF2Redaction:
    def test_filter_redacts_keys(self):
        import logging

        from utils.logging_setup import RedactingFilter

        f = RedactingFilter()
        rec = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="key is sk-abcdefghijklmnopqrstuvwx and done",
            args=(),
            exc_info=None,
        )
        assert f.filter(rec) is True
        assert "sk-abcdefghijklmnopqrstuvwx" not in rec.getMessage()
        assert "REDACTED" in rec.getMessage()


# ---------------------------------------------------------------------------
# G-1: non-string continuation_id validated cleanly
# ---------------------------------------------------------------------------
class TestG1UuidGuard:
    def test_non_string_returns_false(self):
        from utils.conversation_store import _is_valid_uuid

        for bad in (123, ["x"], {"a": 1}, 4.5, None):
            assert _is_valid_uuid(bad) is False


# ---------------------------------------------------------------------------
# G-2: malformed issues_found is normalized, not crashed on
# ---------------------------------------------------------------------------
class TestG2IssuesFoundNormalization:
    def test_none_and_non_string_severity_coerced(self):
        from tools.shared.base_models import WorkflowRequest

        req = WorkflowRequest(
            step="s",
            step_number=1,
            total_steps=1,
            next_step_required=False,
            findings="f",
            issues_found=[
                {"severity": None, "description": "x"},
                {"severity": 3, "description": "y"},
                "not-a-dict",
                {"description": "no severity key"},
            ],
        )
        # non-dict dropped
        assert len(req.issues_found) == 3
        # every surviving item has a string severity that .upper() won't crash on
        for item in req.issues_found:
            sev = item.get("severity", "unknown")
            assert isinstance(sev, str)
            sev.upper()
