# X Language VS Code Extension

VS Code extension for the X programming language providing:
- Syntax highlighting
- Real-time type checking (diagnostics)
- Code completion (IntelliSense)
- Hover type information
- Go to Definition

## Installation

### From Source (Development)

1. Install Python dependencies:
   ```bash
   cd vscode-xlang/server
   pip install -e .
   ```

2. Install Node.js dependencies and compile TypeScript:
   ```bash
   cd vscode-xlang
   npm install
   npm run compile
   ```

3. Open the `vscode-xlang` folder in VS Code and press F5 to launch the Extension Development Host.

### Packaged Extension

```bash
cd vscode-xlang
npx vsce package
```

Then install the generated `.vsix` file in VS Code.

## Features

### Syntax Highlighting
Full TextMate grammar for `.x` files covering:
- Keywords (control flow, declarations, modifiers)
- Types (primitives, generics)
- Strings (double, single, template)
- Numbers (integers, floats, hex)
- Operators
- Comments
- Decorators
- String interpolation

### Type Checking (Real-time Diagnostics)
- Parses and type-checks on every change
- Shows errors as red squiggles
- Uses the existing X language type checker
- Supports strict typing mode

### Code Completion (Ctrl+Space)
- Keywords
- Built-in types
- Built-in functions (`print`, `range`, `typeOf`, `sleep`, `input`, etc.)
- Classes and interfaces from current document
- Context-aware (basic implementation)

### Hover (Type Information)
Hover over symbols to see:
- Function signatures
- Type descriptions

### Go to Definition (Ctrl+Click / F12)
Jump to the declaration of what is under the cursor: classes, interfaces,
enums, type aliases, functions, methods, constructors, interface signatures,
fields, `let`/`const`/`var` bindings, parameters and enum members — inside the
current file. Works from inside the declaration itself and from inside the
body of the enclosing function. See §11 for how it works and its limits.

## Configuration

Settings (in VS Code settings.json):

```json
{
  "xlang.enableTypeChecking": true,
  "xlang.strictTyping": false,
  "xlang.serverPath": ""
}
```

## Architecture

```
vscode-xlang/
├── package.json           # Extension manifest
├── tsconfig.json          # TypeScript config
├── language-configuration.json  # Brackets, comments, folding
├── syntaxes/
│   └── x.tmLanguage.json  # TextMate grammar
├── src/
│   └── extension.ts       # VS Code extension entry point
├── server/
│   ├── server.py          # LSP server (Python)
│   ├── pyproject.toml     # Server dependencies
│   └── README.md
└── sample.x               # Test file
```

## Development

### Running the LSP Server Standalone

```bash
cd vscode-xlang/server
python server.py
```

The server communicates via stdio (LSP standard).

### Testing the Server

```bash
cd vscode-xlang/server
python -c "
from server import XLanguageServer
server = XLanguageServer()
# ... test features
"
```

## Requirements

- Python 3.10+ (for LSP server)
- Node.js 18+ (for VS Code extension)
- X language package installed (`pip install -e ../..`)

## License

MIT
---

# How X syntax highlighting and the language server work

*Detailed build report — 2026-10-08.*

## 1. Two completely separate mechanisms

Nothing in VS Code "knows" X by itself. Two independent pieces are contributed
by this extension, and they fail independently:

| Feature | Provided by | Mechanism | Failure mode |
|---|---|---|---|
| Syntax highlighting | `syntaxes/x.tmLanguage.json` | TextMate grammar, **purely declarative** | Plain white text, no colors |
| Type suggestions, hover, diagnostics, Ctrl+Click | `server/server.py` | Language Server Protocol over stdio | No completions, no squiggles |

The grammar never talks to Python. The language server never talks to colors.
A VS Code *theme* decides which color each TextMate **scope** gets — our
grammar only labels tokens (`keyword.control.x`, `string.quoted.double.x`, …).

## 2. Syntax highlighting — how it works

`package.json` declares the wiring:

```jsonc
"contributes": {
  "languages": [
    { "id": "x", "extensions": [".x"], "configuration": "./language-configuration.json" }
  ],
  "grammars": [
    { "language": "x", "scopeName": "source.x", "path": "./syntaxes/x.tmLanguage.json" }
  ]
}
```

Rules for it to work (all of these were verified):

1. `languages[].id` must equal `grammars[].language` → both `"x"`.
2. `grammars[].scopeName` must equal the `scopeName` inside the grammar file →
   both `"source.x"`.
3. The grammar file must be **valid JSON** with **no UTF-8 BOM** (a BOM is
   silently ignored and you get no highlighting at all).
4. The extension must actually be **installed** — a grammar sitting in a
   project folder does nothing.

`language-configuration.json` supplies the non-color basics: `//` and `/* */`
comment toggling, bracket matching/auto-close, folding.

## 3. Language server — how it works

```
.vscode/editor  ── JSON-RPC over stdio ──►  server/server.py (pygls 2.1.1)
     ▲                                            │
     │                                            ├─ xlang.lexer.Lexer
     │                                            ├─ xlang.parser.Parser (recover_errors=True)
     └──── completions / hover / diagnostics ─────┴─ xlang.typecheck.checker.TypeChecker
```

* **Client side** — `src/extension.ts` compiles to `out/extension.js`. It
  activates on `onLanguage:x` (i.e. the moment you open any `.x` file), picks a
  Python interpreter, spawns `server.py`, and creates a `LanguageClient`.
* **Server side** — `server.py` subclasses `pygls.lsp.server.LanguageServer`
  and registers handlers for `didOpen` / `didChange` / `didSave`,
  `completion`, `hover`, `definition`, `initialize` and the configuration
  notifications.
* **Diagnostics** — on every keystroke the server re-lexes, re-parses
  (`recover_errors=True`, so one bad line does not hide the rest of the file)
  and re-type-checks, then pushes `textDocument/publishDiagnostics`. Type
  checking is **skipped when the parse produced errors**, exactly like the
  `x check` CLI does.
* **Project config** — for each document the server walks up from the file's
  directory looking for `x.toml` (`discover_config`) and feeds it to the
  parser's feature flags and to the `TypeChecker`. So `strict_typing = true`
  in `x.toml` produces the same red squiggles in the editor as on the command
  line. The result is cached per directory and cleared when `x.toml` changes.

### Python interpreter selection (order tried)

1. `xlang.pythonPath` setting, if non-empty
2. `<workspace>/.venv/bin/python` … `venv/bin/python` (and the Windows equivalents)
3. `python3`, then `python`

Each candidate is probed with `python -c "import pygls"` (5 s timeout) before
being accepted. On this machine `.venv/bin/python` wins — it is the only Python
that has `pygls` installed. `PYTHONPATH` is also set to the workspace root so
`import xlang` resolves regardless of the current working directory.

## 4. What was actually wrong, and what we changed

Nothing here was a theme problem. Four independent defects:

| # | Defect | File | Fix |
|---|---|---|---|
| 1 | The extension had **never been installed** — `code --list-extensions` contained no `xlang` | *(missing)* | Packaged a `.vsix` with `@vscode/vsce` and installed it |
| 2 | `XLanguageServer(JsonRPCServer)` did not set `_text_document_sync_kind` / `_notebook_document_sync`, so `initialize` raised `AttributeError` and VS Code killed the connection | `server/server.py` | Subclass `pygls.lsp.server.LanguageServer`, which sets them |
| 3 | The server called `self.publish_diagnostics(...)`, a method that does not exist in pygls 2.x | `server/server.py` | Use `text_document_publish_diagnostics(PublishDiagnosticsParams(...))` |
| 4 | It spawned a bare `python`, which does not exist outside an activated venv and has no `pygls` | `src/extension.ts` | Interpreter resolution described in §3, plus a clear warning if `pygls` is missing |
| 5 | `Parser(...)` without `recover_errors=True` raised on the first syntax error, so diagnostics came back empty | `server/server.py` | `recover_errors=True`; collect `lexer.errors` and `parser.errors` |
| 6 | `didChange` did `'range' in change` on an lsprotocol **dataclass** → `TypeError`; documents went stale | `server/server.py` | Advertise `TextDocumentSyncKind.Full` and take `content_changes[-1].text` |
| 7 | Grammar had a stray `"match"` alongside `"begin"` in the interpolation rule and a meaningless top-level `injectionSelector`; builtins were shadowed by the generic "any identifier followed by `(`" rule | `syntaxes/x.tmLanguage.json` | Removed both, reordered so `support.function.builtin.x` wins |
| 8 | `initializationOptions` / settings were never sent or read | both files | `xlang.enableTypeChecking` and `xlang.strictTyping` are now pushed on `initialize` and on every settings change |

Also added: `xlang.pythonPath` setting, an **X Language** output channel that
logs the interpreter/server path and startup failures (previously errors went
nowhere), a `**/*.{x,toml}` file watcher so `x.toml` edits invalidate the config
cache, a `.vscodeignore` so the package stays clean, and `tsc` now compiles
with zero errors.

## 5. What was installed, and where

| Thing | Where | Why | Needed again? |
|---|---|---|---|
| `pygls 2.1.1`, `lsprotocol 2025.0.0`, `cattrs` | `.venv/lib/python3.12/site-packages/` | LSP protocol library for `server.py` | Already present |
| `x-language 0.1.0` (editable) | `.venv`, points at this repo | So the server can `import xlang` | Already present |
| `@vscode/vsce` 4.0.0 | npx cache (`~/.npm/_npx/`) | Packaging tool | Only when repackaging |
| `vscode-textmate` + `vscode-oniguruma` | `/tmp/opencode/grammartest/` | **Verification only** — tokenized the grammar offline to prove it works | No, throwaway |
| `vscode-languageclient 10.1.2` | `vscode-xlang/node_modules/` (bundled into the `.vsix`) | Client half of LSP | Already present |
| **`xlang.xlang` 0.1.0** | **`~/.vscode/extensions/xlang.xlang-0.1.0/`** | The installed extension | Already present |
| `xlang-0.1.0.vsix` | `/tmp/opencode/` | Install artifact | Regenerate with `npx @vscode/vsce package` |

Nothing was installed system-wide, no `sudo`, no global `npm install -g`, no
file outside `~/.vscode/extensions/` and `/tmp/`.

## 6. Verification performed

1. **Grammar** — loaded `x.tmLanguage.json` with the real `vscode-textmate`
   engine + Oniguruma WASM and tokenized `sample.x` and a purpose-built file.
   All 10 required scopes present (`comment.line.double-slash.x`,
   `keyword.control.x`, `keyword.declaration.x`, `storage.type.primitive.x`,
   `string.quoted.double.x`, `string.template.x`, `constant.numeric.integer.x`,
   `entity.name.function.x`, `entity.name.type.class.x`, `comment.block.x`);
   escape sequences and `${...}` interpolation both tokenized.
2. **Server handshake** — scripted LSP client: `initialize` returns full
   capabilities (`completionProvider`, `hoverProvider`, `definitionProvider`,
   `referencesProvider`, `textDocumentSync.change = 1`).
3. **Diagnostics parity** — the LSP's diagnostics were diffed against
   `x check` on the example files: identical wherever the two report the same
   scope, including the 9 strict-typing errors in
   `examples/strict_typing_errors.x`. `examples/main.x` is clean.
   (`examples/test_import_strict.x` differs only because the CLI merges the
   errors of the file it imports into one list while the LSP keeps them on
   their own document — pre-existing, and unaffected by any change here.)
4. **Installed copy** — probed the *installed* `server.py` directly:
   9 diagnostics, 59 completion items, hover OK.
5. **`tsc -p ./`** compiles clean. (`npm run lint` fails only because the repo
   has never had an ESLint config — pre-existing.)
6. **Go to definition** — 29/29 on a purpose-built fixture covering functions,
   methods, constructors, parameters (inside and outside the signature),
   fields, `let` bindings, type names, enum members, interface signatures,
   self-jumps, builtins and keywords. A sweep over `examples/*.x` resolved
   260/743 words in `main.x` with **0** exceptions and **0** targets inside a
   comment.
7. **`void`-return check** — reported by the CLI and by the LSP at the same
   line/column; bare `return` in a `void` function and `any` functions that
   do return a value are still accepted.
8. **Test suite** — 489 passed. The 3 remaining failures are pre-existing
   (`typeOf` returning `'class'`/`'interface'` where the test wants
   `'function'`) and fail identically with these changes stashed.

## 7. Is it permanent? Do I have to redo anything after restarting?

**No. Nothing has to be redone after a reboot.** It is installed the same way
as any marketplace extension.

* The extension lives in `~/.vscode/extensions/xlang.xlang-0.1.0/` and is listed
  by `code --list-extensions` as `xlang.xlang@0.1.0`. VS Code loads it on every
  start, automatically, whenever you open a `.x` file. There is no manual step.
* The Python dependencies live in this repo's `.venv/`, which also survives
  restarts. The interpreter path is **auto-detected** every activation
  (`.venv/bin/python`), so it is not a hard-coded absolute path baked into
  settings.
* `x.toml` is read from disk on demand — restarts do not affect it.

Things that **would** make you redo work:

| If you… | Then… |
|---|---|
| Edit `src/extension.ts`, `package.json`, `syntaxes/*.json` or `server/server.py` | The installed copy is stale → recompile, repackage, reinstall (§8) |
| Delete or move the `.venv` | Set `xlang.pythonPath` in settings, or recreate the venv and `pip install pygls lsprotocol` |
| Delete or move this repository | The editable `x-language` install breaks → `pip install -e .` again |
| Move the repo to a different path | `xlang.xlang` still works (the extension folder is independent), but re-run `pip install -e .` from the new location |
| Uninstall the extension | `code --uninstall-extension xlang.xlang` — reversible |

Your VS Code **settings.json was never touched**, so there is nothing to
re-apply there. To undo everything: `code --uninstall-extension xlang.xlang`.

## 8. Rebuilding after you change the source

```bash
cd vscode-xlang
npm run compile                                            # TypeScript -> out/
npx --yes @vscode/vsce package --allow-missing-repository \
    --skip-license -o /tmp/opencode/xlang-0.1.0.vsix       # package
code --install-extension /tmp/opencode/xlang-0.1.0.vsix    # (re)install
```

Then **Ctrl/Cmd+Shift+P → "Developer: Reload Window"**. VS Code does not
hot-reload an extension's compiled code, and it does not re-read the grammar
until the window reloads.

While developing, you can skip packaging entirely: open the `vscode-xlang/`
folder and press **F5** to launch an Extension Development Host.

## 9. Settings reference

| Setting | Default | Effect | Needs restart? |
|---|---|---|---|
| `xlang.enableTypeChecking` | `true` | Master switch for the `TypeChecker` (lex/parse errors still show) | No — pushed live |
| `xlang.strictTyping` | `false` | Force-enables `strict_typing` even if `x.toml` says otherwise | No — pushed live |
| `xlang.pythonPath` | `""` | Override the interpreter used to run the server | **Yes** — "Restart X Language Server" |
| `xlang.serverPath` | `""` | Override which script is run as the server | **Yes** |

## 10. Troubleshooting

Open **View → Output → "X Language"** (this channel is created by the
extension). It prints the exact interpreter and server path it chose; if the
server fails to start, the error appears there.

| Symptom | Likely cause |
|---|---|
| No colors at all | Window not reloaded after install; or the file is not associated with language id `x` (status bar bottom-right should say **X**) |
| Colors but no completions/squiggles | Look at the **X Language** output channel — usually `pygls` missing from the chosen interpreter |
| Warning "…is missing pygls" | Set `xlang.pythonPath` to `.venv/bin/python`, or `pip install pygls lsprotocol` into that interpreter |
| Diagnostics differ from `x check` | `x.toml` not found — the server searches upward from the **file's** directory, `x check` searches from your shell's cwd |
| Ctrl+Click does nothing | The identifier has no declaration in the *same* file — see §11 |

## 11. Follow-up fixes

Two further bugs were reported after the work above.

### Ctrl+Click / F12 (go to definition) did nothing useful

The old handler ran exactly one regex over the buffer —
`\b(class|interface|enum|type)\s+<word>` — so only a *type name* could ever
resolve. Ctrl+Click on a function, a method, a variable or a parameter
returned nothing.

`definition()` in `server/server.py` now resolves in three phases:

1. **The declaration you are sitting on.** Clicking a name inside its own
   signature stays there instead of jumping to an unrelated same-named field
   elsewhere in the file.
2. **The enclosing function/method/constructor body**, found by matching
   braces from the nearest declaration line. This is what makes a *parameter
   usage* land on its own parameter list rather than on a field with the same
   name.
3. **The whole file**, trying the patterns in priority order: class /
   interface / enum / type alias → `function` → method or constructor →
   interface signature → field → `let`/`const`/`var` → parameter → bare enum
   member.

Two details did most of the work:

* The buffer goes through `code_lines()` first, which replaces comments,
  string literals and backtick templates with **spaces of the same length**.
  Line and column positions are unchanged, so the reported ranges are still
  exact — but `// class DeepImpl implements D {` can no longer be returned as
  the definition of `DeepImpl`.
* The parameter pattern only fires where a parameter name can legally sit
  (immediately followed by `,`, `=`, `:` or `)`) and requires the closing `)`
  to be followed by `,`, `;`, `:` or `{`. That is what keeps `print(x)`,
  `foo.bar(x)` and `} catch (System.Exception e) {` from matching.

Verification: 29/29 on a dedicated fixture; a sweep over `examples/*.x` gave
0 exceptions and 0 comment targets.

### `void` functions could return a value

`_resolve_return_type()` deliberately returns `None` for `void` (and for
`any`), so `_check_return()` had nothing left to compare against and never
fired. This type-checked clean:

```x
void function mutateAddress(string city){
    city = "Nagpur";
    return city
}
```

`x check` and the LSP now both report:

```
error: Function 'mutateAddress' is declared 'void' and cannot return a value
```

Implementation: `_returns_void`, `_callable_kind` and `_callable_name` are
saved, set and restored alongside `_expected_return` in `_check_function()`,
`_infer_function_expression()` and `_reset()`. `_check_return()` reports after
the existing constructors check, so `Constructors cannot return a value` still
wins for a constructor. A bare `return` in a `void` function stays legal, and
an `any` function that returns a value stays legal.

`examples/main.x` had exactly this bug at line 40; the stray `return city` was
removed, which is also what makes the two tests that assert the example is
clean pass again.

## 12. Known limitations

* **Go-to-definition is single-file only.** The server searches the current
  buffer; it does not resolve across `import` statements or into the standard
  library. Jumping to `System.io.FileSystem` or to anything in another file is
  not supported yet.
* **No scope analysis.** Phase 2 (enclosing function) and the declaration
  priority order are a good approximation, not a real symbol table: if two
  functions declare the same name, or a local shadows a field declared far
  away, the jump can pick the wrong one. There is no shadowing-aware
  resolution across sibling functions.
* The same applies to **Find All References** (returns an empty list).
* **`vscode-xlang/sample.x` contains invalid X** (it was written with
  TypeScript-style `public T add(T item): T {`; real X syntax is
  `public T add(T item) {`). It is a *highlighting* fixture, not a compiling
  one, so it will show red squiggles.
* There are no semantic tokens — highlighting is 100 % TextMate, so local
  variables and parameters are not colored differently from other identifiers.
