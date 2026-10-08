"""JSON serialization for ``System.utils.JSON.toJSON``.

``toJSON(value)`` mirrors ``JSON.stringify`` from JavaScript: objects and
arrays become a JSON document, non-finite numbers become ``null``, function
values are omitted from objects (and become ``null`` inside arrays), and
``undefined`` behaves the same way.  The optional second argument formats the
output the way ``JSON.stringify(value, null, space)`` does.
"""

from __future__ import annotations

import math
from typing import Any

from .runtime import (
    UNDEFINED,
    RuntimeErrorX,
    XCollectionInstance,
    XEnumMember,
    XExceptionValue,
    XInstance,
)

__all__ = ["stringify"]

#: Marker for "omit this entry" (JavaScript drops ``undefined``/functions
#: from objects).
_OMIT = object()

#: ``JSON.stringify`` caps the indent at ten characters.
_MAX_INDENT = 10


def _fail(message: str) -> RuntimeErrorX:
    return RuntimeErrorX(message)


def _quote(text: str) -> str:
    pieces = ['"']
    for character in text:
        if character == '"':
            pieces.append('\\"')
        elif character == "\\":
            pieces.append("\\\\")
        elif character == "\n":
            pieces.append("\\n")
        elif character == "\r":
            pieces.append("\\r")
        elif character == "\t":
            pieces.append("\\t")
        elif character == "\b":
            pieces.append("\\b")
        elif character == "\f":
            pieces.append("\\f")
        elif ord(character) < 0x20:
            pieces.append(f"\\u{ord(character):04x}")
        else:
            pieces.append(character)
    pieces.append('"')
    return "".join(pieces)


def _number(value: float | int) -> str:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "null"
        if value.is_integer() and abs(value) < 1e21:
            return str(int(value))
        return repr(value)
    return str(value)


def _to_json(value: Any, seen: set[int]) -> Any:
    """Convert an X value into JSON-safe Python data (or ``_OMIT``)."""
    if value is UNDEFINED or value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, XCollectionInstance):
        return _to_json(value._data, seen)
    if isinstance(value, XEnumMember):
        return _to_json(value.value, seen)
    if isinstance(value, XExceptionValue):
        return {
            "name": value.name,
            "message": value.message,
            "cause": _to_json(value.cause, seen),
        }
    if isinstance(value, XInstance):
        value = value.fields
    if isinstance(value, dict):
        identity = id(value)
        if identity in seen:
            raise _fail("Converting circular structure to JSON")
        seen.add(identity)
        try:
            result: dict[str, Any] = {}
            for key, item in value.items():
                converted = _to_json(item, seen)
                if converted is _OMIT:
                    continue
                result[str(key)] = converted
            return result
        finally:
            seen.discard(identity)
    if isinstance(value, (list, tuple, set)):
        identity = id(value)
        if identity in seen:
            raise _fail("Converting circular structure to JSON")
        seen.add(identity)
        try:
            items = sorted(value, key=str) if isinstance(value, set) else value
            result = []
            for item in items:
                converted = _to_json(item, seen)
                result.append(None if converted is _OMIT else converted)
            return result
        finally:
            seen.discard(identity)
    # Functions, classes, namespaces and anything else without a JSON form:
    # omitted from objects, null inside arrays — like JSON.stringify.
    return _OMIT


def _dump(data: Any, indent: str | None, level: int) -> str:
    if data is None:
        return "null"
    if data is True:
        return "true"
    if data is False:
        return "false"
    if isinstance(data, (int, float)):
        return _number(data)
    if isinstance(data, str):
        return _quote(data)
    if isinstance(data, list):
        if not data:
            return "[]"
        if indent:
            pad = "\n" + indent * (level + 1)
            close = "\n" + indent * level
            last = len(data) - 1
            body = "".join(
                pad
                + _dump(item, indent, level + 1)
                + ("," if index < last else "")
                for index, item in enumerate(data)
            )
            return "[" + body + close + "]"
        return "[" + ",".join(
            _dump(item, indent, level + 1) for item in data
        ) + "]"
    if isinstance(data, dict):
        if not data:
            return "{}"
        if indent:
            pad = "\n" + indent * (level + 1)
            close = "\n" + indent * level
            keys = list(data)
            last = len(keys) - 1
            body = ""
            for index, key in enumerate(keys):
                body += (
                    pad
                    + _quote(str(key))
                    + ": "
                    + _dump(data[key], indent, level + 1)
                    + ("," if index < last else "")
                )
            return "{" + body + close + "}"
        return "{" + ",".join(
            _quote(str(key)) + ":" + _dump(data[key], indent, level + 1)
            for key in data
        ) + "}"
    return "null"


def stringify(value: Any, space: Any = None) -> str:
    """Serialize *value* to a JSON string, optionally pretty-printed."""
    indent: str | None
    if space is None:
        indent = None
    elif isinstance(space, bool):
        raise _fail(
            "toJSON indent must be a number of spaces or a string, got boolean"
        )
    elif isinstance(space, int):
        if space < 0:
            raise _fail(f"toJSON indent cannot be negative, got {space}")
        indent = " " * min(space, _MAX_INDENT) or None
    elif isinstance(space, str):
        indent = space[:_MAX_INDENT] or None
    else:
        raise _fail(
            "toJSON indent must be a number of spaces or a string, "
            f"got {type(space).__name__}"
        )

    converted = _to_json(value, set())
    if converted is _OMIT:
        return "null"
    return _dump(converted, indent, 0)
