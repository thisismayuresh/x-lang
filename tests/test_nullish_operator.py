"""`??` nullish coalescing: runtime semantics, JavaScript mixing rules, typing."""
import contextlib
import io
import textwrap
import tempfile
import unittest
from pathlib import Path

from xlang.cli import main
from xlang.config import XConfig
from xlang.interpreter import Interpreter
from xlang.lexer import Lexer
from xlang.parser import Parser


def run_x(source):
    """Parse, interpret, and return (printed_output, error_or_None)."""
    tokens = Lexer(source, "t.x").tokenize()
    program = Parser(tokens, XConfig().features, "t.x").parse()
    output: list[str] = []
    try:
        Interpreter([], output.append).interpret(program)
        return output, None
    except Exception as exc:
        return output, str(exc)


def parse_error(source: str) -> str | None:
    try:
        tokens = Lexer(source, "t.x").tokenize()
        Parser(tokens, XConfig().features, "t.x").parse()
        return None
    except Exception as exc:
        return str(exc)


class NullishRuntimeTests(unittest.TestCase):
    def assertOutput(self, source, expected):
        output, error = run_x(textwrap.dedent(source).lstrip("\n"))
        self.assertIsNone(error, error)
        self.assertEqual(output, expected)

    def test_non_null_left_wins(self):
        self.assertOutput('print(5 ?? 3);', ["5"])

    def test_null_falls_through(self):
        self.assertOutput('print(null ?? "fallback");', ["fallback"])

    def test_undefined_falls_through(self):
        self.assertOutput('print(undefined ?? "fallback");', ["fallback"])

    def test_zero_is_not_nullish(self):
        # JavaScript distinguishes nullish from falsy: 0 survives `??`.
        self.assertOutput('print(0 ?? "x");', ["0"])

    def test_empty_string_is_not_nullish(self):
        self.assertOutput('print("" ?? "x");', [""])

    def test_false_is_not_nullish(self):
        self.assertOutput("print(false ?? true);", ["false"])

    def test_right_operand_not_evaluated_when_left_present(self):
        self.assertOutput(
            """
            let integer calls = 0;
            integer function bump() {
                calls = calls + 1;
                return 99;
            }
            print(5 ?? bump());
            print(calls);
            """,
            ["5", "0"],
        )

    def test_right_operand_evaluated_when_left_nullish(self):
        self.assertOutput(
            """
            let integer calls = 0;
            integer function bump() {
                calls = calls + 1;
                return 99;
            }
            print(null ?? bump());
            print(calls);
            """,
            ["99", "1"],
        )

    def test_chaining_left_to_right(self):
        self.assertOutput('print(null ?? null ?? "c");', ["c"])
        self.assertOutput('print("a" ?? "b" ?? "c");', ["a"])

    def test_combined_with_optional_chaining(self):
        self.assertOutput(
            """
            let profile = null;
            print(profile?.name ?? "anonymous");
            """,
            ["anonymous"],
        )

    def test_variable_operand(self):
        self.assertOutput(
            """
            let string? nickname = null;
            print(nickname ?? "guest");
            """,
            ["guest"],
        )


class NullishMixingRuleTests(unittest.TestCase):
    def test_mixing_or_without_parentheses_is_rejected(self):
        error = parse_error("let x = a || b ?? c;")
        self.assertIsNotNone(error)
        self.assertIn("'??' cannot be mixed with", error)

    def test_mixing_and_without_parentheses_is_rejected(self):
        error = parse_error("let x = a ?? b && c;")
        self.assertIsNotNone(error)
        self.assertIn("'||' and '&&' cannot be mixed with '??'", error)

    def test_mixing_after_and_without_parentheses_is_rejected(self):
        error = parse_error("let x = a && b ?? c;")
        self.assertIsNotNone(error)
        self.assertIn("'??' cannot be mixed with", error)

    def test_mixing_or_after_nullish_is_rejected(self):
        error = parse_error("let x = a ?? b || c;")
        self.assertIsNotNone(error)
        self.assertIn("'||' and '&&' cannot be mixed with '??'", error)

    def test_parenthesised_or_group_is_allowed(self):
        self.assertIsNone(parse_error("let x = (a || b) ?? c;"))

    def test_parenthesised_nullish_group_is_allowed(self):
        self.assertIsNone(parse_error("let x = (a ?? b) || c;"))

    def test_chained_nullish_is_allowed(self):
        self.assertIsNone(parse_error("let x = a ?? b ?? c;"))

    def test_plain_logical_operators_still_mix(self):
        # Only `??` is restricted; `&&` with `||` keeps working as before.
        self.assertIsNone(parse_error("let x = a || b && c;"))


class NullishTernaryInteractionTests(unittest.TestCase):
    """`??` and the `?:` conditional must group exactly as JavaScript does:
    `??` binds tighter than the condition, each ternary branch is its own
    operand chain (so branches may use `&&`/`||` freely), and the
    no-mixing rule still applies *within* the condition.  The expected
    values below were cross-checked against Node."""

    def assertOutput(self, source, expected):
        output, error = run_x(textwrap.dedent(source).lstrip("\n"))
        self.assertIsNone(error, error)
        self.assertEqual(output, expected)

    # -- grouping: ?? binds tighter than ?: ----------------------------
    def test_nullish_binds_the_condition(self):
        # (0 ?? true) is 0 -> falsy -> "d".  If `??` had grouped the other
        # way (0 ?? (true ? ...)) the result would be 0.
        self.assertOutput('print(0 ?? true ? "c" : "d");', ["d"])

    def test_nullish_condition_with_null_left_selects_true_branch(self):
        self.assertOutput('print(null ?? 1 ? "a" : "b");', ["a"])

    def test_nullish_condition_falsy_zero_selects_false_branch(self):
        self.assertOutput('print(0 ?? 1 ? "a" : "b");', ["b"])

    def test_nullish_in_true_branch(self):
        # True branch is `0 ?? "x"` -> 0; a wrong grouping that wrapped the
        # whole ternary would yield "y".
        self.assertOutput('print(true ? 0 ?? "x" : "y");', ["0"])

    def test_nullish_in_true_branch_falls_through(self):
        self.assertOutput('print(true ? null ?? "x" : "y");', ["x"])

    def test_nullish_in_false_branch_taken_when_condition_false(self):
        self.assertOutput('print(0 ? "y" : 5 ?? 9);', ["5"])
        self.assertOutput('print(false ? "t" : null ?? "w");', ["w"])

    def test_false_condition_does_not_rerun_nullish_after_ternary(self):
        # (false ? 1 : 0) ?? 2 would be 2; the correct grouping gives 0.
        self.assertOutput("print(false ? 1 : 0 ?? 2);", ["0"])

    def test_true_condition_result_survives_without_trailing_nullish(self):
        self.assertOutput("print(true ? 1 : 0 ?? 2);", ["1"])

    def test_true_branch_null_result_is_not_coalesced(self):
        # Node: `true ? null : 5 ?? 9` -> null (?? lives in the false
        # branch, it does not wrap the ternary result).
        self.assertOutput("print(true ? null : 5 ?? 9);", ["null"])

    def test_variable_condition_nullish_grouping(self):
        self.assertOutput(
            """
            let a = null;
            print(a ?? true ? "cond-nullish" : "no");
            """,
            ["cond-nullish"],
        )

    def test_assignment_declaration_rhs_with_both_operators(self):
        self.assertOutput(
            """
            let c = false;
            let picked = c ? 1 ?? "x" : null ?? "y";
            print(picked);
            """,
            ["y"],
        )

    # -- parentheses change the grouping -------------------------------
    def test_parenthesised_ternary_as_right_operand(self):
        # With parens the ternary is the right operand of `??`, so the
        # non-nullish 0 wins instead of the branch value.
        self.assertOutput('print(0 ?? (true ? "c" : "d"));', ["0"])

    def test_parenthesised_ternary_then_nullish(self):
        self.assertOutput('print((true ? "a" : "b") ?? "z");', ["a"])

    def test_parenthesised_nullish_group_in_logical(self):
        self.assertOutput("print((0 ?? 1) && 2);", ["false"])

    # -- each branch is an independent chain ---------------------------
    def test_branches_may_mix_logical_and_nullish_independently(self):
        # Condition uses `??`; true branch uses `&&`; false branch uses
        # `??` — legal in JavaScript because they are separate chains.
        self.assertOutput("print(true ?? false ? 1 && 2 : 3 ?? 4);", ["true"])

    def test_false_branch_logical_and_nullish_neighbours(self):
        self.assertOutput("print(0 ? 1 && 2 : 3 ?? 4);", ["3"])

    def test_branch_logical_operators_do_not_trigger_mixing_error(self):
        self.assertIsNone(
            parse_error("let x = a ? b || c : d ?? e;")
        )
        self.assertIsNone(
            parse_error("let x = a ? b ?? c : d && e;")
        )

    def test_condition_nullish_does_not_leak_into_branches(self):
        # `a ?? b` in the condition, `c && d` in the true branch: legal.
        self.assertIsNone(parse_error("let x = a ?? b ? c && d : e;"))

    def test_call_arguments_are_separate_chains(self):
        # The first argument's `??` must not poison the second argument's
        # `&&`, and vice versa.
        self.assertOutput('print(0 ?? 1 ? "a" : "b", 1 && 2);', ["b true"])

    def test_array_elements_are_separate_chains(self):
        self.assertOutput(
            "print([0 ?? 1 ? \"p\" : \"q\", 1 && 2]);",
            ["[q, true]"],
        )

    def test_template_interpolation_expression(self):
        self.assertOutput(
            "print(`t:{0 ?? 1 ? \"a\" : \"b\"}`);",
            ["t:b"],
        )

    def test_nested_ternary_with_nullish_condition(self):
        # 1 is truthy -> 2; the nested `3 ? 4 ?? 5 : 6` is not reached but
        # must still parse and group as `3 ? (4 ?? 5) : 6`.
        self.assertOutput("print(1 ? 2 : 3 ? 4 ?? 5 : 6);", ["2"])

    # -- the no-mixing rule still applies inside the condition ---------
    def test_condition_mixing_nullish_then_and_is_rejected(self):
        error = parse_error('print(0 ?? 1 && 2 ? "a" : "b");')
        self.assertIsNotNone(error)
        self.assertIn("'||' and '&&' cannot be mixed with '??'", error)

    def test_condition_mixing_and_then_nullish_is_rejected(self):
        error = parse_error('print(1 && 2 ?? 3 ? "a" : "b");')
        self.assertIsNotNone(error)
        self.assertIn("'??' cannot be mixed with", error)

    def test_condition_mixing_with_declared_variables_is_rejected(self):
        error = parse_error(
            'let a = null; let b = 1;\nprint(a ?? b && true ? "x" : "y");'
        )
        self.assertIsNotNone(error)
        self.assertIn("cannot be mixed with", error)

    # -- malformed shapes stay errors ----------------------------------
    def test_colon_without_question_mark_is_a_parse_error(self):
        error = parse_error("print(1 ?? 2 : 3);")
        self.assertIsNotNone(error)
        self.assertIn("Expected", error)

    def test_spaced_double_question_mark_is_a_parse_error(self):
        # `? ?` is not `??`; the second `?` cannot start an expression.
        error = parse_error("print(true ? ? 1 : 2);")
        self.assertIsNotNone(error)
        self.assertIn("Unexpected token", error)

    # -- adjacency and optional chaining idioms ------------------------
    def test_adjacent_tokens_without_spaces(self):
        self.assertOutput("print(1??2);", ["1"])
        self.assertOutput("print(1??2?3:4);", ["3"])
        self.assertOutput('print(null??"a"??"b");', ["a"])

    def test_optional_member_then_nullish(self):
        self.assertOutput(
            """
            let u = null;
            print(u?.name ?? "anon");
            """,
            ["anon"],
        )

    def test_optional_index_then_nullish(self):
        self.assertOutput(
            """
            let arr = [null, 5];
            print(arr?[0] ?? "none");
            """,
            ["none"],
        )

    def test_optional_call_then_nullish(self):
        self.assertOutput(
            """
            let callback = null;
            print(callback?.() ?? "fallback");
            """,
            ["fallback"],
        )


class NullishTypeTests(unittest.TestCase):
    def check_source(self, source):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = main(
                    ["check", "--no-config", "--color", "never", str(source_file)]
                )
        return return_code, output.getvalue(), errors.getvalue()

    def assertClean(self, source):
        return_code, output, errors = self.check_source(source)
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)

    def assertTypeError(self, source, message):
        return_code, output, errors = self.check_source(source)
        self.assertEqual(return_code, 1, output)
        self.assertIn(message, errors)

    def test_null_literal_right_operand_widens(self):
        self.assertClean(
            """
            let value: integer = null ?? 7;
            print(value);
            """
        )

    def test_string_literal_right_operand_is_a_string(self):
        self.assertClean(
            """
            let value: string = null ?? "fallback";
            print(value);
            """
        )

    def test_incompatible_right_operand_is_reported(self):
        self.assertTypeError(
            """
            let value: integer = null ?? "text";
            print(value);
            """
        ,
            "expected `integer`, found",
        )

    def test_nullable_left_stripped_from_result(self):
        # string? ?? string should never require a nullable slot.
        self.assertClean(
            """
            let string? nickname = null;
            let value: string = nickname ?? "guest";
            print(value);
            """
        )

    def test_union_result_needs_union_slot(self):
        self.assertTypeError(
            """
            let string? nickname = null;
            let value: string = nickname ?? 42;
            print(value);
            """
        ,
            "expected `string`, found",
        )

    # -- ?? inside ternary branches ------------------------------------
    def test_nullish_in_true_branch_types_as_its_result(self):
        self.assertClean(
            """
            let string s = true ? null ?? "x" : "y";
            print(s);
            """
        )

    def test_nullish_in_false_branch_types_as_its_result(self):
        self.assertClean(
            """
            let string s = true ? "a" : null ?? "b";
            print(s);
            """
        )

    def test_condition_nullish_group_infers_string_result(self):
        # `0 ?? true` is the condition; the ternary itself is string/string.
        self.assertClean(
            """
            let a = 0 ?? true ? "c" : "d";
            print(a.length);
            """
        )

    def test_branch_union_with_nullish_is_reported(self):
        # True branch `5 ?? "x"` is (integer|string), so the ternary is not
        # assignable to a plain string slot.
        self.assertTypeError(
            """
            let string bad = true ? 5 ?? "x" : "y";
            print(bad);
            """
        ,
            "expected `string`, found `(integer|string)`",
        )


if __name__ == "__main__":
    unittest.main()
