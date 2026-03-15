"""Textual-based TUI for SAM — Claude Code-like full terminal UI."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)


class StatusBar(Static):
    """Bottom status bar showing model, tokens, mode."""

    model_name: reactive[str] = reactive("")
    token_info: reactive[str] = reactive("0 / 0")
    mode: reactive[str] = reactive("NORMAL")
    session_id: reactive[str] = reactive("")

    def render(self) -> Text:
        mode_color = "yellow" if "PLAN" in self.mode else "green"
        text = Text()
        text.append(" SAM ", style="bold white on dark_green")
        text.append("  ")
        text.append(self.model_name, style="cyan")
        text.append("  |  ", style="dim")
        text.append(f"Tokens: {self.token_info}", style="dim cyan")
        text.append("  |  ", style="dim")
        text.append(self.mode, style=f"bold {mode_color}")
        if self.session_id:
            text.append("  |  ", style="dim")
            text.append(self.session_id[:8], style="dim")
        return text


class ChatMessage(Static):
    """A single chat message (user or assistant)."""

    def __init__(self, content: str, role: str = "assistant", **kwargs) -> None:
        super().__init__(**kwargs)
        self.content = content
        self.role = role

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Static(
                Text.from_markup(f"[bold bright_cyan]You[/bold bright_cyan]"),
                classes="msg-header user-header",
            )
            yield Static(self.content, classes="msg-body user-body")
        elif self.role == "assistant":
            yield Static(
                Text.from_markup(f"[bold bright_green]SAM[/bold bright_green]"),
                classes="msg-header assistant-header",
            )
            log = RichLog(markup=True, wrap=True, classes="msg-body assistant-body")
            yield log
        elif self.role == "tool":
            yield Static(
                Text.from_markup(f"[bold magenta]Tool[/bold magenta] [dim]{self.content}[/dim]"),
                classes="msg-header tool-header",
            )
        elif self.role == "tool_result":
            yield Static(self.content, classes="msg-body tool-body")
        elif self.role == "error":
            yield Static(
                Text.from_markup(f"[bold red]Error[/bold red]"),
                classes="msg-header",
            )
            yield Static(self.content, classes="msg-body error-body")
        elif self.role == "info":
            yield Static(
                Text.from_markup(f"[dim cyan]{self.content}[/dim cyan]"),
                classes="msg-info",
            )

    def on_mount(self) -> None:
        if self.role == "assistant" and self.content:
            try:
                log = self.query_one(RichLog)
                md = Markdown(self.content, code_theme="monokai")
                log.write(md)
            except NoMatches:
                pass


class ThinkingIndicator(Static):
    """Animated thinking indicator."""

    def render(self) -> Text:
        return Text.from_markup("[dim italic green]Thinking...[/dim italic green]")


class SAMApp(App):
    """SAM Textual TUI Application."""

    CSS = """
    Screen {
        background: $background;
    }

    #chat-scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        padding: 0 1;
    }

    #chat-container {
        height: auto;
        padding: 0 0;
    }

    ChatMessage {
        height: auto;
        margin: 0 0 1 0;
        padding: 0;
    }

    .msg-header {
        height: 1;
        padding: 0 1;
    }

    .user-header {
        background: #1a3a4a;
    }

    .assistant-header {
        background: #1a3a2a;
    }

    .tool-header {
        background: #2a2a3a;
    }

    .msg-body {
        height: auto;
        padding: 0 1 0 3;
    }

    .user-body {
        color: $text;
    }

    .assistant-body {
        color: #90ee90;
        height: auto;
        max-height: 100%;
    }

    .tool-body {
        color: $text-muted;
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }

    .error-body {
        color: red;
    }

    .msg-info {
        height: 1;
        padding: 0 1;
    }

    ThinkingIndicator {
        height: 1;
        padding: 0 1;
    }

    #input-area {
        height: 3;
        dock: bottom;
        padding: 0 1;
        background: $surface;
    }

    #prompt-input {
        height: 1;
        border: tall $accent;
    }

    #prompt-input:focus {
        border: tall $success;
    }

    StatusBar {
        height: 1;
        dock: bottom;
        background: #1a2a1a;
        padding: 0 0;
    }

    Header {
        height: 1;
        background: #0a2a0a;
        color: $text;
    }
    """

    TITLE = "SAM"
    SUB_TITLE = "Smart Agentic Model"

    BINDINGS = [
        Binding("ctrl+c", "cancel", "Cancel", show=True),
        Binding("ctrl+d", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("escape", "focus_input", "Focus Input", show=False),
    ]

    def __init__(self, settings=None, **kwargs):
        super().__init__(**kwargs)
        self._settings = settings
        self._agent = None
        self._sess_mgr = None
        self._session_id = None
        self._repo_map = ""
        self._is_processing = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="chat-scroll"):
            yield Vertical(id="chat-container")
        with Horizontal(id="input-area"):
            yield Input(
                placeholder="Ask SAM anything... (type /help for commands)",
                id="prompt-input",
            )
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the agent when the app mounts."""
        self._add_info("Starting SAM...")
        # Run setup in background so UI renders immediately
        self._setup_agent()

    @work(thread=False)
    async def _setup_agent(self) -> None:
        """Set up agent, session, and repo map."""
        from sam.cli import _build_agent
        from sam.session.manager import SessionManager

        settings = self._settings
        if settings is None:
            from sam.config import Settings
            settings = Settings()
            self._settings = settings

        # Input function for ask_user tool — posts to the TUI
        async def _tui_input_fn(question: str) -> str:
            self._add_info(f"SAM asks: {question}")
            # For now, use a simple approach
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: input("❯ "))

        # Session
        self._sess_mgr = SessionManager(settings)
        self._session_id, conv_history = self._sess_mgr.get_or_create()

        # Agent
        self._agent = _build_agent(
            settings,
            input_fn=_tui_input_fn,
            history=conv_history,
        )

        # Repo map
        try:
            from sam.repo.mapper import RepoMapper
            mapper = RepoMapper(settings.working_dir, token_budget=settings.repo_map_tokens)
            self._repo_map = mapper.generate()
        except Exception:
            pass

        # Update status bar
        status = self.query_one("#status-bar", StatusBar)
        status.model_name = settings.model_id
        status.session_id = self._session_id or ""
        status.mode = "PLAN" if self._agent.plan_mode else "NORMAL"

        # Welcome message
        self._add_info(f"Model: {settings.model_id}")
        self._add_info(f"Working directory: {settings.working_dir}")
        self._add_info(f"Session: {(self._session_id or 'new')[:8]}")
        self._add_info("Type /help for commands. Ctrl+D to quit.")

        self.query_one("#prompt-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input."""
        user_input = event.value.strip()
        if not user_input:
            return

        event.input.value = ""

        if self._is_processing:
            self._add_info("Still processing... please wait.")
            return

        # Handle slash commands
        cmd = user_input.lower()

        if cmd in ("/exit", "/quit"):
            self._save_session()
            self.exit()
            return

        if cmd == "/clear":
            self.action_clear_chat()
            return

        if cmd == "/help":
            self._show_help()
            return

        if cmd == "/plan":
            if self._agent:
                self._agent.plan_mode = not self._agent.plan_mode
                mode = "PLAN (read-only)" if self._agent.plan_mode else "NORMAL"
                self._add_info(f"Mode: {mode}")
                status = self.query_one("#status-bar", StatusBar)
                status.mode = mode
            return

        if cmd == "/reset":
            if self._sess_mgr:
                self._session_id, conv_history = self._sess_mgr.create_session()
                from sam.cli import _build_agent
                self._agent = _build_agent(
                    self._settings, history=conv_history
                )
                self.action_clear_chat()
                self._add_info(f"Reset. New session: {self._session_id[:8]}")
                status = self.query_one("#status-bar", StatusBar)
                status.session_id = self._session_id or ""
            return

        if cmd == "/model":
            if self._settings:
                self._add_info(f"Model: {self._settings.model_id}")
                self._add_info(f"API: {self._settings.api_base}")
            return

        if cmd == "/status":
            self._show_status()
            return

        if cmd.startswith("/"):
            # Check skills
            from sam.skills import SkillRegistry
            skill_name = cmd[1:]
            skills = SkillRegistry()
            skill = skills.get(skill_name)
            if skill:
                self._add_user_message(f"/{skill_name}")
                self._run_agent_turn(skill.prompt)
                return
            self._add_info(f"Unknown command: {cmd} (type /help)")
            return

        # Regular message
        self._add_user_message(user_input)
        self._run_agent_turn(user_input)

    @work(thread=False)
    async def _run_agent_turn(self, message: str) -> None:
        """Run an agent turn in background."""
        if not self._agent:
            self._add_info("Agent not ready yet...")
            return

        self._is_processing = True
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.placeholder = "SAM is thinking..."

        # Add thinking indicator
        container = self.query_one("#chat-container", Vertical)
        thinking = ThinkingIndicator()
        container.mount(thinking)
        self._scroll_to_bottom()

        try:
            # Monkey-patch the console output functions to redirect to TUI
            import sam.ui.console as con
            original_print_assistant = con.print_assistant
            original_print_tool_call = con.print_tool_call
            original_print_tool_result = con.print_tool_result
            original_print_info = con.print_info
            original_print_warning = con.print_warning
            original_print_error = con.print_error
            original_console_print = con.console.print

            captured_assistant_text = []

            def tui_print_assistant(content: str):
                if content.strip():
                    captured_assistant_text.append(content)

            def tui_print_tool_call(name: str, args: dict):
                args_summary = con._summarize_args(args)
                self._add_tool_call(name, args_summary)

            def tui_print_tool_result(result_text: str, is_error: bool = False):
                max_display = 500
                text = result_text[:max_display]
                if len(result_text) > max_display:
                    text += f"\n... ({len(result_text)} chars)"
                if is_error:
                    self._add_error(text)
                else:
                    self._add_tool_result(text)

            def tui_print_info(msg: str):
                self._add_info(msg)

            def tui_print_warning(msg: str):
                self._add_info(f"Warning: {msg}")

            def tui_print_error(msg: str):
                self._add_error(msg)

            # Capture streaming output
            def tui_console_print(*args, **kwargs):
                # Silently capture console.print calls from streaming
                for arg in args:
                    if isinstance(arg, str) and arg.strip():
                        captured_assistant_text.append(arg)

            con.print_assistant = tui_print_assistant
            con.print_tool_call = tui_print_tool_call
            con.print_tool_result = tui_print_tool_result
            con.print_info = tui_print_info
            con.print_warning = tui_print_warning
            con.print_error = tui_print_error
            con.console.print = tui_console_print

            try:
                result = await self._agent.run_turn(
                    message, repo_map=self._repo_map
                )
            finally:
                # Restore original functions
                con.print_assistant = original_print_assistant
                con.print_tool_call = original_print_tool_call
                con.print_tool_result = original_print_tool_result
                con.print_info = original_print_info
                con.print_warning = original_print_warning
                con.print_error = original_print_error
                con.console.print = original_console_print

            # Show the final response
            if result and result.strip():
                self._add_assistant_message(result)

        except Exception as e:
            self._add_error(f"Error: {e}")

        finally:
            # Remove thinking indicator
            try:
                thinking.remove()
            except Exception:
                pass

            self._is_processing = False
            input_widget.placeholder = "Ask SAM anything... (type /help for commands)"
            input_widget.focus()

            # Update status bar
            self._update_status_bar()

            # Auto-save session
            self._save_session()

    def _add_user_message(self, content: str) -> None:
        container = self.query_one("#chat-container", Vertical)
        msg = ChatMessage(content, role="user")
        container.mount(msg)
        self._scroll_to_bottom()

    def _add_assistant_message(self, content: str) -> None:
        container = self.query_one("#chat-container", Vertical)
        msg = ChatMessage(content, role="assistant")
        container.mount(msg)
        self._scroll_to_bottom()

    def _add_tool_call(self, name: str, args_summary: str) -> None:
        container = self.query_one("#chat-container", Vertical)
        msg = ChatMessage(f"{name} {args_summary}", role="tool")
        container.mount(msg)
        self._scroll_to_bottom()

    def _add_tool_result(self, content: str) -> None:
        container = self.query_one("#chat-container", Vertical)
        msg = ChatMessage(content, role="tool_result")
        container.mount(msg)
        self._scroll_to_bottom()

    def _add_error(self, content: str) -> None:
        container = self.query_one("#chat-container", Vertical)
        msg = ChatMessage(content, role="error")
        container.mount(msg)
        self._scroll_to_bottom()

    def _add_info(self, content: str) -> None:
        container = self.query_one("#chat-container", Vertical)
        msg = ChatMessage(content, role="info")
        container.mount(msg)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        try:
            scroll = self.query_one("#chat-scroll", VerticalScroll)
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _show_help(self) -> None:
        from sam.skills import SkillRegistry

        lines = [
            "/help     — Show this help",
            "/plan     — Toggle plan mode (read-only)",
            "/clear    — Clear chat",
            "/reset    — Reset conversation",
            "/model    — Show model info",
            "/status   — Show token usage",
            "/exit     — Exit SAM",
            "",
            "Skills:",
        ]
        skills = SkillRegistry()
        for skill in skills.all_skills():
            lines.append(f"  /{skill.name:12s} — {skill.description}")

        self._add_info("\n".join(lines))

    def _show_status(self) -> None:
        if not self._agent:
            return
        n_msgs = len(self._agent.history.messages)
        tokens = self._agent.history.estimate_tokens()
        ctx = self._settings.context_window
        pct = int(tokens / ctx * 100) if ctx else 0
        mode = "PLAN (read-only)" if self._agent.plan_mode else "NORMAL"

        lines = [
            f"Session:  {(self._session_id or 'none')[:8]}",
            f"Mode:     {mode}",
            f"Messages: {n_msgs}",
            f"Tokens:   ~{tokens:,} / {ctx:,} ({pct}%)",
            f"Model:    {self._settings.model_id}",
            f"Perms:    {self._settings.permission_mode}",
        ]
        self._add_info("\n".join(lines))

    def _update_status_bar(self) -> None:
        if not self._agent:
            return
        try:
            status = self.query_one("#status-bar", StatusBar)
            tokens = self._agent.history.estimate_tokens()
            ctx = self._settings.context_window
            status.token_info = f"~{tokens:,} / {ctx:,}"
            status.mode = "PLAN" if self._agent.plan_mode else "NORMAL"
        except Exception:
            pass

    def _save_session(self) -> None:
        try:
            if self._sess_mgr and self._session_id and self._agent:
                self._sess_mgr.save(self._session_id, self._agent.history)
        except Exception:
            pass

    def action_clear_chat(self) -> None:
        try:
            container = self.query_one("#chat-container", Vertical)
            container.remove_children()
        except Exception:
            pass

    def action_cancel(self) -> None:
        if self._is_processing:
            self._add_info("Cancelling...")

    def action_focus_input(self) -> None:
        try:
            self.query_one("#prompt-input", Input).focus()
        except Exception:
            pass

    def action_quit(self) -> None:
        self._save_session()
        self.exit()


def run_tui(settings=None) -> None:
    """Launch the SAM TUI."""
    app = SAMApp(settings=settings)
    app.run()
