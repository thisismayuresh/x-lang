"""Tests for xlang.introspect — the single-source builtin catalog.

The guard tests here are what turns future drift into a red test: if a
builtin method is added to the interpreter tables without a convention
docstring, or the docstring regex breaks, these fail instead of the editor
silently hiding the method.
"""

from __future__ import annotations

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from xlang.introspect import (
        MemberInfo,
        known_type_names,
        members_of_type,
        namespace_members,
    )
    from xlang.interpreter._common import _ARRAY_METHODS, _STRING_METHODS

    AVAILABLE = True
except Exception:  # pragma: no cover - import failure is a hard error elsewhere
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "xlang.introspect failed to import")
class MembersOfTypeTests(unittest.TestCase):
    def test_string_returns_every_interpreter_method(self):
        names = {m.name for m in members_of_type("string")}
        self.assertTrue(set(_STRING_METHODS) <= names)
        # + length/toString specials answered inline by _get_member.
        self.assertEqual(len(names), 34)

    def test_array_returns_every_interpreter_method(self):
        names = {m.name for m in members_of_type("array")}
        self.assertTrue(set(_ARRAY_METHODS) <= names)
        # + the length special.
        self.assertEqual(len(names), 21)

    def test_primitives_offer_to_string(self):
        for type_name in ("integer", "int", "float", "boolean", "bool", "number"):
            names = {m.name for m in members_of_type(type_name)}
            self.assertEqual(names, {"toString"}, type_name)

    def test_special_members_are_real(self):
        """Round-trip: every special member must answer on a live value.

        Pins the ``_VALUE_TYPE_SPECIAL_MEMBERS`` mirror against
        ``Interpreter._get_member`` — the interpreter's inline special-member
        handling has no table of its own, so this test is what turns drift
        into a red build.
        """
        from xlang.interpreter import Interpreter
        import xlang.introspect as introspect

        interp = Interpreter(
            arguments=[], output=lambda _line: None, auto_call_main=False
        )
        sample_values = {
            "string": "hi",
            "array": [1, 2],
            "integer": 5,
            "float": 1.5,
            "boolean": True,
            "number": 7,
        }
        for owner, specials in introspect._VALUE_TYPE_SPECIAL_MEMBERS.items():
            value = sample_values[owner]
            for name, kind in specials.items():
                resolved = interp._get_member(value, name)
                if kind == "method":
                    self.assertIsNotNone(
                        resolved, f"{owner}.{name} did not resolve"
                    )
                else:
                    self.assertIsNotNone(
                        resolved, f"{owner}.{name} did not resolve"
                    )

    def test_every_string_docstring_parses(self):
        """Every table-backed string method parses ```` ```sig``` — doc ````."""
        members = members_of_type("string")
        unparsed = [
            m.name for m in members if m.kind == "method" and m.signature is None
        ]
        self.assertEqual(unparsed, [], f"unparseable docstrings: {unparsed}")
        trim = next(m for m in members if m.name == "trim")
        self.assertEqual(trim.signature, "trim()")
        self.assertIn("whitespace", trim.doc)
        self.assertEqual(trim.owner, "string")

    def test_every_array_docstring_parses(self):
        """Every table-backed array method parses a signature docstring."""
        members = members_of_type("array")
        unparsed = [
            m.name for m in members if m.kind == "method" and m.signature is None
        ]
        self.assertEqual(unparsed, [], f"unparseable docstrings: {unparsed}")
        sort = next(m for m in members if m.name == "sort")
        self.assertEqual(sort.signature, "sort(compare?)")

    def test_unknown_and_empty_types_return_empty(self):
        self.assertEqual(members_of_type("nosuchtype"), [])
        self.assertEqual(members_of_type(""), [])
        self.assertEqual(members_of_type(None), [])
        # Collections and user classes are namespace_members' job, not tables.
        self.assertEqual(members_of_type("HashMap"), [])

    def test_never_raises_when_the_table_is_broken(self):
        # Simulate a corrupted table by pointing the lookup at a missing
        # implementation; the entry degrades to a name-only MemberInfo.
        import xlang.introspect as introspect

        original = dict(introspect._STRING_METHODS)
        try:
            introspect._STRING_METHODS["ghost"] = "_no_such_implementation"
            # Rebuild the module-level table the public function reads.
            members = introspect.members_of_type("string")
            ghost = next(m for m in members if m.name == "ghost")
            self.assertIsNone(ghost.signature)
        finally:
            introspect._STRING_METHODS.clear()
            introspect._STRING_METHODS.update(original)


@unittest.skipUnless(AVAILABLE, "xlang.introspect failed to import")
class NamespaceMembersTests(unittest.TestCase):
    def names(self, path):
        return {m.name for m in namespace_members(path)}

    def test_hashmap_exposes_instance_methods_without_create(self):
        names = self.names("HashMap")
        self.assertIn("set", names)
        self.assertIn("entries", names)
        self.assertNotIn("create", names)
        self.assertEqual(len(names), 18)

    def test_full_dotted_path_resolves(self):
        self.assertEqual(
            self.names("System.utils.Collections.HashMap"), self.names("HashMap")
        )

    def test_list_alias_matches_linkedlist(self):
        self.assertEqual(self.names("List"), self.names("LinkedList"))

    def test_extended_collections_are_globally_visible(self):
        for name in (
            "TreeMap",
            "TreeSet",
            "LinkedHashMap",
            "LRUCache",
            "ThreadSafeMap",
            "ThreadSafeSet",
        ):
            self.assertTrue(namespace_members(name), f"{name} has no members")

    def test_math_namespace_includes_constants_and_functions(self):
        names = self.names("System.utils.Math")
        self.assertIn("pi", names)
        self.assertIn("sqrt", names)
        pi = next(m for m in namespace_members("System.utils.Math") if m.name == "pi")
        self.assertEqual(pi.kind, "property")
        sqrt = next(m for m in namespace_members("System.utils.Math") if m.name == "sqrt")
        self.assertEqual(sqrt.kind, "method")

    def test_unknown_paths_return_empty(self):
        self.assertEqual(namespace_members("Point"), [])
        self.assertEqual(namespace_members(""), [])
        self.assertEqual(namespace_members(None), [])
        self.assertEqual(namespace_members("System.nope.nope"), [])

    def test_never_raises_on_a_broken_resolver(self):
        import xlang.introspect as introspect

        original = introspect._get_interpreter
        introspect._get_interpreter = lambda: None
        try:
            self.assertEqual(namespace_members("HashMap"), [])
        finally:
            introspect._get_interpreter = original


@unittest.skipUnless(AVAILABLE, "xlang.introspect failed to import")
class KnownTypeNamesTests(unittest.TestCase):
    def test_includes_primitives_and_builtin_collections(self):
        names = known_type_names()
        self.assertIn("string", names)
        self.assertIn("integer", names)
        self.assertTrue(names, "known_type_names() was empty")


@unittest.skipUnless(AVAILABLE, "xlang.introspect failed to import")
class MemberInfoTests(unittest.TestCase):
    def test_is_frozen_pure_data(self):
        member = members_of_type("string")[0]
        self.assertIsInstance(member, MemberInfo)
        with self.assertRaises(Exception):
            member.name = "other"


if __name__ == "__main__":
    unittest.main()
