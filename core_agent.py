import os
import time
import leanclient as lc
from anthropic import Anthropic

PROJECT_PATH = "..."
FILE_PATH = "..."
LEAN_DIR = "..."
MAX_ITERATIONS = 7

anthropic_client = Anthropic()


def get_file_content(sfc: lc.SingleFileClient) -> str:
    return sfc.get_file_content()


def get_diagnostics_summary(sfc: lc.SingleFileClient) -> list[dict]:
    """Return errors and warnings with location info."""
    diags = sfc.get_diagnostics()
    return [
        {
            "severity": d.get("severity"),  # 1=error, 2=warning, 3=info
            "message": d.get("message", ""),
            "line": d.get("range", {}).get("start", {}).get("line"),
            "character": d.get("range", {}).get("start", {}).get("character"),
        }
        for d in diags
        if d.get("severity") in (1, 2)  # errors + warnings only
    ]


def build_prompt(file_content: str, diagnostics: list[dict]) -> str:
    diag_text = "\n".join(
        f"  Line {d['line']}, Col {d['character']} [{['', 'ERROR', 'WARN'][d['severity']]}]: {d['message']}"
        for d in diagnostics
    )
    return f"""You are a Lean 4 expert. Fix the errors in the following Lean file.

## Diagnostics
{diag_text}

## Current file content
```lean
{file_content}
```

Respond with ONLY the corrected Lean 4 file content. No explanation, no markdown fences."""


def apply_full_replacement(sfc: lc.SingleFileClient, new_content: str):
    """Replace entire file content in the LSP (not on disk)."""
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

def read_lean_files(directory: str) -> dict[str, str]:
    """Read all .lean files in the directory. Returns {filename: content}."""
    files = {}
    for fname in os.listdir(directory):
        if fname.endswith(".lean"):
            full_path = os.path.join(directory, fname)
            with open(full_path, "r", encoding="utf-8") as f:
                files[fname] = f.read()
    return files


def explain_lean_file(filename: str, content: str, conversation_history: list) -> list:
    """Ask the LLM to explain the math in the file in plain English."""

    user_message = f"""Here is a Lean 4 file called '{filename}'. 
Please explain the mathematical or abstract definitions in it in plain, human-readable English.
Do not produce any code. Just describe what each definition, theorem, or structure means mathematically. 
Pay more attention to where sorry is, and first use math or abstract proof to prove it and describe it wordly.

````lean
{content}
```
"""

    conversation_history.append({"role": "user", "content": user_message})

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="You are a mathematics expert who explains Lean 4 code in clear, plain English for someone learning formal verification.",
        messages=conversation_history,
    )

    explanation = response.content[0].text.strip()
    conversation_history.append({"role": "assistant", "content": explanation})

    return conversation_history


def reading_agent():
    lean_files = read_lean_files(LEAN_DIR)

    if not lean_files:
        print("No .lean files found in", LEAN_DIR)
        return

    print(f"Found {len(lean_files)} Lean file(s): {', '.join(lean_files.keys())}\n")

    for filename, content in lean_files.items():
        print(f"\n{'='*50}")
        print(f"📄 File: {filename}")
        print("="*50)

        conversation_history = []  # fresh conversation per file

        # Step 1: LLM explains the file
        conversation_history = explain_lean_file(filename, content, conversation_history)
        explanation = conversation_history[-1]["content"]

        print("\n🤖 Here's what I understand about this file mathematically:\n")
        print(explanation)

        # Step 2: Ask user to confirm or correct
        print("\n" + "-"*50)

    print("✅ All files reviewed!")


def get_errors_only(sfc: lc.SingleFileClient) -> list[dict]:
    """Return only severity=1 (errors), ignore warnings."""
    diags = sfc.get_diagnostics()
    return [
        {
            "severity": d.get("severity"),
            "message": d.get("message", ""),
            "line": d.get("range", {}).get("start", {}).get("line"),
            "character": d.get("range", {}).get("start", {}).get("character"),
        }
        for d in diags
        if d.get("severity") == 1  # 1 = error only, skip warnings
    ]


def has_sorry(content: str) -> bool:
    """Check if the file still contains unfinished sorry placeholders."""
    if "sorry" in content:
        return True
    elif "admit" in content:
        return True
    else:
        return False


def build_fix_prompt(file_content: str, errors: list[dict]) -> str:
    error_text = "\n".join(
        f"  Line {e['line']}, Col {e['character']} [ERROR]: {e['message']}"
        for e in errors
    )
    return f"""Fix ONLY the errors in this Lean 4 file. Do not change anything else.

## Errors to fix
{error_text}

## Current file content
```lean
{file_content}
```

Respond with ONLY the corrected Lean 4 file content. No explanation, no markdown fences."""


def build_sorry_prompt(file_content: str) -> str:
    return f"""This Lean 4 file has no errors. Replace every 'sorry' with a real proof or implementation.

## Current file content
```lean
{file_content}
```

Respond with ONLY the completed Lean 4 file content. No explanation, no markdown fences."""


def strip_fences(text: str) -> str:
    """Remove markdown fences AND any preamble/postamble text outside the code block."""
    # If there's a ```lean block, extract only what's inside it
    if "```lean" in text:
        start = text.find("```lean") + len("```lean")
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()

    # If there's a generic ``` block, extract only what's inside it
    if "```" in text:
        start = text.find("```") + 3
        # skip the language tag line if present (e.g. "lean\n")
        newline = text.find("\n", start)
        if newline != -1:
            start = newline + 1
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()

    # No fences — but still strip any lines before the first 'import' or '--'
    # which are the typical first tokens of a Lean file
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("--") or stripped.startswith("/-") or stripped.startswith("theorem") or stripped.startswith("def ") or stripped.startswith("lemma ") or stripped.startswith("section") or stripped.startswith("namespace") or stripped.startswith("open "):
            return "\n".join(lines[i:]).strip()

    return text.strip()


def build_reflection_prompt_with_errors(file_content: str, errors: list[dict]) -> str:
    error_text = "\n".join(
        f"  Line {e['line']}, Col {e['character']} [ERROR]: {e['message']}"
        for e in errors
    )
    return f"""You are a Lean 4 expert and mathematician. Reflect on the following Lean 4 file and its errors.

## Current file content
```lean
{file_content}
```

## Errors
{error_text}

Please do the following:
1. Write out the mathematical proof of each theorem in plain English, step by step.
2. For each error, reflect on the likely cause. Classify it as one of:
   - TYPE ERROR: a type mismatch or wrong type used
   - SYNTAX ERROR: Lean 4 grammar or tactic syntax is wrong
   - MISSING THEOREM: the lemma or theorem you used does not exist in current Mathlib4
   - LOGIC ERROR: the proof strategy is flawed or the theorem may not be provable this way
3. Suggest a concrete fix for each error based on your reflection.

Be specific and mathematical. This reflection will be used to guide the next fix attempt."""


def build_reflection_prompt_no_errors(file_content: str) -> str:
    return f"""You are a Lean 4 expert and mathematician. Reflect on the following Lean 4 file which has no errors but still contains 'sorry' placeholders.

## Current file content
```lean
{file_content}
```

Please do the following:
1. For each theorem or definition with 'sorry', write out the full mathematical proof in plain English, step by step.
2. Suggest which Lean 4 / Mathlib4 tactics or lemmas would best implement each proof step.
3. Flag any theorems that may be difficult or impossible to prove with current Mathlib4.

Be specific and mathematical. This reflection will be used to guide the next proof attempt."""


def run_reflection(file_content: str, errors: list[dict], conversation_history: list) -> list:
    """Run one reflection pass and print the result."""
    print("\n" + "🔍" * 25)
    print("REFLECTION PASS")
    print("🔍" * 25)

    if errors:
        print("Reflecting on errors...")
        prompt = build_reflection_prompt_with_errors(file_content, errors)
    else:
        print("No errors — reflecting on sorry placeholders...")
        prompt = build_reflection_prompt_no_errors(file_content)

    conversation_history.append({"role": "user", "content": prompt})

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system="You are a Lean 4 expert and mathematician. Provide deep mathematical reflection to guide proof writing.",
        messages=conversation_history,
    )

    reflection = response.content[0].text.strip()
    conversation_history.append({"role": "assistant", "content": reflection})

    print("\n📝 Reflection:\n")
    print(reflection)
    print("\n" + "🔍" * 25 + "\n")

    return conversation_history


def call_api_with_retry(messages: list, system: str, max_tokens: int, max_retries: int = 3) -> any:
    """Call the API with automatic retry on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < max_retries - 1:
                wait = 60 * (attempt + 1)  # wait 60s, then 120s, then 180s
                print(f"⏳ Rate limit hit. Waiting {wait}s before retry {attempt + 2}/{max_retries}...")
                time.sleep(wait)
            else:
                raise


def trim_history(conversation_history: list, keep_last: int = 6) -> list:
    """Keep only the most recent N messages to avoid token overflow."""
    if len(conversation_history) > keep_last:
        print(f"✂️  Trimming conversation history to last {keep_last} messages.")
        return conversation_history[-keep_last:]
    return conversation_history


def run_agent():
    client = lc.LeanLSPClient(PROJECT_PATH)
    sfc = client.create_file_client(FILE_PATH)

    conversation_history = []
    total_input_tokens = 0
    total_output_tokens = 0
    REFLECTION_EVERY = 3

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'='*50}")
        print(f"Iteration {iteration}")

        errors = get_errors_only(sfc)
        file_content = get_file_content(sfc)

        # ── Stage 3: no errors, no sorry → done ──────────────────────
        if not errors and not has_sorry(file_content):
            print("✅ No errors and no sorry. File is complete!")
            write_to_disk(file_content)
            print("💾 Written to disk.")
            break

        # ── Trim history to avoid token overflow ──────────────────────
        conversation_history = trim_history(conversation_history, keep_last=6)

        # ── Reflection every N iterations ─────────────────────────────
        if iteration % REFLECTION_EVERY == 0:
            if errors:
                prompt = build_reflection_prompt_with_errors(file_content, errors)
            else:
                prompt = build_reflection_prompt_no_errors(file_content)

            print("\n" + "🔍" * 25)
            print("REFLECTION PASS")
            print("🔍" * 25)

            conversation_history.append({"role": "user", "content": prompt})
            response = call_api_with_retry(
                messages=conversation_history,
                system="You are a Lean 4 expert and mathematician. Provide deep mathematical reflection to guide proof writing.",
                max_tokens=2048,
            )
            reflection = response.content[0].text.strip()
            conversation_history.append({"role": "assistant", "content": reflection})
            print("\n📝 Reflection:\n")
            print(reflection)
            print("\n" + "🔍" * 25 + "\n")
            continue

        # ── Stage 1: errors exist → fix them first ───────────────────
        if errors:
            print(f"❌ Found {len(errors)} error(s) — fixing errors first:")
            for e in errors:
                print(f"   Line {e['line']}: {e['message'][:80]}")
            user_message = build_fix_prompt(file_content, errors)
            stage = "fix_errors"

        # ── Stage 2: no errors, but sorry remains → complete proofs ──
        else:
            print("⚠️  No errors. Completing 'sorry' placeholders...")
            user_message = build_sorry_prompt(file_content)
            stage = "complete_sorry"

        conversation_history.append({"role": "user", "content": user_message})
        response = call_api_with_retry(
            messages=conversation_history,
            system="You are a Lean 4 proof assistant. Output only valid Lean 4 code. Never output markdown fences or explanations.",
            max_tokens=8192,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        raw_response = response.content[0].text.strip()
        
        # Debug: show first 300 chars of raw response so we can see what LLM returned
        print(f"\n🔎 Raw LLM output (first 300 chars):\n{raw_response[:300]}\n")
        
        new_content = strip_fences(raw_response)
        
        # Safety check: if result looks wrong, abort rather than wipe the file
        lines = new_content.splitlines()
        first_real_line = next((l.strip() for l in lines if l.strip()), "")
        if not any(first_real_line.startswith(token) for token in [
            "import", "--", "/-", "theorem", "def ", "lemma", 
            "section", "namespace", "open ", "variable", "set_option", "#"
        ]):
            print(f"⚠️  Safety check failed — LLM output doesn't look like valid Lean.")
            print(f"   First line was: {first_real_line!r}")
            print(f"   Skipping this iteration to protect the file.")
            conversation_history.append({"role": "assistant", "content": raw_response})
            continue

        conversation_history.append({"role": "assistant", "content": new_content})

        if stage == "fix_errors":
            print("🔧 Applying error fix...")
        else:
            print("📝 Applying proof completion...")

        apply_full_replacement(sfc, new_content)
        write_to_disk(new_content)
        print("💾 Written to disk.")

    else:
        print(f"\n⚠️  Reached max iterations ({MAX_ITERATIONS}) without finishing.")

    input_cost  = total_input_tokens  / 1_000_000 * 3
    output_cost = total_output_tokens / 1_000_000 * 15
    print(f"\n📊 Token usage this session:")
    print(f"   Input:  {total_input_tokens} tokens")
    print(f"   Output: {total_output_tokens} tokens")
    print(f"   Estimated cost: ${input_cost + output_cost:.4f}")

    client.close()

if __name__ == "__main__":
    run_agent()