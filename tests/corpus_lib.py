"""Shared executor for the regression corpus in ``tests/corpus_data.py``.

Every row of the generated ``ROWS`` list is executed through the real X
pipeline:

* ``run``     — lex, parse, type-check and interpret.  ``expected_stdout`` and
                ``expected_exit`` are ALWAYS asserted: an empty
                ``expected_stdout`` means "the program prints nothing" and an
                empty ``expected_exit`` means "main returned no exit code".
* ``check``   — lex, parse and type-check only; the program must be clean and
                produce no output.
* ``error``   — same pipeline as ``run``; ``expected_error`` must be a
                non-empty substring of the failure text (not a regular
                expression).  ``expected_stdout`` is only asserted when it is
                non-empty.  ``phase`` (lex | parse | load | type | runtime)
                is metadata recorded at generation time.
* ``format``  — ``format_source`` output must equal ``expected_stdout``
                (always asserted), and formatting must be idempotent.

Recorded expectations never embed absolute paths or memory addresses, so the
corpus is portable across machines.

Regenerate ``corpus_data.py`` with ``generate_corpus.py``; run it with
``test_corpus.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xlang.config import XConfig
from xlang.formatter import format_source
from xlang.lexer import LexError
from xlang.module_loader import ModuleLoader
from xlang.parser import ParseError
from xlang.runtime import Interpreter

COLUMNS = (
    "id",
    "kind",
    "phase",
    "category",
    "name",
    "source",
    "expected_stdout",
    "expected_error",
    "expected_exit",
    "notes",
)


@dataclass
class CaseResult:
    """Outcome of executing one corpus row."""

    stdout: str = ""
    error: str = ""
    exit_code: int | None = None


def error_text(error: BaseException) -> str:
    """Render *error* the way corpus expectations match against it."""
    message = getattr(error, "message", None)
    if isinstance(message, str) and message:
        return message
    return str(error)


def _scrub(text: str, workdir: Path) -> str:
    """Strip *workdir* from *text* so recorded expectations are portable."""
    root = str(workdir)
    return text.replace(root + "/", "").replace(root, "<workdir>")


def _exit_code(stop: SystemExit) -> int | None:
    code = stop.code
    if isinstance(code, bool) or not isinstance(code, (int, float)):
        return None
    return int(code)


def execute_case(kind: str, source: str, workdir: Path) -> CaseResult:
    """Execute one corpus row of *kind* inside *workdir* and report the outcome."""

    def failure(error: BaseException) -> CaseResult:
        return CaseResult(error=_scrub(error_text(error), workdir))

    if kind == "format":
        try:
            return CaseResult(stdout=format_source(source))
        except (LexError, ParseError) as error:
            return failure(error)

    entry = workdir / "main.x"
    entry.write_text(source, encoding="utf-8")
    try:
        program = ModuleLoader(workdir).load_program(entry)
    except (LexError, ParseError) as error:
        return failure(error)
    except Exception as error:  # noqa: BLE001 - import failures are outcomes too
        return CaseResult(error=_scrub(error_text(error), workdir))

    if kind == "check":
        from xlang.typecheck import TypeChecker

        errors = TypeChecker().check(program, source_name=str(entry))
        if errors:
            return failure(errors[0])
        return CaseResult()

    output: list[str] = []
    try:
        result = Interpreter([], output.append, config=XConfig()).interpret(program)
    except SystemExit as stop:
        return CaseResult(stdout=_scrub("\n".join(output), workdir), exit_code=_exit_code(stop))
    except Exception as error:  # noqa: BLE001 - the corpus records every failure
        return CaseResult(stdout=_scrub("\n".join(output), workdir), error=_scrub(error_text(error), workdir))
    exit_code = (
        result
        if isinstance(result, int) and not isinstance(result, bool)
        else None
    )
    return CaseResult(stdout=_scrub("\n".join(output), workdir), exit_code=exit_code)


def write_module(path: Path, rows: list[dict[str, str]]) -> None:
    """Write the generated ``corpus_data.py`` module holding *rows*."""
    lines = [
        '"""Generated regression corpus - do not edit by hand.',
        "",
        "Regenerate with ``python tests/generate_corpus.py`` (add ``--sample N``",
        "to preview rows, ``--no-verify`` to write despite authored-expectation",
        "mismatches).  ``tests/test_corpus.py`` executes every row through the",
        "real X pipeline; a diff here after regeneration means the corpus",
        "builders or the interpreter changed.",
        '"""',
        "",
        "ROWS = [",
    ]
    for row in rows:
        lines.append("    {")
        for column in COLUMNS:
            lines.append(f"        {column!r}: {row.get(column, '')!r},")
        lines.append("    },")
    lines.append("]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
