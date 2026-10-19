# Changelog and release notes

All notable changes to the X language prototype, CLI, playground, and docs
site. Newest entries first. Dates use the local calendar day when the change
landed.

## Unreleased

### Playground

- **Monaco editor** replaces CodeMirror 5. Monaco and its AMD loader are
  **vendored** under `docs-site/playground/monaco/` (about 4.3 MB) — no CDN
  at runtime. Light (`vs`) and dark (`vs-dark`) themes follow the site
  theme toggle.
- Custom **X language** support: Monarch tokenizer (keywords, types,
  strings including templates, comments), language configuration for
  auto-closing brackets/quotes, and a completion provider (Ctrl+Space /
  as you type after `.`) with type-aware members
  (`let s = "hi"` → string methods).
- Multi-file projects still use up to 5 virtual files; each file is a
  separate Monaco **model** (`inmemory://playground/<name>.x`).
- Error lines use Monaco **markers** (squiggles) plus the rustc-style
  diagnostic block in the output pane.
- Worker and fatal-bar behaviour unchanged: WASM boot / worker crash
  messages appear under the output; program errors stay in `#errors`.

### Documentation

- New **Changelog and release notes** page
  (`docs-site/about/changelog.md`), linked from the docs intro and the
  docs-site README.

## Earlier notes (pre-changelog file)

These items shipped before this file existed; they are summarized here so
the history is not lost.

### WASM playground

- Browser playground runs the **real** `xlang` interpreter inside
  **Pyodide** (CPython → WebAssembly) in an **ES-module** Web Worker.
  Interpreter changes ship as a pure-Python wheel (`x playground`,
  `x playground-watch`, `x playground-check`).
- Multi-file (max 5), Format (Ctrl+S), draggable splitter, examples,
  localStorage project restore, fatal error bar.
- Pyodide is vendored under `docs-site/playground/pyodide/` with CDN
  fallback only if the local files are missing.

### Language / CLI (selected)

- Classes, interfaces, enums, decorators, pattern matching, exceptions,
  namespaces, async, threads, collections library, formatter, watch mode,
  `x.toml` config and scripts, rustc-style diagnostics.

---

When you add a user-visible change, append a bullet under **Unreleased**
(or a dated section if you cut a release) in the same change as the code.
See `AGENTS.md` for the documentation policy.
