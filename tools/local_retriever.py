import os
import chromadb

# Define where the local vector database is stored
CHROMA_DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".chroma_db"))
COLLECTION_NAME = "lean_local_lemmas"

# Initialize the client globally so it doesn't reload on every node execution
try:
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = chroma_client.get_collection(name=COLLECTION_NAME)
except Exception as e:
    print(f"⚠️ Warning: Could not connect to local ChromaDB at {CHROMA_DB_DIR}.")
    print(f"Make sure you run 'utils/build_index.py' first. Error: {e}")
    collection = None

def search_local(query: str, k: int = 3) -> str:
    """
    Queries the local Chroma database for the most relevant Lean definitions/theorems.
    """
    if collection is None:
        return ""

    try:
        # Chroma handles the text-to-embedding translation automatically under the hood
        results = collection.query(
            query_texts=[query],
            n_results=k
        )
        
        # Results return a dictionary of lists. We grab the first list of documents.
        documents = results.get("documents", [[]])[0]
        
        if not documents:
            return ""

        # Format the retrieved code blocks into a readable string for the prompt
        formatted_results = "\n".join([f"-- Local Match {i+1} --\n{doc}" for i, doc in enumerate(documents)])
        return formatted_results

    except Exception as e:
        print(f"⚠️ ChromaDB search failed: {e}")
        return ""

# # Quick test execution if you run this file directly
# if __name__ == "__main__":
#     print(search_local("TopologicalSpace compact", k=2))