"""parseFloat / parseInt builtins and System.utils.JSON.parse.

Covers:

* ``parseFloat(text)`` — strict whole-string decimal parse (sign, point,
  exponent, surrounding whitespace), ``number`` result, and
  ``IllegalArgumentException`` on empty/garbage/non-string input
* ``parseInt(text, radix?)`` — radix 2–36 integer parsing, sign, and
  strict rejection of digits outside the radix
* ``System.utils.JSON.parse(text)`` — RFC 8259 values (objects, arrays,
  scalars), round-trip with ``toJSON``, rejection of malformed JSON and the
  non-standard ``NaN``/``Infinity`` extensions, and the unqualified
  ``import System.utils.JSON.parse`` binding
* the type checker's declared result types: ``parseFloat`` → ``float``,
  ``parseInt`` → ``integer`` (mismatching assignments are type errors)
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.cli import main as cli_main
from xlang.config import XConfig
from xlang.interpreter import Interpreter
from xlang.module_loader import ModuleLoader
from xlang.runtime import RuntimeErrorX


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def run_x(source: str, config: XConfig | None = None) -> list[str]:
    """Run *source* and return the printed lines."""
    config = config or XConfig()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        entry = project_root / "main.x"
        entry.write_text(dedent(source), encoding="utf-8")
        loader = ModuleLoader(project_root, config=config)
        program = loader.load_program(entry)
        output: list[str] = []
        Interpreter(config=config, output=output.append).interpret(program)
        return output


def run_x_error(source: str, config: XConfig | None = None) -> RuntimeErrorX:
    """Run *source* and return the raised ``RuntimeErrorX``."""
    config = config or XConfig()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        entry = project_root / "main.x"
        entry.write_text(dedent(source), encoding="utf-8")
        loader = ModuleLoader(project_root, config=config)
        program = loader.load_program(entry)
        try:
            Interpreter(config=config, output=lambda _line: None).interpret(program)
        except RuntimeErrorX as error:
            return error
    raise AssertionError("expected the program to raise RuntimeErrorX")


def check_source(source: str) -> tuple[int, str, str]:
    """Run ``x check --no-config`` on *source*; return (code, out, err)."""
    output = io.StringIO()
    errors = io.StringIO()
    with tempfile.TemporaryDirectory() as temporary_directory:
        source_file = Path(temporary_directory) / "main.x"
        source_file.write_text(dedent(source), encoding="utf-8")
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["check", "--no-config", "--color", "never", str(source_file)]
            )
    return return_code, output.getvalue(), errors.getvalue()


class ParseFloatTests(unittest.TestCase):
    def test_valid_decimals_print_with_number_type(self):
        output = run_x(
            """
            function main() {
                print(parseFloat("3.5"), parseFloat("42"), parseFloat("-0.5"));
                print(parseFloat(".5"), parseFloat("1e3"), parseFloat("1E2"));
                print(parseFloat(" +2.5 "));
                print(typeOf(parseFloat("1")));
            }
            """
        )
        self.assertEqual(
            output,
            ["3.5 42.0 -0.5", "0.5 1000.0 100.0", "2.5", "number"],
        )

    def test_rejects_empty_garbage_and_partial_numbers(self):
        for text in ('""', '"abc"', '"12px"', '"1.2.3"', '"5."', '"0x10"'):
            with self.subTest(text=text):
                error = run_x_error(
                    f"""
                    function main() {{
                        parseFloat({text});
                    }}
                    """
                )
                self.assertEqual(error.exception_name, "IllegalArgumentException")
                self.assertIn("parseFloat", error.message)

    def test_rejects_non_string_and_wrong_arity(self):
        error = run_x_error(
            """
            function main() {
                parseFloat(42);
            }
            """
        )
        self.assertEqual(error.exception_name, "IllegalArgumentException")
        self.assertIn("expects a string", error.message)

        error = run_x_error(
            """
            function main() {
                parseFloat("1", "2");
            }
            """
        )
        self.assertIn("one argument", error.message)

    def test_error_is_catchable_as_illegal_argument(self):
        output = run_x(
            """
            function main() {
                try {
                    parseFloat("nope");
                    print("no throw");
                } catch (IllegalArgumentException error) {
                    print("caught: " + error.message);
                }
            }
            """
        )
        self.assertEqual(len(output), 1)
        self.assertTrue(output[0].startswith("caught: parseFloat"))


class ParseIntTests(unittest.TestCase):
    def test_default_and_explicit_radices(self):
        output = run_x(
            """
            function main() {
                print(parseInt("255"), parseInt("-42"), parseInt("+7"));
                print(parseInt("ff", 16), parseInt("FF", 16));
                print(parseInt("1011", 2), parseInt("777", 8), parseInt("z", 36));
                print(parseInt(" 10 "), typeOf(parseInt("10")));
            }
            """
        )
        self.assertEqual(
            output,
            [
                "255 -42 7",
                "255 255",
                "11 511 35",
                "10 number",
            ],
        )

    def test_rejects_garbage_and_digits_outside_radix(self):
        for text, radix in (
            ('"12px"', None),
            ('"abc"', None),
            ('""', None),
            ('"2"', 2),
            ('"8"', 8),
            ('"10"', 1),
            ('"10"', 37),
            ('"10"', 2.5),
        ):
            with self.subTest(text=text, radix=radix):
                call = f'parseInt({text})' if radix is None else f'parseInt({text}, {radix})'
                error = run_x_error(
                    f"""
                    function main() {{
                        {call};
                    }}
                    """
                )
                self.assertEqual(error.exception_name, "IllegalArgumentException")
                self.assertIn("parseInt", error.message)

    def test_rejects_non_string_text(self):
        error = run_x_error(
            """
            function main() {
                parseInt(10);
            }
            """
        )
        self.assertEqual(error.exception_name, "IllegalArgumentException")
        self.assertIn("expects a string", error.message)


class JsonParseTests(unittest.TestCase):
    def test_parses_objects_arrays_and_scalars(self):
        output = run_x(
            """
            import System.utils.JSON
            function main() {
                print(JSON.parse("42"), JSON.parse("true"), JSON.parse("null"));
                print(JSON.toJSON(JSON.parse("{\\"a\\": [1, 2.5, true, null]}")));
                let parsed = JSON.parse("{\\"nested\\": {\\"k\\": [1, 2]}}");
                print(JSON.toJSON(parsed.nested));
            }
            """
        )
        self.assertEqual(
            output,
            [
                "42 true null",
                '{"a":[1,2.5,true,null]}',
                '{"k":[1,2]}',
            ],
        )

    def test_unqualified_member_import_binds_parse(self):
        output = run_x(
            """
            import System.utils.JSON.parse
            function main() {
                print(parse("[1, 2]"));
            }
            """
        )
        self.assertEqual(output, ["[1, 2]"])

    def test_rejects_malformed_json_and_nan_extension(self):
        for text in (
            '"{bad"',
            '"[1,"',
            '"NaN"',
            '"Infinity"',
            '""',
            # JSON text with an unterminated inner string: {"key": "va
            '"{\\"key\\": \\"va"',
        ):
            with self.subTest(text=text):
                error = run_x_error(
                    f"""
                    import System.utils.JSON
                    function main() {{
                        JSON.parse({text});
                    }}
                    """
                )
                self.assertEqual(error.exception_name, "IllegalArgumentException")
                self.assertIn("JSON.parse failed", error.message)

    def test_rejects_non_string_and_wrong_arity(self):
        error = run_x_error(
            """
            import System.utils.JSON
            function main() {
                JSON.parse(42);
            }
            """
        )
        self.assertEqual(error.exception_name, "IllegalArgumentException")
        self.assertIn("expects a string", error.message)

        error = run_x_error(
            """
            import System.utils.JSON
            function main() {
                JSON.parse("{}", "{}");
            }
            """
        )
        self.assertIn("one argument", error.message)


class ParseBuiltinCheckTests(unittest.TestCase):
    def test_declared_result_types_are_float_and_integer(self):
        return_code, output, errors = check_source(
            """
            function main() {
                let float f = parseFloat("1.5");
                let integer i = parseInt("5", 10);
                print(f, i);
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)

    def test_float_result_is_not_assignable_to_string(self):
        return_code, _output, errors = check_source(
            """
            function main() {
                let string s = parseFloat("1.5");
            }
            """
        )
        self.assertEqual(return_code, 1)
        self.assertIn("float", errors)

    def test_int_result_is_not_assignable_to_string(self):
        return_code, _output, errors = check_source(
            """
            function main() {
                let string s = parseInt("5");
            }
            """
        )
        self.assertEqual(return_code, 1)
        self.assertIn("integer", errors)
