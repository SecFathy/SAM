"""Skill registry and built-in skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Skill:
    """A skill is a named prompt template triggered by /name."""

    name: str
    description: str
    prompt: str


# Built-in skills
_BUILTIN_SKILLS: list[Skill] = [
    Skill(
        name="commit",
        description="Stage and commit changes with a good message",
        prompt=(
            "Look at the current git diff (staged and unstaged). "
            "Stage the relevant changed files (do NOT use git add -A). "
            "Write a concise, conventional commit message that describes "
            "WHAT changed and WHY. Create the commit. "
            "Do NOT push to remote."
        ),
    ),
    Skill(
        name="test",
        description="Find and run the project's test suite",
        prompt=(
            "Detect the project's test framework (pytest, unittest, jest, etc.) "
            "and run the test suite. Report results clearly. "
            "If tests fail, analyze the failures and suggest fixes."
        ),
    ),
    Skill(
        name="lint",
        description="Run the project's linter/formatter",
        prompt=(
            "Detect the project's linter/formatter (ruff, black, eslint, etc.) "
            "from config files. Run it and report results. "
            "If there are auto-fixable issues, fix them."
        ),
    ),
    Skill(
        name="review",
        description="Review recent changes for issues",
        prompt=(
            "Look at the current git diff. Review the changes for:\n"
            "- Bugs and logic errors\n"
            "- Security vulnerabilities\n"
            "- Performance issues\n"
            "- Code style and best practices\n"
            "Provide a concise review with specific line references."
        ),
    ),
    Skill(
        name="explain",
        description="Explain the current project structure",
        prompt=(
            "Explore the project structure, read key files (README, config, entry points), "
            "and provide a concise explanation of:\n"
            "- What the project does\n"
            "- Key directories and files\n"
            "- Tech stack and dependencies\n"
            "- How to build and run it"
        ),
    ),
]


class SkillRegistry:
    """Registry of available skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in _BUILTIN_SKILLS:
            self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def names(self) -> list[str]:
        return sorted(self._skills.keys())
