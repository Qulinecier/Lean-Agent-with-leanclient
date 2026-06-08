import os
import re
import chromadb

# Configuration
# PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Test_Project"))
# TARGET_FILE = r"MLE\test.lean"
PROJECT_DIR = r"E:\SimpleTest\SimpleTest" # E:\Statistics_in_Lean
TARGET_FILE    = r"Test1.lean"   # relative to PROJECT_PATH, MLE\test.lean"
CHROMA_DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".chroma_db"))
COLLECTION_NAME = "lean_local_lemmas"

# Regex to identify the start of a Lean declaration
DECLARATION_PATTERN = re.compile(r"^(theorem|lemma|def|abbrev|class|structure|instance|noncomputable)\s+")

def extract_lean_blocks(filepath: str) -> list[dict]:
    """
    Parses a Lean file and extracts declarations along with their signatures.
    """
    blocks = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_block = []
    current_name = ""
    
    for line in lines:
        if DECLARATION_PATTERN.match(line.strip()):
            # Save the previous block if it exists
            if current_block:
                blocks.append({
                    "name": current_name,
                    "content": "".join(current_block).strip()
                })
            
            # Start a new block
            current_block = [line]
            # Naive extraction of the name (first token after declaration keyword)
            parts = line.strip().split()
            if len(parts) > 1:
                current_name = parts[1].replace(":", "") 
        elif current_block:
            # Continue accumulating lines for the current declaration
            current_block.append(line)
            # Stop accumulating if we hit a completely blank line (heuristic for end of signature)
            if line.strip() == "" and len(current_block) > 3:
                blocks.append({
                    "name": current_name,
                    "content": "".join(current_block).strip()
                })
                current_block = []

    # Catch the last block
    if current_block:
        blocks.append({"name": current_name, "content": "".join(current_block).strip()})

    return blocks

def build_index():
    print(f"Initializing ChromaDB at {CHROMA_DB_DIR}...")
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    
    # Reset collection if it exists to avoid duplicates during testing
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except chromadb.errors.NotFoundError:
        pass
        
    collection = client.create_collection(name=COLLECTION_NAME)

    documents = []
    metadatas = []
    ids = []
    
    target_full_path = os.path.join(PROJECT_DIR, TARGET_FILE)

    print("Scanning project files...")
    for root, _, files in os.walk(PROJECT_DIR):
        for file in files:
            if not file.endswith(".lean"):
                continue
                
            filepath = os.path.join(root, file)
            if os.path.abspath(filepath) == os.path.abspath(target_full_path):
                continue  # Skip the file being actively solved
                
            print(f"Extracting: {filepath}")
            blocks = extract_lean_blocks(filepath)
            
            for i, block in enumerate(blocks):
                if len(block["content"]) < 10:
                    continue # Skip empty or malformed blocks
                    
                documents.append(block["content"])
                metadatas.append({"file": file, "name": block["name"]})
                ids.append(f"{file}_{block['name']}_{i}")

    if documents:
        print(f"Upserting {len(documents)} chunks into ChromaDB...")
        # Batch upsert to handle Chroma limits
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            collection.upsert(
                documents=documents[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
                ids=ids[i:i+batch_size]
            )
        print("✅ Indexing complete.")
    else:
        print("⚠️ No valid Lean declarations found.")

if __name__ == "__main__":
    build_index()