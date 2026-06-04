"""Shared configuration, persistence, Lean helpers, prompt builders, and OpenAI wrappers."""
from __future__ import annotations

import os
import re
import time
import leanclient as lc
from dataclasses import dataclass
from types import SimpleNamespace
from openai import OpenAI


PROJECT_PATH = os.getenv("LEAN_PROJECT_PATH", r"...")
FILE_PATH    = os.getenv("LEAN_FILE_PATH", r"...")   # relative to PROJECT_PATH
LEAN_DIR     = os.getenv("LEAN_DIR", r"...")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "20"))

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")


openai_client = OpenAI(api_key="...")

# ── Persistence paths ────────────────────────────────────────────────────────
_HISTORY_DIR  = os.getenv("LEAN_AGENT_HISTORY_DIR", r"...")
LEARNING_FILE = os.path.join(_HISTORY_DIR, "agent_learning.json")
HISTORY_FILE  = os.path.join(_HISTORY_DIR, "agent_run_history.json")

def _save_json(path: str, data) -> None:
    import json
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
 
 
def _load_json(path: str, default):
    import json
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
 
 
def get_file_content(sfc: lc.SingleFileClient) -> str:
    return sfc.get_file_content()
 
 
def get_diagnostics_summary(sfc: lc.SingleFileClient) -> list[dict]:
    diags = sfc.get_diagnostics()
    return [
        {
            "severity": d.get("severity"),
            "message": d.get("message", ""),
            "line": d.get("range", {}).get("start", {}).get("line"),
            "character": d.get("range", {}).get("start", {}).get("character"),
        }
        for d in diags
        if d.get("severity") in (1, 2)
    ]
 
 
def get_errors_only(sfc: lc.SingleFileClient) -> list[dict]:
    diags = sfc.get_diagnostics()
    results = []
    for d in diags:
        if d.get("severity") != 1:
            continue
        line = d.get("range", {}).get("start", {}).get("line")
        character = d.get("range", {}).get("start", {}).get("character")
        try:
            goal = sfc.get_goal(line, character)
        except Exception:
            goal = None
        results.append({
            "severity": d.get("severity"),
            "message": d.get("message", ""),
            "line": line,
            "character": character,
            "goal": goal,
        })
    return results
 
 
def find_first_sorry(sfc: lc.SingleFileClient) -> dict | None:
    content = sfc.get_file_content()
    lines = content.splitlines()
    for line_idx, text in enumerate(lines):
        col = text.find("sorry")
        if col != -1:
            try:
                goal = sfc.get_goal(line_idx, col)
            except Exception:
                goal = None
            return {
                "line": line_idx,
                "character": col,
                "goal": goal,
                "source_line": text.strip(),
            }
    return None
 
 
def has_sorry(content: str) -> bool:
    return "sorry" in content or "admit" in content
 
 
# ── Block extraction ──────────────────────────────────────────────────────────
 
_BLOCK_STARTERS = re.compile(
    r"^(theorem|lemma|def |noncomputable def|noncomputable lemma|abbrev|structure|class|instance|example)\b"
)
 
 
def find_enclosing_block(content: str, target_line: int) -> tuple[int, int, str]:
    """Return (block_start, block_end, block_text) for the top-level Lean block
    that contains target_line (0-based).
 
    A block starts at a line matching _BLOCK_STARTERS and ends just before the
    next such line (or at end-of-file).  If target_line is not inside any named
    block the entire file is returned so the caller always gets something to work with.
    """
    lines = content.splitlines(keepends=True)
    n = len(lines)
 
    block_start = 0
    for i in range(n):
        stripped = lines[i].lstrip()
        if _BLOCK_STARTERS.match(stripped):
            if i <= target_line:
                block_start = i
            elif i > target_line:
                # We've passed the target — the previous block_start is correct.
                block_end = i - 1
                block_text = "".join(lines[block_start:i])
                return block_start, block_end, block_text
 
    # target is in the last block (or file has no starters)
    block_text = "".join(lines[block_start:])
    return block_start, n - 1, block_text
 
 
def splice_block(original_content: str, block_start: int, block_end: int, new_block: str) -> str:
    """Replace lines [block_start, block_end] (inclusive, 0-based) with new_block."""
    lines = original_content.splitlines(keepends=True)
    before = "".join(lines[:block_start])
    after  = "".join(lines[block_end + 1:])
    if new_block and not new_block.endswith("\n"):
        new_block += "\n"
    return before + new_block + after
 
 
# ── Comment stripping ─────────────────────────────────────────────────────────
 
def strip_lean_comments(text: str) -> str:
    """Remove Lean comments from LLM output:
      - line comments: everything from '--' to end of line
      - block comments: /- ... -/ (non-nested for simplicity)
    """
    # Remove block comments first (non-greedy)
    text = re.sub(r"/-.*?-/", "", text, flags=re.DOTALL)
    # Remove line comments
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        # Find '--' that is not inside a string (heuristic: strip if '--' appears)
        idx = line.find("--")
        if idx != -1:
            line = line[:idx].rstrip()
        if line or not cleaned or cleaned[-1]:  # avoid collapsing multiple blank lines
            cleaned.append(line)
    return "\n".join(cleaned)
 
 
# ── Fence stripping ───────────────────────────────────────────────────────────
 
def strip_fences(text: str) -> str:
    if "```lean" in text:
        start = text.find("```lean") + len("```lean")
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()
    if "```" in text:
        start = text.find("```") + 3
        newline = text.find("\n", start)
        if newline != -1:
            start = newline + 1
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if any(s.startswith(t) for t in [
            "import", "theorem", "lemma", "def ", "noncomputable",
            "section", "namespace", "open ", "variable", "set_option",
            "#", "have ", "obtain", "calc", "by",
        ]):
            return "\n".join(lines[i:]).strip()
    return text.strip()
 
 
# ── Prompt builders (block-scoped) ────────────────────────────────────────────
 
def build_fix_prompt(block_text: str, errors: list[dict], block_start: int) -> str:
    error_lines = []
    for e in errors:
        relative_line = (e["line"] - block_start) if e.get("line") is not None else "?"
        entry = f"  Block-line {relative_line}, Col {e['character']} [ERROR]: {e['message']}"
        if e.get("goal"):
            entry += f"\n    Proof goal:\n{e['goal']}"
        error_lines.append(entry)
    error_text = "\n".join(error_lines)
    return (
        "Fix ONLY the errors in the following Lean 4 block. "
        "Output the corrected block only — no explanation, no markdown fences, no comments.\n\n"
        f"Errors:\n{error_text}\n\n"
        f"Block to fix:\n{block_text}"
    )
 
 
def build_sorry_prompt(block_text: str, sorry_info: dict | None, block_start: int) -> str:
    goal_block = ""
    if sorry_info and sorry_info.get("goal"):
        relative_line = (sorry_info["line"] - block_start) if sorry_info.get("line") is not None else "?"
        goal_block = f"Proof goal at the sorry (block-line {relative_line}):\n{sorry_info['goal']}\n\n"
    return (
        "Replace ONLY the FIRST 'sorry' in the following Lean 4 block with a real proof. "
        "Do NOT change anything else. "
        "Output the corrected block only — no explanation, no markdown fences, no comments.\n\n"
        + goal_block
        + f"Block to complete:\n{block_text}"
    )
 
 
# ── Reflection prompts (these use full file for context, no code output) ──────
 
def build_reflection_prompt_with_errors(file_content: str, errors: list[dict]) -> str:
    error_lines = []
    for e in errors:
        entry = f"  Line {e['line']}, Col {e['character']} [ERROR]: {e['message']}"
        if e.get("goal"):
            entry += f"\n    Goal: {e['goal']}"
        error_lines.append(entry)
    error_text = "\n".join(error_lines)
    return (
        "You are a Lean 4 expert and mathematician. Reflect on the following Lean 4 file and its errors.\n\n"
        f"File:\n```lean\n{file_content}\n```\n\n"
        f"Errors:\n{error_text}\n\n"
        "1. Write out the mathematical proof of each theorem in plain English, step by step.\n"
        "2. For each error classify it: TYPE ERROR / SYNTAX ERROR / MISSING THEOREM / LOGIC ERROR.\n"
        "3. Suggest a concrete fix for each error.\n\n"
        "Be specific and mathematical. This reflection guides the next fix attempt."
    )
 
 
def build_reflection_prompt_no_errors(file_content: str) -> str:
    return (
        "You are a Lean 4 expert and mathematician. "
        "Reflect on the following Lean 4 file which has no errors but still contains 'sorry' placeholders.\n\n"
        f"File:\n```lean\n{file_content}\n```\n\n"
        "1. For each theorem with 'sorry', write out the full mathematical proof in plain English.\n"
        "2. Suggest which Lean 4 / Mathlib4 tactics or lemmas would best implement each proof step.\n"
        "3. Flag any theorems that may be difficult or impossible to prove with current Mathlib4.\n\n"
        "Be specific and mathematical. This reflection guides the next proof attempt."
    )
 
 
# ── LLM / OpenAI agent helpers ───────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Small compatibility wrapper around an OpenAI Responses API response.

    The rest of the agent code was originally written against Anthropic's
    `.content[0].text` and `.usage.input_tokens` interface.  This wrapper keeps
    the Lean repair loop unchanged while using OpenAI's Responses API underneath.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        self.content = [SimpleNamespace(text=self.text)]
        self.usage = SimpleNamespace(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


def _normalise_messages(messages: list[dict]) -> list[dict]:
    """Convert stored conversation turns to Responses API input messages."""
    normalised: list[dict] = []
    for message in messages:
        role = message.get("role", "user")
        if role not in {"user", "assistant", "developer", "system"}:
            role = "user"
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        normalised.append({"role": role, "content": content})
    return normalised


def _extract_response_text(response) -> str:
    """Extract text robustly from an OpenAI Responses API result."""
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for part in getattr(item, "content", []) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _usage_tokens(response) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "prompt_tokens", 0)
    if output_tokens is None:
        output_tokens = getattr(usage, "completion_tokens", 0)
    return int(input_tokens or 0), int(output_tokens or 0)


def call_api_with_retry(messages: list, system: str, max_tokens: int, max_retries: int = 3) -> LLMResponse:
    """Call the OpenAI-backed Lean agent using gpt-5.4-mini by default."""
    for attempt in range(max_retries):
        try:
            response = openai_client.responses.create(
                model=OPENAI_MODEL,
                instructions=system,
                input=_normalise_messages(messages),
                max_output_tokens=max_tokens,
                reasoning={"effort": OPENAI_REASONING_EFFORT},
            )
            text = _extract_response_text(response)
            input_tokens, output_tokens = _usage_tokens(response)
            return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
        except Exception as e:
            lower = str(e).lower()
            retryable = any(marker in lower for marker in [
                "rate_limit", "rate limit", "429", "timeout", "temporarily unavailable", "overloaded"
            ])
            if retryable and attempt < max_retries - 1:
                wait = 60 * (attempt + 1)
                print(f"⏳ OpenAI API retryable error. Waiting {wait}s before retry {attempt + 2}/{max_retries}...")
                time.sleep(wait)
            else:
                raise
 
 
def trim_history(conversation_history: list, keep_last: int = 6) -> list:
    if len(conversation_history) > keep_last:
        print(f"✂️  Trimming conversation history to last {keep_last} messages.")
        return conversation_history[-keep_last:]
    return conversation_history
 
 
# ── File application ──────────────────────────────────────────────────────────
 
def apply_full_replacement(sfc: lc.SingleFileClient, new_content: str):
    old = sfc.get_file_content()
    old_lines = old.splitlines()
    last_line = len(old_lines) - 1
    last_char = len(old_lines[-1]) if old_lines else 0
    change = lc.DocumentContentChange(
        text=new_content,
        start=[0, 0],
        end=[last_line, last_char],
    )
    sfc.update_file(changes=[change])
 
 
def write_to_disk(content: str):
    full_path = os.path.join(PROJECT_PATH, FILE_PATH)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
