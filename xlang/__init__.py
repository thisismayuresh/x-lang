"""Interpreter for the experimental X programming language."""

import warnings

__version__ = "0.1.0"

# X's async functions and fetch() calls are backed by Python coroutines.
# When user code stores, passes around, or otherwise drops an awaitable, CPython
# may emit its internal "coroutine ... was never awaited" RuntimeWarning straight
# onto stderr — an implementation detail leaking into the X program's output.
# The interpreter raises its own X-level diagnostics for every case it can
# detect (discarded statement result, member access on an async result, etc.),
# so silence the raw Python warning here.
warnings.filterwarnings(
    "ignore",
    message="coroutine .* was never awaited",
    category=RuntimeWarning,
)
