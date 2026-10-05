# X Language project

This project is an experimental Python interpreter for **X Language
Specification Draft 0.1**. It is intended as a working language prototype and
learning project, not as a production compiler. The implementation requires
Python 3.10 or newer and has no third-party runtime dependencies.

## Setup

Create and activate the virtual environment, then install the local package:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

The installation provides the `x` command.

## Command-line interface

```sh
x run path/to/main.x [arguments...]
x path/to/main.x [arguments...]
x check path/to/main.x
x build path/to/main.x
x version
x help
```

- `run` executes an X source file and supplies remaining command-line values
  through the `string[] args` parameter to `main`.
- Running `x file.x` is shorthand for `x run file.x`.
- `check` lexes and parses the entry file and its imports.
- `build` currently performs the same validation; it does not emit a native
  executable.
- The process exit code is taken from an integer returned by `main`; a `void`
  or inferred-void `main` returns success.

## Language features implemented

The interpreter currently supports:

- `.x` source files, `//` comments, and `/* ... */` comments.
- Primitive literals: integers, floating point numbers, strings, booleans, and
  `null`.
- `let` variables, `const` constants, inferred and explicit variable types,
  array literals, array indexing, and object literals.
- Standalone functions, typed parameters, inferred/explicit return types,
  first-class function references, generic declaration/call syntax, and
  overload resolution by argument count and runtime value types.
- Classes, fields, constructors, overloaded constructors, instance methods,
  static fields and methods, `this`, single inheritance, and `super`.
- Enums with implicit ordinal values.
- Arithmetic, comparison, equality, logical, assignment, and increment/
  decrement operators.
- `if`/`else`, `while`, `break`, `continue`, iterable `for ... in`, and
  end-exclusive `range(start, end, step)`.
- `try`/`catch`/`finally` and `throw`.
- Program arguments through `args`, plus the `print`, `range`, and `Exception`
  built-ins.
- Project-relative named imports, grouped imports, and import aliases.
- The `System.io.FileSystem` standard-library module described below.

The interpreter executes code dynamically. It does **not** yet provide the
specification's promised static type checker; declared types are primarily
syntax and overload-resolution hints at runtime.

## Project module imports

Each named import resolves to a source file under the current project
directory. Dots in the import path map to folders, and the imported declaration
must be exported.

```text
project/
├── main.x
└── tools/
    └── Greeting.x
```

```x
// tools/Greeting.x
export class Greeting {
    public string message() {
        return "Hello from another module";
    }
}
```

```x
// main.x
import tools.Greeting as Welcome

function main() {
    let Welcome greeting = Welcome();
    print(greeting.message());
}
```

Grouped imports are also supported:

```x
import tools.{Greeting, Printer as ConsolePrinter}
```

The import loader currently combines project declarations into a shared runtime
namespace. Wildcard imports, isolated module namespaces, and full package/name
resolution are not implemented.

## File system standard library

Import the built-in file system class using the X module path:

```x
import System.io.FileSystem
```

`System.io.FileSystem` is currently a built-in module supplied by the Python
runtime; it does not require a `System/io/FileSystem.x` file in the project.
Paths are interpreted relative to the process working directory unless they
are absolute. Text operations use UTF-8.

| Method | Signature | Behavior |
| --- | --- | --- |
| `exists` | `boolean exists(string path)` | Returns whether a path exists. |
| `isFile` | `boolean isFile(string path)` | Returns whether a path is a file. |
| `isDirectory` | `boolean isDirectory(string path)` | Returns whether a path is a directory. |
| `readText` | `string readText(string path)` | Reads a UTF-8 text file; reports missing, unreadable, or invalid UTF-8 files. |
| `writeText` | `void writeText(string path, string content)` | Creates or replaces a UTF-8 text file. Its parent directory must already exist. |
| `appendText` | `void appendText(string path, string content)` | Appends UTF-8 text, creating the file if needed. Its parent directory must already exist. |
| `createDirectory` | `void createDirectory(string path)` | Creates a directory and missing parent directories; succeeds if it already exists. |
| `listDirectory` | `string[] listDirectory(string path)` | Returns immediate entry names in sorted order. |
| `deleteFile` | `void deleteFile(string path)` | Deletes one file; it does not recursively delete directories. |
| `deleteDirectory` | `void deleteDirectory(string path)` | Deletes an empty directory only. |

Example:

```x
import System.io.FileSystem

function main() {
    let string directory = "build/notes";
    let string filePath = directory + "/readme.txt";

    FileSystem.createDirectory(directory);
    FileSystem.writeText(filePath, "First line.\n");
    FileSystem.appendText(filePath, "Second line.\n");
    print(FileSystem.readText(filePath));
}
```

File-system errors are reported as X runtime errors with the attempted
operation and path. File access is **not sandboxed**: X programs run with the
operating-system permissions of the process. Only run programs whose source you
trust.

## Runnable examples

### Queue and language-feature demo

```sh
x run examples/queue_tests.x Alice
```

The project in `examples/queue/` and `examples/queue_tests.x` demonstrates
multi-file grouped imports, a generic queue class, enums, command-line
arguments, iterable loops, `range` loops, `while`, and exception handling. It
runs checks for FIFO order, peek, size, empty state, and dequeue-on-empty.

### File system demo

```sh
x run examples/filesystem_demo.x
```

The demo creates `build/filesystem-demo/notes.txt`, writes and appends text,
reads and lists it, then removes the file and its now-empty directory. The
`build/` directory is ignored by Git.

## Tests

Run the interpreter tests from the project root:

```sh
python -m unittest discover -s tests -v
```

The tests cover parsing and execution of core syntax, functions, classes,
inheritance, generics, exception handling, grouped project imports, and
`System.io.FileSystem` operations.

## Not implemented yet

The specification includes features beyond this prototype. In particular,
these are not yet implemented or are only parsed superficially:

- Static type checking, definite assignment, and compile-time diagnostics.
- Native or bytecode compilation; `build` is currently a syntax/import check.
- Interfaces as enforceable contracts, abstract-method validation, and
  access-control enforcement.
- Generic type checking and type-parameter substitution.
- Nested classes and other nested types.
- Union/nullable type semantics, structural type validation, and records.
- Wildcard imports and independent module namespaces.
- A broader standard library beyond the built-ins documented here.

The detailed syntax proposal remains in [Draft.md](./Draft.md). Where the
interpreter behavior is narrower than that draft, this README describes the
features that can currently be relied upon.
