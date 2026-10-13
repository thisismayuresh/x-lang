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
        """Lex, parse and type-check a document, then publish the diagnostics.

        The document is loaded through :class:`ModuleLoader` so that imported
        interfaces, classes and functions are visible to the type checker —
        the same way ``x check`` works.  The unsaved editor buffer overrides
        the on-disk entry file, and any other open buffers override their own
        files.  Only diagnostics belonging to this document are published.
        """
        source = self._source(uri)
        if not source:
            self.diagnostics_cache[uri] = []
            self._publish(uri, [])
            return

        diagnostics: list[Diagnostic] = []
        entry_path = Path(to_fs_path(uri)).resolve()
        try:
            config = self.project_config(uri)

            # Every open buffer is an override so cross-file checks see
            # unsaved edits, not stale disk contents.
            overrides: dict[Path, str] = {}
            for open_uri, open_source in self.documents.items():
                overrides[Path(to_fs_path(open_uri)).resolve()] = open_source

            project_root = config.path.parent if config.path is not None else entry_path.parent
            loader = ModuleLoader(
                project_root, config, recover_errors=True, source_overrides=overrides
            )
            try:
                program = loader.load_program(entry_path)
            except Exception as error:
                diagnostics.append(self._diagnostic(error, DiagnosticSeverity.Error, source, "xlang"))
                self.diagnostics_cache[uri] = diagnostics
                self._publish(uri, diagnostics)
                return

            # Loader lex/parse errors, scoped to this document only.
            for error in loader.errors:
                if self._error_in_file(error, entry_path):
                    diagnostics.append(self._diagnostic(error, DiagnosticSeverity.Error, source, "xlang"))

            if (
                not diagnostics
                and self.settings.get("enableTypeChecking", True)
                and config.enabled("type_checker")
            ):
                for error in TypeChecker().check(program, source_name=str(entry_path), config=config):
                    if self._error_in_file(error, entry_path):
                        diagnostics.append(
                            self._diagnostic(error, DiagnosticSeverity.Error, source, "xlang")
                        )
        except Exception as error:
            print(f"Error checking {uri}: {error}", file=sys.stderr, flush=True)

        self.diagnostics_cache[uri] = diagnostics
        self._publish(uri, diagnostics)

    @staticmethod
    def _error_in_file(error: object, entry_path: Path) -> bool:
        """True when a lex/parse/type error belongs to ``entry_path``.

        Diagnostics from imported modules are dropped here so a document only
        shows its own problems; each imported file gets its own diagnostics
        when it is opened.
        """
        source_name = getattr(error, "source_name", None)
        if not source_name:
            return True
        try:
            return Path(source_name).resolve() == entry_path
        except Exception:
            return str(source_name) == str(entry_path)


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


# --------------------------------------------------------------------------
# Declared symbols: completions and hover for names in the buffer
# --------------------------------------------------------------------------

_TYPE_TEXT = r"[A-Za-z_][\w.]*(?:<[^=;{}]*>)?(?:\[\])*"
_MODIFIERS_RE = r"(?:(?:public|private|protected|static|final|abstract|async|override|internal|export)\s+)*"

VARIABLE_DECL_RE = re.compile(
    rf"^\s*{_MODIFIERS_RE}"
    rf"(?P<binding>let|const|var)\s+"
    rf"(?:(?P<type>{_TYPE_TEXT})\s+)?"
    rf"(?P<name>[A-Za-z_]\w*)"
    rf"\s*(?::\s*(?P<colon>[^=;]+))?"
    rf"\s*(?:=|;|,|$)"
)

FUNCTION_DECL_RE = re.compile(
    rf"^\s*{_MODIFIERS_RE}"
    rf"(?P<return>{_TYPE_TEXT})\s+function\s*"
    rf"(?:<(?P<generics>[^>]*)>)?\s*"
    rf"(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^)]*)\)"
)

TYPE_DECL_RE = re.compile(
    rf"^\s*{_MODIFIERS_RE}"
    rf"(?P<kind>class|interface|enum|type)\s+(?P<name>[A-Za-z_]\w*)"
)

IMPORT_DECL_RE = re.compile(
    r"^\s*import\s+(?P<path>[A-Za-z_][\w.]*)"
    r"(?:\.(?P<braced>\{(?P<names>[^}]*)\})|(?P<single>\.\s*(?P<one>[A-Za-z_]\w*)))?"
)

_TYPE_KIND = {
    "class": CompletionItemKind.Class,
    "interface": CompletionItemKind.Interface,
    "enum": CompletionItemKind.Enum,
    "type": CompletionItemKind.Struct,
}


_INIT_STRING_RE = re.compile(r"""^["'`]""")
_INIT_INT_RE = re.compile(r"^-?\d+\s*($|[^.0-9])")
_INIT_FLOAT_RE = re.compile(r"^-?\d+\.\d+\s*$")
_INIT_BOOL_RE = re.compile(r"^(true|false)\s*$")
_INIT_ARRAY_RE = re.compile(r"^\[")
_INIT_OBJECT_RE = re.compile(r"^\{")
_INIT_NEW_RE = re.compile(r"^new\s+([A-Za-z_][\w.]*)")
_INIT_IDENT_RE = re.compile(r"^([A-Za-z_]\w*)$")


def _infer_initializer_type(
    initializer: str, source: str, _depth: int = 0
) -> str | None:
    """Best-effort type of an ``= ...`` initializer, mirroring the playground.

    Covers literals, ``new Ctor(...)``, and identifier-to-identifier copy so an
    un-annotated ``let count = 0;`` still shows ``integer`` in the popup.
    """
    value = initializer.strip()
    if not value:
        return None
    if _INIT_STRING_RE.match(value):
        return "string"
    if _INIT_FLOAT_RE.match(value):
        return "float"
    if _INIT_INT_RE.match(value):
        return "integer"
    if _INIT_BOOL_RE.match(value):
        return "boolean"
    if _INIT_ARRAY_RE.match(value):
        return "array"
    if _INIT_OBJECT_RE.match(value):
        return "object"
    new_call = _INIT_NEW_RE.match(value)
    if new_call:
        # `new System.utils.Collections.HashMap()` -> `HashMap`, so the
        # builtin-member catalog matches the short type name.
        return new_call.group(1).split(".")[-1]
    if _depth >= 4:
        return None
    ident = _INIT_IDENT_RE.match(value)
    if ident:
        inner = ident.group(1)
        for raw in source.split("\n"):
            match = VARIABLE_DECL_RE.search(raw)
            if match and match.group("name") == inner:
                annotation = match.group("colon") or match.group("type")
                if annotation:
                    return annotation.strip()
                init = raw.split("=", 1)
                if len(init) == 2:
                    inferred = _infer_initializer_type(
                        init[1].rstrip(";"), source, _depth + 1
                    )
                    if inferred:
                        return inferred
    return None


def _declared_symbols(source: str) -> list[CompletionItem]:
    """Completion items for every name declared in *source*.

    Harvests X-style bindings (``let object<K, string> NAME = ...`` and the
    colon spelling), functions, classes/interfaces/enums/type aliases, and
    imported names — with the declaration as the item's ``detail`` so the
    popup shows the type.
    """
    items: list[CompletionItem] = []
    seen: set[str] = set()
    raw_lines = source.split("\n")

    def add(label: str, kind: CompletionItemKind, detail: str, doc: str) -> None:
        if not label or label in seen:
            return
        seen.add(label)
        items.append(
            CompletionItem(
                label=label,
                kind=kind,
                detail=detail,
                documentation=doc,
                sort_text="0_" + label,
            )
        )

    for line0, line in enumerate(code_lines(source)):
        match = FUNCTION_DECL_RE.search(line)
        if match:
            signature = line.strip()
            for stop in ("{", ";"):
                cut = signature.find(stop)
                if cut >= 0:
                    signature = signature[:cut].rstrip()
            label = match.group("name")
            add(
                label,
                CompletionItemKind.Function,
                signature or label,
                "declared in this file",
            )
            continue
        match = VARIABLE_DECL_RE.search(line)
        if match:
            name = match.group("name")
            annotation = match.group("colon") or match.group("type")
            binding = match.group("binding")
            kind = (
                CompletionItemKind.Constant
                if binding == "const"
                else CompletionItemKind.Variable
            )
            detail = f"{binding} {annotation} {name}".strip() if annotation else f"{binding} {name}"
            if not annotation:
                raw = raw_lines[line0] if line0 < len(raw_lines) else line
                init_match = re.search(r"=\s*([^;]+)", raw)
                if init_match:
                    inferred = _infer_initializer_type(init_match.group(1), source)
                    if inferred:
                        detail = f"{binding} {inferred} {name}"
            add(name, kind, detail, "declared in this file")
            continue
        match = TYPE_DECL_RE.search(line)
        if match:
            kind = _TYPE_KIND.get(match.group("kind"), CompletionItemKind.Struct)
            header = line.strip()
            for stop in ("{", ";", "="):
                cut = header.find(stop)
                if cut >= 0:
                    header = header[:cut].rstrip()
            add(match.group("name"), kind, header or match.group("name"), "declared in this file")
            continue
        match = IMPORT_DECL_RE.search(line)
        if match:
            path = match.group("path")
            names: list[str] = []
            if match.group("names"):
                names = [
                    piece.strip().split()[-1]
                    for piece in match.group("names").split(",")
                    if piece.strip()
                ]
            elif match.group("one"):
                names = [match.group("one")]
            for name in names:
                add(
                    name,
                    CompletionItemKind.Reference,
                    f"imported from {path}",
                    f"`import {path}`",
                )
    return items


def _split_top_level(text: str) -> list[str]:
    """Split *text* on commas that sit outside ``<...>`` nesting."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for character in text:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(0, depth - 1)
        if character == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    if current:
        parts.append("".join(current))
    return parts


def _declaration_display(raw_line: str, word: str, is_parameter: bool) -> str | None:
    """Human-readable declaration text for *word* on *raw_line*."""
    if is_parameter:
        open_paren = raw_line.find("(")
        close_paren = raw_line.find(")", open_paren + 1) if open_paren >= 0 else -1
        if open_paren >= 0 and close_paren > open_paren:
            for part in _split_top_level(raw_line[open_paren + 1 : close_paren]):
                tokens = part.strip().split()
                if tokens and tokens[-1] == word:
                    return " ".join(tokens)
    text = raw_line.strip()
    cuts = [
        index
        for stop in ("{", ";", "=")
        if (index := text.find(stop)) >= 0
    ]
    if cuts:
        text = text[: min(cuts)].rstrip()
    return text or None


def _find_declaration(source: str, word: str) -> tuple[str, int] | None:
    """Locate the first declaration of *word*; return (display, line0)."""
    blanked_lines = code_lines(source)
    raw_lines = source.split("\n")
    for pattern in definition_patterns(word):
        parameter_pattern = "fn" in pattern.groupindex
        for line0, blanked in enumerate(blanked_lines):
            match = pattern.search(blanked)
            if match is None:
                continue
            display = _declaration_display(
                raw_lines[line0], word, parameter_pattern
            )
            if display:
                return display, line0
    return None


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

    member_items = _member_completions(
        ls, uri, source, params.position.line, params.position.character
    )
    if member_items:
        return {"items": member_items, "isIncomplete": False}

    items = _declared_symbols(source)
    declared = {item.label for item in items}
    items += [
        CompletionItem(label=kw, kind=CompletionItemKind.Keyword, sort_text="2_" + kw)
        for kw in KEYWORDS
        if kw not in declared
    ]
    items += [
        CompletionItem(label=t, kind=CompletionItemKind.Class, sort_text="2_" + t)
        for t in TYPES
        if t not in declared
    ]
    items += [
        CompletionItem(label=f, kind=CompletionItemKind.Function, sort_text="1_" + f)
        for f in BUILTINS
        if f not in declared
    ]

    for match in re.finditer(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", source):
        if match.group(1) not in declared:
            items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Class))
    for match in re.finditer(r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)", source):
        if match.group(1) not in declared:
            items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Interface))
    for match in re.finditer(
        r"^\s*(?:public|private|protected|static|final|abstract|async|\s)*"
        r"([A-Za-z_][A-Za-z_0-9]*)\s*\([^;]*\)\s*(?::\s*[A-Za-z_][\w.\[\]]*)?\s*\{",
        source,
        re.MULTILINE,
    ):
        if match.group(1) not in declared:
            items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Method))

    _add_class_members(source, items)
    return {"items": items, "isIncomplete": False}


_FIELD_DECL_RE = re.compile(
    r"^[ \t]*(?:public|private|protected|static|final|abstract|async|export|const|let|var)*\s*"
    r"(?P<type>[A-Za-z_][\w.\[\]<>?, ]*?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;[ \t]*$"
)
_METHOD_DECL_RE = re.compile(
    r"^[ \t]*(?:public|private|protected|static|final|abstract|async|export|const|let|var)*\s*"
    r"(?P<type>[A-Za-z_][\w.\[\]<>?, ]*?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*\([^)]*\)"
)
_CLASS_START_RE = re.compile(
    r"^[ \t]*class\s+(?P<name>[A-Za-z_]\w*)\b[^\n{]*\{"
)


def _add_class_members(source: str, items: list[CompletionItem]) -> None:
    """Offer fields and methods of every ``class`` in *source*.

    A member's ``detail`` is prefixed with its declaring class, so after
    ``let p = new Point();`` the popup for ``p.`` still shows ``Point.x``.
    """
    raw_lines = source.split("\n")
    declared = {item.label for item in items}
    open_classes: list[str] = []

    for raw in raw_lines:
        start = _CLASS_START_RE.match(raw)
        if start:
            open_classes.append(start.group("name"))
            continue

        if not open_classes:
            continue

        stripped = raw.strip()
        if stripped == "}":
            if open_classes:
                open_classes.pop()
            continue

        field = _FIELD_DECL_RE.match(raw)
        if field and field.group("name") not in ("return", "new", "let", "const"):
            name = field.group("name")
            if name in declared:
                continue
            declared.add(name)
            items.append(
                CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Field,
                    detail=f"{open_classes[-1]}.{field.group('type').strip()} {name}",
                    documentation="field",
                )
            )
            continue

        method = _METHOD_DECL_RE.match(raw)
        if method:
            name = method.group("name")
            if name in declared:
                continue
            declared.add(name)
            items.append(
                CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Method,
                    detail=f"{open_classes[-1]}.{method.group('type').strip()} {name}(...)",
                    documentation="method",
                )
            )


_RECEIVER_RE = re.compile(r"([A-Za-z_]\w*)\s*\.(?:[A-Za-z_]\w*)?$")


def _var_static_type(source: str, name: str) -> str | None:
    """Declared or initializer type of local *name*, e.g. ``Point`` for
    ``let p = new Point();``."""
    for raw in source.split("\n"):
        m = VARIABLE_DECL_RE.search(raw)
        if m and m.group("name") == name:
            annotation = m.group("colon") or m.group("type")
            if annotation:
                return annotation.strip().lstrip("?").strip()
            init = re.search(r"=\s*([^;]+)", raw)
            if init:
                # Literals first: `true`/`false` also match the bare-identifier
                # pattern below, so booleans must be checked before the
                # identifier-to-identifier copy. `_infer_initializer_type`
                # also covers `new Ctor(...)` incl. dotted paths like
                # `new System.utils.Collections.HashMap()`.
                inferred = _infer_initializer_type(init.group(1), source)
                if inferred:
                    return inferred
                ident = re.match(r"^\s*([A-Za-z_]\w*)\s*$", init.group(1))
                if ident:
                    return _var_static_type(source, ident.group(1))
    return None


# Members offered after a `.` for built-in and stdlib receiver types. The
# playground keeps the same map in `docs-site/playground/completions.js`;
# keep the two in sync when adding entries.
_BUILTIN_MEMBERS: dict[str, list[tuple[str, str, str]]] = {
    "*": [
        ("length", "property", "size of array/string"),
        ("size", "method", "collection size()"),
        ("toString", "method", "stringify value"),
        ("message", "property", "exception message"),
        ("name", "property", "type / exception name"),
    ],
    "string": [
        ("toUpperCase", "method", "toUpperCase()"),
        ("toLowerCase", "method", "toLowerCase()"),
        ("trim", "method", "trim()"),
        ("includes", "method", "includes(text)"),
        ("indexOf", "method", "indexOf(text)"),
        ("slice", "method", "slice(start, end)"),
        ("substring", "method", "substring(start, end)"),
        ("split", "method", "split(separator)"),
        ("replace", "method", "replace(from, to)"),
        ("charAt", "method", "charAt(index)"),
        ("length", "property", "character count"),
    ],
    "array": [
        ("length", "property", "element count"),
        ("push", "method", "push(value)"),
        ("pop", "method", "pop()"),
        ("map", "method", "map(callback)"),
        ("filter", "method", "filter(callback)"),
        ("reduce", "method", "reduce(callback, init)"),
        ("join", "method", "join(separator)"),
        ("slice", "method", "slice(start, end)"),
        ("indexOf", "method", "indexOf(value)"),
        ("contains", "method", "contains(value)"),
        ("isEmpty", "method", "isEmpty()"),
    ],
    "object": [
        ("keys", "method", "keys()"),
        ("values", "method", "values()"),
        ("entries", "method", "entries()"),
        ("size", "property", "entry count"),
        ("isEmpty", "method", "isEmpty()"),
    ],
    "boolean": [
        ("toString", "method", "toString()"),
    ],
    "number": [
        ("toString", "method", "toString()"),
        ("toFixed", "method", "toFixed(digits)"),
        ("toPrecision", "method", "toPrecision(precision)"),
    ],
    "List": [
        ("add", "method", "add(...)"),
        ("addFirst", "method", "addFirst(...)"),
        ("addLast", "method", "addLast(...)"),
        ("clear", "method", "clear()"),
        ("concat", "method", "concat(...)"),
        ("contains", "method", "contains(...)"),
        ("every", "method", "every(...)"),
        ("filter", "method", "filter(...)"),
        ("find", "method", "find(...)"),
        ("first", "method", "first(...)"),
        ("forEach", "method", "forEach(...)"),
        ("get", "method", "get(...)"),
        ("getFirst", "method", "getFirst()"),
        ("getLast", "method", "getLast()"),
        ("groupBy", "method", "groupBy(...)"),
        ("indexOf", "method", "indexOf(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("join", "method", "join(...)"),
        ("last", "method", "last(...)"),
        ("map", "method", "map(...)"),
        ("partition", "method", "partition(...)"),
        ("pop", "method", "pop()"),
        ("push", "method", "push(...)"),
        ("reduce", "method", "reduce(...)"),
        ("remove", "method", "remove(...)"),
        ("removeFirst", "method", "removeFirst()"),
        ("removeLast", "method", "removeLast()"),
        ("reverse", "method", "reverse()"),
        ("size", "method", "size()"),
        ("slice", "method", "slice(...)"),
        ("some", "method", "some(...)"),
        ("sort", "method", "sort(...)"),
        ("toArray", "method", "toArray()"),
    ],
    "LinkedList": [
        ("add", "method", "add(...)"),
        ("addFirst", "method", "addFirst(...)"),
        ("addLast", "method", "addLast(...)"),
        ("clear", "method", "clear()"),
        ("concat", "method", "concat(...)"),
        ("contains", "method", "contains(...)"),
        ("every", "method", "every(...)"),
        ("filter", "method", "filter(...)"),
        ("find", "method", "find(...)"),
        ("first", "method", "first(...)"),
        ("forEach", "method", "forEach(...)"),
        ("get", "method", "get(...)"),
        ("getFirst", "method", "getFirst()"),
        ("getLast", "method", "getLast()"),
        ("groupBy", "method", "groupBy(...)"),
        ("indexOf", "method", "indexOf(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("join", "method", "join(...)"),
        ("last", "method", "last(...)"),
        ("map", "method", "map(...)"),
        ("partition", "method", "partition(...)"),
        ("pop", "method", "pop()"),
        ("push", "method", "push(...)"),
        ("reduce", "method", "reduce(...)"),
        ("remove", "method", "remove(...)"),
        ("removeFirst", "method", "removeFirst()"),
        ("removeLast", "method", "removeLast()"),
        ("reverse", "method", "reverse()"),
        ("size", "method", "size()"),
        ("slice", "method", "slice(...)"),
        ("some", "method", "some(...)"),
        ("sort", "method", "sort(...)"),
        ("toArray", "method", "toArray()"),
    ],
    "HashMap": [
        ("clear", "method", "clear()"),
        ("computeIfAbsent", "method", "computeIfAbsent(...)"),
        ("computeIfPresent", "method", "computeIfPresent(...)"),
        ("entries", "method", "entries()"),
        ("filter", "method", "filter(...)"),
        ("get", "method", "get(...)"),
        ("getOrDefault", "method", "getOrDefault(...)"),
        ("has", "method", "has(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("keys", "method", "keys()"),
        ("map", "method", "map(...)"),
        ("merge", "method", "merge(...)"),
        ("putAll", "method", "putAll(...)"),
        ("reduce", "method", "reduce(...)"),
        ("remove", "method", "remove(...)"),
        ("set", "method", "set(...)"),
        ("size", "method", "size()"),
        ("values", "method", "values()"),
    ],
    "Set": [
        ("add", "method", "add(...)"),
        ("clear", "method", "clear()"),
        ("difference", "method", "difference(...)"),
        ("has", "method", "has(...)"),
        ("intersection", "method", "intersection(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("remove", "method", "remove(...)"),
        ("size", "method", "size()"),
        ("toArray", "method", "toArray()"),
        ("union", "method", "union(...)"),
    ],
    "Stack": [
        ("clear", "method", "clear()"),
        ("isEmpty", "method", "isEmpty()"),
        ("peek", "method", "peek()"),
        ("pop", "method", "pop()"),
        ("push", "method", "push(...)"),
        ("size", "method", "size()"),
        ("toArray", "method", "toArray()"),
    ],
    "Queue": [
        ("clear", "method", "clear()"),
        ("dequeue", "method", "dequeue()"),
        ("enqueue", "method", "enqueue(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("peek", "method", "peek()"),
        ("size", "method", "size()"),
        ("toArray", "method", "toArray()"),
    ],
    "PriorityQueue": [
        ("clear", "method", "clear()"),
        ("dequeue", "method", "dequeue()"),
        ("enqueue", "method", "enqueue(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("peek", "method", "peek()"),
        ("size", "method", "size()"),
        ("toArray", "method", "toArray()"),
    ],
    "Trie": [
        ("clear", "method", "clear()"),
        ("getAllWords", "method", "getAllWords()"),
        ("getWordsWithPrefix", "method", "getWordsWithPrefix(...)"),
        ("insert", "method", "insert(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("remove", "method", "remove(...)"),
        ("search", "method", "search(...)"),
        ("size", "method", "size()"),
        ("startsWith", "method", "startsWith(...)"),
    ],
    "TreeMap": [
        ("clear", "method", "clear()"),
        ("containsKey", "method", "containsKey(...)"),
        ("firstKey", "method", "firstKey()"),
        ("get", "method", "get(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("items", "method", "items()"),
        ("iterator", "method", "iterator()"),
        ("keysInOrder", "method", "keysInOrder()"),
        ("lastKey", "method", "lastKey()"),
        ("put", "method", "put(...)"),
        ("remove", "method", "remove(...)"),
        ("size", "method", "size()"),
        ("toJSON", "method", "toJSON()"),
        ("valuesInOrder", "method", "valuesInOrder()"),
    ],
    "TreeSet": [
        ("add", "method", "add(...)"),
        ("clear", "method", "clear()"),
        ("contains", "method", "contains(...)"),
        ("first", "method", "first(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("iterator", "method", "iterator()"),
        ("last", "method", "last(...)"),
        ("remove", "method", "remove(...)"),
        ("size", "method", "size()"),
        ("toArray", "method", "toArray()"),
        ("toJSON", "method", "toJSON()"),
    ],
    "LinkedHashMap": [
        ("clear", "method", "clear()"),
        ("containsKey", "method", "containsKey(...)"),
        ("entries", "method", "entries()"),
        ("get", "method", "get(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("iterator", "method", "iterator()"),
        ("keys", "method", "keys()"),
        ("put", "method", "put(...)"),
        ("remove", "method", "remove(...)"),
        ("size", "method", "size()"),
        ("toJSON", "method", "toJSON()"),
        ("values", "method", "values()"),
    ],
    "LRUCache": [
        ("capacity", "method", "capacity()"),
        ("clear", "method", "clear()"),
        ("containsKey", "method", "containsKey(...)"),
        ("get", "method", "get(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("iterator", "method", "iterator()"),
        ("keysInOrder", "method", "keysInOrder()"),
        ("put", "method", "put(...)"),
        ("remove", "method", "remove(...)"),
        ("size", "method", "size()"),
        ("toJSON", "method", "toJSON()"),
    ],
    "ThreadSafeMap": [
        ("clear", "method", "clear()"),
        ("containsKey", "method", "containsKey(...)"),
        ("entries", "method", "entries()"),
        ("get", "method", "get(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("iterator", "method", "iterator()"),
        ("put", "method", "put(...)"),
        ("remove", "method", "remove(...)"),
        ("size", "method", "size()"),
        ("toJSON", "method", "toJSON()"),
    ],
    "ThreadSafeSet": [
        ("add", "method", "add(...)"),
        ("clear", "method", "clear()"),
        ("contains", "method", "contains(...)"),
        ("isEmpty", "method", "isEmpty()"),
        ("iterator", "method", "iterator()"),
        ("remove", "method", "remove(...)"),
        ("size", "method", "size()"),
        ("toArray", "method", "toArray()"),
        ("toJSON", "method", "toJSON()"),
    ],
    "Math": [
        ("sqrt", "method", "sqrt(x)"),
        ("pow", "method", "pow(base, exp)"),
        ("abs", "method", "abs(x)"),
        ("max", "method", "max(a, b, …)"),
        ("min", "method", "min(a, b, …)"),
        ("floor", "method", "floor(x)"),
        ("ceil", "method", "ceil(x)"),
        ("round", "method", "round(x)"),
        ("random", "method", "random()"),
        ("randomInt", "method", "randomInt(max)"),
        ("factorial", "method", "factorial(n)"),
        ("gcd", "method", "gcd(a, b)"),
        ("lcm", "method", "lcm(a, b)"),
        ("sin", "method", "sin(x)"),
        ("cos", "method", "cos(x)"),
        ("tan", "method", "tan(x)"),
        ("log", "method", "log(x)"),
        ("log2", "method", "log2(x)"),
        ("log10", "method", "log10(x)"),
        ("exp", "method", "exp(x)"),
        ("pi", "property", "π constant"),
        ("e", "property", "Euler's number"),
    ],
    "JSON": [
        ("toJSON", "method", "toJSON(value, indent?)"),
        ("parse", "method", "parse(text)"),
    ],
    "FileSystem": [
        ("readText", "method", "readText(path)"),
        ("writeText", "method", "writeText(path, text)"),
        ("appendText", "method", "appendText(path, text)"),
        ("exists", "method", "exists(path)"),
        ("isFile", "method", "isFile(path)"),
        ("isDirectory", "method", "isDirectory(path)"),
        ("listDirectory", "method", "listDirectory(path)"),
        ("createDirectory", "method", "createDirectory(path)"),
        ("deleteFile", "method", "deleteFile(path)"),
        ("deleteDirectory", "method", "deleteDirectory(path)"),
    ],
}

# Aliases the runtime reports for the same shape, so `let names = [...]` and a
# `List` variable both resolve.
_BUILTIN_ALIASES = {
    "integer": "number",
    "int": "number",
    "float": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
}

_BUILTIN_KIND = {
    "method": CompletionItemKind.Method,
    "property": CompletionItemKind.Property,
    "namespace": CompletionItemKind.Module,
    "class": CompletionItemKind.Class,
}


def _builtin_members(type_name: str) -> list[CompletionItem]:
    """Members for a built-in/stdlib receiver type, or ``[]``."""
    key = _BUILTIN_ALIASES.get(type_name, type_name)
    # `string[]` / `object<K, V>`-shaped annotations share the array/object maps.
    lowered = key.lower()
    if lowered.endswith("[]"):
        key = "array"
    entries = list(_BUILTIN_MEMBERS.get(key, []))
    # Only fall back to the wildcard set for types with no dedicated entry;
    # a number or boolean should not inherit `length` from the array/string
    # wildcard.
    if key not in _BUILTIN_MEMBERS:
        entries += _BUILTIN_MEMBERS.get("*", [])
    seen: set[str] = set()
    items: list[CompletionItem] = []
    for name, member_type, detail in entries:
        if name in seen:
            continue
        seen.add(name)
        items.append(
            CompletionItem(
                label=name,
                kind=_BUILTIN_KIND.get(member_type, CompletionItemKind.Method),
                detail=f"{key}.{name}: {detail}",
                documentation="built-in",
            )
        )
    return items


def _members_of_class(source: str, class_name: str) -> list[CompletionItem]:
    """Fields and methods declared directly inside ``class <class_name>``."""
    raw_lines = source.split("\n")
    members: list[CompletionItem] = []
    inside = False
    depth = 0
    for raw in raw_lines:
        start = _CLASS_START_RE.match(raw)
        if start:
            if start.group("name") == class_name:
                inside = True
                depth = 1
            elif inside:
                depth += 1
            continue
        if not inside:
            continue
        depth += raw.count("{") - raw.count("}")
        if depth <= 0:
            inside = False
            continue
        field = _FIELD_DECL_RE.match(raw)
        if field and field.group("name") not in ("return", "new", "let", "const"):
            members.append(
                CompletionItem(
                    label=field.group("name"),
                    kind=CompletionItemKind.Field,
                    detail=f"{class_name}.{field.group('type').strip()} {field.group('name')}",
                    documentation="field",
                )
            )
            continue
        method = _METHOD_DECL_RE.match(raw)
        if method:
            members.append(
                CompletionItem(
                    label=method.group("name"),
                    kind=CompletionItemKind.Method,
                    detail=(
                        f"{class_name}.{method.group('type').strip()} "
                        f"{method.group('name')}(...)"
                    ),
                    documentation="method",
                )
            )
    return members


def _member_completions(
    ls: XLanguageServer, uri: str, source: str, line: int, character: int
) -> list[CompletionItem] | None:
    """Type-aware ``receiver.`` suggestions.

    After ``let p = new Point();`` the popup for ``p.`` offers only ``Point``'s
    fields and methods, each tagged ``Point.x``. Returns ``None`` when the
    text before the cursor is not a member access, so the flat list takes over.
    """
    lines = source.split("\n")
    if line >= len(lines):
        return None
    # Cut the prefix at the last `.`: `print(p.)` leaves `);` after the dot and
    # would otherwise block the match, while `p.` alone still matches.
    prefix = lines[line][:character]
    dot = prefix.rfind(".")
    if dot < 0:
        return None
    match = _RECEIVER_RE.search(prefix[: dot + 1])
    if match is None:
        return None
    receiver = match.group(1)
    type_name = _var_static_type(source, receiver)
    if not type_name:
        return None
    members = _members_of_class(source, type_name)
    if not members:
        # Not a class declared in this file — fall back to built-in / stdlib
        # members, so `let string label = "x"; label.` offers string methods.
        members = _builtin_members(type_name)
    if not members:
        return None
    return members


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
            word = match.group(0)
            value = HOVER_INFO.get(word)
            if value is not None:
                return Hover(
                    contents=MarkupContent(
                        kind=MarkupKind.Markdown, value=f"```x\n{value}\n```"
                    )
                )
            declared = _find_declaration(source, word)
            if declared is None:
                return None
            display, declared_line = declared
            body = f"```x\n{display}\n```"
            if declared_line != line0:
                body += f"\n\ndeclared in this file, line {declared_line + 1}"
            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value=body)
            )
    return None


DECL_KEYWORDS = (
    r"(?:return|if|else|while|for|switch|match|case|default|break|continue|"
    r"throw|catch|new|print)\b"
)
TYPE_TOKEN = (
    r"[A-Za-z_][A-Za-z0-9_]*(?:<[^=;{}]*>)?(?:\[\])*"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
)
MODIFIERS = (
    r"(?:(?:public|private|protected|static|final|abstract|async|override|"
    r"internal|export)\s+)*"
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

    # No local declaration: the name is likely imported.  Search the files
    # this document imports and jump to the declaration there, mirroring
    # ModuleLoader's sibling-relative resolution (`import orchestrator.x`).
    for imported_path in _imported_files(uri, ls._source(uri)):
        try:
            imported_source = imported_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        imported_lines = code_lines(imported_source)
        imported_uri = imported_path.as_uri()
        for pattern in patterns:
            for index, text in enumerate(imported_lines):
                match = pattern.search(text)
                if match:
                    return Location(
                        uri=imported_uri,
                        range=Range(
                            start=Position(line=index, character=match.start("n")),
                            end=Position(line=index, character=match.end("n")),
                        ),
                    )
    return None


IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)")


def _imported_files(uri: str, source: str) -> list[Path]:
    """Filesystem paths of the ``.x`` modules this document imports.

    Resolution matches ``ModuleLoader._path_for_module``: a dotted module
    path is tried next to the importer first, then under the project root.
    Only the entry file's direct imports are considered — enough for
    go-to-definition to cross one file boundary.
    """
    entry = Path(to_fs_path(uri))
    project_root = entry.parent
    seen: set[Path] = set()
    result: list[Path] = []
    for line in code_lines(source):
        match = IMPORT_RE.match(line)
        if not match:
            continue
        parts = match.group(1).split(".")
        relative = entry.parent.joinpath(*parts).with_suffix(".x")
        candidate = relative if relative.is_file() else project_root.joinpath(*parts).with_suffix(".x")
        if candidate.is_file() and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


@server.feature(TEXT_DOCUMENT_REFERENCES)
def references(ls: XLanguageServer, params: ReferenceParams):
    """All places the word under the cursor is used in the document.

    This is what powers "Go to References" / Ctrl+Shift+G.  It scans the
    comment- and string-blanked buffer for whole-word matches of the symbol
    at the cursor, so a click on ``TransactionRule`` lists every ``implements
    TransactionRule``, type annotation and declaration of that name.
    """
    uri = str(params.text_document.uri)
    lines = code_lines(ls._source(uri))
    line0 = params.position.line
    char0 = params.position.character
    if line0 >= len(lines) or char0 > len(lines[line0]):
        return []

    word = None
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", lines[line0]):
        start, end = match.span()
        if start <= char0 < end:
            word = match.group(0)
            break
    if word is None:
        return []

    pattern = re.compile(rf"\b{re.escape(word)}\b")
    locations: list[Location] = []
    for index, text in enumerate(lines):
        for match in pattern.finditer(text):
            locations.append(
                Location(
                    uri=uri,
                    range=Range(
                        start=Position(line=index, character=match.start()),
                        end=Position(line=index, character=match.end()),
                    ),
                )
            )
    return locations


if __name__ == "__main__":
    server.start_io()
