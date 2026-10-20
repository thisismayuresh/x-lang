# Changelog and release notes

All notable changes to the X language prototype, CLI, playground, and docs
site. Newest entries first. Dates use the local calendar day when the change
landed.

**How versions are recorded.** The repository carried no git tags before this
file existed, so the milestones below are recorded retroactively from git
history (commit dates and merge PRs). `pyproject.toml` has read `0.1.0`
since the first commit; the `0.0.x` labels mark pre-release development
trains, not published packages. The VS Code extension versions on its own
(`vscode-xlang/package.json`).

## Current version

- **`x` CLI / `x-language` package — `0.1.0`** (`x --version`, `pyproject.toml`)
- **VS Code extension — `0.1.1`**
- In progress lands under **Unreleased** below.

## Unreleased

### Formatter

- **Object literals that do not fit in 80 columns** are broken one
  `key: value` field per line with a trailing comma (Prettier-style print
  width). Short literals stay inline, nested short objects stay inline on
  their field line, and match-arm patterns (`{name: person} => ...`) are
  never broken.

### Language / interpreter

- **Integer and float keys** in object literals: `{ 200: "a", 1.5: "b" }`
  type-checks against `object<integer, ...>` / `object<float, ...>`, runs
  with `m[200]`, destructures as `{ 200: x }`, matches as `{ 200: v } =>`,
  and formats with the numeric key intact. Integer and string keys are
  distinct entries (`m[200]` ≠ `m["200"]`).
- **Dot access for numeric keys**: `m.200` is sugar for `m[200]` (and
  `m?.200` for `m?.[200]`), so integer-keyed maps read the same as
  string-keyed ones. The lexer no longer swallows the dot in `200.array`
  into a float, so chains like `Partipants.200.array[0]` parse.
- **Member imports no longer leak the module scope**. `import lib.greet`
  binds only `greet`; sibling declarations stay private to `lib`. Using a
  hidden sibling is a type error with an ``add `import lib.X` `` suggestion.
  Whole-module, grouped, alias, and wildcard imports are unchanged.
- **Enums and interfaces used as values are rejected**: `print(Gender)`
  reports `Enum 'Gender' is a type, not a value`; `IFoo(...)` reports only
  `Cannot construct interface`; `typeOf(Gender)` stays accepted.
  Accessing a member through a type alias (`Participants.Gender`)
  reports `Type alias '…' has no member` with an import suggestion.
- **Readable record types in diagnostics**: object-shaped types print as
  `{ name: string, age: integer }` (and nested/numeric keys as
  `{ 200: { name: string } }`) instead of the internal
  `record{string name;integer age}` spelling.
- `print` on an enum or namespace prints `[enum Gender]` /
  `[namespace util]` instead of leaking a Python `Environment` repr.
- Enum member access (`Gender.FEMALE`) now infers as the enum type rather
  than `any`.
- **Interface/record mismatches say what is missing**. Returning, assigning,
  or passing an object literal where an interface (or record) is expected now
  adds gap notes: ``missing required member `age: integer` ``,
  ``missing required method `greet()` ``, and
  ``member `name`: expected `string`, found `integer` `` for each member that
  does not line up.

### Editor / LSP

- **Quick fixes for missing imports**: the checker's
  ``add `import utils.greet` `` suggestion now surfaces as an
  ``Add `import utils.greet` `` code action in the VS Code extension,
  inserting the statement after the file's last import.
- **Auto-import completions**: typing the name of an export from a local
  `.x` file offers it with the matching `import` edit applied on accept.
  Already-declared names and already-imported modules are skipped.

### Tooling / CI

- **GitHub Actions test workflow** (`.github/workflows/tests.yml`): runs the
  full suite (interpreter tests + CSV corpus) on Python 3.10 and 3.14, checks
  the playground wheel is not stale against `xlang/`, and `node --check`s the
  authored docs-site JavaScript on every push and pull request. Known
  typeOf/showcase failures are deselected with a commented list to burn down.
- `pyproject.toml` gained a `dev` extra (`pip install -e ".[dev]"`: pytest
  plus `pygls`/`lsprotocol` for the LSP tests) so CI and local runs install
  the same test dependencies.
- The suite's config-discovery test now passes `--config` explicitly (the
  repository's own `x.toml` used to shadow the fixture's), and corpus row
  `R0441` was updated to the documented `new Collections.HashMap()` instance
  style — so the pre-CI baseline is green apart from the deselected list.

### Documentation

- The docs renderer understands **CommonMark code spans**: closing on an
  equal run of backticks, so help strings like ``add `import X` `` and the
  inline `` ```x file.x `` examples in how-it-works render correctly.
- Restored five lost list-continuation indents in `docs-site/README.md`
  (decorator and `delete` bullets plus the checklist wrap), whose
  continuation lines were rendering as stray paragraphs.
- "Current limitations" now records that interfaces have no
  TypeScript-style index signatures (`[key: number]: T` reports
  `Expected a name`) and shows the `object<K, V>` alias equivalent.
- The root README links the published site and the
  **[browser playground](https://thisismayuresh.github.io/x-lang/playground.html)**
  up top and documents the new CI workflow under Tests.

## 0.1.0 — Monaco playground, topbar navigation & changelog (2026-10-19)

Merge: PR #14 (`feat/playground-monaco-and-changelog`).

- **Monaco editor** replaces CodeMirror 5 in the browser playground. Monaco
  and its AMD loader are **vendored** under `docs-site/playground/monaco/`
  (about 4.3 MB) — no CDN at runtime. Light (`vs`) and dark (`vs-dark`)
  themes follow the site theme toggle.
- Custom **X language** support: Monarch tokenizer (keywords, types,
  strings including templates, comments), language configuration for
  auto-closing brackets/quotes, and a completion provider (Ctrl+Space /
  as you type after `.`) with type-aware members
  (`let s = "hi"` → string methods).
- Multi-file projects use up to 5 virtual files, each a separate Monaco
  **model** (`inmemory://playground/<name>.x`); error lines use Monaco
  **markers** plus the rustc-style diagnostic block in the output pane.
- **Topbar navigation** across the docs site: Docs / Changelog / Playground
  with an active tab.
- New **Changelog and release notes** page (`docs-site/about/changelog.md`),
  linked from the docs intro and the docs-site README.
- `project-ideas.md` is no longer tracked (gitignored).

## 0.0.7 — TypeScript compilation & test hardening (2026-10-18)

Merge: PR #13 (`feat/typescript-compile-and-tests`).

- **`x compile`** — type-checks like `check`, then emits a TypeScript
  translation of the entry file and its imports (`codegen` package with a
  tree-walking TypeScript emitter). `--target`/`--out` flags and a
  `[compile]` table in `x.toml`.
- **Tests grow by ~300 cases**: 133 TypeScript-compile emitter/CLI tests,
  39 class/inheritance/nesting, 61 object-literal/type-annotation/value-type,
  and 65 switch/match/decorator/closure/equality/enum/exception cases.
- TypeScript compile demos for oop, match, async, exceptions and nesting;
  config docs for `[compile]` and the full built-in command list.
- Playground wheel rebuilt from the updated `xlang/` sources.

## 0.0.6 — Example gallery (2026-10-15)

Merge: PR #12 (`feat/examples`).

- New examples: `exceptions/try_with_resources.x`, `subscription_demo.x`,
  `toString.x`, with README entries for each.

## 0.0.5 — Diagnostics, completions & cross-file editor intelligence (2026-10-13)

Merges: PR #8 / #9 (`feat/doc-site-and-wsam-playground`), PR #11
(`feat/banking-platform-and-lsp-navigation`).

- **`object<K, V>` literals are validated key by key** with friendly
  diagnostics (a numeric key against `object<integer, …>` etc.).
- The playground renders **rustc-style diagnostics** in the browser and
  always launches clean on the hello-world example.
- **Type-aware member completions** in VS Code: after
  `let p = new Point();` the popup for `p.` offers only `Point`'s fields
  and methods; built-in collections get the same treatment.
- **Collections switch to `new` + instance methods** (from static call
  style) — the VS Code extension version bumps to **0.1.1** here.
- **Import-aware LSP diagnostics and cross-file Go to Definition**:
  the server loads the document through the same `ModuleLoader` as
  `x check`, so cross-file `implements`/`extends` type errors surface, and
  Ctrl+Click crosses direct `import` statements.
- `banking_platform` — a Java-to-X translation example.
- Decorators demo extended (composing, method and class decorators);
  `settings_types` fixed to pass strict typing; `INTROSPECTION.md` design
  notes added.

## 0.0.4 — Doc site, type-system flags & browser playground (2026-10-10 → 2026-10-11)

Merges: PR #6 / #7 (`feat/doc-site-and-wsam-playground`).

- **Docs site** ships (`docs-site/`), later published via the GitHub Pages
  workflow (with `.nojekyll` so assets serve verbatim).
- **String-literal types and literal unions**: annotations like
  `"theme" | "backup"` (also with colon syntax), enforced by the type
  checker, plus
  case-insensitive **primitive aliases** behind the `primitive_aliases`
  feature flag in `x.toml` (parser, type checker, runtime overload
  matching, config, tests).
- **Browser playground** (first cut): the real `xlang` interpreter inside
  **Pyodide** (CPython → WebAssembly) in an **ES-module** Web Worker;
  `run_files` / `run_source` / `format_file` API; wheel build script
  (`x playground`, `x playground-watch`, `x playground-check`).
  Pyodide and CodeMirror 5 are **vendored** (no CDN, with CDN fallback only
  if the local files are missing).
- Playground editor: CodeMirror X syntax mode, bracket guides, static
  completion catalog, bundled example programs, multi-file (max 5),
  Format (Ctrl+S), draggable splitter, localStorage restore, fatal error
  bar.
- `AGENTS.md` repository agent instructions; playground internals docs;
  `settings_types` example.

## 0.0.3 — REPL, import suggestions & formatter (2026-10-09)

Merges: PR #4 (`feat/repl-implemented`), PR #5 (`feat/implemented-formatter`).

- **REPL** — session-scoped type checking of each entry before execution.
- **File member import suggestions**: using a hidden sibling declaration
  suggests the `import` that would bind it.
- **`x format`** — the token-stream formatter (two-space indentation,
  normalized spacing, idempotent).
- `dev` script added to `x.toml` scripts.

## 0.0.2 — HTTP module, LSP & type suggestions (2026-10-08)

Merges: PR #2 (`feat/implemented-http-module`), PR #3
(`feat/lsp-and-type-suggestions`).

- **HTTP `fetch`** in `System.io.Network`.
- **Language Server Protocol server + type suggestions** for VS Code
  (diagnostics, completions, hover) and the first `vscode-xlang`
  extension scaffold.
- **File watch mode** (`x --watch` / `-w`) wired into the CLI usage, and
  toml default-export fixes.

## 0.0.1 — Core language, runtime & standard library (2026-10-05 → 2026-10-07)

Merge: PR #1 (`feat/implement-toml-and-language-specs`).

- **The language itself**: lexer, parser and tree-walking interpreter for
  the full surface — classes, interfaces, enums, decorators, pattern
  matching, exceptions, namespaces, async and threads; multiline template
  literals with interpolation; top-level executable statements.
- **Modules**: import/export with module structure, duplicate-`main`
  warnings, an enhanced module loader, and language utils.
- **Standard library**: `Console` built-in io module, asynchronous
  filesystem operations, and the **DSA collections library** — HashMap,
  LinkedList, Stack, Queue, PriorityQueue (heapq), Trie (incl.
  `getWordsWithPrefix`), Set, the iterator protocol and `List.groupBy` /
  `partition`.
- **Configuration**: `x.toml`-based configuration and feature flags, a
  sample `x.test.toml`, and configuration management in the CLI.
- **Diagnostics**: proper type-error reporting; constructor rules (a
  constructor may not return a value, return-type validation).
- **Tests begin**: the first interpreter/type-checker test batches.
- 20 DSA algorithm examples; interface declarations with runtime
  validation of function types.

---

When you add a user-visible change, append a bullet under **Unreleased**
(or a dated section if you cut a release) in the same change as the code.
See `AGENTS.md` for the documentation policy.
