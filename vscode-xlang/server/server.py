"""X Language LSP Server entry point."""

import os
import re
import sys
from pathlib import Path

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if os.path.isdir(os.path.join(_REPO_ROOT, "xlang")) and _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lsprotocol.types import (
    INITIALIZE,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_REFERENCES,
    WORKSPACE_DID_CHANGE_CONFIGURATION,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
    CompletionItem,
    CompletionItemKind,
    CompletionParams,
    DefinitionParams,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidChangeWatchedFilesParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    Hover,
    HoverParams,
    InitializeParams,
    Location,
    MarkupContent,
    MarkupKind,
    Position,
    PublishDiagnosticsParams,
    Range,
    ReferenceParams,
    TextDocumentSyncKind,
)

from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path

from xlang.config import XConfig, discover_config, load_config
from xlang.lexer import Lexer
from xlang.module_loader import ModuleLoader
from xlang.parser import Parser
from xlang.typecheck.checker import TypeChecker

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[^ \t]")


class XLanguageServer(LanguageServer):
    """LSP Server for the X language."""

    def __init__(self) -> None:
        super().__init__(
            name="xlang-server",
            version="v0.1.0",
            text_document_sync_kind=TextDocumentSyncKind.Full,
        )
        self.documents: dict[str, str] = {}
        self.diagnostics_cache: dict[str, list[Diagnostic]] = {}
        self.settings: dict[str, object] = {
            "enableTypeChecking": True,
            "strictTyping": False,
        }
        self._config_cache: dict[str, XConfig] = {}

    def apply_settings(self, settings: object) -> None:
        if isinstance(settings, dict):
            self.settings.update(settings)

    def project_config(self, uri: str) -> XConfig:
        """Load the nearest ``x.toml`` for a document, mirroring the CLI."""
        directory = os.path.dirname(to_fs_path(uri)) or os.getcwd()
        cached = self._config_cache.get(directory)
        if cached is not None:
            return cached
        try:
            config = load_config(discover_config(Path(directory)))
        except Exception as error:
            print(f"Cannot read x.toml for {directory}: {error}", file=sys.stderr, flush=True)
            config = load_config(None)
        if self.settings.get("strictTyping") is True:
            config.features["strict_typing"] = True
        self._config_cache[directory] = config
        return config

    def _source(self, uri: str) -> str:
        if uri in self.documents:
            return self.documents[uri]
        try:
            return self.workspace.get_text_document(uri).source
        except Exception:
            return ""

    def _publish(self, uri: str, diagnostics: list[Diagnostic]) -> None:
        self.text_document_publish_diagnostics(
            PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
        )

    @staticmethod
    def _position(line: int | None, column: int | None) -> Position:
        return Position(
            line=max(0, (line or 1) - 1),
            character=max(0, (column or 1) - 1),
        )

    @staticmethod
    def _length(source: str, line0: int, column0: int, token_value: str | None) -> int:
        if token_value:
            return max(1, len(token_value))
        lines = source.split("\n")
        if 0 <= line0 < len(lines) and column0 < len(lines[line0]):
            match = WORD_RE.match(lines[line0], column0)
            if match:
                return max(1, match.end() - match.start())
        return 1

    @classmethod
    def _diagnostic(
        cls,
        error,
        severity: DiagnosticSeverity,
        source: str,
        source_name: str,
    ) -> Diagnostic:
        start = cls._position(getattr(error, "line", None), getattr(error, "column", None))
        token = getattr(error, "token", None)
        token_value = getattr(token, "value", None) if token is not None else None
        length = cls._length(source, start.line, start.character, token_value)
        end = Position(line=start.line, character=start.character + length)
        return Diagnostic(
            range=Range(start=start, end=end),
            severity=severity,
            message=getattr(error, "message", str(error)),
            source=source_name,
        )

    def _update_diagnostics(self, uri: str) -> None:
        """Lex, parse and type-check a document, then publish the diagnostics."""
        source = self._source(uri)
        if not source:
            self.diagnostics_cache[uri] = []
            self._publish(uri, [])
            return

        diagnostics: list[Diagnostic] = []
        try:
            config = self.project_config(uri)
            lexer = Lexer(source, uri, recover_errors=True)
            tokens = lexer.tokenize()
            for error in lexer.errors:
                diagnostics.append(self._diagnostic(error, DiagnosticSeverity.Error, source, "xlang"))

            parser = Parser(
                tokens,
                config.features,
                uri,
                recover_errors=True,
            )
            program = parser.parse()
            for error in parser.errors:
                diagnostics.append(self._diagnostic(error, DiagnosticSeverity.Error, source, "xlang"))

            if (
                not diagnostics
                and self.settings.get("enableTypeChecking", True)
                and config.enabled("type_checker")
            ):
                for error in TypeChecker().check(program, source_name=uri, config=config):
                    diagnostics.append(
                        self._diagnostic(error, DiagnosticSeverity.Error, source, "xlang")
                    )
        except Exception as error:
            print(f"Error checking {uri}: {error}", file=sys.stderr, flush=True)

        self.diagnostics_cache[uri] = diagnostics
        self._publish(uri, diagnostics)


server = XLanguageServer()


@server.feature(INITIALIZE)
def initialize(ls: XLanguageServer, params: InitializeParams) -> None:
    ls.apply_settings(params.initialization_options)


@server.feature(WORKSPACE_DID_CHANGE_CONFIGURATION)
def did_change_configuration(ls: XLanguageServer, params) -> None:
    ls.apply_settings(params.settings)
    ls._config_cache.clear()


@server.feature(WORKSPACE_DID_CHANGE_WATCHED_FILES)
def did_change_watched_files(ls: XLanguageServer, params: DidChangeWatchedFilesParams) -> None:
    ls._config_cache.clear()
    for change in params.changes:
        uri = str(change.uri)
        if uri in ls.documents:
            ls._update_diagnostics(uri)


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: XLanguageServer, params: DidOpenTextDocumentParams) -> None:
    uri = str(params.text_document.uri)
    ls.documents[uri] = params.text_document.text
    ls._update_diagnostics(uri)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: XLanguageServer, params: DidChangeTextDocumentParams) -> None:
    uri = str(params.text_document.uri)
    if params.content_changes:
        ls.documents[uri] = params.content_changes[-1].text
    ls._update_diagnostics(uri)


@server.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: XLanguageServer, params: DidCloseTextDocumentParams) -> None:
    uri = str(params.text_document.uri)
    ls.documents.pop(uri, None)
    ls.diagnostics_cache.pop(uri, None)
    ls._publish(uri, [])


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: XLanguageServer, params: DidSaveTextDocumentParams) -> None:
    ls._update_diagnostics(str(params.text_document.uri))


KEYWORDS = [
    "class", "interface", "enum", "type", "function", "let", "const", "var",
    "if", "else", "while", "for", "switch", "case", "default", "return",
    "break", "continue", "new", "import", "export", "extends", "implements",
    "public", "private", "protected", "static", "final", "abstract", "async",
    "await", "try", "catch", "finally", "throw", "match", "this", "super",
    "constructor",
]

TYPES = ["int", "string", "float", "boolean", "void", "any", "null", "undefined"]

BUILTINS = ["print", "range", "typeOf", "sleep", "input", "parseInt", "parseFloat"]

IMPORT_LINE_RE = re.compile(r"^\s*import\s+(.*)$")


def _import_completions(
    ls: XLanguageServer, uri: str, source: str, line: int, character: int
) -> list[CompletionItem] | None:
    """Return import target suggestions when the cursor sits after ``import``.

    Offers every standard-library ``System.*`` module plus local ``.x`` files
    (as dot-separated module paths), so TAB can complete imports the same way
    a package manager completes dependency paths.  Returns ``None`` when the
    cursor is not in an import statement.
    """
    lines = source.split("\n")
    if line >= len(lines):
        return None
    prefix = lines[line][:character]
    if IMPORT_LINE_RE.match(prefix) is None:
        return None

    items: list[CompletionItem] = []
    for path in sorted(ModuleLoader.STANDARD_LIBRARY_MODULES):
        items.append(
            CompletionItem(label=path, kind=CompletionItemKind.Module, detail="standard library")
        )

    try:
        fs_path = to_fs_path(uri)
    except Exception:
        fs_path = ""
    directory = os.path.dirname(fs_path) if fs_path else os.getcwd()

    seen: set[str] = set()
    for candidate in _local_x_files(ls, uri, directory):
        rel = os.path.relpath(candidate, directory)
        if rel.startswith(".."):
            continue
        module_path = rel[:-2].replace(os.sep, ".").lstrip("./")
        if not module_path or module_path in seen:
            continue
        seen.add(module_path)
        items.append(
            CompletionItem(label=module_path, kind=CompletionItemKind.File, detail=rel)
        )
    return items


def _local_x_files(ls: XLanguageServer, uri: str, directory: str) -> list[str]:
    """Resolve importable ``.x`` files near the document and in the project root."""
    roots: list[str] = [directory]
    try:
        config = ls.project_config(uri)
        if config.path is not None:
            roots.insert(0, str(config.path.parent))
    except Exception:
        pass

    found: list[str] = []
    for root in roots:
        try:
            for entry in sorted(os.walk(root)):
                folder = entry[0]
                for name in sorted(entry[2]):
                    if name.endswith(".x"):
                        found.append(os.path.join(folder, name))
        except (OSError, PermissionError):
            continue
    return found


@server.feature(TEXT_DOCUMENT_COMPLETION)
def completions(ls: XLanguageServer, params: CompletionParams):
    source = ls._source(str(params.text_document.uri))
    uri = str(params.text_document.uri)
    import_items = _import_completions(
        ls, uri, source, params.position.line, params.position.character
    )
    if import_items is not None:
        return import_items

    items = [CompletionItem(label=kw, kind=CompletionItemKind.Keyword) for kw in KEYWORDS]
    items += [CompletionItem(label=t, kind=CompletionItemKind.Class) for t in TYPES]
    items += [CompletionItem(label=f, kind=CompletionItemKind.Function) for f in BUILTINS]

    for match in re.finditer(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", source):
        items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Class))
    for match in re.finditer(r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)", source):
        items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Interface))
    for match in re.finditer(
        r"^\s*(?:public|private|protected|static|final|abstract|async|\s)*"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*(?::\s*[A-Za-z_][\w.\[\]]*)?\s*\{",
        source,
        re.MULTILINE,
    ):
        items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Method))

    return items


HOVER_INFO = {
    "print": "print(value: any): void\n\nPrints a value to stdout.",
    "range": "range(start: int, end?: int, step?: int): int[]\n\nReturns an array of numbers.",
    "typeOf": "typeOf(value: any): string\n\nReturns the type name of a value.",
    "sleep": "sleep(ms: int): Promise<void>\n\nSleeps for the specified milliseconds.",
    "input": "input(prompt?: string): string\n\nReads a line from stdin.",
    "int": "Primitive integer type.",
    "string": "Primitive string type.",
    "float": "Primitive floating-point type.",
    "boolean": "Primitive boolean type.",
    "void": "Represents no value.",
    "any": "Any type (disables type checking).",
}


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: XLanguageServer, params: HoverParams):
    source = ls._source(str(params.text_document.uri))
    lines = source.split("\n")
    line0 = params.position.line
    char0 = params.position.character
    if line0 >= len(lines) or char0 > len(lines[line0]):
        return None

    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", lines[line0]):
        start, end = match.span()
        if start <= char0 < end:
            value = HOVER_INFO.get(match.group(0))
            if value is None:
                return None
            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value=f"```x\n{value}\n```")
            )
    return None


DECL_KEYWORDS = (
    r"(?:return|if|else|while|for|switch|match|case|default|break|continue|"
    r"throw|catch|new|print)\b"
)
TYPE_TOKEN = r"[A-Za-z_][A-Za-z0-9_]*(?:\[\])*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
MODIFIERS = (
    r"(?:(?:public|private|protected|static|final|abstract|async|override|"
    r"internal)\s+)*"
)


def definition_patterns(word: str, enum_member: bool = True) -> list[re.Pattern]:
    """Ordered patterns that match where ``word`` is *declared*.

    Every pattern captures the declared name in group ``n``.  Patterns are
    ordered by confidence (type before function before method before field
    before parameter before enum member); callers decide how much of the
    buffer each pattern is allowed to see.
    """
    w = re.escape(word)
    guard = rf"^\s*(?!{DECL_KEYWORDS})"
    patterns = [
        # class / interface / enum / type alias
        re.compile(rf"\b(?:class|interface|enum|type)\s+(?P<n>{w})\b"),
        # free function: "int function add(a, b) {"
        re.compile(rf"\bfunction\s+(?P<n>{w})\s*\("),
        # method or constructor: "public void greet() {"
        re.compile(
            rf"{guard}{MODIFIERS}(?:{TYPE_TOKEN}\s+){{1,2}}"
            rf"(?P<n>{w})\s*\([^()]*\)\s*(?::[^{{]*)?\{{"
        ),
        # interface / abstract signature: "void serialize();"
        re.compile(
            rf"{guard}{MODIFIERS}{TYPE_TOKEN}\s+(?P<n>{w})\s*\([^()]*\)\s*;"
        ),
        # field or local declaration: "string name;", "int x = 5;"
        re.compile(
            rf"{guard}{MODIFIERS}{TYPE_TOKEN}\s+(?P<n>{w})"
            rf"\s*(?::[^=;]*)?(?:=[^;]*)?;"
        ),
        # let / const / var binding (also matches loop variables); the
        # delimiter guard stops the optional type token being taken as the name
        re.compile(
            rf"\b(?:let|const|var)\s+(?:{TYPE_TOKEN}\s+)?(?P<n>{w})"
            rf"(?=\s*(?:=|;|,|:|$))"
        ),
        # parameter of a declaration: >=1 token, no "=" and no nested "("
        # before the parameter list (keeps calls such as `print(x)` out); the
        # name must sit where a parameter name sits (followed by , = : or ))
        # and the list must be followed by , ; : or { (never end-of-line)
        re.compile(
            rf"{guard}{MODIFIERS}(?P<pre>(?:[^\s()={{}}]+\s+)+)"
            rf"(?P<fn>[A-Za-z_][A-Za-z0-9_]*)\s*\([^()]*\b(?P<n>{w})\b"
            rf"(?=\s*(?:,|=|:|\)))[^()]*\)\s*(?:,|;|:|\{{)"
        ),
        # bare indented member (enum entries): "ACTIVE,"
    ]
    if enum_member:
        patterns.append(re.compile(rf"^\s+(?P<n>{w})\s*,?\s*(?://.*)?$"))
    return patterns


def code_lines(source: str) -> list[str]:
    """Split `source` into lines with comments and literals blanked out.

    Blanked characters become spaces, so every line keeps its original length
    and all columns still line up with the editor.  Nothing that looks like a
    declaration inside a comment or a string can then be resolved.
    """
    out: list[str] = []
    index = 0
    total = len(source)
    while index < total:
        character = source[index]
        following = source[index + 1] if index + 1 < total else ""
        if character == "/" and following == "/":
            while index < total and source[index] != "\n":
                out.append(" ")
                index += 1
        elif character == "/" and following == "*":
            out.append("  ")
            index += 2
            while index < total and not (
                source[index] == "*"
                and index + 1 < total
                and source[index + 1] == "/"
            ):
                out.append("\n" if source[index] == "\n" else " ")
                index += 1
            if index < total:
                out.append("  ")
                index += 2
        elif character in ('"', "'", "`"):
            quote = character
            out.append(" ")
            index += 1
            while index < total and source[index] != "\n":
                if source[index] == "\\":
                    out.append(" ")
                    if index + 1 < total and source[index + 1] != "\n":
                        out.append(" ")
                        index += 2
                    else:
                        index += 1
                    continue
                if source[index] == quote:
                    out.append(" ")
                    index += 1
                    break
                out.append(" ")
                index += 1
        else:
            out.append(character)
            index += 1
    return "".join(out).split("\n")


CALLABLE_LINE = re.compile(
    rf"^\s*(?!{DECL_KEYWORDS}){MODIFIERS}(?:{TYPE_TOKEN}\s+){{1,2}}"
    rf"[A-Za-z_][A-Za-z0-9_]*\s*\([^()]*\)\s*(?::[^{{]*)?\{{\s*$"
)


def block_end(lines: list[str], opener: int) -> int:
    """Line index of the `}` matching the `{` on line `opener`."""
    depth = 0
    opened = False
    for scan in range(opener, len(lines)):
        for character in lines[scan]:
            if character == "{":
                depth += 1
                opened = True
            elif character == "}":
                depth -= 1
                if opened and depth == 0:
                    return scan
    return len(lines) - 1


def enclosing_callable(lines: list[str], line0: int) -> tuple[int, int] | None:
    """Innermost function/method/constructor body that contains `line0`."""
    for index in range(line0, -1, -1):
        if not CALLABLE_LINE.match(lines[index]):
            continue
        end = block_end(lines, index)
        if index <= line0 <= end:
            return index, end
    return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls: XLanguageServer, params: DefinitionParams):
    uri = str(params.text_document.uri)
    lines = code_lines(ls._source(uri))
    line0 = params.position.line
    char0 = params.position.character
    if line0 >= len(lines) or char0 > len(lines[line0]):
        return None

    word = None
    word_start = -1
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", lines[line0]):
        start, end = match.span()
        if start <= char0 < end:
            word = match.group(0)
            word_start = start
            break
    if word is None:
        return None

    patterns = definition_patterns(
        word, enum_member=any(re.search(r"\benum\b", text) for text in lines)
    )

    def located(line: int, column: int) -> Location:
        return Location(
            uri=uri,
            range=Range(
                start=Position(line=line, character=column),
                end=Position(line=line, character=column + len(word)),
            ),
        )

    # Clicking a name inside its own declaration must stay there, otherwise a
    # same-named field elsewhere in the file wins the file-wide search.
    for pattern in patterns:
        for match in pattern.finditer(lines[line0]):
            if match.start("n") == word_start:
                return located(line0, match.start("n"))

    # Inside a function body, prefer a declaration from that function (this is
    # what makes parameter usages land on the parameter list).
    block = enclosing_callable(lines, line0)
    if block is not None:
        start, end = block
        for pattern in patterns:
            for index in range(start, end + 1):
                match = pattern.search(lines[index])
                if match:
                    return located(index, match.start("n"))

    for pattern in patterns:
        for index, text in enumerate(lines):
            match = pattern.search(text)
            if match:
                return located(index, match.start("n"))
    return None


@server.feature(TEXT_DOCUMENT_REFERENCES)
def references(ls: XLanguageServer, params: ReferenceParams):
    return []


if __name__ == "__main__":
    server.start_io()
