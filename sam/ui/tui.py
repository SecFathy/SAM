"""Textual TUI for SAM — modern, clean, Claude Code-inspired."""

from __future__ import annotations

import asyncio
import re
from contextlib import contextmanager
from pathlib import Path

from rich.markdown import Markdown
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.timer import Timer
from textual.widgets import Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

_DIR_MARKER = "+"
_FILE_MARKER = "-"


# ── Suggestion menu ──────────────────────────────────────────────────


class SuggestionMenu(OptionList):
    """Autocomplete dropdown for / commands and @ file paths."""

    DEFAULT_CSS = """
    SuggestionMenu {
        height: auto;
        max-height: 12;
        width: 100%;
        dock: bottom;
        layer: overlay;
        offset-y: -4;
        background: #252525;
        color: #d4d4d4;
        border: round #3d3d3d;
        padding: 0 1;
        margin: 0 2;
        display: none;
        scrollbar-size: 1 1;
    }
    SuggestionMenu:focus {
        border: round #5a5a5a;
    }
    SuggestionMenu > .option-list--option-highlighted {
        background: #333333;
        color: #ffffff;
    }
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._prefix = ""
        self._items: list[tuple[str, str]] = []

    def show_commands(
        self, prefix: str, commands: list[tuple[str, str]]
    ) -> None:
        self._prefix = prefix
        self._items = []
        self.clear_options()
        for name, desc in commands:
            if prefix and not name.startswith(prefix):
                continue
            self._items.append((name, desc))
            label = Text()
            label.append(f" /{name} ", style="bold #d19a66")
            label.append(desc, style="#7f848e")
            self.add_option(Option(label, id=name))
        self.display = bool(self._items)
        if self._items:
            self.highlighted = 0

    def show_files(self, prefix: str, working_dir: Path) -> None:
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
            all_entries = list(search_dir.iterdir())
        except OSError:
            self.display = False
            return

        # Filter hidden files and apply partial match
        filtered = []
        for entry in all_entries:
            if entry.name.startswith("."):
                continue
            if partial and not entry.name.lower().startswith(
                partial
            ):
                continue
            filtered.append(entry)

        # Sort: directories first, then files, alphabetical
        dirs = sorted(
            [e for e in filtered if e.is_dir()],
            key=lambda e: e.name.lower(),
        )
        files = sorted(
            [e for e in filtered if e.is_file()],
            key=lambda e: e.name.lower(),
        )

        for entry in (dirs + files)[:20]:
            try:
                rel = str(entry.relative_to(working_dir))
            except ValueError:
                continue

            is_dir = entry.is_dir()
            display = rel + ("/" if is_dir else "")
            self._items.append((display, ""))

            label = Text()
            if is_dir:
                label.append(
                    f" {_DIR_MARKER} ", style="#61afef"
                )
                label.append(display, style="bold #61afef")
            else:
                label.append(
                    f" {_FILE_MARKER} ", style="#5c6370"
                )
                label.append(display, style="#abb2bf")
            self.add_option(Option(label, id=display))

        self.display = bool(self._items)
        if self._items:
            self.highlighted = 0

    def hide(self) -> None:
        self.display = False
        self._items = []

    def get_selected_value(self) -> str | None:
        idx = self.highlighted
        if idx is not None and 0 <= idx < len(self._items):
            return self._items[idx][0]
        return None


# ── Message widgets ──────────────────────────────────────────────────


class Separator(Static):
    """Thin horizontal rule between conversation turns."""

    DEFAULT_CSS = """
    Separator {
        height: 1;
        margin: 1 2 0 2;
        color: #2d2d2d;
    }
    """

    def render(self) -> Text:
        w = max(self.size.width - 4, 10)
        return Text("\u2500" * w, style="#2d2d2d")


class HumanLabel(Static):
    """'You' label above user messages."""

    DEFAULT_CSS = """
    HumanLabel {
        height: 1;
        padding: 0 2;
        margin: 0 0 0 0;
    }
    """

    def render(self) -> Text:
        return Text("You", style="bold #d19a66")


class UserMessage(Static):
    """User message text."""

    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        padding: 0 2 0 2;
    }
    """

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self._text = text

    def render(self) -> Text:
        return Text(self._text, style="white")


class AssistantLabel(Static):
    """'SAM' label above assistant responses."""

    DEFAULT_CSS = """
    AssistantLabel {
        height: 1;
        padding: 0 2;
        margin: 1 0 0 0;
    }
    """

    def render(self) -> Text:
        return Text("SAM", style="bold #61afef")


class AssistantMessage(RichLog):
    """Assistant response with full markdown rendering."""

    DEFAULT_CSS = """
    AssistantMessage {
        height: auto;
        max-height: 100%;
        padding: 0 2 0 2;
        margin: 0;
        scrollbar-size: 0 0;
        overflow-y: auto;
    }
    """


class ToolCallMessage(Static):
    """Compact tool call indicator."""

    DEFAULT_CSS = """
    ToolCallMessage {
        height: auto;
        padding: 0 2 0 4;
    }
    """

    def __init__(self, name: str, summary: str = "", **kw) -> None:
        super().__init__(**kw)
        self._name = name
        self._summary = summary

    def render(self) -> Text:
        t = Text()
        t.append("\u25b8 ", style="#5c6370")
        t.append(self._name, style="bold #5c6370")
        if self._summary:
            t.append(f" {self._summary}", style="#4b5263")
        return t


class ToolResultMessage(Static):
    """Tool result — dim, compact."""

    DEFAULT_CSS = """
    ToolResultMessage {
        height: auto;
        padding: 0 2 0 6;
        max-height: 10;
        overflow-y: auto;
    }
    """

    def __init__(self, text: str, is_error: bool = False, **kw) -> None:
        super().__init__(**kw)
        self._text = text
        self._is_error = is_error

    def render(self) -> Text:
        if self._is_error:
            return Text(self._text, style="#e06c75")
        return Text(self._text, style="#4b5263")


class InfoMessage(Static):
    """System/info message."""

    DEFAULT_CSS = """
    InfoMessage {
        height: auto;
        padding: 0 2 0 4;
    }
    """

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self._text = text

    def render(self) -> Text:
        return Text(self._text, style="italic #5c6370")


class ThinkingIndicator(Static):
    """Animated thinking dots."""

    DEFAULT_CSS = """
    ThinkingIndicator {
        height: 1;
        padding: 0 2 0 4;
    }
    """

    _dots = 0
    _timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.4, self._tick)

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        self.refresh()

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    def render(self) -> Text:
        dots = "." * (self._dots + 1)
        return Text(f"thinking{dots}", style="#5c6370")


class WelcomeBanner(Static):
    """Clean welcome header."""

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        padding: 1 2 0 2;
    }
    """

    def __init__(self, model: str, cwd: str, **kw) -> None:
        super().__init__(**kw)
        self._model = model
        self._cwd = cwd

    def render(self) -> Text:
        t = Text()
        t.append("\u2588\u2588\u2588", style="bold #61afef")
        t.append(" SAM ", style="bold white")
        t.append("v0.2.0", style="#5c6370")
        t.append("\n")
        t.append(
            f"    {self._model}", style="#7f848e"
        )
        t.append("  \u2502  ", style="#3d3d3d")
        t.append(self._cwd, style="#7f848e")
        t.append("\n")
        t.append(
            "    Type / for commands, @ to mention files",
            style="#5c6370",
        )
        return t


# ── Main Application ─────────────────────────────────────────────────


class SAMApp(App):
    """SAM TUI."""

    TITLE = "SAM"

    CSS = """
    Screen {
        background: #1e1e1e;
        layers: default overlay;
    }

    #chat-scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-color: #2d2d2d;
        scrollbar-color-hover: #3d3d3d;
        scrollbar-color-active: #5a5a5a;
    }

    #chat-container {
        height: auto;
        padding: 0 0 1 0;
    }

    #bottom-area {
        height: auto;
        max-height: 4;
        dock: bottom;
        background: #1e1e1e;
    }

    #input-row {
        height: 3;
        padding: 0 2;
        background: #1e1e1e;
        border-top: solid #2d2d2d;
    }

    #prompt-input {
        height: 1;
        background: #1e1e1e;
        border: none;
        color: #d4d4d4;
    }

    #prompt-input:focus {
        border: none;
    }

    #status-line {
        height: 1;
        padding: 0 2;
        background: #1e1e1e;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", show=False, priority=True),
        Binding("ctrl+d", "quit", show=False, priority=True),
        Binding("ctrl+l", "clear_chat", show=False),
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
        yield SuggestionMenu(id="suggestion-menu")
        with Vertical(id="bottom-area"):
            with Vertical(id="input-row"):
                yield Input(
                    placeholder="\u276f ",
                    id="prompt-input",
                )
        yield Static("", id="status-line")

    async def on_mount(self) -> None:
        self._build_command_list()
        self._setup_agent()

    def _build_command_list(self) -> None:
        self._slash_commands = [
            ("help", "Show available commands"),
            ("plan", "Toggle plan mode"),
            ("clear", "Clear chat"),
            ("reset", "New session"),
            ("model", "Show model info"),
            ("status", "Token usage"),
            ("exit", "Quit"),
        ]
        try:
            from sam.skills import SkillRegistry
            for s in SkillRegistry().all_skills():
                self._slash_commands.append(
                    (s.name, s.description)
                )
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

        async def _tui_input(q: str) -> str:
            self._add_info(f"SAM asks: {q}")
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: input("> ")
            )

        self._sess_mgr = SessionManager(settings)
        sid, conv = self._sess_mgr.get_or_create()
        self._session_id = sid

        self._agent = _build_agent(
            settings, input_fn=_tui_input, history=conv,
        )

        try:
            from sam.repo.mapper import RepoMapper
            mapper = RepoMapper(
                settings.working_dir,
                token_budget=settings.repo_map_tokens,
            )
            self._repo_map = mapper.generate()
        except Exception:
            pass

        container = self.query_one("#chat-container", Vertical)
        container.mount(WelcomeBanner(
            model=settings.model_id,
            cwd=str(settings.working_dir),
        ))

        self._update_status()
        self.query_one("#prompt-input", Input).focus()

    # ── Autocomplete ──

    def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        menu = self.query_one("#suggestion-menu", SuggestionMenu)

        if text.startswith("/"):
            menu.show_commands(text[1:], self._slash_commands)
            return

        at_idx = text.rfind("@")
        if at_idx >= 0 and (
            at_idx == 0 or text[at_idx - 1].isspace()
        ):
            after = text[at_idx + 1:]
            if " " not in after and self._settings:
                menu.show_files(
                    after, self._settings.working_dir
                )
                return

        menu.hide()

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        menu = self.query_one("#suggestion-menu", SuggestionMenu)
        inp = self.query_one("#prompt-input", Input)
        selected = event.option.id
        if selected is None:
            menu.hide()
            return
        text = inp.value
        if text.startswith("/"):
            inp.value = f"/{selected}"
            inp.cursor_position = len(inp.value)
            menu.hide()
        else:
            at_idx = text.rfind("@")
            if at_idx >= 0:
                inp.value = f"{text[:at_idx]}@{selected}"
                inp.cursor_position = len(inp.value)
                # If a directory was selected, keep menu open
                # on_input_changed will fire and show contents
                if selected.endswith("/"):
                    pass  # don't hide — let it drill in
                else:
                    menu.hide()
        inp.focus()

    def _apply_suggestion(self) -> bool:
        menu = self.query_one("#suggestion-menu", SuggestionMenu)
        if not (menu.display and menu._items):
            return False
        val = menu.get_selected_value()
        if not val:
            return False
        inp = self.query_one("#prompt-input", Input)
        text = inp.value
        if text.startswith("/"):
            inp.value = f"/{val}"
            menu.hide()
        else:
            at_idx = text.rfind("@")
            if at_idx >= 0:
                inp.value = f"{text[:at_idx]}@{val}"
            # Keep menu open for dirs so it drills in
            if not val.endswith("/"):
                menu.hide()
        inp.cursor_position = len(inp.value)
        inp.focus()
        return True

    async def on_key(self, event) -> None:
        menu = self.query_one("#suggestion-menu", SuggestionMenu)
        if not menu.display:
            return
        if event.key == "up":
            event.prevent_default()
            h = menu.highlighted
            if h is not None and h > 0:
                menu.highlighted = h - 1
        elif event.key == "down":
            event.prevent_default()
            h = menu.highlighted
            if h is not None and h < len(menu._items) - 1:
                menu.highlighted = h + 1
        elif event.key == "tab":
            event.prevent_default()
            self._apply_suggestion()
        elif event.key == "escape":
            event.prevent_default()
            menu.hide()
            self.query_one("#prompt-input", Input).focus()

    # ── Input submission ──

    async def on_input_submitted(
        self, event: Input.Submitted
    ) -> None:
        menu = self.query_one("#suggestion-menu", SuggestionMenu)
        if menu.display:
            if self._apply_suggestion():
                return
            menu.hide()

        user_input = event.value.strip()
        if not user_input:
            return
        event.input.value = ""

        if self._is_processing:
            self._add_info("Processing...")
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
                state = "on" if self._agent.plan_mode else "off"
                self._add_info(
                    f"Plan mode {state}"
                )
                self._update_status()
            return
        if cmd == "/reset":
            if self._sess_mgr:
                sid, conv = self._sess_mgr.create_session()
                self._session_id = sid
                from sam.cli import _build_agent
                self._agent = _build_agent(
                    self._settings, history=conv
                )
                self.action_clear_chat()
                self._add_info(f"New session {sid[:8]}")
            return
        if cmd == "/model":
            if self._settings:
                self._add_info(
                    f"{self._settings.model_id}"
                    f" @ {self._settings.api_base}"
                )
            return
        if cmd == "/status":
            self._show_status()
            return
        if cmd.startswith("/"):
            from sam.skills import SkillRegistry
            skill = SkillRegistry().get(cmd[1:])
            if skill:
                self._add_user_turn(f"/{skill.name}")
                self._run_agent_turn(skill.prompt)
                return
            self._add_info(f"Unknown: {cmd}")
            return

        processed = self._expand_at_refs(user_input)
        self._add_user_turn(user_input)
        self._run_agent_turn(processed)

    def _add_user_turn(self, text: str) -> None:
        """Add a user message with separator and label."""
        container = self.query_one(
            "#chat-container", Vertical
        )
        container.mount(Separator())
        container.mount(HumanLabel())
        container.mount(UserMessage(text))
        self._scroll_bottom()

    def _add_assistant_turn(self, text: str) -> None:
        """Add assistant response with label and markdown."""
        container = self.query_one(
            "#chat-container", Vertical
        )
        container.mount(AssistantLabel())
        log = AssistantMessage(
            markup=False, wrap=True, highlight=True
        )
        container.mount(log)
        md = Markdown(text, code_theme="monokai")
        log.write(md)
        self._scroll_bottom()

    def _expand_at_refs(self, text: str) -> str:
        if "@" not in text or not self._settings:
            return text
        parts = re.findall(r"@(\S+)", text)
        result = text
        for ref in parts:
            fp = self._settings.working_dir / ref
            if fp.exists():
                result = result.replace(
                    f"@{ref}", f"`{ref}` (file: {fp})"
                )
        return result

    @work(thread=False)
    async def _run_agent_turn(self, message: str) -> None:
        if not self._agent:
            self._add_info("Agent not ready...")
            return

        self._is_processing = True
        inp = self.query_one("#prompt-input", Input)
        inp.placeholder = ""

        container = self.query_one(
            "#chat-container", Vertical
        )
        thinking = ThinkingIndicator()
        container.mount(thinking)
        self._scroll_bottom()

        try:
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

            def _pa(c):
                if c.strip():
                    captured.append(c)

            def _ptc(name, args):
                s = con._summarize_args(args)
                self._mount(ToolCallMessage(name, s))

            def _ptr(t, is_error=False):
                show = t[:400]
                if len(t) > 400:
                    show += f"\n... ({len(t)} chars)"
                self._mount(
                    ToolResultMessage(show, is_error)
                )

            def _pi(m):
                self._add_info(m)

            def _pw(m):
                self._add_info(f"warn: {m}")

            def _pe(m):
                self._mount(ToolResultMessage(m, True))

            def _cp(*a, **kw):
                for x in a:
                    if isinstance(x, str) and x.strip():
                        captured.append(x)

            @contextmanager
            def _noop(*a, **kw):
                yield None

            con.print_assistant = _pa
            con.print_tool_call = _ptc
            con.print_tool_result = _ptr
            con.print_info = _pi
            con.print_warning = _pw
            con.print_error = _pe
            con.console.print = _cp
            con.console.status = _noop
            con.console.log = lambda *a, **kw: None

            try:
                result = await self._agent.run_turn(
                    message, repo_map=self._repo_map
                )
            finally:
                for k, v in orig.items():
                    if k.startswith("console_"):
                        attr = k[len("console_"):]
                        setattr(con.console, attr, v)
                    else:
                        setattr(con, k, v)

            if result and result.strip():
                self._add_assistant_turn(result)

        except Exception as e:
            self._mount(
                ToolResultMessage(f"Error: {e}", True)
            )

        finally:
            try:
                thinking.remove()
            except Exception:
                pass
            self._is_processing = False
            inp.placeholder = "\u276f "
            inp.focus()
            self._update_status()
            self._save_session()

    # ── Helpers ──

    def _mount(self, widget: Static) -> None:
        container = self.query_one(
            "#chat-container", Vertical
        )
        container.mount(widget)
        self._scroll_bottom()

    def _add_info(self, text: str) -> None:
        self._mount(InfoMessage(text))

    def _scroll_bottom(self) -> None:
        try:
            self.query_one(
                "#chat-scroll", VerticalScroll
            ).scroll_end(animate=False)
        except Exception:
            pass

    def _update_status(self) -> None:
        try:
            label = self.query_one("#status-line", Static)
            parts = []
            if self._agent:
                tok = self._agent.history.estimate_tokens()
                ctx = self._settings.context_window
                parts.append(f"{tok:,}/{ctx:,}")
                if self._agent.plan_mode:
                    parts.append("PLAN")
            if self._settings:
                parts.append(self._settings.model_id)
            label.update(
                Text(
                    "  \u2502  ".join(parts),
                    style="#3d3d3d",
                )
            )
        except Exception:
            pass

    def _show_help(self) -> None:
        from sam.skills import SkillRegistry

        lines = [
            "Commands:",
            "  /plan      toggle plan mode",
            "  /clear     clear chat",
            "  /reset     new session",
            "  /model     model info",
            "  /status    token usage",
            "  /exit      quit",
            "",
            "  @file.py   mention a file",
            "",
            "Skills:",
        ]
        for s in SkillRegistry().all_skills():
            lines.append(f"  /{s.name:<11s} {s.description}")
        self._add_info("\n".join(lines))

    def _show_status(self) -> None:
        if not self._agent:
            return
        n = len(self._agent.history.messages)
        tok = self._agent.history.estimate_tokens()
        ctx = self._settings.context_window
        pct = int(tok / ctx * 100) if ctx else 0
        mode = "plan" if self._agent.plan_mode else "normal"
        self._add_info(
            f"{n} messages  {tok:,}/{ctx:,} tokens"
            f" ({pct}%)  {mode}"
        )

    def _save_session(self) -> None:
        try:
            if (
                self._sess_mgr
                and self._session_id
                and self._agent
            ):
                self._sess_mgr.save(
                    self._session_id, self._agent.history
                )
        except Exception:
            pass

    def action_clear_chat(self) -> None:
        try:
            self.query_one(
                "#chat-container", Vertical
            ).remove_children()
        except Exception:
            pass

    def action_dismiss_menu(self) -> None:
        try:
            menu = self.query_one(
                "#suggestion-menu", SuggestionMenu
            )
            menu.hide()
            self.query_one("#prompt-input", Input).focus()
        except Exception:
            pass

    def action_quit(self) -> None:
        self._save_session()
        self.exit()


def run_tui(settings=None) -> None:
    """Launch the SAM TUI."""
    SAMApp(settings=settings).run()
