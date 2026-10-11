# Agent instructions — X language

This repository is the X language prototype: a Python interpreter (`xlang/`),
CLI (`x`), examples, and a static docs site (`docs-site/`) with a browser
playground that runs the real interpreter in WebAssembly (Pyodide).

## Always verify interpreter changes

Two checks are **mandatory whenever anything under `xlang/` changes** — treat a
change without them as unfinished:

1. **Run the full test suite.** Do not run only a subset while iterating and
   stop there; before you call the change done, run
   `.venv/bin/python -m pytest tests/ -q` and confirm no *new* failures. (A
   handful of pre-existing `typeOf`/`strict_typing` failures are known; do not
   introduce new ones.)
2. **Recompile the WebAssembly playground wheel.** The docs-site playground
   ships a wheel built from `xlang/`, so it goes stale the moment the
   interpreter changes. Rebuild it with `x playground` (or
   `.venv/bin/python docs-site/playground/build.py`) and confirm
   `x playground-check` passes.

## Documentation is part of the change

**Every meaningful code change must leave the documentation correct.** If you
skip this, the change is incomplete.

Update docs in the same change (commit / session) as the code for:

| Kind of change | Update at least |
| --- | --- |
| Feature addition | Parent README section + any related sub-README |
| Bug fix that changes user-visible behaviour | The section that described the old behaviour |
| Architecture / pipeline change | The architecture section of the relevant README |
| New CLI flag, config key, or script | CLI / configuration section of `docs-site/README.md` |
| Playground / WASM / docs-site change | `docs-site/README.md` **and** `docs-site/about/how-it-works.md` |
| New file under `docs-site/about/` | Link from the main docs page + how-it-works table if relevant |
| Public API of `xlang.playground` | The playground tech table / worker notes |
| New example that is meant to be published | Nearby prose in `docs-site/README.md` |

### Which file?

1. **Language / interpreter (`xlang/`, `pyproject.toml`)** →
   - User-facing: `docs-site/README.md` (and root `README.md` if it still
     documents the same topic).
   - Build/packaging notes: `docs-site/README.md` “Browser playground”.
2. **Playground (`docs-site/playground*`)** →
   - `docs-site/README.md` → “Browser playground (WebAssembly)”.
   - `docs-site/about/how-it-works.md` → “The playground”.
3. **Docs site shell (`index.html`, `markdown.js`, `script.js`, `styles.css`)** →
   - `docs-site/about/how-it-works.md` (file table + behaviour).
4. **Examples / tests / DSA library** →
   - Root `README.md` or the matching sub-README
     (`examples/*/README.md`, `DSA_LIBRARY.md`, `LANGUAGE_FEATURES.md`).

Parent READMEs stay the source of truth. When a sub-area has its own README,
keep the parent’s summary in sync — do not leave the parent describing a
removed or renamed behaviour.

### Playground-specific notes

- The worker is an **ES module** (`new Worker(..., { type: "module" })`).
  Pyodide ≥ 314 rejects classic workers (`importScripts`).
- CodeMirror 5 + addons are **vendored** under
  `docs-site/playground/codemirror/` — do not re-introduce CDN script tags.
- Completions live in `playground/completions.js` (static catalog) +
  `xHint`/`collectDeclarations`/`inferVarType` in `playground.js`
  (declared names at top level, type-aware members after `.`).
- After editing `xlang/`, rebuild the wheel: `x playground` or
  `x playground-watch`. Stale wheel → `x playground-check` fails.
- Fatal / infrastructure errors (WASM boot, worker crash) go to the
  **fatal bar** under the output pane (`#fatal-bar`). User program errors
  stay in `#errors`. Do not put marketing copy in the fatal bar.
- Matching-bracket highlight is colour/underline only — no bar/outline.
- Bracket guide lines are off by default (`bracketGuides: false`).

### Local preview

```sh
python3 -m http.server 8080
# http://127.0.0.1:8080/docs-site/
# http://127.0.0.1:8080/docs-site/playground.html
```

## What “done” means

- Code and docs updated together.
- For interpreter changes (anything under `xlang/`): run the **whole** test
  suite — `.venv/bin/python -m pytest tests/ -q` — and confirm no *new*
  failures. A handful of pre-existing `typeOf` failures may remain; never ignore
  a new one.
- Recompile the WebAssembly playground wheel whenever `xlang/` changed
  (`x playground`, or `x playground-watch` while iterating) and confirm
  `x playground-check` reports `ok`. A stale wheel means the browser playground
  runs old interpreter code.
- For playground JS: `node --check` on edited `.js` files.
- Do not commit secrets. Do not invent URLs.
