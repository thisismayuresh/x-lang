import re
import threading
import unittest
from pathlib import Path

import xlang.stdlib.extended_collections as extended
from xlang.runtime import BuiltinFunction, RuntimeErrorX
from xlang.stdlib.extended_collections import (
    LRUCache,
    LinkedHashMap,
    ThreadSafeMap,
    ThreadSafeSet,
    TreeMap,
    TreeSet,
    build_namespaces,
    from_json,
    to_json,
)


class TreeMapTests(unittest.TestCase):
    def test_keys_iterate_in_ascending_order(self):
        tree = TreeMap()
        for key in ["pear", "apple", "fig", "banana"]:
            tree.put(key, key.upper())
        self.assertEqual(tree.keys_in_order(), ["apple", "banana", "fig", "pear"])
        self.assertEqual(list(tree), ["apple", "banana", "fig", "pear"])
        self.assertEqual(
            tree.values_in_order(), ["APPLE", "BANANA", "FIG", "PEAR"]
        )
        self.assertEqual(
            tree.items(),
            [
                ("apple", "APPLE"),
                ("banana", "BANANA"),
                ("fig", "FIG"),
                ("pear", "PEAR"),
            ],
        )

    def test_put_updates_value_without_changing_sorted_position(self):
        tree = TreeMap()
        tree.put("b", 1)
        tree.put("a", 2)
        tree.put("c", 3)
        tree.put("b", 99)
        self.assertEqual(tree.keys_in_order(), ["a", "b", "c"])
        self.assertEqual(tree.get("b"), 99)
        self.assertEqual(tree.size, 3)

    def test_first_key_and_last_key(self):
        tree = TreeMap({2: "b", 1: "a", 3: "c"})
        self.assertEqual(tree.first_key(), 1)
        self.assertEqual(tree.last_key(), 3)

    def test_first_and_last_key_raise_when_empty(self):
        tree = TreeMap()
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap.first_key: map is empty"):
            tree.first_key()
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap.last_key: map is empty"):
            tree.last_key()

    def test_get_missing_key_raises(self):
        tree = TreeMap({"a": 1})
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap.get: key 'zz' not found"):
            tree.get("zz")
        tree.put("none", None)
        self.assertIsNone(tree.get("none"))

    def test_remove_missing_key_raises_and_present_key_returns_value(self):
        tree = TreeMap({"a": 1})
        with self.assertRaisesRegex(
            RuntimeErrorX, "TreeMap.remove: key 'zz' not found"
        ):
            tree.remove("zz")
        self.assertEqual(tree.remove("a"), 1)
        self.assertFalse(tree.contains_key("a"))
        self.assertEqual(tree.size, 0)

    def test_incomparable_keys_raise(self):
        tree = TreeMap()
        tree.put("a", 1)
        with self.assertRaisesRegex(RuntimeErrorX, "mutually comparable"):
            tree.put(2, 3)

    def test_unhashable_key_raises(self):
        tree = TreeMap()
        with self.assertRaisesRegex(RuntimeErrorX, "mutually comparable|hashable"):
            tree.put([1, 2], "value")
        self.assertTrue(tree.is_empty)

    def test_contains_key_and_container_protocol(self):
        tree = TreeMap({"a": 1})
        self.assertTrue(tree.contains_key("a"))
        self.assertTrue("a" in tree)
        self.assertFalse("b" in tree)
        with self.assertRaisesRegex(RuntimeErrorX, "hashable"):
            tree.contains_key([1])

    def test_size_is_empty_and_clear(self):
        tree = TreeMap()
        self.assertTrue(tree.is_empty)
        self.assertEqual(tree.size, 0)
        tree.put("a", 1)
        self.assertFalse(tree.is_empty)
        self.assertEqual(tree.size, 1)
        self.assertEqual(len(tree), 1)
        tree.clear()
        self.assertTrue(tree.is_empty)
        self.assertEqual(tree.keys_in_order(), [])

    def test_init_from_dict_pairs_and_iterable(self):
        from_dict = TreeMap({"b": 1, "a": 2})
        from_pairs = TreeMap([["b", 1], ["a", 2]])
        from_zip = TreeMap(zip(["b", "a"], [1, 2]))
        copied = TreeMap(from_dict)
        for tree in (from_dict, from_pairs, from_zip, copied):
            self.assertEqual(tree.keys_in_order(), ["a", "b"])
            self.assertEqual(tree.get("a"), 2)

    def test_init_rejects_invalid_entries(self):
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap initial entries"):
            TreeMap(42)
        with self.assertRaisesRegex(RuntimeErrorX, "key, value"):
            TreeMap([["only-key"]])

    def test_iterator_is_a_snapshot(self):
        tree = TreeMap({"b": 1, "a": 2})
        snapshot = tree.iterator()
        tree.put("c", 3)
        tree.remove("a")
        self.assertEqual(list(snapshot), [("a", 2), ("b", 1)])

    def test_repr_shows_sorted_entries(self):
        self.assertEqual(repr(TreeMap({"b": 1, "a": 2})), "TreeMap({'a': 2, 'b': 1})")


class TreeSetTests(unittest.TestCase):
    def test_elements_are_sorted_and_unique(self):
        values = TreeSet([3, 1, 2, 2, 1])
        self.assertEqual(values.to_list(), [1, 2, 3])
        self.assertEqual(list(values), [1, 2, 3])
        self.assertEqual(values.size, 3)

    def test_first_and_last(self):
        values = TreeSet([3, 1, 2])
        self.assertEqual(values.first(), 1)
        self.assertEqual(values.last(), 3)

    def test_first_and_last_raise_when_empty(self):
        values = TreeSet()
        with self.assertRaisesRegex(RuntimeErrorX, "TreeSet.first: set is empty"):
            values.first()
        with self.assertRaisesRegex(RuntimeErrorX, "TreeSet.last: set is empty"):
            values.last()

    def test_remove_present_and_missing(self):
        values = TreeSet([1, 2])
        with self.assertRaisesRegex(
            RuntimeErrorX, "TreeSet.remove: element 9 is not present"
        ):
            values.remove(9)
        values.remove(2)
        self.assertEqual(values.to_list(), [1])
        self.assertFalse(values.contains(2))

    def test_contains_size_and_empty(self):
        values = TreeSet(["b", "a"])
        self.assertTrue(values.contains("a"))
        self.assertTrue("a" in values)
        self.assertFalse("z" in values)
        self.assertEqual(values.size, 2)
        self.assertFalse(values.is_empty)
        values.clear()
        self.assertTrue(values.is_empty)
        self.assertEqual(len(values), 0)

    def test_init_rejects_non_iterable(self):
        with self.assertRaisesRegex(RuntimeErrorX, "TreeSet initial value must be iterable"):
            TreeSet(7)

    def test_unhashable_element_raises(self):
        values = TreeSet()
        with self.assertRaisesRegex(RuntimeErrorX, "hashable"):
            values.add([1])

    def test_iterator_is_a_snapshot(self):
        values = TreeSet([2, 1])
        snapshot = values.iterator()
        values.add(3)
        values.remove(1)
        self.assertEqual(list(snapshot), [1, 2])


class LinkedHashMapTests(unittest.TestCase):
    def test_insertion_order_is_preserved(self):
        ordered = LinkedHashMap([("z", 1), ("a", 2), ("m", 3)])
        self.assertEqual(ordered.keys(), ["z", "a", "m"])
        self.assertEqual(ordered.values(), [1, 2, 3])
        self.assertEqual(ordered.entries(), [("z", 1), ("a", 2), ("m", 3)])
        self.assertEqual(list(ordered), ["z", "a", "m"])
        self.assertEqual([k for k, _ in ordered.iterator()], ["z", "a", "m"])

    def test_overwrite_keeps_position(self):
        ordered = LinkedHashMap()
        ordered.put("z", 1)
        ordered.put("a", 2)
        ordered.put("z", 99)
        self.assertEqual(ordered.keys(), ["z", "a"])
        self.assertEqual(ordered.get("z"), 99)

    def test_remove_then_put_moves_key_to_the_end(self):
        ordered = LinkedHashMap({"b": 1, "a": 2, "c": 3})
        ordered.remove("b")
        ordered.put("b", 4)
        self.assertEqual(ordered.keys(), ["a", "c", "b"])

    def test_get_missing_key_raises(self):
        ordered = LinkedHashMap({"a": 1})
        with self.assertRaisesRegex(
            RuntimeErrorX, "LinkedHashMap.get: key 'zz' not found"
        ):
            ordered.get("zz")

    def test_remove_missing_key_raises(self):
        ordered = LinkedHashMap({"a": 1})
        with self.assertRaisesRegex(
            RuntimeErrorX, "LinkedHashMap.remove: key 'zz' not found"
        ):
            ordered.remove("zz")
        self.assertEqual(ordered.remove("a"), 1)

    def test_size_is_empty_clear_and_contains(self):
        ordered = LinkedHashMap({"a": 1})
        self.assertEqual(ordered.size, 1)
        self.assertFalse(ordered.is_empty)
        self.assertTrue(ordered.contains_key("a"))
        ordered.clear()
        self.assertTrue(ordered.is_empty)
        self.assertEqual(ordered.entries(), [])

    def test_unhashable_key_raises(self):
        ordered = LinkedHashMap()
        with self.assertRaisesRegex(RuntimeErrorX, "keys must be hashable"):
            ordered.put([1], "x")
        with self.assertRaisesRegex(RuntimeErrorX, "keys must be hashable"):
            ordered.get([1])

    def test_init_rejects_invalid_entries(self):
        with self.assertRaisesRegex(RuntimeErrorX, "LinkedHashMap initial entries"):
            LinkedHashMap("not pairs")


class LRUCacheTests(unittest.TestCase):
    def test_capacity_must_be_a_positive_integer(self):
        for capacity in (0, -1, 2.5, "8", True, None):
            with self.assertRaisesRegex(
                RuntimeErrorX, "LRUCache capacity must be a positive integer"
            ):
                LRUCache(capacity)

    def test_default_capacity(self):
        cache = LRUCache()
        self.assertEqual(cache.capacity, 16)

    def test_evicts_least_recently_used_at_capacity(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        self.assertEqual(cache.size, 2)
        self.assertEqual(cache.keys_in_order(), ["b", "c"])
        with self.assertRaisesRegex(RuntimeErrorX, "LRUCache.get: key 'a' not found"):
            cache.get("a")

    def test_get_refreshes_recency(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.get("a"), 1)
        cache.put("c", 3)
        self.assertEqual(cache.keys_in_order(), ["a", "c"])
        self.assertFalse(cache.contains_key("b"))

    def test_put_existing_key_refreshes_without_evicting(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)
        self.assertEqual(cache.size, 2)
        self.assertEqual(cache.keys_in_order(), ["b", "a"])
        self.assertEqual(cache.get("a"), 10)

    def test_get_and_remove_missing_key_raise(self):
        cache = LRUCache(2)
        with self.assertRaisesRegex(RuntimeErrorX, "LRUCache.get: key 'x' not found"):
            cache.get("x")
        with self.assertRaisesRegex(
            RuntimeErrorX, "LRUCache.remove: key 'x' not found"
        ):
            cache.remove("x")

    def test_remove_clear_size_and_order(self):
        cache = LRUCache(3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        self.assertEqual(cache.remove("b"), 2)
        self.assertEqual(cache.keys_in_order(), ["a", "c"])
        self.assertEqual(cache.size, 2)
        self.assertEqual(
            [k for k, _ in cache.iterator()], ["a", "c"]
        )
        self.assertFalse(cache.is_empty)
        cache.clear()
        self.assertTrue(cache.is_empty)
        self.assertEqual(list(cache), [])

    def test_capacity_bound_holds_after_many_inserts(self):
        cache = LRUCache(4)
        for index in range(50):
            cache.put(f"key-{index}", index)
        self.assertEqual(cache.size, 4)
        self.assertEqual(
            cache.keys_in_order(),
            ["key-46", "key-47", "key-48", "key-49"],
        )

    def test_repr_shows_capacity_and_entries(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        self.assertEqual(
            repr(cache), "LRUCache(capacity=2, entries=[('a', 1)])"
        )


class ThreadSafeTests(unittest.TestCase):
    def test_locked_read_modify_write_is_atomic_across_threads(self):
        safe = ThreadSafeMap()
        safe.put("counter", 0)
        workers = 8
        increments = 500

        def bump():
            for _ in range(increments):
                with safe.locked():
                    safe.put("counter", safe.get("counter") + 1)

        threads = [threading.Thread(target=bump) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(safe.get("counter"), workers * increments)
        self.assertEqual(safe.size, 1)

    def test_concurrent_puts_and_snapshot_reads_do_not_fail(self):
        safe = ThreadSafeMap()
        per_thread = 250
        writer_count = 4
        errors = []

        def write(offset):
            try:
                for index in range(per_thread):
                    safe.put(f"key-{offset}-{index}", index)
            except Exception as error:
                errors.append(error)

        def read():
            try:
                for _ in range(100):
                    safe.entries()
                    len(list(safe.iterator()))
            except Exception as error:
                errors.append(error)

        writers = [
            threading.Thread(target=write, args=(offset,))
            for offset in range(writer_count)
        ]
        readers = [threading.Thread(target=read) for _ in range(2)]
        for thread in writers + readers:
            thread.start()
        for thread in writers + readers:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(safe.size, writer_count * per_thread)

    def test_concurrent_set_adds_are_not_lost(self):
        safe = ThreadSafeSet()
        per_thread = 250
        worker_count = 8

        def fill(offset):
            for index in range(per_thread):
                safe.add(offset * per_thread + index)

        threads = [threading.Thread(target=fill, args=(i,)) for i in range(worker_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(safe.size, worker_count * per_thread)
        self.assertEqual(len(safe.to_list()), worker_count * per_thread)

    def test_iteration_uses_snapshots(self):
        safe = ThreadSafeMap(TreeMap({"b": 1, "a": 2}))
        keys = safe.iterator()
        pairs = safe.entries()
        safe.put("c", 3)
        safe.remove("a")
        self.assertEqual([k for k, _ in keys], ["a", "b"])
        self.assertEqual(pairs, [("a", 2), ("b", 1)])
        self.assertEqual(safe.size, 2)
        self.assertEqual(list(safe), ["b", "c"])

        values = ThreadSafeSet(TreeSet([2, 1]))
        elements = values.iterator()
        values.add(3)
        self.assertEqual(list(elements), [1, 2])

    def test_locked_yields_the_wrapped_structure(self):
        safe = ThreadSafeMap(TreeMap({"a": 1}))
        with safe.locked() as inner:
            self.assertIsInstance(inner, TreeMap)
            inner.put("b", inner.get("a") + 1)
        self.assertEqual(safe.entries(), [("a", 1), ("b", 2)])

        values = ThreadSafeSet()
        with values.locked() as inner:
            inner.add(5)
        self.assertEqual(values.to_list(), [5])

    def test_wraps_only_matching_structures(self):
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap or LinkedHashMap"):
            ThreadSafeMap({"a": 1})
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap or LinkedHashMap"):
            ThreadSafeMap(TreeSet())
        with self.assertRaisesRegex(RuntimeErrorX, "TreeSet"):
            ThreadSafeSet(set())
        with ThreadSafeMap().locked() as inner:
            self.assertIsInstance(inner, TreeMap)

    def test_kind_reports_wrapped_structure(self):
        self.assertEqual(ThreadSafeMap().kind, "tree")
        self.assertEqual(ThreadSafeMap(LinkedHashMap()).kind, "linked")

    def test_wrapped_errors_propagate(self):
        safe = ThreadSafeMap()
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap.get: key 'x' not found"):
            safe.get("x")
        values = ThreadSafeSet()
        with self.assertRaisesRegex(RuntimeErrorX, "TreeSet.remove"):
            values.remove(1)

    def test_map_and_set_basic_operations(self):
        safe = ThreadSafeMap(TreeMap())
        safe.put("a", 1)
        safe.put("b", 2)
        self.assertTrue(safe.contains_key("a"))
        self.assertTrue("a" in safe)
        self.assertEqual(len(safe), 2)
        self.assertFalse(safe.is_empty)
        self.assertEqual(safe.remove("a"), 1)
        safe.clear()
        self.assertTrue(safe.is_empty)

        values = ThreadSafeSet(TreeSet([2, 1]))
        self.assertTrue(values.contains(1))
        self.assertTrue(2 in values)
        values.remove(1)
        self.assertEqual(values.to_list(), [2])
        values.clear()
        self.assertTrue(values.is_empty)


class SerializationTests(unittest.TestCase):
    def round_trip(self, value):
        restored = from_json(to_json(value))
        self.assertIs(type(restored), type(value))
        return restored

    def test_treemap_round_trip(self):
        tree = TreeMap({"b": 1, "a": 2, "c": 3})
        restored = self.round_trip(tree)
        self.assertEqual(restored.items(), tree.items())
        self.assertEqual(restored.keys_in_order(), ["a", "b", "c"])

    def test_treeset_round_trip(self):
        values = TreeSet([3, 1, 2])
        restored = self.round_trip(values)
        self.assertEqual(restored.to_list(), [1, 2, 3])

    def test_linked_hash_map_round_trip(self):
        ordered = LinkedHashMap([("z", 1), ("a", 2)])
        restored = self.round_trip(ordered)
        self.assertEqual(restored.keys(), ["z", "a"])
        self.assertEqual(restored.entries(), [("z", 1), ("a", 2)])

    def test_lru_cache_round_trip_preserves_capacity_and_order(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")
        restored = self.round_trip(cache)
        self.assertEqual(restored.capacity, 2)
        self.assertEqual(restored.keys_in_order(), ["b", "a"])

    def test_thread_safe_wrappers_round_trip(self):
        safe_map = ThreadSafeMap(LinkedHashMap({"b": 1, "a": 2}))
        restored_map = self.round_trip(safe_map)
        self.assertEqual(restored_map.kind, "linked")
        self.assertEqual(restored_map.entries(), [("b", 1), ("a", 2)])

        safe_set = ThreadSafeSet(TreeSet([2, 1]))
        restored_set = self.round_trip(safe_set)
        self.assertEqual(restored_set.to_list(), [1, 2])

    def test_nested_structures_round_trip(self):
        document = {
            "maps": [TreeMap({"b": 1, "a": 2})],
            "set": TreeSet([3, 1]),
            "lru": LRUCache(4),
            "count": 3,
        }
        restored = self.round_trip(document)
        self.assertIsInstance(restored["maps"][0], TreeMap)
        self.assertEqual(restored["maps"][0].keys_in_order(), ["a", "b"])
        self.assertIsInstance(restored["set"], TreeSet)
        self.assertEqual(restored["set"].to_list(), [1, 3])
        self.assertIsInstance(restored["lru"], LRUCache)
        self.assertEqual(restored["lru"].capacity, 4)
        self.assertEqual(restored["count"], 3)

    def test_plain_values_round_trip(self):
        for value in (
            {"a": 1, "b": [1, 2, {"c": None}]},
            [1, "x", True, False, 2.5, None],
            42,
            "text",
            None,
            {"nested": {"deep": [True]}},
        ):
            restored = self.round_trip(value)
            self.assertEqual(restored, value)

    def test_plain_set_round_trip(self):
        restored = self.round_trip({3, 1, 2})
        self.assertEqual(restored, {1, 2, 3})

    def test_dict_with_non_string_keys_round_trip(self):
        for value in ({1: "one", 2: "two"}, {"a": 1, 2: "b"}, {None: 1}):
            restored = self.round_trip(value)
            self.assertEqual(restored, value)

    def test_dict_containing_reserved_tag_key_round_trips(self):
        value = {"__xtype__": "custom", "payload": [1, 2]}
        restored = self.round_trip(value)
        self.assertEqual(restored, value)

    def test_class_json_methods_round_trip(self):
        structures = [
            TreeMap({"b": 1, "a": 2}),
            TreeSet([2, 1]),
            LinkedHashMap([("b", 1), ("a", 2)]),
            LRUCache(3),
            ThreadSafeMap(),
            ThreadSafeSet(),
        ]
        for structure in structures:
            restored = type(structure).from_json(structure.to_json())
            self.assertIs(type(restored), type(structure))
            self.assertEqual(restored.size, structure.size)

    def test_invalid_json_raises(self):
        with self.assertRaisesRegex(RuntimeErrorX, "from_json: invalid JSON"):
            from_json("{not json")

    def test_non_string_argument_raises(self):
        with self.assertRaisesRegex(RuntimeErrorX, "from_json expects a JSON string"):
            from_json(42)

    def test_unknown_type_tag_raises(self):
        with self.assertRaisesRegex(RuntimeErrorX, "unknown type tag"):
            from_json('{"__xtype__": "Bogus"}')

    def test_malformed_documents_raise(self):
        with self.assertRaisesRegex(RuntimeErrorX, "missing 'entries'"):
            from_json('{"__xtype__": "TreeMap"}')
        with self.assertRaisesRegex(RuntimeErrorX, "key, value"):
            from_json('{"__xtype__": "TreeMap", "entries": [[1]]}')
        with self.assertRaisesRegex(RuntimeErrorX, "capacity"):
            from_json('{"__xtype__": "LRUCache", "capacity": 0, "entries": []}')
        with self.assertRaisesRegex(RuntimeErrorX, "kind"):
            from_json(
                '{"__xtype__": "ThreadSafeMap", "kind": "hash", "entries": []}'
            )

    def test_from_json_type_mismatch_raises(self):
        document = TreeSet([1]).to_json()
        with self.assertRaisesRegex(RuntimeErrorX, "expected a TreeMap document"):
            TreeMap.from_json(document)

    def test_unsupported_value_raises(self):
        with self.assertRaisesRegex(RuntimeErrorX, "cannot serialise values of type"):
            to_json(object())
        with self.assertRaisesRegex(RuntimeErrorX, "cannot serialise values of type"):
            to_json({"fn": print})


class NamespaceTests(unittest.TestCase):
    def setUp(self):
        self.namespaces = build_namespaces()
        self.expected_types = {
            "TreeMap": TreeMap,
            "TreeSet": TreeSet,
            "LinkedHashMap": LinkedHashMap,
            "LRUCache": LRUCache,
            "ThreadSafeMap": ThreadSafeMap,
            "ThreadSafeSet": ThreadSafeSet,
        }

    def test_returns_six_qualified_builtin_tables(self):
        self.assertEqual(set(self.namespaces), set(self.expected_types))
        for type_name, table in self.namespaces.items():
            self.assertIsInstance(table, dict)
            self.assertIn("create", table)
            for method, builtin in table.items():
                self.assertIsInstance(builtin, BuiltinFunction)
                self.assertEqual(builtin.name, f"{type_name}.{method}")

    def test_create_builds_the_matching_structure(self):
        for type_name, cls in self.expected_types.items():
            instance = self.namespaces[type_name]["create"].call([])
            self.assertIs(type(instance), cls)

    def test_create_rejects_extra_arguments(self):
        for table in self.namespaces.values():
            with self.assertRaisesRegex(RuntimeErrorX, "accepts at most one argument"):
                table["create"].call([1, 2, 3])

    def test_every_method_entry_checks_arity(self):
        for type_name, table in self.namespaces.items():
            for method, builtin in table.items():
                if method == "create":
                    continue
                with self.assertRaisesRegex(
                    RuntimeErrorX, f"{type_name}.{method} expects"
                ):
                    builtin.call([])

    def test_methods_check_the_receiver_type(self):
        with self.assertRaisesRegex(RuntimeErrorX, "expects a TreeMap instance"):
            self.namespaces["TreeMap"]["put"].call(["not a map", "k", "v"])
        with self.assertRaisesRegex(RuntimeErrorX, "expects a LRUCache instance"):
            self.namespaces["LRUCache"]["size"].call([TreeMap()])
        with self.assertRaisesRegex(RuntimeErrorX, "expects a TreeSet instance"):
            self.namespaces["TreeSet"]["add"].call([{"a": 1}, 1])
        with self.assertRaisesRegex(RuntimeErrorX, "expects a ThreadSafeMap instance"):
            self.namespaces["ThreadSafeMap"]["get"].call([TreeSet(), "k"])

    def test_hashmap_style_functional_flow(self):
        table = self.namespaces["TreeMap"]
        tree = table["create"].call([])
        table["put"].call([tree, "b", 1])
        table["put"].call([tree, "a", 2])
        self.assertEqual(table["keysInOrder"].call([tree]), ["a", "b"])
        self.assertEqual(table["valuesInOrder"].call([tree]), [2, 1])
        self.assertEqual(table["items"].call([tree]), [("a", 2), ("b", 1)])
        self.assertEqual(table["get"].call([tree, "a"]), 2)
        self.assertTrue(table["containsKey"].call([tree, "b"]))
        self.assertEqual(table["firstKey"].call([tree]), "a")
        self.assertEqual(table["lastKey"].call([tree]), "b")
        self.assertEqual(table["size"].call([tree]), 2)
        self.assertFalse(table["isEmpty"].call([tree]))
        with self.assertRaisesRegex(RuntimeErrorX, "TreeMap.get: key 'zz' not found"):
            table["get"].call([tree, "zz"])
        with self.assertRaisesRegex(RuntimeErrorX, "expects 3 argument"):
            table["put"].call([tree, "a"])
        table["clear"].call([tree])
        self.assertTrue(table["isEmpty"].call([tree]))

    def test_treeset_flow(self):
        table = self.namespaces["TreeSet"]
        values = table["create"].call([[3, 1, 2]])
        table["add"].call([values, 1])
        table["add"].call([values, 4])
        self.assertEqual(table["toArray"].call([values]), [1, 2, 3, 4])
        self.assertTrue(table["contains"].call([values, 2]))
        self.assertEqual(table["first"].call([values]), 1)
        self.assertEqual(table["last"].call([values]), 4)
        self.assertEqual(table["size"].call([values]), 4)
        with self.assertRaisesRegex(RuntimeErrorX, "not present"):
            table["remove"].call([values, 99])
        table["remove"].call([values, 4])
        self.assertEqual(table["size"].call([values]), 3)

    def test_linked_hash_map_flow(self):
        table = self.namespaces["LinkedHashMap"]
        ordered = table["create"].call([])
        table["put"].call([ordered, "z", 1])
        table["put"].call([ordered, "a", 2])
        table["put"].call([ordered, "z", 3])
        self.assertEqual(table["keys"].call([ordered]), ["z", "a"])
        self.assertEqual(table["values"].call([ordered]), [3, 2])
        self.assertEqual(table["entries"].call([ordered]), [("z", 3), ("a", 2)])
        self.assertEqual(table["remove"].call([ordered, "a"]), 2)
        self.assertEqual(table["size"].call([ordered]), 1)

    def test_lru_cache_flow(self):
        table = self.namespaces["LRUCache"]
        cache = table["create"].call([2])
        self.assertEqual(table["capacity"].call([cache]), 2)
        table["put"].call([cache, "a", 1])
        table["put"].call([cache, "b", 2])
        self.assertEqual(table["get"].call([cache, "a"]), 1)
        table["put"].call([cache, "c", 3])
        self.assertEqual(table["keysInOrder"].call([cache]), ["a", "c"])
        self.assertEqual(table["size"].call([cache]), 2)
        with self.assertRaisesRegex(RuntimeErrorX, "positive integer"):
            self.namespaces["LRUCache"]["create"].call([0])

    def test_thread_safe_flow(self):
        map_table = self.namespaces["ThreadSafeMap"]
        safe = map_table["create"].call(["linked"])
        self.assertEqual(safe.kind, "linked")
        map_table["put"].call([safe, "a", 1])
        self.assertEqual(map_table["get"].call([safe, "a"]), 1)
        self.assertEqual(map_table["entries"].call([safe]), [("a", 1)])
        with self.assertRaisesRegex(RuntimeErrorX, "argument must be"):
            map_table["create"].call(["bogus"])

        set_table = self.namespaces["ThreadSafeSet"]
        values = set_table["create"].call([])
        set_table["add"].call([values, 2])
        set_table["add"].call([values, 1])
        self.assertEqual(set_table["toArray"].call([values]), [1, 2])
        self.assertTrue(set_table["contains"].call([values, 1]))

    def test_json_entries_round_trip_through_tables(self):
        table = self.namespaces["TreeMap"]
        tree = table["create"].call([])
        table["put"].call([tree, "b", 1])
        table["put"].call([tree, "a", 2])
        document = table["toJSON"].call([tree])
        restored = table["fromJSON"].call([document])
        self.assertIs(type(restored), TreeMap)
        self.assertEqual(table["items"].call([restored]), table["items"].call([tree]))
        with self.assertRaisesRegex(RuntimeErrorX, "expects a JSON string"):
            table["fromJSON"].call([42])

    def test_module_source_never_imports_the_interpreter(self):
        source = Path(extended.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(
            source,
            re.compile(r"^\s*(?:from|import)\s+[\w.]*interpreter", re.MULTILINE),
        )
        self.assertNotRegex(
            source,
            re.compile(r"^\s*from\s+\.{1,2}collections\b", re.MULTILINE),
        )


if __name__ == "__main__":
    unittest.main()
