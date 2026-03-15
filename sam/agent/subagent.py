"""Sub-agent system: spawn isolated child agents for parallel research.

A sub-agent gets its own ConversationHistory and a read-only tool set.
It runs a single turn and returns the result, without polluting the
parent agent's context window.
"""

from __future__ import annotations

from pathlib import Path

from sam.agent.history import ConversationHistory
from sam.agent.loop import AgentLoop
from sam.config import Settings
from sam.models.provider import ModelProvider
from sam.tools.base import READONLY_TOOLS, Tool, ToolRegistry, ToolResult


class SubAgentTool(Tool):
    """Spawn a sub-agent to research a question using read-only tools."""

    def __init__(self, settings: Settings, provider: ModelProvider, parent_tools: ToolRegistry) -> None:
        self._settings = settings
        self._provider = provider
        self._parent_tools = parent_tools

    @property
    def name(self) -> str:
        return "sub_agent"

    @property
    def description(self) -> str:
        return (
            "Spawn a sub-agent to research a question in the codebase. "
            "The sub-agent has its own context and uses read-only tools "
            "(read_file, grep, glob, list_directory, git_status, git_diff, web_fetch, web_search). "
            "Use this for exploring code, searching documentation, or answering "
            "questions that require reading many files without filling up your context. "
            "Returns the sub-agent's final answer."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The research question or exploration task for the sub-agent",
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Max iterations for the sub-agent (default: 10)",
                },
            },
            "required": ["task"],
        }

    async def execute(self, task: str, max_iterations: int = 10, **kwargs) -> ToolResult:
        from sam.ui.console import print_info

        print_info(f"  Sub-agent spawned: {task[:80]}...")

        # Build a read-only tool registry from parent's tools
        readonly_tools = ToolRegistry()
        for tool in self._parent_tools.all_tools():
            if tool.name in READONLY_TOOLS:
                readonly_tools.register(tool)

        # Create isolated history with same context window
        child_history = ConversationHistory(
            context_window=self._settings.context_window
        )

        # Create a child settings with reduced iterations
        child_settings = self._settings.model_copy()
        child_settings.max_iterations = min(max_iterations, 15)

        # Create the sub-agent loop
        child_agent = AgentLoop(
            settings=child_settings,
            provider=self._provider,
            tools=readonly_tools,
            history=child_history,
        )
        # Force plan mode so it can't write
        child_agent.plan_mode = True

        try:
            result = await child_agent.run_turn(
                f"You are a research sub-agent. Answer this question thoroughly "
                f"by exploring the codebase with your tools:\n\n{task}"
            )
        except Exception as e:
            return ToolResult(output=f"Sub-agent failed: {e}", error=True)

        print_info("  Sub-agent completed.")

        if not result:
            return ToolResult(output="Sub-agent returned no response.", error=True)

        # Truncate very long results
        if len(result) > 8000:
            result = result[:8000] + "\n... (sub-agent response truncated)"

        return ToolResult(output=result)
