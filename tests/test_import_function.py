"""``import B.greet("Maya")`` — importing a function and calling it at once.

Covers the form written in ``examples/import_function/A.x``:

* the target module is imported exactly like ``import B.greet`` and the
  exported function is invoked immediately with the given arguments
* the import stays bound, so the function can still be called by name
* the call runs where the import is written, so statement order is kept
* misuse — wrong arity, non-callable targets, grouped/wildcard imports —
  reports a real error instead of silently doing nothing
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
from xlang.runtime import Interpreter

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

GREETER_MODULE = """
    export string function greet(string name, string greeting = "Hello") {
        print(greeting + ", " + name + "!");
        return greeting + ", " + name + "!";
    }
"""


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def run_modules(entry_source, modules, arguments=None, environment=None):
    """Write *modules* next to *entry_source* and interpret the entry file."""
    with TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        for module_name, module_source in modules.items():
            module_file = project_root / module_name
            module_file.parent.mkdir(parents=True, exist_ok=True)
            module_file.write_text(dedent(module_source), encoding="utf-8")
        entry_file = project_root / "main.x"
        entry_file.write_text(dedent(entry_source), encoding="utf-8")
        program = ModuleLoader(project_root).load_program(entry_file)
        output = []
        result = Interpreter(
            arguments, output.append, environment=environment
        ).interpret(program)
    return result, output


def run_modules_cli(entry_source, modules):
    """Run the entry file through ``x run``; return ``(code, stdout, stderr)``."""
    output = io.StringIO()
    errors = io.StringIO()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        for module_name, module_source in modules.items():
            module_file = project_root / module_name
            module_file.parent.mkdir(parents=True, exist_ok=True)
            module_file.write_text(dedent(module_source), encoding="utf-8")
        entry_file = project_root / "main.x"
        entry_file.write_text(dedent(entry_source), encoding="utf-8")
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["run", "--no-config", "--color", "never", str(entry_file)]
            )
    return return_code, output.getvalue(), errors.getvalue()


def check_modules_cli(entry_source, modules):
    """Run ``x check`` over the entry file; return ``(code, stdout, stderr)``."""
    output = io.StringIO()
    errors = io.StringIO()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        for module_name, module_source in modules.items():
            module_file = project_root / module_name
            module_file.parent.mkdir(parents=True, exist_ok=True)
            module_file.write_text(dedent(module_source), encoding="utf-8")
        entry_file = project_root / "main.x"
        entry_file.write_text(dedent(entry_source), encoding="utf-8")
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["check", "--no-config", "--color", "never", str(entry_file)]
            )
    return return_code, output.getvalue(), errors.getvalue()


def caret_lines(rendered: str) -> list[str]:
    return [
        line.split("|", 1)[-1]
        for line in rendered.splitlines()
        if "|" in line and "^" in line.split("|", 1)[-1]
    ]


class ImportCallTests(unittest.TestCase):
    def test_import_and_call_in_one_statement(self):
        _, output = run_modules(
            'import B.greet("Maya");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(output, ["Hello, Maya!"])

    def test_import_call_passes_extra_arguments(self):
        _, output = run_modules(
            'import B.greet("Maya", "Hi");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(output, ["Hi, Maya!"])

    def test_import_call_leaves_the_target_bound(self):
        _, output = run_modules(
            'import B.greet("Maya");\n'
            'greet("Bob");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(output, ["Hello, Maya!", "Hello, Bob!"])

    def test_import_call_with_an_alias(self):
        _, output = run_modules(
            'import B.greet as hello("Maya");\n'
            'hello("Bob");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(output, ["Hello, Maya!", "Hello, Bob!"])

    def test_import_call_runs_where_the_import_is_written(self):
        _, output = run_modules(
            'print("before");\n'
            'import B.greet("Maya");\n'
            'print("after");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(output, ["before", "Hello, Maya!", "after"])

    def test_import_call_counts_as_a_top_level_statement(self):
        _, output = run_modules(
            'import B.greet("Maya");\n'
            "function main() {\n"
            '    print("main");\n'
            "}\n",
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(output, ["Hello, Maya!"])

    def test_plain_import_still_auto_calls_main(self):
        _, output = run_modules(
            "import B\n"
            "function main() {\n"
            '    print("main");\n'
            "}\n",
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(output, ["main"])

    def test_import_call_inside_an_imported_module(self):
        _, output = run_modules(
            "import C.hi;\n",
            {
                "B.x": GREETER_MODULE,
                "C.x": 'import B.greet("FromC");\n'
                "export function hi() {\n"
                '    print("hi");\n'
                "}\n",
            },
        )
        self.assertEqual(output, ["Hello, FromC!"])


class ImportCallErrorTests(unittest.TestCase):
    def test_wrong_arity_reports_an_error_at_the_import(self):
        return_code, _, errors = run_modules_cli(
            "import B.greet();\n",
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn(
            "No overload of 'greet' accepts 0 argument(s)", errors
        )
        self.assertIn("| import B.greet();", errors)
        self.assertTrue(any("^" in line for line in caret_lines(errors)))

    def test_undefined_argument_is_reported_with_its_span(self):
        return_code, _, errors = run_modules_cli(
            "import B.greet(unknownVar);\n",
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Name 'unknownVar' is not defined", errors)
        self.assertIn("^^^^^^^^^^", errors)

    def test_non_callable_target_is_rejected(self):
        return_code, _, errors = run_modules_cli(
            'import E.Color("red");\n',
            {"E.x": "export enum Color { RED, GREEN }\n"},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Value is not callable", errors)

    def test_exception_from_the_called_function_reports_the_throw_site(self):
        return_code, _, errors = run_modules_cli(
            "import B.boom();\n",
            {"B.x": 'export function boom() {\n'
            '    throw new Error("boom");\n'
            "}\n"},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Uncaught Error: boom", errors)
        self.assertIn("throw new Error", errors)
        self.assertIn(".x:2:5", errors)

    def test_grouped_import_cannot_be_called(self):
        return_code, _, errors = run_modules_cli(
            'import B.{greet}("Maya");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn(
            "Grouped imports cannot be called; import the names first, "
            "then call them",
            errors,
        )

    def test_wildcard_import_cannot_be_called(self):
        return_code, _, errors = run_modules_cli(
            'import B.*("Maya");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn(
            "A wildcard import cannot be called; import the name directly, "
            "then call it",
            errors,
        )

    def test_import_call_cannot_be_used_as_an_expression(self):
        return_code, _, errors = run_modules_cli(
            'print(import B.greet("Maya"));\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Unexpected token 'import'", errors)

    def test_result_of_an_import_call_cannot_be_chained(self):
        return_code, _, errors = run_modules_cli(
            'import B.greet("Maya").toUpperCase();\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Unexpected token '.'", errors)


class ImportCallCheckerTests(unittest.TestCase):
    def test_check_accepts_import_calls(self):
        return_code, output, errors = check_modules_cli(
            'import B.greet("Maya");\n',
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("syntax is valid", output)
        self.assertIn("types are valid", output)

    def test_check_reports_type_errors_inside_import_call_arguments(self):
        return_code, _, errors = check_modules_cli(
            "import B.greet(true);\n",
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn(
            "Argument 1 of 'greet' has type 'boolean', expected 'string'",
            errors,
        )
        self.assertTrue(any("^" in line for line in caret_lines(errors)))

    def test_check_leaves_undefined_names_to_runtime(self):
        return_code, output, errors = check_modules_cli(
            "import B.greet(undefinedName);\n",
            {"B.x": GREETER_MODULE},
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)


class ImportCallExampleTests(unittest.TestCase):
    def test_repository_example_import_function(self):
        example_file = (
            REPOSITORY_ROOT / "examples" / "import_function" / "A.x"
        )
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["run", "--no-config", "--color", "never", str(example_file)]
            )
        self.assertEqual(return_code, 0, errors.getvalue())
        # The example file is the playground for this feature; assert the
        # import-call runs, not the exact set of lines around it.
        self.assertIn("Hello, Maya!", output.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
