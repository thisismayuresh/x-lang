#!/usr/bin/env python3
"""Run the regression corpus stored in tests/corpus_data.py.

    .venv/bin/python tests/test_corpus.py             # whole corpus
    .venv/bin/python tests/test_corpus.py -v          # verbose unittest
    X_CORPUS_FILTER=strings .venv/bin/python tests/test_corpus.py

Every row of the generated corpus is executed through the real X pipeline and
checked with the per-kind rules below (also documented in corpus_lib.py):

* ``run``     - lex, parse, type-check and interpret.  ``expected_stdout`` is
                ALWAYS asserted (an empty cell means "the program prints
                nothing") and ``expected_exit`` is ALWAYS asserted (an empty
                cell means "main returned no exit code").
* ``check``   - lex, parse and type-check only; the program must be clean and
                produce no output.
* ``error``   - same pipeline as ``run``; ``expected_error`` must be a
                non-empty substring of the failure text (never a regular
                expression).  ``expected_stdout`` is only asserted when its
                cell is non-empty.  ``phase`` is metadata (lex | parse | load
                | type | runtime) and is not re-derived at test time.
* ``format``  - ``format_source`` output must equal ``expected_stdout``
                (always asserted), and formatting must be idempotent:
                format(format(source)) == format(source).

``X_CORPUS_FILTER`` keeps only rows whose id, kind, category or name contains
the given substring.  Regenerate the corpus with ``generate_corpus.py``.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for _extra in (str(HERE), str(ROOT)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from corpus_data import ROWS  # noqa: E402
from corpus_lib import execute_case  # noqa: E402

FILTER = os.environ.get("X_CORPUS_FILTER", "")


class CorpusTest(unittest.TestCase):
    """Executes every corpus row; each row runs as its own subTest."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = list(ROWS)
        if FILTER:
            cls.rows = [
                row
                for row in cls.rows
                if FILTER in row["id"]
                or FILTER in row["kind"]
                or FILTER in row["category"]
                or FILTER in row["name"]
            ]
        if not cls.rows:
            raise unittest.SkipTest(f"no corpus rows match filter {FILTER!r}")
        cls._tmp = tempfile.TemporaryDirectory(prefix="x-corpus-")
        cls.workdir = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _message(self, row: dict[str, str], detail: str) -> str:
        return (
            f"[{row['id']} {row['kind']}] {row['category']}/{row['name']}: "
            f"{detail}"
        )

    def _check_row(self, row: dict[str, str]) -> None:
        kind = row["kind"]
        result = execute_case(kind, row["source"], self.workdir)
        if kind == "run":
            self.assertEqual(
                result.error, "",
                self._message(row, f"unexpected error: {result.error}"),
            )
            self.assertEqual(
                result.stdout, row["expected_stdout"],
                self._message(row, "stdout mismatch"),
            )
            expected_exit = int(row["expected_exit"]) if row["expected_exit"] else None
            self.assertEqual(
                result.exit_code, expected_exit,
                self._message(row, "exit code mismatch"),
            )
        elif kind == "check":
            self.assertEqual(
                result.error, "",
                self._message(row, f"expected clean program, got: {result.error}"),
            )
            self.assertEqual(
                result.stdout, "",
                self._message(row, f"check produced output: {result.stdout!r}"),
            )
        elif kind == "error":
            self.assertTrue(
                row["expected_error"],
                self._message(row, "error row has an empty expected_error"),
            )
            self.assertTrue(
                result.error,
                self._message(row, "expected a failure but the pipeline succeeded"),
            )
            self.assertIn(
                row["expected_error"], result.error,
                self._message(
                    row,
                    f"error mismatch\nexpected substring: {row['expected_error']!r}\n"
                    f"actual error: {result.error!r}",
                ),
            )
            if row["expected_stdout"]:
                self.assertEqual(
                    result.stdout, row["expected_stdout"],
                    self._message(row, "partial stdout mismatch"),
                )
        elif kind == "format":
            self.assertEqual(
                result.error, "",
                self._message(row, f"format_source failed: {result.error}"),
            )
            self.assertEqual(
                result.stdout, row["expected_stdout"],
                self._message(row, "formatted output mismatch"),
            )
            again = execute_case("format", result.stdout, self.workdir)
            self.assertEqual(
                again.stdout, result.stdout,
                self._message(row, "formatter is not idempotent"),
            )
        else:
            self.fail(self._message(row, f"unknown row kind {kind!r}"))

    def test_corpus_rows(self) -> None:
        for row in self.rows:
            with self.subTest(id=row["id"], kind=row["kind"], name=row["name"]):
                self._check_row(row)


if __name__ == "__main__":
    unittest.main()
