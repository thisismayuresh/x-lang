"""Diagnostics for unknown type names, interface conformance, typeOf, push/pop.

Covers the four behaviors:

* unknown type names fail ``run`` and ``check``
* concrete classes must implement every interface member
* ``typeOf`` reports ``Array`` for arrays, class names for instances, and
  collection names for OOP collection instances
* arrays gain ``push``/``pop`` methods
"""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.cli import main as cli_main
from xlang.module_loader import ModuleLoader
from xlang.runtime import Interpreter, RuntimeErrorX


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def run_x(source, arguments=None, environment=None):
    """Run an X source string and return ``(result, printed_output)``."""
    with TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        source_file = project_root / "main.x"
        source_file.write_text(dedent(source), encoding="utf-8")
        program = ModuleLoader(project_root).load_program(source_file)
        output = []
        result = Interpreter(
            arguments, output.append, environment=environment
        ).interpret(program)
    return result, output


def check_source(source):
    """Run ``x check`` on *source* and return ``(exit_code, out, err)``."""
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


def run_cli(arguments):
    """Run ``x`` with *arguments* and return ``(exit_code, out, err)``."""
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        return_code = cli_main(arguments)
    return return_code, output.getvalue(), errors.getvalue()


class UnknownTypeNameRunTests(unittest.TestCase):
    def test_unknown_variable_annotation_fails_run(self):
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x("""
                function main() {
                    let Foo x = 1;
                    print(x);
                }
                """)
        error = caught.exception
        self.assertEqual(error.message, "Unknown type 'Foo'")
        self.assertEqual(error.line, 2)
        self.assertEqual(error.column, 5)
        self.assertTrue(error.source_name.endswith("main.x"))

    def test_unknown_parameter_type_fails_run(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Unknown type 'intsssssx'"
        ):
            run_x("""
                function myFunction(intsssssx i = 0) {
                    print(i);
                }
                function main() {
                    myFunction(9);
                }
                """)

    def test_unknown_return_type_fails_run(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Unknown type 'Nope'"):
            run_x("""
                Nope function make() {
                    return 1;
                }
                function main() {
                    make();
                }
                """)

    def test_unknown_new_target_fails_run(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Unknown type 'Missing'"):
            run_x("""
                function main() {
                    let Missing value = new Missing();
                    print(value);
                }
                """)

    def test_unknown_type_in_local_annotation_fails_run(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Unknown type 'Locally'"):
            run_x("""
                function main() {
                    let Locally wrong = 1;
                    print(wrong);
                }
                """)

    def test_known_annotations_run_successfully(self):
        result, output = run_x("""
            class Point {
                public integer x;
                public Point(integer x) { this.x = x; }
            }
            interface Greeter {
                string greet();
            }
            class Loud implements Greeter {
                public Loud() {}
                public string greet() { return "hi"; }
            }
            function take(int|string value) {
                print(value);
            }
            function main() {
                let Point p = new Point(1);
                let Greeter g = new Loud();
                let integer[] numbers = [1, 2];
                let string? nothing = null;
                take(1);
                take("s");
                print(p.x, g.greet(), numbers, nothing);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["1", "s", "1 hi [1, 2] null"])

    def test_local_enum_annotations_are_accepted(self):
        result, output = run_x("""
            function main() {
                enum Status {
                    READY,
                    DONE
                }
                let Status current = Status.DONE;
                print(current == Status.DONE);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["true"])

    def test_feature_off_skips_declaration_validation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                "function main() {\n"
                "    let intsssssx i = 0;\n"
                "    print(i);\n"
                "}\n",
                encoding="utf-8",
            )
            return_code, output, errors = run_cli(
                [
                    "run",
                    "--no-config",
                    "--feature",
                    "type_checker=off",
                    "--color",
                    "never",
                    str(source_file),
                ]
            )
        self.assertEqual(return_code, 0, errors)
        self.assertEqual(output.splitlines(), ["0"])
        self.assertEqual(errors, "")


class UnknownTypeNameCheckTests(unittest.TestCase):
    def test_check_reports_unknown_type_name(self):
        return_code, output, errors = check_source("""
            function main() {
                let Foo x = 1;
                print(x);
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertEqual(output, "")
        self.assertIn("Unknown type 'Foo'", errors)
        self.assertIn("x: found 1 type error(s)", errors)
        self.assertIn(":2:5", errors)

    def test_check_reports_unknown_parameter_type(self):
        return_code, output, errors = check_source("""
            function myFunction(intsssssx i = 0) {
                print(i);
            }
            function main() {
                myFunction(9);
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Unknown type 'intsssssx'", errors)
        self.assertIn("x: found 1 type error(s)", errors)

    def test_check_accepts_known_type_names(self):
        return_code, output, errors = check_source("""
            class Box {
                public integer value;
                public Box(integer value) { this.value = value; }
            }
            function main() {
                let Box box = new Box(2);
                print(box.value);
            }
            """)
        self.assertEqual(return_code, 0, errors)
        self.assertIn("syntax is valid", output)
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")


class InterfaceImplementationRunTests(unittest.TestCase):
    def test_missing_interface_method_fails_run(self):
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x("""
                interface Person {
                    string getGender();
                }
                class Animal implements Person {
                    public Animal() {}
                }
                function main() {
                    print(new Animal());
                }
                """)
        error = caught.exception
        self.assertEqual(
            error.message,
            "Class 'Animal' does not implement 'getGender()' from interface 'Person'",
        )
        self.assertEqual(error.line, 4)
        self.assertEqual(error.column, 1)
        self.assertTrue(error.source_name.endswith("main.x"))

    def test_missing_interface_property_fails_run(self):
        with self.assertRaisesRegex(
            RuntimeErrorX,
            "Class 'Broken' does not implement property 'name' from interface 'Named'",
        ):
            run_x("""
                interface Named {
                    string name,
                }
                class Broken implements Named {
                    public Broken() {}
                }
                function main() {
                    print(new Broken());
                }
                """)

    def test_complete_implementation_runs(self):
        result, output = run_x("""
            interface Person {
                string getGender(),
            }
            class Animal implements Person {
                public Animal() {}
                public string getGender() { return "unknown"; }
            }
            function main() {
                print(new Animal().getGender());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["unknown"])

    def test_inherited_method_satisfies_interface(self):
        result, output = run_x("""
            interface Person {
                string getGender();
            }
            class Animal implements Person {
                public Animal() {}
                public string getGender() { return "unknown"; }
            }
            class Dog extends Animal implements Person {
                public Dog() {}
            }
            function main() {
                print(new Dog().getGender());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["unknown"])

    def test_abstract_class_may_leave_interface_unimplemented(self):
        result, output = run_x("""
            interface Person {
                string getGender();
            }
            abstract class Animal implements Person {
                public Animal() {}
            }
            function main() {
                print("ok");
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["ok"])

    def test_interface_extends_requires_union_of_members(self):
        result, output = run_x("""
            interface Named {
                string name(),
            }
            interface Person extends Named {
                string getGender(),
            }
            class Animal implements Person {
                public Animal() {}
                public string name() { return "creature"; }
                public string getGender() { return "unknown"; }
            }
            function main() {
                print(new Animal().name(), new Animal().getGender());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["creature unknown"])


class InterfaceImplementationCheckTests(unittest.TestCase):
    def test_check_reports_missing_interface_method(self):
        return_code, output, errors = check_source("""
            interface Person {
                string getGender();
            }
            class Animal implements Person {
                public Animal() {}
            }
            function main() {
                print(new Animal());
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertEqual(output, "")
        self.assertIn(
            "Class 'Animal' does not implement 'getGender()' "
            "from interface 'Person'",
            errors,
        )
        self.assertIn("x: found 1 type error(s)", errors)
        self.assertIn(":4:1", errors)

    def test_check_reports_missing_interface_property(self):
        return_code, output, errors = check_source("""
            interface Named {
                string name,
            }
            class Broken implements Named {
                public Broken() {}
            }
            function main() {
                print(new Broken());
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Class 'Broken' does not implement property 'name' "
            "from interface 'Named'",
            errors,
        )
        self.assertIn("x: found 1 type error(s)", errors)

    def test_check_accepts_complete_implementation(self):
        return_code, output, errors = check_source("""
            interface Person {
                string getGender();
            }
            class Animal implements Person {
                public Animal() {}
                public string getGender() { return "unknown"; }
            }
            function main() {
                print(new Animal().getGender());
            }
            """)
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")


class TypeOfTests(unittest.TestCase):
    def test_type_of_reports_array_for_plain_and_typed_arrays(self):
        result, output = run_x("""
            function main() {
                print(typeOf([1, 2]));
                print(typeOf([]));
                let integer[] typed = [1, 2];
                print(typeOf(typed));
                print(typeOf([[1], [2]]));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Array", "Array", "Array", "Array"])

    def test_type_of_reports_class_name_for_instances(self):
        result, output = run_x("""
            class User {}
            function main() {
                print(typeOf(new User()));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["User"])

    def test_type_of_reports_collection_instance_names(self):
        result, output = run_x("""
            function main() {
                let stack = Stack.create();
                stack.push("x");
                print(typeOf(stack));
                print(typeOf(HashMap.create()));
                print(typeOf(Queue.create()));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Stack", "HashMap", "Queue"])

    def test_type_of_keeps_existing_object_and_primitive_results(self):
        result, output = run_x("""
            class User {}
            function greet() {}
            function main() {
                print(typeOf({name: "Alice"}));
                print(typeOf("text"));
                print(typeOf(1));
                print(typeOf(true));
                print(typeOf(null));
                print(typeOf(greet));
                print(typeOf(User));
                print(typeOf(range(0, 2)));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "object",
                "string",
                "number",
                "boolean",
                "object",
                "function",
                "function",
                "object",
            ],
        )


class ArrayPushPopTests(unittest.TestCase):
    def test_push_appends_in_place(self):
        result, output = run_x("""
            function main() {
                let values = [1, 2];
                print(values.push(3));
                print(values);
                values.push("four");
                print(values);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["null", "[1, 2, 3]", "[1, 2, 3, four]"])

    def test_pop_removes_and_returns_last_element(self):
        result, output = run_x("""
            function main() {
                let values = ["a", "b"];
                print(values.pop());
                print(values);
                print(values.pop());
                print(values.isEmpty());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["b", "[a]", "a", "true"])

    def test_functional_list_push_and_pop(self):
        result, output = run_x("""
            function main() {
                let values = [1];
                List.push(values, 2);
                print(values);
                print(List.pop(values));
                print(values);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["[1, 2]", "2", "[1]"])

    def test_push_validates_typed_array_items(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Expected 'integer' for array item"
        ):
            run_x("""
                function main() {
                    let integer[] values = [1];
                    values.push("bad");
                }
                """)

    def test_pop_on_empty_array_errors(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Array.pop: array is empty"):
            run_x("""
                function main() {
                    let values = [];
                    values.pop();
                }
                """)

    def test_push_and_pop_reject_bad_arity(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Array.push expects one value"):
            run_x("""
                function main() {
                    [1].push();
                }
                """)
        with self.assertRaisesRegex(RuntimeErrorX, "Array.push expects one value"):
            run_x("""
                function main() {
                    [1].push(2, 3);
                }
                """)
        with self.assertRaisesRegex(RuntimeErrorX, "Array.pop expects no arguments"):
            run_x("""
                function main() {
                    [1].pop(2);
                }
                """)


class TypeNameEdgeCaseTests(unittest.TestCase):
    def test_class_names_starting_with_record_are_accepted(self):
        result, printed = run_x("""
            class records {
                public records() {}
            }
            class Recorder {
                public Recorder() {}
            }
            function main() {
                let records a = new records();
                let Recorder b = new Recorder();
                print(typeOf(a));
                print(typeOf(b));
            }
            """)
        self.assertEqual(printed, ["records", "Recorder"])

    def test_catch_union_type_names(self):
        return_code, output, errors = check_source("""
            function main() {
                try {
                    throw new Exception("boom");
                } catch (RuntimeException | NoSuchThing e) {
                    print(typeOf(e));
                }
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Unknown type 'NoSuchThing'", errors)
        self.assertIn("x: found 1 type error(s)", errors)

        return_code, output, errors = check_source("""
            function main() {
                try {
                    throw new Exception("boom");
                } catch (RuntimeException | Exception e) {
                    print(typeOf(e));
                }
            }
            """)
        self.assertEqual(return_code, 0, errors)
        self.assertEqual(errors, "")

    def test_union_inside_generic_arguments(self):
        return_code, output, errors = check_source("""
            function main() {
                let object<string|integer, int> p = {};
                print(typeOf(p));
            }
            """)
        self.assertEqual(return_code, 0, errors)
        self.assertEqual(errors, "")


class DiagnosticHintTests(unittest.TestCase):
    """``= note:`` and ``= help:`` follow-ups on hint-bearing diagnostics."""

    def check_strict(self, source):
        output = io.StringIO()
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = cli_main(
                    [
                        "check",
                        "--no-config",
                        "--feature",
                        "strict_typing=on",
                        "--color",
                        "never",
                        str(source_file),
                    ]
                )
        return return_code, output.getvalue(), errors.getvalue()

    def hint_lines(self, errors):
        return [
            line.strip()
            for line in errors.splitlines()
            if line.strip().startswith(("= help:", "= note:"))
        ]

    def test_missing_return_type_help(self):
        return_code, output, errors = self.check_strict("""
            function add(a, b) {
                return a + b;
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Function 'add' must have an explicit return type (strict_typing enabled)",
            errors,
        )
        self.assertIn(
            "= help: add an explicit return type, e.g. `int function add(int a, int b)`",
            errors,
        )

    def test_untyped_parameter_help(self):
        return_code, output, errors = self.check_strict("""
            function add(a, b) {
                return a + b;
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Parameter 'a' in function 'add' must have an explicit type", errors
        )
        self.assertIn(
            "= help: type the parameter, e.g. `int function add(int xp)`", errors
        )

    def test_constructor_parameter_help_names_the_constructor(self):
        return_code, output, errors = self.check_strict("""
            class Point {
                public integer x;
                public Point(x) { this.x = x; }
            }
            any function main() {
                let Point p = new Point(1);
                print(p.x);
                return "";
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Parameter 'x' in constructor 'Point' must have an explicit type", errors
        )
        self.assertIn(
            "= help: type the parameter, e.g. `public Point(int x)`", errors
        )
        self.assertNotIn("in function 'Point'", errors)

    def test_method_parameter_help_names_the_method(self):
        return_code, output, errors = self.check_strict("""
            class Point {
                public integer x;
                public Point(integer x) { this.x = x; }
                public string describe(seperator) { return ""; }
            }
            any function main() {
                print(new Point(1).describe(","));
                return "";
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Parameter 'seperator' in method 'describe' must have an explicit type",
            errors,
        )
        self.assertIn(
            "= help: type the parameter, e.g. `string describe(int xp)`", errors
        )
        self.assertNotIn("in function 'describe'", errors)

    def test_unknown_type_help_suggests_the_closest_known_type(self):
        return_code, output, errors = self.check_strict("""
            any function main() {
                let intger bad = 1;
                print(bad);
                return "";
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Unknown type 'intger'", errors)
        self.assertIn("= help: did you mean `integer`?", errors)

    def test_unknown_member_help_suggests_the_closest_member(self):
        return_code, output, errors = self.check_strict("""
            class Point {
                public integer x;
                public Point(integer x) { this.x = x; }
                public integer valu() { return this.x; }
            }
            any function main() {
                let Point p = new Point(1);
                return "" + p.valu2();
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("'Point' has no member 'valu2'", errors)
        self.assertIn("= help: did you mean `valu`?", errors)

    def test_assignment_mismatch_note_reports_expected_and_found(self):
        return_code, output, errors = self.check_strict("""
            any function main() {
                let integer n = "text";
                print(n);
                return "";
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot assign 'string' to 'n' of type 'integer'", errors)
        self.assertIn("= note: expected `integer`, found `string`", errors)

    def test_constant_reassignment_help_suggests_let(self):
        return_code, output, errors = self.check_strict("""
            any function main() {
                const integer k = 1;
                k = 2;
                print(k);
                return "";
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot reassign constant 'k'", errors)
        self.assertIn(
            "= help: declare 'k' with `let` instead of `const` to allow reassignment",
            errors,
        )

    def test_wrong_arity_help_lists_every_overload(self):
        return_code, output, errors = self.check_strict("""
            any function overloaded(integer a) { return ""; }
            any function overloaded(integer a, integer b) { return ""; }
            any function main() {
                overloaded(1, 2, 3);
                return "";
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("No overload of 'overloaded' accepts 3 argument(s)", errors)
        self.assertIn(
            "= help: available overloads: `any function overloaded(integer a)`, "
            "`any function overloaded(integer a, integer b)`",
            errors,
        )

    def test_missing_interface_method_help(self):
        return_code, output, errors = self.check_strict("""
            interface Shape {
                string name();
            }
            class Ball implements Shape {
                public integer r;
                public Ball(integer r) { this.r = r; }
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Class 'Ball' does not implement 'name()' from interface 'Shape'", errors
        )
        self.assertIn("= help: implement `string name()` on class `Ball`", errors)

    def test_missing_interface_property_help(self):
        return_code, output, errors = self.check_strict("""
            interface Configurable {
                string label;
            }
            class Broken implements Configurable {
                public integer n;
                public Broken() { this.n = 1; }
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Class 'Broken' does not implement property 'label' from interface "
            "'Configurable'",
            errors,
        )
        self.assertIn(
            "= help: add a `string label` property to class `Broken`", errors
        )

    def test_hint_blocks_align_for_two_digit_line_numbers(self):
        source = "\n".join(
            ["// filler"] * 9 + ["function add(a, b) {", "    return a + b;", "}"]
        )
        return_code, output, errors = self.check_strict(source)
        self.assertEqual(return_code, 1, output)
        self.assertIn(":10:1", errors)
        lines = errors.splitlines()
        excerpt_index = next(
            index for index, line in enumerate(lines) if "| ^" in line
        )
        hint_index = next(
            index
            for index, line in enumerate(lines)
            if line.strip().startswith("= help:")
        )
        caret_bar = lines[excerpt_index].index("|")
        hint_equals = lines[hint_index].index("=")
        self.assertEqual(caret_bar, hint_equals)


class MultiDimensionalArrayTypeTests(unittest.TestCase):
    """Array annotations must match the literal's nesting depth exactly."""

    def test_rejects_flat_array_for_two_dimensional_annotation(self):
        return_code, output, errors = check_source("""
            function main() {
                let int[][] wrong = [1, 2];
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("expected `integer[][]`, found `integer[]`", errors)

    def test_rejects_array_for_scalar_annotation(self):
        return_code, output, errors = check_source("""
            function main() {
                let int value = [1, 2];
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("expected `integer`, found `integer[]`", errors)

    def test_rejects_shallow_array_for_three_dimensional_annotation(self):
        return_code, output, errors = check_source("""
            function main() {
                let int[][][] cube = [[1, 2]];
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("expected `integer[][][]`, found `integer[][]`", errors)

    def test_rejects_deep_array_for_one_dimensional_annotation(self):
        return_code, output, errors = check_source("""
            function main() {
                let int[] wrong = [[1, 2]];
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("expected `integer[]`, found `integer[][]`", errors)

    def test_accepts_literals_whose_depth_matches_the_annotation(self):
        return_code, output, errors = check_source("""
            function main() {
                let int[][] grid = [[1, 2], [3, 4]];
                let int[][][] cube = [[[1, 2]], [[3]]];
                let int value = grid[0][1] + cube[0][0][1];
                print(value);
            }
            """)
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)

    def test_missing_let_reports_the_full_array_type(self):
        return_code, output, errors = check_source("""
            function main() {
                int[][] rows = [[1]];
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("write 'let int[][] rows = ...'", errors)


class ConstMutationCheckTests(unittest.TestCase):
    """``const`` bindings reject deep mutation during ``x check``."""

    def test_element_write_through_const_is_reported(self):
        return_code, output, errors = check_source("""
            function main() {
                const numbers = [1, 2];
                numbers[0] = 9;
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot modify element of constant 'numbers'", errors)
        self.assertIn("declare 'numbers' with `let` instead of `const`", errors)

    def test_member_write_through_const_is_reported(self):
        return_code, output, errors = check_source("""
            function main() {
                const config = {port: 1};
                config.port = 2;
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot modify member of constant 'config'", errors)

    def test_increment_through_const_is_reported(self):
        return_code, output, errors = check_source("""
            function main() {
                const counter = new Counter();
                counter.value++;
                const total = 0;
                total++;
            }
            class Counter {
                integer value = 0;
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot modify member of constant 'counter'", errors)
        self.assertIn("Cannot reassign constant 'total'", errors)

    def test_mutation_through_a_let_alias_is_allowed(self):
        return_code, output, errors = check_source("""
            function main() {
                const numbers = [1, 2];
                let alias = numbers;
                alias[0] = 9;
                print(numbers[0]);
            }
            """)
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)


class GenericSetAnnotationTests(unittest.TestCase):
    """``Set<T>`` annotations type-check against ``new Set()`` values."""

    def test_class_instances_may_be_stored_in_a_typed_set(self):
        return_code, output, errors = check_source("""
            class Employee {
                string name;
                public Employee(string name) { this.name = name; }
            }
            function main() {
                let Set<Employee> staff = new Set();
                staff.add(new Employee("Ann"));
                print(staff.size());
            }
            """)
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)

    def test_element_type_mismatch_is_reported(self):
        return_code, output, errors = check_source("""
            function main() {
                let Set<int> numbers = new Set<string>();
                print(numbers.size());
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot assign", errors)


if __name__ == "__main__":
    unittest.main()


class TryWithResourcesCheckTests(unittest.TestCase):
    """``try (let r = ...)`` bindings are checked like local variables."""

    def test_annotation_mismatch_on_a_resource_is_reported(self):
        return_code, output, errors = check_source("""
            class Res {
                public void close() { }
            }
            function main() {
                try (let integer r = new Res()) {
                    print(r);
                }
                finally {
                    print("done");
                }
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot assign 'Res' to 'r' of type 'integer'", errors)

    def test_reassigning_a_const_resource_is_reported(self):
        return_code, output, errors = check_source("""
            class Res {
                public void close() { }
            }
            function main() {
                try (const r = new Res()) {
                    r = new Res();
                }
                finally {
                    print("done");
                }
            }
            """)
        self.assertEqual(return_code, 1, output)
        self.assertIn("Cannot reassign constant 'r'", errors)

    def test_strict_typing_requires_a_resource_annotation(self):
        source = """
            class Res {
                public void close() { }
            }
            integer function work() {
                try (let r = new Res()) {
                    print(r);
                }
                finally {
                    print("done");
                }
                return 0;
            }
            """
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            config_file = Path(temporary_directory) / "x.toml"
            config_file.write_text("strict_typing = true\n", encoding="utf-8")
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = cli_main(
                    ["check", "--color", "never", str(source_file)]
                )
        self.assertEqual(return_code, 1, output.getvalue())
        self.assertIn(
            "Resource variable 'r' must have an explicit type", errors.getvalue()
        )
