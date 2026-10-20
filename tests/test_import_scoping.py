"""Per-file import visibility.

A member import binds only the declaration it names: ``import util.Gender``
gives you ``Gender`` — not util's whole scope (the old flatten leaked every
sibling declaration into every importer).  Whole-module and wildcard imports
keep exposing everything they flatten, enum/interface names are types (not
values), and type aliases have no members.  Errors suggest the exact
import line that would fix the file.
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

UTIL_MODULE = """
    export enum Gender {
      MALE = "Male",
      FEMALE = "Female",
    }

    export type Participants = Object<integer, string>

    export interface Marker {
      string label,
    }

    export string function greet() {
      return "hi"
    }
"""


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def _write_project(entry_source: str, modules: dict[str, str]) -> Path:
    """Materialise entry + modules under a temp dir; return the entry path."""
    directory = tempfile.mkdtemp()
    project_root = Path(directory)
    for module_name, module_source in modules.items():
        module_file = project_root / module_name
        module_file.parent.mkdir(parents=True, exist_ok=True)
        module_file.write_text(dedent(module_source), encoding="utf-8")
    entry_file = project_root / "main.x"
    entry_file.write_text(dedent(entry_source), encoding="utf-8")
    return entry_file


def check_modules(entry_source: str, modules: dict[str, str] | None = None):
    """``x check`` the entry file; return ``(code, combined_output)``."""
    entry_file = _write_project(entry_source, modules or {"util.x": UTIL_MODULE})
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        return_code = cli_main(
            ["check", "--no-config", "--color", "never", str(entry_file)]
        )
    return return_code, output.getvalue() + errors.getvalue()


def run_modules(entry_source: str, modules: dict[str, str] | None = None):
    """``x run`` the entry file; return ``(code, combined_output)``."""
    entry_file = _write_project(entry_source, modules or {"util.x": UTIL_MODULE})
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        return_code = cli_main(
            ["run", "--no-config", "--color", "never", str(entry_file)]
        )
    return return_code, output.getvalue() + errors.getvalue()


def run_modules_raw(entry_source: str, modules: dict[str, str] | None = None):
    """Interpret directly (no type checker); return ``(output_lines)``."""
    entry_file = _write_project(entry_source, modules or {"util.x": UTIL_MODULE})
    program = ModuleLoader(entry_file.parent).load_program(entry_file)
    output: list[str] = []
    Interpreter([], output.append, validate=False).interpret(program)
    return output


class ImportVisibilityCheckTests(unittest.TestCase):
    def test_member_import_binds_only_the_named_declaration(self):
        code, output = check_modules(
            """
            import util.Gender

            print(greet())
            """
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "Name 'greet' is not defined in this module", output
        )
        self.assertIn("help: add `import util.greet`", output)

    def test_member_import_of_a_single_declaration_is_clean(self):
        code, output = check_modules(
            """
            import util.Gender

            let g = Gender.MALE
            print(g)
            """
        )
        self.assertEqual(code, 0, output)
        self.assertIn("types are valid", output)

    def test_member_import_exposes_the_named_type(self):
        code, output = check_modules(
            """
            import util.Participants

            let p: Participants = { 1: "a" }
            print(p)
            """
        )
        self.assertEqual(code, 0, output)

    def test_sibling_type_stays_hidden_without_an_import(self):
        code, output = check_modules(
            """
            import util.Gender

            let p: Participants = { 1: "a" }
            print(p)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "Type 'Participants' is not defined in this module", output
        )
        self.assertIn("help: add `import util.Participants`", output)

    def test_whole_module_import_keeps_the_module_visible(self):
        code, output = check_modules(
            """
            import util

            let p: Participants = { 1: "a" }
            print(Gender.MALE, greet(), p)
            """
        )
        self.assertEqual(code, 0, output)

    def test_member_alias_binds_the_alias(self):
        code, output = check_modules(
            """
            import util.Gender as G

            print(G.MALE)
            """
        )
        self.assertEqual(code, 0, output)

    def test_grouped_import_binds_the_named_members(self):
        code, output = check_modules(
            """
            import util.{Gender, greet}

            print(Gender.FEMALE, greet())
            """
        )
        self.assertEqual(code, 0, output)

    def test_wildcard_import_exposes_the_exports(self):
        code, output = check_modules(
            """
            import util.*

            print(Gender.MALE, greet())
            """
        )
        self.assertEqual(code, 0, output)


class TypeAsValueCheckTests(unittest.TestCase):
    def test_enum_as_a_value_is_rejected(self):
        code, output = check_modules(
            """
            import util.Gender

            print(Gender)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn("Enum 'Gender' is a type, not a value", output)

    def test_interface_as_a_value_is_rejected(self):
        code, output = check_modules(
            """
            import util.Marker

            print(Marker)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn("Interface 'Marker' is a type, not a value", output)

    def test_typeof_accepts_type_names(self):
        code, output = check_modules(
            """
            import util.Gender
            import util.Marker

            print(typeOf(Gender), typeOf(Marker))
            """
        )
        self.assertEqual(code, 0, output)

    def test_interface_construction_reports_only_the_construct_error(self):
        code, output = check_modules(
            """
            import util.Marker

            let m = Marker("x")
            print(m)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn("Cannot construct interface 'Marker'", output)
        self.assertNotIn("is a type, not a value", output)

    def test_alias_member_access_is_rejected_with_an_import_suggestion(self):
        code, output = check_modules(
            """
            import util.Participants

            print(Participants.Gender.MALE)
            """
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "Type alias 'Participants' has no member 'Gender'", output
        )
        self.assertIn("help: add `import util.Gender`", output)


class ImportVisibilityRunTests(unittest.TestCase):
    def test_member_import_program_runs(self):
        code, output = run_modules(
            """
            import util.Gender

            print(Gender.MALE)
            """
        )
        self.assertEqual(code, 0, output)
        self.assertIn("MALE", output)

    def test_hidden_sibling_use_fails_the_run(self):
        code, output = run_modules(
            """
            import util.Gender

            print(greet())
            """
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "Name 'greet' is not defined in this module", output
        )

    def test_whole_module_program_runs(self):
        code, output = run_modules(
            """
            import util

            print(Gender.FEMALE, greet())
            """
        )
        self.assertEqual(code, 0, output)
        self.assertIn("FEMALE", output)
        self.assertIn("hi", output)


class NamespaceStringifyTests(unittest.TestCase):
    """``print`` never leaks a Python Environment repr (checker bypassed)."""

    def test_enum_prints_as_an_enum_label(self):
        output = run_modules_raw(
            """
            import util.Gender

            print(Gender)
            """
        )
        self.assertEqual(output, ["[enum Gender]"])

    def test_module_namespace_prints_as_a_namespace_label(self):
        output = run_modules_raw(
            """
            import util

            print(util)
            """
        )
        self.assertEqual(output, ["[namespace util]"])


if __name__ == "__main__":
    unittest.main()
