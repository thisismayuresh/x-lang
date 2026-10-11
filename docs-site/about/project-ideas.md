# Project ideas

What this documentation project set out to do, and what could come next.

## Principles that shipped

- **The README is the single source of truth.** Documentation lives in the
  repository next to the code. No CMS, no separate docs toolchain, no
  generated HTML committed to git. The site reads `docs-site/README.md`
  directly and renders it in the browser.
- **Content and shell are separate.** Writers only ever touch markdown.
  `index.html`, `markdown.js`, `script.js`, and `styles.css` are a fixed
  frame that never needs editing for content changes.
- **Zero dependencies, vanilla everything.** No React, no highlight.js, no
  CSS framework. The whole site is four files a browser loads as-is.
- **Examples are verified, not aspirational.** Every runnable example in the
  README was executed with the real interpreter and its real stdout pasted
  underneath as an `output` block. What you read is what the language does.
- **Diagnostics are truth.** Where the docs describe type-checker or
  parser behaviour, the wording and error strings come from running the
  compiler, not from guesses.
- **Diagrams live in the README.** SVG is passed through the parser, so
  architecture drawings version with the document and work offline.
- **Readable in both themes.** Light and dark, a sticky table of contents,
  scroll-spy navigation, mobile menu — without a framework.

## Ideas for what comes next

- **Search** across the rendered README (build a heading + text index client
  side, no server).
- **Playground polish** — the first version shipped as
  [`playground.html`](playground.html) (CodeMirror editor + Pyodide/WASM
  worker). Next: shareable URLs for snippets, multi-file projects, and
  per-example **Run** buttons wired to the same worker.
- **Version switcher** for docs of released language versions.
- **Diff view** for examples that changed between releases.
- **`x doc serve`** — a toolchain command that starts a static server on
  `docs-site/` so readers never need to remember the `python3 -m http.server`
  incantation.
- **Publishing pipeline** to GitHub Pages / any static host (it is already a
  static folder — this is mostly CI).
- **Per-example run buttons** wired to the same endpoint as the playground.
- **Inline cross-links** auto-checked (no dead `#anchors`, no links to
  sections that were renamed).
- **Translation-ready structure** — one README per language, same shell.

## How to add an idea

Ideas are prose in this file — edit `docs-site/about/project-ideas.md`,
reload the site, done. If an idea grows into a real feature, it belongs in
the repository issue tracker, not in a doc comment.
