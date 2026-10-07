from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .config import (
    ConfigError,
    discover_config,
    load_env_file,
    load_config,
)
from .diagnostics import SourceWarning, render_diagnostic, render_warning
from .interpreter import Interpreter
from .lexer import LexError
from .module_loader import ModuleLoader
from .parser import ParseError
from .runtime import (
    RuntimeErrorX,
    ThrownValue,
    XExceptionValue,
    XInstance,
)
from .typecheck import TypeCheckFailure, TypeChecker


USAGE = """X language interpreter

Usage:
  x [OPTIONS] run <file>.x [-- <program arguments...>]
  x [OPTIONS] check <file>.x
  x [OPTIONS] build <file>.x
  x [OPTIONS] install <package>...
  x <file>.x [program arguments...]

Options:
  --config <path>       Read project settings from x.toml or another TOML file
  --no-config           Disable automatic and explicit configuration loading
  --feature NAME=on|off Override one feature flag
  --profile <name>      Add arguments and environment from a run profile
  --color <mode>        Diagnostic color: auto, always, or never
  -h, --help            Show this help
  -V, --version         Show the interpreter version
"""


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(USAGE, end="")
        return 0

    if arguments[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if arguments[0] in ("-V", "--version", "version"):
        print(f"X {__version__}")
        return 0

    normalized_arguments, is_implicit_command = _insert_implicit_run_command(arguments)
    argument_parser = _create_argument_parser()
    try:
        parsed = argument_parser.parse_args(normalized_arguments)
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        return 0

    if getattr(parsed, "show_version", False):
        print(f"X {__version__}")
        return 0

    if parsed.no_config and parsed.config_path is not None:
        print("x: --config cannot be combined with --no-config", file=sys.stderr)
        return 2

    current_directory = Path.cwd()
    config_path = None
    if not parsed.no_config:
        if parsed.config_path is not None:
            config_path = Path(parsed.config_path)
        else:
            config_path = discover_config(current_directory)

    try:
        config = load_config(
            config_path,
            parsed.feature_overrides,
            parsed.color,
        )
    except ConfigError as error:
        return _report_config_error(error, parsed.color, show_context=not parsed.no_context)

    command = config.default_command if is_implicit_command else parsed.command
    if command is None:
        print("x: expected a command or a source file", file=sys.stderr)
        print(USAGE, end="", file=sys.stderr)
        return 2
    if parsed.profile is not None and command != "run":
        print("x: --profile can only be used with the run command", file=sys.stderr)
        return 2

    if command == "install":
        if not config.enabled("package_manager"):
            print("x: package manager is experimental; enable with --feature package_manager=on", file=sys.stderr)
            return 2
        packages = getattr(parsed, "packages", [])
        print("x: package manager is not yet implemented")
        print(f"x: would install: {', '.join(packages)}")
        return 0

    source_path = Path(parsed.source)
    if source_path.suffix != ".x":
        print("x: source files must use the .x extension", file=sys.stderr)
        return 2
    if source_path.is_dir():
        print(f"x: '{source_path}' is a directory", file=sys.stderr)
        return 2
    if not source_path.exists():
        print(f"x: source file '{source_path}' does not exist", file=sys.stderr)
        return 2
    if not os.access(source_path, os.R_OK):
        print(f"x: cannot read '{source_path}': permission denied", file=sys.stderr)
        return 2

    try:
        run_profile = config.selected_run(parsed.profile) if command == "run" else None
    except ConfigError as error:
        return _report_config_error(error, config.color, show_context=not parsed.no_context)

    program_arguments = []
    if run_profile is not None:
        program_arguments.extend(run_profile.arguments)
    cli_program_arguments = list(getattr(parsed, "program_arguments", []))
    if cli_program_arguments and cli_program_arguments[0] == "--":
        cli_program_arguments.pop(0)
    program_arguments.extend(cli_program_arguments)

    project_root = config.path.parent if config.path is not None else current_directory
    loader = ModuleLoader(project_root, config, recover_errors=True)
    interpreter: Interpreter | None = None
    try:
        program = loader.load_program(source_path)
        _report_module_warnings(loader, config.color)
        if loader.errors:
            return _report_source_errors(
                loader.errors,
                loader.sources,
                source_path,
                config.color,
                show_context=not parsed.no_context,
            )
        if command in ("check", "build"):
            if config.enabled("type_checker"):
                type_errors = TypeChecker().check(program, source_name=str(source_path), config=config)
                if type_errors:
                    return _report_source_errors(
                        type_errors,
                        loader.sources,
                        source_path,
                        config.color,
                        label="type error",
                        show_context=not parsed.no_context,
                    )
            print(f"{source_path}: syntax is valid")
            if config.enabled("type_checker"):
                print(f"{source_path}: types are valid")
            if command == "build":
                print(
                    "X 0.1 currently interprets source; no native executable was produced."
                )
            return 0

        env_file_directory = (
            config.path.parent
            if config.path is not None
            else source_path.resolve().parent
        )
        dotenv_environment = load_env_file(env_file_directory / ".env")
        environment = {
            key: value
            for key, value in dotenv_environment.items()
            if key not in os.environ
        }
        if run_profile is not None:
            environment.update(run_profile.environment)
        interpreter = Interpreter(
            program_arguments,
            config=config,
            environment=environment,
        )
        try:
            result = interpreter.interpret(program)
        finally:
            _report_warnings(interpreter.warnings, loader.sources, config.color)
        if result is None:
            return 0
        if isinstance(result, int) and not isinstance(result, bool):
            if 0 <= result <= 255:
                return result
            print("x: main must return an exit code between 0 and 255", file=sys.stderr)
            return 1
        print("x: main must return void or an integer exit code", file=sys.stderr)
        return 1
    except ConfigError as error:
        return _report_config_error(error, config.color, show_context=not parsed.no_context)
    except TypeCheckFailure as failure:
        return _report_source_errors(
            failure.errors,
            loader.sources,
            source_path,
            config.color,
            label="type error",
            show_context=not parsed.no_context,
        )
    except (LexError, ParseError, RuntimeErrorX) as error:
        if (
            isinstance(error, RuntimeErrorX)
            and error.exception_name != "RuntimeException"
        ):
            display_name = (
                "Cannot divide by zero"
                if error.exception_name == "ArithmeticException"
                and "Division by zero" in error.message
                else error.exception_name
            )
            typed_error = RuntimeErrorX(
                f"{display_name}: {error.message}",
                error.exception_name,
            )
            typed_error.line = error.line
            typed_error.column = error.column
            typed_error.source_name = error.source_name
            error = typed_error
        return _report_source_error(
            error,
            loader.sources,
            source_path,
            config.color,
            show_context=not parsed.no_context,
        )
    except ThrownValue as thrown:
        value = thrown.value
        if isinstance(value, XExceptionValue):
            display_name = (
                "Cannot divide by zero"
                if value.name == "ArithmeticException"
                and "Division by zero" in value.message
                else f"Uncaught {value.name}"
            )
            message = f"{display_name}: {value.message}"
        elif isinstance(value, XInstance) and _is_exception_instance(value):
            exception_name = value.xclass.name
            exception_message = value.fields.get("message", "")
            message = f"Uncaught {exception_name}: {exception_message}"
        else:
            message = f"Uncaught exception: {value}"
        uncaught_error = RuntimeErrorX(message)
        uncaught_error.line = thrown.line
        uncaught_error.column = thrown.column
        uncaught_error.source_name = thrown.source_name
        return _report_source_error(
            uncaught_error,
            loader.sources,
            source_path,
            config.color,
        )
    except OSError as error:
        source_name = getattr(error, "filename", None) or str(source_path)
        print(f"x: cannot read '{source_name}': {error}", file=sys.stderr)
        return 2
    except RecursionError as error:
        message = "Maximum recursion depth exceeded"
        runtime_error = RuntimeErrorX(message, "RuntimeException")
        # Try to get the current location from the interpreter
        if interpreter is not None and interpreter.current_location is not None:
            source_name, line, column = interpreter.current_location
            runtime_error.source_name = source_name or str(source_path)
            runtime_error.line = line
            runtime_error.column = column
        else:
            runtime_error.source_name = str(source_path)
            runtime_error.line = None
            runtime_error.column = None
        return _report_source_error(
            runtime_error,
            loader.sources,
            source_path,
            config.color,
        )
    except Exception as error:
        # Catch any other Python exceptions and convert to X language errors
        # to avoid exposing Python implementation details
        message = f"Runtime error: {str(error)}"
        runtime_error = RuntimeErrorX(message, "RuntimeException")
        # Try to get the current location from the interpreter
        if interpreter is not None and interpreter.current_location is not None:
            source_name, line, column = interpreter.current_location
            runtime_error.source_name = source_name or str(source_path)
            runtime_error.line = line
            runtime_error.column = column
        else:
            runtime_error.source_name = str(source_path)
            runtime_error.line = None
            runtime_error.column = None
        return _report_source_error(
            runtime_error,
            loader.sources,
            source_path,
            config.color,
        )


def _is_exception_instance(value: XInstance) -> bool:
    current_class = value.xclass
    while current_class is not None:
        if current_class.is_exception_base:
            return True
        current_class = current_class.parent
    return False


def _create_argument_parser() -> argparse.ArgumentParser:
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--config", dest="config_path", default=argparse.SUPPRESS
    )
    common_parser.add_argument(
        "--no-config", action="store_true", default=argparse.SUPPRESS
    )
    common_parser.add_argument(
        "--feature",
        dest="feature_overrides",
        action="append",
        default=argparse.SUPPRESS,
    )
    common_parser.add_argument("--profile", default=argparse.SUPPRESS)
    common_parser.add_argument(
        "--color", choices=("auto", "always", "never"), default=argparse.SUPPRESS
    )
    common_parser.add_argument(
        "--no-context", action="store_true", default=argparse.SUPPRESS
    )

    parser = argparse.ArgumentParser(
        prog="x",
        description="Run, validate, or build an X language source file.",
        epilog="With no command, a source file is run directly.",
        parents=[common_parser],
    )
    parser.add_argument(
        "-V",
        "--version",
        dest="show_version",
        action="store_true",
        help="show the interpreter version and exit",
    )
    parser.set_defaults(
        config_path=None,
        no_config=False,
        feature_overrides=[],
        profile=None,
        color=None,
        no_context=False,
        show_version=False,
    )
    subparsers = parser.add_subparsers(dest="command")
    for command in ("run", "check", "build", "install"):
        command_parser = subparsers.add_parser(
            command,
            parents=[common_parser],
            add_help=True,
        )
        if command == "install":
            command_parser.add_argument("packages", nargs="+")
        else:
            command_parser.add_argument("source")
            if command == "run":
                command_parser.add_argument(
                    "program_arguments", nargs=argparse.REMAINDER
                )
    return parser


def _insert_implicit_run_command(
    arguments: list[str],
) -> tuple[list[str], bool]:
    known_commands = {"run", "check", "build"}
    first_non_option = 0
    while first_non_option < len(arguments):
        current_argument = arguments[first_non_option]
        if current_argument in known_commands:
            if first_non_option == 0:
                return arguments, False
            leading_options = arguments[:first_non_option]
            remaining_arguments = arguments[first_non_option + 1:]
            return [
                current_argument,
                *leading_options,
                *remaining_arguments,
            ], False
        if current_argument == "--":
            return arguments, False
        if not current_argument.startswith("-"):
            if current_argument.endswith(".x"):
                return ["run", *arguments], True
            return arguments, False
        if current_argument in {"--config", "--feature", "--profile", "--color"}:
            first_non_option += 2
        else:
            first_non_option += 1
    return arguments, False


def _display_name(source_name: str) -> str:
    """Show a path relative to the working directory when it lives inside it.

    Diagnostics read best as ``--> examples/main.x:4:3``; anything outside the
    working directory keeps the path the user (or the loader) supplied.
    """
    try:
        relative = os.path.relpath(Path(source_name).resolve(), Path.cwd())
    except (OSError, ValueError):
        return source_name
    if relative.startswith(".."):
        return source_name
    return relative


def _report_config_error(error: ConfigError, color_mode: str | None, show_context: bool = True) -> int:
    source_text = None
    try:
        source_text = error.path.read_text(encoding="utf-8")
    except OSError:
        pass
    diagnostic = render_diagnostic(
        error,
        source_text,
        _display_name(str(error.path)),
        color_mode or "auto",
        show_context=show_context,
    )
    print(diagnostic, file=sys.stderr)
    return 2


def _report_source_error(
    error: BaseException,
    sources: dict[Path, str],
    entry_path: Path,
    color_mode: str,
    show_context: bool = True,
) -> int:
    source_name = getattr(error, "source_name", None)
    resolved_name = Path(source_name).resolve() if source_name else entry_path.resolve()
    source_text = sources.get(resolved_name)
    if source_text is None:
        try:
            source_text = resolved_name.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            source_text = None
    diagnostic = render_diagnostic(
        error,
        source_text,
        _display_name(source_name) if source_name else str(entry_path),
        color_mode,
        show_context=show_context,
    )
    print(diagnostic, file=sys.stderr)
    return 1


def _report_source_errors(
    errors: list[BaseException],
    sources: dict[Path, str],
    entry_path: Path,
    color_mode: str,
    label: str = "error",
    show_context: bool = True,
) -> int:
    ordered_errors = sorted(
        errors,
        key=lambda error: (
            str(
                Path(getattr(error, "source_name", None) or entry_path).resolve()
            ),
            getattr(error, "line", 0) or 0,
            getattr(error, "column", 0) or 0,
        ),
    )
    for error in ordered_errors:
        source_name = getattr(error, "source_name", None)
        resolved_name = (
            Path(source_name).resolve() if source_name else entry_path.resolve()
        )
        source_text = sources.get(resolved_name)
        if source_text is None:
            try:
                source_text = resolved_name.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                source_text = None
        diagnostic = render_diagnostic(
            error,
            source_text,
            _display_name(source_name) if source_name else str(entry_path),
            color_mode,
            show_context=show_context,
        )
        print(diagnostic, file=sys.stderr)
    print(f"x: found {len(errors)} {label}(s)", file=sys.stderr)
    return 1


def _report_module_warnings(loader: ModuleLoader, color_mode: str) -> None:
    _report_warnings(loader.warnings, loader.sources, color_mode)


def _report_warnings(
    warnings: list[SourceWarning],
    sources: dict[Path, str],
    color_mode: str,
) -> None:
    for warning in warnings:
        warning_path = Path(warning.source_name).resolve()
        source = sources.get(warning_path)
        diagnostic = render_warning(
            warning.message,
            source,
            _display_name(warning.source_name),
            warning.line,
            warning.column,
            color_mode,
            notes=warning.notes,
            helps=warning.helps,
        )
        print(diagnostic, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
