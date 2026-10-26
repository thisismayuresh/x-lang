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

- **Diagnostics echo the source's type spelling** — error messages repeat the
  annotation exactly as it was written instead of the internal canonical
  name: `let number[] xs = ["a"];` reports `type 'number[]'` (not
  `float[]`), `let int n = "text";` reports `type 'int'` (not `integer`),
  and an aliased annotation reports the alias (`Score`, `Function`). The
  "found" side still shows the inferred type. Compatibility and equality
  are unchanged — only the wording. The `number` alias itself, its array
  forms (`number[]` through `number[][][]`), and variables named after
  their own type (`let number number = 5;`) are now pinned by
  `tests/test_number_type.py` and documented in a new "The number type
  and array annotations" section.
- **`??` nullish coalescing** — `a ?? b` evaluates to `a` unless it is
  `null`/`undefined` (then `b`), with JavaScript's mixing restriction:
  `??` combined with `&&`/`||` without parentheses is a parse error. The
  operator chains with `?.` (`user?.profile?.name ?? "anonymous"`), works
  in both statement and expression positions, and the checker strips the
  nullish step when inferring (`a ?? b` where `a` is `string?` infers
  `string` for the non-null branch). Interaction with `?:` matches
  JavaScript: `a ?? b ? c : d` groups as `(a ?? b) ? c : d`, ternary
  branches are independent operand chains, and the no-mixing rule
  applies inside the condition — pinned by
  `NullishTernaryInteractionTests` (expected values cross-checked
  against Node). Closes the `??` does-not-parse
  limitation.
- **Nullable and union types** — `T?` (shorthand for `T | null | undefined`)
  and `A | B` unions now work in prefix (`let integer | null a`) and colon
  annotations, parameters, and return types. `null`/`undefined` are
  assignable where the type allows them; assigning `null` to `integer`
  reports `Cannot assign 'null' to 'x' of type 'integer'`. Argument errors
  show the whole union (`expected '(string|integer)'` /
  `expected 'string?'`), and runtime matching scores union members in
  declaration order. Closes the union/nullable limitation.
- **TypeScript-style `Promise<T>` async/await** — an `async` function's call
  type is always `Promise<T>` (declared `Promise<T>` kept as-is, plain `T`
  wrapped, `void`/`any` untouched), `async` may follow the return type
  (`Promise<{obj: {...}}> async function f()`), and async bodies are checked
  against the unwrapped `T`. Returning a promise from an async body is
  implicitly awaited (one level of flattening, as in JavaScript); `await` on
  a plain value yields the value; `typeOf(promiseCall)` is `"Promise"`.
  There is no `Promise` constructor and no `.then`/`.catch` — `new
  Promise(...)`, `.then(...)`, and `.catch(...)` are rejected (keywords are
  legal member names after `.`, so `p.catch(...)` parses and then fails at
  the call). Discarding an async call's result as a statement raises a
  runtime error suggesting `await`, and Python's "coroutine never awaited"
  warning is suppressed. `Promise<void>` functions need no return.
- **Generic type-parameter substitution is enforced** — `_signature_type`
  resolves through class + base mappings, member/field access substitutes
  receiver arguments (`Box<integer>.item` is `integer`), `new` infers type
  arguments from constructor arguments, call sites infer them from argument
  types, and overloads see the substituted signatures (method argument and
  arity errors included). `List<string>` in a `List<integer>` slot, and now
  `List<integer>.add("x")`, are type errors; Python-backed collection
  methods get a dedicated rule table (`add`/`push`/`enqueue`/`has`/`get`…
  against the element type, map `set`/`get`/`getOrDefault`/`computeIf*`
  against `K`/`V`), while dynamic collections without type arguments stay
  permissive.
- **`for ... of` over collections with element-type inference** — arrays,
  strings, `range`, and the collection classes (LinkedList/List, Stack,
  Queue, PriorityQueue, Set, HashMap keys) iterate directly without
  `.toArray()`; the checker infers the loop variable's element type from
  what is iterated (`for (Student s of students)` types `s` as `Student`)
  and validates annotated loop variables. Closes the iterator-protocol
  limitation.
- **`System.concurrent.Lock`** — a re-entrant mutex for coordinating OS
  threads: `lock()`, `tryLock()`/`tryLock(ms)` (non-blocking or bounded
  wait), `unlock()` (friendly not-owner error), `isLocked()`. Constructed
  as `System.concurrent.Lock()` (short `Lock` after import), typed as
  `Lock` in annotations, `typeOf` reports `"Lock"`, printing yields `[Lock]`,
  and the `threads` feature flag gates the module. Closes part of the
  "no locks" limitation.
- **Security hardening + `tests/test_security.py` (27 tests)** — printing
  functions, builtins, thread handles, locks, and promises no longer leaks
  Python `repr`s with memory addresses (`[function greet]`, `[Lock]`,
  `[ThreadHandle]`, `[Promise]`; unknown objects render as their class
  name); `sleep`/`tryLock`/`delay` durations must be finite (`inf`/`NaN`
  rejected instead of hanging `asyncio.sleep` or overflowing `time_t`);
  raw null bytes in string and template literals are lex errors (the `\0`
  escape already was). The suite also pins: no `eval`/`exec`/`Function`/
  `open`/`globals`/`getattr`/`__import__`, dunder and tuple-literal
  rejection, the `.x` import sandbox, clean X errors for recursion/depth/
  repeat/`Math.pow` overflow (no Python tracebacks), and the JS-compatible
  loose/strict equality semantics security checks must account for.

- **Per-file module scopes — imports no longer share one global namespace**
  (closes the `Independent module namespaces` roadmap item and the
  `import B.greet` scope-leak limitation). The loader now records what each
  file's imports bind (`Program.import_bindings`) and the order in which
  files completed (`Program.modules`), and the interpreter executes each
  source file in its own top-level `Environment` chained to the builtins,
  dependencies first. Sibling declarations stay private at runtime (calling
  an unimported helper raises `Name 'greet' is not defined` instead of
  resolving through a shared scope), an imported function still resolves its
  own file's helpers through its closure, type aliases are never bound at
  runtime (matching the flat path), and two files may declare the same
  top-level name without `'Serializable' is already declared in this scope` —
  **`x run examples/main.x` runs again** instead of failing at load. The flat
  `program.declarations` list is still built for the type checker, TypeScript
  codegen, and hand-built programs such as the REPL, which keep a single
  shared scope.
- **`typeOf` reports `"function"` for class and interface values again**,
  matching the documented JavaScript-style mapping (a regression from the
  interface work had it return `"class"` / `"interface"` and broke three
  tests while README and the builtin's own docstring said `"function"`).
- **`parseFloat(text)` and `parseInt(text, radix?)` builtins** — strict
  whole-string number parsing with no import. `parseFloat` returns a
  `float` (optional sign, decimal point, `e`-exponent, surrounding
  whitespace); `parseInt` returns an `integer` in a radix of 2–36
  (default 10). Empty input, trailing garbage (`"12px"`), and digits
  outside the radix raise `IllegalArgumentException` instead of returning
  `NaN` or a prefix value. The checker types the results `float` and
  `integer`; both names are also registered in the VS Code completions
  (they were already listed there) and the playground catalog.
- **`System.utils.JSON.parse(text)`** — strict RFC 8259 parsing back into
  X objects/arrays/scalars, the inverse of `toJSON`. Malformed JSON raises
  `IllegalArgumentException`, and non-standard `NaN`/`Infinity` literals are
  rejected. Documents nested deeper than `MAX_JSON_PARSE_DEPTH` (500
  levels) are rejected up front — `JSON.parse failed: input nests too
  deeply` — instead of relying on the host json scanner, whose guard
  depends on the C stack and became stack-sensitive on CPython 3.14;
  `response.json()` and the collections' `fromJSON`/`from_json` share the
  cap. The loader allowlists `System.utils.JSON.parse` for member
  imports (`import System.utils.JSON.parse` binds `parse`), and the
  playground catalog gains the `JSON.parse` completion.
- **`examples/main.x` passes `--feature strict_typing=on`**: the showcase's
  23 untyped `let` declarations in `examples/main_tests.x` now carry
  explicit annotations, and `deserialize` converts its string with the new
  `parseFloat` instead of the string-concatenating `0 + parts[2]`.
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
- **Namespace-member imports**: `export namespace` is now a declaration
  (previously a parse error), `export { ... };` may name declarations inside
  a top-level namespace, and `import util.MyNamespace.fun` walks namespaces
  inside the shortest existing prefix file to bind the member flat —
  keeping its namespace closure, so sibling references still resolve. The
  exported namespace is the export boundary (like a class and its methods):
  only the module-level namespace needs `export`, and its members and
  nested namespaces are reachable through the chain without their own
  `export`. Aliases (`import util.MyNamespace.greet as sayHi`), enums,
  import calls (`import util.MyNamespace.greet("Ada")`), and
  `import util.MyNamespace.*` (wildcard over every member, bare names and
  `MyNamespace.greet` both working, optionally aliased) work the same way;
  a missing member reports `'greet' is not a member of namespace
  'util.MyNamespace'`, and an unexported module-level hop or non-namespace
  chain part reports the usual style of error. See
  `examples/namespace_demo`. Also fixes a latent crash when a flatten
  collision was reported for a module outside the project root, and stops
  repeated imports of the same namespace member from emitting duplicate
  `const` bindings in TypeScript codegen.
- **`extends` / `implements` through namespace imports**: a class imported
  via a namespace chain (flat or dotted: `extends Shapes.Square`,
  `implements Shapes.Shape`) resolves its parent/interface — the
  interpreter defers classes whose parent is an import alias until the
  aliases bind, and the checker resolves dotted interface names the same
  way it already resolves dotted `extends`. The playground's
  `collectDeclarations` now also registers `as alias` import names for
  completions.
- **Map interfaces**: an interface whose only member is a
  `keyType key { fields }` entry names a dictionary type —
  `interface Participants { integer key { string name, ... } }` binds
  `let Participants byId = { 100: { name: "Maya", ... } }` with the same
  per-key diagnostics as `object<K, V>`, the same runtime structural check,
  `m[100]` / `m.100` access, and a TypeScript index-signature emit
  (`[key: number]: { name: string; ... };`). `key` stays a normal
  identifier elsewhere (a field or method named `key` still parses); a map
  interface cannot mix with other members, be implemented by a class, or
  be constructed with `new`.
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

- **New completion and hover entries for Milestone 1 features** — the
  language server (`vscode-xlang/server/server.py`) and the playground
  catalog (`docs-site/playground/completions.js`) both offer `Promise<T>`,
  `Lock`, and `ThreadHandle` in type positions, the `Lock` members
  (`lock`/`tryLock`/`unlock`/`isLocked`) and `ThreadHandle` members
  (`join`/`isAlive`) after a `.`, the `System.concurrent` namespace
  children (`Lock`, `Thread`, `Async`) with `Async.delay`/`Async.all` and
  `Thread.start`, and the `sleep` builtin. The server's type list also
  gains the previously missing `integer` and `var` spellings, with hovers
  for `integer`, `var`, `Promise`, `Lock`, and `ThreadHandle`.

- **Quick fixes for missing imports**: the checker's
  ``add `import utils.greet` `` suggestion now surfaces as an
  ``Add `import utils.greet` `` code action in the VS Code extension,
  inserting the statement after the file's last import.
- **Auto-import completions**: typing the name of an export from a local
  `.x` file offers it with the matching `import` edit applied on accept.
  Already-declared names and already-imported modules are skipped.
- **Member suggestions resolve across imports**: `Gender.` offers the
  enum's members even when the enum lives in an imported file (same for
  interfaces behind `object<K, V>` aliases, with dotted paths like `t.200.`
  walked segment by segment), and object-literal receivers offer the
  literal's own keys before the builtin `keys`/`values` methods.
- **Playground completions after `.` for user types**: the browser
  playground now offers user-declared enum members (`Gender.`),
  class/interface fields (`IParticipantValue.`), and object-literal keys
  (`let object<string, any> obj = { "name": ... }` → `obj.` offers `name`),
  scanning **every open playground file** so types imported from another
  tab complete too. Type-before-name annotations (`let IParticipantValue p
  = ...`) and enum-valued bindings (`let g = Gender.FEMALE`) infer the
  receiver's type; `let g = Gender.FEMALE` also works.
- **Playground import-path completions**: `import ` (Ctrl+Space) offers the
  other open playground files; `import util.` offers that file's exported
  declarations plus a `*` wildcard; `import util.Ns.` offers the names
  inside its exported namespace. Non-exported declarations stay hidden.
- **Playground `Ns.` completions**: a namespace's declared members
  (functions, classes, interfaces, enums, types, variables, nested
  namespaces) now complete after `Ns.` — for same-file namespaces,
  dotted `import util.Ns` bindings, and `as` aliases alike, with nested
  `A.B.` chains walked. Class-member scanning also accepts method
  signatures that end in `{` (the usual multi-line style).
- **Playground suggestions scan every open file** in plain and
  type-position contexts too (`let x: `, parameter annotations,
  `extends`/`implements`): types, functions, imports, and variables
  declared in another tab complete in whichever file you type. The plain
  pool now includes user types, so `let Participant` offers
  `Participant`.

### Tooling / CI

- **New `x lint` command** — runs the `undeclared-variables` rule over the
  loaded program: a name that resolves to no local, parameter, declaration,
  import, builtin, or enabled feature global is reported with the runtime's
  `Name 'x' is not defined` wording (including the
  `... because the 'feature' feature is disabled in x.toml` clause for
  feature globals), shown with line and column, labelled `lint error`, and
  exits 1; a clean file prints `no lint issues` and exits 0. The rule reuses
  the type checker's scope machinery — no second AST walk — and `x check` is
  unchanged because it passes no rules. Getting runtime parity meant fixing
  what the checker binds: catch clauses were unpacked in the wrong order
  (type vs. name), destructuring and match pattern names and nested enums
  were never defined, `[imports].default` aliases and `input`
  (`command_input`) were unknown, and the loader's per-file visibility now
  counts a file's own namespace members as declared there. Configured per
  project in the `[lint]` table (`undeclared-variables`, default `true`;
  unknown rule names and non-boolean values are configuration errors).
  Pinned by `tests/test_lint.py`, and every published example lints clean.
- **Regression corpus moved into `tests/` as generated Python** — the
  `csv_tests/` directory and its four CSV files are gone.
  `tests/generate_corpus.py` now writes a single generated
  `tests/corpus_data.py` (1403 rows: run, check, error, format) that
  `tests/test_corpus.py` executes as subtests, so the whole suite —
  interpreter tests included — runs with one `python -m pytest tests/ -q`,
  locally and in CI. Regeneration stays deterministic and verification-gated;
  it also picked up the drift the CSVs had accumulated: the stale
  "nullish coalescing is unsupported" error row is gone now that `??` parses,
  mutation row `E0112` records the record-field parser message, the
  `new Collections.HashMap()` instance style is encoded in the generator
  instead of hand-patched into the CSV, and the check/format rows for the
  newer examples (aadhar, banking platform, try-with-resources, ...) joined
  the corpus.
- **GitHub Actions test workflow** (`.github/workflows/tests.yml`): runs the
  full suite (interpreter tests + regression corpus) on Python 3.10 and 3.14,
  checks the playground wheel is not stale against `xlang/`, and
  `node --check`s the authored docs-site JavaScript on every push and pull
  request. The old `--deselect` list is gone: Milestone 1 fixed the typeOf
  and strict-showcase failures it used to mask, so every test now gates CI.
- `pyproject.toml` gained a `dev` extra (`pip install -e ".[dev]"`: pytest
  plus `pygls`/`lsprotocol` for the LSP tests) so CI and local runs install
  the same test dependencies.
- The suite's config-discovery test now passes `--config` explicitly (the
  repository's own `x.toml` used to shadow the fixture's), and corpus row
  `R0441` uses the documented `new Collections.HashMap()` instance style —
  now recorded in the generator itself, so regeneration cannot silently
  revert it again.

### Documentation

- **New example: `examples/aadhar/`** — the JS resume-aware Aadhaar CSV
  generator, transpiled to statically-typed X. `aadhar_generator.x`
  validates Verhoeff checksums with module-private tables; `main.x` resumes
  from the last `id,value` row and writes each record through a `CsvWriter`
  opened in `try (...)` parens — `close()` runs on every exit path, before
  the optional `catch` reports a failed append as `[STOP]`. Both files pass
  `x check --feature strict_typing=on`; linked from the try-with-resources
  section and the examples tree in both READMEs.

- **Milestone 1 language docs** across `README.md` and `docs-site/README.md`:
  new `### Nullish coalescing: ??` and `### Nullable and union types`
  sections, a rewritten `### Async/await` section documenting
  `Promise<T>`/await/implicit flattening and the deliberate absence of
  `new Promise`/`.then`/`.catch`, a `### Locks` section with the full
  `System.concurrent.Lock` API table, a `for ... of` collections example in
  the loops chapter, a `## Security` section describing the hardened
  interpreter model (with the warning that X has the OS user's
  permissions), collection-method argument checking in the generics
  bullet and DSA chapter, and refreshed "Language features implemented"
  bullets. The stale limitation bullets (`??` does not parse, unions do
  not exist, generics not enforced, iterator protocol TODO, no locks) and
  the collections "Iterator protocol" / "Static type enforcement" TODOs
  are now marked done; the remaining limitations list names automatic type
  narrowing, nominal inline records, and atomics/cancellation instead.

- Both READMEs describe the new per-file module scopes: the interpreter
  architecture section explains `Program.modules` / `Program.import_bindings`
  and one environment per file, the import section notes runtime privacy, and
  the root README's `import B.greet` entry plus the docs README's `Known
  issue` write-up are re-marked as fixed (the roadmap's `Independent module
  namespaces` item is gone).
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
