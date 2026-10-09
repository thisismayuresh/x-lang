"""
X language interpreter with module namespace support.

Module imports create Environment-backed namespace objects containing
exported declarations accessible via dot access. Flattened top-level
bindings are preserved only when they do not create collisions between
different declarations; when flattening would introduce a conflicting
binding for an existing name, a RuntimeErrorX is raised. This prevents
silent cross-module name collisions while maintaining backward
compatibility where safe.
"""

from __future__ import annotations
import asyncio
import functools
import heapq
import inspect
import os
import sys
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable
import math
import random

from ..ast_nodes import (
    ArrayLiteral,
    Assignment,
    AwaitExpression,
    Binary,
    Block,
    BreakStatement,
    Call,
    ClassDeclaration,
    ClassicForStatement,
    DoWhileStatement,
    DefaultPattern,
    EnumDeclaration,
    ExpressionStatement,
    ForStatement,
    FunctionDeclaration,
    FunctionExpression,
    ImportCall,
    ImportDeclaration,
    ImportAlias,
    ImportNamespaceAlias,
    ImportNamespaceAlias,
    Identifier,
    IfStatement,
    Index,
    Literal,
    LiteralPattern,
    MatchExpression,
    Member,
    NewExpression,
    NamespaceDeclaration,
    ObjectLiteral,
    OptionalChain,
    Program,
    ReturnStatement,
    Spread,
    ArrayPattern,
    BindingPattern,
    EnumPattern,
    ObjectPattern,
    SwitchCase,
    SwitchStatement,
    ThisExpression,
    TemplateLiteral,
    ThrowStatement,
    TryStatement,
    TypeDeclaration,
    UndefinedPattern,
    UndefinedLiteral,
    Unary,
    VariableDeclaration,
    WhileStatement,
    WildcardPattern,
)
from .. import jsonify
from ..config import XConfig
from ..diagnostics import SourceWarning, member_noun
from ..network import FetchCall, normalize_fetch_call, perform_fetch
from ..runtime import (
    EXCEPTION_PARENTS as _EXCEPTION_PARENTS,
)
from ..runtime import (
    BuiltinFunction,
    Environment,
    LoopSignal,
    OverloadedFunction,
    ReturnSignal,
    RuntimeErrorX,
    ThrownValue,
    UNDEFINED,
    XArray,
    XClass,
    XCollectionInstance,
    XEnumMember,
    XExceptionValue,
    XFunction,
    XInstance,
    XObject,
    XSuper,
    XThreadHandle,
    exception_children,
)


#: Largest string a ``repeat``/``padStart``/``padEnd`` builtin may build.
MAX_STRING_LENGTH = 10_000_000


class ComparatorItem:
    """Wrapper that makes arbitrary X-language values heap-orderable.

    When a custom comparator function is supplied to PriorityQueue.create,
    each enqueued value is wrapped in a ComparatorItem.  Python's heapq
    module calls ``__lt__`` to determine heap order, so we delegate the
    comparison to the user-supplied X function via ``call_fn``.
    """

    def __init__(
        self,
        value: Any,
        comparator_fn: Any,
        call_fn: Any,
    ) -> None:
        """Store the wrapped value, the comparator function, and the call dispatch."""
        self.value = value
        self.comparator_fn = comparator_fn
        self.call_fn = call_fn

    def __lt__(self, other: "ComparatorItem") -> bool:
        """Return True when self should be popped before other (i.e. self < other)."""
        result = self.call_fn(self.comparator_fn, [self.value, other.value])
        return (result or 0) < 0

    def __le__(self, other: "ComparatorItem") -> bool:
        """Return True when self <= other (heapq may call this in Python 3.12+)."""
        result = self.call_fn(self.comparator_fn, [self.value, other.value])
        return (result or 0) <= 0

    def __eq__(self, other: object) -> bool:
        """Equality by wrapped value identity."""
        if not isinstance(other, ComparatorItem):
            return NotImplemented
        return self.value == other.value  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return f"ComparatorItem({self.value!r})"


#: Dot-callable methods on plain X arrays (``myArray.map(cb)``).
#: Maps method name -> ``Interpreter`` method implementing the call.  Every
#: implementation receives the receiver as ``arguments[0]`` — the same shape
#: the HashMap/LinkedList builtins use — so ``List.map(array, cb)`` works too.
_ARRAY_METHODS: dict[str, str] = {
    "map": "_array_map",
    "filter": "_array_filter",
    "reduce": "_array_reduce",
    "forEach": "_array_for_each",
    "find": "_array_find",
    "some": "_array_some",
    "every": "_array_every",
    "indexOf": "_array_index_of",
    "contains": "_array_contains",
    "sort": "_array_sort",
    "reverse": "_array_reverse",
    "slice": "_array_slice",
    "concat": "_array_concat",
    "join": "_array_join",
    "first": "_array_first",
    "last": "_array_last",
    "isEmpty": "_array_is_empty",
    "clear": "_array_clear",
    "push": "_array_push",
    "pop": "_array_pop",
}

#: Dot-callable methods on X strings (``text.toUpperCase()``), keyed the same
#: way as ``_ARRAY_METHODS``.  Index arguments count Unicode code points,
#: matching the language's documented string-indexing behavior.
_STRING_METHODS: dict[str, str] = {
    "toUpperCase": "_string_to_upper_case",
    "toLowerCase": "_string_to_lower_case",
    "trim": "_string_trim",
    "strip": "_string_strip",
    "stripLeading": "_string_strip_leading",
    "stripTrailing": "_string_strip_trailing",
    "startsWith": "_string_starts_with",
    "endsWith": "_string_ends_with",
    "contains": "_string_contains",
    "indexOf": "_string_index_of",
    "lastIndexOf": "_string_last_index_of",
    "replace": "_string_replace",
    "replaceAll": "_string_replace_all",
    "split": "_string_split",
    "charAt": "_string_char_at",
    "codePointAt": "_string_code_point_at",
    "substring": "_string_substring",
    "slice": "_string_slice",
    "repeat": "_string_repeat",
    "padStart": "_string_pad_start",
    "padEnd": "_string_pad_end",
    "isEmpty": "_string_is_empty",
    "isBlank": "_string_is_blank",
    "toCharArray": "_string_to_char_array",
    "chars": "_string_chars",
    "codePoints": "_string_code_points",
    "format": "_string_format",
    "valueOf": "_string_value_of",
    "join": "_string_join",
    "lines": "_string_lines",
    "indent": "_string_indent",
    "transform": "_string_transform",
}


def _is_class_method(function: XFunction) -> bool:
    """True when *function* was declared inside a class body.

    Class members carry their owning class (and, once read off an instance,
    a bound ``this``), which is what separates a method from a plain function
    for ``typeOf`` and other diagnostics.
    """
    return function.parent_class is not None or function.bound_this is not None


