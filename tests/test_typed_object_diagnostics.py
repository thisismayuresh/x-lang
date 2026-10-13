"""Typed-object diagnostics: per-key errors for ``object<K, V>`` literals."""

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

from xlang.cli import main
from xlang.playground import _diagnostic
from xlang.runtime import Interpreter, RuntimeErrorX
from xlang.typecheck.errors import TypeCheckError


class TypedObjectDiagnosticTests(unittest.TestCase):
    def check_source(self, source):
        with TemporaryDirectory() as temporary_directory:
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
        self.assertIn("types are valid", output)
        self.assertEqual(errors, "")

    def assertError(self, source, *fragments):
        return_code, output, errors = self.check_source(source)
        self.assertEqual(return_code, 1, output)
        self.assertEqual(output, "")
        for fragment in fragments:
            self.assertIn(fragment, errors)
        return errors

    def test_unknown_key_via_alias_names_the_key_and_allowed_keys(self):
        errors = self.assertError(
            """
            type K = "theme" | "mode";
            function main() {
                let object<K, string> settings = { theme: "dark", zz: "x" };
                print(settings);
            }
            """,
            "Object key 'zz' is not allowed in 'settings'",
            "allowed keys: \"theme\", \"mode\"",
            "remove the 'zz' entry",
        )
        self.assertNotIn("Cannot assign", errors)

    def test_unknown_key_via_inline_union(self):
        self.assertError(
            """
            function main() {
                let object<"a" | "b", integer> counts = { zz: 1 };
                print(counts);
            }
            """,
            "Object key 'zz' is not allowed in 'counts'",
            "allowed keys: \"a\", \"b\"",
        )

    def test_caret_underlines_the_offending_key_token(self):
        errors = self.assertError(
            """
            type K = "a" | "b";
            function main() {
                let object<K, string> m = { a: "1", zz: "2" };
                print(m);
            }
            """,
        )
        caret_line = next(
            line for line in errors.splitlines() if "^" in line and "|" in line
        )
        covered = caret_line.split("|")[-1]
        self.assertIn("zz", covered)
        self.assertNotIn('"1"', covered)

    def test_one_error_per_unknown_key(self):
        errors = self.assertError(
            """
            type K = "a" | "b";
            function main() {
                let object<K, string> m = { zz: "1", yy: "2" };
                print(m);
            }
            """,
            "Object key 'zz' is not allowed",
            "Object key 'yy' is not allowed",
        )
        self.assertEqual(errors.count("error: Object key"), 2)

    def test_wrong_value_type_reports_expected_and_found(self):
        self.assertError(
            """
            function main() {
                let object<string, string> m = { age: 21 };
                print(m);
            }
            """,
            "Value for key 'age' in 'm' has the wrong type",
            "expected `string`, found `integer`",
        )

    def test_call_argument_literal_gets_the_friendly_error(self):
        self.assertError(
            """
            type K = "a" | "b";
            any function take(object<K, string> settings) { print(settings); }
            any function main() {
                take({ theme: "x" });
            }
            """,
            "Object key 'theme' is not allowed in argument 1 of 'take'",
            "parameter 'settings' is typed",
        )

    def test_assignment_literal_gets_the_friendly_error(self):
        self.assertError(
            """
            type K = "a" | "b";
            any function main() {
                let object<K, string> m = { a: "1" };
                m = { zz: "2" };
                print(m);
            }
            """,
            "Object key 'zz' is not allowed in 'm'",
        )

    def test_valid_literal_and_spread_stay_clean(self):
        self.assertClean(
            """
            type K = "a" | "b";
            any function main() {
                let object<K, string> m = { a: "1", b: "2" };
                let object<K, string> n = { ...m, b: "3" };
                print(m, n);
            }
            """
        )

    def test_alias_annotation_spelling_is_preserved_in_notes(self):
        errors = self.assertError(
            """
            type SettingsKey = "theme" | "mode";
            export const object<SettingsKey, string> DEFAULTS = { zz: "x" };
            any function main() { print(DEFAULTS); }
            """,
            "typed `object<SettingsKey, string>`",
        )
        self.assertNotIn('"theme"|"mode")', errors)


class TypedObjectArrayRuntimeTests(unittest.TestCase):
    """``object<K, V>[]`` works; inline unions are re-checked at runtime."""

    def run_program(self, source):
        from xlang.lexer import Lexer
        from xlang.parser import Parser
        from xlang.config import XConfig

        tokens = Lexer(dedent(source), "main.x").tokenize()
        program = Parser(tokens, XConfig().features, "main.x").parse()
        printed: list[str] = []
        interpreter = Interpreter([], printed.append, config=XConfig())
        interpreter.interpret(program)
        return printed

    def test_array_of_typed_objects_declares_and_indexes(self):
        output = self.run_program(
            """
            any function main() {
                let object<string, integer>[] rows = [{ a: 1 }, { b: 2 }];
                print(rows);
                print(rows[0]);
            }
            """
        )
        self.assertEqual(output[0], "[{a: 1}, {b: 2}]")
        self.assertEqual(output[1], "{a: 1}")

    def test_array_of_typed_objects_as_parameter(self):
        output = self.run_program(
            """
            any function total(object<string, integer>[] rows) {
                print(rows);
            }
            any function main() {
                total([{ a: 1 }]);
            }
            """
        )
        self.assertEqual(output, ["[{a: 1}]"])

    def test_runtime_rejects_key_outside_inline_union(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "object key 'zz'"
        ):
            self.run_program(
                """
                any function main() {
                    let object<"a" | "b", string> m = { a: "1" };
                    m["zz"] = "2";
                    print(m);
                }
                """
            )

    def test_runtime_accepts_key_inside_inline_union(self):
        output = self.run_program(
            """
            any function main() {
                let object<"a" | "b", string> m = { a: "1" };
                m["b"] = "2";
                print(m);
            }
            """
        )
        self.assertEqual(output, ["{a: 1, b: 2}"])


class PlaygroundDiagnosticPayloadTests(unittest.TestCase):
    """The WASM payload carries everything the rustc-style renderer needs."""

    def test_typecheck_payload_includes_notes_helps_and_span(self):
        error = TypeCheckError(
            "Object key 'zz' is not allowed in 'A'",
            source_name="main.x",
            line=3,
            column=30,
            notes=["'A' is typed `object<K, string>`", 'allowed keys: "a", "b"'],
            helps=["remove the 'zz' entry"],
            end_line=3,
            end_column=32,
        )
        item = _diagnostic("typecheck", error)
        self.assertEqual(item["message"], "Object key 'zz' is not allowed in 'A'")
        self.assertEqual(item["line"], 3)
        self.assertEqual(item["column"], 30)
        self.assertEqual(item["endLine"], 3)
        self.assertEqual(item["endColumn"], 32)
        self.assertEqual(len(item["notes"]), 2)
        self.assertEqual(item["helps"], ["remove the 'zz' entry"])
        self.assertEqual(item["file"], "main.x")

    def test_plain_error_payload_defaults_to_empty_follow_ups(self):
        item = _diagnostic("typecheck", TypeCheckError("boom", line=1, column=1))
        self.assertEqual(item["notes"], [])
        self.assertEqual(item["helps"], [])
        self.assertIsNone(item["endLine"])
        self.assertIsNone(item["endColumn"])


if __name__ == "__main__":
    unittest.main()
