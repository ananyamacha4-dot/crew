"""Custom CrewAI tools for the Researcher agent.

Free tools, no API keys required:
  - duckduckgo_search : web search via DuckDuckGo
  - wikipedia_lookup  : Wikipedia article summary
  - http_get          : generic GET request returning text

All tools return short, plain-text strings (or truncated text) so the LLM
can read them cheaply.
"""

from __future__ import annotations

from crewai.tools import tool

MAX_CHARS = 4000  # cap any tool response to keep prompts cheap


def _truncate(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n…[truncated, {len(text) - limit} chars cut]"


@tool("duckduckgo_search")
def duckduckgo_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo. Returns a numbered list of
    'title — url — snippet' lines. Use for current events, library docs,
    game mechanics references."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "duckduckgo-search package not installed."

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return f"DuckDuckGo search failed: {e}"

    if not results:
        return f"No results for: {query}"

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"{i}. {title}\n   {url}\n   {body}")
    return _truncate("\n\n".join(lines))


@tool("wikipedia_lookup")
def wikipedia_lookup(topic: str, sentences: int = 5) -> str:
    """Look up a topic on Wikipedia. Returns the article summary. Use for
    well-established facts: game rules, algorithms, historical info."""
    try:
        import wikipedia
    except ImportError:
        return "wikipedia package not installed."

    try:
        summary = wikipedia.summary(topic, sentences=sentences, auto_suggest=True)
        url = wikipedia.page(topic, auto_suggest=True).url
        return _truncate(f"{summary}\n\nSource: {url}")
    except wikipedia.DisambiguationError as e:
        options = ", ".join(e.options[:5])
        return f"Ambiguous topic. Try one of: {options}"
    except wikipedia.PageError:
        return f"No Wikipedia page found for: {topic}"
    except Exception as e:
        return f"Wikipedia lookup failed: {e}"


@tool("http_get")
def http_get(url: str) -> str:
    """Make a GET request to a URL and return the response body as text.
    Use for fetching API responses, raw docs, or RSS feeds. Returns up to
    4000 chars."""
    import httpx

    if not url.startswith(("http://", "https://")):
        return "URL must start with http:// or https://"

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "crewai-builder/1.0"})
        status = r.status_code
        text = r.text
    except Exception as e:
        return f"HTTP GET failed: {e}"

    return _truncate(f"HTTP {status}\n\n{text}")
