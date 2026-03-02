"""Model presets and registry for known model configurations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Configuration for a known model."""

    model_id: str
    context_window: int
    description: str
    supports_tool_calling: bool = True
    tool_call_parser: str = "hermes"  # hermes, native, none
    recommended_temperature: float = 0.0
    recommended_max_tokens: int = 4096
    editor_model: str | None = None  # For architect/editor split


# Known model configurations
MODEL_REGISTRY: dict[str, ModelConfig] = {
    "qwen-coder": ModelConfig(
        model_id="Qwen/Qwen2.5-Coder-32B-Instruct",
        context_window=131072,
        description="Strong default for DGX — Qwen2.5 Coder 32B",
        supports_tool_calling=True,
        tool_call_parser="hermes",
    ),
    "qwen3-coder": ModelConfig(
        model_id="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        context_window=262144,
        description="Best agentic coding model (MoE, fits on DGX)",
        supports_tool_calling=True,
        tool_call_parser="hermes",
    ),
    "deepseek-coder": ModelConfig(
        model_id="deepseek-ai/DeepSeek-Coder-V2-Instruct",
        context_window=131072,
        description="Alternative strong coder — DeepSeek V2",
        supports_tool_calling=True,
        tool_call_parser="hermes",
    ),
    "qwen-coder-7b": ModelConfig(
        model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
        context_window=32768,
        description="Lighter, for editor role in architect/editor split",
        supports_tool_calling=True,
        tool_call_parser="hermes",
        recommended_max_tokens=2048,
    ),
}


def get_model_config(name_or_id: str) -> ModelConfig | None:
    """Look up a model config by preset name or model ID."""
    if name_or_id in MODEL_REGISTRY:
        return MODEL_REGISTRY[name_or_id]

    # Try matching by model_id
    for config in MODEL_REGISTRY.values():
        if config.model_id == name_or_id:
            return config

    return None


def list_presets() -> list[tuple[str, ModelConfig]]:
    """Return all registered presets."""
    return list(MODEL_REGISTRY.items())
