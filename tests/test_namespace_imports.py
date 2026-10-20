"""Namespace-member imports: ``import util.MyNamespace.fun``.

Covers the loader walking an exported namespace chain inside the shortest
existing prefix module file:

* the member is bound flat in the importing scope and keeps its namespace
  closure, so sibling references like ``print(obj)`` still resolve
* aliases, enums, and nested namespace chains work the same way
* ``import util.MyNamespace`` binds the namespace itself; whole-module
  ``import util`` plus ``util.MyNamespace.fun()`` keeps working
* the exported namespace is the export boundary: its members (and nested
  namespaces) are reachable without their own ``export``; a missing member
  or an unexported module-level hop reports a clear error
"""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.cli import main as cli_main
from xlang.module_loader import ModuleLoader
from xlang.runtime import Interpreter

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

UTIL_MODULE = """
export namespace MyNamespace {

function fun() {
    print(obj)
}

let object<string, any> obj = {
    "name": "Maya"
}

string function greet(string who) {
    return "hi, " + who;
}

integer function add(integer a, integer b) {
    return a + b;
}

export enum Color {
    RED = "red",
    GREEN = "green",
}

}

export const integer MAX = 100;
"""


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def run_modules(entry_source, modules):
    """Write *modules* next to *entry_source* and interpret the entry file."""
    with TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        for module_name, module_source in modules.items():
            module_file = project_root / module_name
            module_file.parent.mkdir(parents=True, exist_ok=True)
            module_file.write_text(dedent(module_source), encoding="utf-8")
        entry_file = project_root / "main.x"
        entry_file.write_text(dedent(entry_source), encoding="utf-8")
        program = ModuleLoader(project_root).load_program(entry_file)
        output = []
        Interpreter([], output.append).interpret(program)
    return output


def run_modules_cli(entry_source, modules):
    """Run the entry file through ``x run``; return ``(code, stdout, stderr)``."""
    output = io.StringIO()
    errors = io.StringIO()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        for module_name, module_source in modules.items():
            module_file = project_root / module_name
            module_file.parent.mkdir(parents=True, exist_ok=True)
            module_file.write_text(dedent(module_source), encoding="utf-8")
        entry_file = project_root / "main.x"
        entry_file.write_text(dedent(entry_source), encoding="utf-8")
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["run", "--no-config", "--color", "never", str(entry_file)]
            )
    return return_code, output.getvalue(), errors.getvalue()


def check_modules_cli(entry_source, modules):
    """Run ``x check`` over the entry file; return ``(code, stdout, stderr)``."""
    output = io.StringIO()
    errors = io.StringIO()
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        for module_name, module_source in modules.items():
            module_file = project_root / module_name
            module_file.parent.mkdir(parents=True, exist_ok=True)
            module_file.write_text(dedent(module_source), encoding="utf-8")
        entry_file = project_root / "main.x"
        entry_file.write_text(dedent(entry_source), encoding="utf-8")
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["check", "--no-config", "--color", "never", str(entry_file)]
            )
    return return_code, output.getvalue(), errors.getvalue()


class NamespaceMemberImportTests(unittest.TestCase):
    def test_member_import_binds_flat_and_keeps_namespace_closure(self):
        # `fun` references sibling `obj` declared after it inside the
        # namespace; the flattened binding must keep the namespace closure.
        output = run_modules(
            "import util.MyNamespace.fun\n" "fun()\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["{name: Maya}"])

    def test_export_specifier_marks_namespace_members_exported(self):
        output = run_modules(
            "import util.MyNamespace.greet\n" 'print(greet("Ada"))\n',
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Ada"])

    def test_member_import_with_an_alias(self):
        output = run_modules(
            "import util.MyNamespace.greet as sayHi\n" 'print(sayHi("Bo"))\n',
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Bo"])

    def test_enum_member_via_namespace_chain(self):
        output = run_modules(
            "import util.MyNamespace.Color\n" "print(Color.RED)\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["RED"])

    def test_repeated_member_imports_from_the_same_module(self):
        # The second import hits the already-loaded-module cache and must
        # still walk the namespace chain from the cached declarations.
        output = run_modules(
            "import util.MyNamespace.fun\n"
            "import util.MyNamespace.add\n"
            "print(add(2, 3))\n"
            "fun()\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["5", "{name: Maya}"])

    def test_nested_namespace_chain(self):
        nested_util = """
export namespace Outer {
    export namespace Inner {
        export string function tag() {
            return "outer-inner"
        }
    }
}
"""
        output = run_modules(
            "import util.Outer.Inner.tag\n" 'print(tag())\n',
            {"util.x": nested_util},
        )
        self.assertEqual(output, ["outer-inner"])

    def test_namespace_itself_is_importable_as_a_member(self):
        output = run_modules(
            "import util.MyNamespace\n" 'print(MyNamespace.greet("Ana"))\n',
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Ana"])

    def test_whole_module_import_exposes_namespace_members(self):
        output = run_modules(
            "import util\n"
            'print(util.MyNamespace.greet("Maya"))\n'
            "print(util.MAX)\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Maya", "100"])

    def test_export_specifier_can_export_the_namespace_itself(self):
        util_module = """
export namespace Outer {
    export string function tag() {
        return "outer"
    }
}
export { Outer };
"""
        output = run_modules(
            "import util.Outer.tag\n" 'print(tag())\n',
            {"util.x": util_module},
        )
        self.assertEqual(output, ["outer"])

    def test_flatten_collision_is_reported_across_namespaces(self):
        other_module = """
export namespace Other {
    export string function greet(string who) {
        return "other, " + who;
    }
}
"""
        return_code, _, errors = run_modules_cli(
            "import util.MyNamespace.greet\n"
            "import other.Other.greet\n"
            'print(greet("X"))\n',
            {"util.x": UTIL_MODULE, "other.x": other_module},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("'greet' is already declared", errors)


class NamespaceMemberImportErrorTests(unittest.TestCase):
    def test_missing_member_is_rejected(self):
        return_code, _, errors = run_modules_cli(
            "import util.MyNamespace.nope\n" "nope()\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn(
            "'nope' is not a member of namespace 'util.MyNamespace'", errors
        )

    def test_unexported_member_inside_exported_namespace_is_importable(self):
        util_module = """
export namespace MyNamespace {
    function hidden() {
        print("hidden")
    }
}
"""
        output = run_modules(
            "import util.MyNamespace.hidden\n" "hidden()\n",
            {"util.x": util_module},
        )
        self.assertEqual(output, ["hidden"])

    def test_import_call_of_a_namespace_member(self):
        util_module = """
export namespace MyNamespace {
    string function greet(string who) {
        print("calling")
        return "hi, " + who;
    }
}
"""
        output = run_modules(
            'import util.MyNamespace.greet("Maya")\n' 'print(greet("Bo"))\n',
            {"util.x": util_module},
        )
        self.assertEqual(output, ["calling", "calling", "hi, Bo"])

    def test_nested_unexported_namespace_inside_exported_one(self):
        util_module = """
export namespace Outer {
    namespace Inner {
        function tag() {
            return "outer-inner"
        }
    }
}
"""
        output = run_modules(
            "import util.Outer.Inner.tag\n" "print(tag())\n",
            {"util.x": util_module},
        )
        self.assertEqual(output, ["outer-inner"])

    def test_unexported_namespace_in_the_chain_is_rejected(self):
        util_module = """
namespace Secret {
    export string function peek() {
        return "secret"
    }
}
"""
        return_code, _, errors = run_modules_cli(
            "import util.Secret.peek\n" "print(peek())\n",
            {"util.x": util_module},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("'Secret' is not exported by module 'util'", errors)

    def test_chain_part_that_is_not_a_namespace_is_rejected(self):
        return_code, _, errors = run_modules_cli(
            "import util.MAX.thing\n" "thing()\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("'MAX' does not name a namespace in module 'util'", errors)


class NamespaceWildcardImportTests(unittest.TestCase):
    def test_wildcard_binds_all_exported_members(self):
        output = run_modules(
            "import util.MyNamespace.*\n"
            'print(greet("Ada"))\n'
            "print(add(2, 3))\n"
            "fun()\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Ada", "5", "{name: Maya}"])

    def test_wildcard_binds_unexported_members_too(self):
        util_module = """
export namespace MyNamespace {
    export string function greet(string who) {
        return "hi, " + who;
    }
    function hidden() {
        print("hidden")
    }
}
"""
        output = run_modules(
            "import util.MyNamespace.*\n" "hidden()\n",
            {"util.x": util_module},
        )
        self.assertEqual(output, ["hidden"])

    def test_wildcard_then_namespace_qualified_call(self):
        output = run_modules(
            "import util.MyNamespace.*\n" 'print(MyNamespace.greet("Ada"))\n',
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Ada"])

    def test_wildcard_with_an_alias(self):
        output = run_modules(
            "import util.MyNamespace.* as N\n" 'print(N.greet("Bo"))\n',
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Bo"])

    def test_wildcard_over_a_nested_namespace_chain(self):
        nested_util = """
export namespace Outer {
    export namespace Inner {
        export string function tag() {
            return "outer-inner"
        }
    }
}
"""
        output = run_modules(
            "import util.Outer.Inner.*\n" 'print(tag())\n',
            {"util.x": nested_util},
        )
        self.assertEqual(output, ["outer-inner"])

    def test_wildcard_and_member_import_of_the_same_module(self):
        output = run_modules(
            "import util.MyNamespace.*\n"
            "import util.MyNamespace.greet as sayHi\n"
            'print(greet("Ada"))\n'
            'print(sayHi("Bo"))\n',
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(output, ["hi, Ada", "hi, Bo"])

    def test_wildcard_of_a_namespace_without_member_exports(self):
        util_module = """
export namespace MyNamespace {
    string function greet(string who) {
        return "hi, " + who;
    }
}
"""
        output = run_modules(
            "import util.MyNamespace.*\n" 'print(greet("X"))\n',
            {"util.x": util_module},
        )
        self.assertEqual(output, ["hi, X"])

    def test_wildcard_of_an_empty_namespace_is_rejected(self):
        util_module = """
export namespace MyNamespace {
}
"""
        return_code, _, errors = run_modules_cli(
            "import util.MyNamespace.*\n" "print(MyNamespace)\n",
            {"util.x": util_module},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("Namespace 'util.MyNamespace' declares no members", errors)

    def test_wildcard_chain_part_that_is_not_a_namespace_is_rejected(self):
        return_code, _, errors = run_modules_cli(
            "import util.MAX.*\n" "print(MAX)\n",
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("'MAX' does not name a namespace in module 'util'", errors)

    def test_wildcard_over_an_unexported_namespace_is_rejected(self):
        util_module = """
namespace Secret {
    export string function peek() {
        return "secret"
    }
}
"""
        return_code, _, errors = run_modules_cli(
            "import util.Secret.*\n" "print(peek())\n",
            {"util.x": util_module},
        )
        self.assertEqual(return_code, 1)
        self.assertIn("'Secret' is not exported by module 'util'", errors)


class NamespaceClassInheritanceTests(unittest.TestCase):
    """`extends` / `implements` through namespace-chain imports."""

    SHAPE_MODULE = """
export namespace Shapes {
    export interface Shape {
        integer area();
    }
    export class Square implements Shape {
        integer side = 0;
        Square(integer side) {
            this.side = side;
        }
        integer area() {
            return this.side * this.side;
        }
    }
}
"""

    def test_extends_class_imported_through_namespace_chain(self):
        output = run_modules(
            "import util.Shapes.Square\n"
            "class MySquare extends Square {\n"
            "    MySquare(integer side) {\n"
            "        super(side);\n"
            "    }\n"
            "}\n"
            "print(MySquare(5).area())\n",
            {"util.x": self.SHAPE_MODULE},
        )
        self.assertEqual(output, ["25"])

    def test_implements_interface_imported_through_namespace_chain(self):
        output = run_modules(
            "import util.Shapes.Shape\n"
            "class MySquare implements Shape {\n"
            "    integer side = 0;\n"
            "    MySquare(integer side) {\n"
            "        this.side = side;\n"
            "    }\n"
            "    integer area() {\n"
            "        return this.side * this.side;\n"
            "    }\n"
            "}\n"
            "print(MySquare(4).area())\n",
            {"util.x": self.SHAPE_MODULE},
        )
        self.assertEqual(output, ["16"])

    def test_implements_interface_via_namespace_wildcard(self):
        output = run_modules(
            "import util.Shapes.*\n"
            "class MySquare implements Shape {\n"
            "    integer side = 0;\n"
            "    MySquare(integer side) {\n"
            "        this.side = side;\n"
            "    }\n"
            "    integer area() {\n"
            "        return this.side * this.side;\n"
            "    }\n"
            "}\n"
            "print(MySquare(4).area())\n",
            {"util.x": self.SHAPE_MODULE},
        )
        self.assertEqual(output, ["16"])

    def test_extends_through_dotted_namespace_path(self):
        output = run_modules(
            "import util.Shapes\n"
            "class MySquare extends Shapes.Square {\n"
            "    MySquare(integer side) {\n"
            "        super(side);\n"
            "    }\n"
            "}\n"
            "print(MySquare(6).area())\n",
            {"util.x": self.SHAPE_MODULE},
        )
        self.assertEqual(output, ["36"])

    def test_implements_dotted_interface_name_is_accepted(self):
        return_code, output, errors = check_modules_cli(
            "import util.Shapes\n"
            "class MySquare implements Shapes.Shape {\n"
            "    integer side = 0;\n"
            "    MySquare(integer side) {\n"
            "        this.side = side;\n"
            "    }\n"
            "    integer area() {\n"
            "        return this.side * this.side;\n"
            "    }\n"
            "}\n",
            {"util.x": self.SHAPE_MODULE},
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("types are valid", output)


class NamespaceMemberImportCheckTests(unittest.TestCase):
    def test_check_accepts_namespace_member_imports(self):
        return_code, output, errors = check_modules_cli(
            "import util.MyNamespace.greet\n" 'print(greet("Ada"))\n',
            {"util.x": UTIL_MODULE},
        )
        self.assertEqual(return_code, 0, errors)
        self.assertIn("syntax is valid", output)
        self.assertIn("types are valid", output)


class NamespaceImportExampleTests(unittest.TestCase):
    def test_repository_example_namespace_demo(self):
        example_file = (
            REPOSITORY_ROOT / "examples" / "namespace_demo" / "main.x"
        )
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = cli_main(
                ["run", "--no-config", "--color", "never", str(example_file)]
            )
        self.assertEqual(return_code, 0, errors.getvalue())
        lines = output.getvalue().splitlines()
        self.assertIn("hi, Ada", lines)
        self.assertIn("5", lines)
        self.assertIn("hi, Bo", lines)
        self.assertIn("42", lines)
        self.assertIn("100", lines)


if __name__ == "__main__":
    unittest.main()
