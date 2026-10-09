"""Pretty-printer for X language source files.

``format_source`` re-prints a program from its token stream with consistent
indentation (two spaces), spacing, and blank-line handling while preserving
string literals, template literals, and comments verbatim.  The result is
idempotent: formatting already-formatted code returns it unchanged, so
``x --watch format file.x`` never fights the user's editor.

The formatter runs the real lexer and parser first, so a file with syntax
errors is reported instead of rewritten into something even more broken.
"""

from __future__ import annotations

from .lexer import Lexer, Token
from .parser import Parser

INDENT_WIDTH = 2

# Operators printed with surrounding spaces.
_BINARY_KINDS = {
    "=", "==", "===", "!=", "!==", "<", ">", "<=", ">=", "&&", "||",
    "+", "-", "*", "/", "%", "+=", "-=", "*=", "/=",
    "in", "of",
}

# Tokens that never take a space before them.
_NO_SPACE_BEFORE = {";", ",", ")", "]", ".", "?.", "?[", ":"}

# Tokens that never take a space after them.
_NO_SPACE_AFTER = {"(", "[", ".", "?.", "?[", "!", "@", "..."}

# Tokens that may sit next to an operand without a separating space.
_OPERAND_KINDS = {
    "IDENTIFIER", "NUMBER", "STRING", "TEMPLATE_STRING",
    ")", "]", "this", "super",
    "true", "false", "null", "Null", "undefined", "Undefined",
}

# After these tokens a following ``+``/``-`` is unary rather than binary.
_UNARY_CONTEXT_KINDS = {
    "(", "[", "{", ",", ";", ":", "=>", "?", "return", "case", "throw",
    *_BINARY_KINDS,
}

# Keywords after which a ``{`` opens a code block rather than an object.
_BLOCK_OPEN_KEYWORDS = {"else", "do", "try", "finally", "catch"}

# Keywords whose parenthesised header is followed by a block.
_PAREN_BLOCK_KEYWORDS = {
    "if", "while", "for", "switch", "catch", "function", "match",
}

# Keywords that mark the next ``{`` as a declaration-style block.
_DECLARATION_BLOCK_KEYWORDS = {
    "class", "interface", "enum", "namespace", "function", "type",
}

# Kinds that may end an ASI-terminated statement on the previous line.
_STATEMENT_END_KINDS = _OPERAND_KINDS | {
    "}", "++", "--", "return", "break", "continue", "*",
}

# Kinds that may begin an ASI-terminated statement on a fresh line.
_STATEMENT_START_KINDS = {
    "IDENTIFIER", "NUMBER", "STRING", "TEMPLATE_STRING", "!", "@",
    "abstract", "async", "await", "break", "class", "const", "continue",
    "do", "enum", "export", "false", "final", "for", "function", "if",
    "import",
    "interface", "internal", "let", "match", "namespace", "new",
    "null", "Null", "override", "package", "private", "protected",
    "public", "return", "static", "super", "switch", "this", "throw",
    "true", "try", "type", "undefined", "Undefined", "virtual", "void",
    "while",
}


class _BraceFrame:
    """One ``{ ... `` region on the formatter's brace stack."""

    __slots__ = ("kind",)

    def __init__(self, kind: str) -> None:
        #: "block", "switch", "match", or "object"
        self.kind = kind


class _Formatter:
    def __init__(self, source: str, tokens: list[Token]) -> None:
        self.source = source
        self.tokens = [token for token in tokens if token.kind != "EOF"]
        self.index = 0
        self.lines: list[str] = []
        self.current: list[str] = []
        self.indent = 0
        self.paren_depth = 0
        self.bracket_depth = 0
        self.brace_stack: list[_BraceFrame] = []
        self.paren_contexts: list[str] = []
        self.last_closed_paren_context = ""
        self.pending_paren_keyword: str | None = None
        self.pending_block_keyword = False
        self.pending_declaration_block = False
        self.pending_match_brace = False
        self.pending_arrow_block = False
        self.case_colon_pending = False
        self.pending_case_block = False
        self.case_body_pending = False
        self.ternary_depth = 0
        self.last_token_was_unary = False
        self.after_inline_comment = False
        self.pending_statement_break = False
        self.last_end_line = 0
        self.just_opened_block = True

    # ── public entry ────────────────────────────────────────────────

    def format(self) -> str:
        while self.index < len(self.tokens):
            token = self.tokens[self.index]
            if token.kind == "COMMENT":
                self._emit_comment(token)
                self.index += 1
                continue
            self._emit_token(token)
            self.index += 1
        self._finish_line()
        body = "\n".join(self.lines).rstrip()
        return body + "\n" if body else ""

    # ── token helpers ───────────────────────────────────────────────

    def _peek(self, offset: int = 0) -> Token | None:
        position = self.index + offset
        if position < len(self.tokens):
            return self.tokens[position]
        return None

    def _previous_code_token(self) -> Token | None:
        for position in range(self.index - 1, -1, -1):
            token = self.tokens[position]
            if token.kind != "COMMENT":
                return token
        return None

    def _raw_text(self, token: Token) -> str:
        if token.start >= 0 and token.end >= token.start:
            return self.source[token.start:token.end]
        return token.value

    def _in_object_literal(self) -> bool:
        return bool(self.brace_stack) and self.brace_stack[-1].kind == "object"

    # ── output primitives ───────────────────────────────────────────

    def _finish_line(self) -> None:
        if self.current:
            self.lines.append("".join(self.current).rstrip())
            self.current = []

    def _newline(self) -> None:
        self._finish_line()

    def _write(self, text: str) -> None:
        if not self.current and self.indent:
            self.current.append(" " * (self.indent * INDENT_WIDTH))
        self.current.append(text)

    def _ensure_newline(self) -> None:
        if self.current:
            self._newline()

    def _maybe_blank_before(self, token: Token) -> None:
        if self.just_opened_block:
            return
        if self.paren_depth > 0 or self.bracket_depth > 0:
            return
        if self.current or not self.lines:
            return
        if token.line - self.last_end_line >= 2 and self.lines[-1] != "":
            self.lines.append("")

    # ── spacing ─────────────────────────────────────────────────────

    def _needs_space(self, previous: Token | None, token: Token) -> bool:
        if previous is None:
            return False
        if token.kind == ":":
            return self._colon_needs_space()
        if token.kind in _NO_SPACE_BEFORE:
            return False
        if self.last_token_was_unary and token.kind in _OPERAND_KINDS:
            return False
        if token.kind in ("++", "--") and previous.kind in _OPERAND_KINDS:
            return False
        if previous.kind in _NO_SPACE_AFTER:
            return False
        if previous.kind in ("++", "--") and token.kind in _OPERAND_KINDS:
            return False
        if token.kind == "(":
            if previous.kind in _PAREN_BLOCK_KEYWORDS:
                return True
            if previous.kind == "return":
                return True
            if previous.kind in _OPERAND_KINDS:
                return False
            return True
        if token.kind == "[":
            if previous.kind in _OPERAND_KINDS:
                return False
            return True
        if token.kind in ("++", "--"):
            return True
        return True

    def _colon_needs_space(self) -> bool:
        if self.case_colon_pending:
            return False
        if self.ternary_depth > 0:
            return True
        if self._in_object_literal():
            return False
        return True

    def _is_unary_position(self, previous: Token | None) -> bool:
        if previous is None:
            return True
        return previous.kind in _UNARY_CONTEXT_KINDS

    # ── comments ────────────────────────────────────────────────────

    def _emit_comment(self, token: Token) -> None:
        text = token.value.rstrip()
        end_line = token.line + token.value.count("\n")
        if self.pending_statement_break and token.line > self.last_end_line:
            self.pending_statement_break = False
        # A comment only trails code when it sat on the same source line.
        trailing = bool(self.current) and token.line <= self.last_end_line
        parts = text.split("\n")
        if trailing:
            self.current.append(" " + parts[0].rstrip())
        else:
            self._ensure_newline()
            self._maybe_blank_before(token)
            self._write(parts[0].rstrip())
        for part in parts[1:]:
            self._newline()
            self.current.append(part.rstrip())
        # A ``//`` comment (or a multi-line ``/* */``) ends the line; a
        # single-line block comment stays inline with the code around it.
        if token.value.startswith("//") or len(parts) > 1:
            self._newline()
        else:
            self.after_inline_comment = True
        self.last_end_line = end_line
        self.just_opened_block = False

    # ── the main emit path ──────────────────────────────────────────

    def _emit_token(self, token: Token) -> None:
        kind = token.kind

        if self.pending_statement_break:
            self.pending_statement_break = False
            self._ensure_newline()

        if self.case_body_pending and kind != "{":
            self.case_body_pending = False
            self._ensure_newline()

        if kind in ("case", "default") and self._at_switch_body_level():
            self._emit_case_label(token)
            return

        if kind == ":" and self.case_colon_pending:
            self._finish_case_colon(token)
            return

        if kind == "{":
            self._emit_open_brace(token)
            return
        if kind == "}":
            self._emit_close_brace(token)
            return

        if kind == ";":
            self._emit_semicolon(token)
            return

        if self._asi_line_break(token):
            self._ensure_newline()

        self._maybe_blank_before(token)
        self._space_before(token)
        self._write(self._render(token))
        self._after_token(token)

    def _render(self, token: Token) -> str:
        if token.kind in ("STRING", "TEMPLATE_STRING"):
            return self._raw_text(token)
        return token.value

    def _space_before(self, token: Token) -> None:
        if not self.current:
            self.after_inline_comment = False
            return
        if self.after_inline_comment:
            self.after_inline_comment = False
            if token.kind not in _NO_SPACE_BEFORE:
                self.current.append(" ")
            return
        previous = self._previous_code_token()
        if self._needs_space(previous, token):
            self.current.append(" ")

    def _after_token(self, token: Token) -> None:
        kind = token.kind
        self.last_end_line = token.line + self._raw_text(token).count("\n")
        self.just_opened_block = False
        self.last_token_was_unary = kind == "!" or (
            kind in ("+", "-", "++", "--")
            and self._is_unary_position(self._previous_code_token())
        )

        if kind == "(":
            context = self.pending_paren_keyword or ""
            self.pending_paren_keyword = None
            self.paren_contexts.append(context)
            self.paren_depth += 1
        elif kind == ")":
            context = self.paren_contexts.pop() if self.paren_contexts else ""
            self.paren_depth = max(0, self.paren_depth - 1)
            self.last_closed_paren_context = context
            if context == "match":
                self.pending_match_brace = True
            elif context not in ("switch", "match") and context in _PAREN_BLOCK_KEYWORDS:
                self.pending_block_keyword = True
            self.pending_paren_keyword = None
        elif kind == "[":
            self.bracket_depth += 1
        elif kind == "]":
            self.bracket_depth = max(0, self.bracket_depth - 1)
        elif kind == "?":
            self.ternary_depth += 1
        elif kind == ":" and self.ternary_depth > 0:
            self.ternary_depth -= 1
        elif kind == "=>":
            self.pending_arrow_block = True
            self.pending_block_keyword = True

        self.pending_case_block = False

        if kind in _PAREN_BLOCK_KEYWORDS:
            self.pending_paren_keyword = kind
        if kind in _BLOCK_OPEN_KEYWORDS:
            self.pending_block_keyword = True
        if kind in _DECLARATION_BLOCK_KEYWORDS:
            self.pending_declaration_block = True
        if kind == "match":
            self.pending_match_brace = True
        if kind in (";", "}"):
            self.pending_match_brace = False
            self.pending_declaration_block = False
        if kind == "," and self._top_brace_is("match"):
            if self.paren_depth == 0 and self.bracket_depth == 0:
                self._newline()

    def _top_brace_is(self, kind: str) -> bool:
        return bool(self.brace_stack) and self.brace_stack[-1].kind == kind

    def _asi_line_break(self, token: Token) -> bool:
        """True when a source newline between statements must be kept.

        X lets a line break terminate a statement when the ``;`` is omitted,
        so the formatter has to preserve those breaks even though it collapses
        cosmetic wrapping inside expressions.
        """
        if self.paren_depth > 0 or self.bracket_depth > 0:
            return False
        if self._top_brace_is("object") or self._top_brace_is("match"):
            return False
        if token.line <= self.last_end_line:
            return False
        previous = self._previous_code_token()
        if previous is None:
            return False
        return (
            previous.kind in _STATEMENT_END_KINDS
            and token.kind in _STATEMENT_START_KINDS
        )

    def _emit_semicolon(self, token: Token) -> None:
        self._maybe_blank_before(token)
        self._space_before(token)
        self._write(";")
        self.last_end_line = token.line
        self.just_opened_block = False
        self.pending_match_brace = False
        self.pending_declaration_block = False
        self.pending_case_block = False
        if self.paren_depth > 0 or self.bracket_depth > 0:
            return
        # Defer the line break so a trailing ``// comment`` can stay on
        # this line; the next code token flushes the break.
        self.pending_statement_break = True

    # ── braces ──────────────────────────────────────────────────────

    def _at_switch_body_level(self) -> bool:
        return (
            self.paren_depth == 0
            and self._top_brace_is("switch")
        )

    def _classify_brace(self) -> str:
        previous = self._previous_code_token()
        if self.pending_case_block:
            return "block"
        if self.pending_match_brace:
            return "match"
        if self.pending_arrow_block or self.pending_block_keyword:
            return "block"
        if self.pending_declaration_block:
            return "block"
        if previous is None:
            return "block"
        if previous.kind == ")":
            context = self.last_closed_paren_context
            if context == "switch":
                return "switch"
            if context == "match":
                return "match"
            return "block"
        if previous.kind in _BLOCK_OPEN_KEYWORDS:
            return "block"
        if previous.kind == "}":
            return "block"
        if previous.kind in _OPERAND_KINDS:
            # class Foo {, enum E {, interface I {, match value {
            return "block"
        return "object"

    def _emit_open_brace(self, token: Token) -> None:
        kind = self._classify_brace()
        self.case_body_pending = False
        self._maybe_blank_before(token)
        self._space_before(token)
        self._write("{")
        self.last_end_line = token.line
        self.pending_arrow_block = False
        self.pending_block_keyword = False
        self.pending_declaration_block = False
        self.pending_match_brace = False
        self.pending_case_block = False
        self.case_colon_pending = False
        self.ternary_depth = 0

        following = self._peek(1)
        if kind == "object":
            if following is not None and following.kind == "}":
                self._write("}")
                self._update_state_after_brace()
                self.index += 1
                self.last_end_line = following.line
                return
            self.brace_stack.append(_BraceFrame("object"))
            return

        # block / switch / match: the body starts on the next line.
        self.brace_stack.append(_BraceFrame(kind))
        self.indent += 1
        self._newline()
        self.just_opened_block = True

    def _emit_close_brace(self, token: Token) -> None:
        frame = self.brace_stack.pop() if self.brace_stack else _BraceFrame("block")
        if frame.kind == "object":
            if self.current and not self.current[-1].endswith("{"):
                self.current.append(" ")
            self._write("}")
            self.last_end_line = token.line
            self._update_state_after_brace()
            return
        self._ensure_newline()
        self.indent = max(0, self.indent - 1)
        self._write("}")
        self.last_end_line = token.line
        self.just_opened_block = False
        self._update_state_after_brace()
        following = self._peek(1)
        joinable = following is not None and (
            following.kind in ("else", "catch", "finally", ";", ",", ")", "]")
            or (following.kind == "while" and following.line == token.line)
        )
        if not joinable:
            self._newline()

    def _update_state_after_brace(self) -> None:
        self.pending_block_keyword = False
        self.pending_declaration_block = False
        self.pending_match_brace = False
        self.case_colon_pending = False
        self.ternary_depth = 0

    # ── switch / case ───────────────────────────────────────────────

    def _emit_case_label(self, token: Token) -> None:
        self._ensure_newline()
        self._maybe_blank_before(token)
        self._write(token.value)
        self.last_end_line = token.line
        self.case_colon_pending = True
        self.just_opened_block = False

    def _finish_case_colon(self, token: Token) -> None:
        self.case_colon_pending = False
        self._write(":")
        self.last_end_line = token.line
        self.case_body_pending = True
        self.pending_case_block = True


def format_source(source: str, source_name: str | None = None) -> str:
    """Return *source* reformatted with canonical X style.

    Raises ``LexError`` or ``ParseError`` when the input is not valid X,
    because a broken program cannot be reformatted safely.
    """
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    lexer = Lexer(normalized, source_name, recover_errors=False, keep_comments=True)
    tokens = lexer.tokenize()
    parser = Parser(
        [token for token in tokens if token.kind != "COMMENT"],
        None,
        source_name,
        recover_errors=False,
    )
    parser.parse()
    formatter = _Formatter(normalized, tokens)
    return formatter.format()
