"""Reading/learning phase for Lean project files."""
from __future__ import annotations

import os

try:
    from .basics import (
        LEAN_DIR,
        LEARNING_FILE,
        _load_json,
        _save_json,
        call_api_with_retry,
    )
except ImportError:  # Allows running these files directly from one folder.
    from basics import (
        LEAN_DIR,
        LEARNING_FILE,
        _load_json,
        _save_json,
        call_api_with_retry,
    )


# ── Reading / learning agent ──────────────────────────────────────────────────
 
def read_lean_files(directory: str) -> dict[str, str]:
    files = {}
    for fname in os.listdir(directory):
        if fname.endswith(".lean"):
            full_path = os.path.join(directory, fname)
            with open(full_path, "r", encoding="utf-8") as f:
                files[fname] = f.read()
    return files
 
 
def explain_lean_file(filename: str, content: str, conversation_history: list) -> list:
    user_message = (
        f"Here is a Lean 4 file called '{filename}'.\n"
        "Please explain the mathematical or abstract definitions in it in plain, human-readable English.\n"
        "Do not produce any code. Just describe what each definition, theorem, or structure means mathematically.\n"
        "Pay more attention to where sorry is, and first use math or abstract proof to prove it and describe it wordly.\n\n"
        f"```lean\n{content}\n```"
    )
    conversation_history.append({"role": "user", "content": user_message})
    response = call_api_with_retry(
        messages=conversation_history,
        max_tokens=4096,
        system="You are a mathematics expert who explains Lean 4 code in clear, plain English for someone learning formal verification.",
    )
    explanation = response.content[0].text.strip()
    conversation_history.append({"role": "assistant", "content": explanation})
    return conversation_history
 
 
def learn_lean_file(filename: str, content: str, conversation_history: list) -> list:
    user_message = (
        f"You are analysing a Lean 4 file called '{filename}' to extract reusable knowledge "
        "for a proof-repair agent.\n\n"
        "Please extract and report the following three sections exactly:\n\n"
        "---\n"
        "## 1. Mathlib Lemmas & Theorems Used\n"
        "List every Mathlib lemma, theorem, or definition referenced in this file "
        "(via `apply`, `exact`, `rw`, `simp`, `have ... :=`, `use`, `refine`, etc.).\n"
        "For each one write:\n"
        "- Name (fully qualified if visible)\n"
        "- How it was used (e.g. `apply`, `rw`, `exact`, `simp only [...]`)\n"
        "- A one-line note on what it does\n\n"
        "## 2. Author's Own Definitions & Theorems\n"
        "List every `def`, `lemma`, `theorem`, `noncomputable def`, `abbrev`, or `structure` "
        "defined in this file (i.e. NOT from Mathlib).\n"
        "For each one write:\n"
        "- Name and signature (inputs \u2192 output type)\n"
        "- Whether it is fully proved, or still has `sorry`/`admit`\n\n"
        "## 3. Proof Style & Tactic Patterns\n"
        "Describe the recurring tactic patterns and proof-writing style used in this file.\n"
        "Focus on:\n"
        "- Which tactic combinators appear most (`by`, `calc`, `obtain`, `rcases`, `constructor`, `intro`, `induction`, etc.)\n"
        "- Any recurring idioms (e.g. `set T := ... with hT`, `field_simp` then `ring`, epsilon-delta patterns)\n"
        "- Anything done to make a proof work (unusual coercions, `norm_cast`, `push_cast`, custom simp sets, etc.)\n"
        "- Whether `Classical.epsilon`, `ENNReal`, `EReal`, or other tricky types appear and how they are handled\n"
        "---\n\n"
        f"Here is the file:\n\n```lean\n{content}\n```"
    )
    conversation_history.append({"role": "user", "content": user_message})
    response = call_api_with_retry(
        messages=conversation_history,
        max_tokens=4096,
        system=(
            "You are an expert Lean 4 / Mathlib engineer. "
            "Your job is to extract precise, structured knowledge from Lean 4 source files "
            "so that a proof-repair agent can reuse that knowledge when fixing errors and "
            "filling sorry placeholders. Be specific and terse. Always use Lean 4 names, not Lean 3."
        ),
    )
    learning = response.content[0].text.strip()
    conversation_history.append({"role": "assistant", "content": learning})
    return conversation_history
 
 
def reading_agent():
    lean_files = read_lean_files(LEAN_DIR)
    if not lean_files:
        print("No .lean files found in", LEAN_DIR)
        return
    print(f"Found {len(lean_files)} Lean file(s): {', '.join(lean_files.keys())}\n")
    stored: dict = _load_json(LEARNING_FILE, {})
    for filename, content in lean_files.items():
        print(f"\n{'='*50}")
        print(f"📄 File: {filename}")
        print("="*50)
        conversation_history: list = []
        conversation_history = learn_lean_file(filename, content, conversation_history)
        learning_text = conversation_history[-1]["content"]
        print("\n🧠 Lean knowledge extracted:\n")
        print(learning_text)
        print("\n" + "-"*50)
        stored[filename] = {
            "learning": learning_text,
            "conversation_history": conversation_history,
        }
    _save_json(LEARNING_FILE, stored)
    print(f"\n✅ All files learned! Knowledge saved to '{LEARNING_FILE}'.")
