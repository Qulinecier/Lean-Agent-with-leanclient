from typing import TypedDict, List, Optional

class ProofState(TypedDict):
    project_path: str
    file_path: str
    lines: List[str]
    target_block_start: Optional[int]
    target_block_end: Optional[int]
    base_prompt: List[str]
    generated_code: Optional[str]
    iteration_count: int
    is_complete: bool
    informal_proof_step: str
    retrieved_lemmas: str