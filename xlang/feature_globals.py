"""Globals each optional feature provides at runtime.

Kept outside the interpreter so static analysis (the type checker behind
``x lint``) can reason about feature-provided names without importing the
interpreter: a name listed here resolves only while its feature is enabled
in x.toml, and otherwise raises ``Name 'x' is not defined because the
'feature' feature is disabled in x.toml`` at runtime.
"""

from __future__ import annotations

FEATURE_GLOBALS: dict[str, tuple[str, ...]] = {
    "collections": (
        "Collections",
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
        "ThreadSafeMap",
        "ThreadSafeSet",
    ),
    "threads": ("Thread",),
    "async": ("Async", "sleep"),
    "filesystem": ("FileSystem",),
    "object_literals": ("Object",),
    "decorators": ("trace",),
    "command_input": ("input",),
}
