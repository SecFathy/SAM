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
    # Item 1: Auto-fix loop
    Skill(
        name="fix",
        description="Edit code, run tests, fix failures — repeat until green",
        prompt=(
            "You are in auto-fix mode. Follow this loop:\n"
            "1. Run the project's test suite (detect pytest/unittest/jest/etc.)\n"
            "2. If all tests pass, report success and stop.\n"
            "3. If tests fail, read the failing test files and the source files involved.\n"
            "4. Analyze the root cause of each failure.\n"
            "5. Edit the source code to fix the failures (NOT the tests, unless the tests are wrong).\n"
            "6. Go back to step 1.\n\n"
            "Continue this loop until all tests pass or you've tried 5 fix attempts. "
            "If you can't fix a failure after 5 attempts, report what you tried and what's still failing. "
            "Create a checkpoint before making changes."
        ),
    ),
    # Item 3: Git workflow skills
    Skill(
        name="pr",
        description="Create a pull request from current changes",
        prompt=(
            "Prepare and create a GitHub pull request:\n"
            "1. Check `git status` and `git diff` for current changes.\n"
            "2. If changes are uncommitted, stage and commit them with a good message.\n"
            "3. Check if you're on a feature branch. If on main/master, create a descriptive branch first.\n"
            "4. Push the branch to origin.\n"
            "5. Create a PR using `gh pr create` with:\n"
            "   - A concise title (under 70 chars)\n"
            "   - A body with ## Summary (bullet points of changes) and ## Test plan\n"
            "6. Report the PR URL."
        ),
    ),
    Skill(
        name="branch",
        description="Create a feature branch for a task",
        prompt=(
            "Create a new feature branch:\n"
            "1. Ask the user what the feature/task is (via ask_user).\n"
            "2. Generate a good branch name (e.g., feat/add-auth, fix/memory-leak).\n"
            "3. Create and switch to the new branch from main/master.\n"
            "4. Report the branch name."
        ),
    ),
    Skill(
        name="conflict",
        description="Detect and resolve merge conflicts",
        prompt=(
            "Check for and resolve git merge conflicts:\n"
            "1. Run `git status` to check for conflict markers.\n"
            "2. For each conflicted file, read it and identify the conflict sections.\n"
            "3. Analyze both sides of each conflict and determine the correct resolution.\n"
            "4. Edit the files to resolve conflicts (remove conflict markers).\n"
            "5. Stage the resolved files.\n"
            "6. Report what was resolved."
        ),
    ),
    Skill(
        name="changelog",
        description="Generate changelog from recent commits",
        prompt=(
            "Generate a changelog:\n"
            "1. Run `git log --oneline` to see recent commits (last 20).\n"
            "2. Optionally check `git tag` for version tags.\n"
            "3. Group commits by type (Features, Fixes, Refactoring, etc.).\n"
            "4. Format as a clean markdown changelog.\n"
            "5. Print the changelog (do NOT write to a file unless asked)."
        ),
    ),
    # Item 6: Project scaffolding skills
    Skill(
        name="init",
        description="Set up missing project configs (.gitignore, CI, etc.)",
        prompt=(
            "Analyze the project and set up missing configuration:\n"
            "1. Detect the project type (Python, Node, Rust, Go, etc.) from existing files.\n"
            "2. Check for and create missing essential configs:\n"
            "   - .gitignore (language-appropriate)\n"
            "   - pyproject.toml / package.json / Cargo.toml (if missing)\n"
            "   - Basic CI config (.github/workflows/ci.yml)\n"
            "   - .editorconfig\n"
            "3. Only create files that are missing — do NOT overwrite existing configs.\n"
            "4. Report what was created."
        ),
    ),
    Skill(
        name="deps",
        description="Audit dependencies for issues",
        prompt=(
            "Audit the project's dependencies:\n"
            "1. Detect the package manager (pip/npm/cargo/go).\n"
            "2. Check for outdated packages (pip list --outdated / npm outdated).\n"
            "3. Look for known security vulnerabilities (pip-audit / npm audit if available).\n"
            "4. Check for unused dependencies by searching imports.\n"
            "5. Report findings with recommendations."
        ),
    ),
    Skill(
        name="doc",
        description="Generate docstrings and documentation from code",
        prompt=(
            "Generate documentation for the project:\n"
            "1. Read the project's main source files.\n"
            "2. Identify public functions, classes, and methods lacking docstrings.\n"
            "3. Add clear, concise docstrings following the project's existing style.\n"
            "4. If no style exists, use Google-style docstrings for Python, JSDoc for JS/TS.\n"
            "5. Report what was documented."
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
