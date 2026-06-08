# import os
# import leanclient as lc

# def splice_block(lines: list[str], block_start: int, block_end: int, new_block: str) -> str:
#     before = "\n".join(lines[:block_start])
#     after  = "\n".join(lines[block_end + 1:])
#     return before + "\n" + new_block + "\n" + after # [cite: 128]

# def apply_code_update(state: dict) -> dict:
#     new_content = splice_block(
#         state["lines"], 
#         state["target_block_start"], 
#         state["target_block_end"], 
#         state["generated_code"]
#     ) # [cite: 134]
    
#     client = lc.LeanLSPClient(state["project_path"])
#     sfc = client.create_file_client(state["file_path"])
    
#     old_lines = sfc.get_file_content().splitlines()
#     last_line = len(old_lines) - 1
#     last_char = len(old_lines[-1]) if old_lines else 0
    
#     change = lc.DocumentContentChange(
#         text=new_content,
#         start=[0, 0],
#         end=[last_line, last_char],
#     ) # 
#     sfc.update_file(changes=[change]) # [cite: 129]
    
#     full_path = os.path.join(state["project_path"], state["file_path"])
#     with open(full_path, "w", encoding="utf-8") as f:
#         f.write(new_content) # [cite: 129]
        
#     client.close()
    
#     return {
#         "iteration_count": state["iteration_count"] + 1,
#         "generated_code": None 
#     }

import os

def splice_block(lines: list[str], block_start: int, block_end: int, new_block: str) -> str:
    before = "\n".join(lines[:block_start])
    after  = "\n".join(lines[block_end + 1:])
    return before + "\n" + new_block + "\n" + after

def apply_code_update(state: dict) -> dict:
    # 1. Stitch the LLM's new code into the existing lines
    new_content = splice_block(
        state["lines"], 
        state["target_block_start"], 
        state["target_block_end"], 
        state["generated_code"]
    )

    # Save directly to disk (No LSP client needed here!)
    full_path = os.path.join(state["project_path"], state["file_path"])
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("💾 New Lean block written to disk.")

    # Update the LangGraph state for the next iteration
    return {
        "iteration_count": state.get("iteration_count", 0) + 1,
        "generated_code": None 
    }