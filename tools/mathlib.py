import requests

def search_mathlib(query_string: str, num_results: int = 5) -> str:
    """
    Queries LeanSearch API for Mathlib theorems.
    """
    url = "https://leansearch.net/search" 
    payload = {
        "query": [query_string],
        "num_results": num_results
    }
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or not isinstance(data, list) or len(data) == 0:
            return ""

        theorems_list = data[0]
        if not theorems_list:
            return ""

        formatted_results = []
        for idx, item in enumerate(theorems_list, 1):
            theorem = item.get("result", {})
            
            name_list = theorem.get("name", [])
            full_name = ".".join(name_list) if isinstance(name_list, list) else name_list
            signature = theorem.get("signature", "")
            informal_desc = theorem.get("informal_description", "No description")
            
            formatted_results.append(
                f"-- Mathlib Match {idx} --\n"
                f"Name: {full_name}\n"
                f"Signature: {signature}\n"
                f"Description: {informal_desc}\n"
            )

        return "\n".join(formatted_results)

    except Exception as e:
        print(f"⚠️ LeanSearch API failed: {e}")
        return ""

# if __name__ == "__main__":
#     print(search_mathlib("cramer's rule", num_results=3))