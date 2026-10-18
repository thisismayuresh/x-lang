"""Interpreter coverage for object literals, types, and core value semantics."""
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


class ObjectLiteralTests(unittest.TestCase):
    def test_empty_object(self):
        out, err = run_x("function main() { let o = {}; print(o); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["{}"])

    def test_single_field(self):
        out, err = run_x("function main() { let o = {a: 1}; print(o.a); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_multiple_fields(self):
        out, err = run_x(
            "function main() { let o = {a: 1, b: 2}; print(o.a); print(o.b); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2"])

    def test_bracket_access(self):
        out, err = run_x(
            "function main() { let o = {a: 1, b: 2}; print(o[\"b\"]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2"])

    def test_field_mutation(self):
        out, err = run_x(
            "function main() { let o = {a: 1}; o.a = 9; print(o.a); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["9"])

    def test_new_field_via_bracket(self):
        out, err = run_x(
            "function main() { let o = {}; o[\"x\"] = 4; print(o.x); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["4"])

    def test_nested_object(self):
        out, err = run_x(
            "function main() { let o = {a: {b: {c: 1}}}; print(o.a.b.c); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_object_field_is_object(self):
        out, err = run_x(
            "function main() { let inner = {v: 42}; let outer = {i: inner}; print(outer.i.v); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["42"])

    def test_spread(self):
        out, err = run_x(
            "function main() { let a = {x: 1}; let b = {y: 2, ...a}; print(b.x); print(b.y); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2"])

    def test_spread_overwrites(self):
        out, err = run_x(
            "function main() { let a = {x: 1}; let b = {x: 99, ...a}; print(b.x); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_spread_chain(self):
        out, err = run_x(
            "function main() {"
            "  let a = {a: 1}; let b = {b: 2}; let c = {...a, ...b, c: 3};"
            "  print(c.a); print(c.b); print(c.c);"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2", "3"])

    def test_key_iteration(self):
        out, err = run_x(
            "function main() {"
            "  let o = {a: 1, b: 2};"
            "  for (string k in o) { print(k); }"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["a", "b"])

    def test_object_passed_to_function(self):
        out, err = run_x(
            "integer function getX(o) { return o.x; }"
            "function main() { print(getX({x: 7})); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["7"])

    def test_object_returned_from_function(self):
        out, err = run_x(
            "function make() { return {a: 1}; }"
            "function main() { print(make().a); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_object_in_array(self):
        out, err = run_x(
            "function main() { let items = [{v: 1}, {v: 2}]; print(items[1].v); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2"])

    def test_typeOf_object(self):
        out, err = run_x("function main() { print(typeOf({})); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["object"])


class TypeAnnotationTests(unittest.TestCase):
    def test_let_with_integer(self):
        out, err = run_x("function main() { let v: integer = 1; print(v); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_let_with_string(self):
        out, err = run_x("function main() { let v: string = \"s\"; print(v); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["s"])

    def test_let_with_float(self):
        out, err = run_x("function main() { let v: float = 1.5; print(v); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["1.5"])

    def test_let_with_boolean(self):
        out, err = run_x("function main() { let v: boolean = true; print(v); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["true"])

    def test_let_with_array(self):
        out, err = run_x(
            "function main() { let v: integer[] = [1, 2]; print(v[0]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_let_with_2d_array(self):
        out, err = run_x(
            "function main() { let v: integer[][] = [[1, 2], [3, 4]]; print(v[1][0]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3"])

    def test_parameter_annotation(self):
        out, err = run_x(
            "integer function f(integer n) { return n + 1; }"
            "function main() { print(f(1)); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2"])

    def test_return_type_annotation(self):
        out, err = run_x(
            "integer function f() { return 5; }"
            "function main() { print(f()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])

    def test_const_reassign_fails(self):
        out, err = run_x(
            "function main() { const a = 1; a = 2; print(a); }"
        )
        self.assertIn("constant", err)

    def test_let_reassign_ok(self):
        out, err = run_x("function main() { let a = 1; a = 2; print(a); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["2"])

    def test_shadowing_in_block(self):
        out, err = run_x(
            "function main() {"
            "  let x = 1;"
            "  { let x = 2; print(x); }"
            "  print(x);"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2", "1"])

    def test_type_alias(self):
        out, err = run_x(
            "type Point = record { integer x; integer y; };"
            "function main() { let p: Point = {x: 1, y: 2}; print(p.x); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_record_annotation(self):
        out, err = run_x(
            "function main() {"
            "  let p: record { integer id; string name; } = {id: 1, name: \"x\"};"
            "  print(p.id); print(p.name);"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "x"])

    def test_record_type_alias_annotation(self):
        out, err = run_x(
            "type Person = record { string name; integer age; };"
            "function main() {"
            "  let p: Person = {name: \"a\", age: 30};"
            "  print(p.name); print(p.age);"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["a", "30"])


class ValueTypeTests(unittest.TestCase):
    def test_integer_arithmetic(self):
        out, err = run_x(
            "function main() { print(2 + 3); print(10 - 4); print(3 * 4); print(8 / 2); }"
        )
        self.assertIsNone(err)
        # Division always yields a float in X.
        self.assertEqual(out, ["5", "6", "12", "4.0"])

    def test_float_division(self):
        out, err = run_x("function main() { let a = 7 / 2; print(a); print(typeOf(a)); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["3.5", "number"])

    def test_modulo(self):
        out, err = run_x("function main() { print(7 % 3); }")
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_string_concat(self):
        out, err = run_x(
            "function main() { print(\"a\" + \"b\"); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["ab"])

    def test_string_length(self):
        out, err = run_x(
            "function main() { let s = \"hello\"; print(s.length); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])

    def test_string_index(self):
        out, err = run_x(
            "function main() { print(\"hello\"[0]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["h"])

    def test_boolean_operators(self):
        out, err = run_x(
            "function main() { print(true && false); print(true || false); print(!true); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["false", "true", "false"])

    def test_equality(self):
        out, err = run_x(
            "function main() { print(1 == 1); print(1 == 2); print(\"a\" == \"a\"); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["true", "false", "true"])

    def test_inequality(self):
        out, err = run_x(
            "function main() { print(1 != 2); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["true"])

    def test_comparison_operators(self):
        out, err = run_x(
            "function main() { print(1 < 2); print(2 <= 2); print(3 > 2); print(3 >= 4); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["true", "true", "true", "false"])

    def test_ternary_operator(self):
        out, err = run_x(
            "function main() { print(true ? 1 : 2); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_null_equality(self):
        out, err = run_x(
            "function main() { let v = null; print(v == null); print(v != null); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["true", "false"])

    def test_typeOf_int_and_float(self):
        out, err = run_x(
            "function main() { print(typeOf(1)); print(typeOf(1.5)); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["number", "number"])

    def test_typeOf_string_boolean_array(self):
        out, err = run_x(
            "function main() { print(typeOf(\"s\")); print(typeOf(true)); print(typeOf([1])); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["string", "boolean", "Array"])


class ArrayTests(unittest.TestCase):
    def test_literal_and_index(self):
        out, err = run_x(
            "function main() { let a = [10, 20, 30]; print(a[0]); print(a[2]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["10", "30"])

    def test_length(self):
        out, err = run_x(
            "function main() { print([1, 2, 3].length); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3"])

    def test_push(self):
        out, err = run_x(
            "function main() { let a = [1]; a.push(2); print(a.length); print(a[1]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2", "2"])

    def test_2d_array(self):
        out, err = run_x(
            "function main() { let g = [[1, 2], [3, 4]]; print(g[1][0]); print(g[0][1]); print(g.length); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3", "2", "2"])

    def test_3d_array(self):
        out, err = run_x(
            "function main() { let g = [[[1]]]; print(g[0][0][0]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_element_assignment(self):
        out, err = run_x(
            "function main() { let a = [1, 2]; a[0] = 9; print(a[0]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["9"])

    def test_iteration(self):
        out, err = run_x(
            "function main() { for (let v in [1, 2]) { print(v); } }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2"])

    def test_array_in_object(self):
        out, err = run_x(
            "function main() { let o = {tags: [\"a\", \"b\"]}; print(o.tags[1]); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["b"])

    def test_array_in_nested_iteration(self):
        out, err = run_x(
            "function main() {"
            "  let data = [[1, 2], [3, 4]];"
            "  for (let row in data) { print(row[0] + row[1]); }"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3", "7"])


class ControlFlowTests(unittest.TestCase):
    def test_while_loop(self):
        out, err = run_x(
            "function main() { let i = 0; while (i < 3) { print(i); i = i + 1; } }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["0", "1", "2"])

    def test_for_range(self):
        out, err = run_x(
            "function main() { for (let i in range(0, 3)) { print(i); } }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["0", "1", "2"])

    def test_for_of_array(self):
        out, err = run_x(
            "function main() { for (let v in [1, 2]) { print(v); } }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2"])

    def test_for_of_object_keys(self):
        out, err = run_x(
            "function main() {"
            "  let o = {a: 1, b: 2};"
            "  for (string k in o) { print(k); }"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["a", "b"])

    def test_try_catch(self):
        out, err = run_x(
            "function main() { try { throw \"boom\"; } catch (e) { print(e); } }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["boom"])

    def test_try_finally(self):
        out, err = run_x(
            "function main() { try { print(\"t\"); } finally { print(\"f\"); } }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["t", "f"])

    def test_lambda(self):
        out, err = run_x(
            "function main() { let f = (x) => x * 2; print(f(3)); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["6"])

    def test_match_expression(self):
        out, err = run_x(
            "function main() {"
            "  let v = match (2) { 1 => \"one\", 2 => \"two\", _ => \"other\" };"
            "  print(v);"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["two"])


if __name__ == "__main__":
    unittest.main()
