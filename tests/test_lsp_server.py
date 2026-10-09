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
        _expression_completions,
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


if __name__ == "__main__":
    unittest.main()
