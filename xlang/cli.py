from __future__ import annotations

import sys
from pathlib import Path

from . import __version__
from .lexer import LexError
from .module_loader import ModuleLoader
from .parser import ParseError
from .runtime import Interpreter, RuntimeErrorX, ThrownValue, XExceptionValue


USAGE = """X language interpreter

Usage:
  x <file>.x [arguments...]
  x run <file>.x [arguments...]
  x check <file>.x
  x build <file>.x
  x version
"""


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if arguments[0] in ("-V", "--version", "version"):
        print(f"X {__version__}")
        return 0

    command = "run"
    if arguments[0] in ("run", "check", "build"):
        command = arguments.pop(0)
    if not arguments:
        print("x: expected a source file ending in .x", file=sys.stderr)
        return 2

    source_path = Path(arguments.pop(0))
    program_arguments = arguments
    if source_path.suffix != ".x":
        print("x: source files must use the .x extension", file=sys.stderr)
        return 2
    try:
        project_root = Path.cwd()
        program = ModuleLoader(project_root).load_program(source_path)
        if command in ("check", "build"):
            print(f"{source_path}: syntax is valid")
            if command == "build":
                print("X 0.1 currently interprets source; no native executable was produced.")
            return 0
        result = Interpreter(program_arguments).interpret(program)
        if result is None:
            return 0
        if isinstance(result, int) and not isinstance(result, bool):
            if 0 <= result <= 255:
                return result
            print("x: main must return an exit code between 0 and 255", file=sys.stderr)
            return 1
        print("x: main must return void or an integer exit code", file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as error:
        print(f"x: cannot read '{source_path}': {error}", file=sys.stderr)
        return 2
    except (LexError, ParseError, RuntimeErrorX) as error:
        print(f"x: {source_path}: {error}", file=sys.stderr)
        return 1
    except ThrownValue as thrown:
        value = thrown.value
        if isinstance(value, XExceptionValue):
            message = value.message
        else:
            message = str(value)
        print(f"x: {source_path}: uncaught exception: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
