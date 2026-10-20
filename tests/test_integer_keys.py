"""Integer (and float) keys in object literals — parser, checker, runtime, formatter.

``Object<integer, T>`` maps take integer keys: ``{ 200: {...} }`` parses with
``key_is_number`` set, typechecks against integer-keyed object types (and
rejects string keys there), runs with ``m[200]`` subscripting (``m[200]`` and
``m["200"]`` are different keys), destructures as ``{ 200: x }``, and formats
back out with the numeric key intact.
"""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.ast_nodes import Index, Literal, Member, OptionalChain
from xlang.cli import main as cli_main
from xlang.formatter import format_source
from xlang.lexer import Lexer
from xlang.module_loader import ModuleLoader
from xlang.parser import Parser
from xlang.runtime import Interpreter


def parse(source, recover=True, source_name="intkey.x"):
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


class IntegerKeyParserTests(unittest.TestCase):
    def test_number_key_is_recorded_as_numeric(self):
        program, errors = parse("let m = { 200: 1, \"x\": 2 };")
        self.assertEqual(errors, [])
        entries = program.declarations[0].initializer.entries
        self.assertEqual(entries[0].key, "200")
        self.assertTrue(entries[0].key_is_number)
        self.assertEqual(entries[1].key, "x")
        self.assertFalse(entries[1].key_is_number)

    def test_float_key_is_numeric_too(self):
        program, errors = parse("let m = { 1.5: \"a\" };")
        self.assertEqual(errors, [])
        entry = program.declarations[0].initializer.entries[0]
        self.assertTrue(entry.key_is_number)
        self.assertEqual(entry.key, "1.5")

    def test_number_key_shorthand_is_a_parse_error(self):
        _, errors = parse("let m = { 200 };")
        self.assertTrue(
            any(
                "Expected ':' after object field name" in error.message
                for error in errors
            ),
            errors,
        )

    def test_numeric_destructuring_field_parses(self):
        program, errors = parse("const { 200: x } = m;")
        self.assertEqual(errors, [])
        pattern = program.declarations[0].pattern
        self.assertEqual(pattern.fields[0][0], "200")

    def test_numeric_destructuring_shorthand_is_a_parse_error(self):
        _, errors = parse("const { 200 } = m;")
        self.assertTrue(
            any(
                "Expected ':' after numeric binding field" in error.message
                for error in errors
            ),
            errors,
        )


class IntegerKeyTypecheckTests(unittest.TestCase):
    def test_integer_keys_match_an_integer_object_type(self):
        code, output = check_source(
            """
            let m: object<integer, integer> = { 200: 1, 210: 2 }
            print(m)
            """
        )
        self.assertEqual(code, 0, output)

    def test_string_key_is_rejected_for_an_integer_object_type(self):
        code, output = check_source(
            """
            let m: object<integer, integer> = { "200": 1 }
            print(m)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn("Object key '200' is not allowed in 'm'", output)

    def test_integer_key_is_rejected_for_a_string_object_type(self):
        code, output = check_source(
            """
            let m: object<string, integer> = { 200: 1 }
            print(m)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn("Object key '200' is not allowed in 'm'", output)

    def test_wrong_value_type_names_the_numeric_key(self):
        code, output = check_source(
            """
            let m: object<integer, integer> = { 200: "no" }
            print(m)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "Value for key '200' in 'm' has the wrong type", output
        )

    def test_float_key_matches_a_float_object_type(self):
        code, output = check_source(
            """
            let m: object<float, integer> = { 1.5: 1 }
            print(m)
            """
        )
        self.assertEqual(code, 0, output)

    def test_float_key_is_rejected_for_an_integer_object_type(self):
        code, output = check_source(
            """
            let m: object<integer, integer> = { 1.5: 1 }
            print(m)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn("Object key '1.5' is not allowed in 'm'", output)

    def test_nested_object_values_with_numeric_keys(self):
        code, output = check_source(
            """
            let m: object<integer, object<string, string|integer>> = {
              200: { "name": "A", "age": 21 }
            }
            print(m)
            """
        )
        self.assertEqual(code, 0, output)

    def test_function_returning_an_integer_keyed_object(self):
        code, output = check_source(
            """
            type P = Object<integer, Object<string, string|integer>>

            P function make() {
              return {
                200: { "name": "Ayesha", "age": 21 },
                210: { "name": "Zoya", "age": "unknown" }
              }
            }

            const P made = make()
            print(made)
            """
        )
        self.assertEqual(code, 0, output)

    def test_dot_number_access_is_typechecked(self):
        code, output = check_source(
            """
            let m: object<integer, integer> = { 200: 1 }
            print(m.200)
            """
        )
        self.assertEqual(code, 0, output)

    def test_incompatible_return_reports_readable_record_types(self):
        code, output = check_source(
            """
            Object<integer, integer> function f() {
              return { 200: "no" }
            }
            """
        )
        self.assertEqual(code, 1)
        self.assertIn("{ 200: string }", output)
        self.assertNotIn("record{", output)


class IntegerKeyRuntimeTests(unittest.TestCase):
    def test_print_shows_integer_keys(self):
        output = run_source_raw('let m = { 200: 1 }\nprint(m)\n')
        self.assertEqual(output, ["{200: 1}"])

    def test_integer_and_string_keys_are_distinct_entries(self):
        output = run_source_raw(
            'let m = { 200: "int", "200": "str" }\nprint(m[200], m["200"])\n'
        )
        self.assertEqual(output, ["int str"])

    def test_computed_integer_subscript(self):
        output = run_source_raw(
            "let m = { 200: 1 }\nlet k = 200\nprint(m[k])\n"
        )
        self.assertEqual(output, ["1"])

    def test_string_subscript_on_an_integer_keyed_map_fails(self):
        code, output = run_source('let m = { 200: 1 }\nprint(m["200"])\n')
        self.assertEqual(code, 1)
        self.assertIn("IndexOutOfBounds", output)

    def test_numeric_field_destructuring(self):
        output = run_source_raw(
            "const { 200: x } = { 200: 7 }\nprint(x)\n"
        )
        self.assertEqual(output, ["7"])

    def test_numeric_match_pattern(self):
        output = run_source_raw(
            "print(match (200) { 200 => \"yes\", _ => \"no\" })\n"
        )
        self.assertEqual(output, ["yes"])

    def test_numeric_object_match_pattern(self):
        output = run_source_raw(
            "print(match ({ 200: 7 }) { { 200: v } => v, _ => 0 })\n"
        )
        self.assertEqual(output, ["7"])

    def test_dot_number_access_parses_as_subscript(self):
        program, errors = parse("let a = m.200.array[0];")
        self.assertEqual(errors, [])
        expression = program.declarations[0].initializer
        self.assertIsInstance(expression, Index)
        self.assertEqual(expression.index.value, 0)
        member = expression.object
        self.assertIsInstance(member, Member)
        self.assertEqual(member.name, "array")
        subscript = member.object
        self.assertIsInstance(subscript, Index)
        self.assertIsInstance(subscript.index, Literal)
        self.assertEqual(subscript.index.value, 200)

    def test_dot_optional_number_access_parses_as_index_segment(self):
        program, errors = parse("let a = m?.200;")
        self.assertEqual(errors, [])
        expression = program.declarations[0].initializer
        self.assertIsInstance(expression, OptionalChain)
        segment = expression.segments[0]
        self.assertEqual(segment.kind, "index")
        self.assertTrue(segment.optional)
        self.assertEqual(segment.value.value, 200)

    def test_dot_number_access_runs(self):
        output = run_source_raw(
            "let m = { 200: { \"array\": [7] } }\n"
            "print(m.200.array[0], m.200)\n"
        )
        self.assertEqual(output, ["7 {array: [7]}"])

    def test_dot_number_access_with_cli(self):
        code, output = run_source(
            """
            let m = { 200: 1, 210: 2 }
            print(m.200, m.210)
            """
        )
        self.assertEqual(code, 0, output)
        self.assertIn("1 2", output)


class IntegerKeyFormatterTests(unittest.TestCase):
    def assert_formats(self, source, expected):
        formatted = format_source(source, "<test>")
        self.assertEqual(formatted, expected)
        self.assertEqual(format_source(formatted, "<test>"), expected)

    def test_numeric_keys_stay_inline(self):
        self.assert_formats(
            "let m={200:1,210:2};\n",
            "let m = { 200: 1, 210: 2 };\n",
        )

    def test_float_and_string_keys_keep_their_spelling(self):
        self.assert_formats(
            'let m={1.5:"a","200":1};\n',
            'let m = { 1.5: "a", "200": 1 };\n',
        )


if __name__ == "__main__":
    unittest.main()
