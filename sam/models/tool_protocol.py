"""Hermes-style fallback for models without native tool calling.

When vLLM's native tool calling is unreliable, we inject tool definitions
into the system prompt and parse <tool_call> XML tags from text output.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sam.models.streaming import StreamAccumulator, ToolCallAccumulator


TOOL_PROMPT_TEMPLATE = """You have access to the following tools. To call a tool, respond with a <tool_call> block:

<tool_call>
{{"name": "tool_name", "arguments": {{"arg1": "value1"}}}}
</tool_call>

You can call multiple tools by using multiple <tool_call> blocks.

Available tools:
{tool_definitions}
"""


def format_tool_definitions(tools: list[dict]) -> str:
    """Format tool schemas into a human-readable prompt section."""
    lines = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "")
        desc = func.get("description", "")
        params = func.get("parameters", {})

        lines.append(f"### {name}")
        lines.append(f"{desc}")
        lines.append("")

        props = params.get("properties", {})
        required = set(params.get("required", []))
        if props:
            lines.append("Parameters:")
            for pname, pschema in props.items():
                req = " (required)" if pname in required else ""
                ptype = pschema.get("type", "string")
                pdesc = pschema.get("description", "")
                lines.append(f"  - {pname} ({ptype}){req}: {pdesc}")
            lines.append("")

    return "\n".join(lines)


def inject_tools_into_system(
    system_content: str,
    tools: list[dict],
) -> str:
    """Inject tool definitions into the system prompt for Hermes-style calling."""
    tool_defs = format_tool_definitions(tools)
    tool_section = TOOL_PROMPT_TEMPLATE.format(tool_definitions=tool_defs)
    return system_content + "\n\n" + tool_section


def parse_tool_calls_from_text(text: str) -> tuple[str, list[ToolCallAccumulator]]:
    """Parse <tool_call> blocks from assistant text output.

    Returns:
        Tuple of (clean_text_without_tool_calls, list_of_tool_calls)
    """
    tool_calls = []
    clean_text = text

    # Match <tool_call>...</tool_call> blocks
    pattern = re.compile(
        r"<tool_call>\s*(.*?)\s*</tool_call>",
        re.DOTALL,
    )

    for match in pattern.finditer(text):
        raw = match.group(1).strip()

        # Try to parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to fix common issues
            data = _try_fix_json(raw)
            if data is None:
                continue

        name = data.get("name", "")
        arguments = data.get("arguments", {})

        if name:
            tc = ToolCallAccumulator(
                id=f"call_{uuid.uuid4().hex[:8]}",
                name=name,
                arguments=json.dumps(arguments) if isinstance(arguments, dict) else str(arguments),
            )
            tool_calls.append(tc)

    # Remove tool_call blocks from the text
    clean_text = pattern.sub("", text).strip()

    return clean_text, tool_calls


def convert_accumulator_with_hermes(accumulator: StreamAccumulator) -> StreamAccumulator:
    """Post-process an accumulator to extract Hermes-style tool calls from text."""
    if accumulator.has_tool_calls:
        # Already has native tool calls, don't double-process
        return accumulator

    if not accumulator.content:
        return accumulator

    clean_text, tool_calls = parse_tool_calls_from_text(accumulator.content)

    if tool_calls:
        accumulator.content = clean_text
        for i, tc in enumerate(tool_calls):
            accumulator.tool_calls[i] = tc

    return accumulator


def _try_fix_json(raw: str) -> dict | None:
    """Try to fix malformed JSON from model output."""
    # Strip markdown code fences
    raw = re.sub(r"```json?\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw)
    raw = raw.strip()

    # Try as-is
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try wrapping in braces
    if not raw.startswith("{"):
        try:
            return json.loads("{" + raw + "}")
        except json.JSONDecodeError:
            pass

    # Try fixing trailing commas
    fixed = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    return None
