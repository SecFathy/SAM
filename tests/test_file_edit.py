"""Tests for the 4-layer fuzzy file editing."""

import pytest
import tempfile
from pathlib import Path

from sam.tools.file_edit import FileEditTool


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def tool(tmp_dir):
    return FileEditTool(tmp_dir)


def write_file(tmp_dir: Path, name: str, content: str) -> Path:
    p = tmp_dir / name
    p.write_text(content)
    return p


# --- Layer 1: Exact Match ---

@pytest.mark.asyncio
async def test_exact_match(tmp_dir, tool):
    write_file(tmp_dir, "test.py", "def hello():\n    return 'world'\n")
    result = await tool.execute(
        path="test.py",
        search="def hello():\n    return 'world'",
        replace="def hello():\n    return 'universe'",
    )
    assert not result.error
    assert "exact match" in result.output
    content = (tmp_dir / "test.py").read_text()
    assert "universe" in content


# --- Layer 2: Whitespace-Normalized ---

@pytest.mark.asyncio
async def test_whitespace_normalized(tmp_dir, tool):
    write_file(tmp_dir, "test.py", "x  =   1\n")
    result = await tool.execute(
        path="test.py",
        search="x = 1",
        replace="x = 2",
    )
    assert not result.error
    assert "whitespace" in result.output.lower() or "exact" in result.output.lower()
    content = (tmp_dir / "test.py").read_text()
    assert "2" in content


# --- Layer 3: Indentation-Flexible ---

@pytest.mark.asyncio
async def test_indentation_flexible(tmp_dir, tool):
    content = "class Foo:\n    def bar(self):\n        return 1\n"
    write_file(tmp_dir, "test.py", content)
    # Search with wrong indentation
    result = await tool.execute(
        path="test.py",
        search="def bar(self):\n    return 1",
        replace="def bar(self):\n    return 2",
    )
    assert not result.error
    new_content = (tmp_dir / "test.py").read_text()
    assert "return 2" in new_content


# --- Layer 4: Fuzzy Match ---

@pytest.mark.asyncio
async def test_fuzzy_match(tmp_dir, tool):
    content = "def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item.price\n    return total\n"
    write_file(tmp_dir, "test.py", content)
    # Slightly different text (typo, minor changes)
    result = await tool.execute(
        path="test.py",
        search="def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item.price\n    return  total",
        replace="def calculate_total(items):\n    return sum(item.price for item in items)",
    )
    assert not result.error
    new_content = (tmp_dir / "test.py").read_text()
    assert "sum(item.price" in new_content


# --- Error Cases ---

@pytest.mark.asyncio
async def test_file_not_found(tool):
    result = await tool.execute(path="nonexistent.py", search="x", replace="y")
    assert result.error
    assert "not found" in result.output.lower()


@pytest.mark.asyncio
async def test_no_match(tmp_dir, tool):
    write_file(tmp_dir, "test.py", "hello world\n")
    result = await tool.execute(
        path="test.py",
        search="completely different text that does not exist anywhere",
        replace="replacement",
    )
    assert result.error
    assert "could not find" in result.output.lower()
