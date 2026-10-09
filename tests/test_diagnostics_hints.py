"""Rustc-style diagnostic rendering: gutters, notes, helps, colour, CLI.

The suite drives :func:`xlang.diagnostics.render_diagnostic` and
:func:`xlang.diagnostics.render_warning` directly with synthetic
:class:`xlang.typecheck.TypeCheckError` objects, calls the CLI's
``_report_source_errors`` for the multi-error path, and runs
``python -m xlang check`` / ``run`` end to end on a temporary fixture.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from xlang.cli import _report_source_errors
from xlang.diagnostics import (
    BLUE,
    BOLD,
    CYAN,
    GREEN,
    RED,
    RESET,
    SourceWarning,
    render_diagnostic,
    render_warning,
)
from xlang.typecheck import TypeCheckError, TypeCheckFailure

REPO_ROOT = Path(__file__).resolve().parent.parent

CHECKER_NOTE = "expected `integer`, found `string`"


class TtyStream(io.StringIO):
    """A stream that claims to be a terminal, for ``color_mode="auto"``."""

    def isatty(self) -> bool:
        return True


def render(
    error: BaseException,
    source: str | None = None,
    source_name: str | None = None,
    color: str = "never",
    show_context: bool = True,
    stream: io.StringIO | None = None,
) -> str:
    name = source_name if source_name is not None else getattr(error, "source_name", None)
    return render_diagnostic(
        error, source, name or "program.x", color, stream, show_context
    )


def padded_source(total: int, target_line: int, text: str) -> str:
    """A source file of *total* lines whose *target_line* holds *text*."""
    lines = [f"    let filler{index} = {index};" for index in range(1, total + 1)]
    lines[target_line - 1] = text
    return "\n".join(lines) + "\n"


class SingleDigitLayoutTests(unittest.TestCase):
    def test_full_block_is_byte_exact(self):
        error = TypeCheckError(
            "Cannot assign 'string' to 'count'",
            source_name="program.x",
            line=2,
            column=5,
            notes=[CHECKER_NOTE],
            helps=["assign a number instead"],
        )
        source = "function main() {\n    return 0;\n}\n"
        self.assertEqual(
            render(error, source),
            "error: Cannot assign 'string' to 'count'\n"
            " --> program.x:2:5\n"
            "  |\n"
            "2 |     return 0;\n"
            "  |     ^ Cannot assign 'string' to 'count'\n"
            f"  = note: {CHECKER_NOTE}\n"
            "  = help: assign a number instead"
        )

    def test_block_without_notes_ends_after_the_caret(self):
        error = TypeCheckError("boom", source_name="program.x", line=1, column=1)
        self.assertEqual(
            render(error, "let x = 1;\n"),
            "error: boom\n"
            " --> program.x:1:1\n"
            "  |\n"
            "1 | let x = 1;\n"
            "  | ^ boom"
        )

    def test_multiline_message_stays_inside_the_gutter(self):
        error = TypeCheckError(
            "first part\nsecond part", source_name="program.x", line=1, column=1
        )
        rendered = render(error, "let x = 1;\n")
        self.assertEqual(
            rendered.splitlines(),
            [
                "error: first part",
                "       second part",
                " --> program.x:1:1",
                "  |",
                "1 | let x = 1;",
                "  | ^ first part",
                "  |   second part",
            ],
        )

    def test_error_without_line_number_is_flush_left(self):
        error = TypeCheckError(
            "cannot read 'x.toml'",
            source_name="x.toml",
            notes=["check the path"],
            helps=["create the file"],
        )
        self.assertEqual(
            render(error, None),
            "error: cannot read 'x.toml'\n"
            "--> x.toml\n"
            "= note: check the path\n"
            "= help: create the file"
        )

    def test_error_without_column_omits_the_column(self):
        error = TypeCheckError("boom", source_name="program.x", line=4)
        rendered = render(error, "a\nb\nc\nd\n")
        self.assertIn("--> program.x:4\n", rendered)
        self.assertNotIn(":4:", rendered)


class WideGutterTests(unittest.TestCase):
    def check_alignment(self, target_line: int) -> None:
        width = len(str(target_line))
        column = 5
        error = TypeCheckError(
            "type mismatch",
            source_name="big.x",
            line=target_line,
            column=column,
            notes=[CHECKER_NOTE],
            helps=["use a number"],
        )
        source = padded_source(target_line + 2, target_line, "    let value = 0;")
        lines = render(error, source).splitlines()
        self.assertEqual(len(lines), 7)
        arrow, bar, source_row, caret, note, help_line = lines[1:]
        self.assertEqual(lines[0], "error: type mismatch")
        self.assertEqual(arrow.index("-->"), width)
        self.assertEqual(bar, " " * (width + 1) + "|")
        self.assertEqual(source_row.split("|", 1)[0].rstrip(), str(target_line))
        self.assertEqual(source_row.index("|"), width + 1)
        self.assertEqual(note.index("= note:"), width + 1)
        self.assertEqual(help_line.index("= help:"), width + 1)
        self.assertEqual(arrow.index("-->") + 1, bar.index("|"))
        self.assertEqual(caret.index("^"), bar.index("|") + 2 + (column - 1))

    def test_line_100_keeps_every_marker_on_the_same_column(self):
        self.check_alignment(100)

    def test_line_1000_keeps_every_marker_on_the_same_column(self):
        self.check_alignment(1000)

    def test_notes_follow_the_gutter_when_the_context_is_hidden(self):
        error = TypeCheckError(
            "type mismatch",
            source_name="big.x",
            line=100,
            column=5,
            notes=[CHECKER_NOTE],
        )
        lines = render(
            error,
            padded_source(102, 100, "    let value = 0;"),
            show_context=False,
        ).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1].index("-->"), 3)
        self.assertEqual(lines[2].index("= note:"), 4)
        self.assertNotIn("|", "\n".join(lines))

    def test_notes_survive_a_missing_source_at_a_wide_line_number(self):
        error = TypeCheckError(
            "type mismatch",
            source_name="big.x",
            line=100,
            column=5,
            helps=["use a number"],
        )
        lines = render(error, None).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1], "   --> big.x:100:5")
        self.assertEqual(lines[2], "    = help: use a number")

    def test_line_past_the_end_of_the_source_keeps_the_hints(self):
        error = TypeCheckError(
            "type mismatch", source_name="small.x", line=5000, column=5,
            notes=[CHECKER_NOTE],
        )
        lines = render(error, "let a = 1;\nlet b = 2;\n").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1], "    --> small.x:5000:5")
        self.assertEqual(lines[2], f"     = note: {CHECKER_NOTE}")


class HintTests(unittest.TestCase):
    def test_multiline_note_and_help_are_indented_under_the_marker(self):
        error = TypeCheckError(
            "type mismatch",
            source_name="program.x",
            line=1,
            column=1,
            notes=["first line\nsecond line\n\nlast line"],
            helps=["replace the literal"],
        )
        rendered = render(error, "let x = 1;\n")
        self.assertEqual(
            rendered.splitlines()[-5:-1],
            [
                "  = note: first line",
                "    second line",
                "",
                "    last line",
            ],
        )
        self.assertEqual(rendered.splitlines()[-1], "  = help: replace the literal")
        for line in rendered.splitlines():
            self.assertEqual(line, line.rstrip())

    def test_empty_note_and_help_print_the_marker_only(self):
        error = TypeCheckError(
            "type mismatch",
            source_name="program.x",
            line=1,
            column=1,
            notes=[""],
            helps=[""],
        )
        rendered = render(error, "let x = 1;\n")
        self.assertEqual(rendered.splitlines()[-2:], ["  = note:", "  = help:"])
        for line in rendered.splitlines():
            self.assertEqual(line, line.rstrip())

    def test_ansi_already_inside_a_note_is_passed_through(self):
        note = "\x1b[31mexpected integer\x1b[0m"
        error = TypeCheckError(
            "type mismatch",
            source_name="program.x",
            line=1,
            column=1,
            notes=[note],
        )
        colored = render(error, "let x = 1;\n", color="always")
        self.assertIn(note, colored)
        self.assertNotIn("\x1b[36m\x1b[31m", colored)
        self.assertIn(f"{CYAN}{BOLD}= note:{RESET}", colored)
        plain = render(error, "let x = 1;\n", color="never")
        self.assertIn(note, plain)

    def test_notes_render_without_a_snippet_and_without_a_line(self):
        error = TypeCheckError(
            "type mismatch", source_name="program.x", notes=["only a name"]
        )
        self.assertEqual(
            render(error, None),
            "error: type mismatch\n"
            "--> program.x\n"
            "= note: only a name"
        )

    def test_notes_render_when_the_source_is_unknown(self):
        error = TypeCheckError(
            "type mismatch", source_name="program.x", line=2, column=1,
            notes=["only a name"],
        )
        lines = render(error, None).splitlines()
        self.assertEqual(lines[1], " --> program.x:2:1")
        self.assertEqual(lines[2], "  = note: only a name")


class WarningTests(unittest.TestCase):
    SOURCE = "function main() {\n    let x = 1;\n}\n"

    def test_warning_output_is_byte_identical(self):
        self.assertEqual(
            render_warning(
                "main() is never called",
                self.SOURCE,
                "runner.x",
                1,
                10,
                "never",
            ),
            "warning: main() is never called\n"
            " --> runner.x:1:10\n"
            "  |\n"
            "1 | function main() {\n"
            "  |          ^ main() is never called"
        )

    def test_warning_without_a_line_number_is_byte_identical(self):
        self.assertEqual(
            render_warning("unused import", None, "runner.x", None, None, "never"),
            "warning: unused import\n"
            "--> runner.x",
        )

    def test_warning_without_a_source_keeps_the_location_only(self):
        self.assertEqual(
            render_warning("unused import", None, "runner.x", 3, 1, "never"),
            "warning: unused import\n"
            " --> runner.x:3:1",
        )

    def test_warning_accepts_notes_and_helps(self):
        rendered = render_warning(
            "deprecated API",
            self.SOURCE,
            "runner.x",
            2,
            5,
            "never",
            notes=["use `print` instead"],
            helps=["replace the call"],
        )
        self.assertEqual(
            rendered.splitlines()[-2:],
            ["  = note: use `print` instead", "  = help: replace the call"],
        )

    def test_warning_without_notes_matches_the_notes_free_rendering(self):
        with_notes = render_warning(
            "deprecated API", self.SOURCE, "runner.x", 2, 5, "never", notes=[]
        )
        self.assertEqual(
            with_notes,
            render_warning("deprecated API", self.SOURCE, "runner.x", 2, 5, "never"),
        )

    def test_source_warning_defaults_to_no_hints(self):
        warning = SourceWarning("careful", "runner.x")
        self.assertEqual(warning.notes, ())
        self.assertEqual(warning.helps, ())
        self.assertIsNone(warning.line)
        self.assertIsNone(warning.column)


class ColorTests(unittest.TestCase):
    def make_error(self) -> TypeCheckError:
        return TypeCheckError(
            "type mismatch",
            source_name="program.x",
            line=2,
            column=5,
            notes=[CHECKER_NOTE],
            helps=["assign a number instead"],
        )

    def test_color_always_marks_every_part_of_the_block(self):
        rendered = render(
            self.make_error(), "function main() {\n    return 0;\n}\n", color="always"
        )
        self.assertIn(f"{RED}{BOLD}error{RESET}: type mismatch", rendered)
        self.assertIn(f"{BLUE}{BOLD}-->{RESET} program.x:2:5", rendered)
        self.assertIn(f"{BLUE}{BOLD}|{RESET}\n", rendered)
        self.assertIn(f"{CYAN}{BOLD}2{RESET} {BLUE}{BOLD}|{RESET}", rendered)
        self.assertIn(f"{RED}{BOLD}^{RESET}", rendered)
        self.assertIn(
            f"{CYAN}{BOLD}= note:{RESET} {CYAN}{CHECKER_NOTE}{RESET}", rendered
        )
        self.assertIn(
            f"{GREEN}{BOLD}= help:{RESET} {GREEN}assign a number instead{RESET}",
            rendered,
        )

    def test_color_never_emits_pure_ascii(self):
        rendered = render(
            self.make_error(), "function main() {\n    return 0;\n}\n", color="never"
        )
        self.assertNotIn("\x1b", rendered)
        self.assertIn("= note:", rendered)

    def test_auto_color_follows_the_stream_and_no_color(self):
        source = "function main() {\n    return 0;\n}\n"
        with mock.patch.dict(os.environ):
            os.environ.pop("NO_COLOR", None)
            on_tty = render(
                self.make_error(), source, color="auto", stream=TtyStream()
            )
            self.assertIn("\x1b[31m", on_tty)
            os.environ["NO_COLOR"] = "1"
            suppressed = render(
                self.make_error(), source, color="auto", stream=TtyStream()
            )
            self.assertNotIn("\x1b", suppressed)
            forced = render(self.make_error(), source, color="always")
            self.assertIn("\x1b[31m", forced)
            pipe = render(self.make_error(), source, color="auto", stream=io.StringIO())
            self.assertNotIn("\x1b", pipe)


class RobustnessTests(unittest.TestCase):
    def test_tab_in_the_source_keeps_the_caret_aligned(self):
        source = "function main() {\n\tlet value = 1;\n}\n"
        error = TypeCheckError("bad", source_name="tab.x", line=2, column=2)
        lines = render(error, source).splitlines()
        source_row, caret_row = lines[3], lines[4]
        self.assertNotIn("\t", source_row)
        self.assertEqual(source_row.index("let"), caret_row.index("^"))

    def test_non_ascii_source_keeps_the_caret_aligned(self):
        source = 'let string label = "café";\n'
        error = TypeCheckError("bad", source_name="uni.x", line=1, column=20)
        lines = render(error, source).splitlines()
        self.assertEqual(lines[3].index('"café"'), lines[4].index("^"))
        self.assertIn("café", lines[3])

    def test_tab_and_non_ascii_inside_the_message_do_not_crash(self):
        error = TypeCheckError(
            "mismatch\tfor 'café' → 数值",
            source_name="program.x",
            line=1,
            column=5,
            notes=["note\twith a tab", "unicode: héllo"],
        )
        rendered = render(error, "let x = 1;\n")
        self.assertIn("mismatch\tfor 'café' → 数值", rendered)
        self.assertIn("note\twith a tab", rendered)
        self.assertIn("unicode: héllo", rendered)
        self.assertIn("  |     ^", rendered)

    def test_unusable_positions_degrade_to_a_header_only_block(self):
        for line, column in ((0, 0), (None, None), ("n/a", "n/a"), (-3, -3)):
            error = TypeCheckError(
                "boom", source_name="program.x", line=line, column=column
            )
            rendered = render(error, "let x = 1;\n")
            self.assertEqual(
                rendered, "error: boom\n--> program.x", msg=f"{line} {column}"
            )

    def test_unusable_column_still_shows_the_snippet_without_a_caret(self):
        error = TypeCheckError(
            "boom", source_name="program.x", line=1, column="not-a-column"
        )
        lines = render(error, "let x = 1;\n").splitlines()
        self.assertEqual(
            lines,
            ["error: boom", " --> program.x:1", "  |", "1 | let x = 1;"],
        )

    def test_empty_message_leaves_no_trailing_space(self):
        error = TypeCheckError("", source_name="program.x", line=1, column=1)
        for line in render(error, "let x = 1;\n").splitlines():
            self.assertEqual(line, line.rstrip())


class ReportSourceErrorsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "program.x"
        self.source = (
            "function main() {\n"
            "    let integer a = 1;\n"
            "    let integer b = 2;\n"
            "    let integer c = 3;\n"
            "}\n"
        )
        self.path.write_text(self.source, encoding="utf-8")

    def test_failure_renders_independent_blocks_in_source_order(self):
        errors = [
            TypeCheckError(
                "first problem",
                source_name=str(self.path),
                line=4,
                column=5,
                notes=["note for first"],
            ),
            TypeCheckError(
                "second problem",
                source_name=str(self.path),
                line=2,
                column=5,
                helps=["help for second"],
            ),
            TypeCheckError(
                "third problem", source_name=str(self.path), line=3, column=5
            ),
        ]
        failure = TypeCheckFailure(errors)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            return_code = _report_source_errors(
                failure.errors,
                {self.path.resolve(): self.source},
                self.path,
                "never",
                label="type error",
            )
        text = stderr.getvalue()
        self.assertEqual(return_code, 1)
        self.assertEqual(text.count("error: "), 3)
        self.assertEqual(text.count("-->"), 3)
        self.assertEqual(text.count("^"), 3)
        self.assertEqual(text.count("= note:"), 1)
        self.assertEqual(text.count("= help:"), 1)
        self.assertIn("x: found 3 type error(s)", text)
        self.assertIn("2 |     let integer a = 1;", text)
        self.assertIn("3 |     let integer b = 2;", text)
        self.assertIn("4 |     let integer c = 3;", text)
        self.assertLess(text.index("second problem"), text.index("third problem"))
        self.assertLess(text.index("third problem"), text.index("first problem"))
        self.assertIn("= note: note for first", text)
        self.assertIn("= help: help for second", text)

    def test_failure_exposes_the_first_diagnostic(self):
        errors = [
            TypeCheckError(
                "first problem", source_name=str(self.path), line=4, column=5
            ),
            TypeCheckError(
                "second problem", source_name=str(self.path), line=2, column=5
            ),
        ]
        failure = TypeCheckFailure(errors)
        self.assertEqual(failure.errors, errors)
        self.assertEqual(failure.message, "first problem")
        self.assertEqual(failure.line, 4)
        self.assertEqual(failure.column, 5)
        self.assertEqual(failure.source_name, str(self.path))


class CliEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = TemporaryDirectory()
        directory = Path(cls.temporary_directory.name)
        cls.fixture = directory / "types.x"
        cls.fixture.write_text(
            "integer function main() {\n"
            '    let integer count = "not a number";\n'
            "    let string label = 5;\n"
            "    print(count);\n"
            "    print(label);\n"
            "    return 0;\n"
            "}\n",
            encoding="utf-8",
        )
        cls.wide_fixture = directory / "wide.x"
        filler = "".join(f"// filler line {index}\n" for index in range(1, 99))
        cls.wide_fixture.write_text(
            filler
            + "integer function main() {\n"
            + '    let integer count = "not a number";\n'
            + "    print(count);\n"
            + "    return 0;\n"
            + "}\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def run_x(self, *arguments: str, env: dict[str, str] | None = None):
        environment = dict(os.environ)
        environment.pop("NO_COLOR", None)
        if env:
            environment.update(env)
        return subprocess.run(
            [sys.executable, "-m", "xlang", *arguments],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=environment,
            timeout=120,
        )

    def test_check_and_run_render_type_errors_identically(self):
        checked = self.run_x("--no-config", "--color", "never", "check", str(self.fixture))
        ran = self.run_x("--no-config", "--color", "never", "run", str(self.fixture))
        self.assertEqual(checked.returncode, 1, checked.stderr)
        self.assertEqual(ran.returncode, 1, ran.stderr)
        self.assertEqual(checked.stderr, ran.stderr)
        self.assertEqual(checked.stdout, "")
        self.assertEqual(ran.stdout, "")
        blocks = checked.stderr.count("error: ")
        self.assertGreaterEqual(blocks, 2)
        self.assertEqual(checked.stderr.count("-->"), blocks)
        # One caret line per block; the marker itself may be a run of "^"
        # covering the whole offending span.
        caret_lines = [
            line
            for line in checked.stderr.splitlines()
            if "^" in line.split("|", 1)[-1]
        ]
        self.assertEqual(len(caret_lines), blocks)
        summary = re.search(r"x: found (\d+) type error\(s\)", checked.stderr)
        self.assertIsNotNone(summary, checked.stderr)
        self.assertEqual(int(summary.group(1)), blocks)
        self.assertIn('2 |     let integer count = "not a number";', checked.stderr)
        self.assertIn("3 |     let string label = 5;", checked.stderr)
        for hint in self.hint_lines(checked.stderr):
            self.assertEqual(hint.index("="), 2, hint)

    def test_color_flags_control_ansi_escapes(self):
        colored = self.run_x(
            "--no-config", "--color", "always", "check", str(self.fixture)
        )
        self.assertEqual(colored.returncode, 1, colored.stderr)
        self.assertIn("\x1b[31m", colored.stderr)
        self.assertIn("\x1b[36m", colored.stderr)
        self.assertIn("\x1b[34m", colored.stderr)
        plain = self.run_x(
            "--no-config", "--color", "never", "check", str(self.fixture)
        )
        self.assertNotIn("\x1b", plain.stderr)
        env_plain = self.run_x(
            "--no-config", "check", str(self.fixture), env={"NO_COLOR": "1"}
        )
        self.assertNotIn("\x1b", env_plain.stderr)

    @staticmethod
    def hint_lines(text: str) -> list[str]:
        return [
            line
            for line in text.splitlines()
            if line.lstrip().startswith(("= note:", "= help:"))
        ]

    def test_wide_line_numbers_stay_aligned_end_to_end(self):
        result = self.run_x(
            "--no-config", "--color", "never", "check", str(self.wide_fixture)
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        lines = [line for line in result.stderr.splitlines() if line]
        arrow = next(line for line in lines if "-->" in line)
        bar = next(line for line in lines if line.endswith("|"))
        source_row = next(line for line in lines if line.startswith("100 |"))
        caret = next(line for line in lines if "^" in line)
        self.assertEqual(arrow.index("-->"), 3)
        self.assertEqual(bar.index("|"), 4)
        self.assertEqual(source_row.index("|"), 4)
        self.assertEqual(arrow.index("-->") + 1, bar.index("|"))
        column = int(arrow.rsplit(":", 1)[1])
        self.assertEqual(caret.index("^"), bar.index("|") + 2 + (column - 1))
        hints = self.hint_lines(result.stderr)
        self.assertTrue(hints, result.stderr)
        for hint in hints:
            self.assertEqual(hint.index("="), 4, hint)


if __name__ == "__main__":
    unittest.main()
