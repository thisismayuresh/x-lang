"""Security posture of the X interpreter.

Pins the properties that keep untrusted X programs from escaping into the
host Python runtime: no dunder/eval/exec escape hatches, import resolution
stays inside `.x` sources, diagnostics never leak interpreter internals or
memory addresses, resource limits fail with clean X errors instead of Python
tracebacks, and the JS-compatible loose equality rules the docs warn about
behave exactly as documented.
"""
import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.cli import main


def run_cli(source: str, check_only: bool = False):
    """Write *source* to a temp project and run `x check`/`x run`.

    Returns (return_code, stdout, stderr).
    """
    with tempfile.TemporaryDirectory() as temporary_directory:
        source_file = Path(temporary_directory) / "main.x"
        source_file.write_text(
            textwrap.dedent(source).lstrip("\n"), encoding="utf-8"
        )
        arguments = ["--no-config", "--color", "never"]
        arguments.append("check" if check_only else "run")
        arguments.append(str(source_file))
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
    return return_code, output.getvalue(), errors.getvalue()


class NoPythonEscapeTests(unittest.TestCase):
    def assertRejected(self, source, fragment):
        return_code, output, errors = run_cli(source)
        combined = output + errors
        self.assertEqual(return_code, 1, combined)
        self.assertIn(fragment, combined)

    def test_dunder_member_access_on_string_is_rejected(self):
        self.assertRejected(
            'function main() { print("x".__class__); }',
            "Value has no member '__class__'",
        )

    def test_dunder_member_access_on_array_is_rejected(self):
        self.assertRejected(
            "function main() { print([].__class__); }",
            "Value has no member '__class__'",
        )

    def test_dunder_member_access_on_object_literal_is_rejected(self):
        self.assertRejected(
            "function main() { let o = {a: 1}; print(o.__dict__); }",
            "Object has no field '__dict__'",
        )

    def test_tuple_literal_does_not_parse(self):
        self.assertRejected(
            "function main() { print(()); }",
            "expected an expression",
        )

    def test_eval_and_exec_are_undefined(self):
        self.assertRejected(
            'function main() { print(eval("1+1")); }',
            "Name 'eval' is not defined",
        )
        self.assertRejected(
            'function main() { print(exec("x = 1")); }',
            "Name 'exec' is not defined",
        )

    def test_reflection_builtins_are_undefined(self):
        for call in (
            'Function("return 1")',
            'getattr(System, "x")',
            "globals()",
            'open("/etc/passwd")',
            '__import__("os")',
        ):
            with self.subTest(call=call):
                return_code, output, errors = run_cli(
                    f"function main() {{ print({call}); }}"
                )
                combined = output + errors
                self.assertEqual(return_code, 1, combined)
                self.assertIn("is not defined", combined)

    def test_type_of_user_function_reports_x_level_name(self):
        return_code, output, errors = run_cli(
            """
            function greet() { return 1; }
            function main() { print(typeOf(greet)); }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("function", output)


class ImportSandboxTests(unittest.TestCase):
    def assertRejected(self, source, fragment):
        return_code, output, errors = run_cli(source)
        combined = output + errors
        self.assertEqual(return_code, 1, combined)
        self.assertIn(fragment, combined)

    def test_python_modules_do_not_resolve(self):
        for module in ("os", "subprocess", "sys", "xlang.runtime"):
            with self.subTest(module=module):
                self.assertRejected(
                    f"import {module}\nfunction main() {{ print(\"x\"); }}",
                    "does not exist",
                )

    def test_absolute_and_parent_paths_are_parse_errors(self):
        for path in ("/etc/passwd", "../../secret", "../x"):
            with self.subTest(path=path):
                self.assertRejected(
                    f"import {path}\nfunction main() {{ print(\"x\"); }}",
                    "Expected import path",
                )

    def test_dotted_imports_stay_inside_dot_x_files(self):
        self.assertRejected(
            "import java.lang.Runtime\nfunction main() { print(\"x\"); }",
            "does not exist",
        )


class NoInternalLeakTests(unittest.TestCase):
    def assertOutput(self, source, expected):
        return_code, output, errors = run_cli(source)
        self.assertEqual(return_code, 0, errors)
        printed = [line for line in output.splitlines() if line]
        self.assertEqual(printed, expected)

    def test_printing_a_function_never_shows_python_repr(self):
        return_code, output, errors = run_cli(
            """
            function greet() { return 1; }
            function main() { print(greet); }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("[function greet]", output)
        self.assertNotIn("0x", output)
        self.assertNotIn("bound method", output)
        self.assertNotIn("OverloadedFunction", output)

    def test_printing_a_namespace_builtin_never_shows_python_repr(self):
        return_code, output, errors = run_cli(
            """
            function main() { print(System.concurrent.Lock); }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("[function Lock]", output)
        self.assertNotIn("0x", output)
        self.assertNotIn("_lock_factory", output)

    def test_printing_a_lock_handle_is_a_stable_token(self):
        self.assertOutput(
            """
            function main() { print(System.concurrent.Lock()); }
            """,
            ["[Lock]"],
        )

    def test_printing_a_thread_builtin_never_shows_python_repr(self):
        return_code, output, errors = run_cli(
            """
            function main() { print(System.concurrent.Thread.start); }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("[function Thread.start]", output)
        self.assertNotIn("0x", output)


class ResourceLimitTests(unittest.TestCase):
    def assertCleanXError(self, source, fragment):
        return_code, output, errors = run_cli(source)
        combined = output + errors
        self.assertEqual(return_code, 1, combined)
        self.assertIn(fragment, combined)
        self.assertNotIn("Traceback (most recent call last)", combined)

    def test_unbounded_recursion_is_a_clean_x_error(self):
        self.assertCleanXError(
            """
            function f(integer n) { return f(n + 1); }
            function main() { print(f(0)); }
            """,
            "the program nests too deeply",
        )

    def test_string_repeat_is_capped(self):
        self.assertCleanXError(
            """
            function main() { print("ab".repeat(99999999999).length); }
            """,
            "exceeds the maximum string length of 10000000",
        )

    def test_parser_depth_is_capped(self):
        depth = 50000
        self.assertCleanXError(
            "function main() { print(" + "(" * depth + "1" + ")" * depth + "); }",
            "Program is nested too deeply to parse",
        )

    def test_json_parse_depth_is_a_clean_x_error(self):
        depth = 100000
        self.assertCleanXError(
            "import System.utils.JSON\n"
            "function main() {\n"
            '    let s = "' + "[" * depth + "]" * depth + '";\n'
            "    let v = JSON.parse(s);\n"
            '    print("parsed");\n'
            "}\n",
            "nests too deeply",
        )

    def test_infinite_sleep_duration_is_rejected(self):
        self.assertCleanXError(
            """
            async function main() {
                let v = parseFloat("1e400");
                await sleep(v);
            }
            """,
            "sleep duration must be a finite number of milliseconds",
        )

    def test_infinite_try_lock_timeout_is_rejected(self):
        self.assertCleanXError(
            """
            function main() {
                let lock = System.concurrent.Lock();
                let v = parseFloat("1e400");
                print(lock.tryLock(v));
            }
            """,
            "Lock.tryLock duration must be a finite number of milliseconds",
        )

    def test_math_pow_overflow_is_a_clean_x_error(self):
        self.assertCleanXError(
            """
            import System.utils.Math
            function main() {
                let x = Math.pow(9, 999999999);
                print(x);
            }
            """,
            "math range error",
        )


class InjectionTests(unittest.TestCase):
    def test_null_byte_escape_is_a_parse_error(self):
        return_code, output, errors = run_cli(
            'function main() { print("a\\0b"); }'
        )
        combined = output + errors
        self.assertEqual(return_code, 1, combined)
        self.assertIn("Unknown escape sequence", combined)

    def test_raw_null_byte_in_string_literal_is_a_lex_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_bytes(
                b'function main() { print("a\x00b"); }\n'
            )
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = main(
                    ["--no-config", "--color", "never", "run", str(source_file)]
                )
        combined = output.getvalue() + errors.getvalue()
        self.assertEqual(return_code, 1, combined)
        self.assertIn("null byte", combined)

    def test_raw_null_byte_in_template_literal_is_a_lex_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_bytes(
                b"function main() { print(`a\x00b`); }\n"
            )
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = main(
                    ["--no-config", "--color", "never", "run", str(source_file)]
                )
        combined = output.getvalue() + errors.getvalue()
        self.assertEqual(return_code, 1, combined)
        self.assertIn("null byte", combined)

    def test_line_break_escapes_stay_data_not_syntax(self):
        # \r\n inside a string literal is data; it must not terminate the
        # statement or smuggle a second one.
        return_code, output, errors = run_cli(
            r"""
            function main() {
                let s = "one\r\ntwo";
                print(s.length);
                print(s.contains("one\r\ntwo"));
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        printed = [line for line in output.splitlines() if line]
        # "one" + CR + "LF" + "two" is 8 characters.
        self.assertEqual(printed[0], "8")


class EqualitySemanticsTests(unittest.TestCase):
    """JS-compatible loose equality — the surface the security docs warn
    about when `==` is used for checks like `input == 1`."""

    def assertOutput(self, source, expected):
        return_code, output, errors = run_cli(source)
        self.assertEqual(return_code, 0, errors)
        printed = [line for line in output.splitlines() if line]
        self.assertEqual(printed, expected)

    def test_loose_equality_matches_javascript(self):
        self.assertOutput(
            """
            function main() {
                print(1 == "1");
                print(0 == "");
                print("10" == 10);
                print(null == false);
                print(null == undefined);
            }
            """,
            ["true", "true", "true", "false", "true"],
        )

    def test_strict_equality_rejects_type_juggling(self):
        self.assertOutput(
            """
            function main() {
                print(1 === "1");
                print("10" === 10);
                print(null === undefined);
                print(0 === "");
            }
            """,
            ["false", "false", "false", "false"],
        )


if __name__ == "__main__":
    unittest.main()
