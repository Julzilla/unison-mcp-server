"""The capabilities guidance must name the CLI actually being spawned."""

import unittest

from clink import get_registry
from clink.constants import CLI_DISPLAY_NAMES
from tools.clink import CLinkTool


class TestAgentCapabilitiesGuidance(unittest.TestCase):
    def setUp(self):
        self.tool = CLinkTool()

    def test_names_the_cli_being_spawned(self):
        for name, display in CLI_DISPLAY_NAMES.items():
            with self.subTest(cli=name):
                self.assertIn(display, self.tool._agent_capabilities_guidance(name))

    def test_no_target_is_told_it_is_gemini(self):
        """The regression. Every target used to receive the same Gemini claim."""
        for name in CLI_DISPLAY_NAMES:
            if name == "gemini":
                continue
            with self.subTest(cli=name):
                self.assertNotIn("Gemini", self.tool._agent_capabilities_guidance(name))

    def test_unknown_client_falls_back_to_its_own_name(self):
        """User-defined clients in ~/.unison/cli_clients still read sensibly."""
        text = self.tool._agent_capabilities_guidance("my-custom-cli")
        self.assertIn("my-custom-cli", text)
        self.assertNotIn("Gemini", text)

    def test_capability_instruction_survives(self):
        text = self.tool._agent_capabilities_guidance("kimi")
        self.assertIn("full suite of", text)
        self.assertIn("without", text)

    def test_every_registered_client_has_a_display_name(self):
        """Guards against a new target being added without one, which would
        make it fall back to a bare key like 'opencode' mid-sentence."""
        for name in get_registry().list_clients():
            with self.subTest(cli=name):
                self.assertIn(name, CLI_DISPLAY_NAMES)


if __name__ == "__main__":
    unittest.main()
