"""Tests for mapping ``thinking_mode`` onto a provider's reasoning effort.

Kimi K3 is the motivating case: it accepts ``low``/``high``/``max`` and has no
``medium``, while the tool layer speaks ``minimal``/``low``/``medium``/``high``/
``max``. The endpoint answers HTTP 200 for an effort it does not recognise and
then reasons less than it would at ``low``, so forwarding an unsupported value
verbatim degrades output with nothing in the response to show for it.
"""

import unittest
from unittest.mock import Mock

from providers.openai_compatible import OpenAICompatibleProvider, _resolve_reasoning_effort
from providers.shared import ModelCapabilities, ProviderType


def _caps(supported=None, default=None):
    return ModelCapabilities(
        provider=ProviderType.CUSTOM,
        model_name="k3",
        friendly_name="Kimi K3",
        context_window=1048576,
        max_output_tokens=65536,
        supports_extended_thinking=True,
        supported_reasoning_efforts=supported,
        default_reasoning_effort=default,
    )


KIMI = ["low", "high", "max"]


class TestResolveReasoningEffort(unittest.TestCase):
    def test_returns_none_when_model_declares_no_vocabulary(self):
        """The parameter stays off the wire for every provider that would reject it."""
        self.assertIsNone(_resolve_reasoning_effort(_caps(), "high"))
        self.assertIsNone(_resolve_reasoning_effort(_caps(supported=[]), "high"))

    def test_returns_none_for_missing_capabilities(self):
        self.assertIsNone(_resolve_reasoning_effort(None, "high"))

    def test_exact_match_passes_through(self):
        for effort in KIMI:
            self.assertEqual(_resolve_reasoning_effort(_caps(KIMI), effort), effort)

    def test_unsupported_depth_clamps_to_nearest(self):
        """Kimi has no 'minimal' and no 'medium'; both must land on a real rung."""
        self.assertEqual(_resolve_reasoning_effort(_caps(KIMI), "minimal"), "low")

    def test_exact_tie_resolves_upward(self):
        """'medium' sits equidistant between low and high, and must not round down.

        Rounding down would make an explicit medium request weaker than the
        depth the endpoint applies on its own.
        """
        self.assertEqual(_resolve_reasoning_effort(_caps(KIMI), "medium"), "high")

    def test_falls_back_to_declared_default(self):
        self.assertEqual(_resolve_reasoning_effort(_caps(KIMI, default="high"), None), "high")
        self.assertEqual(_resolve_reasoning_effort(_caps(KIMI, default="low"), ""), "low")

    def test_no_request_and_no_default_sends_nothing(self):
        """Absent both, let the endpoint apply its own default."""
        self.assertIsNone(_resolve_reasoning_effort(_caps(KIMI), None))

    def test_unrecognised_request_never_reaches_the_wire(self):
        """A junk thinking_mode falls back to the default, never passes through.

        Measured against the live endpoint: an unrecognised effort returns 200
        and produces fewer reasoning tokens than 'low', so forwarding it is
        strictly worse than the declared default.
        """
        self.assertEqual(_resolve_reasoning_effort(_caps(KIMI, default="high"), "bogus"), "high")
        self.assertIsNone(_resolve_reasoning_effort(_caps(KIMI), "bogus"))

    def test_case_and_whitespace_are_normalised(self):
        self.assertEqual(_resolve_reasoning_effort(_caps(KIMI), "  MAX "), "max")

    def test_vocabulary_outside_the_ladder_is_left_alone(self):
        """A model using its own words gets its default, not a guessed mapping."""
        caps = _caps(supported=["fast", "thorough"], default="fast")
        self.assertEqual(_resolve_reasoning_effort(caps, "fast"), "fast")
        self.assertEqual(_resolve_reasoning_effort(caps, "medium"), "fast")

    def test_default_outside_vocabulary_is_not_sent(self):
        caps = _caps(supported=KIMI, default="medium")
        self.assertIsNone(_resolve_reasoning_effort(caps, "bogus"))


class TestReasoningEffortReachesCompletionParams(unittest.TestCase):
    """The mapping is only useful if it survives the kwargs allow-list.

    ``thinking_mode`` arrives in kwargs and is filtered out there, which is why
    it was accepted and silently discarded before this change.
    """

    def setUp(self):
        class TestProvider(OpenAICompatibleProvider):
            FRIENDLY_NAME = "Test"

            def get_capabilities(self, model_name):
                return _caps(KIMI, default="high")

            def get_provider_type(self):
                return ProviderType.CUSTOM

            def validate_model_name(self, model_name):
                return True

            def list_models(self, **kwargs):
                return ["k3"]

        self.provider = TestProvider("test-key")

    def _captured_params(self, **kwargs):
        captured = {}

        def _create(**params):
            captured.update(params)
            message = Mock()
            message.content = "ok"
            choice = Mock()
            choice.message = message
            choice.finish_reason = "stop"
            response = Mock()
            response.choices = [choice]
            response.model = "k3"
            response.id = "test"
            response.created = 0
            response.usage = Mock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            return response

        self.provider.client.chat.completions.create = _create
        self.provider.generate_content(prompt="hi", model_name="k3", **kwargs)
        return captured

    def test_thinking_mode_becomes_reasoning_effort(self):
        params = self._captured_params(thinking_mode="minimal")
        self.assertEqual(params.get("reasoning_effort"), "low")

    def test_thinking_mode_is_not_forwarded_verbatim(self):
        params = self._captured_params(thinking_mode="medium")
        self.assertNotIn("thinking_mode", params)
        self.assertEqual(params.get("reasoning_effort"), "high")


if __name__ == "__main__":
    unittest.main()
