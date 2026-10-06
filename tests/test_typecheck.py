import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.cli import main
from xlang.config import load_config
from xlang.module_loader import ModuleLoader
from xlang.typecheck import TypeChecker, TypeCheckError, TypeDiagnostic


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


class TypeCheckCliTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def check_source(self, source):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            return_code, output, errors = self.run_cli(
                ["check", "--no-config", "--color", "never", str(source_file)]
            )
        return return_code, output, errors

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
        self.assertIn("x: found 1 type error(s)", errors)

    def test_check_accepts_well_typed_program(self):
        self.assertClean(
            """
            integer function add(integer a, integer b) {
                return a + b;
            }
            interface Greeter {
                string greet();
            }
            class Loud implements Greeter {
                public string name;
                public Loud(string name) { this.name = name; }
                public string greet() { return this.name; }
            }
            function main() {
                let integer n = add(1, 2);
                let Greeter g = new Loud("hi");
                print(g.greet());
                let string? maybe = null;
                print(maybe);
                let integer[] nums = [1, 2, 3];
                for (integer v of nums) { print(v); }
            }
            """
        )

    def test_check_rejects_literal_type_mismatch(self):
        return_code, output, errors = self.check_source(
            """
            function main() {
                let integer x = "text";
                print(x);
            }
            """
        )
        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertIn(
            "Cannot assign 'string' to 'x' of type 'integer'", errors
        )
        self.assertIn(":2:5", errors)
        self.assertIn("let integer x = \"text\";", errors)
        self.assertIn("^", errors)
        self.assertIn("x: found 1 type error(s)", errors)

    def test_check_rejects_wrong_argument_type(self):
        self.assertTypeError(
            """
            function add(integer a, integer b) {
                return a + b;
            }
            function main() {
                print(add(1, "two"));
            }
            """,
            "Argument 2 of 'add' has type 'string', expected 'integer'",
        )

    def test_check_rejects_float_argument_for_integer_parameter(self):
        self.assertTypeError(
            """
            function add(integer a, integer b) {
                return a + b;
            }
            function main() {
                print(add(1, 2.5));
            }
            """,
            "Argument 2 of 'add' has type 'float', expected 'integer'",
        )

    def test_check_rejects_missing_return(self):
        self.assertTypeError(
            """
            integer function twice(integer n) {
                print(n);
            }
            function main() {
                print(twice(2));
            }
            """,
            "Function 'twice' must return a value of type 'integer'",
        )

    def test_check_rejects_return_type_mismatch(self):
        self.assertTypeError(
            """
            string function label(integer n) {
                return n;
            }
            function main() {
                print(label(1));
            }
            """,
            "Return type 'integer' is not compatible with 'string'",
        )

    def test_check_rejects_definite_assignment_violation(self):
        self.assertTypeError(
            """
            function main() {
                let integer x;
                print(x);
            }
            """,
            "Variable 'x' is used before it is definitely assigned",
        )

    def test_check_accepts_assignment_before_use(self):
        self.assertClean(
            """
            function main() {
                let integer x;
                x = 5;
                print(x);
            }
            """
        )

    def test_check_rejects_interface_mismatch_at_assignment(self):
        self.assertTypeError(
            """
            interface Greeter {
                string greet();
            }
            class Missing {
                public Missing() {}
            }
            function main() {
                let Greeter g = new Missing();
                print(g.greet());
            }
            """,
            "Cannot assign 'Missing' to 'g' of type 'Greeter'",
        )

    def test_check_rejects_union_argument_mismatch(self):
        self.assertTypeError(
            """
            function take(int|string v) {
                print(v);
            }
            function main() {
                take(true);
            }
            """,
            "Argument 1 of 'take' has type 'boolean', expected '(integer|string)'",
        )

    def test_check_accepts_values_covered_by_union(self):
        self.assertClean(
            """
            function take(int|string v) {
                print(v);
            }
            function main() {
                take(3);
                take("s");
            }
            """
        )

    def test_check_rejects_record_field_mismatch(self):
        self.assertTypeError(
            """
            type Point = {
                integer x;
                integer y;
            }
            function main() {
                let Point p = {x: 1, y: "no"};
                print(p);
            }
            """,
            "Cannot assign 'record{integer x;string y}' to 'p' "
            "of type 'record{integer x;integer y}'",
        )

    def test_check_accepts_matching_record(self):
        self.assertClean(
            """
            type Point = {
                integer x;
                integer y;
            }
            function main() {
                let Point p = {x: 1, y: 2};
                print(p);
            }
            """
        )

    def test_check_rejects_generic_argument_mismatch(self):
        self.assertTypeError(
            """
            function <T> T identity(T value) {
                return value;
            }
            function main() {
                print(identity<integer>("text"));
            }
            """,
            "Argument 1 of 'identity' has type 'string', expected 'integer'",
        )

    def test_check_accepts_matching_generic_argument(self):
        self.assertClean(
            """
            function <T> T identity(T value) {
                return value;
            }
            function main() {
                print(identity<integer>(5));
            }
            """
        )

    def test_check_reports_division_by_zero_outside_try(self):
        self.assertTypeError(
            """
            function main() {
                let integer result = 4 / 0;
                print(result);
            }
            """,
            "Cannot divide by zero",
        )

    def test_check_accepts_division_by_zero_inside_try(self):
        self.assertClean(
            """
            function main() {
                try {
                    let integer result = 4 / 0;
                    print(result);
                } catch (ArithmeticException e) {
                    print(e.message);
                }
            }
            """
        )

    def test_check_rejects_const_reassignment(self):
        self.assertTypeError(
            """
            function main() {
                const integer k = 1;
                k = 2;
                print(k);
            }
            """,
            "Cannot reassign constant 'k'",
        )

    def test_check_rejects_unknown_member_on_class_instance(self):
        self.assertTypeError(
            """
            class Box {
                public integer value;
                public Box() { this.value = 1; }
            }
            function main() {
                let Box b = new Box();
                print(b.missing);
            }
            """,
            "'Box' has no member 'missing'",
        )

    def test_check_rejects_private_method_access_from_outside(self):
        self.assertTypeError(
            """
            class Clock {
                private void tick() { print(1); }
                public void show() { this.tick(); }
                public Clock() {}
            }
            function main() {
                let Clock c = new Clock();
                c.tick();
            }
            """,
            "Cannot access private method 'Clock.tick'",
        )

    def test_check_rejects_protected_property_access_from_outside(self):
        self.assertTypeError(
            """
            class Vault {
                protected string secret;
                public Vault() { this.secret = "s"; }
            }
            function peek(Vault v) {
                print(v.secret);
            }
            function main() {
                peek(new Vault());
            }
            """,
            "Cannot access protected property 'Vault.secret'",
        )

    def test_check_rejects_final_class_extension(self):
        self.assertTypeError(
            """
            final class Closed {}
            class Open extends Closed {}
            function main() {}
            """,
            "Cannot extend final class 'Closed'",
        )

    def test_check_rejects_constructing_abstract_class(self):
        self.assertTypeError(
            """
            abstract class Shape {
                public abstract string speak();
                public Shape() {}
            }
            function main() {
                let Shape s = new Shape();
                print(s);
            }
            """,
            "Cannot construct abstract class 'Shape'",
        )

    def test_check_rejects_subclass_missing_abstract_method(self):
        self.assertTypeError(
            """
            abstract class Shape {
                public abstract string speak();
                public Shape() {}
            }
            class Circle extends Shape {
                public Circle() {}
            }
            function main() {
                print(new Circle());
            }
            """,
            "Class 'Circle' does not implement abstract method 'speak'",
        )

    def test_check_accepts_empty_object_literal(self):
        self.assertClean(
            """
            function main() {
                let object seen = {};
                print(seen);
            }
            """
        )

    def test_check_accepts_constructor_call_without_new(self):
        self.assertClean(
            """
            class Point {
                public integer x;
                public Point(integer x) { this.x = x; }
            }
            function main() {
                let Point p = Point(3);
                print(p.x);
            }
            """
        )

    def test_check_rejects_constructor_call_argument_without_new(self):
        self.assertTypeError(
            """
            class Point {
                public integer x;
                public Point(integer x) { this.x = x; }
            }
            function main() {
                let Point p = Point("nope");
                print(p.x);
            }
            """,
            "Argument 1 of 'Point' has type 'string', expected 'integer'",
        )

    def test_check_rejects_array_element_type_mismatch(self):
        self.assertTypeError(
            """
            function main() {
                let integer[] values = [1, 2, "name"];
                print(values);
            }
            """,
            "Cannot assign '(integer|string)[]' to 'values' of type 'integer[]'",
        )

    def test_feature_type_checker_off_skips_type_checking(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                'function main() {\n    let integer x = "text";\n    print(x);\n}\n',
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                [
                    "check",
                    "--no-config",
                    "--feature",
                    "type_checker=off",
                    "--color",
                    "never",
                    str(source_file),
                ]
            )

        self.assertEqual(return_code, 0, errors)
        self.assertIn("syntax is valid", output)
        self.assertNotIn("types are valid", output)
        self.assertEqual(errors, "")

    def test_run_command_does_not_type_check(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                'function main() {\n    let integer x = "text";\n    print(x);\n}\n',
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                ["run", "--no-config", "--color", "never", str(source_file)]
            )

        self.assertEqual(return_code, 0, errors)
        self.assertEqual(output.splitlines(), ["text"])
        self.assertEqual(errors, "")

    def test_check_of_syntax_error_stays_a_syntax_diagnostic(self):
        repository_root = Path(__file__).resolve().parents[1]
        return_code, output, errors = self.run_cli(
            [
                "check",
                "--no-config",
                "--color",
                "never",
                str(repository_root / "examples" / "errors" / "syntax_error.x"),
            ]
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertNotIn("type error", errors)
        self.assertIn("found 1 error(s)", errors)

    def test_check_of_known_good_example_reports_both_lines(self):
        repository_root = Path(__file__).resolve().parents[1]
        source_path = repository_root / "examples" / "main.x"
        return_code, output, errors = self.run_cli(
            ["check", "--no-config", "--color", "never", str(source_path)]
        )

        self.assertEqual(return_code, 0, errors)
        self.assertIn(f"{source_path}: syntax is valid", output)
        self.assertIn(f"{source_path}: types are valid", output)
        self.assertEqual(errors, "")

    def test_build_command_also_type_checks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                'function main() {\n    let integer x = "text";\n    print(x);\n}\n',
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                ["build", "--no-config", "--color", "never", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertIn("x: found 1 type error(s)", errors)


class TypeCheckerApiTests(unittest.TestCase):
    def load_program(self, source: str):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        source_file = Path(temporary_directory.name) / "program.x"
        source_file.write_text(dedent(source), encoding="utf-8")
        loader = ModuleLoader(
            Path(temporary_directory.name), load_config(None), recover_errors=True
        )
        program = loader.load_program(source_file)
        self.assertEqual(loader.errors, [])
        return program

    def messages(self, source: str) -> list[str]:
        program = self.load_program(source)
        return [
            error.message for error in TypeChecker().check(program, "program.x")
        ]

    def test_type_diagnostic_is_an_alias_of_type_check_error(self):
        self.assertIs(TypeDiagnostic, TypeCheckError)

    def test_valid_program_produces_no_diagnostics(self):
        program = self.load_program(
            """
            function main() {
                let integer n = 1;
                print(n);
            }
            """
        )
        self.assertEqual(TypeChecker().check(program), [])

    def test_diagnostics_carry_message_location_and_source_name(self):
        program = self.load_program(
            """
            function main() {
                let integer x = "text";
                print(x);
            }
            """
        )
        errors = TypeChecker().check(program, "program.x")
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].message,
            "Cannot assign 'string' to 'x' of type 'integer'",
        )
        self.assertEqual(errors[0].line, 2)
        self.assertEqual(errors[0].column, 5)
        self.assertTrue(errors[0].source_name.endswith("program.x"))

    def test_independent_errors_are_all_reported_once(self):
        messages = self.messages(
            """
            function main() {
                let integer a = "text";
                const integer k = 1;
                k = 2;
                let integer b;
                print(b);
                print(a);
                print(k);
            }
            """
        )
        self.assertEqual(
            sorted(messages),
            sorted(
                [
                    "Cannot assign 'string' to 'a' of type 'integer'",
                    "Cannot reassign constant 'k'",
                    "Variable 'b' is used before it is definitely assigned",
                ]
            ),
        )

    def test_checker_instance_can_be_reused_across_programs(self):
        checker = TypeChecker()
        broken = self.load_program(
            """
            function main() {
                let integer x = "text";
                print(x);
            }
            """
        )
        valid = self.load_program(
            """
            function main() {
                print(1);
            }
            """
        )
        self.assertEqual(len(checker.check(broken)), 1)
        self.assertEqual(checker.check(valid), [])
        self.assertEqual(len(checker.check(broken)), 1)

    def test_check_or_raise_raises_the_first_diagnostic(self):
        program = self.load_program(
            """
            function main() {
                let integer x = "text";
                print(x);
            }
            """
        )
        with self.assertRaises(TypeCheckError) as caught:
            TypeChecker().check_or_raise(program, "program.x")
        self.assertEqual(
            caught.exception.message,
            "Cannot assign 'string' to 'x' of type 'integer'",
        )


if __name__ == "__main__":
    unittest.main()
