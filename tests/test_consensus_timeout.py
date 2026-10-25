"""CONSENSUS_MODEL_TIMEOUT_SECONDS overrides the per-model consensus timeout."""

from unittest.mock import patch

import pytest

from tools.consensus import DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS, _consensus_model_timeout


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
        ("", DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
        ("300", 300.0),
        (" 450.5 ", 450.5),
        ("abc", DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
        ("0", DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
        ("-30", DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
        ("inf", DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
        ("1e999", DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
        ("nan", DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS),
    ],
)
def test_consensus_model_timeout(raw, expected):
    with patch("tools.consensus.get_env", return_value=raw):
        assert _consensus_model_timeout() == expected


def test_default_is_unchanged_from_upstream():
    assert DEFAULT_CONSENSUS_MODEL_TIMEOUT_SECONDS == 120.0
