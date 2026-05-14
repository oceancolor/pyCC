"""MCP utilities. Ported from utils/mcp/dateTimeParser.ts and elicitationValidation.ts"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# dateTimeParser.ts
# ---------------------------------------------------------------------------


def looks_like_iso8601(input: str) -> bool:
    """Return True if *input* looks like an ISO 8601 date or datetime string."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}(T|$)", input.strip()))


def _tz_offset_str() -> str:
    """Return the local timezone offset as '+HH:MM' or '-HH:MM'."""
    now = datetime.now()
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    offset_minutes = int((now - utc_now).total_seconds() / 60)
    sign = "+" if offset_minutes >= 0 else "-"
    abs_min = abs(offset_minutes)
    return f"{sign}{abs_min // 60:02d}:{abs_min % 60:02d}"


async def parse_natural_language_datetime(
    input: str,
    format: str = "date-time",
    signal: Optional[Any] = None,
) -> Dict[str, Any]:
    """Parse natural language date/time into ISO 8601 format.

    This is a best-effort Python port. A full implementation would call
    a language model (Claude Haiku) to interpret the input. Here we use
    Python's dateutil / stdlib fallback.

    Args:
        input: Natural language string, e.g. "tomorrow at 3pm".
        format: ``'date'`` (YYYY-MM-DD) or ``'date-time'`` (full ISO 8601).
        signal: Unused cancellation signal (for API compatibility).

    Returns:
        ``{"success": True, "value": "<iso-string>"}`` or
        ``{"success": False, "error": "<message>"}``.
    """
    # Try dateutil if available
    try:
        from dateutil import parser as du_parser  # type: ignore
        from dateutil.relativedelta import relativedelta  # type: ignore

        dt = du_parser.parse(input, default=datetime.now())
        if format == "date":
            return {"success": True, "value": dt.strftime("%Y-%m-%d")}
        tz_str = _tz_offset_str()
        return {"success": True, "value": dt.strftime(f"%Y-%m-%dT%H:%M:%S{tz_str}")}
    except Exception:
        pass

    # Minimal regex fallback for common patterns
    try:
        now = datetime.now()
        text = input.strip().lower()
        dt: Optional[datetime] = None
        if text in ("today",):
            dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif text in ("tomorrow",):
            from datetime import timedelta
            dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif text in ("yesterday",):
            from datetime import timedelta
            dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        # YYYY-MM-DD
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            dt = datetime.strptime(text, "%Y-%m-%d")

        if dt is not None:
            if format == "date":
                return {"success": True, "value": dt.strftime("%Y-%m-%d")}
            tz_str = _tz_offset_str()
            return {"success": True, "value": dt.strftime(f"%Y-%m-%dT%H:%M:%S{tz_str}")}
    except Exception:
        pass

    return {"success": False, "error": "Unable to parse date/time from input"}


# ---------------------------------------------------------------------------
# elicitationValidation.ts
# ---------------------------------------------------------------------------

STRING_FORMATS = {
    "email": {"description": "email address", "example": "user@example.com"},
    "uri": {"description": "URI", "example": "https://example.com"},
    "date": {"description": "date", "example": "2024-03-15"},
    "date-time": {"description": "date-time", "example": "2024-03-15T14:30:00Z"},
}


def is_enum_schema(schema: Dict[str, Any]) -> bool:
    """Return True if schema is a single-select enum."""
    return schema.get("type") == "string" and ("enum" in schema or "oneOf" in schema)


def is_multi_select_enum_schema(schema: Dict[str, Any]) -> bool:
    """Return True if schema is a multi-select enum (type: array with items.enum)."""
    return (
        schema.get("type") == "array"
        and isinstance(schema.get("items"), dict)
        and ("enum" in schema["items"] or "anyOf" in schema["items"])
    )


def get_enum_values(schema: Dict[str, Any]) -> List[str]:
    """Extract enum option values from an EnumSchema dict."""
    if "oneOf" in schema:
        return [item.get("const", str(item)) for item in schema["oneOf"]]
    return list(schema.get("enum", []))


def get_enum_labels(schema: Dict[str, Any]) -> List[str]:
    """Extract display labels from an EnumSchema dict."""
    if "oneOf" in schema:
        return [item.get("title", item.get("const", "")) for item in schema["oneOf"]]
    labels = schema.get("enumNames")
    return list(labels) if labels else get_enum_values(schema)


def get_format_hint(schema: Dict[str, Any]) -> Optional[str]:
    """Return a helpful placeholder/hint string for the given schema."""
    t = schema.get("type")
    if t == "string":
        fmt = schema.get("format")
        if fmt and fmt in STRING_FORMATS:
            info = STRING_FORMATS[fmt]
            return f"{info['description']}, e.g. {info['example']}"
        return None
    if t in ("number", "integer"):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        example = "42" if t == "integer" else "3.14"
        if minimum is not None and maximum is not None:
            return f"({t} between {minimum} and {maximum})"
        if minimum is not None:
            return f"({t} >= {minimum})"
        if maximum is not None:
            return f"({t} <= {maximum})"
        return f"({t}, e.g. {example})"
    return None


def validate_elicitation_input(
    string_value: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate a string input against a primitive schema definition.

    Returns ``{"value": coerced_value, "isValid": True}`` or
    ``{"isValid": False, "error": "<message>"}``.
    """
    t = schema.get("type", "string")

    try:
        if is_enum_schema(schema):
            values = get_enum_values(schema)
            if string_value not in values:
                return {"isValid": False, "error": f"Must be one of: {', '.join(values)}"}
            return {"value": string_value, "isValid": True}

        if t == "string":
            min_len = schema.get("minLength")
            max_len = schema.get("maxLength")
            if min_len is not None and len(string_value) < min_len:
                return {"isValid": False, "error": f"Must be at least {min_len} character(s)"}
            if max_len is not None and len(string_value) > max_len:
                return {"isValid": False, "error": f"Must be at most {max_len} character(s)"}
            fmt = schema.get("format")
            if fmt == "email" and "@" not in string_value:
                return {"isValid": False, "error": "Must be a valid email address"}
            if fmt == "uri" and not re.match(r"https?://", string_value):
                return {"isValid": False, "error": "Must be a valid URI"}
            if fmt == "date" and not re.match(r"^\d{4}-\d{2}-\d{2}$", string_value):
                return {"isValid": False, "error": "Must be a valid date, e.g. 2024-03-15"}
            if fmt == "date-time" and not re.match(r"^\d{4}-\d{2}-\d{2}T", string_value):
                return {"isValid": False, "error": "Must be a valid date-time"}
            return {"value": string_value, "isValid": True}

        if t in ("number", "integer"):
            val: Union[int, float]
            val = int(string_value) if t == "integer" else float(string_value)
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and val < minimum:
                return {"isValid": False, "error": f"Must be >= {minimum}"}
            if maximum is not None and val > maximum:
                return {"isValid": False, "error": f"Must be <= {maximum}"}
            return {"value": val, "isValid": True}

        if t == "boolean":
            low = string_value.strip().lower()
            if low in ("true", "yes", "1"):
                return {"value": True, "isValid": True}
            if low in ("false", "no", "0"):
                return {"value": False, "isValid": True}
            return {"isValid": False, "error": "Must be true or false"}

    except (ValueError, TypeError) as exc:
        return {"isValid": False, "error": str(exc)}

    return {"isValid": False, "error": f"Unsupported schema type: {t!r}"}
