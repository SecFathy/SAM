"""Textual-based TUI for SAM — clean, minimal Claude Code-style terminal UI."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

# ── Suggestion/autocomplete menu ─────────────────────────────────────


class SuggestionMenu(OptionList):
    """Dropdown suggestion menu for / commands and @ file paths."""

    DEFAULT_CSS = """
    SuggestionMenu {
        height: auto;
        max-height: 12;
        dock: bottom;
        layer: overlay;
        background: #252525;
        color: #cccccc;
        border: solid #444444;
        padding: 0;
        margin: 0 1 0 1;
        display: none;
    }
    SuggestionMenu:focus {
        border: solid #666666;
    }
    SuggestionMenu > .option-list--option-highlighted {
        background: #3a3a3a;
        color: #ffffff;
    }
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._prefix = ""
        self._items: list[tuple[str, str]] = []  # (value, description)

    def show_commands(self, prefix: str, commands: list[tuple[str, str]]) -> None:
        """Show slash command suggestions."""
        self._prefix = prefix
        self._items = []
        self.clear_options()

        for name, desc in commands:
            if prefix and not name.startswith(prefix):
                continue
            self._items.append((name, desc))
            label = Text()
            label.append(f"/{name}", style="bold #cc7832")
            label.append(f"  {desc}", style="dim #888888")
            self.add_option(Option(label, id=name))

        if self._items:
            self.display = True
            self.highlighted = 0
        else:
            self.display = False

    def show_files(self, prefix: str, working_dir: Path) -> None:
        """Show @ file path suggestions."""
        self._prefix = prefix
        self._items = []
        self.clear_options()

        base = working_dir / prefix if prefix else working_dir

        if prefix and not base.is_dir():
            search_dir = base.parent
            partial = base.name.lower()
        else:
            search_dir = base
            partial = ""

        if not search_dir.is_dir():
            self.display = False
            return

        try:
            entries = sorted(search_dir.iterdir())
        except OSError:
            self.display = False
            return

        count = 0
        for entry in entries:
            if count >= 20:
                break
            name = entry.name
            if name.startswith("."):
                continue
            if partial and not name.lower().startswith(partial):
                continue

            try:
                rel = str(entry.relative_to(working_dir))
            except ValueError:
                continue

            display = rel + ("/" if entry.is_dir() else "")
            kind = "dir" if entry.is_dir() else ""
            self._items.append((display, kind))

            label = Text()
            label.append(f"@{display}", style="bold #6a9fb5")
            if kind:
                label.append(f"  {kind}", style="dim #666666")
            self.add_option(Option(label, id=display))
            count += 1

        if self._items:
            self.display = True
            self.highlighted = 0
        else:
            self.display = False

    def hide(self) -> None:
        self.display = False
        self._items = []

    def get_selected_value(self) -> str | None:
        """Get the value of the currently highlighted item."""
        if self.highlighted is not None and 0 <= self.highlighted < len(self._items):
            return self._items[self.highlighted][0]
        return None


# ── Lightweight message widgets ──────────────────────────────────────


class UserMessage(Static):
    """User message — bold prompt prefix, plain text."""

    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 2;
    }
    """

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self._text = text

    def render(self) -> Text:
        t = Text()
        t.append("> ", style="bold #cc7832")
        t.append(self._text, style="bold white")
        return t


class AssistantMessage(Static):
    """Assistant response — plain text."""

    DEFAULT_CSS = """
    AssistantMessage {
        height: auto;
        margin: 0 0 0 0;
        padding: 0 2 0 4;
        color: #e0e0e0;
    }
    """

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self._text = text

    def render(self) -> Text:
        return Text(self._text, style="#e0e0e0")


class ToolCallMessage(Static):
    """Compact tool call — single dim line with triangle marker."""

    DEFAULT_CSS = """
    ToolCallMessage {
        height: auto;
        margin: 0 0 0 0;
        padding: 0 2 0 4;
    }
    """

    def __init__(self, name: str, summary: str = "", **kw) -> None:
        super().__init__(**kw)
        self._name = name
        self._summary = summary

    def render(self) -> Text:
        t = Text()
        t.append("  > ", style="dim #666666")
        t.append(self._name, style="bold #888888")
        if self._summary:
            t.append(f" {self._summary}", style="dim #666666")
        return t


class ToolResultMessage(Static):
    """Tool result — dim, indented, truncated."""

    DEFAULT_CSS = """
    ToolResultMessage {
        height: auto;
        margin: 0 0 0 0;
        padding: 0 2 0 6;
        max-height: 12;
        overflow-y: auto;
    }
    """

    def __init__(self, text: str, is_error: bool = False, **kw) -> None:
        super().__init__(**kw)
        self._text = text
        self._is_error = is_error

    def render(self) -> Text:
        style = "red" if self._is_error else "dim #555555"
        return Text(self._text, style=style)


class InfoMessage(Static):
    """Subtle info/system message."""

    DEFAULT_CSS = """
    InfoMessage {
        height: auto;
        margin: 0 0 0 0;
        padding: 0 2 0 4;
    }
    """

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self._text = text

    def render(self) -> Text:
        return Text(self._text, style="dim italic #888888")


class ThinkingDots(Static):
    """Minimal thinking indicator."""

    DEFAULT_CSS = """
    ThinkingDots {
        height: 1;
        padding: 0 2 0 4;
    }
    """

    def render(self) -> Text:
        return Text("...", style="dim #666666")


class WelcomeBanner(Static):
    """Clean welcome banner — just the essentials."""

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        padding: 1 2;
        margin: 0 0 0 0;
    }
    """

    def __init__(self, model: str, cwd: str, **kw) -> None:
        super().__init__(**kw)
        self._model = model
        self._cwd = cwd

    def render(self) -> Text:
        t = Text()
        t.append("SAM", style="bold #cc7832")
        t.append(" v0.2.0\n", style="dim")
        t.append(f"  model: {self._model}\n", style="dim #888888")
        t.append(f"  cwd:   {self._cwd}\n", style="dim #888888")
        t.append("  /help for commands, @ to mention files, Ctrl+D to quit", style="dim #666666")
        return t


# ── Main Application ─────────────────────────────────────────────────


class SAMApp(App):
    """SAM TUI — clean, minimal, Claude Code-inspired."""

    TITLE = "SAM"

    CSS = """
    Screen {
        background: #1a1a1a;
        layers: default overlay;
    }

    #chat-scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-color: #333333;
        scrollbar-color-hover: #555555;
        scrollbar-color-active: #777777;
    }

    #chat-container {
        height: auto;
    }

    #input-area {
        height: auto;
        max-height: 6;
        dock: bottom;
        background: #1a1a1a;
    }

    #input-bar {
        height: 3;
        padding: 0 1;
        background: #1a1a1a;
        border-top: solid #333333;
    }

    #prompt-input {
        height: 1;
        background: #1a1a1a;
        border: none;
        color: #e0e0e0;
    }

    #prompt-input:focus {
        border: none;
    }

    #mode-label {
        height: 1;
        padding: 0 2;
        background: #1a1a1a;
        color: #555555;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel", "Cancel", show=False),
        Binding("ctrl+d", "quit", "Quit", show=False),
        Binding("ctrl+l", "clear_chat", "Clear", show=False),
        Binding("escape", "dismiss_menu", show=False),
    ]

    def __init__(self, settings=None, **kwargs):
        super().__init__(**kwargs)
        self._settings = settings
        self._agent = None
        self._sess_mgr = None
        self._session_id = None
        self._repo_map = ""
        self._is_processing = False
        self._slash_commands: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="chat-scroll"):
            yield Vertical(id="chat-container")
        with Vertical(id="input-area"):
            yield SuggestionMenu(id="suggestion-menu")
            with Vertical(id="input-bar"):
                yield Input(placeholder="> ", id="prompt-input")
        yield Static("", id="mode-label")

    async def on_mount(self) -> None:
        self._build_command_list()
        self._setup_agent()

    def _build_command_list(self) -> None:
        """Build the list of slash commands for autocomplete."""
        self._slash_commands = [
            ("help", "Show available commands"),
            ("plan", "Toggle plan mode (read-only)"),
            ("clear", "Clear chat history"),
            ("reset", "Start new session"),
            ("model", "Show model info"),
            ("status", "Token usage and stats"),
            ("exit", "Quit SAM"),
        ]
        try:
            from sam.skills import SkillRegistry
            skills = SkillRegistry()
            for s in skills.all_skills():
                self._slash_commands.append((s.name, s.description))
        except Exception:
            pass

    @work(thread=False)
    async def _setup_agent(self) -> None:
        from sam.cli import _build_agent
        from sam.session.manager import SessionManager

        settings = self._settings
        if settings is None:
            from sam.config import Settings
            settings = Settings()
            self._settings = settings

        async def _tui_input_fn(question: str) -> str:
            self._add_info(f"SAM asks: {question}")
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: input("> "))

        self._sess_mgr = SessionManager(settings)
        self._session_id, conv_history = self._sess_mgr.get_or_create()

        self._agent = _build_agent(
            settings,
            input_fn=_tui_input_fn,
            history=conv_history,
        )

        try:
            from sam.repo.mapper import RepoMapper
            mapper = RepoMapper(settings.working_dir, token_budget=settings.repo_map_tokens)
            self._repo_map = mapper.generate()
        except Exception:
            pass

        # Welcome banner
        container = self.query_one("#chat-container", Vertical)
        banner = WelcomeBanner(
            model=settings.model_id,
            cwd=str(settings.working_dir),
        )
        container.mount(banner)

        self._update_mode_label()
        self.query_one("#prompt-input", Input).focus()

    # ── Input handling with autocomplete ──

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show suggestions as user types."""
        text = event.value
        menu = self.query_one("#suggestion-menu", SuggestionMenu)

        # Slash command completion
        if text.startswith("/"):
            prefix = text[1:]  # strip the /
            menu.show_commands(prefix, self._slash_commands)
            return

        # @ file completion — find last @ token
        at_idx = text.rfind("@")
        if at_idx >= 0:
            # @ must be at start or after whitespace
            if at_idx == 0 or text[at_idx - 1].isspace():
                after_at = text[at_idx + 1:]
                # Only complete if no space after the partial path
                if " " not in after_at and self._settings:
                    menu.show_files(after_at, self._settings.working_dir)
                    return

        menu.hide()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection from the suggestion menu."""
        menu = self.query_one("#suggestion-menu", SuggestionMenu)
        inp = self.query_one("#prompt-input", Input)
        text = inp.value

        selected = event.option.id
        if selected is None:
            menu.hide()
            return

        if text.startswith("/"):
            # Replace the whole input with the selected command
            inp.value = f"/{selected}"
            inp.cursor_position = len(inp.value)
        else:
            # @ file — replace from the last @ onward
            at_idx = text.rfind("@")
            if at_idx >= 0:
                before = text[:at_idx]
                inp.value = f"{before}@{selected}"
                inp.cursor_position = len(inp.value)

        menu.hide()
        inp.focus()

    def _apply_suggestion_from_key(self) -> bool:
        """Apply the highlighted suggestion and return True if menu was visible."""
        menu = self.query_one("#suggestion-menu", SuggestionMenu)
        if menu.display and menu._items:
            val = menu.get_selected_value()
            if val:
                inp = self.query_one("#prompt-input", Input)
                text = inp.value
                if text.startswith("/"):
                    inp.value = f"/{val}"
                else:
                    at_idx = text.rfind("@")
                    if at_idx >= 0:
                        inp.value = f"{text[:at_idx]}@{val}"
                inp.cursor_position = len(inp.value)
                menu.hide()
                inp.focus()
                return True
        return False

    async def on_key(self, event) -> None:
        """Handle key events for menu navigation."""
        menu = self.query_one("#suggestion-menu", SuggestionMenu)

        if menu.display:
            if event.key == "up":
                event.prevent_default()
                if menu.highlighted is not None and menu.highlighted > 0:
                    menu.highlighted = menu.highlighted - 1
                return
            elif event.key == "down":
                event.prevent_default()
                if menu.highlighted is not None and menu.highlighted < len(menu._items) - 1:
                    menu.highlighted = menu.highlighted + 1
                return
            elif event.key == "tab":
                event.prevent_default()
                self._apply_suggestion_from_key()
                return
            elif event.key == "escape":
                event.prevent_default()
                menu.hide()
                self.query_one("#prompt-input", Input).focus()
                return

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input."""
        # If menu is showing, Tab/Enter applies the selection
        menu = self.query_one("#suggestion-menu", SuggestionMenu)
        if menu.display:
            if self._apply_suggestion_from_key():
                # Don't submit — just applied the completion
                return
            menu.hide()

        user_input = event.value.strip()
        if not user_input:
            return

        event.input.value = ""

        if self._is_processing:
            self._add_info("Processing... please wait.")
            return

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
                mode = "plan mode (read-only)" if self._agent.plan_mode else "normal mode"
                self._add_info(f"Switched to {mode}")
                self._update_mode_label()
            return

        if cmd == "/reset":
            if self._sess_mgr:
                self._session_id, conv_history = self._sess_mgr.create_session()
                from sam.cli import _build_agent
                self._agent = _build_agent(self._settings, history=conv_history)
                self.action_clear_chat()
                self._add_info(f"New session: {self._session_id[:8]}")
            return

        if cmd == "/model":
            if self._settings:
                self._add_info(f"{self._settings.model_id} @ {self._settings.api_base}")
            return

        if cmd == "/status":
            self._show_status()
            return

        if cmd.startswith("/"):
            from sam.skills import SkillRegistry
            skill_name = cmd[1:]
            skills = SkillRegistry()
            skill = skills.get(skill_name)
            if skill:
                self._mount_msg(UserMessage(f"/{skill_name}"))
                self._run_agent_turn(skill.prompt)
                return
            self._add_info(f"Unknown command: {cmd}")
            return

        # Expand @file references into inline file content hints
        processed = self._expand_at_references(user_input)

        self._mount_msg(UserMessage(user_input))
        self._run_agent_turn(processed)

    def _expand_at_references(self, text: str) -> str:
        """Expand @file references to include file path hints for the agent."""
        if "@" not in text or not self._settings:
            return text

        import re
        parts = re.findall(r"@(\S+)", text)
        expanded = text
        for ref in parts:
            full_path = self._settings.working_dir / ref
            if full_path.exists():
                # Replace @ref with a clear file reference the agent understands
                expanded = expanded.replace(
                    f"@{ref}",
                    f"`{ref}` (file: {full_path})",
                )
        return expanded

    @work(thread=False)
    async def _run_agent_turn(self, message: str) -> None:
        if not self._agent:
            self._add_info("Agent not ready...")
            return

        self._is_processing = True
        inp = self.query_one("#prompt-input", Input)
        inp.placeholder = "..."

        container = self.query_one("#chat-container", Vertical)
        thinking = ThinkingDots()
        container.mount(thinking)
        self._scroll_bottom()

        try:
            from contextlib import contextmanager

            import sam.ui.console as con

            orig = {
                "assistant": con.print_assistant,
                "tool_call": con.print_tool_call,
                "tool_result": con.print_tool_result,
                "info": con.print_info,
                "warning": con.print_warning,
                "error": con.print_error,
                "console_print": con.console.print,
                "console_status": con.console.status,
                "console_log": con.console.log,
            }

            captured = []

            def _pa(content: str):
                if content.strip():
                    captured.append(content)

            def _ptc(name: str, args: dict):
                summary = con._summarize_args(args)
                self._mount_msg(ToolCallMessage(name, summary))

            def _ptr(text: str, is_error: bool = False):
                show = text[:400]
                if len(text) > 400:
                    show += f"\n... ({len(text)} chars)"
                self._mount_msg(ToolResultMessage(show, is_error=is_error))

            def _pi(msg: str):
                self._add_info(msg)

            def _pw(msg: str):
                self._add_info(f"warn: {msg}")

            def _pe(msg: str):
                self._mount_msg(ToolResultMessage(msg, is_error=True))

            def _cp(*args, **kwargs):
                for a in args:
                    if isinstance(a, str) and a.strip():
                        captured.append(a)

            # No-op context manager to replace console.status (Rich spinner)
            @contextmanager
            def _noop_status(*args, **kwargs):
                yield None

            def _noop_log(*args, **kwargs):
                pass

            con.print_assistant = _pa
            con.print_tool_call = _ptc
            con.print_tool_result = _ptr
            con.print_info = _pi
            con.print_warning = _pw
            con.print_error = _pe
            con.console.print = _cp
            con.console.status = _noop_status
            con.console.log = _noop_log

            try:
                result = await self._agent.run_turn(message, repo_map=self._repo_map)
            finally:
                con.print_assistant = orig["assistant"]
                con.print_tool_call = orig["tool_call"]
                con.print_tool_result = orig["tool_result"]
                con.print_info = orig["info"]
                con.print_warning = orig["warning"]
                con.print_error = orig["error"]
                con.console.print = orig["console_print"]
                con.console.status = orig["console_status"]
                con.console.log = orig["console_log"]

            if result and result.strip():
                self._mount_msg(AssistantMessage(result))

        except Exception as e:
            self._mount_msg(ToolResultMessage(f"Error: {e}", is_error=True))

        finally:
            try:
                thinking.remove()
            except Exception:
                pass
            self._is_processing = False
            inp.placeholder = "> "
            inp.focus()
            self._update_mode_label()
            self._save_session()

    # ── helpers ──

    def _mount_msg(self, widget: Static) -> None:
        container = self.query_one("#chat-container", Vertical)
        container.mount(widget)
        self._scroll_bottom()

    def _add_info(self, text: str) -> None:
        self._mount_msg(InfoMessage(text))

    def _scroll_bottom(self) -> None:
        try:
            self.query_one("#chat-scroll", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def _update_mode_label(self) -> None:
        try:
            label = self.query_one("#mode-label", Static)
            parts = []
            if self._agent:
                tokens = self._agent.history.estimate_tokens()
                ctx = self._settings.context_window
                parts.append(f"~{tokens:,}/{ctx:,} tokens")
                if self._agent.plan_mode:
                    parts.append("PLAN MODE")
            if self._settings:
                parts.append(self._settings.model_id)
            label.update(Text("  ".join(parts), style="dim #555555"))
        except Exception:
            pass

    def _show_help(self) -> None:
        from sam.skills import SkillRegistry

        lines = [
            "Commands:",
            "  /plan     toggle plan mode (read-only)",
            "  /clear    clear chat",
            "  /reset    new session",
            "  /model    show model info",
            "  /status   token usage",
            "  /exit     quit",
            "",
            "Mentions:",
            "  @file.py  reference a file (tab to complete)",
            "",
            "Skills:",
        ]
        skills = SkillRegistry()
        for s in skills.all_skills():
            lines.append(f"  /{s.name:<12s} {s.description}")

        self._add_info("\n".join(lines))

    def _show_status(self) -> None:
        if not self._agent:
            return
        n = len(self._agent.history.messages)
        tokens = self._agent.history.estimate_tokens()
        ctx = self._settings.context_window
        pct = int(tokens / ctx * 100) if ctx else 0
        mode = "plan (read-only)" if self._agent.plan_mode else "normal"
        self._add_info(
            f"session {(self._session_id or '-')[:8]}  "
            f"{n} msgs  ~{tokens:,}/{ctx:,} tokens ({pct}%)  {mode}"
        )

    def _save_session(self) -> None:
        try:
            if self._sess_mgr and self._session_id and self._agent:
                self._sess_mgr.save(self._session_id, self._agent.history)
        except Exception:
            pass

    def action_clear_chat(self) -> None:
        try:
            self.query_one("#chat-container", Vertical).remove_children()
        except Exception:
            pass

    def action_cancel(self) -> None:
        if self._is_processing:
            self._add_info("Cancelling...")

    def action_dismiss_menu(self) -> None:
        try:
            menu = self.query_one("#suggestion-menu", SuggestionMenu)
            if menu.display:
                menu.hide()
                self.query_one("#prompt-input", Input).focus()
            else:
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
