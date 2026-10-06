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


if __name__ == "__main__":
    unittest.main()
