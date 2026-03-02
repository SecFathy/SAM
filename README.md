<h1 align="center">SAM</h1>
<h3 align="center">Smart Agentic Model</h3>

<p align="center">
  <em>An open-source CLI coding agent for your own LLMs.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/sam-agent/"><img src="https://img.shields.io/pypi/v/sam-agent?color=0073e6&label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/sam-agent/"><img src="https://img.shields.io/pypi/pyversions/sam-agent?color=0073e6" alt="Python"></a>
  <a href="https://pepy.tech/project/sam-agent"><img src="https://img.shields.io/pepy/dt/sam-agent?color=blue&label=Downloads" alt="Downloads"></a>
  <a href="https://github.com/SecFathy/SAM/blob/main/LICENSE"><img src="https://img.shields.io/github/license/SecFathy/SAM?color=green" alt="License"></a>
  <a href="https://github.com/SecFathy/SAM/stargazers"><img src="https://img.shields.io/github/stars/SecFathy/SAM?style=social" alt="Stars"></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> &bull;
  <a href="#quickstart">Quickstart</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="#plan-mode">Plan Mode</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#contributing">Contributing</a>
</p>

---

SAM is a terminal-based AI coding agent that connects to **any OpenAI-compatible API** — [vLLM](https://github.com/vllm-project/vllm), [Ollama](https://ollama.com), [LM Studio](https://lmstudio.ai), or a remote endpoint. It reads your codebase, reasons about changes, calls tools, edits files, and verifies its own work. Your code stays on your machine.

```
╭─ You ──────────────────────────────────────────────────────╮
│ ❯ add input validation to the signup endpoint              │
╰────────────────────────────────────────────────────────────╯

  grep → "def signup" in src/
  read_file → src/routes/auth.py (lines 45-80)
  read_file → src/schemas.py
  edit_file → src/routes/auth.py
    + Added email format validation
    + Added password length check
  run_command → pytest tests/test_auth.py
    12 passed

Added email format and password length validation to the signup endpoint.
```

---

## Why SAM?

| | SAM | Proprietary agents |
|---|---|---|
| **Model freedom** | Any model — Qwen, DeepSeek, Mistral, LLaMA, your fine-tunes | Locked to one provider |
| **Privacy** | Runs against local inference. Code never leaves your machine | Code sent to third-party APIs |
| **Cost** | Free with local GPU / self-hosted | Per-token billing |
| **API keys** | `api_key: "not-needed"` | Required |
| **Open source** | MIT licensed, fully extensible | Closed source |

---

## Features

| Feature | Description |
|---------|-------------|
| **ReAct Agent Loop** | Think → Act → Observe cycle with automatic tool calling and multi-step reasoning |
| **10+ Built-in Tools** | File read/write/edit, shell execution, grep, glob, git status/diff, user interaction |
| **4-Layer Fuzzy Editing** | Exact → whitespace-normalized → indentation-flexible → fuzzy matching. Built for open-source models. |
| **Plan Mode** | Read-only codebase exploration that produces a structured plan for approval before execution |
| **Repo Mapping** | Tree-sitter symbol extraction with PageRank ranking — the model sees your codebase structure |
| **Context Condensation** | Automatic history summarization at 75% context usage — long sessions stay coherent |
| **Architect / Editor** | Two-model workflow: a large model plans, a smaller model executes |
| **Sessions** | Save and resume conversations across terminal restarts |
| **Rich UI** | Markdown rendering, syntax highlighting, loading spinners, `@file` autocomplete |

---

## Installation

**From PyPI:**

```bash
pip install sam-agent
```

**With tree-sitter** (enhanced repo mapping):

```bash
pip install "sam-agent[tree-sitter]"
```

**From source:**

```bash
git clone https://github.com/SecFathy/SAM.git
cd SAM
pip install -e ".[dev]"
```

---

## Quickstart

### 1. Start an inference server

<table>
<tr><td><b>vLLM</b></td><td><b>Ollama</b></td><td><b>LM Studio</b></td></tr>
<tr>
<td>

```bash
vllm serve Qwen/Qwen2.5-Coder-32B-Instruct
```

</td>
<td>

```bash
ollama run qwen2.5-coder:32b
```

</td>
<td>

Start server in LM Studio GUI on `localhost:1234`

</td>
</tr>
</table>

### 2. Launch SAM

```bash
sam
```

SAM opens an interactive REPL. Describe what you need — it reads code, makes edits, runs commands, and verifies the result.

### 3. One-shot mode

```bash
sam chat "fix the failing test in tests/test_auth.py"
```

### 4. Other commands

```bash
sam models                     # List configured model presets
sam sessions                   # List saved sessions
sam -m deepseek-coder          # Use a specific model preset
sam --api-base http://gpu:8000/v1   # Point to a different server
```

---

## Configuration

SAM loads `config.yaml` from (in order):

1. Current working directory
2. Parent directories (walking upward)
3. `~/.sam/config.yaml` (global fallback)

Environment variables with `SAM_` prefix override any config value (e.g. `SAM_API_BASE`, `SAM_MODEL`).

<details>
<summary><b>Example config.yaml</b></summary>

```yaml
# ── API ─────────────────────────────────────────────
api_base: "http://localhost:8000/v1"
api_key: "not-needed"

# ── Model ───────────────────────────────────────────
model: "qwen-coder"

# ── Agent ───────────────────────────────────────────
max_iterations: 25          # Max tool-call loops per turn
temperature: 0.0            # 0.0 = deterministic
max_tokens: 4096            # Max tokens per LLM response
repo_map_tokens: 2048       # Token budget for repo map

# ── Model presets ───────────────────────────────────
models:
  qwen-coder:
    model_id: "Qwen/Qwen2.5-Coder-32B-Instruct"
    context_window: 131072
    description: "Qwen 32B — recommended"

  qwen3-coder:
    model_id: "Qwen/Qwen3-Coder-480B-A35B-Instruct"
    context_window: 262144
    description: "Qwen 480B MoE — highest quality"

  deepseek-coder:
    model_id: "deepseek-ai/DeepSeek-Coder-V2-Instruct"
    context_window: 131072
    description: "DeepSeek Coder V2"

  qwen-coder-7b:
    model_id: "Qwen/Qwen2.5-Coder-7B-Instruct"
    context_window: 32768
    description: "Lightweight — good for editor role"
```

</details>

---

## CLI Reference

```
Usage: sam [OPTIONS] COMMAND [ARGS]...

  SAM — Smart Agentic Model: CLI coding agent for open-source LLMs.

Commands:
  chat       Send a one-shot message to SAM
  models     List available model presets
  sessions   List saved sessions

Options:
  -m, --model TEXT         Model preset or exact model ID
  --api-base TEXT          API base URL (e.g. http://localhost:8000/v1)
  -s, --session TEXT       Resume a saved session by ID
  --temperature FLOAT      Sampling temperature (default: 0.0)
  --max-tokens INTEGER     Max tokens per response (default: 4096)
  --response-time          Print LLM response latency
  --help                   Show this message and exit
```

## Interactive Commands

| Command   | Description                              |
|-----------|------------------------------------------|
| `/help`   | Show available commands                  |
| `/plan`   | Toggle plan mode (read-only exploration) |
| `/clear`  | Clear the terminal                       |
| `/reset`  | Reset conversation history               |
| `/model`  | Show current model and API info          |
| `/status` | Show token usage, mode, and session info |
| `/exit`   | Exit SAM                                 |

**Keyboard shortcuts:** `Ctrl+C` cancel current turn &bull; `Ctrl+D` exit &bull; `Alt+Enter` newline in prompt

---

## Plan Mode

Plan mode lets you review what SAM intends to do **before** it touches any code.

Toggle it with `/plan`. SAM switches to read-only tools (grep, glob, read_file, etc.), explores the codebase, and outputs a structured implementation plan.

```
/plan

╭─ You [PLAN MODE] ──────────────────────────────────────────╮
│ ❯ add rate limiting to the API                              │
╰─────────────────────────────────────────────────────────────╯

  grep → "app.middleware" in src/
  read_file → src/app.py
  read_file → src/middleware.py
  read_file → requirements.txt

### Summary
Add token-bucket rate limiting as ASGI middleware.

### Files to Modify
- src/middleware.py — New `RateLimiter` class
- src/app.py — Register middleware in `create_app()`
- requirements.txt — Add `limits>=3.0`

### Implementation Steps
1. Add `limits` to requirements.txt
2. Create RateLimiter class in src/middleware.py
3. Register middleware in src/app.py:create_app()
4. Add tests in tests/test_rate_limit.py

### Verification
- pytest tests/test_rate_limit.py
- Manual: hit endpoint >10 times/min, expect 429

Approve plan? (y = execute, n = discard, edit = revise)
❯ y

Plan approved — executing with full tool access...
```

| Input  | Action                                          |
|--------|-------------------------------------------------|
| `y`    | Exit plan mode, execute the plan with full tools |
| `n`    | Discard the plan, stay in plan mode              |
| `edit` | Give feedback — SAM revises the plan             |

---

## Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with optional line-range pagination |
| `write_file` | Create or completely overwrite a file |
| `edit_file` | Search/replace edits with 4-layer fuzzy matching |
| `run_command` | Execute shell commands (tests, builds, git, etc.) |
| `grep` | Search file contents with regex patterns |
| `glob` | Find files matching glob patterns (`**/*.py`) |
| `list_directory` | List directory contents |
| `git_status` | Show git working tree status |
| `git_diff` | Show staged and unstaged changes |
| `ask_user` | Ask the user a question with optional choices |

---

## Supported Models

SAM works with **any model** served through an OpenAI-compatible API. Tested with:

| Model | Params | Context | Recommendation |
|-------|--------|---------|----------------|
| **Qwen2.5-Coder-32B-Instruct** | 32B | 128K | Best all-around for single-GPU setups |
| **Qwen3-Coder-480B-A35B** | 480B MoE | 256K | Highest quality — needs multi-GPU |
| **DeepSeek-Coder-V2** | 236B MoE | 128K | Strong alternative to Qwen |
| **Qwen2.5-Coder-7B** | 7B | 32K | Fast — good as editor in two-model split |
| **CodeLlama-34B** | 34B | 16K | Meta's code model |
| **Mistral-Large** | 123B | 128K | Strong general-purpose |

> Add your own models in `config.yaml` under the `models:` key.

---

## Architecture

```
sam/
├── cli.py                    # Click CLI entry point + interactive REPL
├── config.py                 # Pydantic settings + YAML config loading
├── context.py                # @file mention resolution
│
├── agent/
│   ├── loop.py               # Core ReAct agent loop (Think → Act → Observe)
│   ├── history.py            # Conversation history with token tracking
│   ├── planner.py            # Architect/Editor two-model workflow
│   └── condensation.py       # Context condensation at 75% capacity
│
├── tools/
│   ├── base.py               # Tool ABC, ToolResult, ToolRegistry
│   ├── file_read.py          # Read with pagination
│   ├── file_write.py         # Create / overwrite files
│   ├── file_edit.py          # 4-layer fuzzy search/replace
│   ├── shell.py              # Shell execution with timeout + safety
│   ├── grep_tool.py          # Regex content search
│   ├── glob_tool.py          # File pattern matching
│   ├── git.py                # git status + git diff
│   └── ask_user.py           # Interactive user questions
│
├── models/
│   ├── provider.py           # OpenAI SDK wrapper (vLLM / Ollama / any)
│   ├── streaming.py          # Stream accumulator + tool call parsing
│   ├── registry.py           # Model preset registry
│   └── tool_protocol.py      # Tool call protocol definitions
│
├── repo/
│   ├── mapper.py             # Tree-sitter + PageRank repo mapping
│   ├── tags.py               # Symbol extraction from source files
│   ├── graph.py              # Dependency graph construction
│   └── languages.py          # Language detection + grammar registry
│
├── session/
│   ├── storage.py            # Session persistence (JSON)
│   └── manager.py            # Session lifecycle management
│
├── ui/
│   ├── console.py            # Rich console + output helpers
│   ├── display.py            # Markdown + code rendering
│   ├── spinner.py            # Loading spinners
│   └── prompt.py             # Prompt utilities
│
└── prompts/
    ├── system.md             # Main system prompt template
    └── plan_mode.md          # Plan mode system prompt template
```

---

## Contributing

Contributions are welcome. To get started:

```bash
git clone https://github.com/SecFathy/SAM.git
cd SAM
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check sam/
```

**Guidelines:**
- Follow existing code style and conventions
- Add tests for new tools or agent behavior changes
- Keep PRs focused — one feature or fix per PR

---

## Roadmap

- [ ] Multi-file diff preview before applying edits
- [ ] MCP (Model Context Protocol) server support
- [ ] Plugin system for custom tools
- [ ] Web UI dashboard
- [ ] VS Code / JetBrains extension
- [ ] Streaming output in agent loop
- [ ] Auto-detect inference server (vLLM, Ollama, LM Studio)

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Built by <a href="https://github.com/SecFathy">@SecFathy</a>
</p>
