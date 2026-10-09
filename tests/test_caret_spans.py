"""Caret-span diagnostics: ``^^^`` underlines the offending expression."""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.config import XConfig
from xlang.diagnostics import SourceWarning, render_diagnostic, render_warning
from xlang.lexer import Lexer
from xlang.module_loader import ModuleLoader
from xlang.parser import Parser, ParseError, token_end_column
from xlang.runtime import Interpreter, RuntimeErrorX
from xlang.typecheck.errors import TypeCheckError

REPO_ROOT = Path(__file__).resolve().parent.parent

CARET_LINE = re.compile(r"^ *\| *(\^+)(?: .*)?$")
SOURCE_LINE = re.compile(r"^ *(\d+) \| (.*)$")


def caret_spans(text):
    """Return ``[(line_number, start_column, covered_text)]`` for a render."""
    spans = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if index == 0 or not CARET_LINE.match(line):
            continue
        source = SOURCE_LINE.match(lines[index - 1])
        if source is None:
            continue
        carets = CARET_LINE.match(line).group(1)
        gutter = line.index("|") + 2
        start = line.index("^")
        column = start - gutter
        spans.append((int(source.group(1)), column, source.group(2)[column:column + len(carets)]))
    return spans


class RenderSpanTests(unittest.TestCase):
    @staticmethod
    def error(line, column, end_line=None, end_column=None, message="boom"):
        error = RuntimeErrorX(message, "RuntimeException")
        error.line = line
        error.column = column
        error.end_line = end_line
        error.end_column = end_column
        return error

    def render(self, error, source, source_name="demo.x"):
        return render_diagnostic(error, source, source_name, "never")

    def test_carets_cover_the_reported_span(self):
        error = self.error(3, 11, 3, 18)
        source = "line one\nline two\n  let x = thing[0];\n"
        spans = caret_spans(self.render(error, source))
        self.assertEqual(spans, [(3, 10, "thing[0]")])

    def test_single_caret_when_no_end_position(self):
        error = self.error(3, 11)
        source = "line one\nline two\n  let x = thing[0];\n"
        spans = caret_spans(self.render(error, source))
        self.assertEqual(spans, [(3, 10, "t")])

    def test_span_on_another_line_collapses_to_a_caret(self):
        error = self.error(3, 11, 4, 9)
        source = "line one\nline two\n  let x = thing\n;\n"
        spans = caret_spans(self.render(error, source))
        self.assertEqual(spans, [(3, 10, "t")])

    def test_type_error_span_uses_end_positions(self):
        error = TypeCheckError(
            "Cannot assign 'string' to 'count' of type 'integer'",
            line=2,
            column=5,
            end_line=2,
            end_column=31,
            notes=("expected `integer`, found `string`",),
        )
        source = 'function main() {\n    let integer count = "boom";\n}\n'
        rendered = self.render(error, source)
        spans = caret_spans(rendered)
        self.assertEqual(len(spans), 1)
        _, column, covered = spans[0]
        self.assertEqual(column, 4)
        self.assertEqual(covered, 'let integer count = "boom";')
        self.assertIn("= note: ", rendered)

    def test_warning_span_covers_its_range(self):
        source = "line one\n    let x = 1;\n"
        warning = SourceWarning(
            "never used", "demo.x", line=2, column=5, end_line=2, end_column=9
        )
        spans = caret_spans(
            render_warning(
                warning.message,
                source,
                warning.source_name,
                warning.line,
                warning.column,
                "never",
                end_line=warning.end_line,
                end_column=warning.end_column,
            )
        )
        self.assertEqual(spans, [(2, 4, "let x")])

    def test_warning_without_range_keeps_a_single_caret(self):
        source = "line one\n    let x = 1;\n"
        warning = SourceWarning("never used", "demo.x", line=2, column=5)
        spans = caret_spans(
            render_warning(
                warning.message,
                source,
                warning.source_name,
                warning.line,
                warning.column,
                "never",
            )
        )
        self.assertEqual(spans, [(2, 4, "l")])


def parse(source, source_name="demo.x"):
    tokens = Lexer(source, source_name).tokenize()
    return Parser(tokens, {}, source_name).parse()


class ParserSpanTests(unittest.TestCase):
    def test_expression_nodes_carry_end_positions(self):
        program = parse("function main() {\n    let x = values[index + 1];\n}\n")
        declaration = program.declarations[0].body[0]
        expression = declaration.initializer
        self.assertEqual(expression.line, 2)
        self.assertEqual(expression.column, 13)
        self.assertEqual(expression.end_line, 2)
        self.assertEqual(expression.end_column, 29)
        self.assertEqual(expression.object.end_column, 18)

    def test_call_and_binary_nodes_carry_end_positions(self):
        program = parse("function main() {\n    total = count(a) + 1;\n}\n")
        statement = program.declarations[0].body[0]
        assignment = statement.expression
        call = assignment.value.left
        self.assertEqual(call.column, 13)
        self.assertEqual(call.end_column, 20)
        self.assertEqual(assignment.value.end_column, 24)

    def test_string_token_end_column_includes_quotes(self):
        tokens = Lexer('let x = "abc";', "demo.x").tokenize()
        string_token = next(token for token in tokens if token.kind == "STRING")
        self.assertEqual(token_end_column(string_token), 13)

    def test_parse_error_marks_the_token_end(self):
        tokens = Lexer("function main() {\n    let x = ;\n}\n", "demo.x").tokenize()
        parser = Parser(tokens, {}, "demo.x")
        with self.assertRaises(ParseError) as caught:
            parser.parse()
        error = caught.exception
        self.assertEqual((error.line, error.column), (2, 13))
        self.assertEqual(error.end_line, 2)
        self.assertEqual(error.end_column, 13)


class InterpreterSpanTests(unittest.TestCase):
    @staticmethod
    def runtime_only_config():
        config = XConfig()
        config.features["type_checker"] = False
        return config

    def run_x(self, source):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            source_file = project_root / "main.x"
            source_file.write_text(source, encoding="utf-8")
            program = ModuleLoader(project_root).load_program(source_file)
            output = []
            Interpreter(
                None,
                output.append,
                config=self.runtime_only_config(),
            ).interpret(program)
        return output

    def failing(self, source):
        with self.assertRaises(RuntimeErrorX) as caught:
            self.run_x(source)
        return caught.exception

    def test_missing_key_error_underlines_the_index_expression(self):
        source = (
            "function main() {\n"
            "    let object<string, integer> freqMap = {};\n"
            '    let string key = "H";\n'
            "    if (freqMap[key]) {\n"
            "        print(1);\n"
            "    }\n"
            "}\n"
        )
        error = self.failing(source)
        self.assertEqual((error.line, error.column), (4, 9))
        self.assertEqual((error.end_line, error.end_column), (4, 20))
        rendered = render_diagnostic(error, source, "main.x", "never")
        self.assertEqual(caret_spans(rendered), [(4, 8, "freqMap[key]")])

    def test_binary_error_underlines_the_expression(self):
        source = 'function main() {\n    let string s = "abc";\n    print(s - 1);\n}\n'
        error = self.failing(source)
        self.assertEqual((error.line, error.column), (3, 11))
        self.assertEqual((error.end_line, error.end_column), (3, 15))
        rendered = render_diagnostic(error, source, "main.x", "never")
        self.assertEqual(caret_spans(rendered), [(3, 10, "s - 1")])

    def test_undefined_name_underlines_the_identifier(self):
        source = "function main() {\n    missingFunction();\n}\n"
        error = self.failing(source)
        self.assertEqual((error.line, error.column), (2, 5))
        self.assertEqual((error.end_line, error.end_column), (2, 19))
        rendered = render_diagnostic(error, source, "main.x", "never")
        self.assertEqual(caret_spans(rendered), [(2, 4, "missingFunction")])


class CliCaretTests(unittest.TestCase):
    frequency_source = (
        "let object<string, integer> freqMap = {};\n"
        'let string userInput = "Hello";\n'
        "for (let char in userInput) {\n"
        "    if (freqMap[char]) {\n"
        "        freqMap[char] = freqMap[char] + 1;\n"
        "    } else {\n"
        "        freqMap[char] = 1;\n"
        "    }\n"
        "}\n"
        "print(freqMap);\n"
    )

    fixed_frequency_source = (
        "let object<string, integer> freqMap = {};\n"
        'let string userInput = "Hello";\n'
        "for (let char in userInput) {\n"
        "    if (char in freqMap) {\n"
        "        freqMap[char] = freqMap[char] + 1;\n"
        "    } else {\n"
        "        freqMap[char] = 1;\n"
        "    }\n"
        "}\n"
        "print(freqMap);\n"
    )

    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = TemporaryDirectory()
        cls.directory = Path(cls.temporary_directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def run_x(self, source):
        source_file = self.directory / "main.x"
        source_file.write_text(source, encoding="utf-8")
        environment = dict(os.environ)
        environment.pop("NO_COLOR", None)
        return subprocess.run(
            [sys.executable, "-m", "xlang", "run", "--no-config", str(source_file)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=environment,
            timeout=120,
        )

    def test_char_frequency_lookup_underlines_the_subscript(self):
        completed = self.run_x(self.frequency_source)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("Cannot access key H", completed.stderr)
        spans = caret_spans(completed.stderr)
        self.assertEqual(len(spans), 1)
        line, _, covered = spans[0]
        self.assertEqual(line, 4)
        self.assertEqual(covered, "freqMap[char]")
        self.assertIn("^^^^^^^^^^^^^", completed.stderr)

    def test_char_frequency_with_membership_check_counts_letters(self):
        completed = self.run_x(self.fixed_frequency_source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "{H: 1, e: 1, l: 2, o: 1}")


if __name__ == "__main__":
    unittest.main()
