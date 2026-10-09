from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int
    start: int = -1
    end: int = -1


class LexError(Exception):
    def __init__(
        self,
        message: str,
        line: int,
        column: int,
        source_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_name = source_name


KEYWORDS = {
    "abstract", "as", "async", "await", "break", "case", "catch", "class", "const", "continue",
    "default", "do", "else", "enum", "extends", "false", "finally", "for", "function",
    "if", "implements", "import", "in", "interface", "internal", "let", "new",
    "match", "namespace", "null", "Null", "undefined", "Undefined", "of", "package",
    "private", "protected", "public", "return",
    "static", "super", "switch", "this", "throw", "true", "try", "type", "void",
    "while", "export", "override", "virtual", "final",
}

MULTI_CHARACTER_TOKENS = (
    "===", "!==", "?.", "?[",
    "...",
    "=>",
    "==", "!=", "<=", ">=", "&&", "||", "+=", "-=", "*=", "/=",
    "++", "--",
)

# Results of scan_template_interpolation.
INTERPOLATION_CLOSED = "closed"
INTERPOLATION_UNTERMINATED = "unterminated"
INTERPOLATION_ENDS_TEMPLATE = "ends-template"

BOM_CHARACTER = "\ufeff"


def scan_template_interpolation(text: str, start: int) -> tuple[str, int]:
    """Locate the ``}`` closing a template interpolation.

    ``start`` is the index right after the opening ``{``.  Returns
    ``(INTERPOLATION_CLOSED, index_of_brace)`` on success,
    ``(INTERPOLATION_ENDS_TEMPLATE, index_of_backtick)`` when a backtick is
    reached that cannot open a nested template literal (so the enclosing
    template ends there), and ``(INTERPOLATION_UNTERMINATED, len(text))`` when
    the text runs out first.  Nested braces, quoted strings, comments, and
    nested template literals are skipped so their braces are not mistaken for
    the end of the interpolation.
    """
    depth = 1
    position = start
    length = len(text)
    while position < length:
        character = text[position]
        following = text[position + 1] if position + 1 < length else ""
        if character in ("'", '"'):
            quoted_end = _skip_quoted(text, position)
            if quoted_end < 0:
                return INTERPOLATION_UNTERMINATED, length
            position = quoted_end
            continue
        if character == "`":
            template_end = _skip_nested_template(text, position)
            if template_end < 0:
                return INTERPOLATION_ENDS_TEMPLATE, position
            position = template_end
            continue
        if character == "/" and following == "/":
            newline = text.find("\n", position)
            position = length if newline < 0 else newline + 1
            continue
        if character == "/" and following == "*":
            comment_end = text.find("*/", position + 2)
            if comment_end < 0:
                return INTERPOLATION_UNTERMINATED, length
            position = comment_end + 2
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return INTERPOLATION_CLOSED, position
        position += 1
    return INTERPOLATION_UNTERMINATED, length


def _skip_quoted(text: str, start: int) -> int:
    """Index after the quote closing at ``start``, else the newline, else -1."""
    quote = text[start]
    position = start + 1
    while position < len(text):
        character = text[position]
        if character == "\\":
            position += 2
            continue
        if character == quote:
            return position + 1
        if character == "\n":
            return position
        position += 1
    return -1


def _skip_nested_template(text: str, start: int) -> int:
    """Index after the backtick closing the template opened at ``start``, else -1."""
    position = start + 1
    length = len(text)
    while position < length:
        character = text[position]
        if character == "\\":
            position += 2
            continue
        if character == "`":
            return position + 1
        if text.startswith("{{", position):
            position += 2
            continue
        if character == "{":
            status, index = scan_template_interpolation(text, position + 1)
            if status != INTERPOLATION_CLOSED:
                return -1
            position = index + 1
            continue
        position += 1
    return -1


class Lexer:
    def __init__(
        self,
        source: str,
        source_name: str | None = None,
        initial_line: int = 1,
        initial_column: int = 1,
        recover_errors: bool = False,
        keep_comments: bool = False,
    ) -> None:
        self.source = source
        self.source_name = source_name
        self.position = 0
        self.line = initial_line
        self.column = initial_column
        self.recover_errors = recover_errors
        self.keep_comments = keep_comments
        self.errors: list[LexError] = []

    def tokenize(self) -> list[Token]:
        if self.source.startswith(BOM_CHARACTER):
            self.position = len(BOM_CHARACTER)
        tokens: list[Token] = []
        try:
            self._scan_tokens(tokens)
        except RecursionError:
            error = LexError(
                "Template literals are nested too deeply",
                self.line,
                self.column,
                self.source_name,
            )
            if not self.recover_errors:
                raise error from None
            self.errors.append(error)
        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens

    def _scan_tokens(self, tokens: list[Token]) -> None:
        while not self._at_end():
            character = self._peek()
            if character.isspace():
                self._advance()
                continue
            if self._starts_with("//"):
                if self.keep_comments:
                    tokens.append(self._comment_token("//"))
                else:
                    self._skip_line_comment()
                continue
            if self._starts_with("/*"):
                if self.keep_comments:
                    tokens.append(self._comment_token("/*"))
                else:
                    self._skip_block_comment()
                continue

            start_line = self.line
            start_column = self.column
            start_offset = self.position
            if character.isalpha() or character == "_":
                value = self._read_identifier()
                kind = value if value in KEYWORDS else "IDENTIFIER"
                tokens.append(
                    Token(kind, value, start_line, start_column, start_offset, self.position)
                )
                continue
            if character.isdigit():
                tokens.append(
                    Token(
                        "NUMBER",
                        self._read_number(),
                        start_line,
                        start_column,
                        start_offset,
                        self.position,
                    )
                )
                continue
            if character in ('"', "'"):
                tokens.append(
                    Token(
                        "STRING",
                        self._read_string(character),
                        start_line,
                        start_column,
                        start_offset,
                        self.position,
                    )
                )
                continue
            if character == "`":
                tokens.append(
                    Token(
                        "TEMPLATE_STRING",
                        self._read_template_string(),
                        start_line,
                        start_column,
                        start_offset,
                        self.position,
                    )
                )
                continue

            matched_operator = next(
                (
                    operator
                    for operator in MULTI_CHARACTER_TOKENS
                    if self._starts_with(operator)
                ),
                None,
            )
            if matched_operator is not None:
                for _ in matched_operator:
                    self._advance()
                tokens.append(
                    Token(
                        matched_operator,
                        matched_operator,
                        start_line,
                        start_column,
                        start_offset,
                        self.position,
                    )
                )
                continue
            if character in "{}()[];,.?:|+-*/%!=<>@":
                self._advance()
                tokens.append(
                    Token(
                        character,
                        character,
                        start_line,
                        start_column,
                        start_offset,
                        self.position,
                    )
                )
                continue
            error = LexError(
                f"Unexpected character {character!r}",
                start_line,
                start_column,
                self.source_name,
            )
            if not self.recover_errors:
                raise error
            self.errors.append(error)
            self._advance()

    def _comment_token(self, prefix: str) -> Token:
        """Scan a ``//`` or ``/*`` comment into a ``COMMENT`` token."""
        start_line = self.line
        start_column = self.column
        start_offset = self.position
        if prefix == "//":
            self._skip_line_comment()
        else:
            self._skip_block_comment()
        return Token(
            "COMMENT",
            self.source[start_offset:self.position],
            start_line,
            start_column,
            start_offset,
            self.position,
        )

    def _at_end(self) -> bool:
        return self.position >= len(self.source)

    def _peek(self, offset: int = 0) -> str:
        index = self.position + offset
        if index >= len(self.source):
            return "\0"
        return self.source[index]

    def _advance(self) -> str:
        character = self.source[self.position]
        self.position += 1
        if character == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return character

    def _starts_with(self, text: str) -> bool:
        return self.source.startswith(text, self.position)

    def _read_identifier(self) -> str:
        start = self.position
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        return self.source[start:self.position]

    def _read_number(self) -> str:
        start = self.position
        while self._peek().isdigit():
            self._advance()
        if self._peek() == "." and self._peek(1) != ".":
            self._advance()
            while self._peek().isdigit():
                self._advance()
        return self.source[start:self.position]

    def _read_string(self, quote: str) -> str:
        start_line = self.line
        start_column = self.column
        self._advance()
        characters: list[str] = []
        ended_at_newline = False
        while not self._at_end() and self._peek() != quote:
            if self._peek() == "\n":
                error = LexError(
                    "String literal cannot contain a newline",
                    self.line,
                    self.column,
                    self.source_name,
                )
                if not self.recover_errors:
                    raise error
                self.errors.append(error)
                ended_at_newline = True
                break
            if self._peek() == "\\":
                escape_line = self.line
                escape_column = self.column
                self._advance()
                if self._at_end():
                    break
                escaped = self._advance()
                escape_values = {
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                    "\\": "\\",
                    '"': '"',
                    "'": "'",
                }
                if escaped not in escape_values:
                    error = LexError(
                        f"Unknown escape sequence \\{escaped}",
                        escape_line,
                        escape_column,
                        self.source_name,
                    )
                    if not self.recover_errors:
                        raise error
                    self.errors.append(error)
                    characters.append(escaped)
                    continue
                characters.append(escape_values[escaped])
                continue
            characters.append(self._advance())
        if not ended_at_newline:
            if self._at_end():
                error = LexError(
                    "Unterminated string literal",
                    start_line,
                    start_column,
                    self.source_name,
                )
                if not self.recover_errors:
                    raise error
                self.errors.append(error)
                return "".join(characters)
            self._advance()
        value = "".join(characters)
        if quote == "'" and len(value) != 1:
            error = LexError(
                "Character literals must contain exactly one character",
                start_line,
                start_column,
                self.source_name,
            )
            if not self.recover_errors:
                raise error
            self.errors.append(error)
        return value

    def _read_template_string(self) -> str:
        start_line = self.line
        start_column = self.column
        self._advance()
        characters: list[str] = []
        escape_values = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "\\": "\\",
            "`": "`",
        }
        while not self._at_end():
            character = self._peek()
            if character == "`":
                self._advance()
                return "".join(characters)
            if self._starts_with("{{"):
                characters.append(self._advance())
                characters.append(self._advance())
                continue
            if character == "\\":
                self._advance()
                if not self._at_end():
                    escaped = self._advance()
                    characters.append(escape_values.get(escaped, "\\" + escaped))
                else:
                    characters.append("\\")
                continue
            if character == "{":
                interpolation_line = self.line
                interpolation_column = self.column
                status, index = scan_template_interpolation(
                    self.source, self.position + 1
                )
                if status == INTERPOLATION_ENDS_TEMPLATE:
                    while self.position < index:
                        characters.append(self._advance())
                    continue
                if status != INTERPOLATION_CLOSED:
                    if not self.recover_errors:
                        raise LexError(
                            "Unterminated template interpolation",
                            interpolation_line,
                            interpolation_column,
                            self.source_name,
                        )
                    while not self._at_end():
                        characters.append(self._advance())
                    return "".join(characters)
                while self.position <= index:
                    characters.append(self._advance())
                continue
            characters.append(self._advance())
        error = LexError(
            "Unterminated template literal",
            start_line,
            start_column,
            self.source_name,
        )
        if not self.recover_errors:
            raise error
        self.errors.append(error)
        return "".join(characters)

    def _skip_line_comment(self) -> None:
        while not self._at_end() and self._peek() != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        start_line = self.line
        start_column = self.column
        self._advance()
        self._advance()
        while not self._at_end() and not self._starts_with("*/"):
            self._advance()
        if self._at_end():
            error = LexError(
                "Unterminated block comment",
                start_line,
                start_column,
                self.source_name,
            )
            if not self.recover_errors:
                raise error
            self.errors.append(error)
            return
        self._advance()
        self._advance()
