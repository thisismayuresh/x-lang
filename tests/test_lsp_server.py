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
    from lsprotocol.types import CompletionItemKind, CompletionParams, Position

    from server import (  # noqa: E402
        XLanguageServer,
        _declared_symbols,
        _expression_completions,
        _find_declaration,
        _import_completions,
        _module_matches,
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

    def test_object_variable_offers_no_builtin_fiction(self):
        # Plain object literals answer only field reads at runtime
        # (`obj.keys()` raises "Object has no field 'keys'"), so the popup
        # must not advertise Object.keys/values/isEmpty as instance members.
        labels = self.members_for("let obj = {};", "obj")
        self.assertNotIn("keys", labels)
        self.assertNotIn("values", labels)
        self.assertNotIn("isEmpty", labels)

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


if __name__ == "__main__":
    unittest.main()
