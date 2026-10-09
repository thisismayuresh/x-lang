"""Tests for the ``x repl`` interactive session."""

import unittest

from xlang.config import XConfig
from xlang.repl import run_repl


def run_session(lines, config=None, banner=False):
    """Feed *lines* to a REPL session; return ``(exit_code, out, errors)``."""
    remaining = iter(lines)
    output = []
    errors = []

    def input_fn(_prompt):
        try:
            return next(remaining)
        except StopIteration as stop:
            raise EOFError from stop

    exit_code = run_repl(
        config or XConfig(),
        input_fn=input_fn,
        output=output.append,
        error_output=errors.append,
        banner=banner,
    )
    return exit_code, output, errors


class ReplSessionTests(unittest.TestCase):
    def test_expressions_print_their_value_and_state_persists(self):
        exit_code, output, errors = run_session(
            [
                "1 + 1",
                "let x = 5",
                "x * 2",
                "x = x + 1",
                "x",
                ".exit",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertIn("2", output)
        self.assertIn("10", output)
        self.assertIn("6", output)

    def test_redeclaring_a_name_across_entries_is_allowed(self):
        exit_code, output, errors = run_session(
            [
                "let x = 1",
                "let x = 2",
                "x",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertIn("2", output)

    def test_multiline_function_definitions_continue_until_balanced(self):
        exit_code, output, errors = run_session(
            [
                "function double(n) {",
                "    return n * 2;",
                "}",
                "double(21)",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertIn("42", output)

    def test_parse_error_does_not_swallow_the_next_entry(self):
        exit_code, output, errors = run_session(
            [
                "bad syntax here +",
                "let v = 1",
                "v",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(errors)
        self.assertIn("error:", errors[0])
        self.assertIn("1", output)

    def test_type_error_is_reported_against_the_current_entry(self):
        exit_code, output, errors = run_session(
            [
                "let v = 1",
                'v = "str"',
                "v",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(any("Cannot assign 'string'" in line for line in errors))
        # Line numbers point at the current entry, not the whole session.
        self.assertTrue(any("--> <repl>:1:1" in line for line in errors))
        self.assertIn("1", output)

    def test_runtime_errors_keep_the_session_running(self):
        exit_code, output, errors = run_session(
            [
                "1 / 0",
                "7 * 6",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(any("divide" in line for line in errors))
        self.assertIn("42", output)

    def test_exit_command_and_end_of_input_end_the_session(self):
        exit_code, output, errors = run_session([".exit"])
        self.assertEqual(exit_code, 0)

        exit_code, output, errors = run_session(["1"])
        self.assertEqual(exit_code, 0)

        exit_code, output, errors = run_session(["quit"])
        self.assertEqual(exit_code, 0)

    def test_help_command_describes_the_session(self):
        exit_code, output, errors = run_session([".help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertTrue(any(".exit" in line for line in output))

    def test_system_process_exit_stops_the_session_with_its_code(self):
        exit_code, output, errors = run_session(
            [
                "System.process.exit(3)",
                "1 + 1",
            ]
        )

        self.assertEqual(exit_code, 3)
        self.assertTrue(any("process exited with code 3" in line for line in output))

    def test_main_is_never_invoked_by_the_session(self):
        exit_code, output, errors = run_session(
            [
                'function main() { print("should not run"); }',
                "1 + 1",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertNotIn("should not run", output)

    def test_declarations_echo_nothing_but_expressions_do(self):
        exit_code, output, errors = run_session(
            [
                "let total = 41",
                "total + 1",
                'print("side effect")',
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertIn("side effect", output)
        self.assertIn("42", output)
        self.assertNotIn("41", output)

    def test_entry_waiting_for_an_operand_waits_for_more_input(self):
        exit_code, output, errors = run_session(
            [
                "let n =",
                "5",
                "n * 2",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertIn("10", output)


if __name__ == "__main__":
    unittest.main()
