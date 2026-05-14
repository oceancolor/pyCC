"""WebSearchTool prompt. Ported from WebSearchTool/prompt.ts"""
from __future__ import annotations

WEB_SEARCH_TOOL_NAME = "WebSearch"


def get_web_search_prompt() -> str:
    return """
- Allows Claude to search the web and use the results to inform responses
- Provides up-to-date information for current events and recent data
- Returns search result information formatted as search result blocks, including links as markdown hyperlinks
- Use this tool for accessing information beyond Claude's knowledge cutoff
- Searches are performed automatically within a single API call

CRITICAL REQUIREMENT - You MUST follow this:
  - After answering the user's question, you MUST include a "Sources:" section at the end of your response
  - In the Sources section, list all relevant URLs from the search results as markdown hyperlinks: [Title](URL)
  - This is MANDATORY - never skip including sources in your response
  - Example format:

    [Your answer here]

    Sources:
    - [Page Title](https://example.com/page)
    - [Another Title](https://example.com/other)
"""
