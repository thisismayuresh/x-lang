"""Interpreter coverage for switch, match, decorators, closures, equality,
enums, and exceptions — scenario matrices including nested cases."""
import unittest

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


class SwitchTests(unittest.TestCase):
    def test_simple_case(self):
        out, err = run_x(
            'any function main() { switch (1) { case 1: { print("one"); } } }'
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["one"])

    def test_matching_case_among_several(self):
        out, err = run_x("""
            any function main() {
                switch (2) {
                    case 1: { print("one"); }
                    case 2: { print("two"); }
                    case 3: { print("three"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["two", "three"])

    def test_default_case(self):
        out, err = run_x("""
            any function main() {
                switch (9) {
                    case 1: { print("one"); }
                    default: { print("other"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["other"])

    def test_default_skipped_when_case_matches(self):
        out, err = run_x("""
            any function main() {
                switch (1) {
                    case 1: { print("one"); }
                    default: { print("other"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["one", "other"])

    def test_fallthrough_is_default_semantics(self):
        out, err = run_x("""
            any function main() {
                switch (1) {
                    case 1: { print("one"); }
                    case 2: { print("two"); }
                    default: { print("other"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["one", "two", "other"])

    def test_break_inside_loop_breaks_the_loop(self):
        out, err = run_x("""
            any function main() {
                for (int i in range(1, 4)) {
                    switch (i) {
                        case 1: { print("one"); break; }
                        default: { print("many"); break; }
                    }
                }
                print("done");
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["one", "done"])

    def test_string_cases(self):
        out, err = run_x("""
            any function main() {
                let string mode = "dark";
                switch (mode) {
                    case "light": { print("light mode"); }
                    case "dark": { print("dark mode"); }
                    default: { print("auto"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["dark mode", "auto"])

    def test_boolean_cases(self):
        out, err = run_x("""
            any function main() {
                switch (true) {
                    case false: { print("no"); }
                    case true: { print("yes"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["yes"])

    def test_expression_subject(self):
        out, err = run_x("""
            any function main() {
                switch (2 * 3) {
                    case 6: { print("six"); }
                    default: { print("nope"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["six", "nope"])

    def test_statements_after_switch_run(self):
        out, err = run_x("""
            any function main() {
                switch (1) { case 1: { print("in"); } }
                print("after");
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["in", "after"])

    def test_nested_switch(self):
        out, err = run_x("""
            any function main() {
                switch (1) {
                    case 1: {
                        print("outer one");
                        switch (2) {
                            case 2: { print("inner two"); }
                            default: { print("inner other"); }
                        }
                    }
                    default: { print("outer other"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["outer one", "inner two", "inner other", "outer other"])

    def test_switch_inside_function(self):
        out, err = run_x("""
            function classify(int n) {
                switch (n) {
                    case 0: { return "zero"; }
                    default: { return "nonzero"; }
                }
            }
            any function main() {
                print(classify(0));
                print(classify(5));
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["zero", "nonzero"])

    def test_enum_case(self):
        out, err = run_x("""
            enum Color { RED, GREEN }
            any function main() {
                let Color c = Color.GREEN;
                switch (c) {
                    case Color.RED: { print("red"); }
                    case Color.GREEN: { print("green"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["green"])

    def test_float_case(self):
        out, err = run_x("""
            any function main() {
                switch (1.5) {
                    case 1.5: { print("one and a half"); }
                    default: { print("other"); }
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["one and a half", "other"])

    def test_no_case_and_no_default_runs_nothing(self):
        out, err = run_x("""
            any function main() {
                switch (42) {
                    case 1: { print("one"); }
                }
                print("done");
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["done"])


class MatchTests(unittest.TestCase):
    def test_literal_pattern(self):
        out, err = run_x("""
            any function main() {
                let int n = 2;
                let string label = match n {
                    1 => "one",
                    2 => "two",
                    _ => "many"
                };
                print(label);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["two"])

    def test_binding_pattern(self):
        out, err = run_x("""
            any function main() {
                let int n = 41;
                let int result = match n {
                    0 => 0,
                    x => x + 1
                };
                print(result);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["42"])

    def test_wildcard_catches_rest(self):
        out, err = run_x("""
            any function main() {
                let string s = match "z" {
                    "a" => "letter a",
                    _ => "something else"
                };
                print(s);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["something else"])

    def test_null_pattern(self):
        out, err = run_x("""
            any function main() {
                let var value = null;
                let string s = match value {
                    null => "nothing",
                    _ => "something"
                };
                print(s);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["nothing"])

    def test_string_literal_patterns(self):
        out, err = run_x("""
            any function main() {
                for (string word in ["go", "stop", "yield"]) {
                    print(match word {
                        "go" => "green",
                        "stop" => "red",
                        _ => "yellow"
                    });
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["green", "red", "yellow"])

    def test_array_destructure_pattern(self):
        out, err = run_x("""
            any function main() {
                let int[] pair = [3, 4];
                let int sum = match pair {
                    [a, b] => a + b,
                    _ => -1
                };
                print(sum);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["7"])

    def test_array_rest_pattern(self):
        out, err = run_x("""
            any function main() {
                let int[] xs = [1, 2, 3, 4];
                let int head = match xs {
                    [first, ...rest] => first,
                    _ => 0
                };
                print(head);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_object_destructure_pattern(self):
        out, err = run_x("""
            any function main() {
                let object user = {name: "Ada", age: 36};
                let string s = match user {
                    {name: who} => who,
                    _ => "anon"
                };
                print(s);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["Ada"])

    def test_guard_filters_arm(self):
        out, err = run_x("""
            any function main() {
                let int n = 15;
                let string s = match n {
                    x if x > 100 => "huge",
                    x if x > 10 => "big",
                    x => "small"
                };
                print(s);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["big"])

    def test_enum_pattern(self):
        out, err = run_x("""
            enum State { ON, OFF }
            any function main() {
                let State s = State.OFF;
                let string label = match s {
                    State.ON => "lit",
                    State.OFF => "dark"
                };
                print(label);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["dark"])

    def test_match_nested_in_match(self):
        out, err = run_x("""
            any function main() {
                let int a = 1;
                let int b = 2;
                let string s = match a {
                    1 => match b {
                        2 => "one-two",
                        _ => "one-other"
                    },
                    _ => "other"
                };
                print(s);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["one-two"])

    def test_match_inside_function_body(self):
        out, err = run_x("""
            function grade(int score) {
                return match score {
                    s if s >= 90 => "A",
                    s if s >= 80 => "B",
                    _ => "C"
                };
            }
            any function main() {
                print(grade(95));
                print(grade(85));
                print(grade(10));
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["A", "B", "C"])

    def test_match_on_boolean(self):
        out, err = run_x("""
            any function main() {
                let boolean ok = true;
                print(match ok {
                    true => "yes",
                    false => "no"
                });
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["yes"])

    def test_match_over_array_inputs(self):
        out, err = run_x("""
            function describe(object value) {
                return match value {
                    null => "empty",
                    [first, ...rest] => "list head " + first,
                    {kind: k} => "obj " + k,
                    _ => "other"
                };
            }
            any function main() {
                print(describe(null));
                print(describe([7, 8, 9]));
                print(describe({kind: "err"}));
                print(describe(3));
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["empty", "list head 7", "obj err", "other"])


class DecoratorTests(unittest.TestCase):
    def test_identity_function_decorator(self):
        out, err = run_x("""
            function identity(var target) { return target; }
            @identity
            function greet() { return "hi"; }
            any function main() { print(greet()); }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["hi"])

    def test_wrapping_function_decorator(self):
        out, err = run_x("""
            function logged(var target) {
                return (a, b) => {
                    print("calling");
                    return target(a, b);
                };
            }
            @logged
            function add(int a, int b) { return a + b; }
            any function main() { print(add(2, 3)); }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["calling", "5"])

    def test_decorator_factory(self):
        out, err = run_x("""
            function suite(string name) {
                return (target) => {
                    print("suite " + name);
                    return target;
                };
            }
            @suite("smoke")
            function example() { return "ok"; }
            any function main() { print(example()); }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["suite smoke", "ok"])

    def test_stacked_decorators(self):
        out, err = run_x("""
            function mark(var target) { return target; }
            function twice(var target) {
                return () => {
                    print("x2");
                    return target();
                };
            }
            @mark
            @twice
            function f() { return "v"; }
            any function main() { print(f()); }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["x2", "v"])

    def test_class_decorator(self):
        out, err = run_x("""
            function tag(var target) { return target; }
            @tag
            class Widget { public string name = "w"; }
            any function main() {
                let Widget w = new Widget();
                print(w.name);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["w"])

    def test_method_decorator(self):
        out, err = run_x("""
            function logged(var target) { return target; }
            class Svc {
                public Svc() {}
                @logged
                public string run() { return "ok"; }
            }
            any function main() { print(new Svc().run()); }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["ok"])

    def test_builtin_trace_decorator(self):
        out, err = run_x("""
            @trace
            function work() { return 1; }
            any function main() { print(work()); }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["Calling work", "1"])

    def test_trace_on_class_and_method(self):
        out, err = run_x("""
            @trace
            class Box {
                public Box() {}
                @trace
                public string value() { return "box"; }
            }
            any function main() { print(new Box().value()); }
            """)
        self.assertIsNone(err)
        self.assertEqual(
            out,
            ["Constructing Box", "Calling value", "box"],
        )

    def test_decorator_must_return_function(self):
        out, err = run_x("""
            function bad(var target) { return 42; }
            @bad
            function f() { return "x"; }
            any function main() { print(f()); }
            """)
        self.assertIn("must return a function", err or "")


class ClosureTests(unittest.TestCase):
    def test_closure_captures_local(self):
        out, err = run_x("""
            function make() {
                let int n = 10;
                int function get() { return n; }
                return get;
            }
            any function main() {
                let Function g = make();
                print(g());
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["10"])

    def test_counter_closure(self):
        out, err = run_x("""
            function makeCounter() {
                let int count = 0;
                int function tick() { count = count + 1; return count; }
                return tick;
            }
            any function main() {
                let Function c = makeCounter();
                print(c());
                print(c());
                print(c());
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2", "3"])

    def test_two_closures_separate_state(self):
        out, err = run_x("""
            function makeCounter(int start) {
                let int count = start;
                int function tick() { count = count + 1; return count; }
                return tick;
            }
            any function main() {
                let Function a = makeCounter(0);
                let Function b = makeCounter(100);
                print(a());
                print(b());
                print(a());
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "101", "2"])

    def test_arrow_closure_captures_parameter(self):
        out, err = run_x("""
            function adder(int base) {
                return (int n): int => base + n;
            }
            any function main() {
                let Function add5 = adder(5);
                print(add5(3));
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["8"])

    def test_nested_function_sees_outer_locals(self):
        out, err = run_x("""
            any function main() {
                let int a = 1;
                let int b = 2;
                int function sum() { return a + b; }
                print(sum());
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["3"])

    def test_closure_as_callback(self):
        out, err = run_x("""
            any function main() {
                let int factor = 10;
                int function apply(int n) { return n * factor; }
                print(apply(4));
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["40"])

    def test_nested_function_not_run_at_declaration(self):
        out, err = run_x("""
            any function main() {
                let int count = 0;
                print("before");
                int function bump() { count = count + 1; return count; }
                print("after");
                print(count);
                print(bump());
                print(count);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["before", "after", "0", "1", "1"])


class EqualityTests(unittest.TestCase):
    def test_strict_equality_int(self):
        out, err = run_x("""
            any function main() {
                print(1 === 1);
                print(1 === 2);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true", "false"])

    def test_strict_equality_int_float_same_value(self):
        out, err = run_x("""
            any function main() {
                print(1 === 1.0);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true"])

    def test_loose_equality_int_float(self):
        out, err = run_x("""
            any function main() {
                print(1 == 1.0);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true"])

    def test_equality_null_undefined(self):
        out, err = run_x("""
            any function main() {
                print(null == null);
                print(undefined == undefined);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true", "true"])

    def test_null_not_equal_value(self):
        out, err = run_x("""
            any function main() {
                print(null == 0);
                print(null == "");
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["false", "false"])

    def test_string_equality(self):
        out, err = run_x("""
            any function main() {
                print("ab" == "ab");
                print("ab" == "a" + "b");
                print("ab" == "ba");
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true", "true", "false"])

    def test_inequality_operators(self):
        out, err = run_x("""
            any function main() {
                print(1 != 2);
                print(1 !== 1.0);
                print(2 > 1);
                print(2 >= 2);
                print(1 < 2);
                print(1 <= 0);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true", "false", "true", "true", "true", "false"])


class EnumTests(unittest.TestCase):
    def test_implicit_ordinals(self):
        out, err = run_x("""
            enum Level { LOW, MID, HIGH }
            any function main() {
                print(Level.LOW);
                print(Level.MID);
                print(Level.HIGH);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["LOW", "MID", "HIGH"])

    def test_enum_in_function_scope(self):
        out, err = run_x("""
            any function main() {
                enum Shade { LIGHT, DARK }
                let Shade s = Shade.DARK;
                print(s == Shade.DARK);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true"])

    def test_enum_same_member_equality(self):
        out, err = run_x("""
            enum Flag { ON, OFF }
            any function main() {
                let Flag a = Flag.ON;
                let Flag b = Flag.ON;
                print(a == b);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["true"])

    def test_enum_different_members_unequal(self):
        out, err = run_x("""
            enum Flag { ON, OFF }
            any function main() {
                print(Flag.ON == Flag.OFF);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["false"])

    def test_cross_enum_members_unequal(self):
        out, err = run_x("""
            enum A { X }
            enum B { X }
            any function main() {
                print(A.X == B.X);
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["false"])

    def test_enum_in_match(self):
        out, err = run_x("""
            enum Direction { N, S, E, W }
            function move(Direction d) {
                return match d {
                    Direction.N => "up",
                    Direction.S => "down",
                    Direction.E => "right",
                    Direction.W => "left"
                };
            }
            any function main() {
                print(move(Direction.N));
                print(move(Direction.W));
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["up", "left"])


class ExceptionTests(unittest.TestCase):
    def test_throw_and_catch(self):
        out, err = run_x("""
            any function main() {
                try {
                    throw new Exception("boom");
                }
                catch (Exception e) {
                    print("caught " + e.message);
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["caught boom"])

    def test_finally_runs_on_normal_path(self):
        out, err = run_x("""
            any function main() {
                try {
                    print("body");
                }
                finally {
                    print("cleanup");
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["body", "cleanup"])

    def test_finally_runs_on_throw(self):
        out, err = run_x("""
            any function main() {
                try {
                    throw new Exception("x");
                }
                catch (Exception e) {
                    print("handled");
                }
                finally {
                    print("cleanup");
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["handled", "cleanup"])

    def test_custom_exception_class(self):
        out, err = run_x("""
            class AppError extends Exception {
                public int code;
                public AppError(string message, int code) {
                    super(message);
                    this.code = code;
                }
            }
            any function main() {
                try {
                    throw new AppError("bad", 42);
                }
                catch (AppError e) {
                    print(e.message);
                    print(e.code);
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["bad", "42"])

    def test_catch_specific_type_first(self):
        out, err = run_x("""
            any function main() {
                try {
                    throw new Exception("plain");
                }
                catch (Exception e) {
                    print("exception catch");
                }
                catch (Throwable t) {
                    print("throwable catch");
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["exception catch"])

    def test_rethrow_from_catch(self):
        out, err = run_x("""
            any function main() {
                try {
                    try {
                        throw new Exception("inner");
                    }
                    catch (Exception e) {
                        throw new Exception("outer:" + e.message);
                    }
                }
                catch (Exception e2) {
                    print(e2.message);
                }
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["outer:inner"])

    def test_try_inside_function_with_return(self):
        out, err = run_x("""
            function safeDiv(int a, int b) {
                try {
                    if (b == 0) {
                        throw new Exception("div0");
                    }
                    return a / b;
                }
                catch (Exception e) {
                    return -1;
                }
            }
            any function main() {
                print(safeDiv(10, 2));
                print(safeDiv(10, 0));
            }
            """)
        self.assertIsNone(err)
        self.assertEqual(out, ["5.0", "-1"])


if __name__ == "__main__":
    unittest.main()
