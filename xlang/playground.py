"""Run and format X source for the docs-site playground.

The browser loads these entry points inside Pyodide (CPython compiled to
WebAssembly). The interpreter itself is *not* recompiled per change — it
ships as a pure-Python wheel of ``xlang/`` that micropip installs into the
Pyodide virtual filesystem. Rebuild that wheel with
``docs-site/playground/build.py`` whenever ``xlang/`` changes.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

from .config import XConfig
from .formatter import format_source
from .interpreter import Interpreter
from .lexer import LexError
from .module_loader import ModuleLoader
from .parser import ParseError
from .runtime import RuntimeErrorX, ThrownValue
from .typecheck import TypeCheckFailure

DEFAULT_ENTRY = "main.x"
MAX_FILES = 5
MAX_FILE_BYTES = 64_000


def run_source(source: str) -> dict[str, Any]:
    """Execute a single-file program (compat wrapper around ``run_files``)."""
    return run_files([{"name": DEFAULT_ENTRY, "content": source}])


def run_files(files: list[dict[str, Any]], entry: str | None = None) -> dict[str, Any]:
    """Execute a small multi-file project in a temporary directory.

    *files* is a list of ``{"name": "main.x", "content": "..."}`` dicts
    (at most ``MAX_FILES``). Relative ``import Other.stuff`` loads
    ``Other.x`` from the same virtual project root, matching the CLI. The
    playground always runs with the interpreter's default feature set, so no
    per-run feature overrides are accepted here.
    """
    started = time.perf_counter()
    result: dict[str, Any] = {
        "ok": False,
        "output": [],
        "errors": [],
        "durationMs": 0.0,
    }
    output: list[str] = result["output"]
    errors: list[dict[str, Any]] = result["errors"]

    prepared, prep_errors = _prepare_files(files, entry)
    errors.extend(prep_errors)
    if prep_errors:
        return _finish(result, started)

    entry_name = prepared[0][0]
    config = XConfig()
    config.features["network"] = False

    with _virtual_project(prepared) as project_root:
        try:
            loader = ModuleLoader(project_root, config=config, recover_errors=True)
            program = loader.load_program(project_root / entry_name)
        except LexError as error:
            errors.append(_error("lex", error.message, error.line, error.column, entry_name))
            return _finish(result, started)
        except ParseError as error:
            errors.append(_error("parse", error.message, error.line, error.column, entry_name))
            return _finish(result, started)
        except RuntimeErrorX as error:
            item = _runtime_error(error)
            item["file"] = entry_name
            errors.append(item)
            return _finish(result, started)
        except RecursionError:
            errors.append(
                _error(
                    "runtime",
                    "Maximum recursion depth exceeded while parsing",
                    None,
                    None,
                    entry_name,
                )
            )
            return _finish(result, started)

        for collected in loader.errors:
            item = _diagnostic("parse", collected)
            if not item.get("file"):
                item["file"] = _source_name_file(getattr(collected, "source_name", None), entry_name)
            errors.append(item)
        if errors:
            return _finish(result, started)

        try:
            interpreter = Interpreter([], output.append, config=config)
            interpreter.interpret(program)
        except TypeCheckFailure as failure:
            for diagnostic in failure.errors:
                item = _diagnostic("typecheck", diagnostic)
                if not item.get("file"):
                    item["file"] = _source_name_file(
                        getattr(diagnostic, "source_name", None), entry_name
                    )
                errors.append(item)
            return _finish(result, started)
        except LexError as error:
            errors.append(_error("lex", error.message, error.line, error.column, entry_name))
        except ParseError as error:
            errors.append(_error("parse", error.message, error.line, error.column, entry_name))
        except ThrownValue as thrown:
            item = _thrown_value(thrown)
            item["file"] = _source_name_file(thrown.source_name, entry_name)
            errors.append(item)
        except RuntimeErrorX as error:
            item = _runtime_error(error)
            item["file"] = _source_name_file(error.source_name, entry_name)
            errors.append(item)
        except RecursionError:
            errors.append(
                _error(
                    "runtime",
                    "Maximum recursion depth exceeded; the program nests too deeply",
                    None,
                    None,
                    entry_name,
                )
            )
        except MemoryError:
            errors.append(
                _error("runtime", "Out of memory while running the program", None, None, entry_name)
            )
        except KeyboardInterrupt:
            errors.append(_error("runtime", "Execution was interrupted", None, None, entry_name))
        except Exception as error:  # noqa: BLE001 — surface anything else cleanly
            errors.append(_error("internal", f"{type(error).__name__}: {error}", None, None, entry_name))
        else:
            if not errors:
                result["ok"] = True

    return _finish(result, started)


def format_file(source: str, filename: str = DEFAULT_ENTRY) -> dict[str, Any]:
    """Reformat *source* with the canonical X formatter."""
    if not isinstance(source, str):
        return {"ok": False, "source": source, "error": "Source must be a string"}
    try:
        formatted = format_source(source, source_name=filename)
    except LexError as error:
        return {
            "ok": False,
            "source": source,
            "error": f"{error.message} (line {error.line}, column {error.column})",
            "line": error.line,
            "column": error.column,
        }
    except ParseError as error:
        return {
            "ok": False,
            "source": source,
            "error": f"{error.message} (line {error.line}, column {error.column})",
            "line": error.line,
            "column": error.column,
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "source": source, "error": f"{type(error).__name__}: {error}"}
    return {"ok": True, "source": formatted, "error": None}


def _prepare_files(
    files: Any, entry: str | None
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(files, list) or not files:
        return [], [_error("internal", "files must be a non-empty list", None, None)]

    if len(files) > MAX_FILES:
        return [], [
            _error("internal", f"At most {MAX_FILES} files are allowed in the playground", None, None)
        ]

    cleaned: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(_error("internal", f"files[{index}] must be an object", None, None))
            continue
        name = item.get("name")
        content = item.get("content", "")
        if not isinstance(name, str) or not name.strip():
            errors.append(_error("internal", f"files[{index}].name is required", None, None))
            continue
        name = _safe_filename(name)
        if not name.endswith(".x"):
            name = name + ".x"
        if name in seen:
            errors.append(_error("internal", f"Duplicate file name '{name}'", None, None))
            continue
        if not isinstance(content, str):
            errors.append(_error("internal", f"files['{name}'].content must be a string", None, None))
            continue
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            errors.append(
                _error("internal", f"File '{name}' is too large (max {MAX_FILE_BYTES} bytes)", None, None)
            )
            continue
        seen.add(name)
        cleaned.append((name, content))

    if errors or not cleaned:
        return [], errors or [_error("internal", "No valid files", None, None)]

    entry_name = _safe_filename(entry or DEFAULT_ENTRY)
    if not entry_name.endswith(".x"):
        entry_name = entry_name + ".x"
    if entry_name not in seen:
        # Prefer main.x, else first file.
        main = next((name for name, _ in cleaned if name == DEFAULT_ENTRY), None)
        entry_name = main or cleaned[0][0]
    else:
        # Move entry to the front so run_files can treat index 0 as entry.
        cleaned.sort(key=lambda pair: 0 if pair[0] == entry_name else 1)

    # Entry is always index 0 after sort.
    if cleaned[0][0] != entry_name:
        cleaned.sort(key=lambda pair: 0 if pair[0] == entry_name else 1)
    return cleaned, []


def _safe_filename(name: str) -> str:
    base = Path(str(name)).name.strip()
    base = base.replace("\\", "_").replace("/", "_")
    base = "".join(ch for ch in base if ch.isalnum() or ch in "._-")
    if not base or base in {".", ".."}:
        base = DEFAULT_ENTRY
    return base[:64]


def _source_name_file(source_name: str | None, fallback: str) -> str:
    if not source_name:
        return fallback
    return Path(source_name).name or fallback


def _finish(result: dict[str, Any], started: float) -> dict[str, Any]:
    result["durationMs"] = round((time.perf_counter() - started) * 1000.0, 3)
    if result["errors"] and not result["ok"]:
        result["ok"] = False
    return result


def _error(
    kind: str,
    message: str,
    line: int | None,
    column: int | None,
    file: str | None = None,
    *,
    notes: Sequence[str] = (),
    helps: Sequence[str] = (),
    end_line: int | None = None,
    end_column: int | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "message": message,
        "line": line,
        "column": column,
        "file": file,
        "notes": list(notes),
        "helps": list(helps),
        "endLine": end_line,
        "endColumn": end_column,
    }


def _diagnostic(kind: str, diagnostic: Any) -> dict[str, Any]:
    source_name = getattr(diagnostic, "source_name", None)
    return _error(
        kind,
        getattr(diagnostic, "message", str(diagnostic)),
        getattr(diagnostic, "line", None),
        getattr(diagnostic, "column", None),
        Path(source_name).name if source_name else None,
        notes=getattr(diagnostic, "notes", ()) or (),
        helps=getattr(diagnostic, "helps", ()) or (),
        end_line=getattr(diagnostic, "end_line", None),
        end_column=getattr(diagnostic, "end_column", None),
    )


def _runtime_error(error: RuntimeErrorX) -> dict[str, Any]:
    name = getattr(error, "exception_name", None) or "RuntimeException"
    message = getattr(error, "message", str(error))
    source_name = getattr(error, "source_name", None)
    return _error(
        "runtime",
        f"{name}: {message}",
        getattr(error, "line", None),
        getattr(error, "column", None),
        Path(source_name).name if source_name else None,
        end_line=getattr(error, "end_line", None),
        end_column=getattr(error, "end_column", None),
    )


def _thrown_value(thrown: ThrownValue) -> dict[str, Any]:
    value = thrown.value
    message = "Uncaught exception"
    name = "Exception"
    fields = getattr(value, "fields", None)
    if isinstance(fields, dict):
        raw_message = fields.get("message")
        if isinstance(raw_message, str) and raw_message:
            message = raw_message
        raw_name = fields.get("name")
        if isinstance(raw_name, str) and raw_name:
            name = raw_name
    xclass = getattr(value, "xclass", None)
    declaration = getattr(xclass, "declaration", None)
    class_name = getattr(declaration, "name", None)
    if isinstance(class_name, str) and class_name:
        name = class_name
    source_name = thrown.source_name
    return _error(
        "runtime",
        f"{name}: {message}",
        thrown.line,
        thrown.column,
        Path(source_name).name if source_name else None,
    )


class _virtual_project:
    """Write prepared ``(name, content)`` pairs into a temporary directory."""

    def __init__(self, files: list[tuple[str, str]]) -> None:
        self._files = files
        self._directory: Path | None = None

    def __enter__(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="x-playground-"))
        for name, content in self._files:
            (directory / name).write_text(content, encoding="utf-8")
        self._directory = directory
        return directory

    def __exit__(self, *exc_info: object) -> None:
        if self._directory is not None:
            shutil.rmtree(self._directory, ignore_errors=True)
