"""``x lint``: the undeclared-variables rule, its scope rules, and x.toml.

The lint reuses the type checker's scope machinery, so these tests pin down
the contract that keeps it from crying wolf: runtime-provided names
(builtins, feature globals, default-import aliases), names the loader's
visibility map grants (own declarations in any order, imports, namespace
members), and the pattern-introduced bindings (catch, destructuring, match,
nested enums) all resolve; a name nothing declares is reported with the
runtime's wording and tagged ``lint error``.
"""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from xlang.cli import main

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


class LintCliTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def lint_source(self, source, *extra_arguments):
        """Write ``source`` to a temp ``main.x`` and run ``x lint`` on it."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            return self.run_cli(
                ["lint", "--no-config", "--color", "never", *extra_arguments,
                 str(source_file)]
            )

    def check_source(self, source, *extra_arguments):
        """Write ``source`` to a temp ``main.x`` and run ``x check`` on it."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(dedent(source), encoding="utf-8")
            return self.run_cli(
                ["check", "--no-config", "--color", "never", *extra_arguments,
                 str(source_file)]
            )

    def lint_project(self, files, entry, *extra_arguments):
        """Write a multi-file project and lint ``entry`` from it."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            for name, source in files.items():
                module_file = project / name
                module_file.parent.mkdir(parents=True, exist_ok=True)
                module_file.write_text(dedent(source), encoding="utf-8")
            return self.run_cli(
                ["lint", "--no-config", "--color", "never", *extra_arguments,
                 str(project / entry)]
            )

    def test_reports_undeclared_name_in_let_initializer(self):
        return_code, output, errors = self.lint_source(
            """
            let total = missingValue + 1;
            """
        )
        self.assertEqual(return_code, 1, output)
        self.assertEqual(output, "")
        self.assertIn("Name 'missingValue' is not defined", errors)
        self.assertIn("found 1 lint error(s)", errors)

    def test_reports_each_undeclared_use_with_its_location(self):
        return_code, output, errors = self.lint_source(
            """
            function main() {
                print(missingThing);
                missingFunction();
            }
            """
        )
        self.assertEqual(return_code, 1, output)
        self.assertIn("Name 'missingThing' is not defined", errors)
        self.assertIn("Name 'missingFunction' is not defined", errors)
        self.assertIn("found 2 lint error(s)", errors)
        self.assertIn("main.x:2:", errors)
        self.assertIn("main.x:3:", errors)

    def test_check_command_stays_unaffected_by_the_rule(self):
        return_code, output, errors = self.check_source(
            """
            function main() {
                print(missingThing);
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)
        self.assertNotIn("is not defined", output + errors)

    def test_builtins_recursion_and_this_are_clean(self):
        return_code, output, errors = self.lint_source(
            """
            function factorial(integer n) {
                if (n <= 1) {
                    return 1;
                }
                return n * factorial(n - 1);
            }

            function main() {
                let integers = range(3);
                print(typeOf(factorial(5)), integers.length, parseInt("7"));
                print(args.length);
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("no lint issues", output)

    def test_feature_globals_resolve_while_the_feature_is_enabled(self):
        return_code, output, errors = self.lint_source(
            """
            function main() {
                let line = input("> ");
                print(line);
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("no lint issues", output)

    def test_feature_global_reports_the_runtime_wording_when_disabled(self):
        return_code, output, errors = self.lint_source(
            """
            function main() {
                print(input("> "));
            }
            """,
            "--feature", "command_input=off",
        )
        self.assertEqual(return_code, 1, output)
        self.assertIn(
            "Name 'input' is not defined because the "
            "'command_input' feature is disabled in x.toml",
            errors,
        )
        self.assertIn("found 1 lint error(s)", errors)

    def test_pattern_bindings_declare_their_names(self):
        return_code, output, errors = self.lint_source(
            """
            function main() {
                try {
                    throw new Exception("boom");
                } catch (error) {
                    print(error.message);
                }
                try {
                    throw new Exception("typed");
                } catch (Exception failure) {
                    print(failure.message);
                }
                let {first, second} = {first: 1, second: 2};
                let [left, right] = [3, 4];
                print(first + second + left + right);
                match (200) {
                    [code, ...details] if code == 200 => "ok",
                    _ => "other"
                };
                enum Status { OK, BAD }
                print(Status.OK);
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("no lint issues", output)

    def test_namespace_member_used_before_its_declaration_is_clean(self):
        return_code, output, errors = self.lint_source(
            """
            export namespace Demo {
                function show() {
                    print(later);
                }

                let later = 42;
            }
            """
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("no lint issues", output)

    def test_default_import_aliases_are_available(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            config_file = project / "x.toml"
            config_file.write_text(
                '[imports]\ndefault = ["System.utils.Math"]\n',
                encoding="utf-8",
            )
            source_file = project / "main.x"
            source_file.write_text(
                "print(Math.max(3, 10));\n", encoding="utf-8"
            )
            return_code, output, errors = self.run_cli(
                ["lint", "--config", str(config_file), "--color", "never",
                 str(source_file)]
            )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("no lint issues", output)

    def test_unimported_sibling_name_suggests_the_import(self):
        # A member import binds only the name it names: `helper` stays
        # invisible here, and the finding carries the import line that
        # would fix the file.
        return_code, output, errors = self.lint_project(
            {
                "main.x": """
                    import util.greeting;

                    function main() {
                        print(helper());
                    }
                    """,
                "util.x": """
                    export string function greeting() {
                        return "hi";
                    }

                    export string function helper() {
                        return "there";
                    }
                    """,
            },
            "main.x",
        )
        self.assertEqual(return_code, 1, output)
        self.assertIn("Name 'helper' is not defined in this module", errors)
        self.assertIn("add `import util.helper`", errors)

    def test_rule_disabled_through_x_toml_is_clean(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            config_file = project / "x.toml"
            config_file.write_text(
                "[lint]\nundeclared-variables = false\n", encoding="utf-8"
            )
            source_file = project / "main.x"
            source_file.write_text(
                "print(missingThing);\n", encoding="utf-8"
            )
            return_code, output, errors = self.run_cli(
                ["lint", "--config", str(config_file), "--color", "never",
                 str(source_file)]
            )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("no lint issues", output)

    def test_unknown_lint_rule_is_a_config_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            config_file = project / "x.toml"
            config_file.write_text(
                "[lint]\nno-such-rule = true\n", encoding="utf-8"
            )
            source_file = project / "main.x"
            source_file.write_text("print(1);\n", encoding="utf-8")
            return_code, output, errors = self.run_cli(
                ["lint", "--config", str(config_file), "--color", "never",
                 str(source_file)]
            )
        self.assertNotEqual(return_code, 0)
        self.assertIn(
            "Unknown lint rule 'no-such-rule'. Available rules: "
            "undeclared-variables",
            errors,
        )

    def test_non_boolean_lint_rule_value_is_a_config_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            config_file = project / "x.toml"
            config_file.write_text(
                '[lint]\nundeclared-variables = "yes"\n', encoding="utf-8"
            )
            source_file = project / "main.x"
            source_file.write_text("print(1);\n", encoding="utf-8")
            return_code, output, errors = self.run_cli(
                ["lint", "--config", str(config_file), "--color", "never",
                 str(source_file)]
            )
        self.assertNotEqual(return_code, 0)
        self.assertIn(
            "Lint rule 'undeclared-variables' must be true or false", errors
        )


class LintExamplesTests(unittest.TestCase):
    """The acceptance gate: published examples lint clean end to end."""

    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def lint_example(self, relative_path):
        source_file = REPOSITORY_ROOT / relative_path
        return self.run_cli(
            ["lint", "--config", str(REPOSITORY_ROOT / "x.toml"),
             "--color", "never", str(source_file)]
        )

    def test_representative_examples_lint_clean(self):
        # These exercised every false positive the rule had: namespace
        # forward references, untyped/typed catch bindings, destructuring,
        # match patterns, nested enums, wildcard/aliased imports, and the
        # default-import aliases.
        examples = (
            "examples/namespace_demo/main.x",
            "examples/namespace_demo/util.x",
            "examples/imports_demo/util.x",
            "examples/import_export/simple/main.x",
            "examples/control_flow/main.x",
            "examples/demo_default_imports.x",
        )
        for example in examples:
            with self.subTest(example=example):
                return_code, output, errors = self.lint_example(example)
                self.assertEqual(return_code, 0, f"{example}: {errors}")

    def test_parse_error_example_fails_without_a_lint_finding(self):
        # A file the loader rejects cannot be linted; the failure must come
        # from the loader, not be relabelled a lint finding.
        return_code, output, errors = self.lint_example(
            "examples/test/test_missing_let.x"
        )
        self.assertEqual(return_code, 1, output)
        self.assertIn("must start with 'let'", errors)
        self.assertNotIn("lint error", errors)


if __name__ == "__main__":
    unittest.main()
