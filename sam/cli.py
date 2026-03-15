"""Click CLI: interactive and one-shot modes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from prompt_toolkit.completion import Completer, Completion
from rich.table import Table

from sam.config import ModelPreset, Settings
from sam.session.manager import SessionManager
from sam.ui.console import (
    console,
    print_banner,
    print_error,
    print_info,
    print_success,
    print_warning,
)


async def _default_input_fn(question: str) -> str:
    """Fallback input function using plain stdin (for one-shot mode)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input("❯ "))


def _build_agent(settings: Settings, input_fn=None, history=None):
    """Wire up the agent with all dependencies."""
    from sam.agent.history import ConversationHistory
    from sam.agent.loop import AgentLoop
    from sam.models.provider import ModelProvider
    from sam.tools.ask_user import AskUserQuestionTool
    from sam.tools.base import ToolRegistry
    from sam.tools.directory import DirectoryTool
    from sam.tools.file_read import FileReadTool
    from sam.tools.shell import ShellTool

    tools = ToolRegistry()
    tools.register(FileReadTool(settings.working_dir))
    tools.register(ShellTool(settings.working_dir))
    tools.register(DirectoryTool(settings.working_dir))
    tools.register(AskUserQuestionTool(input_fn or _default_input_fn))

    # Register Phase 2 tools if available
    try:
        from sam.tools.file_write import FileWriteTool
        tools.register(FileWriteTool(settings.working_dir))
    except ImportError:
        pass

    try:
        from sam.tools.file_edit import FileEditTool
        tools.register(FileEditTool(settings.working_dir))
    except ImportError:
        pass

    try:
        from sam.tools.grep_tool import GrepTool
        tools.register(GrepTool(settings.working_dir))
    except ImportError:
        pass

    try:
        from sam.tools.glob_tool import GlobTool
        tools.register(GlobTool(settings.working_dir))
    except ImportError:
        pass

    try:
        from sam.tools.git import GitDiffTool, GitStatusTool
        tools.register(GitStatusTool(settings.working_dir))
        tools.register(GitDiffTool(settings.working_dir))
    except ImportError:
        pass

    # Phase 3 tools: web, memory
    try:
        from sam.tools.web_fetch import BrowserFetchTool, WebFetchTool
        tools.register(WebFetchTool())
        tools.register(BrowserFetchTool())
    except ImportError:
        pass

    try:
        from sam.tools.web_search import WebSearchTool
        tools.register(WebSearchTool())
    except ImportError:
        pass

    try:
        from sam.tools.memory_tool import MemoryDeleteTool, MemoryReadTool, MemoryWriteTool
        tools.register(MemoryWriteTool())
        tools.register(MemoryReadTool())
        tools.register(MemoryDeleteTool())
    except ImportError:
        pass

    # Background task tools
    try:
        from sam.tools.background import BackgroundRunTool, BackgroundStatusTool
        tools.register(BackgroundRunTool(settings.working_dir))
        tools.register(BackgroundStatusTool())
    except ImportError:
        pass

    # Checkpoint tools for multi-file rollback
    try:
        from sam.tools.checkpoint import CheckpointCreateTool, CheckpointRestoreTool
        tools.register(CheckpointCreateTool(settings.working_dir))
        tools.register(CheckpointRestoreTool(settings.working_dir))
    except ImportError:
        pass

    provider = ModelProvider(settings)
    if history is None:
        history = ConversationHistory(context_window=settings.context_window)

    # Sub-agent tool — needs provider and tools registry
    try:
        from sam.agent.subagent import SubAgentTool
        tools.register(SubAgentTool(settings, provider, tools))
    except ImportError:
        pass

    agent = AgentLoop(
        settings=settings,
        provider=provider,
        tools=tools,
        history=history,
        input_fn=input_fn,
    )

    return agent


def _make_settings(**overrides) -> Settings:
    """Build settings from overrides, filtering out None values."""
    filtered = {k: v for k, v in overrides.items() if v is not None}
    return Settings(**filtered)


class _FileCompleter(Completer):
    """Tab-completer that triggers on @-prefixed file paths."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    def get_completions(self, document, complete_event):

        text = document.text_before_cursor
        # Find the last @ token being typed
        at_idx = text.rfind("@")
        if at_idx < 0:
            return
        # @ must be at start or preceded by whitespace
        if at_idx > 0 and not text[at_idx - 1].isspace():
            return

        prefix = text[at_idx + 1 :]  # everything after @
        # Don't complete if there's a space in the middle (already moved on)
        if " " in prefix:
            return

        base = self.working_dir / prefix if prefix else self.working_dir

        # If prefix looks like a partial path, list the parent directory
        if prefix and not base.is_dir():
            search_dir = base.parent
            partial = base.name
        else:
            search_dir = base
            partial = ""

        if not search_dir.is_dir():
            return

        try:
            entries = sorted(search_dir.iterdir())
        except OSError:
            return

        for entry in entries:
            name = entry.name
            if name.startswith("."):
                continue
            if not name.lower().startswith(partial.lower()):
                continue

            # Build the relative path from working_dir
            rel = entry.relative_to(self.working_dir)
            display = str(rel) + ("/" if entry.is_dir() else "")
            # The completion replaces everything after @
            yield Completion(
                display,
                start_position=-len(prefix),
                display_meta="dir" if entry.is_dir() else "",
            )


def _print_help() -> None:
    """Print available slash commands."""
    from rich.table import Table as RichTable

    from sam.skills import SkillRegistry

    table = RichTable(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column(style="dim")
    table.add_row("/help", "Show this help menu")
    table.add_row("/plan", "Toggle plan mode (read-only exploration)")
    table.add_row("/clear", "Clear the screen")
    table.add_row("/reset", "Reset conversation history")
    table.add_row("/model", "Show current model and API info")
    table.add_row("/status", "Show token usage and session stats")
    table.add_row("/exit", "Exit SAM")

    # Skills
    skills = SkillRegistry()
    for skill in skills.all_skills():
        table.add_row(f"/{skill.name}", skill.description)

    console.print(table)
    console.print()


async def _run_interactive(settings: Settings) -> None:
    """Run SAM in interactive mode."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.lexers import PygmentsLexer
    from prompt_toolkit.styles import Style as PTStyle
    from pygments.lexers.markup import MarkdownLexer

    print_banner()
    print_info(f"Model: {settings.model_id}")
    print_info(f"Working directory: {settings.working_dir}")
    console.print("[dim]Type /help for commands. Ctrl+C to cancel, Ctrl+D to quit.[/dim]")

    # Session management — resume or create
    sess_mgr = SessionManager(settings)
    session_id, conv_history = sess_mgr.get_or_create()
    if settings.session_id and len(conv_history.messages) > 0:
        print_success(f"Resumed session: {session_id} ({len(conv_history.messages)} messages)")
    else:
        print_info(f"Session: {session_id}")
    console.print()

    # Set up prompt history & session (needed before agent for ask_user input_fn)
    history_file = Path.home() / ".sam" / "prompt_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    completer = _FileCompleter(settings.working_dir)
    pt_style = PTStyle.from_dict({
        "prompt": "bold ansibrightcyan",
        "": "ansiwhite",
    })
    session = PromptSession(
        history=FileHistory(str(history_file)),
        completer=completer,
        lexer=PygmentsLexer(MarkdownLexer),
        style=pt_style,
    )

    # Input function for AskUserQuestion tool — uses prompt_toolkit
    async def _interactive_input_fn(question: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: session.prompt(HTML("<prompt>❯ </prompt>")),
        )

    agent = _build_agent(settings, input_fn=_interactive_input_fn, history=conv_history)

    # Try to build repo map
    repo_map = ""
    try:
        from sam.repo.mapper import RepoMapper
        mapper = RepoMapper(settings.working_dir, token_budget=settings.repo_map_tokens)
        repo_map = mapper.generate()
    except Exception:
        pass

    def _draw_top_border(plan_mode: bool = False):
        """Draw the top rounded border with 'You' title (yellow in plan mode)."""
        w = console.width
        label = " You [PLAN MODE] " if plan_mode else " You "
        color = "yellow" if plan_mode else "dim"
        inner = w - 2  # minus ╭ and ╮
        bar = f"\u2500{label}" + "\u2500" * max(0, inner - len(label) - 1)
        console.print(f"[{color}]\u256d{bar}\u256e[/{color}]")

    def _draw_bottom_border(plan_mode: bool = False):
        """Draw the bottom rounded border (yellow in plan mode)."""
        w = console.width
        color = "yellow" if plan_mode else "dim"
        inner = w - 2  # minus ╰ and ╯
        line = "\u2500" * inner
        console.print(f"[{color}]\u2570{line}\u256f[/{color}]")

    while True:
        console.print()
        _draw_top_border(plan_mode=agent.plan_mode)
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.prompt(HTML("<prompt>│ ❯ </prompt>")),
            )
        except (EOFError, KeyboardInterrupt):
            _draw_bottom_border(plan_mode=agent.plan_mode)
            try:
                sess_mgr.save(session_id, agent.history)
            except Exception:
                pass
            console.print(f"\n[dim]Goodbye! (session {session_id} saved)[/dim]")
            break

        _draw_bottom_border(plan_mode=agent.plan_mode)

        user_input = user_input.strip()
        if not user_input:
            continue
        # --- Slash commands ---
        cmd = user_input.lower()
        if cmd in ("exit", "quit", "/exit", "/quit"):
            try:
                sess_mgr.save(session_id, agent.history)
            except Exception:
                pass
            console.print(f"[dim]Goodbye! (session {session_id} saved)[/dim]")
            break
        if cmd == "/clear":
            console.clear()
            continue
        if cmd == "/help":
            _print_help()
            continue
        if cmd == "/plan":
            agent.plan_mode = not agent.plan_mode
            if agent.plan_mode:
                print_success(
                    "Plan mode ON — SAM will explore code and produce a plan (read-only)."
                )
            else:
                agent._pending_plan = None
                print_info("Plan mode OFF — full tool access restored.")
            continue
        if cmd == "/reset":
            session_id, conv_history = sess_mgr.create_session()
            agent = _build_agent(settings, input_fn=_interactive_input_fn, history=conv_history)
            print_success(f"Conversation reset. New session: {session_id}")
            continue
        if cmd == "/model":
            print_info(f"Model: {settings.model_id}")
            print_info(f"API:   {settings.api_base}")
            continue
        if cmd == "/status":
            n_msgs = len(agent.history.messages)
            tokens = agent.history.estimate_tokens()
            ctx = settings.context_window
            pct = int(tokens / ctx * 100) if ctx else 0
            mode = "PLAN (read-only)" if agent.plan_mode else "NORMAL"
            print_info(f"Session:  {session_id}")
            print_info(f"Mode:     {mode}")
            print_info(f"Messages: {n_msgs}")
            print_info(f"Tokens:   ~{tokens:,} / {ctx:,} ({pct}%)")
            print_info(f"Model:    {settings.model_id}")
            print_info(f"Perms:    {settings.permission_mode}")
            continue
        if cmd.startswith("/"):
            # Check if it's a skill
            from sam.skills import SkillRegistry
            skill_name = cmd[1:]  # strip leading /
            skills = SkillRegistry()
            skill = skills.get(skill_name)
            if skill:
                console.print()
                try:
                    if settings.stream:
                        await agent.run_turn_streaming(skill.prompt, repo_map=repo_map)
                    else:
                        await agent.run_turn(skill.prompt, repo_map=repo_map)
                except KeyboardInterrupt:
                    print_warning("Cancelled.")
                except Exception as e:
                    print_error(f"Error: {e}")
                try:
                    sess_mgr.save(session_id, agent.history)
                except Exception:
                    pass
                console.print()
                continue
            print_warning(f"Unknown command: {cmd}  (type /help for commands)")
            continue

        console.print()
        try:
            if settings.stream:
                await agent.run_turn_streaming(user_input, repo_map=repo_map)
            else:
                await agent.run_turn(user_input, repo_map=repo_map)
        except KeyboardInterrupt:
            print_warning("Cancelled.")
        except Exception as e:
            print_error(f"Error: {e}")

        # Auto-save session after each turn
        try:
            sess_mgr.save(session_id, agent.history)
        except Exception:
            pass

        console.print()

        # --- Plan approval flow ---
        if agent.plan_mode and agent._pending_plan:
            while True:
                console.print(
                    "[bold yellow]Approve plan?[/bold yellow]"
                    " [dim](y = execute, n = discard, edit = revise)[/dim]"
                )
                try:
                    choice = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: session.prompt(HTML("<prompt>❯ </prompt>")),
                    )
                except (EOFError, KeyboardInterrupt):
                    print_info("Plan discarded.")
                    agent._pending_plan = None
                    break

                choice = choice.strip().lower()
                if choice in ("y", "yes"):
                    plan_text = agent._pending_plan
                    agent._pending_plan = None
                    agent.plan_mode = False
                    print_success("Plan approved — executing with full tool access...")
                    console.print()
                    try:
                        _run = agent.run_turn_streaming if settings.stream else agent.run_turn
                        await _run(
                            f"Execute the following plan:\n\n{plan_text}",
                            repo_map=repo_map,
                        )
                    except KeyboardInterrupt:
                        print_warning("Cancelled.")
                    except Exception as e:
                        print_error(f"Error: {e}")
                    console.print()
                    break
                elif choice in ("n", "no"):
                    print_info("Plan discarded. Still in plan mode.")
                    agent._pending_plan = None
                    break
                elif choice in ("edit", "revise"):
                    console.print("[dim]Enter your feedback for the plan revision:[/dim]")
                    try:
                        feedback = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: session.prompt(HTML("<prompt>❯ </prompt>")),
                        )
                    except (EOFError, KeyboardInterrupt):
                        print_info("Plan discarded.")
                        agent._pending_plan = None
                        break
                    feedback = feedback.strip()
                    if not feedback:
                        print_warning("No feedback provided. Plan kept as-is.")
                        break
                    agent._pending_plan = None
                    console.print()
                    try:
                        _run = agent.run_turn_streaming if settings.stream else agent.run_turn
                        await _run(
                            f"Revise the plan based on this feedback:\n\n{feedback}",
                            repo_map=repo_map,
                        )
                    except KeyboardInterrupt:
                        print_warning("Cancelled.")
                    except Exception as e:
                        print_error(f"Error: {e}")
                    console.print()
                    # Loop back to approval if a new plan was generated
                    if not agent._pending_plan:
                        break
                else:
                    print_warning("Please enter y, n, or edit.")


async def _run_oneshot(settings: Settings, message: str) -> None:
    """Run SAM in one-shot mode."""
    agent = _build_agent(settings)

    repo_map = ""
    try:
        from sam.repo.mapper import RepoMapper
        mapper = RepoMapper(settings.working_dir, token_budget=settings.repo_map_tokens)
        repo_map = mapper.generate()
    except Exception:
        pass

    await agent.run_turn(message, repo_map=repo_map)


# --- CLI Commands ---

@click.group(invoke_without_command=True)
@click.option("-m", "--model", default=None, help="Model preset or exact model ID")
@click.option("--api-base", default=None, help="vLLM API base URL")
@click.option("-s", "--session", "session_id", default=None, help="Session ID to resume")
@click.option("--temperature", type=float, default=None, help="Sampling temperature")
@click.option("--max-tokens", type=int, default=None, help="Max tokens per response")
@click.option(
    "--response-time", "show_response_time",
    is_flag=True, default=None, help="Show LLM response time",
)
@click.option("--stream/--no-stream", default=None, help="Stream LLM responses (default: on)")
@click.option(
    "--permission-mode", "permission_mode",
    type=click.Choice(["auto", "safe", "ask"]),
    default=None, help="Permission mode (default: safe)",
)
@click.option("--tui", is_flag=True, default=False, help="Launch Textual TUI (full terminal UI)")
@click.pass_context
def main(
    ctx, model, api_base, session_id, temperature,
    max_tokens, show_response_time, stream, permission_mode, tui,
):
    """SAM — Smart Agentic Model: CLI coding agent for open-source LLMs."""
    ctx.ensure_object(dict)
    ctx.obj["model"] = model
    ctx.obj["api_base"] = api_base
    ctx.obj["session_id"] = session_id
    ctx.obj["temperature"] = temperature
    ctx.obj["max_tokens"] = max_tokens
    ctx.obj["show_response_time"] = show_response_time
    ctx.obj["stream"] = stream
    ctx.obj["permission_mode"] = permission_mode

    if ctx.invoked_subcommand is None:
        settings = _make_settings(
            model=model,
            api_base=api_base,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            show_response_time=show_response_time,
            stream=stream,
            permission_mode=permission_mode,
        )
        if tui:
            from sam.ui.tui import run_tui
            run_tui(settings)
        else:
            asyncio.run(_run_interactive(settings))


@main.command(name="chat")
@click.argument("message", nargs=-1, required=True)
@click.pass_context
def chat_cmd(ctx, message):
    """Send a one-shot message to SAM."""
    settings = _make_settings(
        model=ctx.obj["model"],
        api_base=ctx.obj["api_base"],
        session_id=ctx.obj["session_id"],
        temperature=ctx.obj["temperature"],
        max_tokens=ctx.obj["max_tokens"],
        show_response_time=ctx.obj["show_response_time"],
        stream=ctx.obj["stream"],
        permission_mode=ctx.obj["permission_mode"],
    )
    msg = " ".join(message)
    asyncio.run(_run_oneshot(settings, msg))


@main.command(name="tui")
@click.pass_context
def tui_cmd(ctx):
    """Launch SAM with the full Textual TUI."""
    settings = _make_settings(
        model=ctx.obj["model"],
        api_base=ctx.obj["api_base"],
        session_id=ctx.obj["session_id"],
        temperature=ctx.obj["temperature"],
        max_tokens=ctx.obj["max_tokens"],
        show_response_time=ctx.obj["show_response_time"],
        stream=ctx.obj["stream"],
        permission_mode=ctx.obj["permission_mode"],
    )
    from sam.ui.tui import run_tui
    run_tui(settings)


@main.command(name="models")
def models_cmd():
    """List available model presets."""
    ModelPreset.load()

    table = Table(title="SAM Model Presets")
    table.add_column("Preset", style="cyan")
    table.add_column("Model ID", style="white")
    table.add_column("Context", style="green")
    table.add_column("Description", style="dim")

    for name, info in ModelPreset.PRESETS.items():
        ctx = f"{info['context_window'] // 1024}K"
        table.add_row(name, info["model_id"], ctx, info["description"])

    console.print(table)


@main.command(name="sessions")
def sessions_cmd():
    """List saved sessions."""
    from sam.config import SESSIONS_DIR

    if not SESSIONS_DIR.exists():
        print_info("No sessions found.")
        return

    session_files = sorted(SESSIONS_DIR.glob("*.json"))
    if not session_files:
        print_info("No sessions found.")
        return

    table = Table(title="Saved Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Modified", style="dim")

    from datetime import datetime

    for sf in session_files:
        sid = sf.stem
        mtime = datetime.fromtimestamp(sf.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(sid, mtime)

    console.print(table)
