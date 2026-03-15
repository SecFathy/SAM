"""Pydantic settings and model configuration with YAML config file support."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

SAM_HOME = Path.home() / ".sam"
SESSIONS_DIR = SAM_HOME / "sessions"
CONFIG_FILENAME = "config.yaml"


def _load_config_file() -> dict[str, Any]:
    """Load config from YAML file.

    Search order:
      1. Current directory
      2. Walk up parent directories (finds project-root config.yaml)
      3. ~/.sam/config.yaml (global fallback)
    """
    # 1. Current directory
    local_config = Path.cwd() / CONFIG_FILENAME
    if local_config.exists():
        return _parse_yaml(local_config)

    # 2. Walk up parent directories to find a project-level config
    for parent in Path.cwd().parents:
        candidate = parent / CONFIG_FILENAME
        if candidate.exists():
            return _parse_yaml(candidate)
        # Stop at filesystem root or home directory
        if parent == Path.home() or parent == parent.parent:
            break

    # 3. Global config (~/.sam/config.yaml)
    global_config = SAM_HOME / CONFIG_FILENAME
    if global_config.exists():
        return _parse_yaml(global_config)

    return {}


def _parse_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML config file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception:
        return {}


class ModelPreset:
    """Known model presets, loaded from config file + built-in defaults."""

    _DEFAULTS: dict[str, dict] = {
        "qwen-coder": {
            "model_id": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "context_window": 131072,
            "description": "Strong default for DGX",
        },
        "qwen3-coder": {
            "model_id": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "context_window": 262144,
            "description": "Best agentic coding model (MoE)",
        },
        "deepseek-coder": {
            "model_id": "deepseek-ai/DeepSeek-Coder-V2-Instruct",
            "context_window": 131072,
            "description": "Alternative strong coder",
        },
        "qwen-coder-7b": {
            "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "context_window": 32768,
            "description": "Lighter, for editor role",
        },
    }

    PRESETS: dict[str, dict] = {}

    @classmethod
    def load(cls) -> None:
        """Load presets from config file, merged with built-in defaults."""
        cls.PRESETS = dict(cls._DEFAULTS)
        config = _load_config_file()
        custom_models = config.get("models", {})
        if isinstance(custom_models, dict):
            for name, info in custom_models.items():
                if isinstance(info, dict) and "model_id" in info:
                    cls.PRESETS[name] = {
                        "model_id": info["model_id"],
                        "context_window": info.get("context_window", 32768),
                        "description": info.get("description", ""),
                    }

    @classmethod
    def resolve(cls, name_or_id: str) -> str:
        """Resolve a preset name to a model ID, or return the string as-is."""
        if not cls.PRESETS:
            cls.load()
        if name_or_id in cls.PRESETS:
            return cls.PRESETS[name_or_id]["model_id"]
        return name_or_id

    @classmethod
    def context_window(cls, name_or_id: str) -> int:
        """Get context window for a preset, default 32K for unknown models."""
        if not cls.PRESETS:
            cls.load()
        if name_or_id in cls.PRESETS:
            return cls.PRESETS[name_or_id]["context_window"]
        for preset in cls.PRESETS.values():
            if preset["model_id"] == name_or_id:
                return preset["context_window"]
        return 32768


class Settings(BaseSettings):
    """SAM configuration loaded from config.yaml + env vars + CLI flags."""

    model_config = {"env_prefix": "SAM_"}

    # Model settings
    model: str = Field(default="", description="Model preset or exact model ID")
    api_base: str = Field(default="", description="vLLM OpenAI-compatible API base URL")
    api_key: str = Field(default="", description="API key (not needed for local vLLM)")

    # Agent settings
    max_iterations: int = Field(default=0, description="Max agent loop iterations per turn")
    temperature: float = Field(default=-1.0, description="Sampling temperature")
    max_tokens: int = Field(default=0, description="Max tokens per response")
    repo_map_tokens: int = Field(default=0, description="Token budget for repo map")
    show_response_time: bool = Field(
        default=False, description="Print LLM response time after each call"
    )
    stream: bool = Field(default=True, description="Stream LLM responses token-by-token")
    hermes_tool_calling: bool = Field(
        default=False,
        description="Use Hermes-style <tool_call> XML instead of native tool calling",
    )
    permission_mode: str = Field(
        default="safe",
        description=(
            "Permission mode: auto (no prompts), safe (confirm writes/shell), ask (confirm all)"
        ),
    )

    # Session
    session_id: Optional[str] = Field(default=None, description="Session ID to resume")

    # Paths
    working_dir: Path = Field(default_factory=Path.cwd, description="Working directory")

    def model_post_init(self, __context: Any) -> None:
        """Merge config file values as defaults under CLI/env overrides."""
        config = _load_config_file()

        # Apply config file values only where no CLI/env override was given
        if not self.model:
            self.model = config.get("model", "qwen-coder")
        if not self.api_base:
            self.api_base = config.get("api_base", "http://localhost:8000/v1")
        if not self.api_key:
            self.api_key = config.get("api_key", "not-needed")
        if self.max_iterations == 0:
            self.max_iterations = config.get("max_iterations", 25)
        if self.temperature < 0:
            self.temperature = config.get("temperature", 0.0)
        if self.max_tokens == 0:
            self.max_tokens = config.get("max_tokens", 4096)
        if self.repo_map_tokens == 0:
            self.repo_map_tokens = config.get("repo_map_tokens", 2048)
        if not self.show_response_time:
            self.show_response_time = config.get("show_response_time", False)
        # stream defaults to True; only override if explicitly set to False in config
        if self.stream and config.get("stream") is False:
            self.stream = False
        # hermes_tool_calling: check config, then auto-detect from model registry
        if not self.hermes_tool_calling:
            if config.get("hermes_tool_calling"):
                self.hermes_tool_calling = True
        # permission_mode: default "safe" unless overridden
        if self.permission_mode == "safe":
            cfg_mode = config.get("permission_mode")
            if cfg_mode in ("auto", "safe", "ask"):
                self.permission_mode = cfg_mode

        # Load model presets
        ModelPreset.load()

    @property
    def model_id(self) -> str:
        return ModelPreset.resolve(self.model)

    @property
    def context_window(self) -> int:
        return ModelPreset.context_window(self.model)

    @property
    def condensation_threshold(self) -> int:
        """Trigger condensation at 75% of context window."""
        return int(self.context_window * 0.75)
