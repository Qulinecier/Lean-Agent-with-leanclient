import os
import time
import re
import json
from anthropic import Anthropic

anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
HISTORY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "History", "proof_history.json"))

def load_history(path: str, max_turns: int = 10) -> list:
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read().strip()
        if not content: return []
        try:
            history = json.loads(content)
            return history[-(max_turns * 2):]
        except json.JSONDecodeError:
            return []
    return []

def save_history(history: list, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)

def strip_fences(text: str) -> str:
    if "```lean" in text:
        start = text.find("```lean") + len("```lean")
        end = text.find("```", start)
        if end != -1: return text[start:end].strip()
    if "```" in text:
        start = text.find("```") + 3
        newline = text.find("\n", start)
        if newline != -1: start = newline + 1
        end = text.find("```", start)
        if end != -1: return text[start:end].strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if any(s.startswith(t) for t in ["import", "theorem", "lemma", "def ", "noncomputable", "section", "namespace", "open ", "variable", "set_option", "#", "have ", "obtain", "calc", "by"]):
            return "\n".join(lines[i:]).strip()
    return text.strip()

def strip_lean_comments(text: str) -> str:
    text = re.sub(r"/-.*?-/", "", text, flags=re.DOTALL)
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        idx = line.find("--")
        if idx != -1: line = line[:idx].rstrip()
        if line or not cleaned or cleaned[-1]: cleaned.append(line)
    return "\n".join(cleaned)

def generate_tactic(state: dict) -> dict:
    base_prompt = "\n".join(state["base_prompt"])
    if state.get("retrieved_lemmas"):
        final_prompt = base_prompt + f"\n\nAvailable Lemmas:\n{state['retrieved_lemmas']}"
    else:
        final_prompt = base_prompt

    history = load_history(HISTORY_FILE)

    for attempt in range(3):
        try:
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8192,
                system="You are a Lean 4 proof assistant. Output ONLY the corrected Lean 4 block. No markdown fences, no explanations, no comments.",
                messages=[*history, {"role": "user", "content": final_prompt}]
            )
            raw_response = response.content[0].text.strip()
            new_block = strip_lean_comments(strip_fences(raw_response))
            
            history.append({"role": "user", "content": final_prompt})
            history.append({"role": "assistant", "content": new_block})
            save_history(history, HISTORY_FILE)
            
            return {"generated_code": new_block}
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < 2:
                time.sleep(60 * (attempt + 1))
            else:
                raise