"""`for-of` / `for-in` iteration: direct iteration over collection
instances (no `.toArray()`), string character loops, element typing, and
loop-variable inference.
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


class ForOfRuntimeTests(unittest.TestCase):
    def assertOutput(self, source, expected):
        output, error = run_x(dedent(source))
        self.assertIsNone(error, error)
        self.assertEqual(output, expected)

    def test_linkedlist_iterates_directly(self):
        self.assertOutput(
            """
            function main() {
                let LinkedList list = new LinkedList();
                list.add(1);
                list.add(2);
                for (integer v of list) { print(v); }
            }
            """,
            ["1", "2"],
        )

    def test_stack_iterates_directly(self):
        self.assertOutput(
            """
            function main() {
                let Stack stack = new Stack();
                stack.push(1);
                stack.push(2);
                for (integer v of stack) { print(v); }
            }
            """,
            ["1", "2"],
        )

    def test_queue_iterates_directly(self):
        self.assertOutput(
            """
            function main() {
                let Queue q = new Queue();
                q.enqueue("a");
                q.enqueue("b");
                for (string v of q) { print(v); }
            }
            """,
            ["a", "b"],
        )

    def test_string_iterates_characters(self):
        self.assertOutput(
            """
            function main() {
                for (string ch of "abc") { print(ch); }
            }
            """,
            ["a", "b", "c"],
        )

    def test_hashmap_iterates_keys(self):
        self.assertOutput(
            """
            function main() {
                let HashMap map = new HashMap();
                map.set("k1", 1);
                map.set("k2", 2);
                for (string k of map) { print(k); }
            }
            """,
            ["k1", "k2"],
        )

    def test_array_iterates_directly(self):
        self.assertOutput(
            """
            function main() {
                for (integer v of [1, 2, 3]) { print(v); }
            }
            """,
            ["1", "2", "3"],
        )

    def test_untyped_loop_variable_takes_element_type(self):
        self.assertOutput(
            """
            function main() {
                for (v of [1, 2]) { print(v); }
            }
            """,
            ["1", "2"],
        )

    def test_break_and_continue_inside_collection_loop(self):
        self.assertOutput(
            """
            function main() {
                let LinkedList list = new LinkedList();
                list.add(1);
                list.add(2);
                list.add(3);
                list.add(4);
                for (integer v of list) {
                    if (v == 2) { continue; }
                    if (v == 4) { break; }
                    print(v);
                }
            }
            """,
            ["1", "3"],
        )

    def test_for_in_over_object_keys(self):
        self.assertOutput(
            """
            function main() {
                let obj = { a: 1, b: 2 };
                for (string k in obj) { print(k); }
            }
            """,
            ["a", "b"],
        )


class ForOfTypeTests(unittest.TestCase):
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

    def test_matching_element_annotation_is_clean(self):
        self.assertClean(
            """
            function main() {
                for (integer v of [1, 2]) { print(v); }
                for (string c of "ab") { print(c); }
                let string[] names = ["a"];
                for (string n of names) { print(n); }
            }
            """
        )

    def test_array_element_mismatch_is_reported(self):
        self.assertTypeError(
            """
            function main() {
                for (integer v of ["a", "b"]) { print(v); }
            }
            """,
            "Cannot assign 'string' to 'v' of type 'integer'",
        )

    def test_generic_collection_element_mismatch_is_reported(self):
        self.assertTypeError(
            """
            function main() {
                let LinkedList<string> list = new LinkedList();
                list.add("x");
                for (integer v of list) { print(v); }
            }
            """,
            "Cannot assign 'string' to 'v' of type 'integer'",
        )

    def test_untyped_loop_variable_gets_element_type(self):
        self.assertTypeError(
            """
            function main() {
                for (v of [1, 2]) {
                    let string s = v;
                    print(s);
                }
            }
            """,
            "Cannot assign 'integer' to 's' of type 'string'",
        )

    def test_untyped_loop_variable_cannot_be_reassigned_to_a_stranger(self):
        self.assertTypeError(
            """
            function main() {
                for (v of [1, 2]) {
                    v = "text";
                    print(v);
                }
            }
            """,
            "Cannot assign 'string' to 'v' of type 'integer'",
        )

    def test_dynamic_iterable_stays_permissive(self):
        self.assertClean(
            """
            any function pick() { return [1, 2]; }
            function main() {
                for (any v of pick()) { print(v); }
            }
            """
        )


if __name__ == "__main__":
    unittest.main()
