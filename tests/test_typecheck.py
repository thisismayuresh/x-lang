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

    def test_check_return_to_interface_notes_missing_members(self):
        self.assertTypeError(
            """
            interface IThing {
                string name,
                integer age,
            }
            IThing function make() {
                return { name: "a", other: 1 };
            }
            function main() {
                print(make().name);
            }
            """,
            "missing required member `age: integer`",
        )

    def test_check_return_to_interface_notes_mismatched_members(self):
        self.assertTypeError(
            """
            interface IThing {
                string name,
            }
            IThing function make() {
                return { name: 5 };
            }
            function main() {
                print(make().name);
            }
            """,
            "member `name`: expected `string`, found `integer`",
        )

    def test_check_variable_to_interface_notes_missing_members(self):
        self.assertTypeError(
            """
            interface IThing {
                integer age,
            }
            function main() {
                let IThing t = { name: "a" };
                print(t);
            }
            """,
            "missing required member `age: integer`",
        )

    def test_check_argument_to_interface_notes_missing_members(self):
        self.assertTypeError(
            """
            interface IThing {
                integer age,
            }
            function take(IThing t) {
                print(t);
            }
            function main() {
                take({ name: "a" });
            }
            """,
            "missing required member `age: integer`",
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
            "Cannot assign '{ x: integer, y: string }' to 'p' "
            "of type '{ x: integer, y: integer }'",
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

    def test_check_accepts_string_literal_union_member(self):
        self.assertClean(
            """
            type SettingsKey = "theme" | "backup";
            function main() {
                let SettingsKey key = "theme";
                print(key);
            }
            """
        )

    def test_check_rejects_string_literal_union_nonmember(self):
        self.assertTypeError(
            """
            type SettingsKey = "theme" | "backup";
            function main() {
                let SettingsKey key = "nope";
                print(key);
            }
            """,
            'Cannot assign \'string\' to \'key\' of type \'("theme"|"backup")\'',
        )

    def test_check_rejects_plain_string_for_literal_union(self):
        self.assertTypeError(
            """
            type SettingsKey = "theme" | "backup";
            function main() {
                let string raw = "theme";
                let SettingsKey key = raw;
                print(key);
            }
            """,
            'Cannot assign \'string\' to \'key\' of type \'("theme"|"backup")\'',
        )

    def test_check_accepts_literal_union_argument(self):
        self.assertClean(
            """
            type SettingsKey = "theme" | "backup";
            string function describe(SettingsKey key) {
                return key;
            }
            function main() {
                print(describe("backup"));
            }
            """
        )

    def test_check_object_with_literal_key_type(self):
        self.assertClean(
            """
            type SettingsKey = "theme" | "backup";
            export const object<SettingsKey, string> DEFAULT_SETTINGS = {
                theme: "system",
                backup: "0"
            };
            function main() {
                print(DEFAULT_SETTINGS.theme);
            }
            """
        )

    def test_check_colon_annotation(self):
        self.assertClean(
            """
            function main() {
                let count: integer = 3;
                print(count);
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
            "Cannot access protected field 'Vault.secret'",
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

    def test_run_command_reports_type_errors_like_check(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                'function main() {\n    let integer x = "text";\n    print(x);\n}\n',
                encoding="utf-8",
            )
            run_code, run_output, run_errors = self.run_cli(
                ["run", "--no-config", "--color", "never", str(source_file)]
            )
            check_code, check_output, check_errors = self.run_cli(
                ["check", "--no-config", "--color", "never", str(source_file)]
            )

        self.assertEqual(run_code, 1, run_errors)
        self.assertEqual(run_output, "")
        self.assertIn(
            "Cannot assign 'string' to 'x' of type 'integer'", run_errors
        )
        self.assertIn(":2:5", run_errors)
        self.assertIn("x: found 1 type error(s)", run_errors)
        self.assertEqual(
            (run_code, run_output, run_errors),
            (check_code, check_output, check_errors),
        )

    def test_run_renders_every_type_error_with_its_own_source_line(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                "function add(a, b) {\n"
                "    return a + b;\n"
                "}\n"
                "function main() {\n"
                "    print(add(1, 2));\n"
                "}\n"
                "main();\n",
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                [
                    "run",
                    "--no-config",
                    "--feature",
                    "strict_typing=on",
                    "--color",
                    "never",
                    str(source_file),
                ]
            )

        self.assertEqual(return_code, 1, errors)
        self.assertEqual(output, "")
        self.assertIn("x: found 4 type error(s)", errors)
        self.assertNotIn("(at ", errors)
        self.assertEqual(errors.count("-->"), 4)
        self.assertEqual(errors.count("function add(a, b) {"), 3)
        self.assertEqual(errors.count("function main() {"), 1)
        for message in (
            "Function 'add' must have an explicit return type",
            "Parameter 'a' in function 'add' must have an explicit type",
            "Parameter 'b' in function 'add' must have an explicit type",
            "Function 'main' must have an explicit return type",
        ):
            self.assertIn(message, errors)

    def test_run_reports_type_errors_from_imported_modules(self):
        repository_root = Path(__file__).resolve().parents[1]
        source_path = repository_root / "examples" / "test_import_strict.x"
        imported_path = repository_root / "examples" / "imported_func.x"
        return_code, output, errors = self.run_cli(
            [
                "run",
                "--no-config",
                "--feature",
                "strict_typing=on",
                "--color",
                "never",
                str(source_path),
            ]
        )

        self.assertEqual(return_code, 1, errors)
        self.assertEqual(output, "")
        self.assertIn("x: found 6 type error(s)", errors)
        self.assertIn("examples/imported_func.x:6:1", errors)
        self.assertIn("export function untypedImported(a, b) {", errors)
        self.assertIn("examples/test_import_strict.x:8:1", errors)

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


class StrictTypingCliTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def check_strict(self, source, command="check"):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            return self.run_cli(
                [
                    command,
                    "--no-config",
                    "--feature",
                    "strict_typing=on",
                    "--color",
                    "never",
                    str(source_file),
                ]
            )

    def test_constructor_without_return_type_passes_strict_typing(self):
        return_code, output, errors = self.check_strict(
            """
            class Point {
                public integer x;
                public Point(integer x) { this.x = x; }
                public integer getX() { return this.x; }
            }
            any function main() {
                let Point p = new Point(3);
                print(p.getX());
                return "";
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("syntax is valid", output)
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")

    def test_constructor_parameters_still_require_types_under_strict_typing(self):
        return_code, output, errors = self.check_strict(
            """
            class Point {
                public integer x;
                public Point(x) { this.x = x; }
            }
            any function main() {
                let Point p = new Point(1);
                print(p.x);
                return "";
            }
            """
        )
        self.assertEqual(return_code, 1, output)
        self.assertEqual(output, "")
        self.assertIn(
            "Parameter 'x' in constructor 'Point' must have an explicit type", errors
        )
        self.assertNotIn("must have an explicit return type", errors)
        self.assertIn("x: found 1 type error(s)", errors)

    def test_void_constructor_passes_strict_typing(self):
        return_code, output, errors = self.check_strict(
            """
            class Counter {
                public integer value;
                public void Counter(integer value) { this.value = value; }
            }
            any function main() {
                let Counter c = new Counter(0);
                print(c.value);
                return "";
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")

    def test_annotated_program_is_clean_under_strict_typing(self):
        return_code, output, errors = self.check_strict(
            """
            class Greeter {
                public string name;
                public Greeter(string name) { this.name = name; }
                public string greet() { return "hi " + this.name; }
            }
            integer function add(integer a, integer b) {
                return a + b;
            }
            any function main() {
                let Greeter g = new Greeter("ada");
                print(g.greet());
                print(add(1, 2));
                return "";
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")

    def test_run_and_check_render_identically_under_strict_typing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                "function add(a, b) {\n    return a + b;\n}\n"
                "function main() {\n    print(add(1, 2));\n}\n"
                "main();\n",
                encoding="utf-8",
            )
            command = [
                "--no-config",
                "--feature",
                "strict_typing=on",
                "--color",
                "never",
                str(source_file),
            ]
            run_code, run_output, run_errors = self.run_cli(["run", *command])
            check_code, check_output, check_errors = self.run_cli(["check", *command])

        self.assertEqual(run_code, 1, run_errors)
        self.assertEqual(run_output, "")
        self.assertIn("x: found 4 type error(s)", run_errors)
        self.assertEqual(
            (run_code, run_output, run_errors),
            (check_code, check_output, check_errors),
        )

    def test_showcase_example_is_clean_under_strict_typing(self):
        repository_root = Path(__file__).resolve().parents[1]
        source_path = repository_root / "examples" / "main.x"
        return_code, output, errors = self.run_cli(
            [
                "check",
                "--no-config",
                "--feature",
                "strict_typing=on",
                "--color",
                "never",
                str(source_path),
            ]
        )

        self.assertEqual(return_code, 0, errors)
        self.assertIn(f"{source_path}: syntax is valid", output)
        self.assertIn(f"{source_path}: types are valid", output)
        self.assertEqual(errors, "")

    def test_aadhar_example_is_clean_under_strict_typing(self):
        # The try-with-resources CSV generator also checks the imported
        # aadhar_generator.x transitively.
        repository_root = Path(__file__).resolve().parents[1]
        source_path = repository_root / "examples" / "aadhar" / "main.x"
        return_code, output, errors = self.run_cli(
            [
                "check",
                "--no-config",
                "--feature",
                "strict_typing=on",
                "--color",
                "never",
                str(source_path),
            ]
        )

        self.assertEqual(return_code, 0, errors)
        self.assertIn(f"{source_path}: syntax is valid", output)
        self.assertIn(f"{source_path}: types are valid", output)
        self.assertEqual(errors, "")


class PrimitiveAliasCaseTests(unittest.TestCase):
    """The ``primitive_aliases`` feature makes built-in type spellings
    case-insensitive (``String``/``INTEGER``/``Object`` → ``string``/…).

    It is **off by default**: capitalized spellings like ``String`` are unknown
    types unless the feature is enabled, by ``x.toml`` or ``--feature``.
    """

    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def check_source(self, source, *extra):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            return self.run_cli(
                ["check", "--no-config", "--color", "never", *extra, str(source_file)]
            )

    def run_source(self, source, *extra):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            return self.run_cli(
                ["run", "--no-config", "--color", "never", *extra, str(source_file)]
            )

    # -- defaults ---------------------------------------------------------

    def test_lowercase_primitives_remain_accepted(self):
        return_code, output, errors = self.check_source(
            """
            integer function add(integer a, integer b) {
                return a + b;
            }
            function main() {
                let string name = "x";
                let object<string, integer> counts = { a: 1 };
                print(add(1, 2), name, counts);
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")

    def test_capitalized_builtin_types_are_unknown_by_default(self):
        for spelling in (
            "String",
            "Integer",
            "Int",
            "Float",
            "Double",
            "Number",
            "Boolean",
            "Bool",
            "Char",
            "Byte",
            "Any",
        ):
            return_code, output, errors = self.check_source(
                f"function probe({spelling} value) {{}}\n"
            )
            self.assertEqual(return_code, 1, f"{spelling}: {output}{errors}")
            self.assertIn(f"Unknown type '{spelling}'", errors, spelling)

    def test_unknown_type_suggestion_is_lowercase(self):
        return_code, _, errors = self.check_source(
            "function probe(String value) {}\n"
        )
        self.assertEqual(return_code, 1)
        self.assertIn("did you mean `string`?", errors)

    # -- enabled by CLI flag ---------------------------------------------

    def test_feature_flag_accepts_capitalized_builtin_types(self):
        for spelling in (
            "String",
            "Integer",
            "Int",
            "Float",
            "Double",
            "Number",
            "Boolean",
            "Bool",
            "Char",
            "Byte",
            "Any",
            "OBJECT",
        ):
            return_code, output, errors = self.check_source(
                f"function probe({spelling} value) {{}}\n",
                "--feature",
                "primitive_aliases=on",
            )
            self.assertEqual(return_code, 0, f"{spelling}: {output}{errors}")
            self.assertIn("types are valid", output, spelling)

    def test_any_case_matches_are_canonicalised(self):
        return_code, output, errors = self.check_source(
            """
            STRING function shout(INTEGER times) {
                return "x";
            }
            function main() {
                let sTRing name = "hi";
                let oBject<string, integer> counts = { a: 1 };
                print(shout(2), name, counts);
            }
            """,
            "--feature",
            "primitive_aliases=on",
        )
        self.assertEqual(return_code, 0, errors)

    def test_generic_arguments_are_case_insensitive_when_enabled(self):
        return_code, output, errors = self.check_source(
            "function probe(List<String> names) {}\n",
            "--feature",
            "primitive_aliases=on",
        )
        self.assertEqual(return_code, 0, errors)

    def test_generic_arguments_rejected_by_default(self):
        return_code, _, errors = self.check_source(
            "function probe(List<String> names) {}\n"
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Unknown type 'String'", errors)

    # -- runtime ----------------------------------------------------------

    def test_overload_resolution_matches_capitalized_types_at_runtime(self):
        return_code, output, errors = self.run_source(
            """
            function describe(String text) {
                return "S:" + text;
            }
            function describe(Integer count) {
                return "I:" + count;
            }
            function main() {
                print(describe("x"), describe(3));
            }
            main();
            """,
            "--feature",
            "primitive_aliases=on",
        )
        self.assertEqual(return_code, 0, errors)
        self.assertEqual(output, "S:x I:3\n")

    def test_capitalized_annotations_run_end_to_end(self):
        return_code, output, errors = self.run_source(
            """
            Object<STRING, INTEGER> function counts() {
                return { a: 1, b: 2 };
            }
            function main() {
                let Int total = 0;
                let Boolean okay = true;
                print(counts(), total, okay);
            }
            main();
            """,
            "--feature",
            "primitive_aliases=on",
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("true", output)

    # -- interaction with user types -------------------------------------

    def test_user_types_are_not_case_folded(self):
        return_code, _, errors = self.check_source(
            """
            class Widget {}
            function probe(widget value) {}
            """,
            "--feature",
            "primitive_aliases=on",
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Unknown type 'widget'", errors)

    def test_user_type_with_capitalized_name_still_resolves(self):
        return_code, output, errors = self.check_source(
            """
            class Palette {}
            function probe(Palette value) {}
            """,
            "--feature",
            "primitive_aliases=on",
        )
        self.assertEqual(return_code, 0, errors)

    # -- configuration ----------------------------------------------------

    def test_feature_enabled_from_config_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            config_path = project_root / "x.toml"
            config_path.write_text(
                "[features]\nprimitive_aliases = true\n", encoding="utf-8"
            )
            source_file = project_root / "main.x"
            source_file.write_text(
                "function probe(String value) {}\n", encoding="utf-8"
            )
            return_code, output, errors = self.run_cli(
                ["check", "--config", str(config_path), "--color", "never", str(source_file)]
            )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)

    def test_cli_flag_overrides_config_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            config_path = project_root / "x.toml"
            config_path.write_text(
                "[features]\nprimitive_aliases = true\n", encoding="utf-8"
            )
            source_file = project_root / "main.x"
            source_file.write_text(
                "function probe(String value) {}\n", encoding="utf-8"
            )
            return_code, output, errors = self.run_cli(
                [
                    "check",
                    "--config",
                    str(config_path),
                    "--feature",
                    "primitive_aliases=off",
                    "--color",
                    "never",
                    str(source_file),
                ]
            )
        self.assertEqual(return_code, 1, output)
        self.assertIn("Unknown type 'String'", errors)


if __name__ == "__main__":
    unittest.main()
