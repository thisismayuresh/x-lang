"""
PriorityQueue implementation for X Language.

Uses Python's heapq module for O(log n) enqueue/dequeue operations.
The internal data structure is a dict::

    {"heap": list, "comparator": callable | None, "mode": "min" | "max"}

This matches the shape used by the interpreter's _priorityqueue_* methods.
"""
from __future__ import annotations

import heapq
from typing import Any, Callable


class _ComparatorItem:
    """Heap-orderable wrapper for values that use a custom comparator.

    Python's heapq calls ``__lt__`` to determine order; we delegate to the
    user-supplied comparator, which must return a negative number when its
    first argument should sort before its second.
    """

    def __init__(self, value: Any, comparator_fn: Callable[[Any, Any], int]) -> None:
        """Store the wrapped value and the comparator function."""
        self.value = value
        self.comparator_fn = comparator_fn

    def __lt__(self, other: "_ComparatorItem") -> bool:
        """Return True when self should be popped before other."""
        return self.comparator_fn(self.value, other.value) < 0

    def __le__(self, other: "_ComparatorItem") -> bool:
        """Return True when self sorts no later than other."""
        return self.comparator_fn(self.value, other.value) <= 0

    def __eq__(self, other: object) -> bool:
        """Equality by wrapped value."""
        if not isinstance(other, _ComparatorItem):
            return NotImplemented
        return self.value == other.value  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return f"_ComparatorItem({self.value!r})"


class PriorityQueueClass:
    """X language PriorityQueue implementation backed by Python's heapq.

    Supports three modes:

    * **min-heap (default)** — smallest value dequeued first.
    * **max-heap** — ``PriorityQueueClass('max')`` — largest dequeued first.
    * **custom comparator** — ``PriorityQueueClass(fn)`` where *fn(a, b)*
      returns a negative int when *a* should be dequeued before *b*.
    """

    def __init__(self, comparator: Any = None) -> None:
        """Initialise the queue.

        Args:
            comparator: ``'max'`` for a max-heap, a callable for a custom
                comparator, or ``None`` (default) for a min-heap.
        """
        self._heap: list[Any] = []
        self._mode: str = "min"
        self._comparator: Callable[[Any, Any], int] | None = None

        if comparator == "max":
            self._mode = "max"
        elif callable(comparator):
            self._comparator = comparator

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def enqueue(self, value: Any) -> None:
        """Add *value* to the heap in O(log n) time."""
        if self._comparator is not None:
            heapq.heappush(self._heap, _ComparatorItem(value, self._comparator))
        elif self._mode == "max":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                heapq.heappush(self._heap, (-value, value))
            else:
                def _reverse(a: Any, b: Any) -> int:
                    return -1 if a > b else (1 if a < b else 0)
                heapq.heappush(self._heap, _ComparatorItem(value, _reverse))
        else:
            heapq.heappush(self._heap, value)

    def dequeue(self) -> Any:
        """Remove and return the highest-priority element in O(log n) time.

        Raises:
            Exception: When the queue is empty.
        """
        if not self._heap:
            raise Exception("PriorityQueue.dequeue: queue is empty")
        return self._unwrap(heapq.heappop(self._heap))

    def clear(self) -> None:
        """Remove all elements from the queue."""
        self._heap.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def peek(self) -> Any:
        """Return the highest-priority element without removing it.

        Raises:
            Exception: When the queue is empty.
        """
        if not self._heap:
            raise Exception("PriorityQueue.peek: queue is empty")
        return self._unwrap(self._heap[0])

    def size(self) -> int:
        """Return the number of elements in the queue."""
        return len(self._heap)

    def isEmpty(self) -> bool:
        """Return True when the queue is empty."""
        return len(self._heap) == 0

    def toArray(self) -> list[Any]:
        """Return a sorted copy of all elements without modifying the queue."""
        return [self._unwrap(item) for item in heapq.nsmallest(len(self._heap), self._heap)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _unwrap(self, item: Any) -> Any:
        """Extract the original value from a heap item."""
        if isinstance(item, _ComparatorItem):
            return item.value
        if isinstance(item, tuple) and len(item) == 2:
            # max-heap stores (-value, value)
            return item[1]
        return item
