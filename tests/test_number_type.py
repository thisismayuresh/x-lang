"""Regression matrix for the `number` type family:

* `number` is an alias of `float` and works in every annotation position,
  including arrays (1D/2D/3D), function signatures, records, interfaces,
  unions, generic arguments, and type aliases.
* A variable may be named after its own type (`let number number = 5`) —
  type positions and value positions stay independent.
* Diagnostics keep the spelling the source used (`number[]`, `int`),
  not the canonical name (`float[]`, `integer`).
"""
import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.cli import main
from xlang.config import XConfig
from xlang.formatter import format_source
from xlang.interpreter import Interpreter
from xlang.lexer import Lexer
from xlang.parser import Parser
from xlang.typecheck import TypeChecker


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def run_x(source):
    """Parse, interpret, and return (printed_output, error_or_None)."""
    tokens = Lexer(dedent(source), "t.x").tokenize()
    program = Parser(tokens, XConfig().features, "t.x").parse()
    output: list[str] = []
    try:
        Interpreter([], output.append).interpret(program)
        return output, None
    except Exception as exc:
        return output, str(exc)


def check_x(source):
    """Type-check and return the list of diagnostic messages."""
    tokens = Lexer(dedent(source), "t.x").tokenize()
    program = Parser(tokens, XConfig().features, "t.x").parse()
    return [error.message for error in TypeChecker().check(program, "t.x")]


class NumberDeclarationTests(unittest.TestCase):
    def test_number_declares_float_values_with_number_typeof(self):
        out, err = run_x(
            """
            let number whole = 5;
            let number fractional = 1.5;
            print(typeOf(whole), typeOf(fractional));
            print(whole + fractional);
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["number number", "6.5"])

    def test_number_in_function_signature(self):
        out, err = run_x(
            """
            number function half(number value) {
                return value / 2;
            }
            print(half(9));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["4.5"])

    def test_number_in_record_field(self):
        out, err = run_x(
            """
            type Price = record {
                number amount;
                number[] history;
            };
            let Price p = { amount: 2.5, history: [1, 2] };
            print(p.amount, p.history);
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2.5 [1, 2]"])

    def test_number_in_interface_and_class(self):
        out, err = run_x(
            """
            interface Measurer {
                number measure();
                number[] samples();
            }
            class Ruler implements Measurer {
                public number base;
                public Ruler(number base) { this.base = base; }
                number measure() { return this.base + 0.5; }
                number[] samples() { return [this.base, this.base + 1]; }
            }
            let Measurer r = new Ruler(1);
            print(r.measure(), r.samples());
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1.5 [1, 2]"])

    def test_number_union_and_alias(self):
        out, err = run_x(
            """
            type Score = number;
            let number|string streak = 3;
            let Score s = 9.5;
            print(streak, s);
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3 9.5"])

    def test_number_as_generic_argument(self):
        out, err = run_x(
            """
            let HashMap<string, number> best = new HashMap<string, number>();
            best.set("high", 12.5);
            print(best.get("high"), typeOf(best));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["12.5 HashMap"])


class NumberArrayTests(unittest.TestCase):
    def test_one_dimensional_array(self):
        out, err = run_x(
            """
            let number[] xs = [1, 2, 3.5];
            xs.push(4);
            print(xs, typeOf(xs));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["[1, 2, 3.5, 4] Array"])

    def test_two_dimensional_array(self):
        out, err = run_x(
            """
            let number[][] grid = [[1, 2], [3, 4]];
            grid[0][1] = 9;
            print(grid);
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["[[1, 9], [3, 4]]"])

    def test_three_dimensional_array(self):
        out, err = run_x(
            """
            let number[][][] cube = [[[1, 2]], [[3]]];
            cube[0][0][1] = 5;
            print(cube);
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["[[[1, 5]], [[3]]]"])

    def test_array_returning_function(self):
        out, err = run_x(
            """
            number[] function pair(number first, number second) {
                return [first, second];
            }
            print(pair(1, 2.5));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["[1, 2.5]"])

    def test_array_in_multidimensional_function_signature(self):
        out, err = run_x(
            """
            number[] function row(number[][] matrix, integer index) {
                return matrix[index];
            }
            print(row([[7, 8], [9]], 1));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["[9]"])


class TypeNameAsIdentifierTests(unittest.TestCase):
    def test_variable_named_after_its_own_type(self):
        out, err = run_x(
            """
            let number number = 5;
            print(number, typeOf(number));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5 number"])

    def test_string_type_name_as_variable(self):
        out, err = run_x(
            """
            let string string = "Maya";
            print(string, typeOf(string));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["Maya string"])

    def test_parameter_named_after_its_own_type(self):
        out, err = run_x(
            """
            number function bump(number number) {
                return number + 1;
            }
            print(bump(41));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["42"])

    def test_type_positions_resolve_while_name_is_shadowed(self):
        out, err = run_x(
            """
            let number number = 5;
            let string string = "text";
            let number[] numbers = [number, number + 1];
            number[] function copy(number[] values) {
                return values;
            }
            print(number, string, copy(numbers));
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5 text [5, 6]"])

    def test_nested_scope_redeclares_type_name_locally(self):
        out, err = run_x(
            """
            let number total = 10;
            {
                let number total = 1;
                print(total);
            }
            print(total);
            """
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "10"])


class NumberDiagnosticsTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def assertTypeError(self, source, message):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            return_code, output, errors = self.run_cli(
                ["check", "--no-config", "--color", "never", str(source_file)]
            )
        self.assertEqual(return_code, 1, output)
        self.assertEqual(output, "")
        self.assertIn(message, errors)

    def test_number_array_rejects_string_elements(self):
        self.assertTypeError(
            'let number[] xs = ["a"];',
            "Cannot assign 'string[]' to 'xs' of type 'number[]'",
        )

    def test_number_2d_rejects_string_elements(self):
        self.assertTypeError(
            'let number[][] grid = [["a"]];',
            "Cannot assign 'string[][]' to 'grid' of type 'number[][]'",
        )

    def test_number_annotation_rejects_string_value(self):
        self.assertTypeError(
            'let number n = "text";',
            "Cannot assign 'string' to 'n' of type 'number'",
        )

    def test_diagnostics_keep_the_written_int_spelling(self):
        self.assertTypeError(
            'let int n = "text";',
            "Cannot assign 'string' to 'n' of type 'int'",
        )

    def test_diagnostics_keep_the_written_float_spelling(self):
        self.assertTypeError(
            'let float n = "text";',
            "Cannot assign 'string' to 'n' of type 'float'",
        )

    def test_unknown_type_is_still_rejected(self):
        self.assertTypeError(
            "let zzzz n = 5;",
            "Unknown type 'zzzz'",
        )


class NumberFormatterTests(unittest.TestCase):
    def assertRoundTrip(self, source):
        formatted = format_source(dedent(source))
        self.assertEqual(formatted, dedent(source))

    def test_number_declarations_survive_formatting(self):
        self.assertRoundTrip("let number number = 5;\n")

    def test_number_arrays_survive_formatting(self):
        self.assertRoundTrip("let number[] xs = [1, 2];\n")
        self.assertRoundTrip("let number[][] grid = [[1]];\n")


if __name__ == "__main__":
    unittest.main()
