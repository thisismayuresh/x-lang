"""Shared executor for the CSV regression corpus in this folder.

Every row of ``run_tests.csv`` / ``check_tests.csv`` / ``error_tests.csv`` /
``format_tests.csv`` is executed through the real X pipeline:

* ``run``     — lex, parse, type-check and interpret.  ``expected_stdout`` and
                ``expected_exit`` are ALWAYS asserted: an empty
                ``expected_stdout`` cell means "the program prints nothing"
                and an empty ``expected_exit`` cell means "main returned no
                exit code".
* ``check``   — lex, parse and type-check only; the program must be clean and
                produce no output.
* ``error``   — same pipeline as ``run``; ``expected_error`` must be a
                non-empty substring of the failure text (not a regular
                expression).  ``expected_stdout`` is only asserted when its
                cell is non-empty.  ``phase`` (lex | parse | load | type |
                runtime) is metadata recorded at generation time.
* ``format``  — ``format_source`` output must equal ``expected_stdout``
                (always asserted), and formatting must be idempotent.

Multi-line values are plain CSV fields (RFC 4180 quoting).  Recorded
expectations never embed absolute paths or memory addresses, so the CSVs are
portable across machines.

Regenerate the CSVs with ``generate_corpus.py``; run them with
``test_corpus.py``.
"""

from __future__ import annotations

import csv
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

CSV_NAMES = (
    "run_tests.csv",
    "check_tests.csv",
    "error_tests.csv",
    "format_tests.csv",
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


def load_rows(csv_dir: Path) -> list[dict[str, str]]:
    """Load every corpus CSV in *csv_dir*, keeping file order and adding ``file``."""
    rows: list[dict[str, str]] = []
    for name in CSV_NAMES:
        path = csv_dir / name
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                row["file"] = name
                rows.append(row)
    return rows


def write_rows(csv_dir: Path, name: str, rows: list[dict[str, str]]) -> None:
    """Write one corpus CSV with the canonical column order."""
    path = csv_dir / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})
