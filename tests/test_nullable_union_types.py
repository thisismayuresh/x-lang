"""Nullable (`T?`) and union (`A | B`, `A | null`) types — annotations,
type-first `let` syntax, runtime dispatch, and null/undefined rules.

`??` has its own file: tests/test_nullish_operator.py.
"""
import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.cli import main
from xlang.config import XConfig
from xlang.interpreter import Interpreter
from xlang.lexer import Lexer
from xlang.parser import Parser


def run_x(source):
    """Parse, interpret, and return (printed_output, error_or_None)."""
    tokens = Lexer(source, "t.x").tokenize()
    program = Parser(tokens, XConfig().features, "t.x").parse()
    output: list[str] = []
    try:
        Interpreter([], output.append).interpret(program)
        return output, None
    except Exception as exc:
        return output, str(exc)


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


class NullableRuntimeTests(unittest.TestCase):
    def assertOutput(self, source, expected):
        output, error = run_x(dedent(source))
        self.assertIsNone(error, error)
        self.assertEqual(output, expected)

    def test_nullable_parameter_accepts_null_and_value(self):
        self.assertOutput(
            """
            string function take(string? s) {
                if (s == null) { return "null"; }
                return s;
            }
            function main() {
                print(take(null));
                print(take("x"));
            }
            """,
            ["null", "x"],
        )

    def test_nullable_variable_colon_annotation(self):
        self.assertOutput(
            """
            function main() {
                let a: integer | null = null;
                print(a);
            }
            """,
            ["null"],
        )

    def test_type_first_union_declaration(self):
        self.assertOutput(
            """
            function main() {
                let integer | null a = null;
                print(a);
                a = 5;
                print(a);
            }
            """,
            ["null", "5"],
        )

    def test_union_return_type_round_trip(self):
        self.assertOutput(
            """
            integer | null function maybe(integer v) {
                if (v > 0) { return v; }
                return null;
            }
            function main() {
                print(maybe(1));
                print(maybe(0));
            }
            """,
            ["1", "null"],
        )

    def test_union_parameter_dispatches_at_runtime(self):
        self.assertOutput(
            """
            function show(string | integer v) { print(v); }
            function main() {
                show("a");
                show(1);
            }
            """,
            ["a", "1"],
        )

    def test_undefined_is_nullish_for_nullable_variables(self):
        self.assertOutput(
            """
            function main() {
                let string? a = undefined;
                print(a == null);
            }
            """,
            ["true"],
        )

    def test_nullable_variable_used_with_nullish_operator(self):
        self.assertOutput(
            """
            function main() {
                let string? missing = null;
                print(missing ?? "fallback");
                let string? present = "here";
                print(present ?? "fallback");
            }
            """,
            ["fallback", "here"],
        )

    def test_non_nullable_parameter_rejects_null_at_runtime(self):
        output, error = run_x(dedent("""
            string function take(string s) { return s; }
            function main() { print(take(null)); }
            """))
        self.assertIsNotNone(error, output)
        self.assertIn(
            "Argument 1 of 'take' has type 'null', expected 'string'", error
        )


class NullableTypeTests(unittest.TestCase):
    def check_source(self, source):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = main(
                    ["check", "--no-config", "--color", "never", str(source_file)]
                )
        return return_code, output.getvalue(), errors.getvalue()

    def assertClean(self, source):
        return_code, output, errors = self.check_source(source)
        self.assertEqual(return_code, 0, errors)
        self.assertIn("syntax is valid", output)
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")

    def assertTypeError(self, source, message):
        return_code, output, errors = self.check_source(source)
        self.assertEqual(return_code, 1, output)
        self.assertEqual(output, "")
        self.assertIn(message, errors)
        self.assertIn("x: found", errors)

    def test_nullable_let_colon_annotation(self):
        self.assertClean(
            """
            function main() {
                let a: integer | null = null;
                let string? b = null;
                print(a);
                print(b);
            }
            """
        )

    def test_type_first_union_let(self):
        self.assertClean(
            """
            function main() {
                let integer | null a = null;
                print(a);
            }
            """
        )

    def test_union_parameter_and_return_annotations(self):
        self.assertClean(
            """
            integer | null function maybe(integer v) {
                if (v > 0) { return v; }
                return null;
            }
            function show(string | integer v) { print(v); }
            function main() {
                print(maybe(1));
                show("a");
                show(2);
            }
            """
        )

    def test_undefined_assignable_to_nullable(self):
        self.assertClean(
            """
            function main() {
                let string? a = undefined;
                print(a == null);
            }
            """
        )

    def test_null_rejected_by_non_nullable_let(self):
        self.assertTypeError(
            """
            function main() { let integer x = null; print(x); }
            """,
            "Cannot assign 'null' to 'x' of type 'integer'",
        )

    def test_value_type_rejected_by_nullable_let(self):
        self.assertTypeError(
            """
            function main() { let string? s = 42; print(s); }
            """,
            "Cannot assign 'integer'",
        )

    def test_union_return_rejects_member_type(self):
        self.assertTypeError(
            """
            string | integer function pick() { return true; }
            function main() { print(pick()); }
            """,
            "Return type 'boolean' is not compatible with '(string|integer)'",
        )

    def test_union_return_accepts_member_type(self):
        self.assertClean(
            """
            string | integer function pick() { return 1; }
            function main() { print(pick()); }
            """
        )

    def test_union_parameter_rejects_outsider_type(self):
        self.assertTypeError(
            """
            function show(string | integer v) { print(v); }
            function main() { show(1.5); }
            """,
            "Argument 1 of 'show' has type 'float', expected '(string|integer)'",
        )

    def test_nullable_parameter_rejects_integer_argument(self):
        self.assertTypeError(
            """
            function take(string? s) { print(s); }
            function main() { take(42); }
            """,
            "Argument 1 of 'take' has type 'integer', expected 'string?'",
        )


if __name__ == "__main__":
    unittest.main()
