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

### Go to Definition (F12)
Navigate to class/interface definitions in the current file.

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