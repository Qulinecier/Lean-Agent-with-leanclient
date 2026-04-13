# lean-proof-agent

An LLM-powered agent that automatically fixes errors and completes `sorry` placeholders in Lean 4 proof files, using real compiler feedback via the Lean 4 language server (LSP).

## How It Works

The agent operates in a feedback loop with the Lean LSP:

1. **Fix errors** — if the file has type errors or syntax errors, the agent reads the diagnostics (line, column, message) and asks Claude to fix them.
2. **Complete sorries** — once the file is error-free, the agent replaces any remaining `sorry` placeholders with real proofs.
3. **Reflect** — every few iterations, the agent runs a reflection pass: it reasons mathematically about the proof strategy before attempting another fix. This helps avoid getting stuck in repeated failed attempts.
4. **Finish** — the loop terminates when the file has no errors and no `sorry`.

It also includes a **reading agent** that explains the mathematical content of your Lean files in plain English, highlighting where `sorry` appears and suggesting proof strategies.

## Requirements

- Python 3.10+
- A Lean 4 project (with a `lakefile.toml`)
- An [Anthropic API key](https://console.anthropic.com/)

## Installation

```bash
git clone https://github.com/yourusername/lean-proof-agent
cd lean-proof-agent
pip install -e .
```

This will automatically install [`leanclient`](https://github.com/oOo0oOo/leanclient) and the Anthropic SDK.

Set your API key:

```bash
export ANTHROPIC_API_KEY=your_key_here
```



## Configuration

At the top of `core_agent.py`, set these variables to point to your Lean project:

```python
PROJECT_PATH = "/path/to/your/lean/project"   # directory containing lakefile.toml
FILE_PATH = "MyProject/MyFile.lean"            # relative path to the file to work on
LEAN_DIR = "/path/to/your/lean/project/MyProject/"  # directory to scan for .lean files
MAX_ITERATIONS = 7                             # max fix attempts before stopping
```

## Usage

**Run the proof agent** (fix errors + complete sorries):

```powershell
python -X utf8 core_agent.py
```

**Run the reading agent** (explain Lean files in plain English):

```python
from core_agent import reading_agent
reading_agent()
```


## Dependencies

- [leanclient](https://github.com/oOo0oOo/leanclient) — Python client for the Lean 4 language server
- [anthropic](https://github.com/anthropics/anthropic-sdk-python) — Anthropic Python SDK

