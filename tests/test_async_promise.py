"""`Promise<T>` async/await: runtime semantics, call typing, and the
JavaScript-compatible await rules.

X has no Promise constructor, `.then`, or `.catch` — only `async`/`await`,
so every test here also pins down that the promise-combinator API surface
stays rejected.
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


class AsyncPromiseRuntimeTests(unittest.TestCase):
    def assertOutput(self, source, expected):
        output, error = run_x(dedent(source))
        self.assertIsNone(error, error)
        self.assertEqual(output, expected)

    def assertRuntimeError(self, source, fragment):
        output, error = run_x(dedent(source))
        self.assertIsNotNone(error, f"expected an error, got output {output}")
        self.assertIn(fragment, error)

    def test_enum_record_promise_example(self):
        self.assertOutput(
            """
            enum Gender {
                MALE,
                FEMALE
            }

            Promise<{ obj: { string name ; Gender gender } }> async function myFunc() {
                return { obj: { name: "John", gender: Gender.MALE } };
            }

            async function main() {
                const result = await myFunc();
                print(result.obj.name);
                print(result.obj.gender);
            }
            """,
            ["John", "MALE"],
        )

    def test_async_call_is_a_promise_and_await_unwraps(self):
        self.assertOutput(
            """
            string async function loadName() { return "Alice"; }
            async function main() {
                print(typeOf(loadName()));
                print(typeOf(await loadName()));
                let Promise<string> p = loadName();
                print(await p);
            }
            """,
            ["Promise", "string", "Alice"],
        )

    def test_plain_t_async_annotation_awaits_to_t(self):
        self.assertOutput(
            """
            string async function loadName() { return "Alice"; }
            async function main() { print(await loadName()); }
            """,
            ["Alice"],
        )

    def test_async_body_returning_another_promise_flattens(self):
        self.assertOutput(
            """
            async function inner() { return 7; }
            Promise<integer> async function outer() { return inner(); }
            async function main() { print(await outer()); }
            """,
            ["7"],
        )

    def test_async_body_await_before_return(self):
        self.assertOutput(
            """
            async function inner() { return 7; }
            Promise<integer> async function outer() { return await inner(); }
            async function main() { print(await outer()); }
            """,
            ["7"],
        )

    def test_promise_void_function_needs_no_return(self):
        self.assertOutput(
            """
            Promise<void> async function nothing() { }
            async function main() {
                await nothing();
                print("ok");
            }
            """,
            ["ok"],
        )

    def test_await_as_statement_is_allowed(self):
        self.assertOutput(
            """
            string async function loadName() { return "Alice"; }
            async function main() {
                await loadName();
                print("done");
            }
            """,
            ["done"],
        )

    def test_await_of_plain_function_result_yields_value(self):
        # JavaScript: awaiting a function result that is not a promise is a
        # no-op unwrap, so the value comes through unchanged.
        self.assertOutput(
            """
            string function plain() { return "ok"; }
            async function main() { print(await plain()); }
            """,
            ["ok"],
        )

    # ------------------------------------------------------------------
    # The promise API surface must stay closed.
    # ------------------------------------------------------------------
    def test_new_promise_is_rejected(self):
        self.assertRuntimeError(
            """
            function main() { let p = new Promise((resolve) => resolve(1)); }
            """,
            "Name 'Promise' is not defined",
        )

    def test_then_on_async_result_is_rejected(self):
        self.assertRuntimeError(
            """
            async function loadName() { return "Alice"; }
            function main() {
                let p = loadName();
                print(p.then((v) => v));
            }
            """,
            "did you forget 'await'",
        )

    def test_discarded_async_call_is_rejected(self):
        self.assertRuntimeError(
            """
            async function loadName() { return "Alice"; }
            async function main() {
                loadName();
                print("floating");
            }
            """,
            "The asynchronous result was discarded",
        )

    def test_catch_on_async_result_is_rejected(self):
        self.assertRuntimeError(
            """
            async function loadName() { return "Alice"; }
            function main() {
                let p = loadName();
                print(p.catch((e) => e));
            }
            """,
            "did you forget 'await'",
        )


class AsyncPromiseTypeTests(unittest.TestCase):
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

    def test_enum_record_promise_example_is_clean(self):
        self.assertClean(
            """
            enum Gender {
                MALE,
                FEMALE
            }

            Promise<{ obj: { string name ; Gender gender } }> async function myFunc() {
                return { obj: { name: "John", gender: Gender.MALE } };
            }

            async function main() {
                const result = await myFunc();
                print(result.obj.name);
            }
            """
        )

    def test_await_unwraps_promise_annotation(self):
        self.assertClean(
            """
            string async function loadName() { return "Alice"; }
            async function main() {
                let string s = await loadName();
                print(s);
            }
            """
        )

    def test_call_without_await_has_promise_type(self):
        self.assertClean(
            """
            string async function loadName() { return "Alice"; }
            async function main() {
                let Promise<string> p = loadName();
                print(await p);
            }
            """
        )

    def test_async_call_without_await_cannot_assign_to_t(self):
        self.assertTypeError(
            """
            string async function loadName() { return "Alice"; }
            function main() { let string s = loadName(); print(s); }
            """,
            "Cannot assign 'Promise<string>' to 's' of type 'string'",
        )

    def test_async_body_checked_against_unwrapped_t(self):
        self.assertTypeError(
            """
            string async function loadName() { return 42; }
            function main() { print("x"); }
            """,
            "Return type 'integer' is not compatible with 'string'",
        )

    def test_promise_void_rejects_value_return(self):
        self.assertTypeError(
            """
            Promise<void> async function nothing() { return 5; }
            function main() { print("x"); }
            """,
            "Function 'nothing' is declared 'void' and cannot return a value",
        )

    def test_plain_function_promise_annotation_is_not_optional(self):
        self.assertTypeError(
            """
            Promise<string> function broken() { return 42; }
            function main() { print("x"); }
            """,
            "Return type 'integer' is not compatible with 'Promise<string>'",
        )

    def test_await_type_flows_into_let_annotation(self):
        self.assertTypeError(
            """
            string async function loadName() { return "Alice"; }
            async function main() {
                let integer n = await loadName();
                print(n);
            }
            """,
            "Cannot assign 'string' to 'n' of type 'integer'",
        )

    def test_async_body_returning_inner_promise_is_clean(self):
        self.assertClean(
            """
            async function inner() { return 7; }
            Promise<integer> async function outer() { return inner(); }
            async function main() { print(await outer()); }
            """
        )

    def test_non_async_function_cannot_await(self):
        return_code, output, errors = self.check_source(
            """
            function main() {
                await sleep(1);
            }
            """
        )
        self.assertEqual(return_code, 1, output)
        self.assertIn("only valid inside an async function", errors)

    def test_await_outside_function_body_is_rejected(self):
        return_code, output, errors = self.check_source(
            """
            string async function loadName() { return "Alice"; }
            let string s = await loadName();
            function main() { print(s); }
            """
        )
        self.assertEqual(return_code, 1, output)
        self.assertIn("only valid inside an async function", errors)


if __name__ == "__main__":
    unittest.main()
