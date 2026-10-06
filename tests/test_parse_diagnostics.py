import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.ast_nodes import (
    ClassDeclaration,
    EnumDeclaration,
    FunctionDeclaration,
    TypeDeclaration,
    VariableDeclaration,
)
from xlang.lexer import Lexer
from xlang.module_loader import ModuleLoader
from xlang.parser import ParseError, Parser
from xlang.runtime import Interpreter


def parse(source, recover=True, source_name="test.x"):
    tokens = Lexer(source, source_name).tokenize()
    parser = Parser(tokens, {}, source_name, recover_errors=recover)
    program = parser.parse()
    return program, parser.errors


def positions(errors):
    return [(error.line, error.column) for error in errors]


def messages(errors):
    return [error.message for error in errors]


class MultiErrorReportingTests(unittest.TestCase):
    def test_reports_every_independent_error_in_one_file(self):
        _, errors = parse("""
int function main() {
    let a = 1
    let b = ;
    let c = 3;
    print(a b c);
    return 0;
}
""")
        self.assertEqual(positions(errors), [(4, 13), (6, 13)])
        self.assertEqual(messages(errors), [
            "Unexpected token ';'; expected an expression",
            "Expected ')' after arguments",
        ])

    def test_automatic_semicolon_insertion_is_not_an_error(self):
        _, errors = parse("""
int function main() {
    let a = 1
    let c = 3;
    return 0;
}
""")
        self.assertEqual(errors, [])

    def test_identical_diagnostics_are_reported_once(self):
        _, errors = parse("""function main() {
    foo(
, 1);
    return 0;
}
""")
        self.assertEqual(len(errors), 1)
        self.assertEqual(positions(errors), [(3, 1)])

    def test_broken_statements_on_one_line_each_report_an_error(self):
        _, errors = parse("""function main() {
    foo(1 + ) let b = ;
    return 0;
}
""")
        self.assertEqual(positions(errors), [(2, 13), (2, 23)])
        self.assertEqual(len(errors), 2)
        self.assertNotEqual(errors[0].message, errors[1].message)

    def test_three_broken_statements_on_one_line_each_report_an_error(self):
        _, errors = parse("""function main() {
    print(1 + ); print(2 + ); print(3 + );
    return 0;
}
""")
        self.assertEqual(positions(errors), [(2, 15), (2, 28), (2, 41)])

    def test_class_member_errors_do_not_cascade(self):
        _, errors = parse("""
class C {
    int a = ;
    int b = ;
    void m() { return; }
}
function main() { let x = ; return 0; }
""")
        self.assertEqual(positions(errors), [(3, 13), (4, 13), (7, 27)])
        for message in messages(errors):
            self.assertNotIn("Expected '}'", message)
            self.assertNotIn("Expected ';' after expression", message)

    def test_for_header_error_does_not_produce_junk_errors(self):
        _, errors = parse("""
function main() {
    for (let i = ; i < 3; i++) {
        print(i);
    }
    let z = ;
    return 0;
}
""")
        self.assertEqual(positions(errors), [(3, 18), (6, 13)])
        for message in messages(errors):
            self.assertNotIn("Expected ';' after expression", message)

    def test_namespace_and_later_file_errors_both_report(self):
        _, errors = parse("""
namespace demo {
    let a = ;
    let b = 2;
}
function main() {
    let c = ;
    return 0;
}
""")
        self.assertEqual(positions(errors), [(3, 13), (7, 13)])

    def test_object_literal_errors_report_once_per_object(self):
        _, errors = parse("""function main() {
    let o = { a: , b: 2 };
    let p = { c: , d: 4 };
    return 0;
}
""")
        self.assertEqual(positions(errors), [(2, 18), (3, 18)])

    def test_enum_member_error_recovers_to_next_declaration(self):
        _, errors = parse("""
enum Color {
    Red = ,
    Blue = 2
}
function main() { return 0; }
""")
        self.assertEqual(len(errors), 1)
        self.assertEqual(positions(errors), [(3, 11)])

    def test_while_condition_error_recovers_before_body(self):
        _, errors = parse("""
function main() {
    while (a + ) {
        print(1);
    }
    let z = ;
    return 0;
}
""")
        self.assertEqual(positions(errors), [(3, 16), (6, 13)])

    def test_error_inside_class_body_recovers_for_next_declaration(self):
        _, errors = parse("""
function main() {
    let a = ;
    return 0;
}
class C {
    int m = 1;
    void method() {
        let q = ;
    }
}
""")
        self.assertEqual(positions(errors), [(3, 13), (9, 17)])

    def test_broken_files_terminate_instead_of_raising(self):
        for source, minimum in (
            ("}}}", 1),
            (")", 1),
            ("@@@", 1),
            ("let = ; let = ;", 1),
            ("{}{}{}", 0),
        ):
            with self.subTest(source=source):
                _, errors = parse(source)
                self.assertGreaterEqual(len(errors), minimum)
                for error in errors:
                    self.assertIsInstance(error, ParseError)

    def test_match_arm_error_recovers_to_following_statement(self):
        _, errors = parse("""
function main() {
    match (1) {
        1 => 2 => ;
        2 => print(2);
    }
    let y = ;
    return 0;
}
""")
        lines = [error.line for error in errors]
        self.assertEqual(lines.count(4), 1)
        self.assertEqual(lines.count(5), 1)
        self.assertEqual(lines.count(7), 1)
        self.assertEqual(len(errors), 3)

    def test_parse_without_recovery_still_raises_first_error(self):
        with self.assertRaises(ParseError) as context:
            parse("""
int function main() {
    let a = 1
    let b = ;
    let c = 3;
    print(a b c);
    return 0;
}
""", recover=False)
        self.assertEqual(context.exception.line, 4)


class MissingDeclarationKeywordTests(unittest.TestCase):
    def test_missing_let_reports_declaration_guidance(self):
        _, errors = parse("UserAccount account = new UserAccount(1);")
        self.assertEqual(len(errors), 1)
        error = errors[0]
        self.assertEqual((error.line, error.column), (1, 13))
        self.assertEqual(
            error.message,
            "Declarations must start with 'let' or 'const'; "
            "write 'let UserAccount account = ...'",
        )

    def test_missing_let_without_initializer_suggests_semicolon(self):
        _, errors = parse("Foo bar;")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].column, 5)
        self.assertEqual(
            errors[0].message,
            "Declarations must start with 'let' or 'const'; "
            "write 'let Foo bar;'",
        )

    def test_missing_let_for_array_type_declaration(self):
        _, errors = parse("int[] values = getValues();")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].column, 7)
        self.assertEqual(
            errors[0].message,
            "Declarations must start with 'let' or 'const'; "
            "write 'let int[] values = ...'",
        )

    def test_missing_let_inside_function_keeps_other_statements_parseable(self):
        _, errors = parse("""function main() {
    Foo bar;
    let x = 1;
    return 0;
}
""")
        self.assertEqual(len(errors), 1)
        self.assertIn("Declarations must start with 'let' or 'const'",
                      errors[0].message)

    def test_ordinary_expressions_are_not_flagged(self):
        _, errors = parse("""function main() {
    a = 1;
    foo();
    a.b.c();
    args[i] = 5;
    let values = [1, 2];
    return 0;
}
""")
        self.assertEqual(errors, [])

    def test_missing_keyword_raises_in_non_recovery_mode(self):
        with self.assertRaises(ParseError) as context:
            parse("UserAccount account = new UserAccount(1);", recover=False)
        self.assertEqual(context.exception.line, 1)
        self.assertEqual(context.exception.column, 13)
        self.assertIn("Declarations must start with 'let' or 'const'",
                      context.exception.message)


class BulkExportTests(unittest.TestCase):
    def test_export_specifiers_mark_top_level_declarations(self):
        program, errors = parse("""
export { greet };
function greet() { return 1; }
""")
        self.assertEqual(errors, [])
        self.assertIsNone(program.declarations[0])
        functions = [
            declaration for declaration in program.declarations
            if isinstance(declaration, FunctionDeclaration)
        ]
        self.assertEqual(len(functions), 1)
        self.assertIn("export", functions[0].modifiers)

    def test_export_list_marks_class_enum_type_and_variable(self):
        program, errors = parse("""
export { User, Color, Point, total };
class User { public int id = 0; }
enum Color { Red, Blue }
type Point = record { int x; int y; };
let total = 0;
""")
        self.assertEqual(errors, [])
        expected = {
            "User": ClassDeclaration,
            "Color": EnumDeclaration,
            "Point": TypeDeclaration,
            "total": VariableDeclaration,
        }
        found = {
            declaration.name: declaration
            for declaration in program.declarations
            if declaration is not None
            and type(declaration) in expected.values()
        }
        self.assertEqual(set(found), set(expected))
        for name, declaration in found.items():
            self.assertIsInstance(declaration, expected[name])
            self.assertIn("export", declaration.modifiers, name)

    def test_export_alias_is_recorded_on_the_declaration(self):
        program, errors = parse("""
export { greet as hello };
function greet() { return 1; }
""")
        self.assertEqual(errors, [])
        declaration = next(
            declaration for declaration in program.declarations
            if isinstance(declaration, FunctionDeclaration)
        )
        self.assertIn("export", declaration.modifiers)
        self.assertEqual(getattr(declaration, "export_aliases", set()), {"hello"})

    def test_unknown_export_name_is_reported(self):
        _, errors = parse("""
export { missing };
function greet() { return 1; }
""")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].message,
                         "Cannot export 'missing': no declaration named 'missing'")

    def test_export_list_requires_semicolon(self):
        _, errors = parse("""
export { greet }
function greet() { return 1; }
""")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].message, "Expected ';' after export list")

    def test_export_specifiers_inside_namespace_are_rejected(self):
        _, errors = parse("""
namespace demo {
    export { helper };
    function helper() { return 1; }
}
""")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].message,
                         "'export { ... }' is only valid at the top level")

    def test_empty_export_list_is_allowed(self):
        _, errors = parse("""
export { };
function greet() { return 1; }
""")
        self.assertEqual(errors, [])

    def test_bulk_exported_function_is_importable_from_another_module(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "greeter.x").write_text("""
export { greet };
function greet() { return "hello"; }
""", encoding="utf-8")
            entry_file = project_root / "main.x"
            entry_file.write_text("""
import greeter.{greet}
function main() {
    print(greet());
}
""", encoding="utf-8")
            program = ModuleLoader(project_root).load_program(entry_file)
            output = []
            result = Interpreter(output=output.append).interpret(program)
        self.assertIsNone(result)
        self.assertEqual(output, ["hello"])

    def test_loader_sees_bulk_exports_without_loader_changes(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_file = project_root / "mod.x"
            module_file.write_text("""
export { greet, Counter };
function greet() { return "hi"; }
class Counter { public int n = 0; }
""", encoding="utf-8")
            loader = ModuleLoader(project_root, recover_errors=True)
            resolved = module_file.resolve()
            loader.load_program(resolved)
            self.assertEqual(loader.errors, [])
            self.assertTrue(loader._is_exported(resolved, "greet"))
            self.assertTrue(loader._is_exported(resolved, "Counter"))
            self.assertFalse(loader._is_exported(resolved, "other"))
            self.assertEqual(
                sorted(loader._exported_names(resolved)), ["Counter", "greet"]
            )


if __name__ == "__main__":
    unittest.main()
