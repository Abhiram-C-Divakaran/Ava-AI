import os
import requests

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

def web_search(query: str, num_results: int = 5) -> list[dict]:
    if not BRAVE_API_KEY:
        return [{"title": "Mock result", "url": "", "snippet": "Set BRAVE_API_KEY for real search."}]
    headers = {"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY}
    params = {"q": query, "count": num_results}
    try:
        resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return [{"title": "Search error", "url": "", "snippet": f"Error {resp.status_code}"}]
        data = resp.json()
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("description", "")}
            for item in data.get("web", {}).get("results", [])
        ]
    except Exception as e:
        return [{"title": "Search failed", "url": "", "snippet": str(e)}]