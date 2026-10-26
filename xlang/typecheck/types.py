"""Type-string parsing and compatibility for the X type checker."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from ..runtime import qualified_exception_paths


PRIMITIVE_ALIASES = {
    "int": "integer",
    "integer": "integer",
    "byte": "integer",
    "float": "float",
    "double": "float",
    "number": "float",
    "boolean": "boolean",
    "bool": "boolean",
    "string": "string",
    "char": "string",
    "void": "void",
    "null": "null",
    "undefined": "undefined",
    "object": "object",
    "Object": "object",
    "Function": "function",
    "function": "function",
    "var": "any",
    "any": "any",
}

#: Names that always refer to a known built-in type rather than a user type.
KNOWN_TYPE_NAMES = frozenset(PRIMITIVE_ALIASES.values())

#: Case-insensitive lookup for primitive aliases, enabling the optional
#: ``primitive_aliases`` feature (``String`` / ``INTEGER`` / ``Object`` →
#: ``string`` / ``integer`` / ``object``).  Values are the canonical
#: lowercase spellings.
PRIMITIVE_ALIASES_CASEFOLD = {
    alias.casefold(): canonical for alias, canonical in PRIMITIVE_ALIASES.items()
}


def canonical_primitive_alias(name: str) -> str | None:
    """Return the canonical primitive type for a case-insensitive spelling.

    ``None`` means the name is not a built-in primitive alias, so callers
    should fall back to their normal resolution.
    """
    return PRIMITIVE_ALIASES_CASEFOLD.get(name.casefold())

#: Every builtin type-name spelling accepted in X annotations.
#:
#: Includes primitive aliases (``int``/``integer``/``bool``/...), collection
#: classes exposed as types (``HashMap``, ``Stack``, extended collections),
#: the ``System``/``Collections`` namespace roots, ``ThreadHandle`` and the
#: built-in exception hierarchy.  User classes, interfaces, enums, type
#: aliases, namespace roots and generic parameters are collected per program.
BUILTIN_TYPE_NAMES = frozenset(
    set(PRIMITIVE_ALIASES)
    | set(PRIMITIVE_ALIASES.values())
    | {
        "record",
        # Collection classes usable as annotations.
        "HashMap",
        "LinkedList",
        "List",
        "Stack",
        "Queue",
        "PriorityQueue",
        "Trie",
        "Set",
        "TreeMap",
        "TreeSet",
        "LinkedHashMap",
        "LRUCache",
        "ConcurrentHashMap",
        "ConcurrentList",
        "ThreadSafeMap",
        "ThreadSafeSet",
        "Collections",
        # Namespace roots and runtime-provided value types.
        "Object",
        "System",
        "FileSystem",
        "Thread",
        "Async",
        "ThreadHandle",
        # Built-in exception hierarchy.
        "Throwable",
        "Exception",
        "Error",
        "RuntimeException",
        "ArithmeticException",
        "TypeException",
        "IllegalArgumentException",
        "IndexOutOfBoundsException",
        "IOException",
        "FileSystemException",
        "HttpException",
        "DatabaseException",
        "DatabaseError",
        # Fully-qualified hierarchy paths, so a catch clause may name an
        # exception inline: catch (System.Throwable.Exception.IOException.
        # HttpException error) — every generated path is accepted.
        *qualified_exception_paths(),
    }
)


class TypeRelations(Protocol):
    """Optional hook used by :func:`is_compatible` for nominal types."""

    def is_subtype(self, source: "XType", target: "XType") -> bool | None:
        """Return True/False when the checker can decide, or None to fall back."""
        ...


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMERIC_KEY_RE = re.compile(r"^[0-9]+(\.[0-9]+)?$")


def _record_field_label(name: str) -> str:
    """Render a record field name the way source spells it."""
    if _IDENTIFIER_RE.match(name) or _NUMERIC_KEY_RE.match(name):
        return name
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True)
class XType:
    """A parsed X type annotation.

    ``dimensions`` is the array depth (``int[][]`` -> 2); ``is_array`` stays
    in sync so existing checks keep working.
    """

    name: str
    arguments: tuple["XType", ...] = ()
    is_array: bool = False
    is_nullable: bool = False
    union_parts: tuple["XType", ...] = ()
    record_fields: tuple[tuple[str, "XType"], ...] = ()
    is_any: bool = False
    dimensions: int = 0
    literal: str | None = None

    def __post_init__(self) -> None:
        depth = self.dimensions
        if depth <= 0 and self.is_array:
            depth = 1
        depth = max(0, depth)
        object.__setattr__(self, "dimensions", depth)
        object.__setattr__(self, "is_array", depth > 0)

    def display(self) -> str:
        """Return a readable type name."""
        if self.is_any:
            return "any"
        if self.literal is not None:
            return f'"{self.literal}"'
        if self.union_parts:
            text = "|".join(part.display() for part in self.union_parts)
            if len(self.union_parts) > 1:
                text = f"({text})"
            if self.is_array:
                text += "[]" * self.dimensions
            if self.is_nullable:
                text += "?"
            return text
        text = self.name
        if self.arguments:
            inner = ", ".join(argument.display() for argument in self.arguments)
            text = f"{text}<{inner}>"
        if self.record_fields:
            # Object-literal style so diagnostics read like the source:
            # `{ 200: { name: string, age: integer } }` rather than the
            # internal `record{...}` spelling.
            fields = ", ".join(
                f"{_record_field_label(field_name)}: {field_type.display()}"
                for field_name, field_type in self.record_fields
            )
            text = f"{{ {fields} }}" if fields else "{}"
        if self.is_array:
            text += "[]" * self.dimensions
        if self.is_nullable:
            text += "?"
        return text


ANY = XType("any", is_any=True)
VOID = XType("void")
NULL = XType("null")
UNDEFINED = XType("undefined")
INTEGER = XType("integer")
FLOAT = XType("float")
BOOLEAN = XType("boolean")
STRING = XType("string")
OBJECT = XType("object")
FUNCTION = XType("function")


def parse_type(type_name: str | None) -> XType:
    """Parse an X type annotation string into an ``XType``."""
    if type_name is None or type_name == "" or type_name == "var":
        return ANY
    text = type_name.strip()
    if text.startswith("record{") and text.endswith("}"):
        return _parse_record(text)
    union_parts = split_union(text)
    if len(union_parts) > 1:
        return XType(
            "union",
            union_parts=tuple(parse_type(part) for part in union_parts),
        )
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return XType("string", literal=_unescape_literal(text[1:-1]))
    nullable = text.endswith("?")
    if nullable:
        text = text[:-1]
    array = text.endswith("[]")
    if array:
        text = text[:-2]
        # Nested arrays: string[][][], one dimension per "[]" suffix.
        inner = parse_type(text)
        return XType(
            inner.name,
            inner.arguments,
            is_array=True,
            is_nullable=nullable or inner.is_nullable,
            union_parts=inner.union_parts,
            record_fields=inner.record_fields,
            is_any=inner.is_any,
            dimensions=inner.dimensions + 1,
            literal=inner.literal,
        )
    generic_name, arguments = _split_generic(text)
    normalized = PRIMITIVE_ALIASES.get(generic_name, generic_name)
    is_any = normalized == "any"
    return XType(
        normalized,
        tuple(parse_type(argument) for argument in arguments),
        is_nullable=nullable,
        is_any=is_any,
    )


def _unescape_literal(inner: str) -> str:
    """Decode a string-literal type body (``"a\\"b"`` -> ``a"b``)."""
    return inner.replace('\\"', '"').replace("\\\\", "\\")


def split_top_level(text: str, separator: str) -> list[str]:
    """Split ``text`` on ``separator`` characters outside any brackets.

    Tracks ``<>``, ``()``, ``[]`` and ``{}`` so nested generic arguments,
    record bodies, and array suffixes keep their own separators intact
    (``Promise<{a: integer, b: string}>`` yields one type argument).
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for character in text:
        if character in "<({[":
            depth += 1
            current.append(character)
        elif character in ">)}]":
            depth = max(0, depth - 1)
            current.append(character)
        elif character == separator and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def split_union(type_name: str) -> list[str]:
    """Split a union type on top-level ``|`` characters."""
    return split_top_level(type_name, "|")


def substitute(type_value: XType, mapping: dict[str, XType]) -> XType:
    """Replace type parameters using ``mapping``."""
    if type_value.is_any:
        return type_value
    if type_value.literal is not None:
        return type_value
    if type_value.union_parts:
        return XType(
            "union",
            arguments=type_value.arguments,
            is_array=type_value.is_array,
            is_nullable=type_value.is_nullable,
            union_parts=tuple(
                substitute(part, mapping) for part in type_value.union_parts
            ),
            record_fields=type_value.record_fields,
            is_any=type_value.is_any,
            dimensions=type_value.dimensions,
        )
    if type_value.name in mapping and not type_value.arguments:
        replacement = mapping[type_value.name]
        return XType(
            replacement.name,
            replacement.arguments,
            is_array=type_value.is_array or replacement.is_array,
            is_nullable=type_value.is_nullable or replacement.is_nullable,
            union_parts=replacement.union_parts,
            record_fields=replacement.record_fields,
            is_any=replacement.is_any,
            dimensions=max(type_value.dimensions, replacement.dimensions),
        )
    return XType(
        type_value.name,
        tuple(substitute(argument, mapping) for argument in type_value.arguments),
        is_array=type_value.is_array,
        is_nullable=type_value.is_nullable,
        record_fields=tuple(
            (name, substitute(field_type, mapping))
            for name, field_type in type_value.record_fields
        ),
        is_any=type_value.is_any,
        dimensions=type_value.dimensions,
        literal=type_value.literal,
    )


def _strip_array(type_value: XType) -> XType:
    """Return the element type of an array type (``integer[][]`` -> ``integer[]``)."""
    depth = max(0, type_value.dimensions - 1)
    return XType(
        type_value.name,
        type_value.arguments,
        is_array=depth > 0,
        is_nullable=type_value.is_nullable,
        union_parts=type_value.union_parts,
        record_fields=type_value.record_fields,
        is_any=type_value.is_any,
        dimensions=depth,
        literal=type_value.literal,
    )


def _strip_nullable(type_value: XType) -> XType:
    return XType(
        type_value.name,
        type_value.arguments,
        is_array=type_value.is_array,
        is_nullable=False,
        union_parts=type_value.union_parts,
        record_fields=type_value.record_fields,
        is_any=type_value.is_any,
        dimensions=type_value.dimensions,
        literal=type_value.literal,
    )


def _numeric_field_literal(name: str) -> XType | None:
    """Integer/float literal for a plain decimal record key like ``"200"``.

    Object literals store numeric keys (``200:``) as record field names, so
    the name is consulted as a number as well as a string when checking the
    field against ``object<K, ...>``.  Anything else — identifiers, signs,
    hex, non-ASCII digits — stays a plain string key.
    """
    if not name.isascii():
        return None
    if name.isdecimal():
        return XType("integer", literal=int(name))
    if "." in name and name.replace(".", "", 1).isdecimal():
        return XType("float", literal=float(name))
    return None


def _record_field_key_fits(
    field_name: str,
    key_type: XType,
    relations: TypeRelations | None,
) -> bool:
    """Whether one record field name satisfies an ``object<K, ...>`` key type."""
    if is_compatible(
        XType("string", literal=field_name), key_type, relations=relations
    ):
        return True
    numeric = _numeric_field_literal(field_name)
    if numeric is None:
        return False
    return is_compatible(numeric, key_type, relations=relations)


def is_compatible(
    source: XType,
    target: XType,
    *,
    relations: TypeRelations | None = None,
) -> bool:
    """Return whether a value of ``source`` may be used where ``target`` is expected."""
    if target.is_any or source.is_any:
        return True
    if source.union_parts and not source.is_array:
        # An array whose *element* is a union (``(record{a}|record{b})[]``)
        # is handled by the array branch below, which strips one dimension
        # before comparing elements.
        return all(
            is_compatible(part, target, relations=relations)
            for part in source.union_parts
        )
    if target.union_parts:
        return any(
            is_compatible(source, part, relations=relations)
            for part in target.union_parts
        )
    if target.literal is not None or source.literal is not None:
        if target.literal is not None:
            if source.literal is None:
                return False
            return source.literal == target.literal and source.name == target.name
        return is_compatible(
            XType(source.name, source.arguments), target, relations=relations
        )
    if source.is_nullable:
        return target.is_nullable or is_compatible(
            _strip_nullable(source), target, relations=relations
        )
    if source.name in {"null", "undefined"}:
        return target.is_nullable or target.name in {"null", "undefined", "object"}
    if target.is_nullable:
        return is_compatible(source, _strip_nullable(target), relations=relations)
    if target.is_array:
        if not source.is_array:
            return source.name in {"array", "object"}
        if source.dimensions != target.dimensions:
            return False
        element_target = _strip_array(target)
        element_source = _strip_array(source)
        return is_compatible(element_source, element_target, relations=relations)
    if target.record_fields:
        source_fields = {
            name: field_type for name, field_type in source.record_fields
        }
        if not source_fields and source.name == "object":
            return True
        for field_name, field_type in target.record_fields:
            if field_name not in source_fields:
                return source.name == "object"
            if not is_compatible(
                source_fields[field_name], field_type, relations=relations
            ):
                return False
        return True
    if target.name == "object":
        if not target.arguments:
            return True
        if source.record_fields and len(target.arguments) == 2:
            key_type, value_type = target.arguments
            return all(
                _record_field_key_fits(field_name, key_type, relations)
                and is_compatible(field_type, value_type, relations=relations)
                for field_name, field_type in source.record_fields
            )
        if (
            source.name == "object"
            and source.arguments
            and len(source.arguments) == len(target.arguments)
        ):
            return all(
                is_compatible(actual, expected, relations=relations)
                for actual, expected in zip(source.arguments, target.arguments)
            )
        # A value whose shape the checker cannot see (bare ``object``, a class
        # instance, ...) stays acceptable, matching the runtime's coercion.
        return True
    if source.is_array and not target.is_array:
        # An array never satisfies a scalar annotation (``int[]`` where ``int``
        # is expected); the runtime would reject it anyway.
        return False
    if target.name == "function":
        return source.name == "function"
    if target.name == "float" and source.name == "integer":
        return True
    if source.name == target.name:
        if target.arguments or source.arguments:
            if len(source.arguments) != len(target.arguments):
                return True
            return all(
                is_compatible(actual, expected, relations=relations)
                for actual, expected in zip(source.arguments, target.arguments)
            )
        return True
    if relations is not None:
        verdict = relations.is_subtype(source, target)
        if verdict is not None:
            return verdict
    if target.arguments or source.arguments:
        if (
            target.arguments
            and source.arguments
            and len(source.arguments) != len(target.arguments)
        ):
            return True
        return _collection_alias(source.name) == _collection_alias(target.name)
    return _collection_alias(source.name) == _collection_alias(target.name)


def _collection_alias(name: str) -> str:
    if name == "List":
        return "LinkedList"
    return name


def _split_generic(text: str) -> tuple[str, list[str]]:
    open_index = text.find("<")
    if open_index < 0 or not text.endswith(">"):
        return text, []
    name = text[:open_index]
    inner = text[open_index + 1 : -1]
    arguments: list[str] = []
    depth = 0
    current: list[str] = []
    for character in inner:
        if character == "<":
            depth += 1
            current.append(character)
        elif character == ">":
            depth -= 1
            current.append(character)
        elif character == "," and depth == 0:
            arguments.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current:
        arguments.append("".join(current).strip())
    return name, arguments


def _parse_record(text: str) -> XType:
    body = text[len("record{") : -1]
    fields: list[tuple[str, XType]] = []
    for piece in body.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        type_part, _, name = piece.rpartition(" ")
        if not name:
            continue
        fields.append((name, parse_type(type_part.strip())))
    return XType("record", record_fields=tuple(fields))


@dataclass
class TypeScope:
    """A nested map of names to types and assignment state."""

    parent: "TypeScope | None" = None
    types: dict[str, XType] = field(default_factory=dict)
    assigned: dict[str, bool] = field(default_factory=dict)
    constants: set[str] = field(default_factory=set)

    def define(self, name: str, type_value: XType, assigned: bool, constant: bool = False) -> None:
        self.types[name] = type_value
        self.assigned[name] = assigned
        if constant:
            self.constants.add(name)

    def lookup(self, name: str) -> tuple[XType, bool] | None:
        if name in self.types:
            return self.types[name], self.assigned.get(name, False)
        if self.parent is not None:
            return self.parent.lookup(name)
        return None

    def lookup_owner(self, name: str) -> "TypeScope | None":
        """The scope that defines *name* (for shadow-safety checks), or None."""
        if name in self.types:
            return self
        if self.parent is not None:
            return self.parent.lookup_owner(name)
        return None

    def is_constant(self, name: str) -> bool:
        if name in self.types:
            if name in self.constants:
                return True
            return False
        if self.parent is not None:
            return self.parent.is_constant(name)
        return False

    def mark_assigned(self, name: str) -> bool:
        if name in self.types:
            self.assigned[name] = True
            return True
        if self.parent is not None:
            return self.parent.mark_assigned(name)
        return False

    def child(self) -> "TypeScope":
        return TypeScope(parent=self)
