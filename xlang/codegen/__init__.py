"""Target backends that turn a checked X ``Program`` into source for another
language.

The CLI reaches this package through :func:`emit`, the single public entry
point. A backend receives the *flattened* program the :class:`ModuleLoader`
produces — every reachable module has already been merged into one declaration
list — so a backend emits a single self-contained file rather than a tree of
modules.

Backends are registered in :data:`TARGETS`. Adding one means writing a module
with an ``emit_<target>(program, ...)`` function and adding its name here; the
CLI validates ``--target`` and ``[compile].target`` against this mapping so an
unknown target is a configuration error, never a traceback.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = [
    "SUPPORTED_TARGETS",
    "CodegenError",
    "emit",
]

#: Maps a ``--target`` name to its backend callable.
TARGETS: dict[str, Callable[..., str]] = {}

#: Human-readable names, in a stable order for error messages and help text.
SUPPORTED_TARGETS: tuple[str, ...] = ("typescript",)


class CodegenError(Exception):
    """A backend could not translate the program.

    Carries an optional location so the CLI can render it with the same
    rustc-style diagnostics used for parse and type errors.
    """

    def __init__(
        self,
        message: str,
        source_name: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source_name = source_name
        self.line = line
        self.column = column


def _load_backend(target: str) -> Callable[..., str]:
    if not TARGETS:
        _register_builtins()
    backend = TARGETS.get(target)
    if backend is None:
        available = ", ".join(SUPPORTED_TARGETS)
        raise CodegenError(
            f"unknown compile target '{target}'. Available targets: {available}"
        )
    return backend


def _register_builtins() -> None:
    # Imported lazily so importing ``xlang.codegen`` stays free of the
    # backend's own dependencies.
    from .typescript import emit_typescript

    TARGETS.setdefault("typescript", emit_typescript)


def emit(
    program: Any,
    target: str,
    source_name: str | None = None,
    config: Any = None,
) -> str:
    """Translate *program* into source for *target*.

    Raises :class:`CodegenError` for an unknown target or a construct the
    backend cannot represent.
    """
    backend = _load_backend(target)
    return backend(program, source_name=source_name, config=config)
