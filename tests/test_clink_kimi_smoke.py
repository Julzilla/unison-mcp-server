"""Smoke tests for the Kimi Code clink integration.

Validates the contract between Unison and Kimi Code (https://www.kimi.com/code).

Fixture provenance matters here, so it is stated per-fixture below. The happy
path and multiline fixtures are verbatim stdout captured from kimi 0.27.0 on
Windows, authenticated via ``KIMI_MODEL_*`` env vars against
``api.kimi.com/coding/``. Fixtures marked SYNTHETIC were hand-written to cover
a branch and are labelled as such — none of them assert that Kimi actually
produces that shape. Mocked binary; no real Kimi invocation in CI.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from clink import get_registry
from clink.agents import create_agent
from clink.agents.kimi import KimiAgent
from clink.constants import CLINK_DEPTH_ENV_VAR
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParserError
from clink.parsers.kimi import KimiJSONLParser
from tools.clink import _check_recursion_guard
from tools.shared.exceptions import ToolExecutionError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# REAL — verbatim stdout from kimi 0.27.0:
#   kimi --prompt "What is 2+2? Answer with one number only." \
#        --output-format stream-json
# Note the meta line carries a `content` field of its own. That is the whole
# reason the parser filters on role.
KIMI_HAPPY_PATH_FIXTURE = (
    '{"role":"assistant","content":"4"}\n'
    '{"role":"meta","type":"session.resume_hint",'
    '"session_id":"session_63f60926-cbeb-411d-ada8-a3367a2294c8",'
    '"command":"kimi -r session_63f60926-cbeb-411d-ada8-a3367a2294c8",'
    '"content":"To resume this session: kimi -r session_63f60926-cbeb-411d-ada8-a3367a2294c8"}\n'
)

# REAL — same invocation shape, prompt was the bat-and-ball problem. Confirms
# multi-line answers survive intact and that a reasoning-heavy prompt still
# produces no reasoning_content field.
KIMI_MULTILINE_FIXTURE = (
    '{"role":"assistant","content":"Let the ball cost $x.\\n\\nThen the bat costs $x + $1.00.'
    '\\n\\n2x = 0.10\\n\\nx = 0.05\\n\\nSo the ball costs **$0.05**."}\n'
    '{"role":"meta","type":"session.resume_hint","session_id":"session_2fd547ff-b009-4daa-b7a6-985a342e818b",'
    '"command":"kimi -r session_2fd547ff-b009-4daa-b7a6-985a342e818b",'
    '"content":"To resume this session: kimi -r session_2fd547ff-b009-4daa-b7a6-985a342e818b"}\n'
)

# REAL — the CLI exiting 0 having emitted only session bookkeeping. This is the
# blank-result case the parser exists to turn into an error.
KIMI_META_ONLY_FIXTURE = (
    '{"role":"meta","type":"session.resume_hint","session_id":"session_deadbeef",'
    '"content":"To resume this session: kimi -r session_deadbeef"}\n'
)

# SYNTHETIC — content delivered as a block list rather than a bare string.
# Not observed on 0.27.0; covers the defensive branch only.
KIMI_BLOCK_CONTENT_FIXTURE = (
    '{"role":"assistant","content":[{"type":"text","text":"first"},{"type":"text","text":"second"}]}\n'
)

# SYNTHETIC — reasoning without an answer. See the parser docstring: kimi 0.27.0
# emits no reasoning_content at all, so this covers forward-compatibility, NOT
# observed behaviour.
KIMI_REASONING_ONLY_FIXTURE = (
    '{"role":"assistant","content":"","reasoning_content":"thinking hard about it",'
    '"finish_reason":"length"}\n'
)

# REAL — stderr from a model name absent from config.toml. This is the failure
# every `-m` value produces under KIMI_MODEL_* auth.
KIMI_CONFIG_ERROR_STDERR = (
    'error: failed to run prompt: config.invalid: Model "k3" is not configured '
    "in config.toml. Add a [models.\"k3\"] entry with max_context_size."
)


def _make_client(name: str = "kimi") -> ResolvedCLIClient:
    role = ResolvedCLIRole(
        name="default",
        prompt_path=Path("systemprompts/clink/default.txt").resolve(),
        role_args=[],
    )
    return ResolvedCLIClient(
        name=name,
        executable=["kimi"],
        internal_args=["--output-format", "stream-json"],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="kimi_jsonl",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestKimiParser:
    def test_happy_path_extracts_answer(self) -> None:
        parsed = KimiJSONLParser().parse(KIMI_HAPPY_PATH_FIXTURE, "")
        assert parsed.content == "4"

    def test_meta_resume_text_does_not_leak_into_answer(self) -> None:
        """The meta line has its own `content`. Keying on content alone would
        append "To resume this session: ..." to every single answer."""
        parsed = KimiJSONLParser().parse(KIMI_HAPPY_PATH_FIXTURE, "")
        assert "resume" not in parsed.content.lower()
        assert parsed.content == "4"

    def test_session_id_captured(self) -> None:
        parsed = KimiJSONLParser().parse(KIMI_HAPPY_PATH_FIXTURE, "")
        assert parsed.metadata["session_id"] == "session_63f60926-cbeb-411d-ada8-a3367a2294c8"

    def test_multiline_answer_preserved(self) -> None:
        parsed = KimiJSONLParser().parse(KIMI_MULTILINE_FIXTURE, "")
        assert "$0.05" in parsed.content
        assert "\n" in parsed.content
        assert "resume" not in parsed.content.lower()

    def test_real_output_reports_zero_reasoning(self) -> None:
        """Guards the docstring claim: 0.27.0 emits no reasoning_content."""
        parsed = KimiJSONLParser().parse(KIMI_MULTILINE_FIXTURE, "")
        assert parsed.metadata["reasoning_chars"] == 0

    def test_meta_only_raises_rather_than_returning_blank(self) -> None:
        with pytest.raises(ParserError, match="no assistant content"):
            KimiJSONLParser().parse(KIMI_META_ONLY_FIXTURE, "")

    def test_empty_stdout_raises(self) -> None:
        with pytest.raises(ParserError, match="empty stdout"):
            KimiJSONLParser().parse("", "")

    def test_non_json_stdout_names_the_output_format_flag(self) -> None:
        with pytest.raises(ParserError, match="--output-format stream-json"):
            KimiJSONLParser().parse("plain text, no JSON here", "")

    def test_config_error_stderr_surfaces_in_metadata(self) -> None:
        parsed = KimiJSONLParser().parse(KIMI_HAPPY_PATH_FIXTURE, KIMI_CONFIG_ERROR_STDERR)
        assert "not configured in config.toml" in parsed.metadata["stderr"]

    def test_malformed_lines_skipped(self) -> None:
        parsed = KimiJSONLParser().parse("not json\n{oops\n" + KIMI_HAPPY_PATH_FIXTURE, "")
        assert parsed.content == "4"

    def test_block_content_list_concatenated(self) -> None:
        parsed = KimiJSONLParser().parse(KIMI_BLOCK_CONTENT_FIXTURE, "")
        assert parsed.content == "first\nsecond"

    def test_reasoning_without_answer_raises(self) -> None:
        with pytest.raises(ParserError, match="reasoning and no answer"):
            KimiJSONLParser().parse(KIMI_REASONING_ONLY_FIXTURE, "")

    def test_parser_name(self) -> None:
        assert KimiJSONLParser.name == "kimi_jsonl"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class TestKimiAgentClass:
    def test_prompt_travels_on_argv_not_stdin(self) -> None:
        """Kimi rejects --output-format outside prompt mode, and prompt mode
        means --prompt on argv. stdin is not an option."""
        plan = KimiAgent(_make_client()).prepare_invocation("hi", [], [])
        assert plan.kind == "argv"
        assert plan.flag == "--prompt"

    def test_images_do_not_change_transport(self) -> None:
        plan = KimiAgent(_make_client()).prepare_invocation("hi", [], ["/tmp/x.png"])
        assert plan.kind == "argv"

    def test_no_read_only_args(self) -> None:
        """Kimi has no read-only flag; enforcement is config.toml permission
        rules plus the snapshot diff. See the README note."""
        assert KimiAgent(_make_client()).get_read_only_args() == []

    def test_render_model_args_uses_m_flag(self) -> None:
        assert KimiAgent(_make_client()).render_model_args("kimi-code/k3") == ["-m", "kimi-code/k3"]


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


class TestKimiRegistryWiring:
    def test_kimi_in_internal_defaults(self) -> None:
        from clink.constants import INTERNAL_DEFAULTS

        assert "kimi" in INTERNAL_DEFAULTS
        assert INTERNAL_DEFAULTS["kimi"].parser == "kimi_jsonl"

    def test_stream_json_is_a_default_arg(self) -> None:
        from clink.constants import INTERNAL_DEFAULTS

        args = INTERNAL_DEFAULTS["kimi"].additional_args
        assert "--output-format" in args
        assert "stream-json" in args

    def test_kimi_in_agent_factory(self) -> None:
        from clink.agents import _AGENTS  # type: ignore[attr-defined]

        assert _AGENTS["kimi"] is KimiAgent

    def test_kimi_parser_registered(self) -> None:
        from clink.parsers import _PARSER_CLASSES  # type: ignore[attr-defined]

        assert _PARSER_CLASSES["kimi_jsonl"] is KimiJSONLParser

    def test_registry_loads_kimi_manifest(self) -> None:
        registry = get_registry()
        assert "kimi" in registry.list_clients()
        client = registry.get_client("kimi")
        assert client.parser == "kimi_jsonl"
        assert set(registry.list_roles("kimi")) >= {"default", "planner", "codereviewer"}

    def test_no_supported_models_allowlist(self) -> None:
        """Regression guard.

        `-m` resolves against [models."..."] keys in the user's own
        config.toml, and those keys are namespaced per provider
        (kimi-code/k3, not k3). Under KIMI_MODEL_* env auth there is no model
        table at all and every -m value fails. Any list shipped here would
        therefore reject working models and admit broken ones, and
        tools/clink.py enforces the list whenever it is non-empty.
        """
        assert get_registry().get_client("kimi").supported_models == []


# ---------------------------------------------------------------------------
# End to end, mocked subprocess
# ---------------------------------------------------------------------------


class _StubProcess:
    def __init__(self, *, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.received_stdin: bytes | None = None

    async def communicate(self, stdin_data: bytes | None = None):
        self.received_stdin = stdin_data
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


class TestKimiEndToEnd:
    @staticmethod
    def _patch(monkeypatch, process: _StubProcess) -> list[str]:
        captured: list[str] = []

        async def fake_exec(*args, **_kw):
            captured.extend(args)
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        return captured

    @pytest.mark.asyncio
    async def test_happy_path_e2e(self, monkeypatch) -> None:
        client = get_registry().get_client("kimi")
        agent = create_agent(client)
        process = _StubProcess(stdout=KIMI_HAPPY_PATH_FIXTURE.encode("utf-8"))
        captured = self._patch(monkeypatch, process)

        result = await agent.run(role=client.roles["default"], prompt="hi", files=[], images=[])

        assert "--prompt" in captured
        assert captured[captured.index("--prompt") + 1].endswith("hi")
        assert "--output-format" in captured
        assert "stream-json" in captured
        assert result.parsed.content == "4"

    @pytest.mark.asyncio
    async def test_stdin_stays_empty_under_argv_transport(self, monkeypatch) -> None:
        client = get_registry().get_client("kimi")
        agent = create_agent(client)
        process = _StubProcess(stdout=KIMI_HAPPY_PATH_FIXTURE.encode("utf-8"))
        self._patch(monkeypatch, process)

        await agent.run(role=client.roles["default"], prompt="hi", files=[], images=[])

        assert process.received_stdin == b""

    @pytest.mark.asyncio
    async def test_model_emitted_as_m_flag(self, monkeypatch) -> None:
        client = get_registry().get_client("kimi")
        agent = create_agent(client)
        process = _StubProcess(stdout=KIMI_HAPPY_PATH_FIXTURE.encode("utf-8"))
        captured = self._patch(monkeypatch, process)

        await agent.run(
            role=client.roles["default"],
            prompt="hi",
            files=[],
            images=[],
            model="kimi-code/k3",
        )

        assert "-m" in captured
        assert captured[captured.index("-m") + 1] == "kimi-code/k3"

    @pytest.mark.asyncio
    async def test_blank_output_raises_rather_than_succeeding(self, monkeypatch) -> None:
        """A run that exits 0 with only bookkeeping must not read as success."""
        client = get_registry().get_client("kimi")
        agent = create_agent(client)
        process = _StubProcess(stdout=KIMI_META_ONLY_FIXTURE.encode("utf-8"))
        self._patch(monkeypatch, process)

        with pytest.raises(Exception, match="no assistant content"):
            await agent.run(role=client.roles["default"], prompt="hi", files=[], images=[])


# ---------------------------------------------------------------------------
# Recursion guard
# ---------------------------------------------------------------------------


class TestKimiRecursionGuard:
    def test_guard_fires_at_depth_2(self, monkeypatch) -> None:
        monkeypatch.setenv(CLINK_DEPTH_ENV_VAR, "2")
        with pytest.raises(ToolExecutionError, match="recursion limit"):
            _check_recursion_guard()

    def test_normal_invocation_passes_guard(self, monkeypatch) -> None:
        monkeypatch.delenv(CLINK_DEPTH_ENV_VAR, raising=False)
        _check_recursion_guard()

    def test_depth_propagates_to_child_env(self) -> None:
        env = KimiAgent(_make_client())._build_environment()
        assert env[CLINK_DEPTH_ENV_VAR] == "1"
