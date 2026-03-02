"""prompt-toolkit input configuration."""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from sam.config import SAM_HOME

SAM_STYLE = Style.from_dict({
    "prompt": "cyan bold",
    "": "",
})


def create_prompt_session() -> PromptSession:
    """Create a configured prompt-toolkit session with history."""
    history_file = SAM_HOME / "prompt_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    # Key bindings
    bindings = KeyBindings()

    @bindings.add("c-c")
    def _(event):
        """Handle Ctrl+C — cancel current input."""
        event.current_buffer.reset()
        event.app.exit(result="")

    session: PromptSession = PromptSession(
        history=FileHistory(str(history_file)),
        style=SAM_STYLE,
        key_bindings=bindings,
        multiline=False,
        enable_history_search=True,
    )

    return session


async def get_user_input(session: PromptSession, prompt: str = "you> ") -> str | None:
    """Get user input, returning None on EOF."""
    import asyncio

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: session.prompt(prompt),
        )
        return result.strip() if result else ""
    except (EOFError, KeyboardInterrupt):
        return None
