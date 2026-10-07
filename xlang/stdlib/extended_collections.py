"""Extended collections for the X language: ordered maps/sets, thread-safe
wrappers, and JSON round-trip serialization.

Structures (plain Python classes with explicit APIs; see class docstrings):

* ``TreeMap``       -- sorted-by-key map backed by a ``dict`` plus a
  ``bisect``-maintained sorted key list
* ``TreeSet``       -- sorted unique set, a view over ``TreeMap``
* ``LinkedHashMap`` -- insertion-ordered map with Python ``dict`` order semantics
* ``LRUCache``      -- fixed-capacity cache built on ``LinkedHashMap`` with
  least-recently-used eviction
* ``ThreadSafeMap`` / ``ThreadSafeSet`` -- ``threading.RLock``-guarded wrappers
  with snapshot iteration and a ``locked()`` context manager for compound
  operations

Unlike ``HashMap.get`` (which returns null), map ``get``/``remove`` raise
``RuntimeErrorX`` when a key or element is absent; every arity/type violation
also raises ``RuntimeErrorX`` with a ``Type.method``-qualified message.
``size``/``is_empty``/``capacity`` are read-only properties; everything else is
a method. Iteration (``iterator()``, ``__iter__``, snapshot accessors) never
observes concurrent mutation.

Serialization: module-level :func:`to_json` / :func:`from_json` round-trip every
structure above plus plain dicts, lists, sets and scalars, preserving the
concrete type through a ``"__xtype__"`` tag::

    {"__xtype__": "TreeMap", "entries": [[1, "a"], [3, "c"]]}

Each structure also has ``to_json()`` / ``classmethod from_json(text)``.

Interpreter integration: :func:`build_namespaces` returns
``{structure name: {method name: BuiltinFunction}}`` shaped exactly like
``xlang.interpreter._hashmap_members()``, built only from ``xlang.runtime`` --
this module never imports the interpreter. Register it with one edit inside
``Interpreter._install_builtins``::

    from .stdlib.extended_collections import build_namespaces
    for name, members in build_namespaces().items():
        namespace = self._make_collection_ns(name, members)
        collections_namespace.define(name, namespace)
        self.globals.define(name, namespace)

``_make_collection_ns`` is what makes ``new TreeMap()`` and dot-calls work; the
raw tables also support the functional style ``TreeMap.put(map, key, value)``.
X-facing method names are camelCase (``contains_key`` -> ``containsKey``,
``isEmpty``, ``toArray`` to match ``Set.toArray``, ``toJSON``/``fromJSON``);
``create`` is the constructor entry point, mirroring ``HashMap.create``.
"""

from __future__ import annotations

import json
import threading
from bisect import bisect_left
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from ..runtime import BuiltinFunction, RuntimeErrorX

_TYPE_KEY = "__xtype__"
_DEFAULT_CACHE_CAPACITY = 16

_UNORDERED_KEY_ERROR = "keys must be hashable and mutually comparable"
_UNHASHABLE_KEY_ERROR = "keys must be hashable"


def _pairs_from(source: Any, label: str) -> list[tuple[Any, Any]]:
    """Normalise a dict, a structure, or an iterable of pairs into tuples."""
    if isinstance(source, dict):
        return list(source.items())
    if isinstance(source, TreeMap):
        return source.items()
    if isinstance(source, LinkedHashMap):
        return source.entries()
    if isinstance(source, (str, bytes)) or not hasattr(source, "__iter__"):
        raise RuntimeErrorX(
            f"{label} initial entries must be a dict or an iterable of [key, value] pairs"
        )
    pairs: list[tuple[Any, Any]] = []
    for entry in source:
        if (
            isinstance(entry, (str, bytes))
            or not isinstance(entry, (list, tuple))
            or len(entry) != 2
        ):
            raise RuntimeErrorX(f"{label} initial entries must be [key, value] pairs")
        pairs.append((entry[0], entry[1]))
    return pairs


class TreeMap:
    """Sorted-by-key map: ``put``/``get``/``remove``/``contains_key``/``clear``,
    ``first_key()``/``last_key()``, ``keys_in_order()``/``values_in_order()``/
    ``items()`` (all in ascending key order), ``size``/``is_empty`` properties,
    ``iterator()`` over ``[key, value]`` pairs, and ``to_json()``/``from_json()``.

    Keys must be hashable and mutually comparable. ``get``/``remove`` raise
    ``RuntimeErrorX`` for absent keys; ``first_key()``/``last_key()`` raise on
    an empty map.
    """

    def __init__(
        self,
        entries: Mapping[Any, Any] | Iterable[tuple[Any, Any]] | None = None,
    ) -> None:
        self._data: dict[Any, Any] = {}
        self._keys: list[Any] = []
        if entries is not None:
            for key, value in _pairs_from(entries, "TreeMap"):
                self.put(key, value)

    def put(self, key: Any, value: Any) -> None:
        """Insert or update *key* (an existing key keeps its sorted position)."""
        index, present = self._locate(key)
        try:
            self._data[key] = value
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNHASHABLE_KEY_ERROR}: {error}") from error
        if not present:
            self._keys.insert(index, key)

    def get(self, key: Any) -> Any:
        """Return the value for *key*; raise ``RuntimeErrorX`` when absent."""
        try:
            return self._data[key]
        except KeyError:
            raise RuntimeErrorX(f"TreeMap.get: key {key!r} not found") from None
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNORDERED_KEY_ERROR}: {error}") from error

    def remove(self, key: Any) -> Any:
        """Remove *key* and return its value; raise ``RuntimeErrorX`` when absent."""
        index, present = self._locate(key)
        if not present:
            raise RuntimeErrorX(f"TreeMap.remove: key {key!r} not found")
        try:
            value = self._data.pop(key)
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNHASHABLE_KEY_ERROR}: {error}") from error
        self._keys.pop(index)
        return value

    def contains_key(self, key: Any) -> bool:
        """Return whether *key* is present."""
        try:
            return key in self._data
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNHASHABLE_KEY_ERROR}: {error}") from error

    def first_key(self) -> Any:
        """Return the smallest key; raise ``RuntimeErrorX`` when empty."""
        if not self._keys:
            raise RuntimeErrorX("TreeMap.first_key: map is empty")
        return self._keys[0]

    def last_key(self) -> Any:
        """Return the largest key; raise ``RuntimeErrorX`` when empty."""
        if not self._keys:
            raise RuntimeErrorX("TreeMap.last_key: map is empty")
        return self._keys[-1]

    def keys_in_order(self) -> list[Any]:
        """Return the keys in ascending order."""
        return list(self._keys)

    def values_in_order(self) -> list[Any]:
        """Return the values, ordered by their keys."""
        return [self._data[key] for key in self._keys]

    def items(self) -> list[tuple[Any, Any]]:
        """Return ``(key, value)`` pairs in ascending key order."""
        return [(key, self._data[key]) for key in self._keys]

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def is_empty(self) -> bool:
        return not self._data

    def clear(self) -> None:
        """Remove every entry."""
        self._data.clear()
        self._keys.clear()

    def iterator(self) -> Iterator[tuple[Any, Any]]:
        """Return a snapshot iterator over ``[key, value]`` pairs in order."""
        return iter(self.items())

    def _locate(self, key: Any) -> tuple[int, bool]:
        """Return ``(insertion index, present)`` for *key* in the sorted key list."""
        try:
            index = bisect_left(self._keys, key)
            return index, index < len(self._keys) and self._keys[index] == key
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNORDERED_KEY_ERROR}: {error}") from error

    def __iter__(self) -> Iterator[Any]:
        return iter(self.keys_in_order())

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: Any) -> bool:
        return self.contains_key(key)

    def __repr__(self) -> str:
        return f"TreeMap({dict(self.items())!r})"

    def to_json(self) -> str:
        return _dump(self)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return _expect_type(cls, _loads(text), f"{cls.__name__}.from_json")


class TreeSet:
    """Sorted unique set: ``add``/``remove``/``contains``/``clear``, ``first()``
    /``last()``, ``to_list()`` (ascending), ``size``/``is_empty`` properties,
    ``iterator()`` over elements, and ``to_json()``/``from_json()``.

    Elements must be hashable and mutually comparable. ``remove`` raises
    ``RuntimeErrorX`` for absent elements; ``first()``/``last()`` raise on an
    empty set.
    """

    def __init__(self, elements: Iterable[Any] | None = None) -> None:
        self._map = TreeMap()
        if elements is not None:
            if not hasattr(elements, "__iter__"):
                raise RuntimeErrorX("TreeSet initial value must be iterable")
            for element in elements:
                self.add(element)

    def add(self, value: Any) -> None:
        """Insert *value* (no-op when already present)."""
        self._map.put(value, True)

    def remove(self, value: Any) -> None:
        """Remove *value*; raise ``RuntimeErrorX`` when absent."""
        if not self._map.contains_key(value):
            raise RuntimeErrorX(f"TreeSet.remove: element {value!r} is not present")
        self._map.remove(value)

    def contains(self, value: Any) -> bool:
        """Return whether *value* is a member."""
        return self._map.contains_key(value)

    def first(self) -> Any:
        """Return the smallest element; raise ``RuntimeErrorX`` when empty."""
        if self._map.is_empty:
            raise RuntimeErrorX("TreeSet.first: set is empty")
        return self._map.first_key()

    def last(self) -> Any:
        """Return the largest element; raise ``RuntimeErrorX`` when empty."""
        if self._map.is_empty:
            raise RuntimeErrorX("TreeSet.last: set is empty")
        return self._map.last_key()

    @property
    def size(self) -> int:
        return self._map.size

    @property
    def is_empty(self) -> bool:
        return self._map.is_empty

    def clear(self) -> None:
        """Remove every element."""
        self._map.clear()

    def to_list(self) -> list[Any]:
        """Return the elements in ascending order."""
        return self._map.keys_in_order()

    def iterator(self) -> Iterator[Any]:
        """Return a snapshot iterator over the elements in ascending order."""
        return iter(self.to_list())

    def __iter__(self) -> Iterator[Any]:
        return iter(self.to_list())

    def __len__(self) -> int:
        return self._map.size

    def __contains__(self, value: Any) -> bool:
        return self.contains(value)

    def __repr__(self) -> str:
        return f"TreeSet({self.to_list()!r})"

    def to_json(self) -> str:
        return _dump(self)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return _expect_type(cls, _loads(text), f"{cls.__name__}.from_json")


class LinkedHashMap:
    """Insertion-ordered map with Python ``dict`` semantics: ``put``/``get``/
    ``remove``/``contains_key``/``clear``, ``keys()``/``values()``/``entries()``
    in insertion order, ``size``/``is_empty`` properties, ``iterator()`` over
    ``[key, value]`` pairs, and ``to_json()``/``from_json()``.

    Re-``put``-ing an existing key updates the value but keeps its position;
    ``remove`` followed by ``put`` moves the key to the end. ``get``/``remove``
    raise ``RuntimeErrorX`` for absent keys.
    """

    def __init__(
        self,
        entries: Mapping[Any, Any] | Iterable[tuple[Any, Any]] | None = None,
    ) -> None:
        self._data: dict[Any, Any] = {}
        if entries is not None:
            for key, value in _pairs_from(entries, "LinkedHashMap"):
                self.put(key, value)

    def put(self, key: Any, value: Any) -> None:
        """Insert or update *key*, preserving insertion order for existing keys."""
        try:
            self._data[key] = value
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNHASHABLE_KEY_ERROR}: {error}") from error

    def get(self, key: Any) -> Any:
        """Return the value for *key*; raise ``RuntimeErrorX`` when absent."""
        try:
            return self._data[key]
        except KeyError:
            raise RuntimeErrorX(f"LinkedHashMap.get: key {key!r} not found") from None
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNHASHABLE_KEY_ERROR}: {error}") from error

    def remove(self, key: Any) -> Any:
        """Remove *key* and return its value; raise ``RuntimeErrorX`` when absent."""
        try:
            return self._data.pop(key)
        except KeyError:
            raise RuntimeErrorX(f"LinkedHashMap.remove: key {key!r} not found") from None
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNHASHABLE_KEY_ERROR}: {error}") from error

    def contains_key(self, key: Any) -> bool:
        """Return whether *key* is present."""
        try:
            return key in self._data
        except TypeError as error:
            raise RuntimeErrorX(f"{_UNHASHABLE_KEY_ERROR}: {error}") from error

    def keys(self) -> list[Any]:
        """Return the keys in insertion order."""
        return list(self._data.keys())

    def values(self) -> list[Any]:
        """Return the values in insertion order."""
        return list(self._data.values())

    def entries(self) -> list[tuple[Any, Any]]:
        """Return ``(key, value)`` pairs in insertion order."""
        return list(self._data.items())

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def is_empty(self) -> bool:
        return not self._data

    def clear(self) -> None:
        """Remove every entry."""
        self._data.clear()

    def iterator(self) -> Iterator[tuple[Any, Any]]:
        """Return a snapshot iterator over ``[key, value]`` pairs in order."""
        return iter(self.entries())

    def __iter__(self) -> Iterator[Any]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: Any) -> bool:
        return self.contains_key(key)

    def __repr__(self) -> str:
        return f"LinkedHashMap({dict(self.entries())!r})"

    def to_json(self) -> str:
        return _dump(self)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return _expect_type(cls, _loads(text), f"{cls.__name__}.from_json")


class LRUCache:
    """Fixed-capacity cache with least-recently-used eviction, built on
    :class:`LinkedHashMap`: ``get``/``put``/``remove``/``contains_key``/``clear``,
    ``capacity``/``size``/``is_empty`` properties, ``keys_in_order()`` (least
    recently used first), ``iterator()`` over pairs in that order, and
    ``to_json()``/``from_json()``.

    A ``put`` that would exceed ``capacity`` evicts the least recently used key;
    both ``get`` and ``put`` mark a key most recently used. ``get``/``remove``
    raise ``RuntimeErrorX`` for absent keys.
    """

    def __init__(self, capacity: int = _DEFAULT_CACHE_CAPACITY) -> None:
        if (
            not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or capacity < 1
        ):
            raise RuntimeErrorX("LRUCache capacity must be a positive integer")
        self._capacity = capacity
        self._map = LinkedHashMap()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def size(self) -> int:
        return self._map.size

    @property
    def is_empty(self) -> bool:
        return self._map.is_empty

    def get(self, key: Any) -> Any:
        """Return the value for *key* and mark it most recently used; raise
        ``RuntimeErrorX`` when absent."""
        if not self._map.contains_key(key):
            raise RuntimeErrorX(f"LRUCache.get: key {key!r} not found")
        value = self._map.remove(key)
        self._map.put(key, value)
        return value

    def put(self, key: Any, value: Any) -> None:
        """Insert or update *key* as most recently used, evicting the least
        recently used key when at capacity."""
        if self._map.contains_key(key):
            self._map.remove(key)
        elif self._map.size >= self._capacity:
            self._map.remove(self._map.keys()[0])
        self._map.put(key, value)

    def remove(self, key: Any) -> Any:
        """Remove *key* and return its value; raise ``RuntimeErrorX`` when absent."""
        if not self._map.contains_key(key):
            raise RuntimeErrorX(f"LRUCache.remove: key {key!r} not found")
        return self._map.remove(key)

    def contains_key(self, key: Any) -> bool:
        """Return whether *key* is cached."""
        return self._map.contains_key(key)

    def clear(self) -> None:
        """Remove every cached entry."""
        self._map.clear()

    def keys_in_order(self) -> list[Any]:
        """Return cached keys from least to most recently used."""
        return self._map.keys()

    def iterator(self) -> Iterator[tuple[Any, Any]]:
        """Return a snapshot iterator over pairs, least recently used first."""
        return self._map.iterator()

    def __iter__(self) -> Iterator[Any]:
        return iter(self.keys_in_order())

    def __len__(self) -> int:
        return self._map.size

    def __contains__(self, key: Any) -> bool:
        return self.contains_key(key)

    def __repr__(self) -> str:
        return f"LRUCache(capacity={self._capacity}, entries={self._map.entries()!r})"

    def to_json(self) -> str:
        return _dump(self)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return _expect_type(cls, _loads(text), f"{cls.__name__}.from_json")


class ThreadSafeMap:
    """``threading.RLock``-guarded wrapper around a :class:`TreeMap` (default)
    or :class:`LinkedHashMap`: ``put``/``get``/``remove``/``contains_key``/
    ``clear``, ``size``/``is_empty``/``kind`` properties, ``entries()`` and
    ``iterator()`` returning lock-held snapshots, plus ``to_json()``/
    ``from_json()``.

    ``locked()`` is a context manager yielding the wrapped structure so
    compound operations (and type-specific APIs such as ``TreeMap.first_key``)
    run under the lock; the lock is reentrant. Errors from the wrapped
    structure propagate unchanged.
    """

    def __init__(self, inner: TreeMap | LinkedHashMap | None = None) -> None:
        if inner is not None and not isinstance(inner, (TreeMap, LinkedHashMap)):
            raise RuntimeErrorX("ThreadSafeMap expects a TreeMap or LinkedHashMap to wrap")
        self._inner: TreeMap | LinkedHashMap = inner if inner is not None else TreeMap()
        self._lock = threading.RLock()

    @property
    def kind(self) -> str:
        """``"tree"`` or ``"linked"`` -- which structure is wrapped."""
        with self._lock:
            return "tree" if isinstance(self._inner, TreeMap) else "linked"

    @property
    def size(self) -> int:
        with self._lock:
            return self._inner.size

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return self._inner.is_empty

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            self._inner.put(key, value)

    def get(self, key: Any) -> Any:
        with self._lock:
            return self._inner.get(key)

    def remove(self, key: Any) -> Any:
        with self._lock:
            return self._inner.remove(key)

    def contains_key(self, key: Any) -> bool:
        with self._lock:
            return self._inner.contains_key(key)

    def clear(self) -> None:
        with self._lock:
            self._inner.clear()

    def entries(self) -> list[tuple[Any, Any]]:
        """Snapshot of ``[key, value]`` pairs in the wrapped map's order."""
        with self._lock:
            return list(self._inner.iterator())

    def iterator(self) -> Iterator[tuple[Any, Any]]:
        """Snapshot iterator over ``[key, value]`` pairs."""
        return iter(self.entries())

    @contextmanager
    def locked(self) -> Iterator[TreeMap | LinkedHashMap]:
        """Hold the lock while yielding the wrapped structure."""
        with self._lock:
            yield self._inner

    def __iter__(self) -> Iterator[Any]:
        return iter([key for key, _ in self.entries()])

    def __len__(self) -> int:
        return self.size

    def __contains__(self, key: Any) -> bool:
        return self.contains_key(key)

    def __repr__(self) -> str:
        with self._lock:
            return f"ThreadSafeMap({self._inner!r})"

    def to_json(self) -> str:
        return _dump(self)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return _expect_type(cls, _loads(text), f"{cls.__name__}.from_json")


class ThreadSafeSet:
    """``threading.RLock``-guarded wrapper around a :class:`TreeSet`:
    ``add``/``remove``/``contains``/``clear``, ``size``/``is_empty`` properties,
    ``to_list()``/``iterator()`` returning lock-held snapshots, and ``to_json()``
    /``from_json()``. ``locked()`` is a reentrant context manager yielding the
    wrapped set for compound operations; to wrap an existing plain set, build
    ``ThreadSafeSet(TreeSet(existing))`` first.
    """

    def __init__(self, inner: TreeSet | None = None) -> None:
        if inner is not None and not isinstance(inner, TreeSet):
            raise RuntimeErrorX("ThreadSafeSet expects a TreeSet to wrap")
        self._inner: TreeSet = inner if inner is not None else TreeSet()
        self._lock = threading.RLock()

    @property
    def size(self) -> int:
        with self._lock:
            return self._inner.size

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return self._inner.is_empty

    def add(self, value: Any) -> None:
        with self._lock:
            self._inner.add(value)

    def remove(self, value: Any) -> None:
        with self._lock:
            self._inner.remove(value)

    def contains(self, value: Any) -> bool:
        with self._lock:
            return self._inner.contains(value)

    def clear(self) -> None:
        with self._lock:
            self._inner.clear()

    def to_list(self) -> list[Any]:
        """Snapshot of the elements in ascending order."""
        with self._lock:
            return self._inner.to_list()

    def iterator(self) -> Iterator[Any]:
        """Snapshot iterator over the elements in ascending order."""
        return iter(self.to_list())

    @contextmanager
    def locked(self) -> Iterator[TreeSet]:
        """Hold the lock while yielding the wrapped set."""
        with self._lock:
            yield self._inner

    def __iter__(self) -> Iterator[Any]:
        return self.iterator()

    def __len__(self) -> int:
        return self.size

    def __contains__(self, value: Any) -> bool:
        return self.contains(value)

    def __repr__(self) -> str:
        with self._lock:
            return f"ThreadSafeSet({self._inner!r})"

    def to_json(self) -> str:
        return _dump(self)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return _expect_type(cls, _loads(text), f"{cls.__name__}.from_json")


def _dump(value: Any) -> str:
    return json.dumps(_encode(value), ensure_ascii=False)


def _loads(text: str) -> Any:
    if not isinstance(text, str):
        raise RuntimeErrorX("from_json expects a JSON string")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeErrorX(f"from_json: invalid JSON: {error}") from error
    return _decode(raw)


def to_json(value: Any) -> str:
    """Serialise *value* -- any structure here, or a plain dict/list/set/scalar
    -- to JSON, preserving concrete structure types via ``"__xtype__"`` tags."""
    return _dump(value)


def from_json(text: str) -> Any:
    """Parse JSON produced by :func:`to_json`, restoring structure types."""
    return _loads(text)


def _expect_type(cls: type, value: Any, context: str) -> Any:
    if not isinstance(value, cls):
        raise RuntimeErrorX(
            f"{context}: expected a {cls.__name__} document, "
            f"got {type(value).__name__}"
        )
    return value


def _encode(value: Any) -> Any:
    if isinstance(value, TreeMap):
        return {
            _TYPE_KEY: "TreeMap",
            "entries": [[_encode(k), _encode(v)] for k, v in value.items()],
        }
    if isinstance(value, TreeSet):
        return {_TYPE_KEY: "TreeSet", "elements": [_encode(v) for v in value.to_list()]}
    if isinstance(value, LinkedHashMap):
        return {
            _TYPE_KEY: "LinkedHashMap",
            "entries": [[_encode(k), _encode(v)] for k, v in value.entries()],
        }
    if isinstance(value, LRUCache):
        return {
            _TYPE_KEY: "LRUCache",
            "capacity": value.capacity,
            "entries": [[_encode(k), _encode(v)] for k, v in value.iterator()],
        }
    if isinstance(value, ThreadSafeMap):
        return {
            _TYPE_KEY: "ThreadSafeMap",
            "kind": value.kind,
            "entries": [[_encode(k), _encode(v)] for k, v in value.entries()],
        }
    if isinstance(value, ThreadSafeSet):
        return {
            _TYPE_KEY: "ThreadSafeSet",
            "elements": [_encode(v) for v in value.to_list()],
        }
    if isinstance(value, dict):
        if _TYPE_KEY in value or any(not isinstance(k, str) for k in value):
            return {
                _TYPE_KEY: "dict",
                "entries": [[_encode(k), _encode(v)] for k, v in value.items()],
            }
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if isinstance(value, set):
        return {
            _TYPE_KEY: "set",
            "elements": [_encode(v) for v in sorted(value, key=str)],
        }
    if isinstance(value, (str, int, float)) or value is None:
        return value
    raise RuntimeErrorX(
        f"to_json cannot serialise values of type {type(value).__name__}"
    )


def _field(raw: dict, key: str, tag: str) -> Any:
    if key not in raw:
        raise RuntimeErrorX(f"from_json: {tag} document is missing {key!r}")
    return raw[key]


def _decode_pairs(raw: dict, tag: str) -> list[tuple[Any, Any]]:
    entries = _field(raw, "entries", tag)
    if not isinstance(entries, (list, tuple)):
        raise RuntimeErrorX(
            f"from_json: {tag} 'entries' must be a list of [key, value] pairs"
        )
    pairs: list[tuple[Any, Any]] = []
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise RuntimeErrorX(
                f"from_json: {tag} 'entries' must be a list of [key, value] pairs"
            )
        pairs.append((_decode(entry[0]), _decode(entry[1])))
    return pairs


def _decode_elements(raw: dict, tag: str) -> list[Any]:
    elements = _field(raw, "elements", tag)
    if not isinstance(elements, (list, tuple)):
        raise RuntimeErrorX(f"from_json: {tag} 'elements' must be a list")
    return [_decode(item) for item in elements]


def _decode(raw: Any) -> Any:
    if isinstance(raw, list):
        return [_decode(item) for item in raw]
    if not isinstance(raw, dict):
        return raw
    tag = raw.get(_TYPE_KEY)
    if tag is None:
        return {key: _decode(item) for key, item in raw.items()}
    if not isinstance(tag, str):
        raise RuntimeErrorX(f"from_json: unknown type tag {tag!r}")
    if tag == "TreeMap":
        return TreeMap(_decode_pairs(raw, tag))
    if tag == "TreeSet":
        return TreeSet(_decode_elements(raw, tag))
    if tag == "LinkedHashMap":
        return LinkedHashMap(_decode_pairs(raw, tag))
    if tag == "LRUCache":
        capacity = _field(raw, "capacity", tag)
        cache = LRUCache(capacity)
        for key, value in _decode_pairs(raw, tag):
            cache.put(key, value)
        return cache
    if tag == "ThreadSafeMap":
        kind = _field(raw, "kind", tag)
        if kind == "tree":
            wrapper: ThreadSafeMap = ThreadSafeMap(TreeMap())
        elif kind == "linked":
            wrapper = ThreadSafeMap(LinkedHashMap())
        else:
            raise RuntimeErrorX(f"from_json: unknown ThreadSafeMap kind {kind!r}")
        for key, value in _decode_pairs(raw, tag):
            wrapper.put(key, value)
        return wrapper
    if tag == "ThreadSafeSet":
        wrapper_set = ThreadSafeSet()
        for element in _decode_elements(raw, tag):
            wrapper_set.add(element)
        return wrapper_set
    if tag == "dict":
        try:
            return dict(_decode_pairs(raw, tag))
        except TypeError as error:
            raise RuntimeErrorX(f"from_json: dict keys must be hashable: {error}") from error
    if tag == "set":
        try:
            return set(_decode_elements(raw, tag))
        except TypeError as error:
            raise RuntimeErrorX(
                f"from_json: set elements must be hashable: {error}"
            ) from error
    raise RuntimeErrorX(f"from_json: unknown type tag {tag!r}")


def _check_arity(name: str, arguments: list[Any], expected: int) -> None:
    """Raise ``RuntimeErrorX`` when a builtin receives the wrong argument count."""
    if len(arguments) != expected:
        raise RuntimeErrorX(
            f"{name} expects {expected} argument(s), got {len(arguments)}"
        )


def _expect_receiver(name: str, value: Any, expected: type) -> Any:
    """Return *value* when it is an instance of *expected*, else raise."""
    if not isinstance(value, expected):
        raise RuntimeErrorX(f"{name} expects a {expected.__name__} instance")
    return value


def _bind(
    type_name: str,
    method_name: str,
    expected: type,
    arity: int,
    call: Callable[[Any, list[Any]], Any],
) -> BuiltinFunction:
    """Build a method-table entry: check *arity* (receiver included), check the
    receiver, then invoke ``call(receiver, extra arguments)``."""
    qualified = f"{type_name}.{method_name}"

    def dispatch(arguments: list[Any]) -> Any:
        _check_arity(qualified, arguments, arity)
        receiver = _expect_receiver(qualified, arguments[0], expected)
        return call(receiver, arguments[1:])

    return BuiltinFunction(qualified, dispatch)


def _from_json_entry(type_name: str, cls: type) -> BuiltinFunction:
    qualified = f"{type_name}.fromJSON"

    def decode(arguments: list[Any]) -> Any:
        _check_arity(qualified, arguments, 1)
        if not isinstance(arguments[0], str):
            raise RuntimeErrorX(f"{qualified} expects a JSON string")
        return cls.from_json(arguments[0])

    return BuiltinFunction(qualified, decode)


def _treemap_create(arguments: list[Any]) -> TreeMap:
    if len(arguments) > 1:
        raise RuntimeErrorX("TreeMap.create accepts at most one argument (initial entries)")
    return TreeMap(arguments[0]) if arguments else TreeMap()


def _treeset_create(arguments: list[Any]) -> TreeSet:
    if len(arguments) > 1:
        raise RuntimeErrorX("TreeSet.create accepts at most one argument (initial elements)")
    return TreeSet(arguments[0]) if arguments else TreeSet()


def _linked_hash_map_create(arguments: list[Any]) -> LinkedHashMap:
    if len(arguments) > 1:
        raise RuntimeErrorX(
            "LinkedHashMap.create accepts at most one argument (initial entries)"
        )
    return LinkedHashMap(arguments[0]) if arguments else LinkedHashMap()


def _lru_cache_create(arguments: list[Any]) -> LRUCache:
    if len(arguments) > 1:
        raise RuntimeErrorX("LRUCache.create accepts at most one argument (capacity)")
    return LRUCache(arguments[0]) if arguments else LRUCache()


def _thread_safe_map_create(arguments: list[Any]) -> ThreadSafeMap:
    if len(arguments) > 1:
        raise RuntimeErrorX(
            "ThreadSafeMap.create accepts at most one argument "
            "('tree', 'linked', or a map to wrap)"
        )
    if not arguments or arguments[0] is None:
        return ThreadSafeMap()
    inner = arguments[0]
    if isinstance(inner, (TreeMap, LinkedHashMap)):
        return ThreadSafeMap(inner)
    if inner == "tree":
        return ThreadSafeMap(TreeMap())
    if inner == "linked":
        return ThreadSafeMap(LinkedHashMap())
    raise RuntimeErrorX(
        "ThreadSafeMap.create argument must be 'tree', 'linked', or a map to wrap"
    )


def _thread_safe_set_create(arguments: list[Any]) -> ThreadSafeSet:
    if len(arguments) > 1:
        raise RuntimeErrorX("ThreadSafeSet.create accepts at most one argument (a TreeSet to wrap)")
    return ThreadSafeSet(arguments[0]) if arguments else ThreadSafeSet()


def _treemap_members() -> dict[str, BuiltinFunction]:
    """Method table for TreeMap (first argument is the map)."""
    return {
        "create": BuiltinFunction("TreeMap.create", _treemap_create),
        "put": _bind("TreeMap", "put", TreeMap, 3, lambda m, a: m.put(*a)),
        "get": _bind("TreeMap", "get", TreeMap, 2, lambda m, a: m.get(*a)),
        "remove": _bind("TreeMap", "remove", TreeMap, 2, lambda m, a: m.remove(*a)),
        "containsKey": _bind("TreeMap", "containsKey", TreeMap, 2, lambda m, a: m.contains_key(*a)),
        "firstKey": _bind("TreeMap", "firstKey", TreeMap, 1, lambda m, a: m.first_key()),
        "lastKey": _bind("TreeMap", "lastKey", TreeMap, 1, lambda m, a: m.last_key()),
        "keysInOrder": _bind("TreeMap", "keysInOrder", TreeMap, 1, lambda m, a: m.keys_in_order()),
        "valuesInOrder": _bind("TreeMap", "valuesInOrder", TreeMap, 1, lambda m, a: m.values_in_order()),
        "items": _bind("TreeMap", "items", TreeMap, 1, lambda m, a: m.items()),
        "size": _bind("TreeMap", "size", TreeMap, 1, lambda m, a: m.size),
        "isEmpty": _bind("TreeMap", "isEmpty", TreeMap, 1, lambda m, a: m.is_empty),
        "clear": _bind("TreeMap", "clear", TreeMap, 1, lambda m, a: m.clear()),
        "iterator": _bind("TreeMap", "iterator", TreeMap, 1, lambda m, a: m.iterator()),
        "toJSON": _bind("TreeMap", "toJSON", TreeMap, 1, lambda m, a: m.to_json()),
        "fromJSON": _from_json_entry("TreeMap", TreeMap),
    }


def _treeset_members() -> dict[str, BuiltinFunction]:
    """Method table for TreeSet (first argument is the set)."""
    return {
        "create": BuiltinFunction("TreeSet.create", _treeset_create),
        "add": _bind("TreeSet", "add", TreeSet, 2, lambda s, a: s.add(*a)),
        "remove": _bind("TreeSet", "remove", TreeSet, 2, lambda s, a: s.remove(*a)),
        "contains": _bind("TreeSet", "contains", TreeSet, 2, lambda s, a: s.contains(*a)),
        "first": _bind("TreeSet", "first", TreeSet, 1, lambda s, a: s.first()),
        "last": _bind("TreeSet", "last", TreeSet, 1, lambda s, a: s.last()),
        "size": _bind("TreeSet", "size", TreeSet, 1, lambda s, a: s.size),
        "isEmpty": _bind("TreeSet", "isEmpty", TreeSet, 1, lambda s, a: s.is_empty),
        "clear": _bind("TreeSet", "clear", TreeSet, 1, lambda s, a: s.clear()),
        "toArray": _bind("TreeSet", "toArray", TreeSet, 1, lambda s, a: s.to_list()),
        "iterator": _bind("TreeSet", "iterator", TreeSet, 1, lambda s, a: s.iterator()),
        "toJSON": _bind("TreeSet", "toJSON", TreeSet, 1, lambda s, a: s.to_json()),
        "fromJSON": _from_json_entry("TreeSet", TreeSet),
    }


def _linked_hash_map_members() -> dict[str, BuiltinFunction]:
    """Method table for LinkedHashMap (first argument is the map)."""
    return {
        "create": BuiltinFunction("LinkedHashMap.create", _linked_hash_map_create),
        "put": _bind("LinkedHashMap", "put", LinkedHashMap, 3, lambda m, a: m.put(*a)),
        "get": _bind("LinkedHashMap", "get", LinkedHashMap, 2, lambda m, a: m.get(*a)),
        "remove": _bind("LinkedHashMap", "remove", LinkedHashMap, 2, lambda m, a: m.remove(*a)),
        "containsKey": _bind("LinkedHashMap", "containsKey", LinkedHashMap, 2, lambda m, a: m.contains_key(*a)),
        "keys": _bind("LinkedHashMap", "keys", LinkedHashMap, 1, lambda m, a: m.keys()),
        "values": _bind("LinkedHashMap", "values", LinkedHashMap, 1, lambda m, a: m.values()),
        "entries": _bind("LinkedHashMap", "entries", LinkedHashMap, 1, lambda m, a: m.entries()),
        "size": _bind("LinkedHashMap", "size", LinkedHashMap, 1, lambda m, a: m.size),
        "isEmpty": _bind("LinkedHashMap", "isEmpty", LinkedHashMap, 1, lambda m, a: m.is_empty),
        "clear": _bind("LinkedHashMap", "clear", LinkedHashMap, 1, lambda m, a: m.clear()),
        "iterator": _bind("LinkedHashMap", "iterator", LinkedHashMap, 1, lambda m, a: m.iterator()),
        "toJSON": _bind("LinkedHashMap", "toJSON", LinkedHashMap, 1, lambda m, a: m.to_json()),
        "fromJSON": _from_json_entry("LinkedHashMap", LinkedHashMap),
    }


def _lru_cache_members() -> dict[str, BuiltinFunction]:
    """Method table for LRUCache (first argument is the cache)."""
    return {
        "create": BuiltinFunction("LRUCache.create", _lru_cache_create),
        "get": _bind("LRUCache", "get", LRUCache, 2, lambda c, a: c.get(*a)),
        "put": _bind("LRUCache", "put", LRUCache, 3, lambda c, a: c.put(*a)),
        "remove": _bind("LRUCache", "remove", LRUCache, 2, lambda c, a: c.remove(*a)),
        "containsKey": _bind("LRUCache", "containsKey", LRUCache, 2, lambda c, a: c.contains_key(*a)),
        "size": _bind("LRUCache", "size", LRUCache, 1, lambda c, a: c.size),
        "isEmpty": _bind("LRUCache", "isEmpty", LRUCache, 1, lambda c, a: c.is_empty),
        "capacity": _bind("LRUCache", "capacity", LRUCache, 1, lambda c, a: c.capacity),
        "clear": _bind("LRUCache", "clear", LRUCache, 1, lambda c, a: c.clear()),
        "keysInOrder": _bind("LRUCache", "keysInOrder", LRUCache, 1, lambda c, a: c.keys_in_order()),
        "iterator": _bind("LRUCache", "iterator", LRUCache, 1, lambda c, a: c.iterator()),
        "toJSON": _bind("LRUCache", "toJSON", LRUCache, 1, lambda c, a: c.to_json()),
        "fromJSON": _from_json_entry("LRUCache", LRUCache),
    }


def _thread_safe_map_members() -> dict[str, BuiltinFunction]:
    """Method table for ThreadSafeMap (first argument is the wrapper)."""
    return {
        "create": BuiltinFunction("ThreadSafeMap.create", _thread_safe_map_create),
        "put": _bind("ThreadSafeMap", "put", ThreadSafeMap, 3, lambda m, a: m.put(*a)),
        "get": _bind("ThreadSafeMap", "get", ThreadSafeMap, 2, lambda m, a: m.get(*a)),
        "remove": _bind("ThreadSafeMap", "remove", ThreadSafeMap, 2, lambda m, a: m.remove(*a)),
        "containsKey": _bind("ThreadSafeMap", "containsKey", ThreadSafeMap, 2, lambda m, a: m.contains_key(*a)),
        "size": _bind("ThreadSafeMap", "size", ThreadSafeMap, 1, lambda m, a: m.size),
        "isEmpty": _bind("ThreadSafeMap", "isEmpty", ThreadSafeMap, 1, lambda m, a: m.is_empty),
        "clear": _bind("ThreadSafeMap", "clear", ThreadSafeMap, 1, lambda m, a: m.clear()),
        "entries": _bind("ThreadSafeMap", "entries", ThreadSafeMap, 1, lambda m, a: m.entries()),
        "iterator": _bind("ThreadSafeMap", "iterator", ThreadSafeMap, 1, lambda m, a: m.iterator()),
        "toJSON": _bind("ThreadSafeMap", "toJSON", ThreadSafeMap, 1, lambda m, a: m.to_json()),
        "fromJSON": _from_json_entry("ThreadSafeMap", ThreadSafeMap),
    }


def _thread_safe_set_members() -> dict[str, BuiltinFunction]:
    """Method table for ThreadSafeSet (first argument is the wrapper)."""
    return {
        "create": BuiltinFunction("ThreadSafeSet.create", _thread_safe_set_create),
        "add": _bind("ThreadSafeSet", "add", ThreadSafeSet, 2, lambda s, a: s.add(*a)),
        "remove": _bind("ThreadSafeSet", "remove", ThreadSafeSet, 2, lambda s, a: s.remove(*a)),
        "contains": _bind("ThreadSafeSet", "contains", ThreadSafeSet, 2, lambda s, a: s.contains(*a)),
        "size": _bind("ThreadSafeSet", "size", ThreadSafeSet, 1, lambda s, a: s.size),
        "isEmpty": _bind("ThreadSafeSet", "isEmpty", ThreadSafeSet, 1, lambda s, a: s.is_empty),
        "clear": _bind("ThreadSafeSet", "clear", ThreadSafeSet, 1, lambda s, a: s.clear()),
        "toArray": _bind("ThreadSafeSet", "toArray", ThreadSafeSet, 1, lambda s, a: s.to_list()),
        "iterator": _bind("ThreadSafeSet", "iterator", ThreadSafeSet, 1, lambda s, a: s.iterator()),
        "toJSON": _bind("ThreadSafeSet", "toJSON", ThreadSafeSet, 1, lambda s, a: s.to_json()),
        "fromJSON": _from_json_entry("ThreadSafeSet", ThreadSafeSet),
    }


def build_namespaces() -> dict[str, dict[str, BuiltinFunction]]:
    """Return ``{structure name: method table}`` for the extended collections.

    The tables are ``name -> BuiltinFunction`` dicts shaped exactly like
    ``xlang.interpreter._hashmap_members()`` output: ``create`` constructs the
    structure, every other entry takes the structure as its first argument, and
    ``toJSON``/``fromJSON`` serialise instances. Only ``xlang.runtime`` is
    imported here, so the interpreter can register the tables with a one-line
    loop (ideally via ``Interpreter._make_collection_ns`` to enable
    ``new TreeMap()`` dot-call style).
    """
    return {
        "TreeMap": _treemap_members(),
        "TreeSet": _treeset_members(),
        "LinkedHashMap": _linked_hash_map_members(),
        "LRUCache": _lru_cache_members(),
        "ThreadSafeMap": _thread_safe_map_members(),
        "ThreadSafeSet": _thread_safe_set_members(),
    }
