"""Map interfaces: ``interface M { integer key { fields } }``.

An interface whose only member is a ``keyType key { fields }`` entry is a
map type: keys fit the key type and every value is an object shaped by the
entry's fields.  The interface works anywhere a type name does —

    let Participants byId = { 100: { name: "Maya" } };

with per-key diagnostics like ``object<K, V>``, runtime bind checks, a
TypeScript index-signature emit, and the usual ``m[100]`` / ``m.100``
access.  ``key`` is contextual: a field or method simply named ``key`` in
an interface or class still parses when no ``{`` follows.
"""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.ast_nodes import (
    ClassDeclaration,
    FunctionDeclaration,
    InterfaceMapEntry,
    VariableDeclaration,
)
from xlang.cli import main as cli_main
from xlang.codegen import emit
from xlang.config import XConfig
from xlang.formatter import format_source
from xlang.lexer import Lexer
from xlang.module_loader import ModuleLoader
from xlang.parser import Parser
from xlang.runtime import Interpreter


def parse(source, recover=True, source_name="mapif.x"):
    tokens = Lexer(source, source_name, recover_errors=recover).tokenize()
    parser = Parser(tokens, {}, source_name, recover_errors=recover)
    program = parser.parse()
    return program, parser.errors


def _write_entry(source: str) -> Path:
    directory = tempfile.mkdtemp()
    entry_file = Path(directory) / "main.x"
    entry_file.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return entry_file


def check_source(source: str):
    entry_file = _write_entry(source)
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        return_code = cli_main(
            ["check", "--no-config", "--color", "never", str(entry_file)]
        )
    return return_code, output.getvalue() + errors.getvalue()


def run_source(source: str):
    entry_file = _write_entry(source)
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        return_code = cli_main(
            ["run", "--no-config", "--color", "never", str(entry_file)]
        )
    return return_code, output.getvalue() + errors.getvalue()


def run_source_raw(source: str):
    """Interpret directly (no type checker); return the printed lines."""
    entry_file = _write_entry(source)
    program = ModuleLoader(entry_file.parent).load_program(entry_file)
    output: list[str] = []
    Interpreter([], output.append, validate=False).interpret(program)
    return output


def compile_source(source: str) -> str:
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        source_file = project_root / "main.x"
        source_file.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
        loader = ModuleLoader(project_root, XConfig())
        program = loader.load_program(source_file)
        assert not loader.errors, loader.errors
        return emit(program, "typescript", source_name="main.x")


MAP_INTERFACE = """
enum Gender { FEMALE = "female", MALE = "male" }

interface Participants {
  integer key {
    string name,
    Gender gender,
    number age,
    any? foo,
    integer[] array,
    boolean isMarried,
  }
}
"""


class MapInterfaceParserTests(unittest.TestCase):
    def test_key_entry_parses_to_interface_map_entry(self):
        program, errors = parse(MAP_INTERFACE)
        self.assertEqual(errors, [])
        interface = program.declarations[1]
        self.assertIsInstance(interface, ClassDeclaration)
        self.assertTrue(interface.is_interface)
        entry = interface.members[0]
        self.assertIsInstance(entry, InterfaceMapEntry)
        self.assertEqual(entry.key_type, "integer")
        self.assertEqual(
            [(member.name, member.type_name) for member in entry.members],
            [
                ("name", "string"),
                ("gender", "Gender"),
                ("age", "number"),
                ("foo", "any?"),
                ("array", "integer[]"),
                ("isMarried", "boolean"),
            ],
        )

    def test_field_simply_named_key_still_parses(self):
        program, errors = parse("interface M { integer key, string value }")
        self.assertEqual(errors, [])
        members = program.declarations[0].members
        self.assertTrue(all(isinstance(m, VariableDeclaration) for m in members))
        self.assertEqual([m.name for m in members], ["key", "value"])

    def test_method_named_key_still_parses(self):
        program, errors = parse("interface M { integer key(); }")
        self.assertEqual(errors, [])
        self.assertIsInstance(
            program.declarations[0].members[0], FunctionDeclaration
        )

    def test_class_property_block_named_key_is_unchanged(self):
        program, errors = parse("class C { integer key { get thing(); } }")
        self.assertEqual(errors, [])
        member = program.declarations[0].members[0]
        self.assertIsInstance(member, VariableDeclaration)
        self.assertEqual(member.name, "key")

    def test_key_entry_must_declare_a_field(self):
        _, errors = parse("interface M { integer key { } }")
        self.assertTrue(
            any("must declare at least one field" in error.message for error in errors)
        )

    def test_key_entry_cannot_mix_with_other_members(self):
        _, errors = parse(
            "interface M { integer key { string name, } string other, }"
        )
        self.assertTrue(
            any(
                "cannot declare other members" in error.message for error in errors
            )
        )

    def test_only_one_key_entry_allowed(self):
        _, errors = parse(
            "interface M { integer key { string name, } integer key { integer age, } }"
        )
        self.assertTrue(
            any("at most one 'key' entry" in error.message for error in errors)
        )

    def test_key_entry_rejects_initializers(self):
        _, errors = parse('interface M { integer key { string name = "x", } }')
        self.assertTrue(
            any("cannot have an initializer" in error.message for error in errors)
        )


class MapInterfaceCheckTests(unittest.TestCase):
    def test_integer_keyed_literal_is_accepted(self):
        return_code, report = check_source(
            MAP_INTERFACE
            + """
let Participants byId = {
  100: {
    name: "Maya", gender: Gender.FEMALE, age: 30,
    foo: null, array: [1, 2], isMarried: false,
  },
  101: {
    name: "Bo", gender: Gender.MALE, age: 21,
    foo: null, array: [3], isMarried: true,
  },
}
"""
        )
        self.assertEqual(return_code, 0, report)

    def test_string_keyed_map_interface(self):
        return_code, report = check_source(
            """
interface Counts { string key { integer total, } }
let Counts byName = { "a": { total: 1 }, "b": { total: 2 } }
"""
        )
        self.assertEqual(return_code, 0, report)

    def test_string_key_in_integer_map_is_rejected(self):
        return_code, report = check_source(
            MAP_INTERFACE
            + """
let Participants byId = {
  "a": { name: "X", gender: Gender.FEMALE, age: 1,
         foo: null, array: [], isMarried: false },
}
"""
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Object key 'a' is not allowed in 'byId'", report)

    def test_missing_value_field_is_rejected(self):
        return_code, report = check_source(
            """
interface M { integer key { string name, integer age, } }
let M m = { 1: { name: "x" } }
"""
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Value for key '1' in 'm' has the wrong type", report)
        self.assertIn("age", report)

    def test_wrong_value_field_type_is_rejected(self):
        return_code, report = check_source(
            """
interface M { integer key { string name, } }
let M m = { 1: { name: 42 } }
"""
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Value for key '1' in 'm' has the wrong type", report)

    def test_parameter_and_return_positions(self):
        return_code, report = check_source(
            MAP_INTERFACE
            + """
Participants function load() {
  return {
    5: { name: "Ana", gender: Gender.FEMALE, age: 40,
         foo: null, array: [], isMarried: true },
  }
}

void function show(Participants data) {
  print(data[5].name)
}

show(load())
"""
        )
        self.assertEqual(return_code, 0, report)

    def test_new_of_map_interface_is_rejected(self):
        return_code, report = check_source(
            """
interface M { integer key { string name, } }
let x = new M()
"""
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Cannot construct interface 'M'", report)

    def test_class_cannot_implement_map_interface(self):
        return_code, report = check_source(
            """
interface M { integer key { string name, } }
class C implements M { }
"""
        )
        self.assertEqual(return_code, 1)
        self.assertIn("cannot implement map interface 'M'", report)

    def test_unknown_key_type_is_rejected(self):
        return_code, report = check_source(
            "interface M { Bogus key { string name, } }"
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Unknown type 'Bogus'", report)


class MapInterfaceRuntimeTests(unittest.TestCase):
    def test_bind_access_mutate_and_iterate(self):
        return_code, report = run_source(
            MAP_INTERFACE
            + """
let Participants byId = {
  100: {
    name: "Maya", gender: Gender.FEMALE, age: 30,
    foo: null, array: [1, 2], isMarried: false,
  },
  101: {
    name: "Bo", gender: Gender.MALE, age: 21,
    foo: null, array: [3], isMarried: true,
  },
}

print(byId[100].name)
print(byId.101.age)
byId[100].name = "Maya K"
print(byId[100].name)
for (id of byId) {
  print(id, byId[id].name)
}
"""
        )
        self.assertEqual(return_code, 0, report)
        self.assertEqual(
            report.splitlines(),
            ["Maya", "21", "Maya K", "100 Maya K", "101 Bo"],
        )

    def test_runtime_bind_check_without_typechecker(self):
        # The checker normally rejects this first; with validation off the
        # interpreter's own interface match still refuses a non-map value.
        with self.assertRaises(Exception) as caught:
            run_source_raw(
                """
interface M { integer key { string name, } }
let M m = 5
print(m)
"""
            )
        self.assertIn("Expected 'M'", str(caught.exception))

    def test_string_keyed_map_runs(self):
        return_code, report = run_source(
            """
interface Counts { string key { integer total, } }
let Counts byName = { "a": { total: 1 } }
print(byName["a"].total)
"""
        )
        self.assertEqual(return_code, 0, report)
        self.assertEqual(report.splitlines(), ["1"])


class MapInterfaceCodegenTests(unittest.TestCase):
    def test_typescript_index_signature(self):
        output = compile_source(
            """
interface M {
  integer key {
    string name,
    integer age,
  }
}
let M m = { 1: { name: "x", age: 2 } }
"""
        )
        self.assertIn(
            "[key: number]: { name: string; age: number };", output
        )
        self.assertIn("let m: M = { 1: { name: \"x\", age: 2 } };", output)

    def test_string_keyed_map_emits_string_index(self):
        output = compile_source(
            """
interface Counts { string key { integer total, } }
"""
        )
        self.assertIn("[key: string]: { total: number };", output)


class MapInterfaceFormatterTests(unittest.TestCase):
    def test_key_entry_formats_idempotently(self):
        source = textwrap.dedent(
            """\
            interface M {
              integer key {
                string name,
                integer age,
              }
            }
            """
        )
        once = format_source(source)
        self.assertIn("integer key {", once)
        self.assertIn("string name,", once)
        self.assertEqual(format_source(once), once)


if __name__ == "__main__":
    unittest.main()
