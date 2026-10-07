import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xlang.cli import main
from xlang.config import ConfigError, discover_config, load_config


class CommandLineTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def test_cli_reports_multiple_lexical_and_syntax_errors(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                """function main() {
    print(1 + );
    print($ + );
    let broken = ;
}
""",
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                ["check", "--no-config", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertIn("Unexpected token ';'; expected an expression", errors)
        self.assertIn("Unexpected character '$'", errors)
        self.assertIn("Unexpected token ')'; expected an expression", errors)
        self.assertIn("found 4 error(s)", errors)

    def test_cli_reports_unclosed_block_at_end_of_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                "function main() {\n    print(1);\n",
                encoding="utf-8",
            )

            return_code, _, errors = self.run_cli(
                ["check", "--no-config", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertIn(
            "Unexpected end of file; expected '}' to close block",
            errors,
        )
        self.assertIn(f"{source_file}:3:", errors)
        self.assertIn("found 1 error(s)", errors)

    def test_toml_run_profile_provides_arguments_and_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            config_path = project_root / "project.toml"
            config_path.write_text(
                """
                [run]
                args = ["configured argument", "two"]
                [run.environment]
                X_MODE = "base"
                [run.profiles.demo]
                args = ["profile value"]
                [run.profiles.demo.environment]
                X_MODE = "profile"
                [cli]
                color = "never"
                """,
                encoding="utf-8",
            )
            source_file = project_root / "main.x"
            source_file.write_text(
                """
                function main(string[] args) {
                    print(args.length)
                    print(args[0])
                    print(args[2])
                    print(args[3])
                    print(System.Environment.X_MODE)
                }
                """,
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                [
                    "run",
                    "--config",
                    str(config_path),
                    "--profile",
                    "demo",
                    str(source_file),
                    "--",
                    "cli argument",
                ]
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(
            output.splitlines(),
            ["4", "configured argument", "profile value", "cli argument", "profile"],
        )
        self.assertEqual(errors, "")

    def test_env_file_is_exposed_through_system_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / ".env").write_text(
                """
                # Local demo configuration
                export X_ENV_DEMO_NAME=X Language
                X_ENV_DEMO_MODE="development mode"
                X_ENV_DEMO_PORT=4312 # local server port
                X_ENV_DEMO_OVERRIDE=from-dotenv
                """,
                encoding="utf-8",
            )
            source_file = project_root / "main.x"
            source_file.write_text(
                """
                function main() {
                    print(System.Environment.X_ENV_DEMO_NAME)
                    print(System.Environment.X_ENV_DEMO_MODE)
                    print(System.Environment.X_ENV_DEMO_PORT)
                    print(System.Environment.X_ENV_DEMO_OVERRIDE)
                    print(System.Environment.has("X_ENV_DEMO_PORT"))
                }
                """,
                encoding="utf-8",
            )

            with patch.dict(
                os.environ, {"X_ENV_DEMO_OVERRIDE": "from-process"}
            ):
                return_code, output, errors = self.run_cli(
                    ["run", "--no-config", str(source_file)]
                )

        self.assertEqual(return_code, 0)
        self.assertEqual(
            output.splitlines(),
            [
                "X Language",
                "development mode",
                "4312",
                "from-process",
                "true",
            ],
        )
        self.assertEqual(errors, "")

    def test_invalid_env_file_reports_its_path_and_line(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / ".env").write_text(
                "X_VALID=value\nnot-an-assignment\n",
                encoding="utf-8",
            )
            source_file = project_root / "main.x"
            source_file.write_text("function main() {}\n", encoding="utf-8")

            return_code, output, errors = self.run_cli(
                ["run", "--no-config", str(source_file)]
            )

        self.assertEqual(return_code, 2)
        self.assertIn(".env:2:1", errors)
        self.assertIn("KEY=VALUE", errors)
        self.assertEqual(output, "")

    def test_configuration_example_runs_with_the_env_example(self):
        repository_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / ".env").write_text(
                (repository_root / ".env.example").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            config_path = project_root / "x.toml"
            config_path.write_text(
                (repository_root / "x.toml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            source_file = project_root / "configured_args.x"
            source_file.write_text(
                (
                    repository_root
                    / "examples"
                    / "configuration"
                    / "configured_args.x"
                ).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                ["run", "--config", str(config_path), str(source_file)]
            )
            profile_code, profile_output, profile_errors = self.run_cli(
                [
                    "run",
                    "--config",
                    str(config_path),
                    "--profile",
                    "feature-tour",
                    str(source_file),
                ]
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(
            output.splitlines(),
            [
                "Argument count: 0",
                "Configured project: x-language",
                "Selected mode: local-development",
                "Service name: X Language Demo",
                "API base URL: http://localhost:8080",
                "Has service name: true",
            ],
        )
        self.assertEqual(errors, "")
        self.assertEqual(profile_code, 0)
        self.assertIn("Configured project: x-language", profile_output)
        self.assertIn("Selected mode: feature-tour", profile_output)
        self.assertEqual(profile_errors, "")

    def test_cli_feature_override_reenables_a_toml_disabled_feature(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            config_path = project_root / "x.toml"
            config_path.write_text(
                "[features]\nobject_literals = false\n",
                encoding="utf-8",
            )
            source_file = project_root / "object.x"
            source_file.write_text(
                "function main() { let value = {answer: 42}; }\n",
                encoding="utf-8",
            )

            failed_code, _, failure = self.run_cli(
                ["check", "--config", str(config_path), str(source_file)]
            )
            passed_code, passed_output, passed_error = self.run_cli(
                [
                    "--config",
                    str(config_path),
                    "--feature",
                    "object-literals=on",
                    "check",
                    str(source_file),
                ]
            )

        self.assertEqual(failed_code, 1)
        self.assertIn("feature 'object_literals' is disabled", failure)
        self.assertIn(f"{source_file}:1:", failure)
        self.assertEqual(passed_code, 0)
        self.assertIn("syntax is valid", passed_output)
        self.assertEqual(passed_error, "")

    def test_runtime_diagnostic_shows_source_line_and_location(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "broken.x"
            source_file.write_text(
                "function main() {\n    let integer result = 4 / 0;\n}\n",
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                ["run", "--no-config", "--color", "never", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertIn(f"{source_file}:2:", errors)
        self.assertIn("let integer result = 4 / 0;", errors)
        self.assertIn("^", errors)
        self.assertNotIn("\x1b[", errors)

    def test_uncaught_exception_diagnostic_includes_exception_type(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "broken.x"
            source_file.write_text(
                'function main() { throw new ArithmeticException("divide by zero"); }\n',
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                ["run", "--no-config", "--color", "never", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertIn("Uncaught ArithmeticException: divide by zero", errors)
        self.assertIn(f"{source_file}:1:", errors)

    def test_uncaught_custom_exception_shows_its_class_name_and_message(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "broken.x"
            source_file.write_text(
                """
                class BadRequestException extends Exception {}
                function main() {
                    throw new BadRequestException("invalid user id");
                }
                """,
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                ["run", "--no-config", "--color", "never", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertIn("Uncaught BadRequestException: invalid user id", errors)
        self.assertIn(f"{source_file}:4:", errors)

    def test_uncaught_arithmetic_failure_diagnostic_includes_exception_type(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "broken.x"
            source_file.write_text(
                "function main() { let int zero = 0; let float result = 1 / zero; }\n",
                encoding="utf-8",
            )
            return_code, output, errors = self.run_cli(
                ["run", "--no-config", "--color", "never", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(output, "")
        self.assertIn(
            "Cannot divide by zero: Division by zero for '/'",
            errors,
        )
        self.assertIn(f"{source_file}:1:", errors)

    def test_error_diagnostic_color_can_be_forced(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "broken.x"
            source_file.write_text("function main() { let = ; }\n", encoding="utf-8")
            return_code, _, errors = self.run_cli(
                ["check", "--no-config", "--color", "always", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertIn("\x1b[", errors)
        self.assertIn("\x1b[31m", errors)
        self.assertIn("-->", errors)

    def test_importing_module_that_calls_main_warns_about_duplicate_call(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_file = project_root / "main.x"
            module_file.write_text(
                """
                export function main() {
                    print("called");
                }
                main()
                """,
                encoding="utf-8",
            )
            entry_file = project_root / "runner.x"
            entry_file.write_text(
                """
                import main
                main()
                """,
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                [
                    "run",
                    "--no-config",
                    "--color",
                    "never",
                    str(entry_file),
                ]
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(output.splitlines(), ["called", "called"])
        self.assertIn("warning:", errors)
        self.assertIn("already calls main() during import", errors)
        self.assertIn(str(entry_file), errors)

    def test_each_explicit_main_call_is_warned_when_imported_module_runs_main(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_file = project_root / "main.x"
            module_file.write_text(
                'export function main() { print("called"); }\nmain()\n',
                encoding="utf-8",
            )
            entry_file = project_root / "runner.x"
            entry_file.write_text(
                "import main\nmain()\nmain()\n",
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                [
                    "run",
                    "--no-config",
                    "--color",
                    "never",
                    str(entry_file),
                ]
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(output.splitlines(), ["called", "called", "called"])
        self.assertEqual(errors.count("warning:"), 2)
        self.assertIn("runner.x:2:1", errors)
        self.assertIn("runner.x:3:1", errors)

    def test_named_and_wildcard_imports_select_exports_from_one_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_file = project_root / "greeting.x"
            module_file.write_text(
                """
                export function sayGreet() {
                    return "greet";
                }
                export function sayHello() {
                    print("hello");
                }
                function privateHelper() {
                    return "private";
                }
                """,
                encoding="utf-8",
            )
            entry_file = project_root / "main.x"
            entry_file.write_text(
                """
                import greeting.sayGreet
                import greeting.sayHello
                import greeting.*
                import greeting.* as Greet

                function main() {
                    print(sayGreet());
                    sayHello();
                    print(Greet.sayGreet());
                    Greet.sayHello();
                }
                main()
                """,
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                [
                    "run",
                    "--no-config",
                    "--color",
                    "never",
                    str(entry_file),
                ]
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(output.splitlines(), ["greet", "hello", "greet", "hello"])
        self.assertEqual(errors, "")

    def test_unaliased_wildcard_import_exposes_all_exports(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "greeting.x").write_text(
                """
                export function sayGreet() {
                    return "greet";
                }
                export function sayHello() {
                    print("hello");
                }
                """,
                encoding="utf-8",
            )
            entry_file = project_root / "main.x"
            entry_file.write_text(
                """
                import greeting.*
                function main() {
                    print(sayGreet());
                    sayHello();
                }
                main()
                """,
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                [
                    "run",
                    "--no-config",
                    "--color",
                    "never",
                    str(entry_file),
                ]
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(output.splitlines(), ["greet", "hello"])
        self.assertEqual(errors, "")

    def test_main_followed_by_line_comment_warns_that_it_is_not_a_call(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_file = project_root / "main.x"
            module_file.write_text(
                """
                export function main() {
                    print("called");
                }
                main//()
                """,
                encoding="utf-8",
            )
            entry_file = project_root / "runner.x"
            entry_file.write_text(
                "import main\nmain()\n",
                encoding="utf-8",
            )

            return_code, output, errors = self.run_cli(
                [
                    "run",
                    "--no-config",
                    "--color",
                    "never",
                    str(entry_file),
                ]
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(output.splitlines(), ["called"])
        self.assertIn("references main without calling it", errors)
        self.assertIn("write 'main()' to invoke it", errors)

    def test_config_rejects_unknown_keys_and_invalid_feature_names(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "x.toml"
            config_path.write_text(
                "[features]\nnot_a_feature = true\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "Unknown feature"):
                load_config(config_path)

            config_path.write_text(
                "[run]\nunknown-option = true\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "Unknown key"):
                load_config(config_path)

    def test_config_discovery_walks_up_from_nested_project_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            nested_directory = project_root / "packages" / "app"
            nested_directory.mkdir(parents=True)
            config_path = project_root / "x.toml"
            config_path.write_text("[features]\nloops = false\n", encoding="utf-8")

            discovered_config = discover_config(nested_directory)

        self.assertEqual(discovered_config, config_path)

    def test_legacy_file_invocation_uses_configured_default_command(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            config_path = project_root / "x.toml"
            config_path.write_text(
                '[cli]\ndefault-command = "check"\n',
                encoding="utf-8",
            )
            source_file = project_root / "main.x"
            source_file.write_text("function main() {}\n", encoding="utf-8")
            return_code, output, errors = self.run_cli(
                ["--config", str(config_path), str(source_file)]
            )

        self.assertEqual(return_code, 0)
        self.assertIn("syntax is valid", output)
        self.assertEqual(errors, "")

    def test_malformed_toml_reports_config_file_and_line(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            config_path = project_root / "bad.toml"
            config_path.write_text("[features\nclasses = true\n", encoding="utf-8")
            source_file = project_root / "main.x"
            source_file.write_text("function main() {}\n", encoding="utf-8")
            return_code, _, errors = self.run_cli(
                ["check", "--config", str(config_path), str(source_file)]
            )

        self.assertEqual(return_code, 2)
        self.assertIn(f"{config_path}:1", errors)
        self.assertIn("^", errors)

    def test_private_access_and_final_extension_have_source_locations(self):
        examples = {
            "private.x": (
                """
                class Vault {
                    private string secret;
                }
                function main() {
                    let Vault vault = new Vault();
                    print(vault.secret);
                }
                """,
                "private field",
                ":7:",
            ),
            "final.x": (
                """
                final class Closed {}
                class Open extends Closed {}
                function main() {}
                """,
                "Cannot extend final class 'Closed'",
                ":3:",
            ),
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            for file_name, (source, expected_message, expected_location) in examples.items():
                with self.subTest(file_name=file_name):
                    source_file = project_root / file_name
                    source_file.write_text(source, encoding="utf-8")
                    return_code, _, errors = self.run_cli(
                        [
                            "run",
                            "--no-config",
                            "--color",
                            "never",
                            str(source_file),
                        ]
                    )
                    self.assertEqual(return_code, 1)
                    self.assertIn(expected_message, errors)
                    self.assertIn(expected_location, errors)
                    self.assertIn("^", errors)


class CliRobustnessTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def test_options_without_a_command_report_usage_instead_of_crashing(self):
        for arguments in (
            ["--no-config"],
            ["--color", "never"],
            ["--feature", "loops=on"],
            ["--"],
        ):
            with self.subTest(arguments=arguments):
                return_code, _, errors = self.run_cli(arguments)
                self.assertEqual(return_code, 2)
                self.assertNotIn("Traceback", errors)
                self.assertNotIn("AttributeError", errors)

    def test_options_without_a_command_mention_the_missing_command(self):
        return_code, _, errors = self.run_cli(["--no-config"])
        self.assertEqual(return_code, 2)
        self.assertIn("x: expected a command or a source file", errors)
        self.assertIn("Usage:", errors)

    def test_version_flag_is_accepted_after_other_options(self):
        for arguments in (["-V"], ["--version"], ["--color", "never", "--version"]):
            with self.subTest(arguments=arguments):
                return_code, output, errors = self.run_cli(arguments)
                self.assertEqual(return_code, 0)
                self.assertTrue(output.startswith("X "))
                self.assertEqual(errors, "")

    def test_missing_source_file_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing.x"
            return_code, output, errors = self.run_cli(
                ["check", "--no-config", str(missing)]
            )

        self.assertEqual(return_code, 2)
        self.assertEqual(output, "")
        self.assertIn(f"x: source file '{missing}' does not exist", errors)
        self.assertNotIn("Imported source file", errors)
        self.assertNotIn("Traceback", errors)

    def test_directory_as_a_source_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory) / "folder.x"
            directory.mkdir()
            return_code, _, errors = self.run_cli(
                ["check", "--no-config", str(directory)]
            )

        self.assertEqual(return_code, 2)
        self.assertIn(f"x: '{directory}' is a directory", errors)
        self.assertNotIn("Traceback", errors)

    def test_unreadable_source_file_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "locked.x"
            source_file.write_text("function main() {}\n", encoding="utf-8")
            source_file.chmod(0)
            if os.access(source_file, os.R_OK):
                self.skipTest("the current user can read every file")
            return_code, _, errors = self.run_cli(
                ["check", "--no-config", str(source_file)]
            )

        self.assertEqual(return_code, 2)
        self.assertIn(f"x: cannot read '{source_file}'", errors)
        self.assertNotIn("Traceback", errors)

    def test_unknown_feature_override_points_at_the_command_line(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text("function main() {}\n", encoding="utf-8")
            return_code, _, errors = self.run_cli(
                ["check", "--feature", "bogus=on", str(source_file)]
            )

        self.assertEqual(return_code, 2)
        self.assertIn("Unknown feature 'bogus'", errors)
        self.assertIn("--> <command line>", errors)

    def test_deeply_nested_source_is_reported_without_a_python_traceback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "deep.x"
            source_file.write_text(
                "let a = " + "(" * 500 + "1" + ")" * 500 + ";\n",
                encoding="utf-8",
            )
            return_code, _, errors = self.run_cli(
                ["check", "--no-config", str(source_file)]
            )

        self.assertEqual(return_code, 1)
        self.assertIn("Program is nested too deeply to parse", errors)
        self.assertIn(f"{source_file}:1:", errors)
        self.assertNotIn("Traceback", errors)
        self.assertNotIn("RecursionError", errors)


if __name__ == "__main__":
    unittest.main()
