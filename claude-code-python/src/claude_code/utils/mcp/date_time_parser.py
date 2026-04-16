"""Natural language date/time parser via Haiku. Ported from utils/mcp/dateTimeParser.ts"""
from __future__ import annotations
from typing import Literal, TypedDict, Union

class ParseSuccess(TypedDict):
    success: Literal[True]
    value: str

class ParseFailure(TypedDict):
    success: Literal[False]
    error: str

DateTimeParseResult = Union[ParseSuccess, ParseFailure]


async def parse_natural_language_date_time(
    input_str: str,
    fmt: Literal["date", "date-time"] = "date-time",
    signal=None,
) -> DateTimeParseResult:
    """Parse natural language date/time using Haiku. Stub: tries dateutil."""
    try:
        import dateutil.parser
        from datetime import datetime
        dt = dateutil.parser.parse(input_str, default=datetime.now())
        if fmt == "date":
            return {"success": True, "value": dt.strftime("%Y-%m-%d")}
        return {"success": True, "value": dt.isoformat()}
    except Exception as e:
        return {"success": False, "error": str(e)}
