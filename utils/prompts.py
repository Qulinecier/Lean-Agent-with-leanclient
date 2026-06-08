# System Prompts
QUERY_GEN_SYSTEM = (
    "You are an expert Lean 4 user. Your task is to generate search queries "
    "to find helpful lemmas for the current proof step. "
    "Output ONLY structured JSON matching the provided schema. Do not include markdown or explanations."
)

TACTIC_GEN_SYSTEM = (
    "You are a Lean 4 proof assistant. Output ONLY the corrected Lean 4 block. "
    "No markdown fences, no explanations, no comments."
)

# User Prompt Builders
def build_query_generation_prompt(informal_step: str, goals: list[str], errors: list[str]) -> str:
    prompt = ""
    if informal_step:
        prompt += f"Current mathematical step:\n{informal_step}\n\n"
    if goals:
        prompt += f"Current Lean goals:\n{chr(10).join(goals)}\n\n"
    if errors:
        prompt += f"Current Lean errors:\n{chr(10).join(errors)}\n\n"
        
    prompt += (
        "Based on the above, extract 2 to 4 highly relevant keywords or type signatures "
        "that would be useful to search in Mathlib or the local project."
    )
    return prompt

def build_tactic_generation_prompt(state: dict, theorem_code: str) -> str:
    prompt = []
    
    if state["current_errors"]:
        prompt.append("Correct the errors here. Do not change my theorem statement.")
        prompt.append(f"Theorem:\n{theorem_code}")
        prompt.append("Errors:")
        for msg in state["current_errors"]:
            prompt.append(msg)
    else:
        prompt.append("Prove the sorry here. Do not change my theorem statement.")
        prompt.append(f"Theorem:\n{theorem_code}")

    if state["current_goals"]:
        prompt.append("Lean Context/Goals:")
        for goal in state["current_goals"]:
            prompt.append(goal)

    if state.get("informal_proof_step"):
        prompt.append(f"Informal Math Blueprint:\n{state['informal_proof_step']}")

    if state.get("retrieved_lemmas"):
        prompt.append(f"Available Lemmas:\n{state['retrieved_lemmas']}")

    return "\n".join(prompt)