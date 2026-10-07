"""Compile-time type checking for X programs.

Public API:

    from xlang.typecheck import TypeChecker
    errors = TypeChecker().check(program, source_name="main.x")

``TypeChecker.check`` never raises; it returns a list of :class:`TypeCheckError`.
Use ``check_or_raise`` to fail fast with the first error. ``TypeDiagnostic`` is
an alias of ``TypeCheckError`` for callers that prefer diagnostic terminology.

``TypeCheckFailure`` is the exception raised when a program is rejected before
execution.  It carries every diagnostic so callers can render each one with its
own source snippet instead of a single concatenated blob.

``TypeChecker.check_declarations`` runs only declaration-level validation
(unknown type names, interface conformance) and is used by the interpreter
as a pre-execution gate.
"""

from .checker import TypeChecker
from .errors import TypeCheckError, TypeCheckFailure

TypeDiagnostic = TypeCheckError

__all__ = [
    "TypeChecker",
    "TypeCheckError",
    "TypeCheckFailure",
    "TypeDiagnostic",
    "check_declarations",
]


def check_declarations(program, source_name=None):
    """Convenience wrapper around ``TypeChecker().check_declarations``."""
    return TypeChecker().check_declarations(program, source_name)
