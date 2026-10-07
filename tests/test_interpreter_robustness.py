import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest import mock

from xlang.config import XConfig
from xlang.module_loader import ModuleLoader
from xlang.parser import ParseError
from xlang.runtime import Interpreter, RuntimeErrorX


class BrokenOutput:
    def write(self, text):
        raise OSError(9, "Bad file descriptor")

    def flush(self):
        raise OSError(9, "Bad file descriptor")


class BrokenInput:
    def readline(self):
        raise OSError(9, "Bad file descriptor")


class RobustnessTests(unittest.TestCase):
    @staticmethod
    def runtime_only_config() -> XConfig:
        config = XConfig()
        config.features["type_checker"] = False
        return config

    def run_x(self, source, arguments=None, config=None):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            source_file = project_root / "main.x"
            source_file.write_text(source, encoding="utf-8")
            program = ModuleLoader(project_root).load_program(source_file)
            output = []
            result = Interpreter(
                arguments, output.append, config=config
            ).interpret(program)
        return result, output

    def assert_runtime_error(self, source, pattern, config=None):
        with self.assertRaisesRegex(RuntimeErrorX, pattern) as raised:
            self.run_x(source, config=config)
        return raised.exception

    def test_array_index_read_reports_bounds_and_length(self):
        error = self.assert_runtime_error(
            """
            function main() {
                let values = [1, 2];
                print(values[9]);
            }
            """,
            r"Cannot access index 9: out of range for array of length 2",
        )
        self.assertEqual(error.exception_name, "IndexOutOfBoundsException")
        self.assertEqual(error.line, 4)

    def test_string_index_read_reports_bounds_and_length(self):
        error = self.assert_runtime_error(
            """
            function main() {
                let string sample = "abc";
                print(sample[4]);
            }
            """,
            r"Cannot access index 4: out of range for string of length 3",
        )
        self.assertEqual(error.exception_name, "IndexOutOfBoundsException")

    def test_index_must_be_an_integer(self):
        self.assert_runtime_error(
            """
            function main() {
                let values = [1, 2];
                print(values["name"]);
            }
            """,
            r"Cannot access index name: index must be an integer",
        )
        self.assert_runtime_error(
            """
            function main() {
                let values = [1, 2];
                print(values[true]);
            }
            """,
            r"Cannot access index true: index must be an integer",
        )

    def test_negative_indexes_count_from_the_end(self):
        result, output = self.run_x("""
            function main() {
                let values = [1, 2, 3];
                print(values[-1]);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["3"])

        self.assert_runtime_error(
            """
            function main() {
                let values = [1, 2, 3];
                print(values[-9]);
            }
            """,
            r"Cannot access index -9: out of range for array of length 3",
        )

    def test_values_without_indexing_report_their_type(self):
        self.assert_runtime_error(
            """
            function main() {
                let number value = 5;
                print(value[0]);
            }
            """,
            r"Cannot access index 0: integer values are not indexable",
        )
        self.assert_runtime_error(
            """
            class Point {
                integer x = 1;
            }
            function main() {
                let Point origin = new Point();
                print(origin[0]);
            }
            """,
            r"Cannot access index 0: Point values are not indexable",
        )

    def test_index_assignment_failures_are_explained(self):
        error = self.assert_runtime_error(
            """
            function main() {
                let values = [1, 2];
                values[5] = 9;
            }
            """,
            r"Cannot assign to index 5: out of range for array of length 2",
        )
        self.assertEqual(error.exception_name, "IndexOutOfBoundsException")

        error = self.assert_runtime_error(
            """
            function main() {
                let string sample = "abc";
                sample[0] = "z";
            }
            """,
            r"Cannot assign to index 0: strings are immutable",
        )
        self.assertEqual(error.exception_name, "TypeException")

        self.assert_runtime_error(
            """
            function main() {
                let number value = 5;
                value[0] = 1;
            }
            """,
            r"Cannot assign to index 0: integer values do not support index assignment",
        )

    def test_object_key_access_reports_missing_keys(self):
        error = self.assert_runtime_error(
            """
            function main() {
                let object record = {name: "Ada"};
                print(record["missing"]);
            }
            """,
            r"Cannot access key missing: object has no such key",
        )
        self.assertEqual(error.exception_name, "IndexOutOfBoundsException")

    def test_optional_chain_only_swallows_missing_values(self):
        result, output = self.run_x("""
            function main() {
                let values = [1, 2];
                print(values?[9]);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["undefined"])

        self.assert_runtime_error(
            """
            function main() {
                let values = [1, 2];
                print(values?["name"]);
            }
            """,
            r"Cannot access index name: index must be an integer",
        )

    def test_index_errors_are_catchable_in_x(self):
        result, output = self.run_x("""
            function main() {
                try {
                    let values = [1];
                    print(values[5]);
                }
                catch (IndexOutOfBoundsException error) {
                    print(error.name);
                    print(error.message);
                }

                try {
                    let values = [1];
                    print(values[5]);
                }
                catch (RuntimeException error) {
                    print(error.name);
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "IndexOutOfBoundsException",
                "Cannot access index 5: out of range for array of length 1",
                "IndexOutOfBoundsException",
            ],
        )

    def test_compound_assignment_failures_are_converted(self):
        error = self.assert_runtime_error(
            """
            function main() {
                let integer value = 5;
                value /= 0;
            }
            """,
            r"Division by zero for '/'",
        )
        self.assertEqual(error.exception_name, "ArithmeticException")

        error = self.assert_runtime_error(
            """
            function main() {
                let values = [1];
                values += 5;
            }
            """,
            r"Invalid operands for '\+='",
        )
        self.assertEqual(error.exception_name, "TypeException")

        self.assert_runtime_error(
            """
            function main() {
                let values = [1];
                values[5] += 1;
            }
            """,
            r"Cannot access index 5: out of range for array of length 1",
        )
        self.assert_runtime_error(
            """
            function main() {
                let string sample = "abc";
                sample[0] += "z";
            }
            """,
            r"Cannot assign to index 0: strings are immutable",
        )

    def test_unary_increment_and_negation_report_invalid_operands(self):
        error = self.assert_runtime_error(
            """
            function main() {
                let string sample = "abc";
                sample++;
            }
            """,
            r"Invalid operands for '\+\+'",
        )
        self.assertEqual(error.exception_name, "TypeException")

        error = self.assert_runtime_error(
            """
            function main() {
                let string sample = "abc";
                print(-sample);
            }
            """,
            r"Invalid operand for '-'",
        )
        self.assertEqual(error.exception_name, "TypeException")

    def test_huge_arithmetic_and_string_operations_fail_cleanly(self):
        error = self.assert_runtime_error(
            """
            function main() {
                print("x" * 99999999999999999999);
            }
            """,
            r"Result of '\*' is too large to represent",
        )
        self.assertEqual(error.exception_name, "ArithmeticException")

        self.assert_runtime_error(
            """
            function main() {
                print("x".repeat(99999999999999999999));
            }
            """,
            r"exceeds the maximum string length of 10000000",
        )
        self.assert_runtime_error(
            """
            function main() {
                print("x".padStart(99999999999999999999));
            }
            """,
            r"exceeds the maximum string length of 10000000",
        )

    def test_circular_structures_print_without_recursion_errors(self):
        result, output = self.run_x("""
            function main() {
                let values = [1];
                values.add(values);
                print(values);
                print(values.join(","));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output[0], "[1, [Circular]]")
        self.assertIn("[Circular]", output[1])

    def test_top_level_control_flow_escapes_are_reported(self):
        error = self.assert_runtime_error("break;", r"'break' used outside of a loop")
        self.assertEqual(error.line, 1)

        error = self.assert_runtime_error(
            "continue;", r"'continue' used outside of a loop"
        )
        self.assertEqual(error.line, 1)

        result, output = self.run_x("return 5;")
        self.assertEqual(result, 5)
        self.assertEqual(output, [])

    def test_deep_recursion_reports_a_runtime_error(self):
        error = self.assert_runtime_error(
            """
            function recurse(integer depth) {
                if (depth > 0) {
                    return recurse(depth - 1);
                }
                return 0;
            }
            function main() {
                print(recurse(100000));
            }
            """,
            r"Maximum recursion depth exceeded",
        )
        self.assertEqual(error.line, 4)

    def test_deeply_nested_expressions_report_a_parse_error(self):
        source = "function main() { print(" + "(" * 3000 + "1" + ")" * 3000 + "); }"
        with self.assertRaises(ParseError):
            self.run_x(source)

    def test_wrong_argument_count_at_runtime_is_reported(self):
        error = self.assert_runtime_error(
            """
            function main() {
                let callback = (value) => value;
                print(callback());
            }
            """,
            r"'<arrow>' expects 1 argument\(s\), got 0",
            config=self.runtime_only_config(),
        )
        self.assertEqual(error.line, 4)

    def test_input_reads_a_line_without_a_prompt(self):
        with mock.patch("sys.stdin", io.StringIO("Ada\n")):
            result, output = self.run_x("""
                function main() {
                    print(input());
                }
                """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Ada"])

    def test_input_writes_the_prompt_before_reading(self):
        prompt = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("Bob\n")), mock.patch(
            "sys.stdout", prompt
        ):
            result, output = self.run_x("""
                function main() {
                    print(input("Name: "));
                }
                """)
        self.assertIsNone(result)
        self.assertEqual(prompt.getvalue(), "Name: ")
        self.assertEqual(output, ["Bob"])

    def test_input_returns_an_empty_string_at_end_of_input(self):
        with mock.patch("sys.stdin", io.StringIO("")):
            result, output = self.run_x("""
                function main() {
                    print("[" + input() + "]");
                }
                """)
        self.assertIsNone(result)
        self.assertEqual(output, ["[]"])

        with mock.patch("sys.stdin", BrokenInput()):
            result, output = self.run_x("""
                function main() {
                    print("[" + input() + "]");
                }
                """)
        self.assertIsNone(result)
        self.assertEqual(output, ["[]"])

    def test_input_reports_a_closed_output_stream(self):
        with mock.patch("sys.stdin", io.StringIO("value\n")), mock.patch(
            "sys.stdout", BrokenOutput()
        ):
            error = self.assert_runtime_error(
                """
                function main() {
                    print(input("Name: "));
                }
                """,
                r"Cannot write input prompt",
            )
        self.assertEqual(error.exception_name, "IOException")

    def test_input_validates_the_requested_type(self):
        with mock.patch("sys.stdin", io.StringIO("abc\n")), mock.patch(
            "sys.stdout", io.StringIO()
        ):
            self.assert_runtime_error(
                """
                function main() {
                    input("Value: ", "integer");
                }
                """,
                r"Expected integer input, got 'abc'",
            )

        with mock.patch("sys.stdin", io.StringIO("41\n")), mock.patch(
            "sys.stdout", io.StringIO()
        ):
            result, output = self.run_x("""
                function main() {
                    print(input("Value: ", "integer") + 1);
                }
                """)
        self.assertIsNone(result)
        self.assertEqual(output, ["42"])

    def test_missing_and_circular_imports_report_runtime_errors(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            source_file = project_root / "main.x"
            source_file.write_text(
                "import helper\nfunction main() { print(1); }\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeErrorX, "does not exist"):
                ModuleLoader(project_root).load_program(source_file)

        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            source_file = project_root / "main.x"
            source_file.write_text("import helper\n", encoding="utf-8")
            (project_root / "helper.x").write_text(
                "import main\nexport function helper() {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                RuntimeErrorX, "Circular module import detected"
            ):
                ModuleLoader(project_root).load_program(source_file)

    def test_conflicting_names_from_two_modules_are_reported(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "one.x").write_text(
                "export function shared() { return 1; }\n", encoding="utf-8"
            )
            (project_root / "two.x").write_text(
                "export function shared() { return 2; }\n", encoding="utf-8"
            )
            source_file = project_root / "main.x"
            source_file.write_text(
                "import one\nimport two\nfunction main() { print(1); }\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                RuntimeErrorX,
                r"'shared' is already declared \(from module 'one' and now "
                r"from module 'two'\)",
            ):
                ModuleLoader(project_root).load_program(source_file)

    def test_importing_the_same_module_twice_keeps_one_declaration(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "helper.x").write_text(
                """
                export function helper() {
                    print("helper body");
                }
                print("helper top");
                """,
                encoding="utf-8",
            )
            source_file = project_root / "main.x"
            source_file.write_text(
                """
                import helper
                import helper
                print("main top");
                """,
                encoding="utf-8",
            )
            program = ModuleLoader(project_root).load_program(source_file)
            output = []
            result = Interpreter(output=output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(output, ["helper top", "main top"])

    def test_shared_module_top_level_statements_run_once_across_imports(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "shared.x").write_text(
                'export function shared() { return 1; }\nprint("shared top");\n',
                encoding="utf-8",
            )
            (project_root / "one.x").write_text(
                "import shared\n"
                'export function one() { return shared(); }\n'
                'print("one top");\n',
                encoding="utf-8",
            )
            (project_root / "two.x").write_text(
                "import shared\n"
                'export function two() { return shared(); }\n'
                'print("two top");\n',
                encoding="utf-8",
            )
            source_file = project_root / "main.x"
            source_file.write_text(
                'import one\nimport two\nprint("main top");\n', encoding="utf-8"
            )
            program = ModuleLoader(project_root).load_program(source_file)
            output = []
            result = Interpreter(output=output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(output, ["shared top", "one top", "two top", "main top"])

    def test_for_loop_over_a_non_iterable_is_reported(self):
        error = self.assert_runtime_error(
            """
            function main() {
                for (integer value in 5) {
                    print(value);
                }
            }
            """,
            r"Value in for loop is not iterable",
        )
        self.assertEqual(error.exception_name, "TypeException")
        self.assertEqual(error.line, 3)

    def test_filesystem_failures_are_catchable_file_system_exceptions(self):
        config = XConfig()
        config.features["filesystem"] = True
        result, output = self.run_x(
            """
            import System.io.FileSystem
            function main() {
                try {
                    print(FileSystem.readText("/tmp/missing_x_probe.txt"));
                }
                catch (IOException error) {
                    print(error.name);
                }

                try {
                    print(FileSystem.readText("/tmp"));
                }
                catch (FileSystemException error) {
                    print(error.name);
                }
            }
            """,
            config=config,
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["FileSystemException", "FileSystemException"])

        with self.assertRaisesRegex(
            RuntimeErrorX, r"Cannot read text file '/tmp/missing_x_probe.txt'"
        ) as raised:
            self.run_x(
                """
                import System.io.FileSystem
                function main() {
                    print(FileSystem.readText("/tmp/missing_x_probe.txt"));
                }
                """,
                config=config,
            )
        self.assertEqual(raised.exception.exception_name, "FileSystemException")

    def test_heavy_loops_stay_fast(self):
        start_time = monotonic()
        result, output = self.run_x("""
            function main() {
                let string text = "";
                for (integer index in range(0, 2000)) {
                    text = text + "x";
                }
                print(text.length);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["2000"])
        self.assertLess(monotonic() - start_time, 5.0)

        start_time = monotonic()
        result, output = self.run_x("""
            function main() {
                let integer[] values = [];
                for (integer index in range(0, 100000)) {
                    values.add(index);
                }
                print(values.length);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["100000"])
        self.assertLess(monotonic() - start_time, 20.0)
