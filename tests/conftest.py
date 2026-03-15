"""Pytest configuration with Rich Toad theme for beautiful test output."""

from __future__ import annotations

import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Toad theme — greens, dark background vibes
TOAD_THEME = Theme({
    "pass": "bold bright_green",
    "fail": "bold red",
    "error": "bold bright_red",
    "skip": "bold yellow",
    "title": "bold bright_green on dark_green",
    "header": "bold green",
    "dim": "dim green",
    "file": "bright_green",
    "duration": "dim cyan",
    "count": "bold bright_white",
    "bar_pass": "green",
    "bar_fail": "red",
    "separator": "dim green",
})

console = Console(theme=TOAD_THEME)


class ToadReporter:
    """Collects test results for the Toad summary."""

    def __init__(self):
        self.results: list[dict] = []
        self.start_time: float = 0

    def start(self):
        self.start_time = time.time()

    def add(self, nodeid: str, outcome: str, duration: float, message: str = ""):
        self.results.append({
            "nodeid": nodeid,
            "outcome": outcome,
            "duration": duration,
            "message": message,
        })

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r["outcome"] == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r["outcome"] == "failed")

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r["outcome"] == "error")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r["outcome"] == "skipped")

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time


_reporter = ToadReporter()


def pytest_sessionstart(session):
    """Print Toad banner at start."""
    _reporter.start()
    toad_art = (
        "[bold bright_green]"
        "    __________  ___    ____\n"
        "   /_  __/ __ \\/   |  / __ \\\n"
        "    / / / / / / /| | / / / /\n"
        "   / / / /_/ / ___ |/ /_/ /\n"
        "  /_/  \\____/_/  |_/_____/[/bold bright_green]"
    )
    console.print()
    console.print(
        Panel(
            f"{toad_art}\n\n"
            "[bold green]SAM Test Suite[/bold green]\n"
            "[dim green]Rich + Toad Theme[/dim green]",
            border_style="bright_green",
            padding=(1, 4),
        )
    )
    console.print()


def pytest_runtest_logreport(report):
    """Capture each test result with live output."""
    if report.when != "call" and not (report.when == "setup" and report.outcome == "error"):
        return

    # Shorten the node ID for display
    nodeid = report.nodeid
    duration = report.duration

    if report.passed:
        icon = "[pass] PASS [/pass]"
        _reporter.add(nodeid, "passed", duration)
    elif report.failed:
        icon = "[fail] FAIL [/fail]"
        msg = str(report.longrepr) if report.longrepr else ""
        _reporter.add(nodeid, "failed", duration, msg)
    elif report.skipped:
        icon = "[skip] SKIP [/skip]"
        _reporter.add(nodeid, "skipped", duration)
    else:
        return

    # Live output per test
    dur_str = f"[duration]{duration:.3f}s[/duration]"
    console.print(f"  {icon}  [file]{nodeid}[/file]  {dur_str}")


def pytest_sessionfinish(session, exitstatus):
    """Print Toad summary at end."""
    console.print()
    console.print("[separator]" + "─" * console.width + "[/separator]")
    console.print()

    # Progress bar
    total = _reporter.total
    if total > 0:
        bar_width = min(console.width - 20, 60)
        pass_width = int(bar_width * _reporter.passed / total)
        fail_width = int(bar_width * _reporter.failed / total)
        skip_width = int(bar_width * _reporter.skipped / total)
        remaining = bar_width - pass_width - fail_width - skip_width

        bar = (
            "[bar_pass]" + "█" * pass_width + "[/bar_pass]"
            + "[bar_fail]" + "█" * fail_width + "[/bar_fail]"
            + "[skip]" + "█" * skip_width + "[/skip]"
            + "[dim]" + "░" * remaining + "[/dim]"
        )
        console.print(f"  {bar}  [count]{_reporter.passed}/{total}[/count]")
        console.print()

    # Summary table
    table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        title="[header]Test Results[/header]",
        title_style="header",
    )
    table.add_column(style="dim green", min_width=12)
    table.add_column(min_width=8)

    table.add_row("Passed", f"[pass]{_reporter.passed}[/pass]")
    table.add_row("Failed", f"[fail]{_reporter.failed}[/fail]")
    if _reporter.errors:
        table.add_row("Errors", f"[error]{_reporter.errors}[/error]")
    if _reporter.skipped:
        table.add_row("Skipped", f"[skip]{_reporter.skipped}[/skip]")
    table.add_row("Total", f"[count]{_reporter.total}[/count]")
    table.add_row("Duration", f"[duration]{_reporter.elapsed:.2f}s[/duration]")

    console.print(table)
    console.print()

    # Print failure details
    failures = [r for r in _reporter.results if r["outcome"] == "failed"]
    if failures:
        console.print("[fail]── Failures ──[/fail]")
        console.print()
        for f in failures:
            console.print(f"  [fail]FAIL[/fail] [file]{f['nodeid']}[/file]")
            if f["message"]:
                # Show first 20 lines of failure message
                lines = f["message"].strip().splitlines()[:20]
                for line in lines:
                    console.print(f"    [dim]{line}[/dim]")
            console.print()

    # Final verdict
    if _reporter.failed == 0 and _reporter.errors == 0:
        console.print(
            Panel(
                "[bold bright_green]All tests passed![/bold bright_green]",
                border_style="bright_green",
                padding=(0, 2),
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]{_reporter.failed} test(s) failed[/bold red]",
                border_style="red",
                padding=(0, 2),
            )
        )
    console.print()
