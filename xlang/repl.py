"""Interactive read-eval-print loop behind the ``x repl`` command.

Each entry is parsed on its own, type-checked together with everything typed
earlier in the session, and then executed against one persistent global
environment so definitions survive from one entry to the next.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from .ast_nodes import (
    ExpressionStatement,
    ImportAlias,
    ImportNamespaceAlias,
    Program,
)
from .config import XConfig
from .lexer import LexError, Lexer
from .parser import ParseError, Parser
from .runtime import Interpreter, RuntimeErrorX
from .typecheck import TypeCheckError, TypeCheckFailure, TypeChecker

REPL_SOURCE = "<repl>"
PROMPT = "x> "
CONTINUATION_PROMPT = "... "
BANNER = (
    "X REPL — expressions print their value, declarations keep their state.\n"
    "  .help   show this help\n"
    "  .exit   leave the REPL (Ctrl-D also works)\n"
)
HELP_TEXT = """\
REPL commands:
  .help, .?   show this help
  .exit       leave the REPL (.quit, exit, quit and Ctrl-D also work)

An entry continues onto the next line while brackets are still open, so
functions, classes and blocks can be typed over several lines.  Expressions
print their value; everything else reports diagnostics and keeps going."""

#: Environment tables that must be cleaned when a name is declared again.
_BINDING_ATTRIBUTES = (
    "values",
    "constants",
    "array_types",
    "object_types",
    "value_types",
)

_DOT_COMMANDS = {".help", ".?"}


def run_repl(
    config: XConfig,
    *,
    input_fn: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
    error_output: Callable[[str], None] | None = None,
    banner: bool = True,
) -> int:
    """Read, evaluate and print entries until the user leaves the session.

    Returns the process exit status: ``0`` for a normal exit, or the status
    requested through ``System.process.exit``.
    """
    if error_output is None:

        def error_output(text: str) -> None:
            print(text, file=sys.stderr)

    if banner:
        output(BANNER)

    interpreter = Interpreter(
        [],
        output=output,
        config=config,
        validate=False,
        auto_call_main=False,
    )
    history: list[str] = []
    buffer: list[str] = []

    while True:
        try:
            line = input_fn(PROMPT if not buffer else CONTINUATION_PROMPT)
        except KeyboardInterrupt:
            buffer.clear()
            output("")
            continue
        except EOFError:
            output("")
            return 0

        stripped = line.strip()
        if not buffer:
            if stripped in _DOT_COMMANDS:
                output(HELP_TEXT)
                continue
            if stripped in {".exit", ".quit"}:
                return 0
            if stripped in {"exit", "quit"} and interpreter.globals.values.get(
                stripped
            ) is None:
                return 0
            if not stripped:
                continue

        buffer.append(line)
        source = "\n".join(buffer)
        program, error = _parse(source, config)
        if program is None and _is_incomplete(source, error):
            continue
        buffer.clear()
        if program is None:
            _report(error, error_output, source=source)
            continue

        exit_code = _evaluate_program(
            program, source, history, interpreter, config, output, error_output
        )
        if exit_code is not None:
            return exit_code


def _evaluate_program(
    program: Program,
    source: str,
    history: list[str],
    interpreter: Interpreter,
    config: XConfig,
    output: Callable[[str], None],
    error_output: Callable[[str], None],
) -> int | None:
    """Check and run one finished entry; return an exit code to stop on."""
    first_line = sum(len(entry.splitlines()) for entry in history)
    history.append(source)
    type_errors = _type_check("\n".join(history), config, first_line)
    if type_errors:
        history.pop()
        for type_error in type_errors:
            _report(type_error, error_output, source=source, line_offset=first_line)
        return None

    try:
        _run(interpreter, program, output)
    except SystemExit as stop:
        exit_code = _exit_code(stop)
        output(f"process exited with code {exit_code}")
        return exit_code
    except (RuntimeErrorX, TypeCheckFailure) as error:
        _report(error, error_output, source=source)
    except Exception as error:  # pragma: no cover - defensive REPL shield
        _report(error, error_output, source=source)
    finally:
        _drain_warnings(interpreter, error_output)
    return None


def _run(
    interpreter: Interpreter,
    program: Program,
    output: Callable[[str], None],
) -> None:
    """Execute *program* and echo the value of a trailing expression."""
    declarations = list(program.declarations)
    trailing = None
    if declarations and isinstance(declarations[-1], ExpressionStatement):
        trailing = declarations.pop()
    _forget_bindings(interpreter, declarations)
    interpreter.interpret(Program(declarations))
    if trailing is None:
        return
    value = interpreter._evaluate(trailing.expression, interpreter.globals)
    if value is not None:
        output(interpreter._stringify(value))


def _forget_bindings(interpreter: Interpreter, declarations: list[Any]) -> None:
    """Drop names this entry declares again so re-declaration is allowed."""
    environment = interpreter.globals
    for declaration in declarations:
        name = _declaration_name(declaration)
        if not name:
            continue
        for attribute in _BINDING_ATTRIBUTES:
            container = getattr(environment, attribute, None)
            if isinstance(container, dict):
                container.pop(name, None)
            elif isinstance(container, set):
                container.discard(name)


def _declaration_name(declaration: Any) -> str | None:
    if isinstance(declaration, (ImportAlias, ImportNamespaceAlias)):
        return declaration.alias_name
    name = getattr(declaration, "name", None)
    if isinstance(name, str) and name:
        return name
    return None


def _parse(source: str, config: XConfig) -> tuple[Program | None, Exception | None]:
    """Lex and parse *source*, returning ``(None, error)`` when it is invalid."""
    try:
        lexer = Lexer(source, REPL_SOURCE, recover_errors=True)
        tokens = lexer.tokenize()
        if lexer.errors:
            return None, lexer.errors[0]
        parser = Parser(
            tokens, config.features, REPL_SOURCE, recover_errors=True
        )
        program = parser.parse()
        if parser.errors:
            return None, parser.errors[0]
        return program, None
    except (LexError, ParseError) as error:
        return None, error


def _type_check(source: str, config: XConfig, first_line: int) -> list[TypeCheckError]:
    """Check the whole session, reporting only diagnostics from the new entry."""
    if not config.enabled("type_checker"):
        return []
    program, error = _parse(source, config)
    if program is None:
        return []
    errors = TypeChecker().check(program, source_name=REPL_SOURCE, config=config)
    return [
        error
        for error in errors
        if error.line is None or error.line > first_line
    ]


def _is_incomplete(source: str, error: Exception | None) -> bool:
    """Return True when *source* looks unfinished rather than simply invalid.

    Open brackets, strings and comments always mean "keep reading"; once the
    delimiters balance, only a diagnostic that points at end-of-input counts as
    unfinished, so real typos are reported instead of swallowing the next line.
    """
    if _scan_delimiters(source):
        return True
    token = getattr(error, "token", None)
    return token is not None and getattr(token, "kind", None) == "EOF"


def _scan_delimiters(source: str) -> str:
    """Return the construct left open at the end of *source*, or ``""``."""
    depth = 0
    quote: str | None = None
    escaped = False
    block_comment = False
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        next_char = source[index + 1] if index + 1 < length else ""
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if char == "/" and next_char == "/":
            newline = source.find("\n", index)
            index = length if newline == -1 else newline
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in "\"'`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        index += 1
    if block_comment:
        return "comment"
    if quote is not None:
        return "string"
    if depth > 0:
        return "brackets"
    return ""


def _exit_code(stop: SystemExit) -> int:
    code = stop.code
    if code is None:
        return 0
    if isinstance(code, bool) or not isinstance(code, (int, float)):
        return 1
    code = int(code)
    if 0 <= code <= 255:
        return code
    return 1


def _drain_warnings(
    interpreter: Interpreter, error_output: Callable[[str], None]
) -> None:
    for warning in interpreter.warnings:
        error_output(f"warning: {warning.message}")
    interpreter.warnings.clear()


def _report(
    error: Any,
    error_output: Callable[[str], None],
    *,
    source: str | None = None,
    line_offset: int = 0,
) -> None:
    """Render one diagnostic the way ``x run`` does, minus the file path.

    ``line_offset`` translates session-wide line numbers (the type checker sees
    the whole history) back onto the entry the user just typed.
    """
    message = getattr(error, "message", None) or str(error)
    line = getattr(error, "line", None)
    column = getattr(error, "column", None)
    error_output(f"error: {message}")
    relative_line = None
    if line:
        relative_line = line - line_offset if line > line_offset else line
        error_output(f" --> {REPL_SOURCE}:{relative_line}:{column or 1}")
    if source is not None and relative_line is not None:
        lines = source.splitlines()
        if 1 <= relative_line <= len(lines):
            text = lines[relative_line - 1]
            gutter = str(relative_line)
            error_output(f"{'':>{len(gutter)}} |")
            error_output(f"{gutter} | {text}")
            caret = " " * max((column or 1) - 1, 0) + "^"
            error_output(f"{'':>{len(gutter)}} | {caret}")
    for note in getattr(error, "notes", None) or ():
        error_output(f"  = note: {note}")
    for hint in getattr(error, "helps", None) or ():
        error_output(f"  = help: {hint}")
