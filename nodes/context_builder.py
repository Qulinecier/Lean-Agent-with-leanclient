import os
import json
from anthropic import Anthropic
from tools.local_retriever import search_local
from tools.mathlib import search_mathlib

QUERY_MODEL = "claude-haiku-4-5" 
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def build_context(state: dict) -> dict:
    base_prompt_text = "\n".join(state.get("base_prompt", []))
    informal_step = state.get("informal_proof_step", "")
    
    if not base_prompt_text and not informal_step:
        return {"retrieved_lemmas": ""}

    # 1. Build Query Prompt natively using the new base_prompt
    prompt_content = f"Current mathematical step:\n{informal_step}\n\nLean Context:\n{base_prompt_text}\n\nBased on the above, extract 2 to 4 highly relevant keywords or type signatures that would be useful to search in Mathlib or the local project."

    query_schema = {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2 to 4 highly relevant keywords or type signatures."
            }
        },
        "required": ["keywords"],
        "additionalProperties": False,
    }

    try:
        response = anthropic_client.messages.create(
            model=QUERY_MODEL,
            max_tokens=150,
            temperature=0.0,
            system="You are an expert Lean 4 user. Your task is to generate search queries to find helpful lemmas for the current proof step. Output ONLY structured JSON matching the provided schema.",
            messages=[{"role": "user", "content": prompt_content}],
            tools=[{
                "name": "generate_query",
                "description": "Generate search query keywords",
                "input_schema": query_schema
            }],
            tool_choice={"type": "tool", "name": "generate_query"}
        )
        
        # Anthropic tool use parsing
        tool_call = next(block for block in response.content if block.type == "tool_use")
        keywords = tool_call.input.get("keywords", [])
        query_string = " ".join(keywords).strip()
        
    except Exception as e:
        print(f"⚠️ Query generation failed: {e}")
        query_string = ""

    print(f"🔍 Generated Search Query: [{query_string}]")
    combined_results = ""

    if query_string:
        try:
            local_results = search_local(query_string, k=3)
            if local_results:
                combined_results += "--- Local Helper Lemmas ---\n" + local_results + "\n\n"
        except Exception as e:
            print(f"⚠️ Local retrieval failed: {e}")

        try:
            mathlib_results = search_mathlib(query_string, num_results=5)
            if mathlib_results:
                combined_results += "--- Mathlib Lemmas (via LeanSearch) ---\n" + mathlib_results + "\n\n"
        except Exception as e:
            pass

    return {"retrieved_lemmas": combined_results.strip()}