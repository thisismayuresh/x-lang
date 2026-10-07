# X Language LSP Server

Python-based Language Server Protocol implementation for the X programming language.

## Installation

```bash
cd server
poetry install
```

Or with pip:

```bash
cd server
pip install -e .
```

## Running

```bash
python server.py
```

The server communicates via stdio (LSP standard).

## Features

- Real-time diagnostics (type errors, parse errors)
- Completion (Ctrl+Space)
- Hover (type information)
- Go to Definition
- Find References (placeholder)

## Configuration

The server reads configuration from VS Code settings:

- `xlang.enableTypeChecking` (boolean, default: true)
- `xlang.strictTyping` (boolean, default: false)

## Architecture

```
server/
├── server.py           # Main LSP server entry point
├── handlers/           # LSP request handlers (future)
├── workspace/          # Document management (future)
└── pyproject.toml      # Dependencies
```

## Integration with X Language

The server reuses the existing X language components:
- `xlang.lexer.Lexer` - Tokenization
- `xlang.parser.Parser` - Parsing
- `xlang.typecheck.TypeChecker` - Type checking

## Development

To run the server in development mode with auto-reload:

```bash
# Install watchdog for file watching
pip install watchdog

# Run with auto-reload (manual restart needed for now)
python server.py
```

## Testing

```bash
poetry run pytest
```