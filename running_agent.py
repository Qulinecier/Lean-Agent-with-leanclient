"""Running/repair phase for the Lean OpenAI agent."""
from __future__ import annotations

import os
import leanclient as lc

try:
    from .basics import (
        FILE_PATH,
        HISTORY_FILE,
        LEARNING_FILE,
        MAX_ITERATIONS,
        OPENAI_MODEL,
        OPENAI_REASONING_EFFORT,
        PROJECT_PATH,
        _load_json,
        _save_json,
        apply_full_replacement,
        build_fix_prompt,
        build_reflection_prompt_no_errors,
        build_reflection_prompt_with_errors,
        build_sorry_prompt,
        call_api_with_retry,
        find_enclosing_block,
        find_first_sorry,
        get_errors_only,
        get_file_content,
        has_sorry,
        splice_block,
        strip_fences,
        strip_lean_comments,
        trim_history,
        write_to_disk,
    )
except ImportError:  # Allows running these files directly from one folder.
    from basics import (
        FILE_PATH,
        HISTORY_FILE,
        LEARNING_FILE,
        MAX_ITERATIONS,
        OPENAI_MODEL,
        OPENAI_REASONING_EFFORT,
        PROJECT_PATH,
        _load_json,
        _save_json,
        apply_full_replacement,
        build_fix_prompt,
        build_reflection_prompt_no_errors,
        build_reflection_prompt_with_errors,
        build_sorry_prompt,
        call_api_with_retry,
        find_enclosing_block,
        find_first_sorry,
        get_errors_only,
        get_file_content,
        has_sorry,
        splice_block,
        strip_fences,
        strip_lean_comments,
        trim_history,
        write_to_disk,
    )


# ── Reflection pass ──────────────────────────────────────────────────────────

def run_reflection(file_content: str, errors: list[dict], conversation_history: list) -> list:
    print("\n" + "🔍" * 25)
    print("REFLECTION PASS")
    print("🔍" * 25)
    if errors:
        prompt = build_reflection_prompt_with_errors(file_content, errors)
    else:
        prompt = build_reflection_prompt_no_errors(file_content)
    conversation_history.append({"role": "user", "content": prompt})
    response = call_api_with_retry(
        messages=conversation_history,
        max_tokens=2048,
        system="You are a Lean 4 expert and mathematician. Provide deep mathematical reflection to guide proof writing.",
    )
    reflection = response.content[0].text.strip()
    conversation_history.append({"role": "assistant", "content": reflection})
    print("\n📝 Reflection:\n")
    print(reflection)
    print("\n" + "🔍" * 25 + "\n")
    return conversation_history
 
 
# ── Main agent ────────────────────────────────────────────────────────────────
 
def run_agent():
    print(f"🤖 OpenAI Lean agent model: {OPENAI_MODEL} (reasoning: {OPENAI_REASONING_EFFORT})")
    client = lc.LeanLSPClient(PROJECT_PATH)
    sfc = client.create_file_client(FILE_PATH)
 
    learning: dict = _load_json(LEARNING_FILE, {})
    if learning:
        print(f"📚 Loaded learning for {len(learning)} file(s) from '{LEARNING_FILE}'.")
    else:
        print(f"⚠️  No learning file found at '{LEARNING_FILE}'. Run reading_agent() first for best results.")
 
    saved_history: list = _load_json(HISTORY_FILE, [])
    if saved_history:
        print(f"🔄 Resuming from saved history ({len(saved_history)} messages) in '{HISTORY_FILE}'.")
        conversation_history: list = saved_history
    else:
        conversation_history = []
        if learning:
            summaries = "\n\n".join(
                f"### {fname}\n{entry['learning']}"
                for fname, entry in learning.items()
            )
            seed_user = (
                "Before we begin fixing the Lean file, here is the structured Lean knowledge "
                "extracted from the project files during the reading phase.\n\n"
                "This covers: (1) Mathlib lemmas already in use, "
                "(2) the author's own definitions and theorems, "
                "(3) the proof style and tactic patterns that work in this codebase.\n\n"
                + summaries
            )
            seed_asst = (
                "Understood. I have studied the Lean knowledge base: the Mathlib lemmas in use, "
                "the author's own definitions, and the proof style of this codebase. "
                "I will apply this knowledge when fixing errors and filling sorry placeholders."
            )
            conversation_history = [
                {"role": "user",    "content": seed_user},
                {"role": "assistant", "content": seed_asst},
            ]
            print("🌱 Seeded conversation history with learning from reading_agent().")
 
    total_input_tokens = 0
    total_output_tokens = 0
    REFLECTION_EVERY = 10
 
    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'='*50}")
        print(f"Iteration {iteration}")
 
        errors = get_errors_only(sfc)
        file_content = get_file_content(sfc)
 
        if not errors and not has_sorry(file_content):
            print("✅ No errors and no sorry. File is complete!")
            write_to_disk(file_content)
            print("💾 Written to disk.")
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
                print(f"🗑️  Cleared '{HISTORY_FILE}' (task complete).")
            break
 
        conversation_history = trim_history(conversation_history, keep_last=6)
 
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
            _save_json(HISTORY_FILE, conversation_history)
            continue
 
        # ── Determine edit target and find its enclosing block ────────
        if errors:
            print(f"❌ Found {len(errors)} error(s) — fixing errors first:")
            for e in errors:
                goal_hint = f" | goal: {str(e['goal'])[:60]}" if e.get("goal") else ""
                print(f"   Line {e['line']}: {e['message'][:80]}{goal_hint}")
            edit_line = min(
                (e["line"] for e in errors if e.get("line") is not None),
                default=0,
            )
            block_start, block_end, block_text = find_enclosing_block(file_content, edit_line)
            print(f"   Editing block lines {block_start}–{block_end} ({block_end - block_start + 1} lines).")
            user_message = build_fix_prompt(block_text, errors, block_start)
            stage = "fix_errors"
 
        else:
            sorry_info = find_first_sorry(sfc)
            if sorry_info:
                goal_hint = str(sorry_info['goal'])[:60] if sorry_info.get("goal") else "no goal available"
                print(f"⚠️  No errors. Attempting first sorry at line {sorry_info['line']}: {sorry_info['source_line'][:60]}")
                print(f"   Goal: {goal_hint}")
                edit_line = sorry_info["line"]
            else:
                print("⚠️  No errors. Attempting first sorry (position unknown)...")
                sorry_info = None
                edit_line = 0
            block_start, block_end, block_text = find_enclosing_block(file_content, edit_line)
            print(f"   Editing block lines {block_start}–{block_end} ({block_end - block_start + 1} lines).")
            user_message = build_sorry_prompt(block_text, sorry_info, block_start)
            stage = "complete_sorry"
 
        conversation_history.append({"role": "user", "content": user_message})
        response = call_api_with_retry(
            messages=conversation_history,
            system=(
                "You are a Lean 4 proof assistant. "
                "Output ONLY the corrected Lean 4 block. "
                "No markdown fences, no explanations, no comments."
            ),
            max_tokens=8192,
        )
 
        total_input_tokens  += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
 
        raw_response = response.content[0].text.strip()
        print(f"\n🔎 Raw LLM output (first 300 chars):\n{raw_response[:300]}\n")
 
        new_block = strip_fences(raw_response)
        new_block = strip_lean_comments(new_block)
 
        # Safety: check the block starts with something plausible
        first_real = next((l.strip() for l in new_block.splitlines() if l.strip()), "")
        if not any(first_real.startswith(t) for t in [
            "theorem", "lemma", "def ", "noncomputable", "abbrev",
            "structure", "class", "instance", "example",
            "have ", "obtain", "calc", "by", "fun ", "let ",
        ]):
            print(f"⚠️  Safety check failed — output doesn't look like a valid Lean block.")
            print(f"   First line was: {first_real!r}")
            print(f"   Skipping this iteration to protect the file.")
            conversation_history.append({"role": "assistant", "content": raw_response})
            _save_json(HISTORY_FILE, conversation_history)
            continue
 
        # Splice new block back into the full file; tail is never touched
        new_content = splice_block(file_content, block_start, block_end, new_block)
 
        conversation_history.append({"role": "assistant", "content": new_block})
 
        if stage == "fix_errors":
            print("🔧 Applying error fix...")
        else:
            print("📝 Applying proof completion...")
 
        apply_full_replacement(sfc, new_content)
        write_to_disk(new_content)
        print("💾 Written to disk.")
 
        _save_json(HISTORY_FILE, conversation_history)
        print(f"💾 History saved to '{HISTORY_FILE}'.")
 
    else:
        print(f"\n⚠️  Reached max iterations ({MAX_ITERATIONS}) without finishing.")
        _save_json(HISTORY_FILE, conversation_history)
        print(f"💾 History saved to '{HISTORY_FILE}' for next run.")
 
    input_cost  = total_input_tokens  / 1_000_000 * 0.75
    output_cost = total_output_tokens / 1_000_000 * 4.50
    print(f"\n📊 Token usage this session:")
    print(f"   Input:  {total_input_tokens} tokens")
    print(f"   Output: {total_output_tokens} tokens")
    print(f"   Estimated cost: ${input_cost + output_cost:.4f}")
 
    client.close()
