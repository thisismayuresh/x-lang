from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, TextIO


@dataclass
class SourceWarning:
    """A non-fatal diagnostic attached to a source location.

    ``notes`` and ``helps`` are optional rustc-style follow-up lines carried
    in the same shape as on a :class:`xlang.typecheck.errors.TypeCheckError`.
    Nothing emits them yet; they default to empty so existing construction
    sites keep working unchanged.
    """

    message: str
    source_name: str
    line: int | None = None
    column: int | None = None
    notes: tuple[str, ...] = ()
    helps: tuple[str, ...] = ()


RED = "\x1b[31m"
GREEN = "\x1b[32m"
BLUE = "\x1b[34m"
CYAN = "\x1b[36m"
YELLOW = "\x1b[33m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

#: Column width used when a source line is displayed with its tabs expanded,
#: so the caret keeps pointing at the same character the column number names.
TAB_WIDTH = 4


def callable_kind(
    name: str, class_name: str | None, is_interface: bool = False
) -> str:
    """Diagnostic label for a callable: ``Function``, ``Method`` or ``Constructor``.

    X has no ``function`` keyword inside a class body — members declared there
    are methods, and the member named after the class is its constructor — so
    diagnostics must never call them functions.  ``class_name`` is the
    enclosing class (or interface) when the callable is a member of one.
    """
    if class_name is None:
        return "Function"
    if not is_interface and name in (class_name, "constructor"):
        return "Constructor"
    return "Method"


def member_noun(modifiers: Iterable[str] | None) -> str:
    """Diagnostic noun for a class member variable, from how it is declared.

    Public members are *properties*, protected and static members are
    *fields*, and private members are *private fields*.
    """
    declared = set(modifiers or ())
    if "private" in declared:
        return "private field"
    if "protected" in declared:
        return "protected field"
    if "static" in declared:
        return "static field"
    return "property"


def render_diagnostic(
    error: BaseException,
    source: str | None,
    source_name: str,
    color_mode: str = "auto",
    stream: TextIO | None = None,
    show_context: bool = True,
) -> str:
    """Render *error* as a rustc-style block and return it as text.

    The plain layout, shown for a one-digit line number, is::

        error: <message>
         --> path:LINE:COL
          |
    LINE | <source line>
          | ^ <message>
          = note: <note text>
          = help: <help text>

    The gutter is exactly as wide as the line number, so at line 100 and at
    line 1000 the ``|`` markers, the ``= note:`` / ``= help:`` markers and
    the ``-->`` arrow (whose second dash sits on the ``|`` column) all keep
    the same columns.  Notes and helps are read from the ``notes`` and
    ``helps`` attributes of *error*, printed after the snippet in that order;
    each may span several lines and continuation lines are indented under the
    marker.  Text that already carries ANSI escapes is passed through
    untouched, so only the escapes this function adds are governed by
    *color_mode*: ``always`` forces colour (even when ``NO_COLOR`` is set),
    ``never`` and ``NO_COLOR`` force plain text, and ``auto`` follows the
    stream.

    The snippet is dropped, never the location or the hints, when *source* is
    ``None``, when *show_context* is false, or when the line number runs past
    the end of the source; the hints then line up with the gutter they would
    have had.  An error without a usable line number has no gutter at all, so
    its location and hints are flush left.  Tabs in the displayed source line
    are expanded before the caret is drawn, and unusable positions fall back
    to a header-only block rather than raising.
    """
    output_stream = stream or sys.stderr
    use_color = _should_use_color(color_mode, output_stream)
    message = getattr(error, "message", str(error))
    line = _position(getattr(error, "line", None), 1)
    column = _position(getattr(error, "column", None), 1)
    message_lines = _message_lines(message)
    error_source = _color("error", RED + BOLD, use_color)
    location_marker = _color("-->", BLUE + BOLD, use_color)

    if line is None:
        lines = _header_lines("error", error_source, message_lines)
        lines.append(f"{location_marker} {source_name}")
        lines.extend(_hint_lines(error, "", use_color))
        return "\n".join(lines)

    gutter = " " * len(str(line))
    location = f"{source_name}:{line}"
    if column is not None:
        location += f":{column}"
    lines = _header_lines("error", error_source, message_lines)
    lines.append(f"{gutter}{location_marker} {location}")

    source_lines = source.splitlines() if source is not None else []
    if not show_context or line > len(source_lines):
        lines.extend(_hint_lines(error, gutter, use_color))
        return "\n".join(lines)

    displayed_source, caret_column = _display_line(
        source_lines[line - 1], column
    )
    source_marker = _color("|", BLUE + BOLD, use_color)
    line_marker = _color(str(line), CYAN + BOLD, use_color)
    lines.append(f"{gutter} {source_marker}")
    lines.append(f"{line_marker} {source_marker} {displayed_source}")
    if caret_column is not None:
        lines.extend(
            _caret_lines(
                gutter,
                source_marker,
                caret_column,
                message_lines,
                RED,
                use_color,
            )
        )
    lines.extend(_hint_lines(error, gutter, use_color))
    return "\n".join(lines)


def render_warning(
    message: str,
    source: str | None,
    source_name: str,
    line: int | None,
    column: int | None,
    color_mode: str = "auto",
    stream: TextIO | None = None,
    *,
    notes: Sequence[str] = (),
    helps: Sequence[str] = (),
) -> str:
    """Render a warning block with the same layout as :func:`render_diagnostic`.

    A warning *may* carry ``notes`` and ``helps``; they are rendered exactly
    like an error's, as ``= note:`` (cyan) and ``= help:`` (green) lines under
    the snippet.  Both are keyword-only and default to empty, so every
    existing call site keeps its current output: the header, the location
    line, the snippet and the yellow caret are unchanged, and the only shared
    rendering change is that ``-->`` is indented to the line-number gutter,
    which affects line 100 and beyond.  A missing or unusable ``line`` still
    yields a header-only block, as before.
    """
    output_stream = stream or sys.stderr
    use_color = _should_use_color(color_mode, output_stream)
    line = _position(line, 1)
    column = _position(column, 1)
    message_lines = _message_lines(message)
    warning_source = _color("warning", YELLOW + BOLD, use_color)
    location_marker = _color("-->", BLUE + BOLD, use_color)

    if line is None:
        lines = _header_lines("warning", warning_source, message_lines)
        lines.append(f"{location_marker} {source_name}")
        lines.extend(_hint_lines_for(notes, helps, "", use_color))
        return "\n".join(lines)

    gutter = " " * len(str(line))
    location = f"{source_name}:{line}"
    if column is not None:
        location += f":{column}"
    lines = _header_lines("warning", warning_source, message_lines)
    lines.append(f"{gutter}{location_marker} {location}")

    source_lines = source.splitlines() if source is not None else []
    if line > len(source_lines):
        lines.extend(_hint_lines_for(notes, helps, gutter, use_color))
        return "\n".join(lines)

    displayed_source, caret_column = _display_line(
        source_lines[line - 1], column
    )
    source_marker = _color("|", BLUE + BOLD, use_color)
    line_marker = _color(str(line), CYAN + BOLD, use_color)
    lines.append(f"{gutter} {source_marker}")
    lines.append(f"{line_marker} {source_marker} {displayed_source}")
    if caret_column is not None:
        lines.extend(
            _caret_lines(
                gutter,
                source_marker,
                caret_column,
                message_lines,
                YELLOW,
                use_color,
            )
        )
    lines.extend(_hint_lines_for(notes, helps, gutter, use_color))
    return "\n".join(lines)


def _position(value: Any, minimum: int) -> int | None:
    """Line or column of a diagnostic, or ``None`` when it is unusable.

    Positions come from AST nodes and from exception attributes, so anything
    that is missing, non-numeric or below *minimum* degrades to "no position"
    instead of raising inside the renderer.
    """
    try:
        position = int(value)
    except (TypeError, ValueError):
        return None
    if position < minimum:
        return None
    return position


def _display_line(line_text: str, column: int | None) -> tuple[str, int | None]:
    """Source line to print plus the 1-based column the caret should mark.

    Tabs are expanded to :data:`TAB_WIDTH`-column stops in both the line and
    the caret offset, so a caret under a tab-indented line stays under the
    same character.  Lines without tabs come back untouched.
    """
    if column is None:
        return line_text, None
    if "\t" not in line_text:
        return line_text, column
    expanded = line_text.expandtabs(TAB_WIDTH)
    offset = len(line_text[: column - 1].expandtabs(TAB_WIDTH))
    return expanded, offset + 1


def _message_lines(message: str) -> list[str]:
    """Split *message* into display lines; an empty message shows as one line."""
    return message.splitlines() or [message]


def _header_lines(plain_label: str, label: str, message_lines: list[str]) -> list[str]:
    """``error: first line`` with continuation lines indented under the text."""
    first = message_lines[0]
    lines = [f"{label}: {first}" if first else f"{label}:"]
    indent = " " * (len(plain_label) + 2)
    lines.extend(f"{indent}{line}" for line in message_lines[1:])
    return lines


def _caret_lines(
    gutter: str,
    source_marker: str,
    column: int,
    message_lines: list[str],
    color: str,
    use_color: bool,
) -> list[str]:
    """Caret line plus continuation lines, kept inside the source gutter.

    An empty message line still draws its caret, with no trailing whitespace.
    """
    pad = " " * max(column - 1, 0)
    caret = _color("^", color + BOLD, use_color)
    base = f"{gutter} {source_marker} {pad}"
    first = _color(message_lines[0], color, use_color)
    lines = [f"{base}{caret} {first}" if first else f"{base}{caret}"]
    lines.extend(
        f"{base}  {_color(line, color, use_color)}"
        if line
        else f"{base}  ".rstrip()
        for line in message_lines[1:]
    )
    return lines


def _hint_lines(error: BaseException, gutter: str, use_color: bool) -> list[str]:
    """rustc-style follow-ups on *error*: ``= note:`` then ``= help:``.

    ``gutter`` is the blank line-number column so ``=`` lines up with the
    source ``|`` marker; an empty gutter keeps the lines flush left.  Errors
    without notes or helps render no hint lines at all.
    """
    return _hint_lines_for(
        getattr(error, "notes", ()) or (),
        getattr(error, "helps", ()) or (),
        gutter,
        use_color,
    )


def _hint_lines_for(
    notes: Sequence[str],
    helps: Sequence[str],
    gutter: str,
    use_color: bool,
) -> list[str]:
    """``= note:`` / ``= help:`` lines for *notes* and *helps*.

    Each entry is split into display lines: the first follows the marker, the
    rest are indented two columns further so a multi-line hint stays inside
    the gutter.  An empty entry still prints its marker, with no trailing
    whitespace, and entries that already contain ANSI escapes are printed
    verbatim.
    """
    prefix = f"{gutter} " if gutter else ""
    continuation = f"{gutter}   " if gutter else "  "
    lines: list[str] = []
    for kind, items, color in (
        ("note", notes, CYAN),
        ("help", helps, GREEN),
    ):
        for item in items:
            for index, text in enumerate(str(item).splitlines() or [""]):
                if index == 0:
                    label = _color(f"= {kind}:", color + BOLD, use_color)
                    if text:
                        lines.append(f"{prefix}{label} {_color(text, color, use_color)}")
                    else:
                        lines.append(f"{prefix}{label}")
                elif text:
                    lines.append(f"{continuation}{_color(text, color, use_color)}")
                else:
                    lines.append(continuation.rstrip())
    return lines


def _should_use_color(color_mode: str, stream: TextIO) -> bool:
    """Whether to emit ANSI escapes: an explicit mode wins over the environment.

    ``always`` colours even when ``NO_COLOR`` is set, ``never`` and
    ``NO_COLOR`` stay plain, and ``auto`` follows the stream.
    """
    if color_mode == "always":
        return True
    if color_mode == "never" or "NO_COLOR" in os.environ:
        return False
    return stream.isatty()


def _color(text: str, color: str, enabled: bool) -> str:
    if not enabled or "\x1b" in text:
        return text
    return f"{color}{text}{RESET}"
