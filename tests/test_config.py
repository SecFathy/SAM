"""Tests for configuration and model presets."""

import pytest
from unittest.mock import patch

from sam.config import ModelPreset, Settings


@pytest.fixture(autouse=True)
def _isolate_config():
    """Prevent local config.yaml from interfering with tests."""
    with patch("sam.config._load_config_file", return_value={}):
        ModelPreset.PRESETS = {}
        yield
        ModelPreset.PRESETS = {}


def test_model_preset_resolve_known():
    assert ModelPreset.resolve("qwen-coder") == "Qwen/Qwen2.5-Coder-32B-Instruct"
    assert ModelPreset.resolve("qwen3-coder") == "Qwen/Qwen3-Coder-480B-A35B-Instruct"


def test_model_preset_resolve_passthrough():
    assert ModelPreset.resolve("my-custom-model") == "my-custom-model"


def test_model_preset_context_window():
    assert ModelPreset.context_window("qwen-coder") == 131072
    assert ModelPreset.context_window("unknown-model") == 32768


def test_settings_defaults():
    settings = Settings()
    assert settings.model == "qwen-coder"
    assert settings.api_base == "http://localhost:8000/v1"
    assert settings.max_iterations == 25
    assert settings.temperature == 0.0


def test_settings_model_id():
    settings = Settings(model="qwen-coder")
    assert settings.model_id == "Qwen/Qwen2.5-Coder-32B-Instruct"


def test_settings_custom_model():
    settings = Settings(model="my-org/my-model")
    assert settings.model_id == "my-org/my-model"


def test_settings_condensation_threshold():
    settings = Settings(model="qwen-coder-7b")
    assert settings.condensation_threshold == int(32768 * 0.75)
