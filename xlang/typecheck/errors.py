from __future__ import annotations

from typing import Any

from ..runtime import RuntimeErrorX


class TypeCheckError(Exception):
    """A compile-time type or definite-assignment diagnostic."""

    def __init__(
        self,
        message: str,
        node: Any | None = None,
        source_name: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source_name = source_name or getattr(node, "source_name", None)
        self.line = line if line is not None else getattr(node, "line", None)
        self.column = column if column is not None else getattr(node, "column", None)


class TypeCheckFailure(RuntimeErrorX):
    """Raised when type checking produced one or more diagnostics.

    Carries every :class:`TypeCheckError` so the CLI can render each one with
    its own source snippet, exactly like lex and parse errors.  The first
    diagnostic is also exposed through ``message``/``line``/``column``/
    ``source_name`` so generic ``except RuntimeErrorX`` handlers keep working
    and keep reporting a single, self-contained message.
    """

    def __init__(self, errors: list[TypeCheckError]) -> None:
        first = errors[0]
        super().__init__(first.message)
        self.errors: list[TypeCheckError] = list(errors)
        self.line = first.line
        self.column = first.column
        self.source_name = first.source_name
