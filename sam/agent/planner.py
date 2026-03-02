"""Architect/editor two-model split.

The architect (larger model) plans the changes, then the editor
(smaller model) executes them with tool calls. This compensates
for weaker models by separating planning from execution.
"""

from __future__ import annotations

from sam.agent.history import ConversationHistory
from sam.config import Settings
from sam.models.provider import ModelProvider
from sam.tools.base import ToolRegistry
from sam.ui.console import console, print_assistant, print_info


ARCHITECT_SYSTEM = """You are the architect. Your role is to analyze the user's request and create a detailed plan.

You do NOT execute changes directly. Instead, produce a clear, step-by-step plan that specifies:
1. Which files need to be read
2. What changes need to be made (with specific search/replace snippets)
3. What commands need to be run for verification

Your plan will be handed to an editor agent that executes it with tools.

Working directory: {working_dir}

{repo_map}

Be specific and precise. Include exact code snippets for changes."""

EDITOR_SYSTEM = """You are the editor. Execute the plan provided by the architect.

Use the available tools to:
1. Read the files mentioned in the plan
2. Make the exact changes specified
3. Run any verification commands

Follow the plan precisely. If you encounter issues, note them but try to complete as much as possible.

Working directory: {working_dir}"""


class PlannerAgent:
    """Two-model architect/editor split for complex tasks."""

    def __init__(
        self,
        settings: Settings,
        architect_provider: ModelProvider,
        editor_provider: ModelProvider,
        tools: ToolRegistry,
    ) -> None:
        self.settings = settings
        self.architect = architect_provider
        self.editor = editor_provider
        self.tools = tools

    async def plan_and_execute(
        self,
        user_message: str,
        repo_map: str = "",
    ) -> str:
        """Have the architect plan, then the editor execute."""
        # Phase 1: Architect creates the plan
        print_info("Architect is planning...")

        architect_system = ARCHITECT_SYSTEM.format(
            working_dir=str(self.settings.working_dir),
            repo_map=repo_map or "No repo map available.",
        )

        architect_messages = [
            {"role": "system", "content": architect_system},
            {"role": "user", "content": user_message},
        ]

        plan_result = await self.architect.chat_complete(architect_messages)
        plan = plan_result.content

        if plan:
            console.print("\n[bold cyan]Architect's Plan:[/bold cyan]")
            print_assistant(plan)
            console.print()

        # Phase 2: Editor executes the plan
        print_info("Editor is executing the plan...")

        from sam.agent.loop import AgentLoop

        editor_history = ConversationHistory(context_window=self.settings.context_window)

        editor_agent = AgentLoop(
            settings=self.settings,
            provider=self.editor,
            tools=self.tools,
            history=editor_history,
        )

        # Override system prompt for editor
        editor_system = EDITOR_SYSTEM.format(
            working_dir=str(self.settings.working_dir),
        )
        editor_history.add_system(editor_system)

        # Give the editor the plan as context
        editor_prompt = f"""The architect has created this plan for the following user request:

USER REQUEST: {user_message}

ARCHITECT'S PLAN:
{plan}

Please execute this plan step by step using the available tools."""

        result = await editor_agent.run_turn(editor_prompt, repo_map="")
        return result
