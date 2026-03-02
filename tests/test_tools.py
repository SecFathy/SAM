"""Tests for individual tools."""

import pytest
import tempfile
from pathlib import Path

from sam.tools.base import ToolRegistry
from sam.tools.file_read import FileReadTool
from sam.tools.file_write import FileWriteTool
from sam.tools.shell import ShellTool
from sam.tools.directory import DirectoryTool
from sam.tools.grep_tool import GrepTool
from sam.tools.glob_tool import GlobTool


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# --- FileReadTool ---

@pytest.mark.asyncio
async def test_read_file(tmp_dir):
    (tmp_dir / "hello.txt").write_text("line1\nline2\nline3\n")
    tool = FileReadTool(tmp_dir)
    result = await tool.execute(path="hello.txt")
    assert not result.error
    assert "line1" in result.output
    assert "line2" in result.output
    assert "3 lines" in result.output


@pytest.mark.asyncio
async def test_read_file_with_offset(tmp_dir):
    content = "\n".join(f"line{i}" for i in range(1, 11))
    (tmp_dir / "big.txt").write_text(content)
    tool = FileReadTool(tmp_dir)
    result = await tool.execute(path="big.txt", offset=5, limit=3)
    assert not result.error
    assert "line5" in result.output
    assert "line7" in result.output


@pytest.mark.asyncio
async def test_read_nonexistent(tmp_dir):
    tool = FileReadTool(tmp_dir)
    result = await tool.execute(path="nope.txt")
    assert result.error


# --- FileWriteTool ---

@pytest.mark.asyncio
async def test_write_new_file(tmp_dir):
    tool = FileWriteTool(tmp_dir)
    result = await tool.execute(path="new.py", content="print('hello')\n")
    assert not result.error
    assert "Created" in result.output
    assert (tmp_dir / "new.py").read_text() == "print('hello')\n"


@pytest.mark.asyncio
async def test_write_creates_dirs(tmp_dir):
    tool = FileWriteTool(tmp_dir)
    result = await tool.execute(path="sub/dir/file.py", content="x = 1\n")
    assert not result.error
    assert (tmp_dir / "sub" / "dir" / "file.py").exists()


# --- ShellTool ---

@pytest.mark.asyncio
async def test_shell_echo(tmp_dir):
    tool = ShellTool(tmp_dir)
    result = await tool.execute(command="echo hello")
    assert not result.error
    assert "hello" in result.output


@pytest.mark.asyncio
async def test_shell_error(tmp_dir):
    tool = ShellTool(tmp_dir)
    result = await tool.execute(command="exit 1")
    assert result.error


@pytest.mark.asyncio
async def test_shell_blocked_command(tmp_dir):
    tool = ShellTool(tmp_dir)
    result = await tool.execute(command="rm -rf /")
    assert result.error
    assert "blocked" in result.output.lower()


@pytest.mark.asyncio
async def test_shell_timeout(tmp_dir):
    tool = ShellTool(tmp_dir)
    result = await tool.execute(command="sleep 10", timeout=1)
    assert result.error
    assert "timed out" in result.output.lower()


# --- DirectoryTool ---

@pytest.mark.asyncio
async def test_list_directory(tmp_dir):
    (tmp_dir / "file1.py").write_text("x")
    (tmp_dir / "file2.txt").write_text("y")
    (tmp_dir / "subdir").mkdir()

    tool = DirectoryTool(tmp_dir)
    result = await tool.execute(path=".")
    assert not result.error
    assert "file1.py" in result.output
    assert "subdir/" in result.output


# --- GrepTool ---

@pytest.mark.asyncio
async def test_grep_finds_pattern(tmp_dir):
    (tmp_dir / "code.py").write_text("def hello():\n    return 'world'\n")
    tool = GrepTool(tmp_dir)
    result = await tool.execute(pattern="def hello")
    assert not result.error
    assert "code.py" in result.output


@pytest.mark.asyncio
async def test_grep_no_match(tmp_dir):
    (tmp_dir / "code.py").write_text("x = 1\n")
    tool = GrepTool(tmp_dir)
    result = await tool.execute(pattern="zzz_nonexistent")
    assert "No matches" in result.output


# --- GlobTool ---

@pytest.mark.asyncio
async def test_glob_finds_files(tmp_dir):
    (tmp_dir / "a.py").write_text("x")
    (tmp_dir / "b.py").write_text("y")
    (tmp_dir / "c.txt").write_text("z")

    tool = GlobTool(tmp_dir)
    result = await tool.execute(pattern="*.py")
    assert not result.error
    assert "a.py" in result.output
    assert "b.py" in result.output
    assert "c.txt" not in result.output


# --- ToolRegistry ---

@pytest.mark.asyncio
async def test_registry(tmp_dir):
    registry = ToolRegistry()
    registry.register(FileReadTool(tmp_dir))
    registry.register(ShellTool(tmp_dir))

    assert registry.get("read_file") is not None
    assert registry.get("nonexistent") is None
    assert len(registry.all_tools()) == 2

    schemas = registry.to_openai_schemas()
    assert len(schemas) == 2
    assert schemas[0]["type"] == "function"


@pytest.mark.asyncio
async def test_registry_execute_unknown(tmp_dir):
    registry = ToolRegistry()
    result = await registry.execute("unknown_tool", {})
    assert result.error
    assert "Unknown tool" in result.output
