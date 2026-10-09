"""``delete(...)`` — removing object keys, array indices and instance fields.

Covers the builtin declared as ``Object.delete`` (see
``DELETE_BUILTIN_NAME`` in ``xlang/interpreter/_native_builtins.py``):

* an object loses the key *and* its value; ``in``/``Object.keys`` agree
* an array element is spliced out: the array shrinks, later elements shift
* class instance fields can be removed, subject to visibility rules
* reading something that was deleted reports a real X error (never ``null``)
* misuse — wrong arity, non-target arguments, immutable containers, stdlib
  builtins — is rejected with ``IllegalArgumentException``/``TypeException``
"""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.cli import main as cli_main
from xlang.config import XConfig
from xlang.module_loader import ModuleLoader
from xlang.runtime import Interpreter, RuntimeErrorX


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def run_x(source, arguments=None, environment=None, config=None):
    """Run *source* and return ``(return_value, printed_output)``."""
    with TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        source_file = project_root / "main.x"
        source_file.write_text(dedent(source), encoding="utf-8")
        program = ModuleLoader(project_root).load_program(source_file)
        output = []
        result = Interpreter(
            arguments,
            output.append,
            config=config,
            environment=environment,
        ).interpret(program)
    return result, output


def check_source(source):
    """Run ``x check`` on *source*; return ``(exit_code, stdout, stderr)``."""
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


def run_source(source):
    """Run *source* through ``x run``; return ``(exit_code, stdout, stderr)``."""
    output = io.StringIO()
    errors = io.StringIO()
    with tempfile.TemporaryDirectory() as temporary_directory:
        source_file = Path(temporary_directory) / "main.x"
        source_file.write_text(dedent(source), encoding="utf-8")
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["run", "--no-config", "--color", "never", str(source_file)]
            )
    return return_code, output.getvalue(), errors.getvalue()


def runtime_only() -> XConfig:
    config = XConfig()
    config.features["type_checker"] = False
    return config


class DeleteObjectTests(unittest.TestCase):
    def test_delete_removes_key_and_value(self):
        result, output = run_x("""
            let object<string, integer> freqMap = {};
            freqMap["a"] = 1;
            freqMap["b"] = 2;
            delete(freqMap.a);
            print(freqMap);
            print("a" in freqMap);
            print(Object.keys(freqMap));
            print(Object.values(freqMap));
            """)
        self.assertIsNone(result)
        self.assertEqual(output[0], "{b: 2}")
        self.assertEqual(output[1], "false")
        self.assertEqual(output[2], "[b]")
        self.assertEqual(output[3], "[2]")

    def test_delete_returns_true_and_reports_a_second_delete(self):
        _, output = run_x("""
            let object<string, string> user = {"name": "Ada"};
            print(delete(user.name));
            print(user);
            """)
        self.assertEqual(output, ["true", "{}"])
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot delete key name: object has no such key"
        ):
            run_x("""
                let object<string, string> user = {"name": "Ada"};
                delete(user.name);
                delete(user.name);
                """)

    def test_delete_accepts_index_syntax(self):
        _, output = run_x("""
            let o = {"a": 1, "b": 2};
            print(delete(o["a"]));
            print(o);
            """)
        self.assertEqual(output, ["true", "{b: 2}"])

    def test_delete_missing_key_reports_the_same_error_as_reading_it(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot delete key absent: object has no such key"
        ):
            run_x("""
                let o = {"keep": 1, "drop": 2};
                delete(o.absent);
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot access key absent: object has no such key"
        ):
            run_x("""
                let o = {"keep": 1, "drop": 2};
                print(o["absent"]);
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Object has no field 'absent'"
        ):
            run_x("""
                let o = {"keep": 1, "drop": 2};
                print(o.absent);
                """)

    def test_reassigning_a_deleted_key_recreates_it(self):
        _, output = run_x("""
            let o = {"a": 1};
            delete(o.a);
            print(o);
            o.a = 5;
            print(o);
            """)
        self.assertEqual(output, ["{}", "{a: 5}"])

    def test_accessing_a_deleted_key_reports_an_error(self):
        source = """
            let o = {"a": 1, "b": 2};
            delete(o.a);
            print(o.a);
            """
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x(source)
        self.assertIn("Object has no field 'a'", caught.exception.message)
        self.assertEqual(caught.exception.line, 3)
        self.assertIsNotNone(caught.exception.end_column)

    def test_index_access_to_a_deleted_key_reports_an_error(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot access key a: object has no such key"
        ):
            run_x("""
                let o = {"a": 1};
                delete(o.a);
                print(o["a"]);
                """)

    def test_delete_then_access_error_is_rendered_with_a_span(self):
        _, _, errors = run_source("""
            let o = {"a": 1};
            delete(o.a);
            print(o["a"]);
            """)
        self.assertIn("Cannot access key a", errors)
        self.assertIn("^^^^^", errors)
        self.assertIn("-->", errors)

    def test_delete_nested_object_key(self):
        _, output = run_x("""
            let profile = {"address": {"city": "Pune", "zip": "411001"}};
            delete(profile.address.city);
            print(profile.address);
            print(profile.address.zip);
            """)
        self.assertEqual(output[0], "{zip: 411001}")
        self.assertEqual(output[1], "411001")

    def test_delete_from_record_typed_object(self):
        _, output = run_x("""
            let record{ string kind; integer n } r = {kind: "x", n: 1};
            delete(r.n);
            print(r);
            print(r.kind);
            """)
        self.assertEqual(output, ["{kind: x}", "x"])

    def test_delete_every_key_while_iterating(self):
        _, output = run_x("""
            let o = {"a": 1, "b": 2, "c": 3};
            for (let key in o) {
                print(key, delete(o[key]));
            }
            print(o);
            """)
        self.assertEqual(
            output, ["a true", "b true", "c true", "{}"]
        )

    def test_delete_every_key_from_a_snapshot(self):
        _, output = run_x("""
            let o = {"a": 1, "b": 2};
            for (let key in Object.keys(o)) {
                delete(o[key]);
            }
            print(o);
            print(Object.keys(o).length);
            """)
        self.assertEqual(output, ["{}", "0"])


class DeleteArrayTests(unittest.TestCase):
    def test_delete_splices_the_element_and_shrinks_the_array(self):
        _, output = run_x("""
            let integer[] values = [10, 20, 30, 40];
            print(delete(values[1]));
            print(values);
            print(values.length);
            """)
        self.assertEqual(output, ["true", "[10, 30, 40]", "3"])

    def test_delete_first_element_shifts_the_rest(self):
        _, output = run_x("""
            let string[] names = ["Ada", "Grace", "Linus"];
            delete(names[0]);
            print(names);
            print(names[0]);
            """)
        self.assertEqual(output, ["[Grace, Linus]", "Grace"])

    def test_delete_last_element_keeps_the_order(self):
        _, output = run_x("""
            let integer[] values = [1, 2, 3];
            delete(values[2]);
            print(values);
            print(values.length);
            """)
        self.assertEqual(output, ["[1, 2]", "2"])

    def test_delete_supports_negative_indices(self):
        _, output = run_x("""
            let integer[] values = [1, 2, 3];
            print(delete(values[-1]));
            print(values);
            """)
        self.assertEqual(output, ["true", "[1, 2]"])

    def test_delete_out_of_range_index_reports_the_read_error(self):
        with self.assertRaisesRegex(
            RuntimeErrorX,
            "Cannot delete index 9: out of range for array of length 2",
        ):
            run_x("""
                let integer[] values = [1, 2];
                delete(values[9]);
                """)

    def test_delete_empty_array_index_reports_an_error(self):
        with self.assertRaisesRegex(
            RuntimeErrorX,
            "Cannot delete index 0: out of range for array of length 0",
        ):
            run_x("""
                let integer[] values = [];
                delete(values[0]);
                """)

    def test_accessing_a_removed_index_reports_an_error(self):
        with self.assertRaisesRegex(
            RuntimeErrorX,
            "Cannot access index 3: out of range for array of length 2",
        ):
            run_x("""
                let integer[] values = [1, 2, 3];
                delete(values[2]);
                print(values[3]);
                """)

    def test_read_after_deleting_the_only_element_reports_an_error(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "out of range for array of length 0"
        ):
            run_x("""
                let integer[] values = [7];
                delete(values[0]);
                print(values[0]);
                """)

    def test_delete_rejects_non_integer_array_indices(self):
        for index in ('"a"', "1.5", "true"):
            with self.subTest(index=index):
                with self.assertRaisesRegex(
                    RuntimeErrorX, "index must be an integer"
                ):
                    run_x(f"""
                        let integer[] values = [1, 2, 3];
                        delete(values[{index}]);
                        """)

    def test_delete_nested_array_element(self):
        _, output = run_x("""
            let integer[][] matrix = [[1, 2], [3, 4]];
            print(delete(matrix[0][1]));
            print(matrix);
            """)
        self.assertEqual(output, ["true", "[[1], [3, 4]]"])

    def test_array_stays_usable_after_deletion(self):
        _, output = run_x("""
            let integer[] values = [1, 2, 3, 4];
            delete(values[0]);
            delete(values[1]);
            values.push(9);
            print(values);
            print(values.reduce((acc, item) => acc + item, 0));
            """)
        self.assertEqual(output, ["[2, 4, 9]", "15"])


class DeleteInstanceTests(unittest.TestCase):
    def test_delete_instance_field_then_access_reports_an_error(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "'Box' has no member 'label'"
        ):
            run_x("""
                class Box {
                    string label;
                    public Box(string label) { this.label = label; }
                }
                let Box box = new Box("hi");
                delete(box.label);
                print(box.label);
                """)

    def test_delete_instance_field_reports_a_second_delete(self):
        _, output = run_x("""
            class Box {
                string label;
                public Box(string label) { this.label = label; }
            }
            let Box box = new Box("hi");
            print(delete(box.label));
            print(typeOf(box));
            """)
        self.assertEqual(output, ["true", "Box"])
        with self.assertRaisesRegex(
            RuntimeErrorX, "'Box' has no member 'label'"
        ):
            run_x("""
                class Box {
                    string label;
                    public Box(string label) { this.label = label; }
                }
                let Box box = new Box("hi");
                delete(box.label);
                delete(box.label);
                """)

    def test_delete_field_inside_the_class(self):
        _, output = run_x("""
            class Session {
                private string token;
                public Session() { this.token = "secret"; }
                public boolean clear() { return delete(this.token); }
            }
            let Session session = new Session();
            print(session.clear());
            """)
        self.assertEqual(output, ["true"])
        with self.assertRaisesRegex(
            RuntimeErrorX, "'Session' has no member 'token'"
        ):
            run_x("""
                class Session {
                    private string token;
                    public Session() { this.token = "secret"; }
                    public boolean clear() { return delete(this.token); }
                }
                let Session session = new Session();
                session.clear();
                session.clear();
                """)

    def test_deleting_a_method_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot delete method 'Box.describe'"
        ):
            run_x("""
                class Box {
                    string describe() { return "box"; }
                }
                let Box box = new Box();
                delete(box.describe);
                """)

    def test_deleting_a_static_field_through_the_class_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeErrorX,
            "Cannot delete 'SECRET' from class 'Config': "
            "class members are shared by every instance",
        ):
            run_x("""
                class Config {
                    static string SECRET = "hunter2";
                }
                delete(Config.SECRET);
                """)

    def test_deleting_a_static_field_through_an_instance_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot delete static field 'Config.SECRET'"
        ):
            run_x("""
                class Config {
                    static string SECRET = "hunter2";
                }
                let Config config = new Config();
                delete(config.SECRET);
                """)

    def test_deleting_a_private_field_from_outside_is_denied(self):
        code, _, errors = check_source("""
            class Vault {
                private string secret;
                public Vault() { this.secret = "x"; }
            }
            let Vault vault = new Vault();
            delete(vault.secret);
            """)
        self.assertNotEqual(code, 0)
        self.assertIn("Cannot access private field 'Vault.secret'", errors)

    def test_private_field_delete_is_denied_at_runtime_too(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot access private field 'Vault.secret'"
        ):
            run_x("""
                class Vault {
                    private string secret;
                    public Vault() { this.secret = "x"; }
                }
                let Vault vault = new Vault();
                delete(vault.secret);
                """, config=runtime_only())


class DeleteMisuseTests(unittest.TestCase):
    def test_delete_requires_exactly_one_argument(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "delete expects exactly one argument, got 0"
        ):
            run_x("delete();")
        with self.assertRaisesRegex(
            RuntimeErrorX, "delete expects exactly one argument, got 2"
        ):
            run_x("""
                let o = {"a": 1};
                delete(o.a, o);
                """)

    def test_delete_rejects_values_that_are_not_targets(self):
        for argument in ("x", "5", '"text"', "make()"):
            with self.subTest(argument=argument):
                with self.assertRaisesRegex(
                    RuntimeErrorX, "delete expects an object key or array index"
                ):
                    run_x(f"""
                        let x = 1;
                        function make() {{ return x; }}
                        delete({argument});
                        """)

    def test_delete_reports_argument_errors_with_the_key_span(self):
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x("let x = 1;\ndelete(x);")
        self.assertEqual((caught.exception.line, caught.exception.column), (2, 8))
        self.assertIsNotNone(caught.exception.end_column)

    def test_delete_from_a_string_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "strings are immutable"
        ):
            run_x("""
                let string text = "abc";
                delete(text.length);
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "strings are immutable"
        ):
            run_x("""
                let string text = "abc";
                delete(text[0]);
                """)

    def test_delete_property_of_a_number_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "values do not support property deletion"
        ):
            run_x("""
                let integer n = 5;
                delete(n.doubled);
                """)

    def test_delete_index_of_a_class_instance_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "class 'Box' members are named, not indexed"
        ):
            run_x("""
                class Box {}
                let Box box = new Box();
                delete(box[0]);
                """)

    def test_stdlib_builtins_cannot_be_deleted(self):
        with self.assertRaisesRegex(
            RuntimeErrorX,
            "builtins are declared in the standard library and cannot be removed",
        ):
            run_x("""
                import System.utils.Math
                delete(Math.abs);
                """)

    def test_imported_namespace_members_cannot_be_deleted(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "from a namespace: imports declare their own members"
        ):
            run_x("delete(System.utils);")

    def test_delete_must_be_called_directly(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "must be called as delete\\(target\\)"
        ):
            run_x("""
                let o = {"a": 1};
                let aliased = delete;
                aliased(o["a"]);
                """)

    def test_indirect_use_of_object_delete_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Object.delete must be called as delete\\(target\\)"
        ):
            run_x("""
                let o = {"a": 1};
                let aliased = Object.delete;
                aliased(o["a"]);
                """)

    def test_object_delete_form_works_the_same(self):
        _, output = run_x("""
            let o = {"a": 1, "b": 2};
            print(Object.delete(o["a"]));
            print(o);
            """)
        self.assertEqual(output, ["true", "{b: 2}"])


class DeleteDiagnosticsTests(unittest.TestCase):
    def test_check_accepts_delete_calls(self):
        code, out, errors = check_source("""
            let object<string, integer> counts = {"a": 1};
            delete(counts.a);
            let integer[] values = [1, 2, 3];
            delete(values[0]);
            """)
        self.assertEqual(code, 0, errors)
        self.assertIn("types are valid", out)

    def test_check_defers_object_key_checks_to_runtime(self):
        """Object keys are not statically known, so the run reports them."""
        code, _, errors = check_source("""
            let o = {"a": 1};
            delete(o.b);
            """)
        self.assertEqual(code, 0, errors)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot delete key b: object has no such key"
        ):
            run_x("""
                let o = {"a": 1};
                delete(o.b);
                """)

    def test_delete_is_a_known_builtin_name(self):
        code, _, errors = check_source("delete();")
        self.assertNotIn("Name 'delete' is not defined", errors)

    def test_type_of_delete_is_function(self):
        _, output = run_x("print(typeOf(delete));")
        self.assertEqual(output, ["function"])

    def test_check_leaves_arity_errors_to_runtime(self):
        """The checker knows ``delete``; arity stays a runtime concern."""
        code, _, errors = check_source("""
            let o = {"a": 1};
            delete(o["a"], 2);
            """)
        self.assertEqual(code, 0, errors)
        self.assertNotIn("Name 'delete' is not defined", errors)


class DeleteExampleTests(unittest.TestCase):
    def test_frequency_map_example_from_main_x(self):
        """The snippet written in ``examples/main.x`` deletes ``freqMap.p``."""
        result, output = run_x("""
            let object<string, integer> freqMap = {};
            let string userInput = "Hello";
            for (let char in userInput) {
                if (char in freqMap) {
                    freqMap[char] = freqMap[char] + 1;
                } else {
                    freqMap[char] = 1;
                }
            }
            freqMap.p = 34;
            delete(freqMap.p);
            print(freqMap);
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["{H: 1, e: 1, l: 2, o: 1}"])

    def test_delete_of_an_undeclared_object_reports_the_name(self):
        """``examples/main.x`` typo probes: ``delete(frreMap.H)``."""
        with self.assertRaisesRegex(
            RuntimeErrorX, "Name 'frreMap' is not defined"
        ):
            run_x("""
                let object<string, integer> freqMap = {};
                delete(frreMap.H);
                """)


if __name__ == "__main__":
    unittest.main()
