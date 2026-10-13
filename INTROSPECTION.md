# Design: single-sourcing builtin knowledge via interpreter introspection

**Status:** implemented (Phases 1–2) — see §11 for what landed and the
resolved open questions. Phase 3 (docstring backfill, `.x` stubs,
did-you-mean suggestions) remains future work.
**Scope:** `xlang/`, `xlang/typecheck/`, `vscode-xlang/`, playground wheel
**Motivation:** the VS Code extension, the typechecker, and the interpreter
each carried their own handwritten copy of "which builtin methods exist", and
the copies had already drifted apart.

---

## 1. The problem

Three separate hardcodings answer the same question today:

| copy | string methods | array methods | where |
|---|---|---|---|
| interpreter (the runtime truth) | **32** | 20 | `xlang/interpreter/_common.py` — `_STRING_METHODS`, `_ARRAY_METHODS` |
| typechecker | 19 | 21 | `xlang/typecheck/checker.py` — `STRING_METHOD_NAMES`, `ARRAY_METHOD_NAMES` |
| VS Code server | **11** | 11 | `vscode-xlang/server/server.py` — `_BUILTIN_MEMBERS` (114 entries, 15 type buckets) |

Reproduce the drift measurement:

```sh
.venv/bin/python -c "
import sys; sys.path.insert(0, 'vscode-xlang/server'); import server
from xlang.interpreter._common import _STRING_METHODS, _ARRAY_METHODS
from xlang.typecheck.checker import STRING_METHOD_NAMES, ARRAY_METHOD_NAMES
lsp = lambda k: {n for n, t, d in server._BUILTIN_MEMBERS[k]}
print('string  interpreter', len(_STRING_METHODS), 'checker', len(STRING_METHOD_NAMES), 'lsp', len(lsp('string')))
print('missing from lsp:', sorted(set(_STRING_METHODS) - lsp('string')))
print('array   interpreter', len(_ARRAY_METHODS), 'checker', len(ARRAY_METHOD_NAMES), 'lsp', len(lsp('array')))
"
```

### User-visible consequences

1. **The editor hides working methods.** `s.strip()`, `s.startsWith()`,
   `s.replaceAll()`, `s.lines()` … all exist and run, but none appear in the
   `s.` completion popup — 21 of 32 string methods are undiscoverable.
2. **Weaker inference in `x check`.** `_builtin_member()`
   (`checker.py:1851`) returns `FUNCTION` only for names in its local set and
   `ANY` otherwise, so `s.strip().trim()` gets loose typing one link down the
   chain. Unknown-but-valid methods don't error (the checker is permissive),
   they silently degrade.
3. **Every new builtin costs three edits.** Nothing enforces the three copies
   agree; drift is structural, not accidental.

---

## 2. Research findings (what already exists)

All of the following was verified against the current tree.

### The server already imports the real interpreter pipeline

`vscode-xlang/server/server.py:53-56`:

```python
from xlang.config import XConfig, discover_config, load_config
from xlang.lexer import Lexer
from xlang.parser import Parser
from xlang.typecheck.checker import TypeChecker
```

This is why editor squiggles match `x check` byte-for-byte. Completions are
the **only** feature that chose to hardcode instead of asking `xlang`. The
streamlined approach is therefore not a new protocol — it extends the pattern
the server already uses for diagnostics.

### The interpreter already carries completion-ready metadata

- `_STRING_METHODS` / `_ARRAY_METHODS` (`xlang/interpreter/_common.py:158,184`)
  are **module-level** dicts mapping method name → implementation name.
  No instance needed to enumerate them.
- Every implementation carries a parseable docstring in one convention:

  ```python
  def _string_trim(self, arguments: list[Any]) -> str:
      """``trim()`` — drop leading and trailing whitespace."""
  ```

  Coverage verified: **32/32 string** and **20/20 array** methods have a
  docstring starting with the double-backtick signature form. A completion can
  therefore offer `trim()` *plus* a real one-line description, parsed with
  `inspect.getdoc()` — zero new metadata.
- `BuiltinFunction` (`xlang/runtime.py:535`) stores the callable as
  `implementation`; `inspect.getdoc(fn.implementation)` reaches the same
  docstrings for namespace members.

### Builtin namespaces are assembled by 15 member builders

`Interpreter` exposes `_hashmap_members`, `_linkedlist_members`,
`_stack_members`, `_queue_members`, `_priorityqueue_members`, `_trie_members`,
`_set_members`, `_math_members` (41 members), `_json_members`,
`_filesystem_members`, `_console_members`, `_thread_members`,
`_object_members`, `_async_members`, `_interface_members`.

They are wired into the environment in `_install_builtins`
(`xlang/interpreter/__init__.py:432-500`):

| path | builder |
|---|---|
| `Object` | `_object_members` |
| `System.io.FileSystem` | `_filesystem_members` |
| `System.io.Console` | `_console_members` |
| `System.concurrent.Thread` | `_thread_members` |
| `System.concurrent.Async` | `_async_members` |
| `System.utils.Math` | `_math_members` |
| `System.utils.JSON` | `_json_members` |
| `System.utils.Collections.{HashMap,LinkedList,Stack,Queue,PriorityQueue,Trie,Set}` | one builder each |
| `HashMap`/`List`/`Stack`/… at global scope | same namespaces re-exported |
| extended collections | `xlang.stdlib.extended_collections.build_namespaces()` |

Two constraints discovered here:

1. **Builders need a real instance.** They reference `self._hashmap_create`
   while building the dict literal, so `Interpreter._hashmap_members(None)`
   raises. An introspection call must construct an `Interpreter` (with a
   sink `output`, see §4) or the builders must be refactored to module-level
   tables.
2. **Namespace members have no docstrings yet.** Measured coverage: 0% for
   collection/math/console builders (`_hashmap_create.__doc__ is None`).
   String/array methods are the exception. Introspection must degrade
   gracefully to name + kind until docstrings are backfilled.

### The checker's use of its local sets

`checker.py:1867-1872` — the sets decide the *return type* of a dot-call, not
whether it's legal:

```python
if object_type.is_array and name in ARRAY_METHOD_NAMES:
    return FUNCTION
if object_type.name == "string" and name in STRING_METHOD_NAMES:
    return FUNCTION
```

Anything unknown falls through to `ANY` (permissive). So the drift produces
weak inference, never false errors — removing the copy is a pure improvement
with no behavior regressions to worry about.

### The playground can use the same API for free

The docs-site playground runs the real interpreter in Pyodide from the wheel
built out of `xlang/`. Any pure-Python module added under `xlang/` ships
inside that wheel automatically — so one introspection module serves the CLI,
the LSP, and the browser.

---

## 3. Proposed design

### Public API: `xlang/introspect.py`

```python
@dataclass(frozen=True)
class MemberInfo:
    name: str                    # "trim"
    kind: str                    # "method" | "property" | "class" | "namespace"
    signature: str | None        # "trim()" parsed from the docstring
    doc: str | None              # "drop leading and trailing whitespace."
    owner: str                   # "string", "HashMap", "Math"

def members_of_type(type_name: str) -> list[MemberInfo]:
    """Builtin members for a value type: string, array, integer, float,
    boolean, object, null, ... Reads _STRING_METHODS/_ARRAY_METHODS plus
    the signature docstrings. Never raises; unknown type -> []."""

def namespace_members(dotted_path: str) -> list[MemberInfo]:
    """Members of a builtin namespace/class: "System.utils.Math",
    "HashMap", "System.io.FileSystem". Enumerates the member builders
    through a lightweight interpreter instance. Never raises."""

def known_type_names() -> set[str]:
    """Names the checker/lexer already recognize (re-export of
    typecheck.types.KNOWN_TYPE_NAMES + BUILTIN_TYPE_NAMES)."""
```

Design rules:

- **Never raises.** Every entry point wraps its body in `try/except` and
  returns `[]` on failure. The editor must degrade to today's flat list, not
  lose completions because a table changed shape.
- **Pure data out.** No interpreter objects, no `Environment`, no
  `BuiltinFunction` leak across the boundary — just `MemberInfo`.
- **Docstring parsing in one place** with a pinned regex, e.g.
  r"``(?P<sig>[^`]+)``\s*[—-]\s*(?P<doc>.+)", guarded by a test that
  32/32 string + 20/20 array methods still parse.

### Two implementation options for namespace members

| option | approach | cost | tradeoff |
|---|---|---|---|
| **A — instance query** | construct a throwaway `Interpreter(arguments=[], output=sink)` and call the builders | no interpreter changes | reads env vars / installs builtins on construction; heavier; construction side effects must be audited |
| **B — module-level tables** | refactor each `_xxx_members()` into a module-level `dict[str, Callable]` name map (same shape as `_STRING_METHODS`); instance code assembles `BuiltinFunction`s from it | touches `xlang/interpreter` | true single source; enumeration needs no instance; slightly bigger diff |

**Recommendation:** ship **A** behind `namespace_members()` first (zero
interpreter risk, immediately unblocks the LSP), then do **B** when a second
consumer (docs, hover) appears. The API hides which option is in use, so the
swap is invisible to callers.

### Where the members flow

```
interpreter tables + docstrings          (source of truth)
        │
        ▼
xlang/introspect.py  (public, tested, never raises)
        ├──► xlang/typecheck/checker.py   derives STRING_METHOD_NAMES etc.
        ├──► vscode-xlang/server/server.py  members_of_type() in _member_completions
        ├──► hover/detail strings           signature + doc for free
        └──► playground wheel (Pyodide)     same module, browser-side
```

---

## 4. Integration plan

### Phase 1 — add the API (no behavior change)

| file | change |
|---|---|
| `xlang/introspect.py` | new module: `MemberInfo`, `members_of_type`, `namespace_members`, `known_type_names` |
| `tests/test_introspect.py` | new: every builtin type returns non-empty; 32/32 + 20/20 docstring parse guard; unknown type → `[]`; never raises on a broken table (monkeypatch) |

Verification: `.venv/bin/python -m pytest tests/test_introspect.py -q`.

### Phase 2 — delete the two copies

| file | change |
|---|---|
| `xlang/typecheck/checker.py` | replace the `STRING_METHOD_NAMES` / `ARRAY_METHOD_NAMES` literals with derivation from `xlang.introspect` (one source) |
| `vscode-xlang/server/server.py` | delete `_BUILTIN_MEMBERS` (114 entries) + `_BUILTIN_ALIASES` + `_BUILTIN_KIND`; `_member_completions` falls back: user class members → `introspect.members_of_type()` / `namespace_members()` → `None` (flat list, unchanged behavior) |
| `tests/test_lsp_server.py` | keep `BuiltinMemberCompletionTests` as the regression net — all 7 tests must still pass with zero hardcoded catalog |

Verification (per `AGENTS.md`): full `pytest tests/ -q` (only the 5 known
pre-existing failures allowed) + `x playground` + `x playground-check`.

### Phase 3 — follow-ups (optional, separate changes)

1. **Signature docstrings for namespace members** — backfill
   `"""``create()`` — new empty HashMap."""` onto collection/math/console
   builders so LSP detail and hover show signatures there too.
2. **Declarative `.x` stubs (the typeshed endgame)** — if X's stdlib grows,
   move builtin signatures into checked-in `.x` stub files that the
   interpreter, checker, LSP and docs all parse. That's the model TypeScript
   (`lib.d.ts`) and Python (typeshed) settled on, and it's the only way to
   get parameter *names*, overloads and typed generics into hover —
   docstrings alone can't carry them.
3. **Strictness decision** — today unknown string methods are legal but
   untyped. Once introspection is single-sourced, the checker could offer
   `did you mean 'strip'?` suggestions from the same table (the
   `_closest_match` helper already exists at `checker.py:154`).

---

## 5. Benefits

- **One edit propagates everywhere.** Adding `s.trimEnd()` to
  `_STRING_METHODS` + its implementation immediately shows up in `x check`
  inference, the `s.` popup, and hover — no second or third edit.
- **The editor stops hiding the language.** Popup completeness goes from
  11/32 to 32/32 string methods (and 11/20 → 20/20 arrays) with the catalog
  deleted rather than updated — impossible to drift because it no longer
  exists.
- **Consistency across surfaces.** CLI, checker, LSP, playground all answer
  from the same module, so "what works" is identical everywhere.
- **Richer completions for free.** Signature + one-line docs already live in
  the docstrings; today's hardcoded entries have hand-typed detail strings
  (`("trim", "method", "trim()")`) which the introspection parses instead.
- **No new infrastructure.** The server already imports `xlang` (§2); this
  adds dict lookups on an import that happens anyway. No IPC, no subprocess,
  no version skew between editor and interpreter, no serialization.
- **Works in the browser too.** Pure Python → ships in the Pyodide wheel at
  zero extra cost.
- **Testable by construction.** A public module with its own test file can
  assert coverage (e.g. "every entry in `_STRING_METHODS` parses"), turning
  future drift into a red test instead of a silent gap.

---

## 6. How the industry solves this (and what applies here)

The implementation language decides the right answer. X's LSP is Python, and
so is its interpreter.

| approach | real-world examples | when it's justified | fit for X |
|---|---|---|---|
| **In-process introspection** — query the runtime in the same process | **jedi** (completions by introspecting the live CPython runtime), CPython's own `pydoc`/`inspect` | language implementation and tooling share a runtime | **best fit** — server already imports `xlang` |
| **Single declarative source, derived views** — one manifest everyone parses | **tsserver** ships `lib.d.ts`; **Pyright/Pylance** ship typeshed stubs | large stdlib, need parameter names/overloads, tooling *can't* import the runtime | endgame for X's stdlib (Phase 3) |
| **Subprocess RPC** — spawn the toolchain, ask over JSON-RPC/stdio | **gopls** (`go list -json`), **rust-analyzer** (cargo metadata), **clangd** (`compile_commands.json`), **jdtls** (embedded JRE) | editor/runtime version skew, crash isolation, sandboxing, heavy computation | not needed — same venv, pure Python, microsecond lookups |
| **Prebuilt index + cache** | **jdtls** JRE index built once per install; rust-analyzer's Salsa incremental cache | introspection is slow | not needed — it's dict lookups |

The crucial contrast:

- **pyright and ruff hardcode Python's stdlib knowledge on purpose — because
  they're written in TypeScript and Rust and physically cannot import the
  runtime they're analyzing.** Their duplication is forced, not sloppy.
- **jedi is written in Python, so it introspects in-process** — and that's
  exactly X's position. Copying pyright's shape while having jedi's ability
  would be choosing the constraint without having it.

When would X revisit the subprocess model? If the extension ever needs to run
against a *different* interpreter than the one the editor was launched with
(multiple X versions per machine), or if native extensions make the
interpreter crash-prone enough to isolate. The playground worker's existing
`run_files` JSON message shape is the natural protocol to reuse if that day
comes — but nothing here needs it.

---

## 7. Risks and mitigations

| risk | mitigation |
|---|---|
| Coupling to private interpreter internals (`_STRING_METHODS`) | move access behind the public `xlang.introspect` module; the private name is then an implementation detail of *one* file, with tests |
| An introspection bug kills completions | `never raises` + `[]` fallback → `_member_completions` returns `None` → flat keyword list (exactly today's degrade path); editor always has something |
| Interpreter construction side effects (env reads, builtin install) in option A | construct with `arguments=[]`, a sink `output` callable, explicit `environment={}`; audit `__init__` before shipping; or short-cut to option B |
| Docstring format drift (0% coverage on collections) | guard test asserts parse rates; entries without docs degrade to name-only rather than crashing |
| Import time | none — the server already imports `xlang` for diagnostics on startup |
| Docstring regex brittleness | single regex, pinned by tests on all 52 currently-documented methods |

---

## 8. Explicitly out of scope

- **No publishing** of the extension to the VS Code Marketplace (project
  requirement — local `.vsix` install only).
- **No subprocess per keystroke.**
- **No second copy** of the stdlib as JSON inside the extension — that
  reintroduces the exact drift this design removes.
- **No probing of user code** for completions (importing user modules in the
  editor would execute arbitrary top-level side effects).

---

## 9. Verification plan (when implemented)

```sh
.venv/bin/python -m pytest tests/ -q            # only the 5 known pre-existing failures
x playground                                     # rebuild the wheel (xlang/ changed)
x playground-check                               # must report ok
node --check docs-site/playground/playground.js  # if the LSP-facing JS changed
```

LSP-specific: `tests/test_lsp_server.py` (33 tests today — the
`BuiltinMemberCompletionTests` 7 become the catalog-deletion regression net)
and `tests/test_introspect.py` (new).

---

## 10. Open questions

Resolved in §11 (implementation notes): module location, option A first,
extended collections included, did-you-mean left for Phase 3.

---

## 11. Implementation notes (what landed)

Phases 1–2 are implemented. Summary of decisions and deltas from the plan
above:

- **Module:** `xlang/introspect.py` (top-level, per Q1). Public surface:
  `MemberInfo`, `members_of_type`, `namespace_members`, `known_type_names`.
  Guarded by `tests/test_introspect.py` (17 tests).
- **Option A shipped** (Q2): `namespace_members` constructs one cached
  throwaway `Interpreter(arguments=[], output=sink, auto_call_main=False)`
  and walks `globals` — `_install_builtins` only assembles in-memory
  `Environment`s, so this is side-effect free. The API hides the choice, so
  swapping to option B later is invisible to callers.
- **Extended collections are included** (Q3): they are registered in
  `globals` at startup, so the environment walk surfaces `TreeMap`,
  `TreeSet`, `LinkedHashMap`, `LRUCache`, `ThreadSafeMap`, `ThreadSafeSet`
  with no extra code.
- **Did-you-mean suggestions** (Q4) remain Phase 3 — the checker change is
  still inference-only.
- **Special members discovered during implementation:** `_get_member`
  answers `length` (string, array) and `toString` (string, numbers)
  inline, with no runtime table. `introspect._VALUE_TYPE_SPECIAL_MEMBERS`
  mirrors them, and `test_special_members_are_real` round-trips every entry
  through a live `Interpreter._get_member` — drift goes red, not silent.
- **Wrapper docstrings:** `_make_collection_ns` now copies the original
  builtin's docstring onto the instance-method wrapper so future Phase 3
  backfills parse through the wrapper.
- **The checker's sets are derived** at import time:
  `STRING_METHOD_NAMES` / `ARRAY_METHOD_NAMES` are frozensets over
  `members_of_type(...)`. Net effect: +14 string methods typed as
  `FUNCTION` (strip/startsWith/…), and the phantom `array.add` (checker
  drift the other way) is gone. No legality change — the checker was
  already permissive.
- **The LSP catalog is deleted:** `_BUILTIN_MEMBERS`, `_BUILTIN_ALIASES`
  and `_BUILTIN_KIND` (≈310 lines) are gone; `_builtin_members` asks
  `introspect` and maps `MemberInfo.kind` to `CompletionItemKind`.
  Completeness: string 11→34, array 11→21; collections and
  `System.utils.Math`/`FileSystem`/etc. now answer from the live
  environment. The old `*` wildcard bucket is gone — a receiver with no
  known members (e.g. `integer` beyond `toString`) falls back to the flat
  keyword list, which is the documented degrade path.
- **One catalog fiction removed:** the old catalog offered
  `obj.keys()/values()/isEmpty()` on plain object literals; those raise
  "Object has no field" at runtime and are no longer suggested
  (`test_object_variable_offers_no_builtin_fiction` pins this).
- **The playground's `completions.js` stays a static snapshot** — the
  browser computes completions on the main thread with no Python to ask.
  It is the only remaining copy and cannot drift the LSP/checker; wiring
  the worker to `introspect` is a possible future enhancement.
