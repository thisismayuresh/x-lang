"""Single-sourced builtin knowledge for tooling (LSP, checker, docs).

The interpreter's own tables — ``_STRING_METHODS`` / ``_ARRAY_METHODS`` and
the builtin namespaces assembled at startup — are the runtime truth for
"which builtin methods exist".  This module exposes that truth as **pure
data** (``MemberInfo``) so the typechecker, the VS Code server and any other
consumer never carry a second handwritten copy.

Public API:

    members_of_type("string")      -> [MemberInfo("trim", "method", ...)]
    namespace_members("HashMap")   -> instance methods of the collection
    namespace_members("System.utils.Math") -> Math's static functions
    known_type_names()             -> {"string", "integer", "Integer", ...}

Design rules (see INTROSPECTION.md):

* **Never raises.**  Every entry point returns ``[]`` / ``set()`` on failure
  so an editor degrades to its flat list instead of losing completions.
* **Pure data out.**  No ``Interpreter``, ``Environment`` or
  ``BuiltinFunction`` crosses the boundary — only frozen ``MemberInfo``.
* **Docstring parsing lives here**, pinned by tests: implementations spell
  their first line ```` ```trim()``` — drop leading whitespace. ```` and
  the parsed signature/doc flow straight into completion details.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass

from .interpreter._common import _ARRAY_METHODS, _STRING_METHODS

#: First-line convention on builtin implementations:
#: ```signature()`` — one-line description.
_SIGNATURE_DOC_RE = re.compile(r"``(?P<sig>[^`]+)``\s*[—–-]\s*(?P<doc>.+)")

#: Value types served from the interpreter's dot-method tables.
_VALUE_TYPE_TABLES: dict[str, dict[str, str]] = {
    "string": _STRING_METHODS,
    "array": _ARRAY_METHODS,
}

#: Special (non-table) members answered inline by ``Interpreter._get_member``:
#: ``length`` properties on strings/arrays and ``toString`` on strings and
#: numbers.  There is no runtime table for these, so this mirror is pinned by
#: a round-trip test (``test_special_members_are_real``) that calls
#: ``_get_member`` for every entry — if the interpreter stops answering one,
#: the test goes red instead of the editor silently offering a dead member.
_VALUE_TYPE_SPECIAL_MEMBERS: dict[str, dict[str, str]] = {
    "string": {"length": "property", "toString": "method"},
    "array": {"length": "property"},
    "integer": {"toString": "method"},
    "float": {"toString": "method"},
    "boolean": {"toString": "method"},
    "number": {"toString": "method"},
}

#: Annotation spellings the checker accepts for a different primitive name.
_VALUE_TYPE_ALIASES: dict[str, str] = {
    "int": "integer",
    "bool": "boolean",
}

#: Cached throwaway interpreter used to enumerate builtin namespaces.
#: Constructed with a sink ``output`` and no arguments; ``_install_builtins``
#: only assembles in-memory Environments, so this is side-effect free apart
#: from reading ``os.environ`` into ``System.process.Environment``.
_INTERPRETER = None


@dataclass(frozen=True)
class MemberInfo:
    """One completable member of a builtin type or namespace."""

    name: str
    kind: str  # "method" | "property" | "namespace" | "class"
    signature: str | None
    doc: str | None
    owner: str


def _parse_signature_doc(doc: str | None) -> tuple[str | None, str | None]:
    """Split a convention docstring into ``(signature, one_line_doc)``.

    Anything that does not start with the ```` ```sig``` — doc ```` form
    yields ``(None, None)``; callers degrade to name-only members.
    """
    if not doc:
        return None, None
    first_line = doc.strip().splitlines()[0].strip()
    match = _SIGNATURE_DOC_RE.match(first_line)
    if not match:
        return None, None
    return match.group("sig").strip(), match.group("doc").strip()


def _member_from_implementation(
    name: str, implementation: object, owner: str, kind: str = "method"
) -> MemberInfo:
    signature, doc = _parse_signature_doc(inspect.getdoc(implementation))
    return MemberInfo(
        name=name, kind=kind, signature=signature, doc=doc, owner=owner
    )


def _normalize_receiver_type(type_name: str | None) -> str:
    """``Stack<string>`` -> ``Stack``; ``string[]`` -> ``array``; trim."""
    text = (type_name or "").strip()
    if not text:
        return ""
    if "<" in text:
        text = text.split("<", 1)[0].strip()
    if text.endswith("[]"):
        return "array"
    return text


def members_of_type(type_name: str | None) -> list[MemberInfo]:
    """Dot-members of a value type: string, array, and the primitives.

    Reads the interpreter's ``_STRING_METHODS`` / ``_ARRAY_METHODS`` tables
    plus the special members (``length``, ``toString``) that
    ``Interpreter._get_member`` answers inline.  User classes and collection
    classes are ``namespace_members``' job and return ``[]`` here.  Never
    raises.
    """
    try:
        raw = _normalize_receiver_type(type_name).lower()
        key = _VALUE_TYPE_ALIASES.get(raw, raw)
        table = _VALUE_TYPE_TABLES.get(key)
        specials = _VALUE_TYPE_SPECIAL_MEMBERS.get(key)
        if table is None and specials is None:
            return []
        members: list[MemberInfo] = []
        if table is not None:
            from .interpreter import Interpreter

            for name, implementation_name in table.items():
                implementation = getattr(Interpreter, implementation_name, None)
                members.append(
                    _member_from_implementation(name, implementation, key)
                )
        for name, kind in (specials or {}).items():
            if any(existing.name == name for existing in members):
                continue
            signature = f"{name}()" if kind == "method" else None
            doc = None
            if key == "string" and name == "length":
                doc = "number of characters"
            elif key == "array" and name == "length":
                doc = "number of elements"
            elif name == "toString":
                doc = "string form of the value"
            members.append(
                MemberInfo(
                    name=name, kind=kind, signature=signature, doc=doc, owner=key
                )
            )
        return members
    except Exception:
        return []


def _get_interpreter():
    """Lazily build the cached throwaway interpreter, or ``None``."""
    global _INTERPRETER
    if _INTERPRETER is not None:
        return _INTERPRETER
    try:
        from .interpreter import Interpreter

        _INTERPRETER = Interpreter(
            arguments=[], output=lambda _line: None, auto_call_main=False
        )
        return _INTERPRETER
    except Exception:
        return None


def _resolve_dotted_path(interpreter, dotted_path: str):
    """Walk ``interpreter.globals`` along a dotted path; ``None`` if absent."""
    node = interpreter.globals
    for segment in dotted_path.split("."):
        segment = segment.strip()
        if not segment:
            return None
        if hasattr(node, "values") and segment in node.values:
            node = node.values[segment]
        elif isinstance(node, dict) and segment in node:
            node = node[segment]
        else:
            return None
    return node


def _members_of_namespace_node(node, owner: str) -> list[MemberInfo]:
    """Enumerate one resolved namespace/class node as ``MemberInfo``s."""
    from .runtime import BuiltinFunction

    members: list[MemberInfo] = []

    if isinstance(node, dict):
        # CollectionNamespace: the dict part holds only the ``create``
        # constructor entry; instance methods live in ``instance_methods``.
        # Expose the instance surface (no ``create``) — what you call on a
        # value made by ``new X()``.
        source = getattr(node, "instance_methods", None)
        if not isinstance(source, dict):
            source = node
        for name, value in source.items():
            if name == "create":
                continue
            if isinstance(value, BuiltinFunction):
                members.append(
                    _member_from_implementation(name, value.implementation, owner)
                )
            else:
                members.append(
                    MemberInfo(
                        name=name, kind="property", signature=None, doc=None, owner=owner
                    )
                )
        return members

    if hasattr(node, "values") and isinstance(getattr(node, "values"), dict):
        for name, value in node.values.items():
            if isinstance(value, BuiltinFunction):
                members.append(
                    _member_from_implementation(name, value.implementation, owner)
                )
            elif isinstance(value, dict) or (
                hasattr(value, "values") and isinstance(getattr(value, "values"), dict)
            ):
                members.append(
                    MemberInfo(
                        name=name, kind="namespace", signature=None, doc=None, owner=owner
                    )
                )
            else:
                members.append(
                    MemberInfo(
                        name=name, kind="property", signature=None, doc=None, owner=owner
                    )
                )
        return members

    return members


def namespace_members(dotted_path: str | None) -> list[MemberInfo]:
    """Members of a builtin namespace or collection class.

    Accepts full paths (``"System.utils.Math"``, ``"System.io.FileSystem"``)
    and the globally re-exported short names (``"HashMap"``, ``"List"``,
    ``"TreeMap"``, ...).  For collection classes the ``create`` constructor
    entry is omitted — the result is what you can call on an *instance*.
    Unknown paths return ``[]``.  Never raises.
    """
    try:
        text = (dotted_path or "").strip()
        if not text:
            return []
        text = _normalize_receiver_type(text)
        if not text:
            return []
        # Value types are members_of_type's job; the globals env has no
        # "string"/"integer"/... binding, so this is just a fast path.
        if _VALUE_TYPE_ALIASES.get(text.lower(), text.lower()) in _VALUE_TYPE_SPECIAL_MEMBERS:
            return members_of_type(text)
        interpreter = _get_interpreter()
        if interpreter is None:
            return []
        node = _resolve_dotted_path(interpreter, text)
        if node is None:
            return []
        owner = text.split(".")[-1]
        return _members_of_namespace_node(node, owner)
    except Exception:
        return []


def known_type_names() -> set[str]:
    """Type names the checker/lexer already recognize (primitives + builtins).

    Lazy-imports ``typecheck.types`` so importing *this* module never drags
    the checker in (the checker itself imports :func:`members_of_type`).
    Never raises.
    """
    try:
        from .typecheck.types import BUILTIN_TYPE_NAMES, KNOWN_TYPE_NAMES

        return set(KNOWN_TYPE_NAMES) | set(BUILTIN_TYPE_NAMES)
    except Exception:
        return set()
