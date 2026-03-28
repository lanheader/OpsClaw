---
name: web-search
description: Search the internet for information using DuckDuckGo. Use when the user asks about current events, recent information, or topics not covered by your built-in knowledge. Also use when you need to look up documentation, error messages, or technical solutions online.
license: MIT
---

# Web Search Skill

Search the internet using DuckDuckGo (no API key required).

## When to Use

- User asks about current events, news, or recent information
- You need to look up error messages, stack traces, or technical solutions
- User asks about topics not in your training data
- You need to verify facts or find authoritative sources
- User asks to research a topic online

## How to Search

Use the built-in `execute` tool to run Python commands:

```python
# Basic search
from duckduckgo_search import DDGS
results = DDGS().text("search query", max_results=5)
for r in results:
    print(f"Title: {r['title']}")
    print(f"URL: {r['href']}")
    print(f"Snippet: {r['body']}")
```

## Fetch Web Page Content

After finding relevant URLs, fetch page content:

```python
import httpx
from bs4 import BeautifulSoup

resp = httpx.get("https://example.com", follow_redirects=True, timeout=10)
soup = BeautifulSoup(resp.text, "html.parser")

# Remove scripts and styles
for tag in soup(["script", "style", "nav", "footer", "header"]):
    tag.decompose()

# Extract text (limit to prevent token overflow)
text = soup.get_text(separator="\n", strip=True)[:5000]
print(text)
```

## Search Tips

1. **Be specific**: Use precise queries instead of vague ones
2. **Try multiple queries**: If first search doesn't find good results, rephrase
3. **Check multiple sources**: Cross-reference information from different results
4. **Prioritize official docs**: Prefer official documentation over blog posts
5. **Handle Chinese queries**: DuckDuckGo supports Chinese, try both Chinese and English queries

## Error Handling

```python
from duckduckgo_search import DDGS

try:
    results = DDGS().text("query", max_results=5)
except Exception as e:
    print(f"Search failed: {e}")
    # Fallback: suggest user check manually
```

## Dependencies

- `duckduckgo-search` (Python package)
- `httpx` (for fetching pages)
- `beautifulsoup4` (for parsing HTML)

Install if missing:
```bash
pip install duckduckgo-search httpx beautifulsoup4
```
