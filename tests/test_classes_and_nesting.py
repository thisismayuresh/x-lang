"""Interpreter coverage for classes, interfaces, enums, and nesting."""
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


class BasicClassTests(unittest.TestCase):
    def test_field_constructor_method(self):
        out, err = run_x(
            "class P { integer x; P(integer x) { this.x = x; } integer get() { return this.x; } }"
            "function main() { print(new P(4).get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["4"])

    def test_multiple_fields(self):
        out, err = run_x(
            "class P { integer x; integer y; P(integer x, integer y) { this.x = x; this.y = y; }"
            " integer sum() { return this.x + this.y; } }"
            "function main() { print(new P(2, 3).sum()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])

    def test_method_chain(self):
        out, err = run_x(
            "class C { integer v; C(integer v) { this.v = v; }"
            " C add(integer n) { this.v = this.v + n; return this; }"
            " integer get() { return this.v; } }"
            "function main() { print(new C(1).add(2).add(3).get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["6"])

    def test_field_mutation(self):
        out, err = run_x(
            "class C { integer n; C() { this.n = 0; } void bump() { this.n = this.n + 1; } }"
            "function main() { let c = new C(); c.bump(); c.bump(); print(c.n); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2"])

    def test_default_field_value(self):
        out, err = run_x(
            "class C { integer n = 7; }"
            "function main() { print(new C().n); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["7"])

    def test_private_field_accessed_inside(self):
        out, err = run_x(
            "class C { private integer n = 3; integer get() { return this.n; } }"
            "function main() { print(new C().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3"])

    def test_class_as_parameter_type(self):
        out, err = run_x(
            "class Point { integer x; Point(integer x) { this.x = x; } }"
            "integer function double(Point p) { return p.x * 2; }"
            "function main() { print(double(new Point(21))); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["42"])

    def test_class_as_return_type(self):
        out, err = run_x(
            "class Point { integer x; Point(integer x) { this.x = x; } }"
            "Point function make(integer x) { return new Point(x); }"
            "function main() { print(make(9).x); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["9"])

    def test_two_instances_are_independent(self):
        out, err = run_x(
            "class C { integer n; C(integer n) { this.n = n; } }"
            "function main() { let a = new C(1); let b = new C(2); print(a.n); print(b.n); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2"])


class InheritanceTests(unittest.TestCase):
    def test_extends_inherits_method(self):
        out, err = run_x(
            "class Base { integer get() { return 1; } }"
            "class Child extends Base { }"
            "function main() { print(new Child().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_extends_overrides_method(self):
        out, err = run_x(
            "class Base { integer get() { return 1; } }"
            "class Child extends Base { integer get() { return 2; } }"
            "function main() { print(new Child().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["2"])

    def test_super_method_call(self):
        out, err = run_x(
            "class Base { integer get() { return 1; } }"
            "class Child extends Base { integer get() { return super.get() + 10; } }"
            "function main() { print(new Child().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["11"])

    def test_super_reaches_grandparent(self):
        out, err = run_x(
            "class A { integer get() { return 1; } }"
            "class B extends A { integer get() { return 2; } }"
            "class C extends B { integer get() { return super.get() + 10; } }"
            "function main() { print(new C().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["12"])

    def test_child_constructor_calls_super_init(self):
        out, err = run_x(
            "class Base { integer n; Base(integer n) { this.n = n; } }"
            "class Child extends Base { integer m; Child(integer n, integer m) { super(n); this.m = m; } }"
            "function main() { let c = new Child(1, 2); print(c.n); print(c.m); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "2"])

    def test_inherited_field_mutation(self):
        out, err = run_x(
            "class Base { integer n = 0; }"
            "class Child extends Base { }"
            "function main() { let c = new Child(); c.n = 5; print(c.n); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])

    def test_three_level_hierarchy(self):
        out, err = run_x(
            "class A { integer get() { return 1; } }"
            "class B extends A { integer get() { return super.get() * 10; } }"
            "class C extends B { integer get() { return super.get() + 1; } }"
            "function main() { print(new C().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["11"])


class StaticTests(unittest.TestCase):
    def test_static_method(self):
        out, err = run_x(
            "class U { static integer twice(integer n) { return n * 2; } }"
            "function main() { print(U.twice(3)); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["6"])

    def test_static_method_via_instance(self):
        out, err = run_x(
            "class C { static integer sq(integer n) { return n * n; } }"
            "function main() { print(new C().sq(5)); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["25"])

    def test_static_field(self):
        out, err = run_x(
            "class C { static integer count = 7; static integer get() { return C.count; } }"
            "function main() { print(C.get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["7"])


class InterfaceTests(unittest.TestCase):
    def test_implements_single_interface(self):
        out, err = run_x(
            "interface Shape { integer area(); }"
            "class Circle implements Shape { integer r; Circle(integer r) { this.r = r; } integer area() { return this.r * 2; } }"
            "function main() { print(new Circle(4).area()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["8"])

    def test_polymorphic_via_interface_type(self):
        out, err = run_x(
            "interface Shape { integer area(); }"
            "class Square implements Shape { integer s; Square(integer s) { this.s = s; } integer area() { return this.s * this.s; } }"
            "integer function total(Shape s) { return s.area(); }"
            "function main() { print(total(new Square(3))); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["9"])

    def test_implements_multiple_interfaces(self):
        out, err = run_x(
            "interface A { integer getA(); }"
            "interface B { integer getB(); }"
            "class C implements A, B { integer getA() { return 1; } integer getB() { return 2; } }"
            "function main() { let a: A = new C(); print(a.getA()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1"])

    def test_interface_with_field_access_via_class(self):
        out, err = run_x(
            "interface I { integer n(); }"
            "class C implements I { integer n() { return 5; } }"
            "function main() { print(new C().n()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])

    def test_interface_method_with_parameters(self):
        out, err = run_x(
            "interface Adder { integer add(integer a, integer b); }"
            "class Sum implements Adder { integer add(integer a, integer b) { return a + b; } }"
            "function main() { print(new Sum().add(2, 3)); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])


class NestedClassTests(unittest.TestCase):
    def test_bare_inner_instantiation(self):
        out, err = run_x(
            "class Outer {"
            "  integer make() { let i = new Inner(5); return i.get(); }"
            "  class Inner { integer v; Inner(integer v) { this.v = v; } integer get() { return this.v; } }"
            "}"
            "function main() { print(new Outer().make()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])

    def test_qualified_inner_instantiation(self):
        out, err = run_x(
            "class Outer { class Inner { integer v; Inner(integer v) { this.v = v; } integer get() { return this.v; } } }"
            "function main() { let i = new Outer.Inner(3); print(i.get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3"])

    def test_three_level_nesting(self):
        out, err = run_x(
            "class A {"
            "  integer get() { return new B().get() + 1; }"
            "  class B {"
            "    integer get() { return new C().get() + 1; }"
            "    class C { integer get() { return 42; } }"
            "  }"
            "}"
            "function main() { print(new A().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["44"])

    def test_four_level_nesting(self):
        out, err = run_x(
            "class L1 {"
            "  integer get() { return new L2().get() + 1; }"
            "  class L2 {"
            "    integer get() { return new L3().get() + 1; }"
            "    class L3 {"
            "      integer get() { return new L4().get() + 1; }"
            "      class L4 { integer get() { return 4; } }"
            "    }"
            "  }"
            "}"
            "function main() { print(new L1().get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["7"])

    def test_nested_field_mutation_from_outside(self):
        out, err = run_x(
            "class Outer { class Inner { integer v; } }"
            "function main() { let i = new Outer.Inner(); i.v = 9; print(i.v); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["9"])

    def test_sibling_access_between_inner_classes(self):
        out, err = run_x(
            "class Outer {"
            "  integer use() { return new Left().get() + new Right().get(); }"
            "  class Left { integer get() { return 1; } }"
            "  class Right { integer get() { return 2; } }"
            "}"
            "function main() { print(new Outer().use()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3"])

    def test_inner_shadows_outer_name(self):
        out, err = run_x(
            "class Item { integer id = 100; }"
            "class Outer {"
            "  integer get() { let i = new Inner(); return i.id; }"
            "  class Inner { integer id = 5; }"
            "}"
            "function main() { print(new Outer().get()); print(new Item().id); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5", "100"])

    def test_nested_class_constructor_args(self):
        out, err = run_x(
            "class Outer { class Inner { integer a; integer b; Inner(integer a, integer b) { this.a = a; this.b = b; } integer sum() { return this.a + this.b; } } }"
            "function main() { print(new Outer.Inner(2, 3).sum()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["5"])


class GenericClassTests(unittest.TestCase):
    def test_box_integer(self):
        out, err = run_x(
            "class Box<T> { T value; Box(T value) { this.value = value; } T get() { return this.value; } }"
            "function main() { print(new Box<integer>(7).get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["7"])

    def test_box_string(self):
        out, err = run_x(
            "class Box<T> { T value; Box(T value) { this.value = value; } T get() { return this.value; } }"
            "function main() { print(new Box<string>(\"hi\").get()); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["hi"])

    def test_box_field_assignment(self):
        out, err = run_x(
            "class Holder<T> { T value; }"
            "function main() { let h = new Holder<string>(); h.value = \"x\"; print(h.value); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["x"])

    def test_generic_class_type_arg_is_inferred_from_constructor(self):
        out, err = run_x(
            "class Pair<A, B> { A first; B second; Pair(A a, B b) { this.first = a; this.second = b; } }"
            "function main() { let p = new Pair<integer, string>(1, \"one\"); print(p.first); print(p.second); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["1", "one"])

    def test_nested_generic_instantiation(self):
        out, err = run_x(
            "class Box<T> { T value; Box(T value) { this.value = value; } }"
            "function main() { let b = new Box<Box<integer>>(new Box<integer>(3)); print(b.value.value); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["3"])


class EnumTests(unittest.TestCase):
    def test_enum_values(self):
        out, err = run_x(
            "enum Color { RED, GREEN, BLUE }"
            "function main() { print(Color.RED); print(Color.GREEN); print(Color.BLUE); }"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["RED", "GREEN", "BLUE"])

    def test_enum_in_match(self):
        out, err = run_x(
            "enum Day { MON, TUE }"
            "function main() {"
            "  let d = Day.MON;"
            "  let s = match (d) { Day.MON => \"mon\", Day.TUE => \"tue\" };"
            "  print(s);"
            "}"
        )
        self.assertIsNone(err)
        self.assertEqual(out, ["mon"])


if __name__ == "__main__":
    unittest.main()
