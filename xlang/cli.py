from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .config import (
    BUILTIN_COMMANDS,
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
  x [OPTIONS] format <file>.x
  x [OPTIONS] install <package>...
  x [OPTIONS] repl
  x [OPTIONS] -watch <file>.x [program arguments...]
  x <script> [-- <script arguments...>]
  x <file>.x [program arguments...]

Options:
  --config <path>       Read project settings from x.toml or another TOML file
  --no-config           Disable automatic and explicit configuration loading
  --feature NAME=on|off Override one feature flag
  --profile <name>      Add arguments and environment from a run profile
  --color <mode>        Diagnostic color: auto, always, or never
  -w, --watch           Re-run automatically whenever a watched file changes
                        (the single-dash form -watch is also accepted)
  -h, --help            Show this help
  -V, --version         Show the interpreter version

Format:
  x format file.x       Rewrite file.x with canonical formatting in place
  x --watch format file.x
                        Reformat automatically whenever file.x changes while
                        you type

Scripts:
  Commands defined in the [scripts] table of x.toml run with 'x <name>',
  similar to 'pnpm start' and package.json scripts:
    x start
    x start -- extra script arguments
"""

_WATCH_POLL_INTERVAL = 0.2
_WATCH_DEBOUNCE = 0.1


@dataclass
class _WatchState:
    """Bookkeeping for a single watch-mode execution."""

    files: set[Path] = field(default_factory=set)
    config_path: Path | None = None
    abort: bool = False


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

    arguments = _normalize_watch_flag(arguments)
    normalized_arguments, is_implicit_command = _insert_implicit_run_command(
        arguments
    )
    normalized_arguments, is_script_invocation = _insert_script_command(
        normalized_arguments
    )
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

    if parsed.watch:
        return _watch_loop(parsed, is_implicit_command, is_script_invocation)
    return _execute(parsed, is_implicit_command, is_script_invocation)


def _exit_code_of(stop: SystemExit) -> int:
    """Map a ``System.process.exit`` request onto a shell exit status."""
    code = stop.code
    if code is None:
        return 0
    if isinstance(code, bool) or not isinstance(code, (int, float)):
        if isinstance(code, str):
            print(code, file=sys.stderr)
        else:
            print(
                "x: System.process.exit expects an integer exit code",
                file=sys.stderr,
            )
        return 1
    if isinstance(code, float):
        code = int(code)
    if 0 <= code <= 255:
        return code
    return 1


def _execute(
    parsed: argparse.Namespace,
    is_implicit_command: bool,
    is_script_invocation: bool,
    watch_state: _WatchState | None = None,
) -> int:
    state = watch_state if watch_state is not None else _WatchState()
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
    state.config_path = config.path

    command = config.default_command if is_implicit_command else parsed.command
    if command is None:
        state.abort = True
        print("x: expected a command or a source file", file=sys.stderr)
        print(USAGE, end="", file=sys.stderr)
        return 2
    if parsed.profile is not None and command != "run":
        state.abort = True
        print("x: --profile can only be used with the run command", file=sys.stderr)
        return 2
    if parsed.watch and command == "install":
        state.abort = True
        print("x: --watch can only be used with run, check, build, or format", file=sys.stderr)
        return 2

    if command == "install":
        state.abort = True
        if not config.enabled("package_manager"):
            print("x: package manager is experimental; enable with --feature package_manager=on", file=sys.stderr)
            return 2
        packages = getattr(parsed, "packages", [])
        print("x: package manager is not yet implemented")
        print(f"x: would install: {', '.join(packages)}")
        return 0

    if command == "repl":
        state.abort = True
        if parsed.watch:
            print("x: --watch cannot be used with repl", file=sys.stderr)
            return 2
        from .repl import run_repl

        return run_repl(config)

    source_path = Path(parsed.source)
    if source_path.suffix != ".x":
        state.abort = True
        script_command = config.scripts.get(parsed.source)
        if script_command is None:
            if is_script_invocation or config.scripts:
                if is_script_invocation and not config.scripts:
                    location = (
                        config.path.name if config.path is not None else "x.toml"
                    )
                    print(
                        f"x: '{parsed.source}' is not a source file and no "
                        f"[scripts] are defined in {location}",
                        file=sys.stderr,
                    )
                else:
                    available = ", ".join(sorted(config.scripts))
                    print(
                        f"x: unknown script '{parsed.source}'. "
                        f"Available scripts: {available}",
                        file=sys.stderr,
                    )
                return 2
            print("x: source files must use the .x extension", file=sys.stderr)
            return 2
        if command in ("check", "build", "format"):
            print(
                f"x: '{parsed.source}' is a script; run it with "
                f"'x {parsed.source}'",
                file=sys.stderr,
            )
            return 2
        if parsed.watch:
            print("x: --watch cannot be used with scripts", file=sys.stderr)
            return 2
        project_root = (
            config.path.parent if config.path is not None else current_directory
        )
        try:
            script_profile = config.selected_run(parsed.profile)
        except ConfigError as error:
            return _report_config_error(
                error, config.color, show_context=not parsed.no_context
            )
        script_arguments: list[str] = []
        if parsed.profile is not None:
            script_arguments.extend(config.profiles[parsed.profile].arguments)
        cli_script_arguments = list(getattr(parsed, "program_arguments", []))
        if cli_script_arguments and cli_script_arguments[0] == "--":
            cli_script_arguments.pop(0)
        script_arguments.extend(cli_script_arguments)
        try:
            dotenv_environment = load_env_file(project_root / ".env")
        except ConfigError as error:
            return _report_config_error(
                error, config.color, show_context=not parsed.no_context
            )
        script_environment = {
            key: value
            for key, value in dotenv_environment.items()
            if key not in os.environ
        }
        script_environment.update(script_profile.environment)
        return _run_script(
            parsed.source,
            script_command,
            script_arguments,
            script_environment,
            project_root,
        )
    if source_path.is_dir():
        print(f"x: '{source_path}' is a directory", file=sys.stderr)
        return 2
    if not source_path.exists():
        print(f"x: source file '{source_path}' does not exist", file=sys.stderr)
        return 2
    if not os.access(source_path, os.R_OK):
        print(f"x: cannot read '{source_path}': permission denied", file=sys.stderr)
        return 2

    if command == "format":
        return _format_source_file(source_path, state, config.color,
                                   show_context=not parsed.no_context)

    try:
        run_profile = config.selected_run(parsed.profile) if command == "run" else None
    except ConfigError as error:
        state.abort = True
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
        state.files.update(loader.sources)
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
        env_file = env_file_directory / ".env"
        state.files.add(env_file)
        dotenv_environment = load_env_file(env_file)
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
        except SystemExit as stop:
            result = _exit_code_of(stop)
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
            typed_error.end_line = error.end_line
            typed_error.end_column = error.end_column
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
        uncaught_error.end_line = getattr(thrown, "end_line", None)
        uncaught_error.end_column = getattr(thrown, "end_column", None)
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
            if interpreter.current_span is not None:
                runtime_error.end_line, runtime_error.end_column = (
                    interpreter.current_span
                )
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
            if interpreter.current_span is not None:
                runtime_error.end_line, runtime_error.end_column = (
                    interpreter.current_span
                )
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
    common_parser.add_argument(
        "-w",
        "--watch",
        dest="watch",
        action="store_true",
        default=argparse.SUPPRESS,
        help="re-run automatically whenever a watched file changes",
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
        watch=False,
    )
    subparsers = parser.add_subparsers(dest="command")
    for command in ("run", "check", "build", "format", "install", "repl"):
        command_parser = subparsers.add_parser(
            command,
            parents=[common_parser],
            add_help=True,
        )
        if command == "install":
            command_parser.add_argument("packages", nargs="+")
        elif command == "repl":
            pass
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
    known_commands = set(BUILTIN_COMMANDS)
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


def _normalize_watch_flag(arguments: list[str]) -> list[str]:
    """Accept the single-dash ``-watch`` spelling before ``--``.

    argparse only understands ``-w``/``--watch``; without this pass,
    ``x -watch main.x`` would be parsed as the short-option cluster ``-w -a -t
    ...`` and fail. Everything after ``--`` belongs to the program, so it is
    left untouched.
    """
    normalized: list[str] = []
    for argument in arguments:
        if argument == "--":
            break
        normalized.append("--watch" if argument == "-watch" else argument)
    else:
        return normalized
    separator_index = len(normalized)
    return [*normalized, *arguments[separator_index:]]


def _insert_script_command(
    arguments: list[str],
) -> tuple[list[str], bool]:
    """Rewrite ``x <script>`` into ``x run <script>``.

    The first positional token is treated as a script name when it is neither
    a built-in command nor a ``.x`` source file, mirroring how a bare
    ``x file.x`` becomes ``x run file.x``. Leading options are moved behind the
    inserted command so the subparser sees them (see
    ``_insert_implicit_run_command``).
    """
    known_commands = set(BUILTIN_COMMANDS)
    first_non_option = 0
    while first_non_option < len(arguments):
        current_argument = arguments[first_non_option]
        if current_argument == "--":
            return arguments, False
        if current_argument.startswith("-"):
            if current_argument in {"--config", "--feature", "--profile", "--color"}:
                first_non_option += 2
            else:
                first_non_option += 1
            continue
        if current_argument in known_commands or current_argument.endswith(".x"):
            return arguments, False
        leading_options = arguments[:first_non_option]
        return [
            "run",
            *leading_options,
            current_argument,
            *arguments[first_non_option + 1:],
        ], True
    return arguments, False


def _format_source_file(
    source_path: Path,
    state: _WatchState,
    color_mode: str | None,
    show_context: bool = True,
) -> int:
    """Rewrite *source_path* with canonical formatting, in place.

    The file is only written when formatting actually changes it, which
    keeps ``x --watch format`` quiet and free of self-triggered rewrite
    loops.  Syntax errors abort the rewrite with a normal diagnostic.
    """
    from .formatter import format_source

    state.files.add(source_path)
    try:
        original = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"x: cannot read '{source_path}': {error}", file=sys.stderr)
        return 2
    try:
        formatted = format_source(original, source_name=str(source_path))
    except (LexError, ParseError) as error:
        return _report_source_errors(
            [error],
            {source_path.resolve(): original},
            source_path,
            color_mode or "auto",
            show_context=show_context,
        )
    if formatted == original:
        print(f"{source_path}: already formatted")
        return 0
    try:
        source_path.write_text(formatted, encoding="utf-8")
    except OSError as error:
        print(f"x: cannot write '{source_path}': {error}", file=sys.stderr)
        return 2
    print(f"{source_path}: formatted")
    return 0


def _watch_loop(
    parsed: argparse.Namespace,
    is_implicit_command: bool,
    is_script_invocation: bool,
) -> int:
    """Run once, then re-run whenever a watched file changes until Ctrl+C."""
    restore_sigint = _ensure_sigint_handler()
    state = _WatchState()
    is_format_command = getattr(parsed, "command", None) == "format"
    try:
        exit_code = _execute(
            parsed, is_implicit_command, is_script_invocation, state
        )
        sys.stdout.flush()
        if state.abort:
            return exit_code
        watched = set(state.files)
        watched.update(_seed_watch_paths(parsed, state))
        print(
            f"x: watching {len(watched)} file(s); press Ctrl+C to stop",
            file=sys.stderr,
        )
        snapshot = _snapshot_files(watched)
        while True:
            time.sleep(_WATCH_POLL_INTERVAL)
            watched.update(state.files)
            current_snapshot = _snapshot_files(watched)
            if current_snapshot == snapshot:
                continue
            time.sleep(_WATCH_DEBOUNCE)
            snapshot = _snapshot_files(watched)
            print("x: change detected; re-running", file=sys.stderr)
            state = _WatchState()
            exit_code = _execute(
                parsed, is_implicit_command, is_script_invocation, state
            )
            sys.stdout.flush()
            if state.abort:
                return exit_code
            watched.update(state.files)
            watched.update(_seed_watch_paths(parsed, state))
            refreshed = _snapshot_files(watched)
            if is_format_command:
                # The formatter rewrites the watched file itself; adopt the
                # post-format signatures so its own write does not loop.
                snapshot = refreshed
            else:
                for path, signature in refreshed.items():
                    snapshot.setdefault(path, signature)
    except KeyboardInterrupt:
        sys.stdout.flush()
        print("\nx: stopped watching", file=sys.stderr)
        return 0
    finally:
        if restore_sigint is not None:
            try:
                signal.signal(signal.SIGINT, restore_sigint)
            except (ValueError, OSError):
                pass


def _ensure_sigint_handler():
    """Install a Ctrl+C handler when SIGINT was inherited as 'ignore'.

    Shells mark asynchronous jobs with SIGINT ignored, which would otherwise
    make a backgrounded ``x -watch`` impossible to stop. Returns the previous
    handler when it was replaced so callers can restore it.
    """
    try:
        if signal.getsignal(signal.SIGINT) is signal.SIG_IGN:
            return signal.signal(signal.SIGINT, signal.default_int_handler)
    except (ValueError, OSError, RuntimeError):
        return None
    return None


def _seed_watch_paths(
    parsed: argparse.Namespace, state: _WatchState
) -> list[Path]:
    """Paths to watch even when the first run failed before loading files."""
    seeds: list[Path] = []
    if state.config_path is not None:
        seeds.append(state.config_path)
    elif not parsed.no_config:
        if parsed.config_path is not None:
            seeds.append(Path(parsed.config_path))
        else:
            discovered_config = discover_config(Path.cwd())
            if discovered_config is not None:
                seeds.append(discovered_config)
    source = getattr(parsed, "source", None)
    if source:
        source_path = Path(source)
        try:
            seeds.append(source_path.resolve())
        except OSError:
            seeds.append(source_path)
    return seeds


def _snapshot_files(
    paths: set[Path],
) -> dict[str, tuple[int, int] | None]:
    """Map each path to its (mtime, size), or None when it does not exist."""
    snapshot: dict[str, tuple[int, int] | None] = {}
    for path in sorted(paths, key=str):
        try:
            stat_result = path.stat()
        except OSError:
            snapshot[str(path)] = None
        else:
            snapshot[str(path)] = (stat_result.st_mtime_ns, stat_result.st_size)
    return snapshot


def _run_script(
    name: str,
    script: str,
    arguments: list[str],
    environment: dict[str, str],
    working_directory: Path,
) -> int:
    """Execute a [scripts] command through the shell, like a package manager."""
    command = script
    if arguments:
        command = f"{command} {' '.join(shlex.quote(argument) for argument in arguments)}"
    print(f"x: running script '{name}': {command}", file=sys.stderr)
    process_environment = dict(os.environ)
    process_environment.update(environment)
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(working_directory),
            env=process_environment,
            check=False,
        )
    except OSError as error:
        print(f"x: cannot run script '{name}': {error}", file=sys.stderr)
        return 2
    return_code = completed.returncode
    if return_code < 0:
        return_code = 128 - return_code
    if return_code > 255:
        return_code = 255
    return return_code


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
