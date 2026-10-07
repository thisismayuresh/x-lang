# VS Code Integration Plan for X Language

## Overview

This document outlines the plan to add type suggestions, syntax highlighting, import suggestions, and other IDE features to VS Code for the X programming language.

---

## Phase 1: Syntax Highlighting (Week 1-2)

### 1.1 Create TextMate Grammar (.tmLanguage)

**Goal**: Provide syntax highlighting for `.x` files in VS Code.

**Steps**:
1. Create `syntaxes/x.tmLanguage.json` based on the X language grammar
2. Define token patterns for:
   - Keywords: `class`, `function`, `let`, `const`, `if`, `else`, `while`, `for`, `return`, `new`, `import`, `export`, `interface`, `enum`, `type`, `abstract`, `final`, `static`, `public`, `private`, `protected`, `async`, `await`, `try`, `catch`, `finally`, `throw`, `switch`, `case`, `default`, `match`, `extends`, `implements`, `package`, `namespace`
   - Types: `int`, `string`, `float`, `boolean`, `void`, `any`, `null`, `undefined`
   - Literals: strings, numbers, template literals
   - Operators: `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `===`, `!==`, `<`, `>`, `<=`, `>=`, `&&`, `||`, `=`, `+=`, `-=`, `*=`, `/=`
   - Comments: `//`, `/* */`
   - Decorators: `@name`
   - Interpolation: `${...}` in template strings

**Deliverable**: `syntaxes/x.tmLanguage.json`

### 1.2 Register Grammar in package.json

Add to extension's `package.json`:
```json
{
  "contributes": {
    "languages": [{
      "id": "x",
      "aliases": ["X", "x"],
      "extensions": [".x"],
      "configuration": "./language-configuration.json"
    }],
    "grammars": [{
      "language": "x",
      "scopeName": "source.x",
      "path": "./syntaxes/x.tmLanguage.json"
    }]
  }
}
```

### 1.3 Language Configuration

Create `language-configuration.json` for:
- Brackets: `()`, `[]`, `{}`
- Auto-closing pairs
- Comments
- Folding rules

---

## Phase 2: Type Checking Integration (Week 2-3)

### 2.1 Language Server Protocol (LSP) Server

**Goal**: Implement an LSP server using the existing type checker.

**Architecture**:
```
xlang_lsp/
├── server.py          # LSP server entry point
├── handlers/
│   ├── diagnostics.py # textDocument/publishDiagnostics
│   ├── completion.py  # textDocument/completion
│   ├── hover.py       # textDocument/hover
│   ├── definition.py  # textDocument/definition
│   └── references.py  # textDocument/references
├── workspace/
│   └── document_manager.py  # Track open documents
└── __main__.py        # CLI entry point
```

**Key Integration Points**:
- Reuse `xlang.parser.Parser`, `xlang.lexer.Lexer`, `xlang.typecheck.TypeChecker`
- Cache parsed programs for incremental checking
- Debounce diagnostics (300ms after typing stops)

### 2.2 Diagnostics (Error Squiggles)

**Implementation**:
```python
# handlers/diagnostics.py
async def handle_diagnostics(server, params):
    document = server.documents[params.textDocument.uri]
    source = document.source
    
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    
    errors = TypeChecker().check(program, source_name=params.textDocument.uri)
    
    diagnostics = []
    for error in errors:
        diagnostics.append(Diagnostic(
            range=Range(
                start=Position(line=error.line - 1, character=error.column - 1),
                end=Position(line=error.line - 1, character=error.column + 10)
            ),
            severity=DiagnosticSeverity.Error,
            message=error.message,
            source="xlang"
        ))
    
    await server.publish_diagnostics(params.textDocument.uri, diagnostics)
```

### 2.3 Completion (Ctrl+Space)

**Sources for completions**:
- Local variables in scope
- Class members (fields, methods)
- Imported modules
- Built-in types (`int`, `string`, `float`, `boolean`, `void`, `any`)
- Keywords
- Built-in functions (`print`, `range`, `typeOf`, `sleep`, `input`)

**Context-aware completions**:
- After `new ` → class names
- After `import ` → module names
- After `.` on instance → member names
- In type annotations → type names

### 2.4 Hover (Type Information)

Show type information on hover:
- Variable type
- Function signature
- Class documentation

---

## Phase 3: Import Suggestions (Week 3-4)

### 3.1 Import Completion

**Trigger**: After typing `import ` or `from `

**Sources**:
- Project modules (scanned from workspace)
- Standard library: `System.io.Console`, `System.io.FileSystem`, `System.Object`, `Object`, `HashMap`, `LinkedList`, `Stack`, `Queue`, `PriorityQueue`, `Trie`, `Set`, `TreeMap`, `TreeSet`, `LRUCache`, `Thread`
- User-defined modules in `x.toml` `[dependencies]`

### 3.2 Auto-import on Undefined Symbol

When type checker reports "Unknown type 'Address'":
- Show quick fix: "Import Address from ./models/Address"
- Show quick fix: "Create new file Address.x"

---

## Phase 4: Advanced Features (Week 4-6)

### 4.1 Go to Definition / Find References

- Navigate to class/function/type definitions
- Find all usages of a symbol

### 4.2 Document Symbols (Outline View)

Show classes, interfaces, enums, functions in the outline view.

### 4.3 Code Actions (Quick Fixes)

- Add missing import
- Add missing return type
- Add missing parameter types
- Fix constructor return type

### 4.4 Semantic Highlighting

Enhance syntax highlighting with semantic tokens:
- Classes, interfaces, enums in different colors
- Functions vs methods
- Parameters vs local variables
- Static vs instance members

---

## Phase 5: Debug Adapter (Week 6-8)

### 5.1 Debug Adapter Protocol (DAP)

Implement DAP for:
- Breakpoints
- Step over/into/out
- Variable inspection
- Call stack
- Watch expressions

---

## Technical Requirements

### Dependencies
```toml
# pyproject.toml additions
[tool.poetry.dependencies]
lsprotocol = "^2024.0.0"
pygls = "^1.2.0"  # Alternative LSP framework
watchdog = "^4.0.0"  # File watching
```

### Extension Structure
```
vscode-xlang/
├── package.json
├── src/
│   ├── extension.ts          # VS Code extension entry
│   ├── lsp-client.ts         # Connect to LSP server
│   └── tasks.ts              # Type check on save task
├── syntaxes/
│   └── x.tmLanguage.json
├── language-configuration.json
└── server/
    └── (Python LSP server - bundled or separate)
```

---

## Immediate Action Items (This Week)

### 1. Create TextMate Grammar
- [ ] Write `syntaxes/x.tmLanguage.json` with comprehensive patterns
- [ ] Test in VS Code with a sample `.x` file

### 2. Fix Type Checker Built-in Functions
- [ ] Add `input` to `_builtin_scope()` with proper return type
- [ ] Add `Console.input` with overloads for typed input
- [ ] Test with `test_input_age.x`

### 3. Create CSV Test Cases
- [ ] Document all identified bugs with test cases
- [ ] Track fix status

### 4. LSP Server Skeleton
- [ ] Create basic LSP server using `lsprotocol` or `pygls`
- [ ] Implement diagnostics handler

---

## Testing Strategy

### Unit Tests for Type Checker
- Test each built-in function signature
- Test constructor return value rejection
- Test user input type validation

### Integration Tests
- LSP diagnostics appear in VS Code
- Completions work in various contexts
- Import suggestions work

---

## Success Criteria

1. **Syntax highlighting** works for all X language constructs
2. **Type errors** appear as red squiggles in real-time
3. **Ctrl+Space** shows relevant completions
4. **Hover** shows type information
5. **Go to Definition** works for user-defined symbols
6. **Import suggestions** appear for undefined types
7. **Auto-import** quick fix available

---

## Notes

- The existing type checker (`TypeChecker`) is robust and covers most static analysis needs
- The parser/lexer are production-ready
- Main effort is wrapping these in LSP and VS Code extension
- Consider bundling Python LSP server with extension for zero-config setup