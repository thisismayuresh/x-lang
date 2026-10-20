"""Tests for the VS Code language server completion helpers."""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(REPO_ROOT, "vscode-xlang", "server")
for path in (REPO_ROOT, SERVER_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from lsprotocol.types import (
        CodeActionKind,
        CompletionItemKind,
        CompletionParams,
        Diagnostic,
        DiagnosticSeverity,
        Position,
        Range,
    )

    from server import (  # noqa: E402
        XLanguageServer,
        _auto_import_items,
        _declared_symbols,
        _expression_completions,
        _find_declaration,
        _import_completions,
        _import_edit,
        _module_matches,
        code_actions,
    )

    AVAILABLE = True
except Exception:  # pragma: no cover - pygls is an optional dependency
    AVAILABLE = False


def _labels(items):
    return [item.label for item in items or []]


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class ModuleMatchTests(unittest.TestCase):
    def test_empty_typing_matches_everything(self):
        self.assertTrue(_module_matches("", "System.utils.Math"))
        self.assertTrue(_module_matches(".", "System.utils.Math"))

    def test_segments_match_consecutively_after_a_dot(self):
        self.assertTrue(_module_matches("System.", "System.utils.Math"))
        self.assertFalse(_module_matches("System.io.", "System.Throwable.Exception.IOException"))
        self.assertTrue(_module_matches("System.io.", "System.io.FileSystem"))

    def test_partial_final_segment_may_skip_namespaces(self):
        self.assertTrue(_module_matches("System.M", "System.utils.Math"))
        self.assertFalse(_module_matches("System.Q", "System.utils.Math"))
        self.assertTrue(_module_matches("Collections", "System.utils.Collections"))

    def test_unrelated_paths_are_filtered(self):
        self.assertFalse(_module_matches("utils.", "oop_demo"))
        self.assertFalse(_module_matches("zzz", "System.utils.Math"))


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class ImportCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = XLanguageServer()
        cls.uri = "file://" + os.path.join(REPO_ROOT, "examples", "main.x")

    def items(self, source, line, character):
        return _import_completions(self.server, self.uri, source, line, character)

    def test_no_import_statement_returns_none(self):
        self.assertIsNone(self.items("let int a = 1;", 0, 14))
        self.assertIsNone(self.items("print(x)", 0, 8))

    def test_bare_import_offers_standard_library(self):
        labels = _labels(self.items("import ", 0, 7))
        self.assertIn("System.utils.Math", labels)
        self.assertIn("System.io.FileSystem", labels)
        self.assertNotIn("System", labels)

    def test_dot_trigger_offers_modules_under_prefix(self):
        labels = _labels(self.items("import System.", 0, 14))
        self.assertIn("System.utils.Math", labels)
        self.assertIn("System.io.FileSystem", labels)
        self.assertIn("System.process.Environment", labels)
        self.assertNotIn("System.Environment", labels)
        self.assertNotIn("System", labels)

    def test_partial_segment_after_dot_is_not_dropped(self):
        labels = _labels(self.items("import System.M", 0, 15))
        self.assertIn("System.utils.Math", labels)

    def test_local_files_are_offered(self):
        labels = _labels(self.items("import oop", 0, 10))
        self.assertIn("oop_demo", labels)

    def test_local_exports_are_offered_after_dot(self):
        labels = _labels(self.items("import import_export.", 0, 21))
        self.assertTrue(any(label.endswith(".sayGreet") for label in labels), labels)

    def test_unknown_prefix_returns_no_items(self):
        self.assertEqual(self.items("import nosuchmodule.", 0, 20), [])


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class ExpressionCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = XLanguageServer()
        cls.uri = "file://" + os.path.join(REPO_ROOT, "examples", "main.x")

    def items(self, source, line, character):
        return _expression_completions(self.server, self.uri, source, line, character)

    def test_system_dot_offers_namespaces(self):
        labels = _labels(self.items("let x = System.", 0, 15))
        self.assertIn("System.io", labels)
        self.assertIn("System.utils", labels)
        self.assertIn("System.process", labels)
        self.assertNotIn("System", labels)

    def test_nested_namespace_is_scoped(self):
        labels = _labels(self.items("let x = System.io.", 0, 18))
        self.assertIn("System.io.FileSystem", labels)
        self.assertNotIn("System.Throwable.Exception.IOException", labels)

    def test_non_system_expressions_are_left_alone(self):
        self.assertIsNone(self.items("foo.", 0, 4))
        self.assertIsNone(self.items("let x = 1;", 0, 10))


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class CompletionRequestTests(unittest.TestCase):
    """Drive the real ``textDocument/completion`` handler."""

    def test_completion_handler_returns_import_items(self):
        from lsprotocol.types import TextDocumentIdentifier

        from server import completions

        server = XLanguageServer()
        uri = "file://" + os.path.join(REPO_ROOT, "examples", "main.x")
        source = "import System.\n"
        server.documents[uri] = source
        params = CompletionParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=0, character=14),
        )
        result = completions(server, params)
        self.assertIsInstance(result, dict)
        labels = [item["label"] if isinstance(item, dict) else item.label
                  for item in result["items"]]
        self.assertIn("System.utils.Math", labels)
        self.assertFalse(result["isIncomplete"])

    def test_import_items_use_a_text_edit_over_the_typed_path(self):
        from server import _import_completions

        server = XLanguageServer()
        uri = "file://" + os.path.join(REPO_ROOT, "examples", "main.x")
        items = _import_completions(server, uri, "import System.", 0, 14)
        math = next(item for item in items if item.label == "System.utils.Math")
        self.assertEqual(math.kind, CompletionItemKind.Module)
        self.assertIsNotNone(math.text_edit)
        self.assertEqual(math.text_edit.range.start.character, 7)
        self.assertEqual(math.text_edit.range.end.character, 14)
        self.assertEqual(math.filter_text, "System.utils.Math")


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class DeclaredSymbolCompletionTests(unittest.TestCase):
    """Names declared in the buffer show up with their types."""

    SOURCE = """\
export type SettingsKey = "theme" | "backup";

export const object<SettingsKey, string> DEFAULT_SETTINGS = {
    theme: "system"
};

export string function getSetting(SettingsKey key) {
    return DEFAULT_SETTINGS.theme;
}

any function main() {
    let integer count = 3;
    let raw: string = "x";
    print(count, raw);
}
"""

    def by_label(self):
        return {item.label: item for item in _declared_symbols(self.SOURCE)}

    def test_declared_variables_are_offered_with_annotations(self):
        items = self.by_label()
        self.assertIn("DEFAULT_SETTINGS", items)
        self.assertIn("object<SettingsKey, string>", items["DEFAULT_SETTINGS"].detail)
        self.assertEqual(items["DEFAULT_SETTINGS"].kind, CompletionItemKind.Constant)
        self.assertIn("count", items)
        self.assertIn("integer", items["count"].detail)
        self.assertEqual(items["count"].kind, CompletionItemKind.Variable)

    def test_colon_annotation_is_shown_in_detail(self):
        items = self.by_label()
        self.assertIn("raw", items)
        self.assertIn("string", items["raw"].detail)

    def test_functions_types_and_parameters_are_offered(self):
        items = self.by_label()
        self.assertIn("getSetting", items)
        self.assertIn("SettingsKey key", items["getSetting"].detail)
        self.assertIn("main", items)
        self.assertIn("SettingsKey", items)
        self.assertEqual(items["SettingsKey"].kind, CompletionItemKind.Struct)

    def test_declared_names_sort_above_keywords(self):
        for item in _declared_symbols(self.SOURCE):
            self.assertTrue(item.sort_text.startswith("0_"), item.label)


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class BuiltinMemberCompletionTests(unittest.TestCase):
    """``x.`` offers the members of ``x``'s declared or inferred type."""

    def members_for(self, declaration, variable):
        """Complete after the dot on *variable*, which *declaration* declares."""
        from lsprotocol.types import TextDocumentIdentifier

        from server import _member_completions

        source = f"{declaration}\n{variable}.\n"
        server = XLanguageServer()
        uri = "file:///member.x"
        server.documents[uri] = source
        items = _member_completions(server, uri, source, 1, len(variable) + 1)
        return [item.label for item in items or []]

    def test_string_variable_offers_string_methods(self):
        labels = self.members_for('let s = "hi";', "s")
        self.assertIn("toUpperCase", labels)
        self.assertIn("trim", labels)
        self.assertIn("split", labels)
        self.assertIn("length", labels)

    def test_array_variable_offers_array_methods(self):
        labels = self.members_for("let names = [1, 2];", "names")
        self.assertIn("push", labels)
        self.assertIn("map", labels)
        self.assertIn("filter", labels)

    def test_integer_variable_does_not_inherit_array_members(self):
        labels = self.members_for("let count = 0;", "count")
        self.assertIn("toString", labels)
        self.assertNotIn("length", labels)
        self.assertNotIn("push", labels)

    def test_boolean_variable_offers_only_sensible_members(self):
        labels = self.members_for("let flag = true;", "flag")
        self.assertIn("toString", labels)
        self.assertNotIn("length", labels)

    def test_object_variable_offers_object_members(self):
        labels = self.members_for("let obj = {};", "obj")
        self.assertIn("keys", labels)
        self.assertIn("values", labels)
        self.assertIn("isEmpty", labels)

    def test_annotated_variable_uses_the_annotation(self):
        labels = self.members_for("let s: string = \"hi\";", "s")
        self.assertIn("toUpperCase", labels)

    def test_class_variable_still_offers_class_fields(self):
        from lsprotocol.types import TextDocumentIdentifier

        from server import completions

        source = (
            "class Point {\n"
            "    integer x;\n"
            "    integer y;\n"
            "}\n"
            "any function f() {\n"
            "    let p = new Point();\n"
            "    p.\n"
            "}\n"
        )
        server = XLanguageServer()
        uri = "file:///class-member.x"
        server.documents[uri] = source
        result = completions(
            server,
            CompletionParams(
                text_document=TextDocumentIdentifier(uri=uri),
                position=Position(line=6, character=6),
            ),
        )
        labels = [item.label for item in result["items"]]
        self.assertIn("x", labels)
        self.assertIn("y", labels)


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class TypedHoverTests(unittest.TestCase):
    """Hover resolves declared names to their declarations."""

    SOURCE = """\
export type SettingsKey = "theme" | "backup";
export const object<SettingsKey, string> DEFAULT_SETTINGS = {
    theme: "system"
};
export string function getSetting(SettingsKey key) {
    return DEFAULT_SETTINGS.theme;
}
"""

    def test_hover_on_declared_const_shows_annotation(self):
        display, _ = _find_declaration(self.SOURCE, "DEFAULT_SETTINGS")
        self.assertIn("object<SettingsKey, string>", display)
        self.assertIn("DEFAULT_SETTINGS", display)

    def test_hover_on_type_alias_and_function(self):
        self.assertIn("SettingsKey", _find_declaration(self.SOURCE, "SettingsKey")[0])
        display, _ = _find_declaration(self.SOURCE, "getSetting")
        self.assertIn("function getSetting", display)
        self.assertIn("SettingsKey key", display)

    def test_hover_on_parameter_shows_its_annotation(self):
        display, _ = _find_declaration(self.SOURCE, "key")
        self.assertEqual(display, "SettingsKey key")

    def test_hover_on_unknown_word_is_none(self):
        self.assertIsNone(_find_declaration(self.SOURCE, "nosuchname"))


class MemberCompletionTests(unittest.TestCase):
    """``receiver.`` offers the receiver class's fields and methods."""

    SOURCE = """\
class Point {
    public integer x;
    public integer y;
    public integer function mag() { return x; }
}

class Circle {
    public float r;
    public float function area() { return r; }
}

any function main() {
    let p = new Point();
    print(p.);
}
"""

    def items_at(self, line, character):
        from lsprotocol.types import CompletionParams, Position, TextDocumentIdentifier

        from server import completions

        ls = XLanguageServer()
        uri = "file:///member-demo.x"
        ls.documents[uri] = self.SOURCE
        result = completions(
            ls,
            CompletionParams(
                text_document=TextDocumentIdentifier(uri=uri),
                position=Position(line=line, character=character),
            ),
        )
        return result["items"] if isinstance(result, dict) else result

    def test_receiver_dot_offers_only_that_class_members(self):
        items = self.items_at(13, 14)  # cursor inside `print(p.);`
        labels = [item.label for item in items]
        self.assertEqual(labels, ["x", "y", "mag"])

    def test_members_are_tagged_with_their_class(self):
        details = {item.label: item.detail for item in self.items_at(13, 14)}
        self.assertEqual(details["x"], "Point.integer x")
        self.assertEqual(details["mag"], "Point.integer function mag(...)")


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class BuiltinCollectionCompletionTests(unittest.TestCase):
    """`m.` after `new HashMap()` offers the collection's instance methods,
    including when the constructor is spelled as a full dotted path
    (`new System.utils.Collections.HashMap()`)."""

    def items_at(self, source, line, character):
        from lsprotocol.types import CompletionParams, Position, TextDocumentIdentifier

        from server import completions

        ls = XLanguageServer()
        uri = "file:///collections.x"
        ls.documents[uri] = source
        result = completions(
            ls,
            CompletionParams(
                text_document=TextDocumentIdentifier(uri=uri),
                position=Position(line=line, character=character),
            ),
        )
        return result["items"] if isinstance(result, dict) else result

    def test_short_new_offers_collection_methods(self):
        source = "any function f() {\n    let m = new HashMap()\n    m.\n}\n"
        labels = [item.label for item in self.items_at(source, 2, 6)]
        self.assertIn("set", labels)
        self.assertIn("get", labels)
        self.assertIn("entries", labels)
        self.assertNotIn("create", labels)

    def test_dotted_new_path_infers_collection_type(self):
        source = (
            "any function f() {\n"
            "    let m = new System.utils.Collections.HashMap()\n"
            "    m.\n"
            "}\n"
        )
        labels = [item.label for item in self.items_at(source, 2, 6)]
        self.assertIn("set", labels)
        self.assertIn("keys", labels)

    def test_set_offers_set_algebra_methods(self):
        source = "any function f() {\n    let s = new Set()\n    s.\n}\n"
        labels = [item.label for item in self.items_at(source, 2, 6)]
        self.assertIn("union", labels)
        self.assertIn("intersection", labels)
        self.assertNotIn("contains", labels)


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class ImportEditTests(unittest.TestCase):
    """``_import_edit`` inserts after the last import, or at the top."""

    def test_inserts_at_top_when_no_imports(self):
        edit = _import_edit("let x = 1;\n", "utils.greet")
        self.assertEqual(edit.new_text, "import utils.greet\n")
        self.assertEqual(edit.range.start.line, 0)
        self.assertEqual(edit.range.start.character, 0)
        self.assertEqual(edit.range.end.line, 0)
        self.assertEqual(edit.range.end.character, 0)

    def test_inserts_after_the_last_import(self):
        edit = _import_edit("import System.io.Console\n\nlet x = 1;\n", "utils.greet")
        self.assertEqual(edit.new_text, "import utils.greet\n")
        self.assertEqual(edit.range.start.line, 1)

    def test_existing_import_returns_none(self):
        self.assertIsNone(_import_edit("import utils.greet\n", "utils.greet"))

    def test_import_mentioned_only_in_a_comment_still_inserts(self):
        edit = _import_edit("// import utils.greet\nlet x = 1;\n", "utils.greet")
        self.assertIsNotNone(edit)
        self.assertEqual(edit.new_text, "import utils.greet\n")
        self.assertEqual(edit.range.start.line, 0)


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class AutoImportCompletionTests(unittest.TestCase):
    """Exported names of local modules complete with an auto-import edit."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls._tmp = tempfile.TemporaryDirectory(prefix="x-lsp-autoimport-")
        cls.directory = cls._tmp.name
        with open(os.path.join(cls.directory, "utils.x"), "w", encoding="utf-8") as fh:
            fh.write(
                'export string function greet(string name) {\n'
                '  return "hi " + name;\n'
                '}\n'
                'export class Widget {\n'
                '  string name;\n'
                '}\n'
            )
        cls.server = XLanguageServer()
        cls.uri = "file://" + os.path.join(cls.directory, "main.x")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def items(self, source, line, character, declared=None):
        return _auto_import_items(
            self.server, self.uri, source, line, character, declared or set()
        )

    def test_exported_name_is_offered_with_an_import_edit(self):
        source = "function main() {\n  print(gre\n}\n"
        items = self.items(source, 1, 10)
        self.assertEqual([item.label for item in items], ["greet"])
        item = items[0]
        self.assertEqual(item.kind, CompletionItemKind.Reference)
        self.assertEqual(item.detail, "import utils.greet")
        self.assertEqual(item.sort_text, "0a_greet")
        edits = item.additional_text_edits or []
        self.assertEqual([edit.new_text for edit in edits], ["import utils.greet\n"])
        self.assertEqual(edits[0].range.start.line, 0)

    def test_already_declared_name_is_skipped(self):
        source = "function main() {\n  print(gre\n}\n"
        self.assertEqual(self.items(source, 1, 10, declared={"greet"}), [])

    def test_typed_prefix_filters_candidates(self):
        source = "function main() {\n  print(Wid\n}\n"
        labels = [item.label for item in self.items(source, 1, 10)]
        self.assertIn("Widget", labels)
        self.assertNotIn("greet", labels)

    def test_whole_module_import_skips_its_candidates(self):
        source = "import utils\nfunction main() {\n  print(gre\n}\n"
        self.assertEqual(self.items(source, 2, 10), [])

    def test_no_word_at_cursor_returns_no_items(self):
        self.assertEqual(self.items("let x = ;\n", 0, 8), [])

    def test_completion_handler_includes_auto_import_items(self):
        from lsprotocol.types import CompletionParams, TextDocumentIdentifier

        from server import completions

        source = "function main() {\n  print(gre\n}\n"
        self.server.documents[self.uri] = source
        result = completions(
            self.server,
            CompletionParams(
                text_document=TextDocumentIdentifier(uri=self.uri),
                position=Position(line=1, character=10),
            ),
        )
        labels = [item.label for item in result["items"]]
        self.assertIn("greet", labels)


@unittest.skipUnless(AVAILABLE, "pygls/lsprotocol is not installed")
class CodeActionTests(unittest.TestCase):
    """Checker ``add `import …` `` helps become quick-fix code actions."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls._tmp = tempfile.TemporaryDirectory(prefix="x-lsp-codeaction-")
        cls.directory = cls._tmp.name
        with open(os.path.join(cls.directory, "utils.x"), "w", encoding="utf-8") as fh:
            fh.write(
                'export string function greet(string name) {\n'
                '  return "hi " + name;\n'
                '}\n'
            )
        cls.server = XLanguageServer()
        cls.uri = "file://" + os.path.join(cls.directory, "main.x")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def actions_for(self, source, helps):
        from lsprotocol.types import (
            CodeActionContext,
            CodeActionParams,
            TextDocumentIdentifier,
        )

        self.server.documents[self.uri] = source
        diagnostic = Diagnostic(
            range=Range(
                start=Position(line=1, character=8),
                end=Position(line=1, character=13),
            ),
            severity=DiagnosticSeverity.Error,
            message="Name 'greet' is not defined in this module",
            data={"helps": helps} if helps else None,
        )
        params = CodeActionParams(
            text_document=TextDocumentIdentifier(uri=self.uri),
            range=diagnostic.range,
            context=CodeActionContext(diagnostics=[diagnostic]),
        )
        return code_actions(self.server, params), diagnostic

    def test_import_help_becomes_a_quick_fix(self):
        actions, diagnostic = self.actions_for(
            "function main() {\n  print(greet(\"x\"));\n}\n",
            ["add `import utils.greet`"],
        )
        self.assertIsNotNone(actions)
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action.title, "Add `import utils.greet`")
        self.assertEqual(action.kind, CodeActionKind.QuickFix)
        self.assertTrue(action.is_preferred)
        self.assertEqual(action.diagnostics, [diagnostic])
        edits = action.edit.changes[self.uri]
        self.assertEqual([edit.new_text for edit in edits], ["import utils.greet\n"])
        self.assertEqual(edits[0].range.start.line, 0)

    def test_insertion_goes_after_existing_imports(self):
        actions, _ = self.actions_for(
            "import System.io.Console\nfunction main() {\n  print(greet(\"x\"));\n}\n",
            ["add `import utils.greet`"],
        )
        edits = actions[0].edit.changes[self.uri]
        self.assertEqual(edits[0].range.start.line, 1)

    def test_diagnostics_without_helps_yield_no_actions(self):
        actions, _ = self.actions_for("function main() {}\n", None)
        self.assertIsNone(actions)

    def test_import_already_present_yields_no_actions(self):
        actions, _ = self.actions_for(
            "import utils.greet\nfunction main() {\n  print(greet(\"x\"));\n}\n",
            ["add `import utils.greet`"],
        )
        self.assertIsNone(actions)


if __name__ == "__main__":
    unittest.main()
