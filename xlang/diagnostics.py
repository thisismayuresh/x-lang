from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass
class SourceWarning:
    """A non-fatal diagnostic attached to a source location."""

    message: str
    source_name: str
    line: int | None = None
    column: int | None = None


RED = "\x1b[31m"
BLUE = "\x1b[34m"
CYAN = "\x1b[36m"
YELLOW = "\x1b[33m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"


def render_diagnostic(
    error: BaseException,
    source: str | None,
    source_name: str,
    color_mode: str = "auto",
    stream: TextIO | None = None,
    show_context: bool = True,
) -> str:
    output_stream = stream or sys.stderr
    use_color = _should_use_color(color_mode, output_stream)
    message = getattr(error, "message", str(error))
    line = getattr(error, "line", None)
    column = getattr(error, "column", None)
    error_source = _color("error", RED + BOLD, use_color)
    location_marker = _color("-->", BLUE + BOLD, use_color)

    if line is None or line < 1:
        return f"{error_source}: {message}\n{location_marker} {source_name}"

    location = f"{source_name}:{line}"
    if column is not None:
        location += f":{column}"
    lines = [
        f"{error_source}: {message}",
        f" {location_marker} {location}",
    ]
    if source is None or not show_context:
        return "\n".join(lines)

    source_lines = source.splitlines()
    if line > len(source_lines):
        return "\n".join(lines)
    line_number_width = len(str(line))
    gutter = " " * line_number_width
    displayed_source = source_lines[line - 1]
    source_marker = _color("|", BLUE + BOLD, use_color)
    line_marker = _color(str(line), CYAN + BOLD, use_color)
    lines.append(f"{gutter} {source_marker}")
    lines.append(f"{line_marker} {source_marker} {displayed_source}")
    if column is not None and column > 0:
        marker = " " * (column - 1) + _color("^", RED + BOLD, use_color)
        lines.append(f"{gutter} {source_marker} {marker} {_color(message, RED, use_color)}")
    return "\n".join(lines)


def render_warning(
    message: str,
    source: str | None,
    source_name: str,
    line: int | None,
    column: int | None,
    color_mode: str = "auto",
    stream: TextIO | None = None,
) -> str:
    output_stream = stream or sys.stderr
    use_color = _should_use_color(color_mode, output_stream)
    warning_source = _color("warning", YELLOW + BOLD, use_color)
    location_marker = _color("-->", BLUE + BOLD, use_color)

    if line is None or line < 1:
        return f"{warning_source}: {message}\n{location_marker} {source_name}"

    location = f"{source_name}:{line}"
    if column is not None:
        location += f":{column}"
    lines = [
        f"{warning_source}: {message}",
        f" {location_marker} {location}",
    ]
    if source is None:
        return "\n".join(lines)

    source_lines = source.splitlines()
    if line > len(source_lines):
        return "\n".join(lines)
    line_number_width = len(str(line))
    gutter = " " * line_number_width
    source_marker = _color("|", BLUE + BOLD, use_color)
    line_marker = _color(str(line), CYAN + BOLD, use_color)
    lines.append(f"{gutter} {source_marker}")
    lines.append(f"{line_marker} {source_marker} {source_lines[line - 1]}")
    if column is not None and column > 0:
        marker = " " * (column - 1) + _color("^", YELLOW + BOLD, use_color)
        lines.append(f"{gutter} {source_marker} {marker} {_color(message, YELLOW, use_color)}")
    return "\n".join(lines)


def _should_use_color(color_mode: str, stream: TextIO) -> bool:
    if color_mode == "always":
        return True
    if color_mode == "never" or "NO_COLOR" in os.environ:
        return False
    return stream.isatty()


def _color(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{color}{text}{RESET}"
