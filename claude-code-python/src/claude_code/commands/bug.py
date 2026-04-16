# 原始 TS: commands/bughunter/ (closest match for bug reporting)
"""Bug command - report a bug or open the GitHub issue template."""
from __future__ import annotations

import platform
import sys
from typing import Any

from ..commands.version import get_version

_BUG_URL = "https://github.com/anthropics/claude-code/issues/new"
_TEMPLATE = """## Bug Report

**Version:** {version}
**OS:** {os}
**Python:** {python}

### Description
(Describe the bug here)

### Steps to reproduce
1.
2.
3.

### Expected behaviour


### Actual behaviour


"""


def build_bug_report_url(body: str | None = None) -> str:
    """Return a pre-filled GitHub new-issue URL."""
    import urllib.parse
    params: dict[str, str] = {"template": "bug_report.md"}
    if body:
        params["body"] = body
    query = urllib.parse.urlencode(params)
    return f"{_BUG_URL}?{query}"


def build_bug_template() -> str:
    return _TEMPLATE.format(
        version=get_version(),
        os=f"{platform.system()} {platform.release()}",
        python=sys.version.split()[0],
    )


async def run(args: str = "", context: Any = None) -> dict[str, Any]:
    """Open the bug-report URL and show the template."""
    template = build_bug_template()
    url = build_bug_report_url()
    return {
        "type": "text",
        "value": (
            f"To report a bug, open:\n  {url}\n\n"
            "Or use this template:\n\n" + template
        ),
    }
