"""Generic classes and functions: receiver-based member substitution,
`new` inference, call-site type-argument inference, invariance, and
method-argument checking.

Runtime round trips live here too — the interpreter's dynamic dispatch must
agree with what the checker promises.
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


BOX_CLASS = """
class Box<T> {
    public T item;
    public Box(T v) { this.item = v; }
    public T get() { return this.item; }
    public void set(T v) { this.item = v; }
}
"""


class GenericRuntimeTests(unittest.TestCase):
    def assertOutput(self, source, expected):
        output, error = run_x(dedent(source))
        self.assertIsNone(error, error)
        self.assertEqual(output, expected)

    def test_box_round_trip_through_generic_members(self):
        self.assertOutput(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                print(b.get());
                b.set(5);
                print(b.item);
            }
            """,
            ["1", "5"],
        )

    def test_nested_generic_boxes(self):
        self.assertOutput(
            """
            class Box<T> {
                public T item;
                public Box(T v) { this.item = v; }
            }
            function main() {
                let Box<Box<integer>> outer = new Box(new Box(1));
                print(outer.item.item);
            }
            """,
            ["1"],
        )

    def test_generic_function_inferred_at_call_site(self):
        self.assertOutput(
            """
            function <T> T identity(T value) { return value; }
            function main() {
                print(identity("hi"));
                print(identity(5));
            }
            """,
            ["hi", "5"],
        )


class CheckerHarness(unittest.TestCase):
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


class GenericCheckerTests(CheckerHarness):
    # ------------------------------------------------------------------
    # Receiver-based member substitution
    # ------------------------------------------------------------------
    def test_method_return_substitutes_receiver_arguments(self):
        self.assertClean(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                let integer n = b.get();
                print(n);
            }
            """
        )

    def test_method_return_mismatch_is_reported(self):
        self.assertTypeError(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                let string s = b.get();
                print(s);
            }
            """,
            "Cannot assign 'integer' to 's' of type 'string'",
        )

    def test_field_access_substitutes_receiver_arguments(self):
        self.assertTypeError(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                let string x = b.item;
                print(x);
            }
            """,
            "Cannot assign 'integer' to 'x' of type 'string'",
        )

    def test_nested_generic_field_access_is_typed(self):
        self.assertClean(
            """
            class Box<T> {
                public T item;
                public Box(T v) { this.item = v; }
            }
            function main() {
                let Box<Box<integer>> outer = new Box(new Box(1));
                let integer deep = outer.item.item;
                print(deep);
            }
            """
        )

    # ------------------------------------------------------------------
    # Invariance and `new` inference
    # ------------------------------------------------------------------
    def test_generic_instances_are_invariant(self):
        self.assertTypeError(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                let Box<string> s = b;
                print(s.get());
            }
            """,
            "Cannot assign 'Box<integer>' to 's' of type 'Box<string>'",
        )

    def test_explicit_new_type_arguments_must_match_annotation(self):
        self.assertTypeError(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box<string>("hi");
                print(b.get());
            }
            """,
            "Cannot assign 'Box<string>' to 'b' of type 'Box<integer>'",
        )

    def test_new_infers_class_arguments_from_constructor(self):
        self.assertClean(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                let integer n = b.get();
                print(n);
            }
            """
        )

    def test_new_inferred_arguments_clash_with_annotation(self):
        self.assertTypeError(
            BOX_CLASS
            + """
            function main() {
                let Box<string> b = new Box(1);
                print(b.get());
            }
            """,
            "Cannot assign 'Box<integer>' to 'b' of type 'Box<string>'",
        )

    # ------------------------------------------------------------------
    # Call-site inference for generic functions
    # ------------------------------------------------------------------
    def test_generic_function_argument_drives_result_type(self):
        self.assertClean(
            """
            function <T> T identity(T value) { return value; }
            function main() {
                let string a = identity("hi");
                let integer b = identity(5);
                print(a);
                print(b);
            }
            """
        )

    def test_generic_function_inferred_result_rejects_mismatch(self):
        self.assertTypeError(
            """
            function <T> T identity(T value) { return value; }
            function main() {
                let string a = identity(5);
                print(a);
            }
            """,
            "Cannot assign 'integer' to 'a' of type 'string'",
        )

    def test_generic_array_parameter_binds_element_type(self):
        self.assertClean(
            """
            function <T> T first(T[] items) { return items[0]; }
            function main() {
                let string s = first(["a", "b"]);
                print(s);
            }
            """
        )

    def test_generic_array_parameter_mismatch_is_reported(self):
        self.assertTypeError(
            """
            function <T> T first(T[] items) { return items[0]; }
            function main() {
                let string s = first([1, 2]);
                print(s);
            }
            """,
            "Cannot assign 'integer' to 's' of type 'string'",
        )

    def test_explicit_type_arguments_still_check_arguments(self):
        self.assertTypeError(
            """
            function <T> T identity(T value) { return value; }
            function main() {
                print(identity<integer>("text"));
            }
            """,
            "Argument 1 of 'identity' has type 'string', expected 'integer'",
        )

    # ------------------------------------------------------------------
    # Method arguments are checked against the receiver's type arguments
    # ------------------------------------------------------------------
    def test_method_argument_checked_against_receiver_type(self):
        self.assertTypeError(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                b.set("wrong");
            }
            """,
            "Argument 1 of 'set' has type 'string', expected 'integer'",
        )

    def test_method_arity_is_checked(self):
        self.assertTypeError(
            BOX_CLASS
            + """
            function main() {
                let Box<integer> b = new Box(1);
                let integer n = b.get("extra");
                print(n);
            }
            """,
            "No overload of 'get' accepts 1 argument(s)",
        )


class CollectionMethodArgumentTests(CheckerHarness):
    """Python-backed collections have no X declarations, so their instance
    methods are checked against the receiver's type arguments by the
    dedicated collection rule table instead of ``_check_overloads``."""

    def test_element_add_type_mismatch_is_reported(self):
        self.assertTypeError(
            """
            import System.utils.Collections.LinkedList
            function main() {
                let List<integer> nums = new List<integer>();
                nums.add("x");
            }
            """,
            "Argument 1 of 'add' has type 'string', expected 'integer'",
        )

    def test_element_add_matching_type_checks_clean(self):
        self.assertClean(
            """
            import System.utils.Collections.LinkedList
            function main() {
                let List<integer> nums = new List<integer>();
                nums.add(5);
                print(nums.size());
            }
            """
        )

    def test_stack_push_checked_against_element_type(self):
        self.assertTypeError(
            """
            import System.utils.Collections.Stack
            function main() {
                let Stack<string> names = new Stack<string>();
                names.push(3);
            }
            """,
            "Argument 1 of 'push' has type 'integer', expected 'string'",
        )

    def test_queue_enqueue_checked_against_element_type(self):
        self.assertTypeError(
            """
            import System.utils.Collections.Queue
            function main() {
                let Queue<string> names = new Queue<string>();
                names.enqueue(3);
            }
            """,
            "Argument 1 of 'enqueue' has type 'integer', expected 'string'",
        )

    def test_set_add_checked_against_element_type(self):
        self.assertTypeError(
            """
            import System.utils.Collections.Set
            function main() {
                let Set<integer> seen = new Set<integer>();
                seen.add("x");
            }
            """,
            "Argument 1 of 'add' has type 'string', expected 'integer'",
        )

    def test_list_contains_checked_against_element_type(self):
        self.assertTypeError(
            """
            import System.utils.Collections.LinkedList
            function main() {
                let List<string> names = new List<string>();
                print(names.contains(5));
            }
            """,
            "Argument 1 of 'contains' has type 'integer', expected 'string'",
        )

    def test_list_get_checked_against_integer_index(self):
        self.assertTypeError(
            """
            import System.utils.Collections.LinkedList
            function main() {
                let List<string> names = new List<string>();
                print(names.get("first"));
            }
            """,
            "Argument 1 of 'get' has type 'string', expected 'integer'",
        )

    def test_map_set_key_and_value_are_both_checked(self):
        self.assertTypeError(
            """
            import System.utils.Collections.HashMap
            function main() {
                let HashMap<string, integer> counts = new HashMap<string, integer>();
                counts.set("a", "wrong");
            }
            """,
            "Argument 2 of 'set' has type 'string', expected 'integer'",
        )

    def test_map_get_checked_against_key_type(self):
        self.assertTypeError(
            """
            import System.utils.Collections.HashMap
            function main() {
                let HashMap<string, integer> counts = new HashMap<string, integer>();
                print(counts.get(2));
            }
            """,
            "Argument 1 of 'get' has type 'integer', expected 'string'",
        )

    def test_dynamic_collection_without_type_arguments_stays_permissive(self):
        self.assertClean(
            """
            import System.utils.Collections.LinkedList
            function main() {
                let xs = new LinkedList();
                xs.add(1);
                xs.add("any");
                print(xs.size());
            }
            """
        )


if __name__ == "__main__":
    unittest.main()
