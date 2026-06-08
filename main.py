from langgraph.graph import StateGraph, END
from state import ProofState
from nodes.environment import extract_env_state
from nodes.context_builder import build_context
from nodes.generator import generate_tactic
from nodes.updater import apply_code_update

def should_continue(state: dict) -> str:
    if state.get("is_complete"):
        return "end"
    if state.get("iteration_count", 0) >= 10: # Updated max iterations to 10
        return "end"
    return "build_context" 

workflow = StateGraph(ProofState)

workflow.add_node("extract_env", extract_env_state)
workflow.add_node("build_context", build_context) 
workflow.add_node("generate_tactic", generate_tactic)
workflow.add_node("apply_update", apply_code_update)

workflow.set_entry_point("extract_env")

workflow.add_conditional_edges(
    "extract_env",
    should_continue,
    {
        "build_context": "build_context",
        "end": END
    }
)

workflow.add_edge("build_context", "generate_tactic")
workflow.add_edge("generate_tactic", "apply_update")
workflow.add_edge("apply_update", "extract_env")

app = workflow.compile()

if __name__ == "__main__":
    initial_state = {
        "project_path": r"E:\SimpleTest",
        "file_path": r"SimpleTest\Test1.lean",
        "iteration_count": 0,
        "is_complete": False
    }
    
    for s in app.stream(initial_state, {"recursion_limit": 50}):
        print(s)