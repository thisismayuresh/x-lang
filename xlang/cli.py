from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import (
    ConfigError,
    discover_config,
    load_config,
)
from .diagnostics import render_diagnostic
from .lexer import LexError
from .module_loader import ModuleLoader
from .parser import ParseError
from .runtime import Interpreter, RuntimeErrorX, ThrownValue, XExceptionValue


USAGE = """X language interpreter

Usage:
  x [OPTIONS] run <file>.x [-- <program arguments...>]
  x [OPTIONS] check <file>.x
  x [OPTIONS] build <file>.x
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
        return _report_config_error(error, parsed.color)

    source_path = Path(parsed.source)
    if source_path.suffix != ".x":
        print("x: source files must use the .x extension", file=sys.stderr)
        return 2

    command = config.default_command if is_implicit_command else parsed.command
    if parsed.profile is not None and command != "run":
        print("x: --profile can only be used with the run command", file=sys.stderr)
        return 2

    try:
        run_profile = config.selected_run(parsed.profile) if command == "run" else None
    except ConfigError as error:
        return _report_config_error(error, config.color)

    program_arguments = []
    if run_profile is not None:
        program_arguments.extend(run_profile.arguments)
    cli_program_arguments = list(getattr(parsed, "program_arguments", []))
    if cli_program_arguments and cli_program_arguments[0] == "--":
        cli_program_arguments.pop(0)
    program_arguments.extend(cli_program_arguments)

    project_root = config.path.parent if config.path is not None else current_directory
    loader = ModuleLoader(project_root, config)
    try:
        program = loader.load_program(source_path)
        if command in ("check", "build"):
            print(f"{source_path}: syntax is valid")
            if command == "build":
                print(
                    "X 0.1 currently interprets source; no native executable was produced."
                )
            return 0

        environment = {} if run_profile is None else run_profile.environment
        result = Interpreter(
            program_arguments,
            config=config,
            environment=environment,
        ).interpret(program)
        if result is None:
            return 0
        if isinstance(result, int) and not isinstance(result, bool):
            if 0 <= result <= 255:
                return result
            print("x: main must return an exit code between 0 and 255", file=sys.stderr)
            return 1
        print("x: main must return void or an integer exit code", file=sys.stderr)
        return 1
    except (LexError, ParseError, RuntimeErrorX) as error:
        return _report_source_error(
            error,
            loader.sources,
            source_path,
            config.color,
        )
    except ThrownValue as thrown:
        value = thrown.value
        if isinstance(value, XExceptionValue):
            message = value.message
        else:
            message = str(value)
        uncaught_error = RuntimeErrorX(f"Uncaught exception: {message}")
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

    parser = argparse.ArgumentParser(
        prog="x",
        description="Run, validate, or build an X language source file.",
        epilog="With no command, a source file is run directly.",
        parents=[common_parser],
    )
    parser.set_defaults(
        config_path=None,
        no_config=False,
        feature_overrides=[],
        profile=None,
        color=None,
    )
    subparsers = parser.add_subparsers(dest="command")
    for command in ("run", "check", "build"):
        command_parser = subparsers.add_parser(
            command,
            parents=[common_parser],
            add_help=True,
        )
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


def _report_config_error(error: ConfigError, color_mode: str | None) -> int:
    source_text = None
    try:
        source_text = error.path.read_text(encoding="utf-8")
    except OSError:
        pass
    diagnostic = render_diagnostic(
        error,
        source_text,
        str(error.path),
        color_mode or "auto",
    )
    print(diagnostic, file=sys.stderr)
    return 2


def _report_source_error(
    error: BaseException,
    sources: dict[Path, str],
    entry_path: Path,
    color_mode: str,
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
        source_name or str(entry_path),
        color_mode,
    )
    print(diagnostic, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
