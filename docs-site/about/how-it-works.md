# How this site is built

This page documents the site you are reading: how a plain `README.md` in the
repository becomes a rendered static webpage, what the shell does, and what
rules the content follows.

## The files

Everything lives in `docs-site/` and uses no frameworks, no build step, and
no dependencies.

| File | Role |
| --- | --- |
| `index.html` | The fixed shell: top bar, sidebar, content area, table of contents, script tags. Never changes when content changes. |
| `README.md` | The content source. This is a copy of the repository README, extended for the website. Editing this file is all a documentation writer does. |
| `markdown.js` | Fetches the markdown, parses it to HTML, builds the sidebar navigation. |
| `script.js` | Everything the page does after render: theme, mobile menu, table of contents, scroll spy, syntax highlighting, copy buttons. |
| `styles.css` | All styling, light and dark themes, responsive layout. |
| `about/` | Extra pages like this one, each a plain markdown file. |
| `playground.html` | The interactive playground (editor + output). Separate shell from the docs pages. |
| `playground/` | Playground assets: Web Worker, CodeMirror X mode, examples, and the interpreter wheel built by `build.py`. |

## From README.md to the page

There is no compilation. A browser loads `index.html`, the two scripts run,
and the page assembles itself:

1. `script.js` boots on `DOMContentLoaded`: theme from `localStorage`,
   mobile-menu wiring.
2. `markdown.js` fetches `README.md` (cache disabled, so edits show up on
   reload). Over `file://` this fetch fails and the shell shows the
   "Could not load README.md" box — the site must be served over HTTP.
3. The block parser turns markdown into HTML: headings get slugged ids
   (`Switch statements` → `#switch-statements`), fenced code becomes labelled
   `.code-block` cards, `output` fences become `.output` boxes, plus tables,
   lists, quotes, horizontal rules, and paragraphs with inline formatting.
4. Raw `<svg>` and `<figure>` blocks pass through untouched, which is how the
   architecture diagrams inside the README render as vector graphics.
5. HTML comments are consumed silently — that is how the
   `<!-- verify: skip -->` markers next to some examples stay invisible.
6. The parsed HTML is injected into `#doc-view`.
7. The sidebar is built from the page's `h2` headings (groups) and `h3`
   headings (children). The right-hand "On this page" list comes from the
   same headings.
8. `script.js` refreshes: syntax highlighting wraps `x` code in token spans,
   copy buttons attach to every code card, an `IntersectionObserver` drives
   the scroll spy that highlights the current section in both menus.

## Markdown conventions the parser understands

- ```` ```x file.x ```` — an X example. The label after the language becomes
  the card title.
- ```` ```output ```` — the verified stdout of the example right above it.
  Rendered as a distinct "Output" box.
- ```` ```sh ```` — a shell command.
- Ordinary fenced blocks (`text`, `markdown`, ...) render as labelled code
  cards.
- Tables, nested lists, blockquotes, `---` rules, and `**bold**` / `*em*` /
  `` `code` `` / `[links](...)` inline.
- Links to `?page=about/...` switch to another page; links starting with
  `../` or `./` resolve one directory up from `docs-site/`, which is how
  repository paths like `../examples/hello.x` work.

## Verified examples

Every `x` code block in the main README is followed by an `output` block
containing what the interpreter actually printed — each pair was executed
with `x run` and the captured stdout was pasted underneath, so the output
can never drift from the code. Blocks that cannot run standalone (multi-file
import demos, declaration-only snippets) carry a `<!-- verify: skip -->`
marker on the line before the fence; the marker hides the comment from
readers but tells the checker to leave the block alone.

To check an example yourself, copy it to a file and run:

```sh
x run example.x
```

## Running the site locally

From the repository root:

```sh
python3 -m http.server 8080
```

Then open the docs at `http://127.0.0.1:8080/docs-site/` and the playground at
`http://127.0.0.1:8080/docs-site/playground.html`. Any static file server
works; nothing has to be built first. The playground in particular needs a real
HTTP origin (its module worker and Pyodide/wheel `fetch` calls do not work from
`file://`).

## Publishing

`.github/workflows/deploy-docs.yml` publishes `docs-site/` to GitHub Pages on
pushes to `main`/`development` (and on manual dispatch). It uploads the folder
as the Pages **artifact** — the branch-based picker only offers `/ (root)` or
`/docs`, so a folder named `docs-site/` is not selectable there. Select
**Settings → Pages → Source = GitHub Actions** once. `docs-site/.nojekyll` keeps
Pages from running Jekyll over the vendored assets.

## The playground

`playground.html` is the interactive editor linked from the top bar and the
docs intro. It is still dependency-free HTML/CSS/JS, with **vendored**
CodeMirror (no CDN) and a **vendored** WebAssembly runtime:

1. The page spawns an **ES-module** Web Worker (`playground/worker.js` with
   `{ type: "module" }`) so a runaway program can be terminated without
   freezing the tab. Pyodide ≥ 314 refuses classic workers
   (`importScripts`), so the worker never uses them.
2. The worker `import()`s **Pyodide** — CPython compiled to WebAssembly — from
   `playground/pyodide/` (checked into the site so no CDN is required at
   runtime). If those files are absent it falls back to jsDelivr.
3. It then installs the local `x-language` wheel with `micropip`. That
   wheel is a pure-Python build of `xlang/` (the same interpreter the
   `x` CLI uses) — **Pyodide is the WASM build**; there is no separate
   C→WASM compile of the language. After changing anything under `xlang/`:

   ```sh
   x playground            # one-shot rebuild of the wheel
   x playground-watch      # rebuild automatically on every xlang/ edit
   x playground-check      # CI-friendly staleness check
   ```

   Equivalent: `.venv/bin/python docs-site/playground/build.py [--watch|--check]`.
   The script fingerprints `xlang/**` + `pyproject.toml`, skips work when
   unchanged, writes `wheels/x_language-*.whl` + `wheels/manifest.json`,
   and copies (or downloads) Pyodide into `playground/pyodide/` once.
   The worker appends `?v=<fingerprint>` to the wheel URL so a browser
   reload after rebuild always fetches the new interpreter.
4. **Run** (or Ctrl+Enter) posts the editor’s files to the worker, which
   calls `xlang.playground.run_files` and returns JSON: printed lines,
   typed errors with line/file/column, `notes`/`helps` follow-ups and the
   caret’s end span (`endLine`/`endColumn`), and wall-clock duration.
   `playground.js` renders each error exactly like the CLI
   (`xlang/diagnostics.py`): a rustc-style block with the `-->` location,
   the offending source line, a `^^^` caret, and `= note:` / `= help:`
   lines. It runs with
   the interpreter’s default feature set — features come from `x.toml` for
   the CLI, never from a browser control. A 15s
   timeout restarts the worker if the program hangs. **Format** (Ctrl+S)
   calls `xlang.playground.format_file` (same pipeline as `x format`).
   Fatal infrastructure failures (WASM boot, worker crash) render in the
   **fatal bar** under the output pane; program errors stay in `#errors`.
5. The editor is CodeMirror 5 with a hand-written X mode
   (`playground/x-mode.js`), bracket colours (guide lines off by default),
   auto-close brackets/quotes, and autocomplete (`playground/completions.js`).
   **Ctrl+Space** lists keywords/types/snippets and the names declared in the
   current buffer — `collectDeclarations` in `playground.js` scans for
   variables, parameters, functions, types/classes/interfaces/enums and
   imports; after `.` it uses a simple
   type inference (`inferVarType` in `playground.js`) so string/list locals
   offer the right members. CodeMirror and its addons are vendored under
   `playground/codemirror/` — no CDN. Up to five files live under a virtual
   `playground/` folder; the splitter between panes is draggable. Matching
   brackets use underline/bold only — no bar.

See the main README section
[Browser playground (WebAssembly)](../README.md) for the full technology
stack and how interpreter edits are republished to WASM.

Sandbox notes: there is no network or OS-thread support inside Pyodide, so
`System.io.Network` and thread demos will not run in the browser.

## Editing rules

- Content changes = edit `docs-site/README.md` (or a file in
  `docs-site/about/`). Reload the page and the site follows.
- `index.html`, `markdown.js`, `script.js`, and `styles.css` are the shell.
  They only change when the behaviour of the site itself changes.
- Keep examples honest: run them, paste the real output underneath.
- **Documentation is part of the change.** Feature additions, bug fixes,
  architecture changes, and other user-visible work must update the
  concerned README (and its parent README) in the same change — see
  `AGENTS.md` at the repository root for the full mapping.

## Extra pages and the ?page= parameter

The shell renders one markdown file at a time. The main page always uses
`README.md`. Any other page inside `docs-site/` is selected with a query
parameter:

| URL | Renders |
| --- | --- |
| `/docs-site/` | `docs-site/README.md` |
| `/docs-site/?page=about/how-it-works.md` | `docs-site/about/how-it-works.md` |
| `/docs-site/?page=about/project-ideas.md` | `docs-site/about/project-ideas.md` |

Only names matching `about/<file>.md` style paths are accepted (no `..`, no
outside files). On an extra page the sidebar lists that page's own headings,
the top bar title becomes the page's `h1`, and the first sidebar entry links
back to the main documentation.

## Project ideas

The goals and future ideas for this documentation project are on their own
page: [Project ideas](?page=about/project-ideas.md).
