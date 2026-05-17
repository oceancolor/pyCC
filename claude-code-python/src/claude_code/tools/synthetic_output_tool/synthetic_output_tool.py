"""
SyntheticOutputTool — structured output for non-interactive / SDK sessions.

Ported from SyntheticOutputTool/SyntheticOutputTool.ts.

Key design decisions mirrored from the TS source:
  - The tool is only created when ``is_non_interactive`` is True.
  - Once created it is always enabled.
  - ``create_synthetic_output_tool`` validates the caller-supplied JSON schema
    using jsonschema (equivalent to the AJV validation in the TS source) and
    returns either ``{"tool": <instance>}`` or ``{"error": <message>}``.
  - A per-schema instance cache avoids repeated validation overhead for
    workflows that call ``agent(schema=SAME_SCHEMA_OBJ)`` many times.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Union

SYNTHETIC_OUTPUT_TOOL_NAME = "StructuredOutput"

# Weak-reference cache keyed by schema object identity (mirrors the TS WeakMap).
_tool_cache: dict[int, dict] = {}


def is_synthetic_output_tool_enabled(is_non_interactive: bool = False) -> bool:
    """Return True only when running in a non-interactive (SDK/CLI) session."""
    return is_non_interactive


class SyntheticOutputTool:
    """Return structured output in a caller-specified format.

    In the TS implementation this is built with ``buildTool``; here we expose
    a plain class with the same surface that the rest of the Python port uses.
    """

    name = SYNTHETIC_OUTPUT_TOOL_NAME
    description = "Return structured output in the requested format"
    is_read_only = True
    is_concurrency_safe = True

    def __init__(self, json_schema: Optional[Dict[str, Any]] = None) -> None:
        self._json_schema = json_schema

    def get_schema(self) -> dict:
        input_schema: dict = self._json_schema or {
            "type": "object",
            "additionalProperties": True,
        }
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": input_schema,
        }

    async def call(self, context: Any = None, **input_data: Any) -> dict:
        """Validate *input_data* against the registered schema (if any) and return it."""
        if self._json_schema is not None:
            try:
                import jsonschema  # optional dependency

                jsonschema.validate(input_data, self._json_schema)
            except ImportError:
                # jsonschema not installed — skip validation (best-effort)
                pass
            except Exception as exc:
                raise ValueError(
                    f"Output does not match required schema: {exc}"
                ) from exc

        return {
            "data": "Structured output provided successfully",
            "structured_output": input_data,
        }

    def render_tool_use_message(self, input_data: dict) -> Optional[str]:
        keys = list(input_data.keys())
        if not keys:
            return None
        if len(keys) <= 3:
            return ", ".join(f"{k}: {json.dumps(input_data[k])}" for k in keys)
        return f"{len(keys)} fields: {', '.join(keys[:3])}…"


def create_synthetic_output_tool(
    json_schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate *json_schema* and return ``{"tool": SyntheticOutputTool}`` or ``{"error": str}``.

    Results are cached by schema *object identity* to avoid repeated work when
    the same schema dict is passed many times (mirrors the TS WeakMap cache).
    """
    cache_key = id(json_schema)
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]

    result = _build_synthetic_output_tool(json_schema)
    _tool_cache[cache_key] = result
    return result


def _build_synthetic_output_tool(
    json_schema: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        try:
            import jsonschema

            jsonschema.Draft7Validator.check_schema(json_schema)
        except ImportError:
            # jsonschema not available — accept schema as-is
            pass
        except Exception as exc:
            return {"error": str(exc)}

        tool = SyntheticOutputTool(json_schema=json_schema)
        return {"tool": tool}
    except Exception as exc:
        return {"error": str(exc)}
