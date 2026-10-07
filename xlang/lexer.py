from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


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


class Lexer:
    def __init__(
        self,
        source: str,
        source_name: str | None = None,
        initial_line: int = 1,
        initial_column: int = 1,
        recover_errors: bool = False,
    ) -> None:
        self.source = source
        self.source_name = source_name
        self.position = 0
        self.line = initial_line
        self.column = initial_column
        self.recover_errors = recover_errors
        self.errors: list[LexError] = []

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while not self._at_end():
            character = self._peek()
            if character.isspace():
                self._advance()
                continue
            if self._starts_with("//"):
                self._skip_line_comment()
                continue
            if self._starts_with("/*"):
                self._skip_block_comment()
                continue

            start_line = self.line
            start_column = self.column
            if character.isalpha() or character == "_":
                value = self._read_identifier()
                kind = value if value in KEYWORDS else "IDENTIFIER"
                tokens.append(Token(kind, value, start_line, start_column))
                continue
            if character.isdigit():
                tokens.append(
                    Token("NUMBER", self._read_number(), start_line, start_column)
                )
                continue
            if character in ('"', "'"):
                tokens.append(
                    Token("STRING", self._read_string(character), start_line, start_column)
                )
                continue
            if character == "`":
                tokens.append(
                    Token(
                        "TEMPLATE_STRING",
                        self._read_template_string(),
                        start_line,
                        start_column,
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
                tokens.append(Token(matched_operator, matched_operator, start_line, start_column))
                continue
            if character in "{}()[];,.?:|+-*/%!=<>@":
                self._advance()
                tokens.append(Token(character, character, start_line, start_column))
                continue
            error = LexError(
                f"Unexpected character {character!r}",
                self.line,
                self.column,
                self.source_name,
            )
            if not self.recover_errors:
                raise error
            self.errors.append(error)
            self._advance()

        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens

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
        if self._peek() == "." and self._peek(1).isdigit():
            self._advance()
            while self._peek().isdigit():
                self._advance()
        return self.source[start:self.position]

    def _read_string(self, quote: str) -> str:
        self._advance()
        characters: list[str] = []
        while not self._at_end() and self._peek() != quote:
            character = self._advance()
            if character == "\n":
                raise LexError(
                    "String literal cannot contain a newline",
                    self.line,
                    self.column,
                    self.source_name,
                )
            if character == "\\":
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
                    raise LexError(
                        f"Unknown escape sequence \\{escaped}",
                        self.line,
                        self.column,
                        self.source_name,
                    )
                characters.append(escape_values[escaped])
            else:
                characters.append(character)
        if self._at_end():
            raise LexError(
                "Unterminated string literal",
                self.line,
                self.column,
                self.source_name,
            )
        self._advance()
        value = "".join(characters)
        if quote == "'" and len(value) != 1:
            raise LexError(
                "Character literals must contain exactly one character",
                self.line,
                self.column,
                self.source_name,
            )
        return value

    def _read_template_string(self) -> str:
        self._advance()
        characters: list[str] = []
        escape_values = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "\\": "\\",
            "`": "`",
        }
        while not self._at_end() and self._peek() != "`":
            character = self._advance()
            if character == "\\" and not self._at_end():
                escaped = self._advance()
                characters.append(escape_values.get(escaped, "\\" + escaped))
            else:
                characters.append(character)
        if self._at_end():
            raise LexError(
                "Unterminated template literal",
                self.line,
                self.column,
                self.source_name,
            )
        self._advance()
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
            raise LexError(
                "Unterminated block comment",
                start_line,
                start_column,
                self.source_name,
            )
        self._advance()
        self._advance()
