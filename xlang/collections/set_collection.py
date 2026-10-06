"""
Set collection implementation for X Language.

Provides a thin, typed wrapper around Python's built-in ``set`` type so that
the X language Set collection mirrors the interpreter's ``_set_*`` methods.
"""
from __future__ import annotations

from typing import Any


class SetClass:
    """X language Set class implementation.

    Wraps a Python ``set`` and exposes the same interface as the interpreter's
    ``_set_*`` methods.  Elements must be hashable (strings, numbers, booleans)
    because the underlying storage is a Python set.
    """

    def __init__(self, initial: Any = None) -> None:
        """Create a new Set, optionally pre-populated from an iterable.

        Args:
            initial: An optional iterable of hashable values to add on
                     construction.  Pass ``None`` (or omit) for an empty set.
        """
        if initial is not None:
            self.data: set[Any] = set(initial)
        else:
            self.data = set()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, value: Any) -> None:
        """Add *value* to the set; no-op when *value* is already present.

        Args:
            value: A hashable value to insert.
        """
        self.data.add(value)

    def remove(self, value: Any) -> bool:
        """Remove *value* from the set if present.

        Args:
            value: The value to remove.

        Returns:
            ``True`` when *value* was present and removed; ``False`` otherwise.
        """
        if value in self.data:
            self.data.discard(value)
            return True
        return False

    def clear(self) -> None:
        """Remove all elements from the set."""
        self.data.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def has(self, value: Any) -> bool:
        """Return ``True`` when *value* is a member of the set.

        Args:
            value: The value to test for membership.
        """
        return value in self.data

    def size(self) -> int:
        """Return the number of elements in the set."""
        return len(self.data)

    def isEmpty(self) -> bool:
        """Return ``True`` when the set contains no elements."""
        return len(self.data) == 0

    def toArray(self) -> list[Any]:
        """Return a sorted list of the set's elements.

        Elements are sorted by their string representation so the output is
        deterministic regardless of insertion order.
        """
        return sorted(self.data, key=str)

    # ------------------------------------------------------------------
    # Set algebra
    # ------------------------------------------------------------------

    def union(self, other: "SetClass") -> "SetClass":
        """Return a new set containing elements from both *self* and *other*.

        Args:
            other: Another SetClass to merge with.
        """
        result = SetClass()
        result.data = self.data | other.data
        return result

    def intersection(self, other: "SetClass") -> "SetClass":
        """Return a new set with elements present in both *self* and *other*.

        Args:
            other: Another SetClass to intersect with.
        """
        result = SetClass()
        result.data = self.data & other.data
        return result

    def difference(self, other: "SetClass") -> "SetClass":
        """Return a new set with elements in *self* that are absent in *other*.

        Args:
            other: Another SetClass whose elements should be excluded.
        """
        result = SetClass()
        result.data = self.data - other.data
        return result

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"Set({sorted(self.data, key=str)!r})"

    def __len__(self) -> int:
        """Support len(set_instance)."""
        return len(self.data)

    def __contains__(self, item: Any) -> bool:
        """Support ``item in set_instance``."""
        return item in self.data
