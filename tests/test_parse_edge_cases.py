import unittest

from xlang.lexer import LexError, Lexer
from xlang.parser import ParseError, Parser


def parse(source, recover=False, source_name="edge.x"):
    tokens = Lexer(source, source_name, recover_errors=recover).tokenize()
    parser = Parser(tokens, {}, source_name, recover_errors=recover)
    program = parser.parse()
    return program, parser.errors


class DeepNestingTests(unittest.TestCase):
    def assert_reports_depth_error(self, source):
        try:
            program, errors = parse(source)
        except RecursionError:
            self.fail("a RecursionError escaped the parser")
            return
        except ParseError as error:
            self.assertEqual(error.message, "Program is nested too deeply to parse")
            self.assertEqual(error.line, 1)
            self.assertGreater(error.column, 1)
            return
        self.fail(f"expected a depth error, parsed {program}")

    def test_deep_parentheses_report_a_positioned_diagnostic(self):
        self.assert_reports_depth_error("let a = " + "(" * 500 + "1" + ")" * 500 + ";")

    def test_deep_brackets_report_a_positioned_diagnostic(self):
        self.assert_reports_depth_error("let a = " + "[" * 500 + "]" * 500 + ";")

    def test_deep_object_literals_report_a_positioned_diagnostic(self):
        self.assert_reports_depth_error("let a = " + "{a: " * 500 + "1" + "}" * 500 + ";")

    def test_deep_unary_chains_report_a_positioned_diagnostic(self):
        self.assert_reports_depth_error("let a = " + "!" * 2000 + "true;")

    def test_recovery_mode_records_the_depth_error_once(self):
        _, errors = parse(
            "let a = " + "(" * 500 + "1" + ")" * 500 + ";",
            recover=True,
        )
        messages = [error.message for error in errors]
        self.assertIn("Program is nested too deeply to parse", messages)
        self.assertEqual(messages.count("Program is nested too deeply to parse"), 1)

    def test_nested_templates_report_a_lexical_diagnostic(self):
        source = "let a = `x" + "{`y" * 1500 + "1" + "}`" * 1500 + ";"
        with self.assertRaises(LexError) as raised:
            Lexer(source, "edge.x").tokenize()
        self.assertEqual(raised.exception.message, "Template literals are nested too deeply")
        self.assertEqual(raised.exception.line, 1)
        self.assertGreater(raised.exception.column, 1)


class LegalDeepProgramsTests(unittest.TestCase):
    def test_deeply_nested_blocks_still_parse(self):
        source = "function main() {" + "{ " * 200 + "let a = 1;" + " }" * 200 + "}"
        program, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(len(program.declarations), 1)

    def test_moderately_nested_expressions_still_parse(self):
        source = "let a = " + "(" * 250 + "1" + ")" * 250 + ";"
        program, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(len(program.declarations), 1)

    def test_long_unary_chains_still_parse(self):
        source = "let a = " + "!" * 500 + "true;"
        program, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(len(program.declarations), 1)

    def test_chained_ternaries_still_parse(self):
        source = "let a = " + "a ? b : " * 100 + "c;"
        program, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(len(program.declarations), 1)

    def test_one_hundred_thousand_character_line_parses(self):
        source = "let a = " + " + ".join(["1"] * 20000) + ";"
        program, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(len(program.declarations), 1)

    def test_nested_templates_still_parse(self):
        source = "let a = `x{ `y{ `z{1}` }` }z`;"
        program, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(len(program.declarations), 1)

    def test_crlf_tabs_and_byte_order_mark_still_parse(self):
        source = "\ufeff" + "function main() {\r\n\tlet a = 1;\r\n}\r\n"
        program, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(len(program.declarations), 1)


if __name__ == "__main__":
    unittest.main()
