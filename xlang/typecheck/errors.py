from __future__ import annotations

from typing import Any


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
