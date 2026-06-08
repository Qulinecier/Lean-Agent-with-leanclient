# import leanclient as lc
# import re

# def get_error_only(diags: lc.DiagnosticsResult) -> list[dict]:
#     return [
#         {
#             "message": d.get("message", ""),
#             "line": d.get("range", {}).get("start", {}).get("line"),
#             "character": d.get("range", {}).get("end", {}).get("character"),
#         }
#         for d in diags if d.get("severity") == 1
#     ] # [cite: 103, 104]

# def flatten_leaf_symbols(symbols: list[dict]) -> list[dict]:
#     leaves = []
#     for sym in symbols:
#         if 'children' in sym and sym['children']:
#             leaves.extend(flatten_leaf_symbols(sym['children']))
#         else:
#             leaves.append(sym)
#     return leaves # [cite: 104]

# def find_enclosing_symbol(leaves: list[dict], line: int) -> tuple[dict, int, int] | None:
#     for i, sym in enumerate(leaves):
#         start = sym['range']['start']['line']
#         if i + 1 < len(leaves):
#             end = leaves[i + 1]['range']['start']['line'] - 2
#         else:
#             end = sym['range']['end']['line']
#         if start <= line <= end:
#             return sym, start, end
#     return None # [cite: 105, 106]

# def find_sorry_positions(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
#     pattern = re.compile(r'\b(sorry|admit)\b')
#     positions = []
#     for i in range(start, end + 1):
#         for m in pattern.finditer(lines[i]):
#             positions.append((i, m.start()))
#     return positions # [cite: 106, 107]

# def extract_env_state(state: dict) -> dict:
#     client = lc.LeanLSPClient(state["project_path"])
#     sfc = client.create_file_client(state["file_path"])
    
#     diags = sfc.get_diagnostics()
#     symbols = sfc.get_document_symbols()
#     leaves = flatten_leaf_symbols(symbols)
#     leaves.sort(key=lambda s: s['range']['start']['line'])
    
#     content = sfc.get_file_content()
#     lines = content.splitlines() # [cite: 129, 130]
    
#     current_goals = []
#     current_errors = []
#     block_start, block_end = None, None
#     is_complete = False

#     if diags.success:
#         sorry_diags = [d for d in diags if "declaration uses 'sorry'" in d.get("message", "")] # [cite: 107, 108]
#         if sorry_diags:
#             sorry_line = sorry_diags[0].get("range", {}).get("start", {}).get("line") # [cite: 108]
#             result = find_enclosing_symbol(leaves, sorry_line) # [cite: 108]
#             if result:
#                 _, block_start, block_end = result # [cite: 109]
#                 sorry_positions = find_sorry_positions(lines, block_start, block_end) # [cite: 110]
#                 for pos in sorry_positions:
#                     goal = sfc.get_goal(pos[0], pos[1]) # [cite: 111]
#                     if goal: current_goals.append(goal["rendered"])
#         else:
#             is_complete = True # [cite: 112]
#     else:
#         errors = get_error_only(diags) # [cite: 113]
#         if errors:
#             first_error = errors[0]
#             result = find_enclosing_symbol(leaves, first_error["line"]) # [cite: 113]
#             if result:
#                 _, block_start, block_end = result # [cite: 113]
                
#             for error in errors:
#                 if block_end and error["line"] <= block_end:
#                     current_errors.append(error["message"]) # [cite: 116]
#                     goal = sfc.get_goal(error["line"], 0) # [cite: 116]
#                     if goal: current_goals.append(goal["rendered"]) # [cite: 117]
#                 elif not block_end:
#                     break

#     client.close()
#     return {
#         "lines": lines,
#         "target_block_start": block_start,
#         "target_block_end": block_end,
#         "current_goals": current_goals,
#         "current_errors": current_errors,
#         "is_complete": is_complete
#     }

import leanclient as lc
import re

def get_error_only(diags: lc.DiagnosticsResult) -> list[dict]:
    return [
        {
            "message": d.get("message", ""),
            "line": d.get("range", {}).get("start", {}).get("line"),
            "character": d.get("range", {}).get("end", {}).get("character"),
        }
        for d in diags if d.get("severity") == 1
    ]

def find_enclosing_symbol(leaves: list[dict], line: int) -> tuple[dict, int, int] | None:
    for i, sym in enumerate(leaves):
        start = sym['range']['start']['line']
        if i + 1 < len(leaves):
            end = leaves[i + 1]['range']['start']['line'] - 2
        else:
            end = sym['range']['end']['line']
        if start <= line <= end:
            return sym, start, end
    return None

def find_sorry_positions(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    pattern = re.compile(r'\b(sorry|admit)\b')
    positions = []
    for i in range(start, end + 1):
        for m in pattern.finditer(lines[i]):
            positions.append((i, m.start()))
    return positions

DECLARATION_PATTERN = re.compile(r"^(theorem|lemma|example|def|abbrev|class|structure|instance|noncomputable|section|end|axiom|open|/--)\s+(\S+)?")

def get_leaves_from_source(lines: list[str]) -> list[dict]:
    matches = []
    for line_no, line in enumerate(lines):
        m = DECLARATION_PATTERN.match(line)
        if m:
            kind = m.group(1)
            raw_name = m.group(2)
            name = None if kind == "example" else (raw_name or None)
            matches.append({
                "name": name,
                "kind": kind,
                "_start_line": line_no,
                "_start_char": 0,
            })
    
    leaves = []
    for i, m in enumerate(matches):
        end_line = matches[i + 1]["_start_line"] - 1 if i + 1 < len(matches) else len(lines)
        leaves.append({
            "name": m["name"],
            "kind": m["kind"],
            "range": {
                "start": {"line": m["_start_line"], "character": 0},
                "end":   {"line": end_line - 1, "character": len(lines[end_line - 1])},
            }
        })
    _KEEP = {"theorem", "lemma", "example"}
    return [leaf for leaf in leaves if leaf["kind"] in _KEEP]

def prompt_generator(sfc, diags, leaves, lines) -> tuple[list, int, int]:
    prompt = []
    if diags.success:
        sorry_diags = [d for d in diags if "declaration uses `sorry`" in d.get("message", "")]
        if sorry_diags:
            first_sorry = sorry_diags[0]
            sorry_line = first_sorry.get("range", {}).get("start", {}).get("line")
            result = find_enclosing_symbol(leaves, sorry_line)

            if result is not None:
                _, sorry_start, sorry_end = result
                theorem_code = "\n".join(lines[sorry_start:sorry_end + 1])
                prompt.append("Prove the sorry here. I mean replace the sorry/admit with some proofs. Do not change my theorem statement.")
                prompt.append("-------------------------")
                prompt.append(theorem_code)

                sorry_index = find_sorry_positions(lines, sorry_start, sorry_end)
                prompt.append("-------------------------")
                prompt.append("Lean info view:")
                for i, sorry in enumerate(sorry_index):
                    goal = sfc.get_goal(sorry[0], sorry[1])
                    if goal:
                        prompt.append(f"Sorry {i+1}:")
                        prompt.append(goal["rendered"])
                return prompt, sorry_start, sorry_end
            return None, None, None
        return None, None, None
    else:
        errors = get_error_only(diags)
        if errors:
            first_error = errors[0]
            result = find_enclosing_symbol(leaves, first_error["line"])
            first_sym, first_start, first_end = result if result else (None, None, None)
            
            error_messages = [first_error["message"]]
            theorem_code = "\n".join(lines[first_start:first_end + 1]) if first_sym else None

            error_goal = []
            if sfc.get_goal(first_error["line"], first_error["character"]):
                error_goal.append(sfc.get_goal(first_error["line"], first_error["character"])["rendered"])
            elif sfc.get_goal(first_error["line"], 0):
                error_goal.append(sfc.get_goal(first_error["line"], 0)["rendered"])

            for error in errors[1:]:
                if first_end and error["line"] <= first_end:
                    error_messages.append(error["message"])
                    if sfc.get_goal(error["line"], 0):
                        error_goal.append(sfc.get_goal(error["line"], 0)["rendered"])
                else:
                    break

            prompt.append("Correct the errors here. There may be some sorries, but leave them as they are now like. Do not change my theorem statement.")
            if theorem_code:
                prompt.append("Theorem you need to edit:")
                prompt.append(theorem_code)
            prompt.append("-------------------------")
            for i, msg in enumerate(error_messages):
                prompt.append(f"Error message {i+1}:\n{msg}")
            for goal in error_goal:
                prompt.append(f"Lean info at error:\n{goal}")
            return prompt, first_start, first_end
        return None, None, None

def extract_env_state(state: dict) -> dict:
    client = lc.LeanLSPClient(state["project_path"])
    sfc = client.create_file_client(state["file_path"])
    
    diags = sfc.get_diagnostics()
    content = sfc.get_file_content()
    lines = content.splitlines()
    leaves = get_leaves_from_source(lines)
    
    prompt_msg, start, end = prompt_generator(sfc, diags, leaves, lines)
    client.close()
    
    if not prompt_msg:
        return {
            "lines": lines,
            "target_block_start": None,
            "target_block_end": None,
            "base_prompt": [],
            "is_complete": True
        }
        
    return {
        "lines": lines,
        "target_block_start": start,
        "target_block_end": end,
        "base_prompt": prompt_msg,
        "is_complete": False
    }