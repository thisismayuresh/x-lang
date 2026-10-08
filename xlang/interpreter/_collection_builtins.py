"""X language interpreter: cohesive builtin-family mixins split from the core Interpreter."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ._common import *  # noqa: F401,F403
from ._common import MAX_STRING_LENGTH, ComparatorItem, _is_class_method, _ARRAY_METHODS, _STRING_METHODS



class CollectionBuiltins:
    def _hashmap_members(self) -> dict[str, BuiltinFunction]:
        return {
            "create": BuiltinFunction("HashMap.create", self._hashmap_create),
            "set": BuiltinFunction("HashMap.set", self._hashmap_set),
            "get": BuiltinFunction("HashMap.get", self._hashmap_get),
            "has": BuiltinFunction("HashMap.has", self._hashmap_has),
            "remove": BuiltinFunction("HashMap.remove", self._hashmap_remove),
            "size": BuiltinFunction("HashMap.size", self._hashmap_size),
            "isEmpty": BuiltinFunction("HashMap.isEmpty", self._hashmap_is_empty),
            "clear": BuiltinFunction("HashMap.clear", self._hashmap_clear),
            "keys": BuiltinFunction("HashMap.keys", self._hashmap_keys),
            "values": BuiltinFunction("HashMap.values", self._hashmap_values),
            "entries": BuiltinFunction("HashMap.entries", self._hashmap_entries),
            "merge": BuiltinFunction("HashMap.merge", self._hashmap_merge),
            "filter": BuiltinFunction("HashMap.filter", self._hashmap_filter),
            "map": BuiltinFunction("HashMap.map", self._hashmap_map),
            "reduce": BuiltinFunction("HashMap.reduce", self._hashmap_reduce),
            "getOrDefault": BuiltinFunction("HashMap.getOrDefault", self._hashmap_get_or_default),
            "computeIfAbsent": BuiltinFunction("HashMap.computeIfAbsent", self._hashmap_compute_if_absent),
            "computeIfPresent": BuiltinFunction("HashMap.computeIfPresent", self._hashmap_compute_if_present),
            "putAll": BuiltinFunction("HashMap.putAll", self._hashmap_put_all),
        }

    def _hashmap_create(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("HashMap.create accepts at most one argument (initial capacity)")
        initial_capacity = arguments[0] if arguments else 16
        if not isinstance(initial_capacity, int) or initial_capacity < 1:
            raise RuntimeErrorX("HashMap.create initial capacity must be a positive integer")
        return {}  # Python dict already provides hash map functionality

    def _hashmap_set(self, arguments: list[Any]) -> None:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.set expects hashmap, key, and value arguments")
        hashmap, key, value = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.set expects a HashMap instance")
        if not isinstance(key, (str, int, float, bool)):
            raise RuntimeErrorX("HashMap keys must be strings, numbers, or booleans")
        hashmap[str(key)] = value
        return None

    def _hashmap_get(self, arguments: list[Any]) -> Any:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.get expects key argument")
        hashmap, key = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.get expects a HashMap instance")
        return hashmap.get(str(key))

    def _hashmap_has(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.has expects key argument")
        hashmap, key = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.has expects a HashMap instance")
        return str(key) in hashmap

    def _hashmap_remove(self, arguments: list[Any]) -> Any:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.remove expects key argument")
        hashmap, key = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.remove expects a HashMap instance")
        return hashmap.pop(str(key), None)

    def _hashmap_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.size expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.size expects a HashMap instance")
        return len(hashmap)

    def _hashmap_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.isEmpty expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.isEmpty expects a HashMap instance")
        return len(hashmap) == 0

    def _hashmap_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.clear expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.clear expects a HashMap instance")
        hashmap.clear()
        return None

    def _hashmap_keys(self, arguments: list[Any]) -> list[str]:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.keys expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.keys expects a HashMap instance")
        return list(hashmap.keys())

    def _hashmap_values(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.values expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.values expects a HashMap instance")
        return list(hashmap.values())

    def _hashmap_entries(self, arguments: list[Any]) -> list[list[Any]]:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.entries expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.entries expects a HashMap instance")
        return [[key, value] for key, value in hashmap.items()]

    def _hashmap_merge(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) < 2:
            raise RuntimeErrorX("HashMap.merge expects at least one other HashMap")
        hashmap = self._unwrap_collection(arguments[0])
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.merge expects a HashMap instance")
        result = dict(hashmap)
        for other in arguments[1:]:
            other = self._unwrap_collection(other)
            if not isinstance(other, dict):
                raise RuntimeErrorX("HashMap.merge all arguments must be HashMaps")
            result.update(other)
        return result

    def _normalize_callable(self, value: Any, context: str) -> Any:
        """Normalize a callable value: unwrap list[XFunction] into OverloadedFunction."""
        if isinstance(value, list) and value and all(isinstance(f, XFunction) for f in value):
            return OverloadedFunction(context, value)
        return value

    def _unwrap_collection(self, value: Any) -> Any:
        """Unwrap an XCollectionInstance to its underlying data (list or dict)."""
        if isinstance(value, XCollectionInstance):
            return value._data
        return value

    def _make_collection_ns(self, type_name: str, members: dict) -> dict:
        """Wrap a collection method dict so that `new Stack()` returns an
        XCollectionInstance and instance dot-calls work on it.

        The raw `create` builtin receives a plain list/dict as first argument
        from the functional API.  We replace it with one that returns an
        XCollectionInstance wrapping that data, and also wrap every other
        method so it transparently unpacks the instance's _data before
        delegating to the original builtin.
        """
        raw_create = members["create"]

        def instance_create(arguments: list) -> XCollectionInstance:
            data = raw_create.call(arguments)
            return XCollectionInstance(type_name, data, wrapped)

        wrapped: dict = {}
        for method_name, builtin in members.items():
            if method_name == "create":
                continue
            original = builtin

            def make_wrapper(orig: BuiltinFunction, mname: str) -> BuiltinFunction:
                def dispatch(arguments: list) -> Any:
                    # If first arg is an XCollectionInstance, unwrap it
                    if arguments and isinstance(arguments[0], XCollectionInstance):
                        return orig.call([arguments[0]._data] + arguments[1:])
                    return orig.call(arguments)
                return BuiltinFunction(f"{type_name}.{mname}", dispatch)

            wrapped[method_name] = make_wrapper(original, method_name)

        wrapped["create"] = BuiltinFunction(f"{type_name}.create", instance_create)
        return wrapped

    def _hashmap_filter(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.filter expects a predicate function")
        hashmap, predicate = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.filter expects a HashMap instance")
        predicate = self._normalize_callable(predicate, "filter")
        if not isinstance(predicate, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.filter predicate must be a function")
        result = {}
        for key, value in hashmap.items():
            try:
                if predicate.call([[key, value]]) if isinstance(predicate, (XFunction, BuiltinFunction)) else self._call(predicate, [[key, value]]):
                    result[key] = value
            except Exception:
                pass
        return result

    def _hashmap_map(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.map expects a mapper function")
        hashmap, mapper = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.map expects a HashMap instance")
        mapper = self._normalize_callable(mapper, "map")
        if not isinstance(mapper, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.map mapper must be a function")
        result = {}
        for key, value in hashmap.items():
            try:
                mapped = self._call(mapper, [[key, value]])
                if isinstance(mapped, list) and len(mapped) == 2:
                    result[str(mapped[0])] = mapped[1]
            except Exception:
                pass
        return result

    def _hashmap_reduce(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.reduce expects an initial value and reducer function")
        hashmap, initial, reducer = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.reduce expects a HashMap instance")
        reducer = self._normalize_callable(reducer, "reduce")
        if not isinstance(reducer, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.reduce reducer must be a function")
        accumulator = initial
        for key, value in hashmap.items():
            try:
                accumulator = self._call(reducer, [accumulator, [key, value]])
            except Exception:
                pass
        return accumulator

    def _hashmap_get_or_default(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.getOrDefault expects key and default value")
        hashmap, key, default = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.getOrDefault expects a HashMap instance")
        return hashmap.get(str(key), default)

    def _hashmap_compute_if_absent(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.computeIfAbsent expects key and mapping function")
        hashmap, key, mapping_func = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.computeIfAbsent expects a HashMap instance")
        mapping_func = self._normalize_callable(mapping_func, "computeIfAbsent")
        if not isinstance(mapping_func, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.computeIfAbsent mapping function must be a function")
        key_str = str(key)
        if key_str not in hashmap:
            try:
                hashmap[key_str] = self._call(mapping_func, [key])
            except Exception:
                pass
        return hashmap.get(key_str)

    def _hashmap_compute_if_present(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.computeIfPresent expects key and remapping function")
        hashmap, key, remapping_func = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.computeIfPresent expects a HashMap instance")
        remapping_func = self._normalize_callable(remapping_func, "computeIfPresent")
        if not isinstance(remapping_func, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.computeIfPresent remapping function must be a function")
        key_str = str(key)
        if key_str in hashmap:
            try:
                new_value = self._call(remapping_func, [key, hashmap[key_str]])
                if new_value is not None:
                    hashmap[key_str] = new_value
                else:
                    del hashmap[key_str]
            except Exception:
                pass
        return hashmap.get(key_str)

    def _hashmap_put_all(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.putAll expects another HashMap")
        hashmap = self._unwrap_collection(arguments[0])
        other = self._unwrap_collection(arguments[1])
        if not isinstance(hashmap, dict) or not isinstance(other, dict):
            raise RuntimeErrorX("HashMap.putAll expects HashMap instances")
        hashmap.update(other)
        return None

    # ------------------------------------------------------------------
    # Array methods (myArray.map(cb), List.map(array, cb))
    # ------------------------------------------------------------------

    def _array_receiver(self, arguments: list[Any], name: str) -> list[Any]:
        """Return the array bound as ``arguments[0]`` for method *name*."""
        if not arguments:
            raise RuntimeErrorX(f"Array.{name} expects an array instance")
        receiver = self._unwrap_collection(arguments[0])
        if not isinstance(receiver, list):
            raise RuntimeErrorX(f"Array.{name} expects an array instance")
        return receiver

    def _require_callback(self, value: Any, message: str) -> Any:
        """Normalize *value* (overload lists) and require a callable result."""
        callback = self._normalize_callable(value, "callback")
        if isinstance(callback, (XFunction, BuiltinFunction, OverloadedFunction)):
            return callback
        raise RuntimeErrorX(message)

    def _call_callback(self, callback: Any, arguments: list[Any], context: str) -> Any:
        """Call *callback* with *arguments*, offering only what it declares.

        ``XFunction.call`` rejects surplus arguments, so a one-parameter
        callback such as ``(int n) => n * 2`` must not be handed the index
        argument that two-parameter callbacks accept.
        """
        if isinstance(callback, BuiltinFunction):
            return callback.call(arguments)
        if isinstance(callback, XFunction):
            parameters = callback.declaration.parameters
            if parameters and parameters[-1].is_rest:
                return callback.call(arguments)
            return callback.call(arguments[: len(parameters)])
        if isinstance(callback, OverloadedFunction):
            for count in range(len(arguments), -1, -1):
                if any(
                    self._accepts_argument_count(function.declaration.parameters, count)
                    for function in callback.functions
                ):
                    return self._call(callback, arguments[:count])
            raise RuntimeErrorX(
                f"No overload of {context} accepts {len(arguments)} argument(s)"
            )
        raise RuntimeErrorX(f"{context} must be a function")

    def _natural_sort_key(self, value: Any) -> tuple[int, Any]:
        """Natural ordering key used by ``sort()`` without a callback.

        Numbers sort numerically, then booleans, then strings lexicographically;
        anything else falls back to its printed form so a mixed array never
        fails to compare.
        """
        if isinstance(value, bool):
            return (1, float(value))
        if isinstance(value, (int, float)):
            return (0, float(value))
        if isinstance(value, str):
            return (2, value)
        return (3, self._stringify(value))

    def _slice_bounds(
        self, start_value: Any, end_value: Any, length: int, label: str
    ) -> tuple[int, int]:
        """Normalize JS-style slice bounds: negatives count from the end and
        both bounds clamp into ``[0, length]``."""
        def normalize(value: Any, default: int) -> int:
            if value is None:
                return default
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuntimeErrorX(f"{label} indices must be integers")
            index = value if value >= 0 else length + value
            return max(0, min(length, index))

        return normalize(start_value, 0), normalize(end_value, length)

    def _array_map(self, arguments: list[Any]) -> list[Any]:
        """``map(callback)`` — a new array of ``callback(value, index)`` results."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.map expects a callback function")
        array = self._array_receiver(arguments, "map")
        mapper = self._require_callback(
            arguments[1], "Array.map callback must be a function"
        )
        return [
            self._call_callback(mapper, [value, index], "Array.map callback")
            for index, value in enumerate(array)
        ]

    def _array_filter(self, arguments: list[Any]) -> list[Any]:
        """``filter(callback)`` — elements whose callback result is truthy."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.filter expects a callback function")
        array = self._array_receiver(arguments, "filter")
        predicate = self._require_callback(
            arguments[1], "Array.filter callback must be a function"
        )
        return [
            value
            for index, value in enumerate(array)
            if self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.filter callback")
            )
        ]

    def _array_reduce(self, arguments: list[Any]) -> Any:
        """``reduce(callback, initialValue?)`` — fold the array into one value.

        Without an initial value the first element seeds the accumulator, so
        reducing an empty array that way is an error.
        """
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX(
                "Array.reduce expects a callback function and an optional initial value"
            )
        array = self._array_receiver(arguments, "reduce")
        reducer = self._require_callback(
            arguments[1], "Array.reduce callback must be a function"
        )
        if len(arguments) == 3:
            accumulator = arguments[2]
            start = 0
        else:
            if not array:
                raise RuntimeErrorX(
                    "Array.reduce of an empty array requires an initial value"
                )
            accumulator = array[0]
            start = 1
        for index in range(start, len(array)):
            accumulator = self._call_callback(
                reducer, [accumulator, array[index], index], "Array.reduce callback"
            )
        return accumulator

    def _array_for_each(self, arguments: list[Any]) -> None:
        """``forEach(callback)`` — run the callback for its side effects."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.forEach expects a callback function")
        array = self._array_receiver(arguments, "forEach")
        visitor = self._require_callback(
            arguments[1], "Array.forEach callback must be a function"
        )
        for index, value in enumerate(array):
            self._call_callback(visitor, [value, index], "Array.forEach callback")
        return None

    def _array_find(self, arguments: list[Any]) -> Any:
        """``find(callback)`` — first matching element, or null when none match."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.find expects a callback function")
        array = self._array_receiver(arguments, "find")
        predicate = self._require_callback(
            arguments[1], "Array.find callback must be a function"
        )
        for index, value in enumerate(array):
            if self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.find callback")
            ):
                return value
        return None

    def _array_some(self, arguments: list[Any]) -> bool:
        """``some(callback)`` — true when at least one element matches."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.some expects a callback function")
        array = self._array_receiver(arguments, "some")
        predicate = self._require_callback(
            arguments[1], "Array.some callback must be a function"
        )
        for index, value in enumerate(array):
            if self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.some callback")
            ):
                return True
        return False

    def _array_every(self, arguments: list[Any]) -> bool:
        """``every(callback)`` — true when all elements match (vacuously on [])."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.every expects a callback function")
        array = self._array_receiver(arguments, "every")
        predicate = self._require_callback(
            arguments[1], "Array.every callback must be a function"
        )
        for index, value in enumerate(array):
            if not self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.every callback")
            ):
                return False
        return True

    def _array_index_of(self, arguments: list[Any]) -> int:
        """``indexOf(value)`` — index of the first strict match, or -1."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.indexOf expects a value argument")
        array = self._array_receiver(arguments, "indexOf")
        sought = arguments[1]
        for index, value in enumerate(array):
            if self._strict_equal(value, sought):
                return index
        return -1

    def _array_contains(self, arguments: list[Any]) -> bool:
        """``contains(value)`` — whether a strict match exists."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.contains expects a value argument")
        array = self._array_receiver(arguments, "contains")
        sought = arguments[1]
        return any(self._strict_equal(value, sought) for value in array)

    def _array_sort(self, arguments: list[Any]) -> list[Any]:
        """Stable in-place sort; returns the array, like JavaScript.

        With no callback, values order naturally (numbers numerically, then
        booleans, then strings, then printed forms).  With a two-argument
        callback the result must be a number: negative/zero/positive, like
        ``Array.prototype.sort``.
        """
        if len(arguments) > 2:
            raise RuntimeErrorX("Array.sort accepts at most one callback")
        array = self._array_receiver(arguments, "sort")
        if len(arguments) == 2:
            comparator = self._require_callback(
                arguments[1], "Array.sort callback must be a function"
            )

            def compare(left: Any, right: Any) -> int:
                outcome = self._call_callback(
                    comparator, [left, right], "Array.sort callback"
                )
                if isinstance(outcome, bool) or not isinstance(outcome, (int, float)):
                    raise RuntimeErrorX("Array.sort callback must return a number")
                if outcome < 0:
                    return -1
                if outcome > 0:
                    return 1
                return 0

            array.sort(key=functools.cmp_to_key(compare))
        else:
            array.sort(key=self._natural_sort_key)
        return array

    def _array_reverse(self, arguments: list[Any]) -> list[Any]:
        """``reverse()`` — reverse in place and return the array."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.reverse expects no arguments")
        array = self._array_receiver(arguments, "reverse")
        array.reverse()
        return array

    def _array_slice(self, arguments: list[Any]) -> list[Any]:
        """``slice(start?, end?)`` — sub-array; negatives count from the end."""
        if len(arguments) > 3:
            raise RuntimeErrorX("Array.slice accepts a start and an end index")
        array = self._array_receiver(arguments, "slice")
        start, end = self._slice_bounds(
            arguments[1] if len(arguments) > 1 else None,
            arguments[2] if len(arguments) > 2 else None,
            len(array),
            "Array.slice",
        )
        return array[start:end]

    def _array_concat(self, arguments: list[Any]) -> list[Any]:
        """``concat(other)`` — a new array with *other* appended."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.concat expects one array argument")
        array = self._array_receiver(arguments, "concat")
        other = self._unwrap_collection(arguments[1])
        if not isinstance(other, list):
            raise RuntimeErrorX("Array.concat expects an array argument")
        return list(array) + list(other)

    def _array_join(self, arguments: list[Any]) -> str:
        """``join(separator?)`` — stringify elements and join them.

        The default separator is ``,``; null and undefined elements become
        empty strings, as in JavaScript.
        """
        if len(arguments) > 2:
            raise RuntimeErrorX("Array.join accepts at most one separator")
        array = self._array_receiver(arguments, "join")
        separator = ","
        if len(arguments) == 2:
            separator = arguments[1]
            if not isinstance(separator, str):
                raise RuntimeErrorX("Array.join separator must be a string")
        return separator.join(
            ""
            if element is None or element is UNDEFINED
            else self._stringify(element)
            for element in array
        )

    def _array_first(self, arguments: list[Any]) -> Any:
        """``first()`` — first element, or null when the array is empty."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.first expects no arguments")
        array = self._array_receiver(arguments, "first")
        return array[0] if array else None

    def _array_last(self, arguments: list[Any]) -> Any:
        """``last()`` — last element, or null when the array is empty."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.last expects no arguments")
        array = self._array_receiver(arguments, "last")
        return array[-1] if array else None

    def _array_is_empty(self, arguments: list[Any]) -> bool:
        """``isEmpty()`` — whether the array has no elements."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.isEmpty expects no arguments")
        array = self._array_receiver(arguments, "isEmpty")
        return len(array) == 0

    def _array_clear(self, arguments: list[Any]) -> None:
        """``clear()`` — remove every element in place."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.clear expects no arguments")
        array = self._array_receiver(arguments, "clear")
        array.clear()
        return None

    def _array_push(self, arguments: list[Any]) -> None:
        """``push(value)`` — append one element in place (returns nothing)."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.push expects one value")
        array = self._array_receiver(arguments, "push")
        array.append(arguments[1])
        return None

    def _array_pop(self, arguments: list[Any]) -> Any:
        """``pop()`` — remove and return the last element."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.pop expects no arguments")
        array = self._array_receiver(arguments, "pop")
        if not array:
            raise RuntimeErrorX("Array.pop: array is empty")
        return array.pop()

    # ------------------------------------------------------------------
    # String methods (text.toUpperCase())
    # ------------------------------------------------------------------

    def _string_receiver(self, arguments: list[Any], name: str) -> str:
        """Return the string bound as ``arguments[0]`` for method *name*."""
        if not arguments or not isinstance(arguments[0], str):
            raise RuntimeErrorX(f"String.{name} expects a string instance")
        return arguments[0]

    def _string_index_argument(
        self, arguments: list[Any], position: int, label: str
    ) -> int:
        """Validate an integer index argument at *position*."""
        if len(arguments) <= position:
            raise RuntimeErrorX(f"{label} expects an index argument")
        value = arguments[position]
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeErrorX(f"{label} index must be an integer")
        return value

    def _string_to_upper_case(self, arguments: list[Any]) -> str:
        """``toUpperCase()`` — Unicode-aware upper-casing."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.toUpperCase expects no arguments")
        return self._string_receiver(arguments, "toUpperCase").upper()

    def _string_to_lower_case(self, arguments: list[Any]) -> str:
        """``toLowerCase()`` — Unicode-aware lower-casing."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.toLowerCase expects no arguments")
        return self._string_receiver(arguments, "toLowerCase").lower()

    def _string_trim(self, arguments: list[Any]) -> str:
        """``trim()`` — drop leading and trailing whitespace."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.trim expects no arguments")
        return self._string_receiver(arguments, "trim").strip()

    def _string_starts_with(self, arguments: list[Any]) -> bool:
        """``startsWith(prefix)`` — whether the string begins with *prefix*."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.startsWith expects a prefix argument")
        text = self._string_receiver(arguments, "startsWith")
        prefix = arguments[1]
        if not isinstance(prefix, str):
            raise RuntimeErrorX("String.startsWith prefix must be a string")
        return text.startswith(prefix)

    def _string_ends_with(self, arguments: list[Any]) -> bool:
        """``endsWith(suffix)`` — whether the string ends with *suffix*."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.endsWith expects a suffix argument")
        text = self._string_receiver(arguments, "endsWith")
        suffix = arguments[1]
        if not isinstance(suffix, str):
            raise RuntimeErrorX("String.endsWith suffix must be a string")
        return text.endswith(suffix)

    def _string_contains(self, arguments: list[Any]) -> bool:
        """``contains(part)`` — whether *part* occurs anywhere in the string."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.contains expects a part argument")
        text = self._string_receiver(arguments, "contains")
        part = arguments[1]
        if not isinstance(part, str):
            raise RuntimeErrorX("String.contains part must be a string")
        return part in text

    def _string_index_of(self, arguments: list[Any]) -> int:
        """``indexOf(part)`` — code-point index of the first match, or -1."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.indexOf expects a part argument")
        text = self._string_receiver(arguments, "indexOf")
        part = arguments[1]
        if not isinstance(part, str):
            raise RuntimeErrorX("String.indexOf part must be a string")
        return text.find(part)

    def _string_replace(self, arguments: list[Any]) -> str:
        """``replace(old, new)`` — replace only the first occurrence."""
        if len(arguments) != 3:
            raise RuntimeErrorX("String.replace expects old and new string arguments")
        text = self._string_receiver(arguments, "replace")
        old, new = arguments[1], arguments[2]
        if not isinstance(old, str) or not isinstance(new, str):
            raise RuntimeErrorX("String.replace expects old and new to be strings")
        return text.replace(old, new, 1)

    def _string_replace_all(self, arguments: list[Any]) -> str:
        """``replaceAll(old, new)`` — replace every occurrence."""
        if len(arguments) != 3:
            raise RuntimeErrorX("String.replaceAll expects old and new string arguments")
        text = self._string_receiver(arguments, "replaceAll")
        old, new = arguments[1], arguments[2]
        if not isinstance(old, str) or not isinstance(new, str):
            raise RuntimeErrorX("String.replaceAll expects old and new to be strings")
        return text.replace(old, new)

    def _string_split(self, arguments: list[Any]) -> list[str]:
        """``split(separator?)`` — split into an array of strings.

        With no separator the string splits on whitespace runs (Python
        ``str.split``); ``""`` splits into individual Unicode code points.
        """
        if len(arguments) > 2:
            raise RuntimeErrorX("String.split accepts at most one separator")
        text = self._string_receiver(arguments, "split")
        if len(arguments) == 1:
            return text.split()
        separator = arguments[1]
        if not isinstance(separator, str):
            raise RuntimeErrorX("String.split separator must be a string")
        if separator == "":
            return list(text)
        return text.split(separator)

    def _string_char_at(self, arguments: list[Any]) -> str:
        """``charAt(index)`` — the one-character string at *index*.

        Indexing counts Unicode code points (negatives count backward from the
        end, like all X string indexing); out-of-range indices raise.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("String.charAt expects an index argument")
        text = self._string_receiver(arguments, "charAt")
        index = self._string_index_argument(arguments, 1, "String.charAt")
        try:
            return text[index]
        except IndexError:
            raise RuntimeErrorX("String.charAt index out of bounds") from None

    def _string_substring(self, arguments: list[Any]) -> str:
        """``substring(start?, end?)`` — JS-style bounds in code points.

        Negative indices clamp to 0 and the bounds swap when *start* > *end*,
        unlike ``slice`` where negatives count from the end.
        """
        if len(arguments) > 3:
            raise RuntimeErrorX("String.substring accepts a start and an end index")
        text = self._string_receiver(arguments, "substring")
        if len(arguments) > 1:
            start = self._string_index_argument(arguments, 1, "String.substring")
        else:
            start = 0
        if len(arguments) > 2:
            end = self._string_index_argument(arguments, 2, "String.substring")
        else:
            end = len(text)
        start = max(0, start)
        end = max(0, end)
        if start > end:
            start, end = end, start
        return text[start:end]

    def _string_slice(self, arguments: list[Any]) -> str:
        """``slice(start?, end?)`` — code-point slice; negatives count from
        the end and out-of-range bounds clamp."""
        if len(arguments) > 3:
            raise RuntimeErrorX("String.slice accepts a start and an end index")
        text = self._string_receiver(arguments, "slice")
        start, end = self._slice_bounds(
            arguments[1] if len(arguments) > 1 else None,
            arguments[2] if len(arguments) > 2 else None,
            len(text),
            "String.slice",
        )
        return text[start:end]

    def _string_repeat(self, arguments: list[Any]) -> str:
        """``repeat(count)`` — concatenate the string *count* times."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.repeat expects a count argument")
        text = self._string_receiver(arguments, "repeat")
        count = arguments[1]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RuntimeErrorX("String.repeat count must be a non-negative integer")
        if count > 0 and len(text) * count > MAX_STRING_LENGTH:
            raise RuntimeErrorX(
                f"String.repeat result of {len(text) * count} characters exceeds "
                f"the maximum string length of {MAX_STRING_LENGTH}",
                "ArithmeticException",
            )
        return text * count

    def _pad_text(self, text: str, length: int, pad: str, left: bool) -> str:
        """Pad *text* out to *length* with *pad* cycled (JS ``padStart``/``padEnd``).

        The padding is built from repetitions of *pad* truncated to the exact
        number of missing characters; an empty pad leaves *text* unchanged.
        """
        if len(text) >= length or pad == "":
            return text
        if length > MAX_STRING_LENGTH:
            raise RuntimeErrorX(
                f"Padding to {length} characters exceeds the maximum string "
                f"length of {MAX_STRING_LENGTH}",
                "ArithmeticException",
            )
        missing = length - len(text)
        fill = (pad * (missing // len(pad) + 1))[:missing]
        return fill + text if left else text + fill

    def _string_pad_start(self, arguments: list[Any]) -> str:
        """``padStart(length, pad?)`` — left-pad to *length* (default pad ``" "``).

        A multi-character pad repeats, as in JavaScript; an empty pad leaves
        the text unchanged because there is nothing to fill with.
        """
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX("String.padStart expects a length argument")
        text = self._string_receiver(arguments, "padStart")
        length = arguments[1]
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise RuntimeErrorX("String.padStart length must be a non-negative integer")
        pad = " " if len(arguments) == 2 else arguments[2]
        if not isinstance(pad, str):
            raise RuntimeErrorX("String.padStart pad must be a string")
        return self._pad_text(text, length, pad, left=True)

    def _string_pad_end(self, arguments: list[Any]) -> str:
        """``padEnd(length, pad?)`` — right-pad to *length* (default pad ``" "``)."""
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX("String.padEnd expects a length argument")
        text = self._string_receiver(arguments, "padEnd")
        length = arguments[1]
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise RuntimeErrorX("String.padEnd length must be a non-negative integer")
        pad = " " if len(arguments) == 2 else arguments[2]
        if not isinstance(pad, str):
            raise RuntimeErrorX("String.padEnd pad must be a string")
        return self._pad_text(text, length, pad, left=False)

    def _string_is_empty(self, arguments: list[Any]) -> bool:
        """``isEmpty()`` — whether the string has no characters."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.isEmpty expects no arguments")
        return self._string_receiver(arguments, "isEmpty") == ""

    def _string_to_char_array(self, arguments: list[Any]) -> list[str]:
        """``toCharArray()`` — one-character strings, one per code point."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.toCharArray expects no arguments")
        return list(self._string_receiver(arguments, "toCharArray"))

    def _string_strip(self, arguments: list[Any]) -> str:
        """``strip()`` — remove leading and trailing whitespace."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.strip expects no arguments")
        return self._string_receiver(arguments, "strip").strip()

    def _string_strip_leading(self, arguments: list[Any]) -> str:
        """``stripLeading()`` — remove leading whitespace."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.stripLeading expects no arguments")
        return self._string_receiver(arguments, "stripLeading").lstrip()

    def _string_strip_trailing(self, arguments: list[Any]) -> str:
        """``stripTrailing()`` — remove trailing whitespace."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.stripTrailing expects no arguments")
        return self._string_receiver(arguments, "stripTrailing").rstrip()

    def _string_last_index_of(self, arguments: list[Any]) -> int:
        """``lastIndexOf(substr, fromIndex?)`` — last index of substring."""
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX("String.lastIndexOf expects 1 or 2 arguments")
        text = self._string_receiver(arguments, "lastIndexOf")
        substr = arguments[1]
        if not isinstance(substr, str):
            raise RuntimeErrorX("String.lastIndexOf substring must be a string")
        if len(arguments) == 3:
            from_idx = arguments[2]
            if isinstance(from_idx, bool) or not isinstance(from_idx, int):
                raise RuntimeErrorX("String.lastIndexOf fromIndex must be an integer")
            return text.rfind(substr, 0, from_idx + 1)
        return text.rfind(substr)

    def _string_code_point_at(self, arguments: list[Any]) -> int:
        """``codePointAt(index)`` — Unicode code point at index."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.codePointAt expects an index argument")
        text = self._string_receiver(arguments, "codePointAt")
        index = arguments[1]
        if isinstance(index, bool) or not isinstance(index, int):
            raise RuntimeErrorX("String.codePointAt index must be an integer")
        if index < 0 or index >= len(text):
            raise RuntimeErrorX("String.codePointAt index out of bounds")
        return ord(text[index])

    def _string_is_blank(self, arguments: list[Any]) -> bool:
        """``isBlank()`` — whether string is empty or only whitespace."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.isBlank expects no arguments")
        return self._string_receiver(arguments, "isBlank").strip() == ""

    def _string_to_char_array(self, arguments: list[Any]) -> list[str]:
        """``toCharArray()`` — one-character strings, one per code point."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.toCharArray expects no arguments")
        return list(self._string_receiver(arguments, "toCharArray"))

    def _string_chars(self, arguments: list[Any]) -> list[str]:
        """``chars()`` — stream of characters (alias for toCharArray)."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.chars expects no arguments")
        return list(self._string_receiver(arguments, "chars"))

    def _string_code_points(self, arguments: list[Any]) -> list[int]:
        """``codePoints()`` — stream of Unicode code points."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.codePoints expects no arguments")
        return [ord(c) for c in self._string_receiver(arguments, "codePoints")]

    def _string_format(self, arguments: list[Any]) -> str:
        """``format(args...)`` — Python-style string formatting."""
        if len(arguments) < 2:
            raise RuntimeErrorX("String.format expects at least one format argument")
        template = self._string_receiver(arguments, "format")
        args = arguments[1:]
        try:
            return template.format(*args)
        except (KeyError, ValueError, IndexError) as e:
            raise RuntimeErrorX(f"String.format failed: {e}")

    def _string_value_of(self, arguments: list[Any]) -> str:
        """``valueOf(value)`` — string representation of any value."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.valueOf expects one argument")
        value = arguments[1]
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _string_join(self, arguments: list[Any]) -> str:
        """``join(delimiter, elements...)`` — join array elements with delimiter."""
        if len(arguments) < 2:
            raise RuntimeErrorX("String.join expects at least delimiter and one element")
        delimiter = arguments[1]
        if not isinstance(delimiter, str):
            raise RuntimeErrorX("String.join delimiter must be a string")
        elements = []
        for arg in arguments[2:]:
            if isinstance(arg, list):
                elements.extend(str(x) for x in arg)
            else:
                elements.append(str(arg))
        return delimiter.join(elements)

    def _string_lines(self, arguments: list[Any]) -> list[str]:
        """``lines()`` — split string into lines."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.lines expects no arguments")
        text = self._string_receiver(arguments, "lines")
        return text.splitlines()

    def _string_indent(self, arguments: list[Any]) -> str:
        """``indent(n)`` — indent each line by n spaces."""
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX("String.indent expects 1 or 2 arguments")
        text = self._string_receiver(arguments, "indent")
        n = arguments[1]
        if isinstance(n, bool) or not isinstance(n, int):
            raise RuntimeErrorX("String.indent spaces must be an integer")
        prefix = " " * max(0, n)
        lines = text.splitlines(keepends=True)
        return "".join(prefix + line if line.strip() or n > 0 else line for line in lines)

    def _string_transform(self, arguments: list[Any]) -> str:
        """``transform(fn)`` — apply function to string."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.transform expects a function argument")
        text = self._string_receiver(arguments, "transform")
        fn = arguments[1]
        # fn should be callable (XFunction or BuiltinFunction)
        if hasattr(fn, 'call'):
            return fn.call([text])
        raise RuntimeErrorX("String.transform argument must be a function")

    def _linkedlist_members(self) -> dict[str, BuiltinFunction]:
        members: dict[str, BuiltinFunction] = {
            "create": BuiltinFunction("LinkedList.create", self._linkedlist_create),
            "add": BuiltinFunction("LinkedList.add", self._linkedlist_add),
            "addFirst": BuiltinFunction("LinkedList.addFirst", self._linkedlist_add_first),
            "addLast": BuiltinFunction("LinkedList.addLast", self._linkedlist_add_last),
            "remove": BuiltinFunction("LinkedList.remove", self._linkedlist_remove),
            "removeFirst": BuiltinFunction("LinkedList.removeFirst", self._linkedlist_remove_first),
            "removeLast": BuiltinFunction("LinkedList.removeLast", self._linkedlist_remove_last),
            "get": BuiltinFunction("LinkedList.get", self._linkedlist_get),
            "getFirst": BuiltinFunction("LinkedList.getFirst", self._linkedlist_get_first),
            "getLast": BuiltinFunction("LinkedList.getLast", self._linkedlist_get_last),
            "size": BuiltinFunction("LinkedList.size", self._linkedlist_size),
            "isEmpty": BuiltinFunction("LinkedList.isEmpty", self._linkedlist_is_empty),
            "clear": BuiltinFunction("LinkedList.clear", self._linkedlist_clear),
            "contains": BuiltinFunction("LinkedList.contains", self._linkedlist_contains),
            "indexOf": BuiltinFunction("LinkedList.indexOf", self._linkedlist_index_of),
            "toArray": BuiltinFunction("LinkedList.toArray", self._linkedlist_to_array),
            "reverse": BuiltinFunction("LinkedList.reverse", self._linkedlist_reverse),
            "groupBy": BuiltinFunction("LinkedList.groupBy", self._linkedlist_group_by),
            "partition": BuiltinFunction("LinkedList.partition", self._linkedlist_partition),
        }
        # Array methods double as the functional API: List.map(array, cb).
        # LinkedList-specific entries above (indexOf, reverse, ...) keep their
        # own behavior.
        for method_name, implementation_name in _ARRAY_METHODS.items():
            members.setdefault(
                method_name,
                BuiltinFunction(
                    f"List.{method_name}", getattr(self, implementation_name)
                ),
            )
        return members

    def _linkedlist_create(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("LinkedList.create accepts at most one argument (initial array)")
        if len(arguments) == 1:
            if not isinstance(arguments[0], list):
                raise RuntimeErrorX("LinkedList.create initial value must be an array")
            return list(arguments[0])
        return []

    def _linkedlist_add(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.add expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.add expects a LinkedList instance")
        linkedlist.append(value)
        return None

    def _linkedlist_add_first(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.addFirst expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.addFirst expects a LinkedList instance")
        linkedlist.insert(0, value)
        return None

    def _linkedlist_add_last(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.addLast expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.addLast expects a LinkedList instance")
        linkedlist.append(value)
        return None

    def _linkedlist_remove(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.remove expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.remove expects a LinkedList instance")
        try:
            linkedlist.remove(value)
            return True
        except ValueError:
            return False

    def _linkedlist_remove_first(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.removeFirst expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.removeFirst expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.removeFirst: list is empty")
        return linkedlist.pop(0)

    def _linkedlist_remove_last(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.removeLast expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.removeLast expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.removeLast: list is empty")
        return linkedlist.pop()

    def _linkedlist_get(self, arguments: list[Any]) -> Any:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.get expects an index argument")
        linkedlist, index = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.get expects a LinkedList instance")
        if not isinstance(index, int) or index < 0 or index >= len(linkedlist):
            raise RuntimeErrorX("LinkedList.get index out of bounds")
        return linkedlist[index]

    def _linkedlist_get_first(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.getFirst expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.getFirst expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.getFirst: list is empty")
        return linkedlist[0]

    def _linkedlist_get_last(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.getLast expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.getLast expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.getLast: list is empty")
        return linkedlist[-1]

    def _linkedlist_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.size expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.size expects a LinkedList instance")
        return len(linkedlist)

    def _linkedlist_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.isEmpty expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.isEmpty expects a LinkedList instance")
        return len(linkedlist) == 0

    def _linkedlist_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.clear expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.clear expects a LinkedList instance")
        linkedlist.clear()
        return None

    def _linkedlist_contains(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.contains expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.contains expects a LinkedList instance")
        return value in linkedlist

    def _linkedlist_index_of(self, arguments: list[Any]) -> int:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.indexOf expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.indexOf expects a LinkedList instance")
        try:
            return linkedlist.index(value)
        except ValueError:
            return -1

    def _linkedlist_to_array(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.toArray expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.toArray expects a LinkedList instance")
        return list(linkedlist)

    def _linkedlist_reverse(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.reverse expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.reverse expects a LinkedList instance")
        linkedlist.reverse()
        return None

    def _linkedlist_group_by(self, arguments: list[Any]) -> dict[str, list[Any]]:
        """Group list elements by the string key returned by *fn(item)*.

        Returns a dict whose keys are the stringified results of calling *fn*
        on each element and whose values are lists of the matching elements.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.groupBy expects a list and a key function")
        linkedlist, fn = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.groupBy expects a LinkedList instance")
        if not isinstance(fn, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("LinkedList.groupBy: second argument must be a function")
        groups: dict[str, list[Any]] = {}
        for item in linkedlist:
            key = str(self._call(fn, [item]))
            groups.setdefault(key, []).append(item)
        return groups

    def _linkedlist_partition(self, arguments: list[Any]) -> list[list[Any]]:
        """Split the list into two sub-lists based on a predicate function.

        Returns ``[[truthy_items], [falsy_items]]`` where *fn(item)* decides
        which partition each element falls into.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.partition expects a list and a predicate function")
        linkedlist, fn = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.partition expects a LinkedList instance")
        if not isinstance(fn, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("LinkedList.partition: second argument must be a function")
        truthy: list[Any] = []
        falsy: list[Any] = []
        for item in linkedlist:
            (truthy if self._is_truthy(self._call(fn, [item])) else falsy).append(item)
        return [truthy, falsy]

    def _stack_members(self) -> dict[str, BuiltinFunction]:
        return {
            "create": BuiltinFunction("Stack.create", self._stack_create),
            "push": BuiltinFunction("Stack.push", self._stack_push),
            "pop": BuiltinFunction("Stack.pop", self._stack_pop),
            "peek": BuiltinFunction("Stack.peek", self._stack_peek),
            "size": BuiltinFunction("Stack.size", self._stack_size),
            "isEmpty": BuiltinFunction("Stack.isEmpty", self._stack_is_empty),
            "clear": BuiltinFunction("Stack.clear", self._stack_clear),
            "toArray": BuiltinFunction("Stack.toArray", self._stack_to_array),
        }

    def _stack_create(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("Stack.create accepts at most one argument (initial array)")
        if len(arguments) == 1:
            if not isinstance(arguments[0], list):
                raise RuntimeErrorX("Stack.create initial value must be an array")
            return list(arguments[0])
        return []

    def _stack_push(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("Stack.push expects a value argument")
        stack, value = arguments[0], arguments[1]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.push expects a Stack instance")
        stack.append(value)
        return None

    def _stack_pop(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.pop expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.pop expects a Stack instance")
        if not stack:
            raise RuntimeErrorX("Stack.pop: stack is empty")
        return stack.pop()

    def _stack_peek(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.peek expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.peek expects a Stack instance")
        if not stack:
            raise RuntimeErrorX("Stack.peek: stack is empty")
        return stack[-1]

    def _stack_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.size expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.size expects a Stack instance")
        return len(stack)

    def _stack_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.isEmpty expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.isEmpty expects a Stack instance")
        return len(stack) == 0

    def _stack_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.clear expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.clear expects a Stack instance")
        stack.clear()
        return None

    def _stack_to_array(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.toArray expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.toArray expects a Stack instance")
        return list(stack)

    def _queue_members(self) -> dict[str, BuiltinFunction]:
        return {
            "create": BuiltinFunction("Queue.create", self._queue_create),
            "enqueue": BuiltinFunction("Queue.enqueue", self._queue_enqueue),
            "dequeue": BuiltinFunction("Queue.dequeue", self._queue_dequeue),
            "peek": BuiltinFunction("Queue.peek", self._queue_peek),
            "size": BuiltinFunction("Queue.size", self._queue_size),
            "isEmpty": BuiltinFunction("Queue.isEmpty", self._queue_is_empty),
            "clear": BuiltinFunction("Queue.clear", self._queue_clear),
            "toArray": BuiltinFunction("Queue.toArray", self._queue_to_array),
        }

    def _queue_create(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("Queue.create accepts at most one argument (initial array)")
        if len(arguments) == 1:
            if not isinstance(arguments[0], list):
                raise RuntimeErrorX("Queue.create initial value must be an array")
            return list(arguments[0])
        return []

    def _queue_enqueue(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("Queue.enqueue expects a value argument")
        queue, value = arguments[0], arguments[1]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.enqueue expects a Queue instance")
        queue.append(value)
        return None

    def _queue_dequeue(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.dequeue expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.dequeue expects a Queue instance")
        if not queue:
            raise RuntimeErrorX("Queue.dequeue: queue is empty")
        return queue.pop(0)

    def _queue_peek(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.peek expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.peek expects a Queue instance")
        if not queue:
            raise RuntimeErrorX("Queue.peek: queue is empty")
        return queue[0]

    def _queue_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.size expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.size expects a Queue instance")
        return len(queue)

    def _queue_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.isEmpty expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.isEmpty expects a Queue instance")
        return len(queue) == 0

    def _queue_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.clear expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.clear expects a Queue instance")
        queue.clear()
        return None

    def _queue_to_array(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.toArray expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.toArray expects a Queue instance")
        return list(queue)

    def _priorityqueue_members(self) -> dict[str, BuiltinFunction]:
        """Return the method table for PriorityQueue collection namespace."""
        return {
            "create":   BuiltinFunction("PriorityQueue.create",   self._priorityqueue_create),
            "enqueue":  BuiltinFunction("PriorityQueue.enqueue",  self._priorityqueue_enqueue),
            "dequeue":  BuiltinFunction("PriorityQueue.dequeue",  self._priorityqueue_dequeue),
            "peek":     BuiltinFunction("PriorityQueue.peek",     self._priorityqueue_peek),
            "size":     BuiltinFunction("PriorityQueue.size",     self._priorityqueue_size),
            "isEmpty":  BuiltinFunction("PriorityQueue.isEmpty",  self._priorityqueue_is_empty),
            "clear":    BuiltinFunction("PriorityQueue.clear",    self._priorityqueue_clear),
            "toArray":  BuiltinFunction("PriorityQueue.toArray",  self._priorityqueue_to_array),
        }

    def _priorityqueue_create(self, arguments: list[Any]) -> dict[str, Any]:
        """Create a new PriorityQueue dict.

        Accepts an optional single argument:
        - ``'max'`` (string)  → max-heap (largest value dequeued first).
        - A callable X function → custom comparator; called as ``fn(a, b)``
          and must return a negative number when ``a`` sorts before ``b``.
        """
        if len(arguments) > 1:
            raise RuntimeErrorX(
                "PriorityQueue.create accepts at most one argument ('max' or comparator fn)"
            )
        mode: str = "min"
        comparator: Any = None
        if len(arguments) == 1:
            arg = arguments[0]
            if arg == "max":
                mode = "max"
            elif isinstance(arg, (XFunction, BuiltinFunction, OverloadedFunction)):
                comparator = arg
            elif arg is not None:
                raise RuntimeErrorX(
                    "PriorityQueue.create argument must be 'max' or a comparator function"
                )
        return {"heap": [], "comparator": comparator, "mode": mode}

    def _priorityqueue_unwrap_item(self, item: Any) -> Any:
        """Unwrap a ComparatorItem or max-heap negation tuple to the original value."""
        if isinstance(item, ComparatorItem):
            return item.value
        # max-heap without comparator stores (-value, value)
        if isinstance(item, tuple) and len(item) == 2:
            return item[1]
        return item

    def _priorityqueue_enqueue(self, arguments: list[Any]) -> None:
        """Push *value* onto the heap in O(log n) time using heapq."""
        if len(arguments) != 2:
            raise RuntimeErrorX("PriorityQueue.enqueue expects exactly one value argument")
        queue, value = arguments[0], arguments[1]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.enqueue expects a PriorityQueue instance")
        heap: list = queue["heap"]
        comparator = queue["comparator"]
        mode: str = queue["mode"]
        if comparator is not None:
            heapq.heappush(heap, ComparatorItem(value, comparator, self._call))
        elif mode == "max":
            # Negate numeric values; fall back to ComparatorItem for non-numeric
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                heapq.heappush(heap, (-value, value))
            else:
                # Wrap with a reversed comparator so largest is popped first
                def _reverse_cmp(a: Any, b: Any) -> int:
                    if a < b:
                        return 1
                    if a > b:
                        return -1
                    return 0

                dummy_fn = BuiltinFunction(
                    "__max_cmp",
                    lambda args: _reverse_cmp(args[0], args[1]),
                )
                heapq.heappush(heap, ComparatorItem(value, dummy_fn, self._call))
        else:
            heapq.heappush(heap, value)
        return None

    def _priorityqueue_dequeue(self, arguments: list[Any]) -> Any:
        """Pop and return the highest-priority element in O(log n) time."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.dequeue expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.dequeue expects a PriorityQueue instance")
        heap: list = queue["heap"]
        if not heap:
            raise RuntimeErrorX("PriorityQueue.dequeue: queue is empty")
        return self._priorityqueue_unwrap_item(heapq.heappop(heap))

    def _priorityqueue_peek(self, arguments: list[Any]) -> Any:
        """Return the highest-priority element without removing it."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.peek expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.peek expects a PriorityQueue instance")
        heap: list = queue["heap"]
        if not heap:
            raise RuntimeErrorX("PriorityQueue.peek: queue is empty")
        return self._priorityqueue_unwrap_item(heap[0])

    def _priorityqueue_size(self, arguments: list[Any]) -> int:
        """Return the number of elements currently in the queue."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.size expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.size expects a PriorityQueue instance")
        return len(queue["heap"])

    def _priorityqueue_is_empty(self, arguments: list[Any]) -> bool:
        """Return True when the queue contains no elements."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.isEmpty expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.isEmpty expects a PriorityQueue instance")
        return len(queue["heap"]) == 0

    def _priorityqueue_clear(self, arguments: list[Any]) -> None:
        """Remove all elements from the queue in place."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.clear expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.clear expects a PriorityQueue instance")
        queue["heap"].clear()
        return None

    def _priorityqueue_to_array(self, arguments: list[Any]) -> list[Any]:
        """Return a sorted list of all elements (does not modify the queue)."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.toArray expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.toArray expects a PriorityQueue instance")
        heap: list = queue["heap"]
        sorted_items = heapq.nsmallest(len(heap), heap)
        return [self._priorityqueue_unwrap_item(item) for item in sorted_items]

    def _trie_members(self) -> dict[str, BuiltinFunction]:
        """Return the method table for Trie collection namespace."""
        return {
            "create":            BuiltinFunction("Trie.create",            self._trie_create),
            "insert":            BuiltinFunction("Trie.insert",            self._trie_insert),
            "search":            BuiltinFunction("Trie.search",            self._trie_search),
            "startsWith":        BuiltinFunction("Trie.startsWith",        self._trie_starts_with),
            "remove":            BuiltinFunction("Trie.remove",            self._trie_remove),
            "size":              BuiltinFunction("Trie.size",              self._trie_size),
            "isEmpty":           BuiltinFunction("Trie.isEmpty",           self._trie_is_empty),
            "clear":             BuiltinFunction("Trie.clear",             self._trie_clear),
            "getAllWords":        BuiltinFunction("Trie.getAllWords",       self._trie_get_all_words),
            "getWordsWithPrefix": BuiltinFunction("Trie.getWordsWithPrefix", self._trie_get_words_with_prefix),
        }

    def _trie_create(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) > 0:
            raise RuntimeErrorX("Trie.create accepts no arguments")
        return {"children": {}, "is_end": False, "count": 0}

    def _trie_insert(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.insert expects a word argument")
        trie, word = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.insert expects a Trie instance")
        if not isinstance(word, str):
            raise RuntimeErrorX("Trie.insert word must be a string")
        node = trie
        for char in word:
            if char not in node["children"]:
                node["children"][char] = {"children": {}, "is_end": False}
            node = node["children"][char]
        if not node["is_end"]:
            node["is_end"] = True
            trie["count"] = trie.get("count", 0) + 1
        return None

    def _trie_search(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.search expects a word argument")
        trie, word = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.search expects a Trie instance")
        if not isinstance(word, str):
            raise RuntimeErrorX("Trie.search word must be a string")
        node = trie
        for char in word:
            if char not in node["children"]:
                return False
            node = node["children"][char]
        return node.get("is_end", False)

    def _trie_starts_with(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.startsWith expects a prefix argument")
        trie, prefix = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.startsWith expects a Trie instance")
        if not isinstance(prefix, str):
            raise RuntimeErrorX("Trie.startsWith prefix must be a string")
        node = trie
        for char in prefix:
            if char not in node["children"]:
                return False
            node = node["children"][char]
        return True

    def _trie_remove(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.remove expects a word argument")
        trie, word = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.remove expects a Trie instance")
        if not isinstance(word, str):
            raise RuntimeErrorX("Trie.remove word must be a string")
        
        def _remove_helper(node: dict[str, Any], word: str, index: int) -> bool:
            if index == len(word):
                if not node.get("is_end", False):
                    return False
                node["is_end"] = False
                trie["count"] = trie.get("count", 0) - 1
                return len(node["children"]) == 0
            char = word[index]
            if char not in node["children"]:
                return False
            should_delete = _remove_helper(node["children"][char], word, index + 1)
            if should_delete:
                del node["children"][char]
                return len(node["children"]) == 0 and not node.get("is_end", False)
            return False
        
        return _remove_helper(trie, word, 0)

    def _trie_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.size expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.size expects a Trie instance")
        return trie.get("count", 0)

    def _trie_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.isEmpty expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.isEmpty expects a Trie instance")
        return trie.get("count", 0) == 0

    def _trie_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.clear expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.clear expects a Trie instance")
        trie["children"] = {}
        trie["is_end"] = False
        trie["count"] = 0
        return None

    def _trie_get_all_words(self, arguments: list[Any]) -> list[str]:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.getAllWords expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.getAllWords expects a Trie instance")
        
        words = []
        
        def _collect_words(node: dict[str, Any], prefix: str) -> None:
            if node.get("is_end", False):
                words.append(prefix)
            for char, child in node["children"].items():
                _collect_words(child, prefix + char)
        
        _collect_words(trie, "")
        return words

    def _trie_get_words_with_prefix(self, arguments: list[Any]) -> list[str]:
        """Return all words stored in the trie that begin with *prefix*.

        Traverses to the prefix node character by character; returns ``[]``
        if any character in the prefix is missing.  Then runs a DFS from
        that node, seeding each collected word with the prefix string.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.getWordsWithPrefix expects a prefix argument")
        trie, prefix = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.getWordsWithPrefix expects a Trie instance")
        if not isinstance(prefix, str):
            raise RuntimeErrorX("Trie.getWordsWithPrefix: prefix must be a string")

        # Walk to the node at the end of the prefix
        node: dict[str, Any] = trie
        for char in prefix:
            if char not in node["children"]:
                return []
            node = node["children"][char]

        # DFS from that node, collecting every complete word
        words: list[str] = []

        def _collect(current_node: dict[str, Any], current_prefix: str) -> None:
            if current_node.get("is_end", False):
                words.append(current_prefix)
            for char, child in current_node["children"].items():
                _collect(child, current_prefix + char)

        _collect(node, prefix)
        return words

    # ──────────────────────────────────────────────────────────────────────────
    # Set methods
    # ──────────────────────────────────────────────────────────────────────────

    def _set_members(self) -> dict[str, BuiltinFunction]:
        """Return the method table for Set collection namespace."""
        return {
            "create":       BuiltinFunction("Set.create",       self._set_create),
            "add":          BuiltinFunction("Set.add",          self._set_add),
            "has":          BuiltinFunction("Set.has",          self._set_has),
            "remove":       BuiltinFunction("Set.remove",       self._set_remove),
            "size":         BuiltinFunction("Set.size",         self._set_size),
            "isEmpty":      BuiltinFunction("Set.isEmpty",      self._set_is_empty),
            "clear":        BuiltinFunction("Set.clear",        self._set_clear),
            "toArray":      BuiltinFunction("Set.toArray",      self._set_to_array),
            "union":        BuiltinFunction("Set.union",        self._set_union),
            "intersection": BuiltinFunction("Set.intersection", self._set_intersection),
            "difference":   BuiltinFunction("Set.difference",  self._set_difference),
        }

    def _set_create(self, arguments: list[Any]) -> set[Any]:
        """Create a new empty Set, optionally initialised from an iterable."""
        if len(arguments) > 1:
            raise RuntimeErrorX("Set.create accepts at most one argument (initial iterable)")
        if len(arguments) == 1:
            init = arguments[0]
            if not hasattr(init, "__iter__"):
                raise RuntimeErrorX("Set.create initial value must be iterable")
            return set(init)
        return set()

    def _set_add(self, arguments: list[Any]) -> None:
        """Add *value* to the set (no-op if already present)."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.add expects exactly one value argument")
        s, value = arguments[0], arguments[1]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.add expects a Set instance")
        s.add(value)
        return None

    def _set_has(self, arguments: list[Any]) -> bool:
        """Return True when *value* is a member of the set."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.has expects exactly one value argument")
        s, value = arguments[0], arguments[1]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.has expects a Set instance")
        return value in s

    def _set_remove(self, arguments: list[Any]) -> bool:
        """Remove *value* from the set; returns True if it was present."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.remove expects exactly one value argument")
        s, value = arguments[0], arguments[1]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.remove expects a Set instance")
        if value in s:
            s.discard(value)
            return True
        return False

    def _set_size(self, arguments: list[Any]) -> int:
        """Return the number of elements in the set."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.size expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.size expects a Set instance")
        return len(s)

    def _set_is_empty(self, arguments: list[Any]) -> bool:
        """Return True when the set contains no elements."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.isEmpty expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.isEmpty expects a Set instance")
        return len(s) == 0

    def _set_clear(self, arguments: list[Any]) -> None:
        """Remove all elements from the set in place."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.clear expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.clear expects a Set instance")
        s.clear()
        return None

    def _set_to_array(self, arguments: list[Any]) -> list[Any]:
        """Return a sorted list of the set's elements (sort key: str representation)."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.toArray expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.toArray expects a Set instance")
        return sorted(s, key=str)

    def _set_union(self, arguments: list[Any]) -> set[Any]:
        """Return a new set containing elements from both sets."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.union expects exactly two Set arguments")
        s1 = arguments[0]
        s2 = arguments[1]
        # Allow the second arg to be an XCollectionInstance (instance dot-call pattern)
        if isinstance(s2, XCollectionInstance):
            s2 = s2._data
        if not isinstance(s1, set):
            raise RuntimeErrorX("Set.union: first argument must be a Set instance")
        if not isinstance(s2, set):
            raise RuntimeErrorX("Set.union: second argument must be a Set instance")
        return s1 | s2

    def _set_intersection(self, arguments: list[Any]) -> set[Any]:
        """Return a new set containing only elements present in both sets."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.intersection expects exactly two Set arguments")
        s1 = arguments[0]
        s2 = arguments[1]
        if isinstance(s2, XCollectionInstance):
            s2 = s2._data
        if not isinstance(s1, set):
            raise RuntimeErrorX("Set.intersection: first argument must be a Set instance")
        if not isinstance(s2, set):
            raise RuntimeErrorX("Set.intersection: second argument must be a Set instance")
        return s1 & s2

    def _set_difference(self, arguments: list[Any]) -> set[Any]:
        """Return a new set with elements in *s1* that are not in *s2*."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.difference expects exactly two Set arguments")
        s1 = arguments[0]
        s2 = arguments[1]
        if isinstance(s2, XCollectionInstance):
            s2 = s2._data
        if not isinstance(s1, set):
            raise RuntimeErrorX("Set.difference: first argument must be a Set instance")
        if not isinstance(s2, set):
            raise RuntimeErrorX("Set.difference: second argument must be a Set instance")
        return s1 - s2

    def _validate_argument_count(
        self, operation: str, arguments: list[Any], expected: int
    ) -> None:
        if len(arguments) != expected:
            raise RuntimeErrorX(
                f"FileSystem.{operation} expects {expected} argument(s), "
                f"got {len(arguments)}"
            )

