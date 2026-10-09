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
    CompletionOptions,
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
    TextEdit,
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

BUILTINS = ["print", "range", "typeOf", "delete", "sleep", "input", "parseInt", "parseFloat"]

IMPORT_LINE_RE = re.compile(r"^\s*import\s+(.*)$")
DOTTED_EXPRESSION_RE = re.compile(
    r"(?P<path>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\.$"
)

_SKIPPED_DIRECTORIES = {
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "build",
    "dist",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "site-packages",
}

_EXPORT_CACHE: dict[str, tuple[float, list[str]]] = {}


def _matches_consecutively(label_parts: list[str], typed_parts: list[str]) -> bool:
    if len(label_parts) < len(typed_parts):
        return False
    return all(
        label_parts[index].startswith(part)
        for index, part in enumerate(typed_parts)
    )


def _module_matches(typed: str, label: str) -> bool:
    """Segment-wise match between what was typed and a module path.

    Typed segments line up with the leading segments of ``label``; only the
    segment being typed may sit below skipped namespaces, so ``System.M``
    still reaches ``System.utils.Math`` while ``System.io.`` stops offering
    ``System.Throwable.Exception.IOException``.  VS Code re-filters with its
    own fuzzy scorer, so this only has to avoid dropping candidates a human
    would expect to see.
    """
    typed_lower = typed.lower()
    if not typed_lower:
        return True
    typed_parts = typed_lower.split(".")
    if typed_parts and typed_parts[-1] == "":
        typed_parts.pop()
        if not typed_parts:
            return True
        return _matches_consecutively(label.lower().split("."), typed_parts)

    label_parts = label.lower().split(".")
    if _matches_consecutively(label_parts, typed_parts):
        return True
    if len(typed_parts) == 1:
        return any(part.startswith(typed_parts[0]) for part in label_parts)
    if not _matches_consecutively(label_parts, typed_parts[:-1]):
        return False
    last = typed_parts[-1]
    return any(
        part.startswith(last) for part in label_parts[len(typed_parts) - 1 :]
    )


def _stdlib_candidates() -> set[str]:
    """Every importable standard-library path plus its namespace prefixes."""
    candidates: set[str] = set()
    for path in ModuleLoader.STANDARD_LIBRARY_MODULES:
        parts = path.split(".")
        for depth in range(1, len(parts) + 1):
            candidates.add(".".join(parts[:depth]))
    return candidates


def _exported_names(path: str, features: dict) -> list[str]:
    """Names declared with ``export`` in a local ``.x`` file, cached by mtime."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    cached = _EXPORT_CACHE.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    names: list[str] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
        program = Parser(
            Lexer(text, path, recover_errors=True).tokenize(),
            features,
            path,
            recover_errors=True,
        ).parse()
    except Exception:
        program = None

    if program is not None:
        for declaration in program.declarations:
            if "export" not in getattr(declaration, "modifiers", set()):
                continue
            name = getattr(declaration, "name", None)
            if isinstance(name, str) and name and name not in names:
                names.append(name)

    _EXPORT_CACHE[path] = (mtime, names)
    return names


def _project_root(ls: XLanguageServer, uri: str) -> str | None:
    try:
        config = ls.project_config(uri)
    except Exception:
        return None
    if config.path is None:
        return None
    return str(config.path.parent)


def _local_modules(
    ls: XLanguageServer, uri: str, directory: str, self_path: str
) -> list[tuple[str, str, str]]:
    """Importable local modules as ``(module_path, file_path, display)``.

    Paths are reported relative to the document folder first (that is where
    the module loader looks first) and then relative to the project root, so a
    file outside the current folder still completes with a resolvable path.
    """
    roots: list[str] = []
    if directory:
        roots.append(directory)
    project_root = _project_root(ls, uri)
    if project_root and project_root not in roots:
        roots.append(project_root)

    self_path = os.path.abspath(self_path) if self_path else ""
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for root in roots:
        try:
            walker = os.walk(root)
            for folder, subfolders, names in walker:
                subfolders[:] = sorted(
                    name
                    for name in subfolders
                    if name not in _SKIPPED_DIRECTORIES and not name.startswith(".")
                )
                for name in sorted(names):
                    if not name.endswith(".x"):
                        continue
                    full_path = os.path.join(folder, name)
                    if os.path.abspath(full_path) == self_path:
                        continue
                    relative = os.path.relpath(full_path, root)
                    if relative.startswith(".."):
                        continue
                    module_path = relative[:-2].replace(os.sep, ".").replace("/", ".")
                    if not module_path or module_path in seen:
                        continue
                    seen.add(module_path)
                    found.append((module_path, full_path, relative))
        except (OSError, PermissionError):
            continue
    found.sort(key=lambda entry: entry[0])
    return found


def _module_completion_items(
    ls: XLanguageServer,
    uri: str,
    typed: str,
    line: int,
    character: int,
    start_col: int,
    stdlib_paths: set[str],
    include_local: bool = True,
) -> list[CompletionItem]:
    """Build completion items for a dotted module path ending at the cursor."""

    def _edit(label: str) -> TextEdit:
        return TextEdit(
            range=Range(
                start=Position(line=line, character=start_col),
                end=Position(line=line, character=character),
            ),
            new_text=label,
        )

    items: list[CompletionItem] = []
    typed_root = typed[:-1] if typed.endswith(".") else typed
    seen: set[str] = set()

    def _add(label: str, kind: CompletionItemKind, detail: str) -> None:
        if label in seen or not _module_matches(typed, label):
            return
        if typed.endswith(".") and label.lower() == typed_root.lower():
            return  # never replace "System." with the shorter "System"
        seen.add(label)
        items.append(
            CompletionItem(
                label=label,
                kind=kind,
                detail=detail,
                filter_text=label,
                text_edit=_edit(label),
            )
        )

    for path in sorted(stdlib_paths):
        _add(path, CompletionItemKind.Module, "standard library")

    if not include_local:
        return items

    try:
        fs_path = to_fs_path(uri)
    except Exception:
        fs_path = ""
    directory = os.path.dirname(fs_path) if fs_path else ""
    features = {}
    try:
        features = dict(ls.project_config(uri).features)
    except Exception:
        features = {}

    for module_path, full_path, display in _local_modules(ls, uri, directory, fs_path):
        _add(module_path, CompletionItemKind.File, display)
        for name in _exported_names(full_path, features):
            _add(f"{module_path}.{name}", CompletionItemKind.Function, display)
    return items


def _import_completions(
    ls: XLanguageServer, uri: str, source: str, line: int, character: int
) -> list[CompletionItem] | None:
    """Return import target suggestions when the cursor sits after ``import``.

    Offers every standard-library ``System.*`` module, every local ``.x``
    file (as a dot-separated module path) and the exported declarations of
    those files, so ``import utils.`` can complete straight to ``utils.greet``.
    Returns ``None`` when the cursor is not in an import statement.
    """
    lines = source.split("\n")
    if line >= len(lines):
        return None
    prefix = lines[line][:character]
    match = IMPORT_LINE_RE.match(prefix)
    if match is None:
        return None

    typed = lines[line][match.start(1) : character].strip().strip('"').strip("'")
    return _module_completion_items(
        ls,
        uri,
        typed,
        line,
        character,
        match.start(1),
        stdlib_paths=ModuleLoader.STANDARD_LIBRARY_MODULES,
        include_local=True,
    )


def _expression_completions(
    ls: XLanguageServer, uri: str, source: str, line: int, character: int
) -> list[CompletionItem] | None:
    """Return ``System.*`` namespace suggestions after a dotted expression."""
    lines = source.split("\n")
    if line >= len(lines):
        return None
    match = DOTTED_EXPRESSION_RE.search(lines[line][:character])
    if match is None:
        return None
    typed = match.group("path") + "."
    if not typed.lower().startswith("system."):
        return None
    items = _module_completion_items(
        ls,
        uri,
        typed,
        line,
        character,
        match.start("path"),
        stdlib_paths=_stdlib_candidates(),
        include_local=False,
    )
    return items or None


@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(trigger_characters=["."]),
)
def completions(ls: XLanguageServer, params: CompletionParams):
    source = ls._source(str(params.text_document.uri))
    uri = str(params.text_document.uri)
    import_items = _import_completions(
        ls, uri, source, params.position.line, params.position.character
    )
    if import_items is not None:
        return {"items": import_items, "isIncomplete": False}

    expression_items = _expression_completions(
        ls, uri, source, params.position.line, params.position.character
    )
    if expression_items:
        return {"items": expression_items, "isIncomplete": False}

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

    return {"items": items, "isIncomplete": False}


HOVER_INFO = {
    "print": "print(value: any): void\n\nPrints a value to stdout.",
    "range": "range(start: int, end?: int, step?: int): int[]\n\nReturns an array of numbers.",
    "typeOf": "typeOf(value: any): string\n\nReturns the type name of a value.",
    "delete": (
        "delete(target: any): boolean\n\n"
        "Removes one object key and its value, splices out one array element "
        "(the array shrinks), or drops one field of a class instance. "
        "Declared as Object.delete; returns true. Deleting a target that is "
        "not there raises the same error reading it would raise."
    ),
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
