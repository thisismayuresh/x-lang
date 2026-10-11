#!/usr/bin/env python3
"""Build / watch the playground runtime for the docs-site WebAssembly worker.

The browser does **not** compile a separate WASM build of the interpreter.
Pyodide *is* CPython compiled to WebAssembly; it installs a pure-Python
wheel of ``xlang/`` and runs ``xlang.playground.run_source``. So whenever
you change the interpreter under ``xlang/``, rebuild the wheel and the
playground picks up the new behaviour.

Usage (from the project root, inside the project venv):

    .venv/bin/python docs-site/playground/build.py           # one-shot build
    .venv/bin/python docs-site/playground/build.py --watch   # rebuild on change
    .venv/bin/python docs-site/playground/build.py --check   # exit 1 if stale

Or via the project script aliases (see x.toml):

    x playground
    x playground-watch

What a build does
-----------------
1. Hashes ``xlang/**``, ``pyproject.toml`` → source fingerprint.
2. If the fingerprint matches ``wheels/manifest.json``, skips (unless --force).
3. Builds ``wheels/x_language-*.whl`` with pip and writes the fingerprint.
4. Ensures the vendored Pyodide runtime lives in ``pyodide/`` (once).

The worker appends ``?v=<fingerprint>`` to the wheel URL so a hard reload
after rebuild always fetches the new interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAYGROUND_DIR = Path(__file__).resolve().parent
WHEELS_DIR = PLAYGROUND_DIR / "wheels"
PYODIDE_DIR = PLAYGROUND_DIR / "pyodide"
MANIFEST = WHEELS_DIR / "manifest.json"
XLANG_DIR = ROOT / "xlang"
PYPROJECT = ROOT / "pyproject.toml"

PYODIDE_VERSION = "314.0.7"
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
PYODIDE_FILES = (
    "pyodide.js",
    "pyodide.mjs",
    "pyodide.asm.wasm",
    "pyodide.asm.mjs",
    "python_stdlib.zip",
    "pyodide-lock.json",
    "micropip-0.11.1-py3-none-any.whl",
)

WATCH_POLL_SECONDS = 0.75


def source_fingerprint() -> str:
    """Stable hash of interpreter sources + packaging metadata."""
    digest = hashlib.sha256()
    files: list[Path] = []
    if XLANG_DIR.is_dir():
        files.extend(
            path
            for path in XLANG_DIR.rglob("*")
            if path.is_file()
            and path.suffix == ".py"
            and "__pycache__" not in path.parts
        )
    if PYPROJECT.is_file():
        files.append(PYPROJECT)
    for path in sorted(files):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def load_manifest() -> dict:
    if not MANIFEST.is_file():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def wheel_is_current(fingerprint: str) -> bool:
    manifest = load_manifest()
    if manifest.get("sourceFingerprint") != fingerprint:
        return False
    wheel_name = manifest.get("wheel")
    if not wheel_name:
        return False
    return (WHEELS_DIR / wheel_name).is_file()


def build_wheel(fingerprint: str) -> int:
    if not PYPROJECT.is_file():
        print(f"error: pyproject.toml not found under {ROOT}", file=sys.stderr)
        return 1

    WHEELS_DIR.mkdir(parents=True, exist_ok=True)
    for stale in WHEELS_DIR.glob("x_language-*.whl"):
        stale.unlink()

    command = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "-w",
        str(WHEELS_DIR),
        str(ROOT),
    ]
    print("+", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL)
    if completed.returncode != 0:
        # Retry with visible output so build failures are debuggable.
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode != 0:
            return completed.returncode

    wheels = sorted(WHEELS_DIR.glob("x_language-*.whl"))
    if not wheels:
        print("error: pip wheel produced no x_language-*.whl", file=sys.stderr)
        return 1

    wheel = wheels[-1]
    MANIFEST.write_text(
        json.dumps(
            {
                "wheel": wheel.name,
                "sourceFingerprint": fingerprint,
                "pyodideVersion": PYODIDE_VERSION,
                "builtAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": (
                    "Built by docs-site/playground/build.py. "
                    "Re-run (or use --watch) after changing xlang/."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"built {wheel.name} ({wheel.stat().st_size} bytes)")
    print(f"fingerprint {fingerprint}")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")
    return 0


def _local_node_modules_pyodide() -> Path | None:
    candidates = [
        ROOT / "node_modules" / "pyodide",
        Path("/tmp/opencode/pyodide-test/node_modules/pyodide"),
        Path.home() / "node_modules" / "pyodide",
    ]
    for candidate in candidates:
        if (candidate / "pyodide.js").is_file() and (candidate / "pyodide.asm.wasm").is_file():
            return candidate
    return None


def ensure_pyodide_runtime() -> int:
    PYODIDE_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for name in PYODIDE_FILES if not (PYODIDE_DIR / name).is_file()]
    if not missing:
        return 0

    source = _local_node_modules_pyodide()
    if source is not None:
        print(f"copying Pyodide runtime from {source}")
        for name in PYODIDE_FILES:
            src = source / name
            if not src.is_file():
                print(f"error: {src} is missing", file=sys.stderr)
                return 1
            shutil.copy2(src, PYODIDE_DIR / name)
        print(f"vendored {len(PYODIDE_FILES)} files into {PYODIDE_DIR.relative_to(ROOT)}")
        return 0

    print(f"downloading Pyodide {PYODIDE_VERSION} from {PYODIDE_CDN}")
    for name in missing:
        url = PYODIDE_CDN + name
        target = PYODIDE_DIR / name
        print(f"  GET {url}")
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                target.write_bytes(response.read())
        except OSError as error:
            print(f"error: download failed for {url}: {error}", file=sys.stderr)
            return 1
    print(f"vendored {len(missing)} files into {PYODIDE_DIR.relative_to(ROOT)}")
    return 0


def build_once(force: bool = False) -> int:
    fingerprint = source_fingerprint()
    if not force and wheel_is_current(fingerprint):
        print(f"playground wheel up to date ({fingerprint})")
        return ensure_pyodide_runtime()

    print(f"building playground wheel (fingerprint {fingerprint})…")
    status = build_wheel(fingerprint)
    if status != 0:
        return status
    return ensure_pyodide_runtime()


def _tracked_mtimes() -> dict[Path, float]:
    mtimes: dict[Path, float] = {}
    for path in XLANG_DIR.rglob("*") if XLANG_DIR.is_dir() else []:
        if path.is_file() and path.suffix == ".py" and "__pycache__" not in path.parts:
            try:
                mtimes[path] = path.stat().st_mtime
            except OSError:
                pass
    if PYPROJECT.is_file():
        mtimes[PYPROJECT] = PYPROJECT.stat().st_mtime
    return mtimes


def watch() -> int:
    status = build_once()
    if status != 0:
        return status

    print(f"watching {XLANG_DIR.relative_to(ROOT)}/*.py — Ctrl+C to stop")
    previous = _tracked_mtimes()
    last_fp = source_fingerprint()
    try:
        while True:
            time.sleep(WATCH_POLL_SECONDS)
            current = _tracked_mtimes()
            if current != previous:
                previous = current
                fingerprint = source_fingerprint()
                if fingerprint == last_fp:
                    continue
                print("\n— interpreter changed, rebuilding —")
                status = build_once(force=True)
                last_fp = source_fingerprint()
                if status != 0:
                    print("build failed; still watching…", file=sys.stderr)
                else:
                    print("done. Reload the playground in the browser to pick it up.")
    except KeyboardInterrupt:
        print("\nstopped watching")
        return 0


def check() -> int:
    fingerprint = source_fingerprint()
    if wheel_is_current(fingerprint):
        print(f"ok: playground wheel matches xlang/ ({fingerprint})")
        return 0
    print(
        "stale: playground wheel does not match xlang/ sources.\n"
        "Run: .venv/bin/python docs-site/playground/build.py",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watch",
        action="store_true",
        help="rebuild the wheel whenever xlang/**/*.py changes",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 0 if the wheel matches xlang/, else 1",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebuild even if the fingerprint already matches",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check()
    if args.watch:
        return watch()
    return build_once(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
