"""X Language LSP Server entry point."""

import sys
import os

# Add the xlang package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'xlang'))

from pygls.server import JsonRPCServer
from pygls.protocol import LanguageServerProtocol
from lsprotocol.converters import get_converter
from lsprotocol.types import (
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_REFERENCES,
    CompletionParams,
    HoverParams,
    DefinitionParams,
    ReferenceParams,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidSaveTextDocumentParams,
    CompletionItem,
    CompletionItemKind,
    Hover,
    MarkupContent,
    MarkupKind,
    Location,
    Range,
    Position,
    Diagnostic,
    DiagnosticSeverity,
    PublishDiagnosticsParams,
)

from xlang.lexer import Lexer
from xlang.parser import Parser
from xlang.typecheck.checker import TypeChecker


class XLanguageServer(JsonRPCServer):
    """LSP Server for X language."""
    
    def __init__(self):
        self.name = "xlang-server"
        self.version = "v0.1.0"
        super().__init__(LanguageServerProtocol, lambda: get_converter())
        self.documents = {}
        self.diagnostics_cache = {}
        self.config = {
            'enable_type_checking': True,
            'strict_typing': False,
        }
    
    def _get_document(self, uri: str) -> str:
        """Get document source from URI."""
        return self.documents.get(uri, '')
    
    def _update_diagnostics(self, uri: str):
        """Update diagnostics for a document."""
        if not self.config.get('enable_type_checking', True):
            self.publish_diagnostics(uri, [])
            return
        
        source = self._get_document(uri)
        if not source:
            self.publish_diagnostics(uri, [])
            return
        
        try:
            lexer = Lexer(source, uri)
            tokens = lexer.tokenize()
            parser = Parser(tokens)
            program = parser.parse()
            
            checker = TypeChecker()
            errors = checker.check(program, source_name=uri)
            
            diagnostics = []
            for error in errors:
                line = max(0, (error.line or 1) - 1)
                column = max(0, (error.column or 1) - 1)
                
                # Calculate end position (approximate)
                end_column = column + 10
                
                diagnostics.append(Diagnostic(
                    range=Range(
                        start=Position(line=line, character=column),
                        end=Position(line=line, character=end_column)
                    ),
                    severity=DiagnosticSeverity.Error,
                    message=error.message,
                    source="xlang",
                    code=error.code if hasattr(error, 'code') else None
                ))
            
            # Send diagnostics notification
            from lsprotocol.types import PublishDiagnosticsParams
            self.protocol.notify(
                "textDocument/publishDiagnostics",
                PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
            )
            self.diagnostics_cache[uri] = diagnostics
            
        except Exception as e:
            # Don't crash on parse errors, just log
            print(f"Error checking {uri}: {e}", file=sys.stderr)
            from lsprotocol.types import PublishDiagnosticsParams
            self.protocol.notify(
                "textDocument/publishDiagnostics",
                PublishDiagnosticsParams(uri=uri, diagnostics=[])
            )


# Create server instance
server = XLanguageServer()


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls, params: DidOpenTextDocumentParams):
    """Handle document open."""
    uri = params.text_document.uri
    ls.documents[uri] = params.text_document.text
    ls._update_diagnostics(uri)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls, params: DidChangeTextDocumentParams):
    """Handle document change."""
    uri = params.text_document.uri
    for change in params.contentChanges:
        if 'range' in change:
            # Incremental update (not fully implemented)
            ls.documents[uri] = params.text_document.text
        else:
            # Full update
            ls.documents[uri] = change.text
    ls._update_diagnostics(uri)


@server.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls, params: DidCloseTextDocumentParams):
    """Handle document close."""
    uri = params.text_document.uri
    ls.documents.pop(uri, None)
    ls.diagnostics_cache.pop(uri, None)
    from lsprotocol.types import PublishDiagnosticsParams
    ls.protocol.notify(
        "textDocument/publishDiagnostics",
        PublishDiagnosticsParams(uri=uri, diagnostics=[])
    )


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls, params: DidSaveTextDocumentParams):
    """Handle document save."""
    # Re-check on save
    uri = params.text_document.uri
    ls._update_diagnostics(uri)


@server.feature(TEXT_DOCUMENT_COMPLETION)
def completions(ls, params: CompletionParams):
    """Provide completions."""
    uri = params.text_document.uri
    source = ls._get_document(uri)
    position = params.position
    
    items = []
    
    # Basic keyword completions
    keywords = [
        ("class", CompletionItemKind.Keyword),
        ("interface", CompletionItemKind.Keyword),
        ("function", CompletionItemKind.Keyword),
        ("let", CompletionItemKind.Keyword),
        ("const", CompletionItemKind.Keyword),
        ("if", CompletionItemKind.Keyword),
        ("else", CompletionItemKind.Keyword),
        ("while", CompletionItemKind.Keyword),
        ("for", CompletionItemKind.Keyword),
        ("return", CompletionItemKind.Keyword),
        ("new", CompletionItemKind.Keyword),
        ("import", CompletionItemKind.Keyword),
        ("export", CompletionItemKind.Keyword),
        ("extends", CompletionItemKind.Keyword),
        ("implements", CompletionItemKind.Keyword),
        ("public", CompletionItemKind.Keyword),
        ("private", CompletionItemKind.Keyword),
        ("protected", CompletionItemKind.Keyword),
        ("static", CompletionItemKind.Keyword),
        ("final", CompletionItemKind.Keyword),
        ("abstract", CompletionItemKind.Keyword),
        ("async", CompletionItemKind.Keyword),
        ("await", CompletionItemKind.Keyword),
        ("try", CompletionItemKind.Keyword),
        ("catch", CompletionItemKind.Keyword),
        ("finally", CompletionItemKind.Keyword),
        ("throw", CompletionItemKind.Keyword),
        ("switch", CompletionItemKind.Keyword),
        ("case", CompletionItemKind.Keyword),
        ("default", CompletionItemKind.Keyword),
        ("match", CompletionItemKind.Keyword),
        ("this", CompletionItemKind.Keyword),
        ("super", CompletionItemKind.Keyword),
        ("constructor", CompletionItemKind.Keyword),
    ]
    
    for kw, kind in keywords:
        items.append(CompletionItem(label=kw, kind=kind))
    
    # Type completions
    types = [
        ("int", CompletionItemKind.Class),
        ("string", CompletionItemKind.Class),
        ("float", CompletionItemKind.Class),
        ("boolean", CompletionItemKind.Class),
        ("void", CompletionItemKind.Class),
        ("any", CompletionItemKind.Class),
        ("null", CompletionItemKind.Value),
        ("undefined", CompletionItemKind.Value),
    ]
    
    for typ, kind in types:
        items.append(CompletionItem(label=typ, kind=kind))
    
    # Built-in function completions
    builtins = [
        ("print", CompletionItemKind.Function),
        ("range", CompletionItemKind.Function),
        ("typeOf", CompletionItemKind.Function),
        ("sleep", CompletionItemKind.Function),
        ("input", CompletionItemKind.Function),
        ("parseInt", CompletionItemKind.Function),
        ("parseFloat", CompletionItemKind.Function),
    ]
    
    for fn, kind in builtins:
        items.append(CompletionItem(label=fn, kind=kind))
    
    # Extract class names from current document
    import re
    class_matches = re.finditer(r'\bclass\s+([A-Z][a-zA-Z0-9_]*)', source)
    for match in class_matches:
        items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Class))
    
    interface_matches = re.finditer(r'\binterface\s+([A-Z][a-zA-Z0-9_]*)', source)
    for match in interface_matches:
        items.append(CompletionItem(label=match.group(1), kind=CompletionItemKind.Interface))
    
    return items


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls, params: HoverParams):
    """Provide hover information."""
    uri = params.text_document.uri
    source = ls._get_document(uri)
    position = params.position
    
    # Simple hover - show type information for word at position
    lines = source.split('\n')
    if position.line >= len(lines):
        return None
    
    line = lines[position.line]
    if position.character >= len(line):
        return None
    
    # Find word at position
    import re
    word_match = None
    for match in re.finditer(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', line):
        start, end = match.span()
        if start <= position.character < end:
            word_match = match
            break
    
    if not word_match:
        return None
    
    word = word_match.group(0)
    
    # Provide basic hover info for known symbols
    hover_info = {
        'print': 'print(value: any): void\n\nPrints a value to stdout.',
        'range': 'range(start: int, end?: int, step?: int): int[]\n\nReturns an array of numbers.',
        'typeOf': 'typeOf(value: any): string\n\nReturns the type name of a value.',
        'sleep': 'sleep(ms: int): Promise<void>\n\nSleeps for the specified milliseconds.',
        'input': 'input(prompt?: string): string\n\nReads a line from stdin.',
        'int': 'Primitive integer type.',
        'string': 'Primitive string type.',
        'float': 'Primitive floating-point type.',
        'boolean': 'Primitive boolean type.',
        'void': 'Represents no value.',
        'any': 'Any type (disables type checking).',
    }
    
    if word in hover_info:
        return Hover(
            contents=MarkupContent(
                kind=MarkupKind.Markdown,
                value=f"```x\n{hover_info[word]}\n```"
            )
        )
    
    return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls, params: DefinitionParams):
    """Go to definition."""
    uri = params.text_document.uri
    source = ls._get_document(uri)
    position = params.position
    
    # Simplified - in full implementation, would use type checker symbol table
    lines = source.split('\n')
    if position.line >= len(lines):
        return None
    
    line = lines[position.line]
    if position.character >= len(line):
        return None
    
    import re
    word_match = None
    for match in re.finditer(r'\b([A-Z][a-zA-Z0-9_]*)\b', line):
        start, end = match.span()
        if start <= position.character < end:
            word_match = match
            break
    
    if not word_match:
        return None
    
    class_name = word_match.group(1)
    
    # Search for class/interface definition in current file
    class_pattern = rf'\b(class|interface)\s+{re.escape(class_name)}\b'
    for i, l in enumerate(lines):
        if re.search(class_pattern, l):
            return Location(
                uri=uri,
                range=Range(
                    start=Position(line=i, character=l.find(class_name)),
                    end=Position(line=i, character=l.find(class_name) + len(class_name))
                )
            )
    
    return None


@server.feature(TEXT_DOCUMENT_REFERENCES)
def references(ls, params: ReferenceParams):
    """Find references."""
    # Simplified implementation
    return []


if __name__ == "__main__":
    server.start_io()