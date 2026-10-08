"""Importable exception paths, inline qualified catch clauses, JSON.toJSON.

Covers:

* ``import System.Throwable.Exception.IOException.HttpException`` binds the
  short name for both ``throw`` and a short ``catch``
* catch clauses written inline with the full hierarchy path
* intermediate imports keep their constructors usable
* feature ``exceptions`` gates the ``System.Throwable`` tree
* every hierarchy node has a loader path and a type-checker name
* ``System.utils.JSON.toJSON`` mirrors ``JSON.stringify`` (compact, indented,
  escaping, omitted functions, circular detection, indent validation)
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.cli import main as cli_main
from xlang.config import FEATURE_DEFAULTS, XConfig
from xlang.interpreter import Interpreter
from xlang.module_loader import ModuleLoader
from xlang.runtime import (
    EXCEPTION_PARENTS,
    RuntimeErrorX,
    ThrownValue,
    qualified_exception_paths,
)
from xlang.typecheck.types import BUILTIN_TYPE_NAMES


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def run_x(source: str, config: XConfig | None = None) -> list[str]:
    """Run *source* and return the printed lines."""
    config = config or XConfig()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        entry = project_root / "main.x"
        entry.write_text(dedent(source), encoding="utf-8")
        loader = ModuleLoader(project_root, config=config)
        program = loader.load_program(entry)
        output: list[str] = []
        Interpreter(config=config, output=output.append).interpret(program)
        return output


def run_x_error(source: str, config: XConfig | None = None):
    """Run *source* and return the raised (ThrownValue | RuntimeErrorX)."""
    config = config or XConfig()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        entry = project_root / "main.x"
        entry.write_text(dedent(source), encoding="utf-8")
        loader = ModuleLoader(project_root, config=config)
        program = loader.load_program(entry)
        try:
            Interpreter(
                config=config, output=lambda text: None
            ).interpret(program)
        except (ThrownValue, RuntimeErrorX) as error:
            return error
    raise AssertionError("expected the program to raise, but it completed")


def check_source(source: str) -> tuple[int, str, str]:
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


FULL_PATH = "System.Throwable.Exception.IOException.HttpException"


class QualifiedCatchTests(unittest.TestCase):
    def test_inline_full_path_catches_imported_exception(self):
        output = run_x(
            f"""
            import System.Throwable.Exception.IOException.HttpException
            any function main() {{
                try {{
                    throw HttpException("boom");
                }} catch ({FULL_PATH} error) {{
                    print("caught: " + error.message);
                }}
            }}
            """
        )
        self.assertEqual(output, ["caught: boom"])

    def test_full_path_construction_without_import(self):
        output = run_x(
            f"""
            any function main() {{
                try {{
                    throw {FULL_PATH}("no import needed");
                }} catch ({FULL_PATH} error) {{
                    print("caught: " + error.message);
                }}
            }}
            """
        )
        self.assertEqual(output, ["caught: no import needed"])

    def test_qualified_parent_type_catches_subclass(self):
        output = run_x(
            f"""
            any function main() {{
                try {{
                    throw {FULL_PATH}("child");
                }} catch (System.Throwable.Exception.IOException error) {{
                    print("parent caught: " + error.message);
                }}
            }}
            """
        )
        self.assertEqual(output, ["parent caught: child"])

    def test_qualified_root_type_catches_any_exception(self):
        output = run_x(
            f"""
            any function main() {{
                try {{
                    throw {FULL_PATH}("root");
                }} catch (System.Throwable error) {{
                    print("root caught: " + error.message);
                }}
            }}
            """
        )
        self.assertEqual(output, ["root caught: root"])

    def test_leaf_path_does_not_catch_sibling(self):
        error = run_x_error(
            f"""
            any function main() {{
                try {{
                    throw FileSystemException("sibling");
                }} catch ({FULL_PATH} error) {{
                    print("should not catch");
                }}
            }}
            """
        )
        self.assertIsInstance(error, ThrownValue)
        self.assertEqual(error.value.name, "FileSystemException")
        self.assertEqual(error.value.message, "sibling")

    def test_union_of_qualified_and_short_types(self):
        output = run_x(
            f"""
            import System.Throwable.Exception.IOException
            any function main() {{
                try {{
                    throw HttpException("arm one");
                }} catch ({FULL_PATH} | RuntimeException error) {{
                    print("union A: " + error.message);
                }}
                try {{
                    throw IllegalArgumentException("arm two");
                }} catch ({FULL_PATH} | IllegalArgumentException error) {{
                    print("union B: " + error.message);
                }}
            }}
            """
        )
        self.assertEqual(output, ["union A: arm one", "union B: arm two"])

    def test_short_catch_after_leaf_import(self):
        output = run_x(
            """
            import System.Throwable.Exception.IOException.HttpException
            any function main() {
                try {
                    throw HttpException("short");
                } catch (HttpException error) {
                    print("short: " + error.message);
                }
            }
            """
        )
        self.assertEqual(output, ["short: short"])


class ExceptionPathImportTests(unittest.TestCase):
    def test_intermediate_import_keeps_constructor(self):
        output = run_x(
            """
            import System.Throwable.Exception.IOException
            any function main() {
                try {
                    throw IOException("still a constructor");
                } catch (IOException error) {
                    print("caught: " + error.message);
                }
            }
            """
        )
        self.assertEqual(output, ["caught: still a constructor"])

    def test_intermediate_import_leaves_children_reachable(self):
        output = run_x(
            """
            import System.Throwable.Exception.IOException
            any function main() {
                try {
                    throw System.Throwable.Exception.IOException.HttpException("child");
                } catch (System.Throwable.Exception.IOException.HttpException error) {
                    print("child: " + error.message);
                }
            }
            """
        )
        self.assertEqual(output, ["child: child"])

    def test_alias_import_exposes_children(self):
        output = run_x(
            """
            import System.Throwable.Exception as Errors
            any function main() {
                try {
                    throw Errors.IOException.HttpException("aliased");
                } catch (System.Throwable.Exception.IOException.HttpException error) {
                    print("aliased: " + error.message);
                }
            }
            """
        )
        self.assertEqual(output, ["aliased: aliased"])

    def test_import_throwable_root_exposes_full_tree(self):
        output = run_x(
            """
            import System.Throwable as Tr
            any function main() {
                try {
                    throw Tr.Exception.IOException.HttpException("root import");
                } catch (Tr.Exception.IOException.HttpException error) {
                    print("root: " + error.message);
                }
            }
            """
        )
        self.assertEqual(output, ["root: root import"])

    def test_unaliased_throwable_import_keeps_the_base_class(self):
        output = run_x(
            """
            import System.Throwable
            any function main() {
                print(typeOf(Throwable));
                print(typeOf(System.Throwable));
            }
            """
        )
        self.assertEqual(output, ["class", "object"])

    def test_exception_paths_disabled_by_feature(self):
        config = XConfig(features={**FEATURE_DEFAULTS, "exceptions": False})
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x(
                f"""
                import {FULL_PATH}
                any function main() {{
                    print(1);
                }}
                """,
                config=config,
            )
        self.assertIn("feature 'exceptions' is disabled", str(caught.exception))


class QualifiedCatchCheckTests(unittest.TestCase):
    def test_check_accepts_qualified_catch_type(self):
        return_code, out, _ = check_source(
            f"""
            any function main() {{
                try {{
                    throw {FULL_PATH}("x");
                }} catch ({FULL_PATH} error) {{
                    print(error.message);
                }}
            }}
            """
        )
        self.assertEqual(return_code, 0, out)
        self.assertIn("types are valid", out)

    def test_check_rejects_unknown_exception_path(self):
        return_code, _, errors = check_source(
            """
            any function main() {
                try {
                    print(1);
                } catch (System.Throwable.Bogus.HttpException error) {
                    print(error.message);
                }
            }
            """
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Unknown type 'System.Throwable.Bogus.HttpException'", errors)

    def test_check_rejects_misspelled_leaf_in_path(self):
        return_code, _, errors = check_source(
            """
            any function main() {
                try {
                    print(1);
                } catch (System.Throwable.Exception.IOExceptionn error) {
                    print(error.message);
                }
            }
            """
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Unknown type 'System.Throwable.Exception.IOExceptionn'", errors)


class ExceptionPathCompletenessTests(unittest.TestCase):
    def test_every_hierarchy_node_has_loader_and_type_name(self):
        for path in qualified_exception_paths():
            self.assertIn(path, ModuleLoader.STANDARD_LIBRARY_MODULES, path)
            self.assertIn(path, BUILTIN_TYPE_NAMES, path)

    def test_paths_cover_representative_hierarchy_nodes(self):
        paths = set(qualified_exception_paths())
        for expected in (
            "System.Throwable",
            "System.Throwable.Exception",
            "System.Throwable.Exception.IOException",
            "System.Throwable.Exception.IOException.HttpException",
            "System.Throwable.Exception.IOException.FileSystemException",
            "System.Throwable.Error",
            "System.Throwable.Error.DatabaseError",
            "System.Throwable.Exception.RuntimeException.ArithmeticException",
        ):
            self.assertIn(expected, paths)

    def test_paths_exist_for_every_class_in_the_parent_map(self):
        for child in EXCEPTION_PARENTS:
            matching = [p for p in qualified_exception_paths() if p.endswith(child)]
            self.assertTrue(matching, f"no import path for {child}")


class ToJsonTests(unittest.TestCase):
    def test_compact_object_matches_stringify(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON
            any function main() {
                print(toJSON({a: 1, b: "x", c: [true, null]}));
            }
            """
        )
        self.assertEqual(output, ['{"a":1,"b":"x","c":[true,null]}'])

    def test_indent_two_matches_stringify(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON
            any function main() {
                print(toJSON({ok: true, tags: ["http"], nested: {status: 200}}, 2));
            }
            """
        )
        self.assertEqual(
            output,
            [
                "{\n"
                '  "ok": true,\n'
                '  "tags": [\n'
                '    "http"\n'
                "  ],\n"
                '  "nested": {\n'
                '    "status": 200\n'
                "  }\n"
                "}"
            ],
        )

    def test_string_indent_uses_the_literal_per_level(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON
            any function main() {
                print(toJSON({a: {b: 1}}, "  "));
            }
            """
        )
        self.assertEqual(output, ['{\n  "a": {\n    "b": 1\n  }\n}'])

    def test_escapes_quotes_and_control_characters(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON
            any function main() {
                print(toJSON("quoted \\" and \\n newline"));
            }
            """
        )
        self.assertEqual(output, ['"quoted \\" and \\n newline"'])

    def test_scalars(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON
            any function main() {
                print(toJSON(42));
                print(toJSON("plain"));
                print(toJSON(null));
            }
            """
        )
        self.assertEqual(output, ["42", '"plain"', "null"])

    def test_function_values_are_omitted_from_objects(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON
            any function someFunc() { return 1; }
            any function main() {
                print(toJSON({f: someFunc, n: 1}));
            }
            """
        )
        self.assertEqual(output, ['{"n":1}'])

    def test_class_instance_serializes_its_fields(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON
            class Point {
                int x;
                public Point(int x) { this.x = x; }
            }
            any function main() {
                print(toJSON(new Point(5)));
            }
            """
        )
        self.assertEqual(output, ['{"x":5}'])

    def test_circular_structure_raises(self):
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x(
                """
                import System.utils.JSON.toJSON
                any function main() {
                    let cycle = {name: "x"};
                    cycle.self = cycle;
                    print(toJSON(cycle));
                }
                """
            )
        self.assertIn("Converting circular structure to JSON", str(caught.exception))

    def test_negative_indent_rejected(self):
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x(
                """
                import System.utils.JSON.toJSON
                any function main() {
                    print(toJSON({a: 1}, -1));
                }
                """
            )
        self.assertIn("indent cannot be negative", str(caught.exception))

    def test_boolean_indent_rejected(self):
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x(
                """
                import System.utils.JSON.toJSON
                any function main() {
                    print(toJSON({a: 1}, true));
                }
                """
            )
        self.assertIn("indent must be a number of spaces or a string", str(caught.exception))

    def test_wrong_arity_rejected(self):
        with self.assertRaises(RuntimeErrorX) as caught:
            run_x(
                """
                import System.utils.JSON.toJSON
                any function main() {
                    print(toJSON());
                }
                """
            )
        self.assertIn("toJSON(value, indent?)", str(caught.exception))

    def test_json_namespace_import(self):
        output = run_x(
            """
            import System.utils.JSON
            any function main() {
                print(JSON.toJSON({n: 1}));
            }
            """
        )
        self.assertEqual(output, ['{"n":1}'])

    def test_tojson_import_alias(self):
        output = run_x(
            """
            import System.utils.JSON.toJSON as jstr
            any function main() {
                print(jstr([1, 2]));
            }
            """
        )
        self.assertEqual(output, ["[1,2]"])

    def test_json_paths_are_registered(self):
        self.assertIn("System.utils.JSON", ModuleLoader.STANDARD_LIBRARY_MODULES)
        self.assertIn(
            "System.utils.JSON.toJSON", ModuleLoader.STANDARD_LIBRARY_MODULES
        )


if __name__ == "__main__":
    unittest.main()
