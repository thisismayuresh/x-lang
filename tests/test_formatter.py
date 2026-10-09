import unittest

from xlang.formatter import format_source
from xlang.lexer import LexError, Lexer
from xlang.parser import ParseError


def code_tokens(source):
    tokens = Lexer(source, recover_errors=False).tokenize()
    return [(token.kind, token.value) for token in tokens if token.kind != "EOF"]


class FormatterTests(unittest.TestCase):
    def assert_formats(self, source, expected):
        formatted = format_source(source, "<test>")
        self.assertEqual(formatted, expected)
        # Formatting must be idempotent and must not change the token stream.
        self.assertEqual(format_source(formatted, "<test>"), expected)
        self.assertEqual(code_tokens(source), code_tokens(formatted))

    def test_normalises_spacing_and_indentation(self):
        self.assert_formats(
            "function  f( int a ,int b ){\nlet sum=a+b;\nreturn sum;\n}\n",
            "function f(int a, int b) {\n  let sum = a + b;\n  return sum;\n}\n",
        )

    def test_if_else_chain_stays_joined(self):
        self.assert_formats(
            "if(x){print(1);}else if(y){print(2);}else{print(3);}\n",
            "if (x) {\n  print(1);\n} else if (y) {\n  print(2);\n} else {\n  print(3);\n}\n",
        )

    def test_for_header_semicolons_stay_inline(self):
        self.assert_formats(
            "for(let i=0;i<10;i++){print(i);}\n",
            "for (let i = 0; i < 10; i++) {\n  print(i);\n}\n",
        )

    def test_object_literals_stay_inline(self):
        self.assert_formats(
            "let o={a:1,b:2};\nlet e={};\n",
            "let o = { a: 1, b: 2 };\nlet e = {};\n",
        )

    def test_arrays_keep_inner_spacing(self):
        self.assert_formats("let a=[1,  2,3];\n", "let a = [1, 2, 3];\n")

    def test_strings_and_templates_are_preserved_verbatim(self):
        self.assert_formats(
            'let s = "keep   spaces\\n";\nlet t = `a ${1+2} b`;\n',
            'let s = "keep   spaces\\n";\nlet t = `a ${1+2} b`;\n',
        )

    def test_line_comments_force_a_newline(self):
        self.assert_formats(
            "let x = 1; // note\nlet y = 2;\n",
            "let x = 1; // note\nlet y = 2;\n",
        )

    def test_own_line_comments_and_blank_lines_survive(self):
        self.assert_formats(
            "// header\n\nlet x = 1;\n",
            "// header\n\nlet x = 1;\n",
        )

    def test_trailing_comment_does_not_glue_to_next_statement(self):
        self.assert_formats(
            "import System.io.Console\n\n// Explains the module\nlet x = 1;\n",
            "import System.io.Console\n\n// Explains the module\nlet x = 1;\n",
        )

    def test_asi_newlines_between_statements_are_kept(self):
        self.assert_formats(
            "function f() {\n  print(1)\n  print(2)\n}\n",
            "function f() {\n  print(1)\n  print(2)\n}\n",
        )

    def test_switch_cases_use_blocks(self):
        self.assert_formats(
            "function p(int x){switch(x){case 1:{print(1);break;}default:{print(2);}}}\n",
            "function p(int x) {\n"
            "  switch (x) {\n"
            "    case 1: {\n"
            "      print(1);\n"
            "      break;\n"
            "    }\n"
            "    default: {\n"
            "      print(2);\n"
            "    }\n"
            "  }\n"
            "}\n",
        )

    def test_match_arms_one_per_line(self):
        self.assert_formats(
            'let r = match (x) { 1 => "a", _ => "b" };\n',
            'let r = match (x) {\n  1 => "a",\n  _ => "b"\n};\n',
        )

    def test_do_while_joins_while_to_the_closing_brace(self):
        self.assert_formats(
            "do{x++;}while(x<10);\n",
            "do {\n  x++;\n} while (x < 10);\n",
        )

    def test_class_members_are_indented(self):
        self.assert_formats(
            "class P{int x;P(int x){this.x=x;}}\n",
            "class P {\n  int x;\n  P(int x) {\n    this.x = x;\n  }\n}\n",
        )

    def test_unary_and_postfix_operators(self):
        self.assert_formats(
            "let n=-1;\nlet m=!flag;\nlet p=i++;\nlet q=++j;\n",
            "let n = -1;\nlet m = !flag;\nlet p = i++;\nlet q = ++j;\n",
        )

    def test_ternary_keeps_spaces(self):
        self.assert_formats("let v=c?a:b;\n", "let v = c ? a : b;\n")

    def test_optional_chain_has_no_spaces(self):
        self.assert_formats(
            "let v = obj?.prop;\n",
            "let v = obj?.prop;\n",
        )

    def test_multiple_blank_lines_collapse_to_one(self):
        self.assert_formats("let a = 1;\n\n\n\nlet b = 2;\n", "let a = 1;\n\nlet b = 2;\n")

    def test_trailing_whitespace_and_final_newline(self):
        self.assert_formats("let a = 1;   \n", "let a = 1;\n")

    def test_empty_source_stays_empty(self):
        self.assertEqual(format_source("", "<test>"), "")
        self.assertEqual(format_source("   \n\n", "<test>"), "")

    def test_syntax_errors_are_reported_not_rewritten(self):
        with self.assertRaises(ParseError):
            format_source("let x = ;\n", "<test>")

    def test_lex_errors_are_reported(self):
        with self.assertRaises(LexError):
            format_source('let s = "unterminated\n', "<test>")

    def test_top_level_return_blocks_formatting(self):
        with self.assertRaises(ParseError) as raised:
            format_source("return 1;\n", "<test>")
        self.assertIn("'return' is only valid inside a function", str(raised.exception))

    def test_carriage_returns_are_normalised(self):
        self.assert_formats("let a = 1;\r\nlet b = 2;\r\n", "let a = 1;\nlet b = 2;\n")


class ReturnOutsideFunctionTests(unittest.TestCase):
    def parse(self, source):
        from xlang.parser import Parser

        tokens = Lexer(source, recover_errors=False).tokenize()
        return Parser(tokens, None, "<test>", recover_errors=False).parse()

    def test_top_level_return_is_rejected(self):
        with self.assertRaises(ParseError) as raised:
            self.parse("return 1;")
        self.assertIn("'return' is only valid inside a function", str(raised.exception))

    def test_return_inside_top_level_loop_is_rejected(self):
        with self.assertRaises(ParseError) as raised:
            self.parse("while (true) { return 1; }")
        self.assertIn("'return' is only valid inside a function", str(raised.exception))

    def test_return_inside_function_is_accepted(self):
        program = self.parse("function f() { return 1; }")
        self.assertEqual(len(program.declarations), 1)

    def test_return_inside_nested_function_is_accepted(self):
        program = self.parse(
            "function outer() { function inner() { return 1; } return inner(); }"
        )
        self.assertEqual(len(program.declarations), 1)

    def test_return_inside_method_is_accepted(self):
        program = self.parse("class C { int m() { return 1; } }")
        self.assertEqual(len(program.declarations), 1)

    def test_return_inside_arrow_body_is_accepted(self):
        program = self.parse("let f = (int x) => { return x; };")
        self.assertEqual(len(program.declarations), 1)


if __name__ == "__main__":
    unittest.main()
