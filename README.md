# X Language project

This project is an experimental Python interpreter for **X Language
Specification Draft 0.1**. It is intended as a working language prototype and
learning project, not as a production compiler. The implementation requires
Python 3.10 or newer. Python 3.11+ uses the standard-library TOML reader;
Python 3.10 installs the small `tomli` compatibility dependency.

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
x -watch path/to/main.x
x --config path/to/x.toml --feature async=off check path/to/main.x
x run --profile development path/to/main.x -- --verbose "value with spaces"
x start
x start -- extra script arguments
x version
x help
```

- `run` executes an X source file and supplies remaining command-line values
  through the `string[] args` parameter to `main`.
- Running `x file.x` is shorthand for `x run file.x`.
- `check` lexes and parses the entry file and its imports.
- `check`, `build`, and `run` report all recoverable lexical and syntax errors
  found in the loaded source files before execution. A malformed construct can
  limit recovery, so errors after it may not be discoverable in that pass.
- `build` currently performs the same validation; it does not emit a native
  executable.
- `-w`/`--watch` (also spelled `-watch`) runs the command once and re-runs it
  whenever the entry file, one of its imported files, or `x.toml` changes;
  press Ctrl+C to stop. Errors keep the watcher alive, so saving a fix
  triggers the next run. Watch mode works with `run`, `check`, and `build`
  and must appear before the source file.
- Commands listed in the `[scripts]` table of `x.toml` run with `x <name>`,
  similar to `pnpm start` and package.json scripts.
- The process exit code is taken from an integer returned by `main`; a `void`
  or inferred-void `main` returns success.

## Project configuration

The CLI discovers `x.toml` in the current directory by default. Pass
`--config path/to/file.toml` to select another file, or `--no-config` to
disable discovery. Command-line `--feature NAME=on|off` settings override
feature values in TOML. The supported features are `access_modifiers`,
`array_push`, `arrow_functions`, `async`, `bulk_export`, `classes`,
`collections`, `command_input`, `concurrency_primitives`, `decorators`,
`destructuring`, `enhanced_input`, `enums`, `equality`, `exceptions`,
`filesystem`, `generics`, `interfaces`, `loops`, `math_library`,
`namespaces`, `network`, `object_literals`, `pattern_matching`, `records`,
`spread`, `static_methods`, `switch`, `threads`, `type_checker`, and
`unions`. They all default to enabled. The experimental `url_imports`,
`package_manager`, and `strict_typing` features are also supported but
default to disabled.

The repository's [x.toml](./x.toml) demonstrates the schema:

```toml
[cli]
default-command = "run"
color = "auto" # auto, always, or never

[features]
classes = true
pattern_matching = false

[run]
args = ["from config", "argument with spaces"]

[run.environment]
APP_MODE = "development"

[run.profiles.test]
args = ["profile-specific argument"]

[run.profiles.test.environment]
APP_MODE = "test"

[scripts]
start = "x run path/to/main.x"
test = "x check path/to/main.x"
```

`[run].args` are passed to the program first, followed by profile arguments
and then any CLI arguments. Use `--` to mark the end of X CLI options and begin
program arguments. Each TOML array entry remains one argument; spaces are not
split. Environment values from the operating system are overlaid by
`[run].environment`, then by the selected profile. X code can read a value
directly as `System.Environment.APP_MODE`; the built-in `System` namespace is
available without an import. `System.Environment.has("APP_MODE")` and
`System.Environment.all()` are also available. Configured environment values
are scoped to the interpreter and do not modify the parent process.
Run profiles are selected with `--profile NAME`.

`[scripts]` maps script names to shell commands, mirroring the `scripts` table
in package.json. Run one with `x start` (or `x run start`); extra command-line
values are appended to the command after shell quoting, profile arguments are
appended when `--profile` is given, and profile/`.env`/`[run.environment]`
values are exported to the process. The command runs in the project root
(directory of `x.toml`) and its exit status becomes the `x` exit code, so
`x test` propagates a failing status exactly like `pnpm test`. Script names
must be single words that do not collide with the built-in commands
(`run`, `check`, `build`, `install`). `--watch` cannot be combined with
scripts because a shell command does not expose the files it depends on.

The CLI also loads a project-root `.env` file when running a program. Copy the
safe demo values in [.env.example](./.env.example) to `.env`, then run the
configuration example:

```sh
cp .env.example .env
x run examples/configuration/configured_args.x
```

Read values directly as `System.Environment.VARIABLE_NAME`; no import or
`get()` call is needed. `.env` assignments support `KEY=VALUE`, optional
`export`, blank lines, full-line comments, and single- or double-quoted values.
The file is not loaded for `check` or `build`. Existing operating-system
variables take precedence over matching `.env` values; TOML run environment
settings and then the selected profile override both. `.env` is ignored by
Git, so keep credentials and machine-specific values there, never in the
tracked example.

An explicit subcommand (`run`, `check`, or `build`) always wins. The
`[cli].default-command` setting applies to the shorthand `x file.x` form.
Unknown keys, feature names, types, and profile names fail with an actionable
configuration error.

## Language features implemented

Implemented and currently demonstrated features:

- [x] `.x` source files, `//` comments, and `/* ... */` comments.
- [x] Primitive literals: integers, floating point numbers, strings, booleans,
  `null`/`Null`, and `undefined`/`Undefined`.
- [x] Multiline backtick template literals with `{expression}` interpolation;
  `print` evaluates any number of arguments and separates their string forms
  with spaces.
- [x] `let` variables, `const` constants, inferred and explicit variable types,
  `int` as an alias for `integer`, array literals/indexing, JavaScript-like
  object literals, array/object destructuring declarations and assignments,
  defaults, rest properties, and object spread.
- [x] Standalone functions, typed parameters, inferred/explicit return types,
  first-class function references, generic declaration/call syntax, and
  overload resolution by argument count and runtime value types. Generic
  `object<K, V>` annotations validate dictionary key/value types at runtime.
- [x] `Function`/`function` callback annotations validate function values.
  `interface` declarations support comma- or semicolon-separated fields and
  method signatures, including nested interface types and typed arrays.
  Interface-typed values are checked structurally: `x check` rejects a value
  whose type lacks a compatible method or fields, and the interpreter applies
  the same conformance rules again at runtime. A method must exist with a
  compatible signature and fields must satisfy their declared types.
- [x] Nested named functions in blocks; their declarations bind functions without
  executing their bodies, and the functions can capture surrounding locals.
- [x] Typed rest parameters (`integer ...values`), array/call-argument spread, and
  object-literal spread.
- [x] Classes, nested classes, namespaces, fields, constructors, overloaded constructors, instance methods,
  static fields and methods, `new`, `this`, single inheritance, and explicit
  parent constructor/method calls through `super`.
- [x] Enforced `public`, `protected`, and `private` instance/static members.
  Unmodified properties and methods are public. `protected` members are
  available within their declaring class and derived classes; `private`
  members are restricted to the declaring class. `final class Name` cannot be
  extended.
- [x] Function, class, constructor, and method decorators. The built-in `@trace`
  decorator logs calls/construction; custom decorators can transform a
  function or class by returning the target they receive.
- [x] Enums with implicit ordinal values, valid at module, class, function, and
  nested block scope.
- [x] Arithmetic, comparison, equality, logical, assignment, and increment/
  decrement operators.
- [x] Ternary conditional expressions and null-safe optional chaining for member
  access (`?.`), calls (`?.()`), and indexing (`?[index]`).
- [x] `if`/`else`, `while`, `do ... while`, classic `for`, `for ... in`, `for ...
  of`, `break`, `continue`, and end-exclusive `range(start, end, step)`.
- [x] Rust-inspired `match` expressions with wildcard, binding, literal, enum,
  array/object destructuring, alternatives, guards, and rest patterns.
- [x] Arrow functions (`let double = (value) => value * 2;`), `switch`
  statements, record type aliases (`type Point = record { int x; int y; };`),
  array `.push(...)`, bulk `export { ... };` lists, and typed `input()`
  validation when `enhanced_input` is enabled.
- [x] `try`/`catch`/`finally` and `throw`.
- [x] Automatic statement terminators at line breaks, closing braces, and EOF.
- [x] JavaScript-like `==` coercion for supported primitive values and strict
  `===` type/reference comparison. Enum members compare only within the same
  enum.
- [x] A compact `Object` helper namespace: `keys`, `values`, `entries`, `assign`,
  and `hasOwn`.
- [x] `async` functions, `await`, concurrent `Async.all`, and OS threads through
  `Thread.start` and `join`.
- [x] Program arguments through `args`, plus the `print`, `range`, and `Exception`
  built-ins, and the `typeOf` runtime type helper.
- [x] Project-relative named imports, grouped imports, wildcard imports, and
  import aliases.
- [x] The `System.io` modules (Console, FileSystem, and the awaitable
  `Network.http` `fetch`), `System.Environment`, `System.concurrent`, and
  `System.utils` described below.
- [x] Fully-qualified catch types over importable `System.Throwable...`
  exception paths, and `JSON.stringify`-style `System.utils.JSON.toJSON`.

The interpreter executes code dynamically, and `x check`, `x build`, and
`x run` all run the static type checker first: declared types, interface
conformance, definite assignment, and `strict_typing` rules become
compile-time diagnostics printed before any statement executes. Runtime
failures still stop execution at the point of failure.

### Diagnostics

Lexical errors identify invalid characters (for example,
`Unexpected character '$'`). Syntax errors identify tokens that cannot appear
in the current grammar position (for example,
`Unexpected token ')'; expected an expression`). The CLI prints each
recoverable source diagnostic with its own file location and excerpt, then
exits unsuccessfully without running the program.

Run `x check examples/errors/syntax_error.x` to see an unexpected-token
diagnostic. The invalid `;` after `=` is a valid character, but it is not a
valid expression token; by contrast, a character such as `$` is reported by
the lexer as an unexpected character.

Type errors use the same rustc-style block, with optional `= note:` and
`= help:` follow-up lines. Run `x check examples/errors/typed_array.x` to
see a note:

```text
error: Cannot assign '(integer|string)[]' to 'values' of type 'integer[]'
 --> examples/errors/typed_array.x:2:5
  |
2 |     let integer[] values = [1, 2, "name"];
  |     ^ Cannot assign '(integer|string)[]' to 'values' of type 'integer[]'
  = note: expected `integer[]`, found `(integer|string)[]`
x: found 1 type error(s)
```

and `x check examples/test/test_interface.x` to see a help:

```text
error: Class 'Animal' does not implement 'getGender()' from interface 'Person'
 --> examples/test/test_interface.x:5:1
  |
5 | class Animal implements Person{
  | ^ Class 'Animal' does not implement 'getGender()' from interface 'Person'
  = help: implement `string getGender()` on class `Animal`
x: found 1 type error(s)
```

`x check` and `x run` report a type error identically, block for block, and
one run can report several errors at once:
`x check examples/test/test_multiple_errors.x` prints two independent
blocks — each with its own header, location, excerpt, and caret — followed
by the single line `x: found 2 type error(s)`. The excerpt is dropped by
`--no-context` (the location and hints stay), and `--color always`,
`--color never`, or `NO_COLOR` control whether the block carries ANSI
colours.

## Runtime types and typed objects

`typeOf(value)` is a built-in and needs no import. It returns JavaScript-style
runtime type names: `"string"`, `"number"` for both integers and floats,
`"boolean"`, `"Array"` for every array, `"object"` for object literals, enum
members, `null`, and `undefined`, and the class name for instances of a user
class (for example `"User"`). Callable values are labelled by where they are
declared: class methods — instance or static, single or overloaded — report
`"method"`, while functions, lambdas, class objects, and builtins report
`"function"`. Collections report their collection name (`"HashMap"`,
`"Stack"`, `"Queue"`, ...). Both `null`/`Null` and `undefined`/`Undefined`
are accepted literal spellings. Optional access that finds no value produces
`undefined`, so `typeOf(profile[0]?.x)` returns `"object"` while printing that
value displays `undefined`. `typeOf` requires exactly one argument.

```x
let object profile = {
    "name": "Maya",
    age: 21
};

print(typeOf(profile)); // object
print(typeOf(profile.name)); // string
print(typeOf(profile.age)); // number
```

X's existing type annotation syntax puts the type before the variable name.
For example, `let object profile = ...` declares a variable named `profile`
with the broad `object` type, while `let profile object = ...` means a
variable named `object` annotated with type `profile`. The type checker
reports an unknown annotation in either order (`Unknown type 'profile'`), so
use the type-before-name order shown here.
For a dictionary whose keys and values are both strings, write
`let object<string, string> user = ...`; the key and value types are checked
when the value is created or assigned, passed to a typed parameter, or
mutated. This generic object type describes key/value types, not a fixed set
of named properties. X does not currently support TypeScript's
`let user: object<string, string>` annotation syntax.

Run the complete sample with:

```sh
x run examples/type_of.x
```

## Optional chaining and ternary expressions

Use `?.member`, `?.(arguments)`, and `?[index]` to stop a chain and return
`null` when the value at that point is `null`. Optional member access also
returns `null` for a missing dictionary property. Optional indexing returns
`null` for an out-of-range sequence index or a missing dictionary key. For
example, `users?[0]` is X's optional-index syntax; it does not require
JavaScript's `users?.[0]` punctuation. A non-null value of the wrong kind and
an invalid index type still report an error. Normal `users[0]` access remains
strict and continues to report invalid indexes.

```x
let users = ["Alice", "Bob"];
let profile = [{name: "Maya"}];
let missing = null;
let callback = null;

print(users?[0]); // Alice
print(typeOf(users?[5])); // object (the result is null)
print(profile?[0]?.name); // Maya
print(typeOf(missing?.profile?.name)); // object (the result is null)
print(callback?.()); // null; callback is not called

let first = true ? users?[0] : "no user";
```

Optional calls do not evaluate their arguments when the callee is `null`.
Chaining can protect both member access and invocation:
`user?.profile?.getName?.()`. Optional chaining is not a substitute for
guarding an undefined variable name; the identifier itself must first be
declared.
The ternary operator is already supported as `condition ? whenTrue : whenFalse`.
Whitespace-separated `? [` continues to be parsed as a ternary expression
whose true value begins with an array literal; contiguous `?[` is the distinct
optional-index operator.

Run the complete example with `x run examples/optional_chaining.x`.

Nested functions use the same declaration syntax and run only when called.
They can close over local variables:

```x
function main() {
    let integer multiplier = 3;

    integer function multiply(integer value) {
        return value * multiplier;
    }

    print(multiply(7)); // 21
}
```

Run the example with `x run examples/nested_functions.x`.

## Project module imports

Each named import first resolves to a source file beside the importing file;
if it is not found there, it resolves under the current project directory.
Dotted path parts map to folders. For example, `import greeting.sayHello`
loads `greeting.x` and selects its exported `sayHello` declaration.

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

Use `*` to import all exports from a file. Add an alias to access them through
a namespace-like value:

```x
import greeting.* as Greet

Greet.sayGreet()
```

An imported module runs its top-level statements once. If the module calls its
exported `main()` itself, the importing file only needs the import:

```text
project/
└── control_flow/
    ├── main.x
    └── main_file.x
```

```x
// control_flow/main.x
export function main() {
    print("Called by the module");
}
main()
```

```x
// control_flow/main_file.x
import main
```

Alternatively, when `main.x` only exports the function and does not call it,
the entry file can import and invoke it:

```x
import main
main()
```

Run the first example with `x run examples/control_flow/main_file.x`. The
import resolves to the sibling `main.x`, executes its top-level call, and
does not implicitly call `main` a second time. Use the second form to control
when the exported function is called.

X warns at each top-level `main()` call in an importer when the imported module
already calls `main()` during import; the warnings do not suppress execution.
It also flags `main//()`. Since `//` starts a line comment, that expression is
parsed as a bare `main` reference followed by a comment and does not invoke the
function. Write `main()` to call it or `// main()` to comment out the call.

The import loader currently combines project declarations into a shared runtime
namespace. Aliased wildcard imports provide a namespace-like object containing
the file's exports; they do not create an isolated module runtime.

## The System namespace

The built-in `System` tree is available without an import — importing a
standard-library module only brings its short name into scope
(`import System.io.FileSystem` binds `FileSystem`, so you can drop the
`System.io` prefix). Everything that ships with the runtime:

```text
System/
├── Environment                    # process environment (no import needed)
│   ├── has(key)                   # true when the variable exists
│   ├── all()                      # snapshot of every variable
│   └── X_MODE, PATH, HOME, ...    # each process variable as a value
├── io/
│   ├── Console                    # print(message), input(prompt)
│   ├── FileSystem                 # file operations, plus every *Async twin
│   │   ├── exists, isFile, isDirectory
│   │   ├── readText, writeText, appendText
│   │   ├── createDirectory, listDirectory
│   │   ├── deleteFile, deleteDirectory
│   │   └── existsAsync, readTextAsync, writeTextAsync, ...
│   └── Network/
│       └── http                   # fetch(url, options) — see HTTP client
├── concurrent/
│   ├── Async                      # Async.all for concurrent results
│   └── Thread                     # Thread.start and Thread.join
├── Throwable/                     # the exception hierarchy, node for node
│   ├── Error/                     #   DatabaseError
│   └── Exception/
│       ├── RuntimeException/      #   ArithmeticException, TypeException,
│       │                          #   IllegalArgumentException,
│       │                          #   IndexOutOfBoundsException
│       ├── IOException/           #   FileSystemException, HttpException
│       └── DatabaseException
└── utils/
    ├── Collections/
    │   ├── HashMap, LinkedList, List (alias of LinkedList)
    │   ├── Stack, Queue, PriorityQueue, Trie, Set
    │   ├── TreeMap, TreeSet, LinkedHashMap, LRUCache
    │   └── ThreadSafeMap, ThreadSafeSet
    ├── Math                       # abs, sqrt, pow, sin, cos, log, max, ...
    └── JSON                       # toJSON(value, indent?) — JSON.stringify
```

Top-level globals that need no namespace and no import: `print`, `range`,
`typeOf`, and `args`, plus `sleep` (when `async` is enabled), `input` (when
`command_input` is enabled), `trace` (when `decorators` is enabled), `Object`
(when `object_literals` is enabled), and the short collection names (`Stack`,
`HashMap`, `Queue`, ...) when `collections` is enabled.

The four import forms for the same module:

```x
import System.io.FileSystem              # binds FileSystem
import System.io.Network.http.fetch      # binds fetch
import System.io.Network.http            # binds http  -> http.fetch(...)
import System.io.Network.http.fetch as httpGet  # binds httpGet
import System.Throwable.Exception.IOException.HttpException  # binds HttpException
import System.utils.JSON.toJSON          # binds toJSON
```

The `network` feature (enabled by default) gates `System.io.Network`; with it
disabled, importing the module fails with
`feature 'network' is disabled`. The `exceptions` feature gates
`System.Throwable` the same way. `System.utils.JSON` is always available.

## Error and exception handling

All built-in thrown errors derive from `Throwable`:

```text
Throwable
├── Error
│   └── DatabaseError
└── Exception
    ├── RuntimeException
    │   ├── ArithmeticException
    │   ├── TypeException
    │   ├── IllegalArgumentException
    │   └── IndexOutOfBoundsException
    ├── IOException
    │   ├── FileSystemException
    │   └── HttpException
    └── DatabaseException
```

Catch a specific type first, then a parent type. `catch (Throwable error)` is
the broad fallback; `catch (Exception error)` catches checked and runtime
exceptions, while `Error` is a separate branch. Catch variables provide
`name`, `message`, `cause`, and `stack` properties. `stack` currently reports
the source location where the error was raised.

Every node of the hierarchy is also importable as a `System.Throwable` path,
and a catch clause may spell the full path inline — no cast or wrapper:

```x
import System.Throwable.Exception.IOException.HttpException

any function main() {
    try {
        throw HttpException("boom");
    } catch (System.Throwable.Exception.IOException.HttpException error) {
        print(error.message);   // boom
    }
}
```

Short and long catch types are interchangeable: a leaf path matches exactly,
a parent path (`System.Throwable.Exception.IOException`) matches its
subclasses, and `System.Throwable` matches every exception. Prefixes bind too —
`import System.Throwable.Exception.IOException` still gives you the ordinary
`IOException` constructor — while an alias (`import System.Throwable.Exception
as Errors`) exposes the subtree for `Errors.IOException.HttpException(...)`.

Errors can preserve a cause:

```x
try {
    throw new DatabaseException(
        "query failed",
        new IOException("connection unavailable")
    );
}
catch (DatabaseException error) {
    print(error.message);
    print(error.cause.message);
}
catch (Exception error) {
    print("Other exception: " + error.name);
}
```

Applications can define their own exception classes by extending `Exception`
or `Error`. Constructor arguments and ordinary public fields provide
application-specific details:

```x
class CustomException extends Exception {
    public integer statusCode;

    public CustomException(string message, integer statusCode) {
        super(message);
        this.statusCode = statusCode;
    }
}

class BadRequestException extends CustomException {
    public BadRequestException(string message) {
        super(message, 400);
    }
}

try {
    throw new BadRequestException("invalid user id");
}
catch (CustomException error) {
    print(error.name + ": " + error.message);
    print(error.statusCode);
}
```

Custom exception instances are catchable by their own class, any custom parent,
`Exception` or `Error`, and `Throwable`. A custom constructor should call
`super(message)` so the base exception's `name`, `message`, `cause`, and
`stack` properties are initialized.

Arithmetic failures use `ArithmeticException`; file-system operation failures
use `FileSystemException`, which can also be caught as `IOException`,
`Exception`, or `Throwable`. HTTP failures from `fetch` use `HttpException`,
which likewise extends `IOException`. See the runnable
[exception hierarchy example](./examples/exceptions/exception_hierarchy.x).

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

Each operation also has an asynchronous counterpart with the `Async` suffix,
such as `readTextAsync`, `writeTextAsync`, and `listDirectoryAsync`. These return
awaitable results and perform blocking filesystem work on a worker thread. Use
`await` on these operations inside an `async` function; the original methods
remain synchronous.

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

Asynchronous file operations can be awaited in an async function:

```x
import System.io.FileSystem

async function main() {
    await FileSystem.writeTextAsync("notes.txt", "First line.\n");
    let string contents = await FileSystem.readTextAsync("notes.txt");
    await sleep(100);
    print(contents);
}
```

File-system errors are reported as X runtime errors with the attempted
operation and path. File access is **not sandboxed**: X programs run with the
operating-system permissions of the process. Only run programs whose source you
trust.

## HTTP client: System.io.Network.http

`fetch` performs HTTP requests from X. It is asynchronous: call it inside an
`async function` and `await` the result. Every failure — refused connections,
DNS lookup failures, TLS errors, timeouts, bad URLs, bad options, invalid
JSON — raises `HttpException`, so `try` / `catch` / `finally` covers the
whole request lifecycle:

```x
import System.io.Network.http.fetch

async function main() {
    try {
        let response = await fetch("https://api.example.com/users", {
            method: "GET",
            // headers pass through verbatim; User-Agent here wins over
            // the userAgent option and the library default
            headers: {
                "Accept": "application/json",
                "User-Agent": "MyApp/1.0 (contact@example.com)"
            },
            timeout: 10
        });
        print(response.status);          // 200
        print(response.ok);              // true
        let users = response.json();
        print(users.length);
    } catch (HttpException error) {
        print("request failed: " + error.message);
    } finally {
        print("done");
    }
}
```

### Request options

All options are validated at the call site — a typo fails immediately with
the source location and the list of valid names, before any network traffic:

| Option           | Type                     | Default   | Meaning |
| ---------------- | ------------------------ | --------- | ------- |
| `method`         | string                   | `"GET"`   | `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` |
| `headers`        | object                   | `{}`      | Extra headers; number/boolean values are stringified |
| `body`           | string / object / array  | none      | Objects and arrays are JSON-encoded with `Content-Type: application/json` |
| `userAgent`      | string                   | `"X/0.1.0"` | curl-style `User-Agent`; an explicit `headers` entry wins |
| `timeout`        | number (seconds)         | `30`      | `0` or `null` disables the limit (JS `fetch` can hang forever) |
| `followRedirects`| boolean                  | `true`    | Set `false` to receive `3xx` responses directly |
| `throwOnError`   | boolean                  | `false`   | Raise `HttpException` for `>= 400` responses, with a body excerpt |
| `verifySsl`      | boolean                  | `true`    | Set `false` to accept unverified TLS certificates |
| `query`          | object                   | none      | Appended as URL query parameters; array values repeat the key |

```x
let response = await fetch("https://api.example.com/search", {
    method: "POST",
    userAgent: "curl-like client",
    headers: {"Authorization": "Bearer token"},
    body: {query: "x language", limit: 10},
    query: {"pretty": true},
    timeout: 5,
    throwOnError: true
});
```

### Response

Every `await fetch(...)` resolves to a response object:

| Member               | Meaning |
| -------------------- | ------- |
| `status`, `statusText`, `ok` | e.g. `200`, `"OK"`, `true` for `2xx` |
| `url`                | final URL after redirects |
| `headers`            | object of lowercased header names to values |
| `body`, `bodyBytes`  | decoded text, and the raw bytes as an array of integers |
| `text()`             | the body text |
| `json()`             | the body parsed as JSON; raises `HttpException` when invalid |
| `header(name)`       | case-insensitive single-header lookup, `null` when absent |

### Errors

```x
try {
    await fetch("http://127.0.0.1:9/api", {timeout: 2});
} catch (HttpException error) {
    print(error.message);
    // Cannot reach '127.0.0.1:9': connection refused (while fetching ...)
} finally {
    print("always runs");
}
```

- Connection, DNS, TLS, timeout, URL, option, and JSON failures raise
  `HttpException`, catchable also as `IOException`, `Exception`, or
  `Throwable`.
- HTTP error statuses return a normal response (`status` `404`, `ok` `false`)
  unless `throwOnError: true` — closer to `curl --fail` with the status and a
  body excerpt in the message.
- Forgetting `await` is reported explicitly:
  `did you forget 'await'?` instead of silently handing back a promise-like
  value.

Compared with JavaScript's built-in `fetch`: no promise ceremony, a default
timeout, first-class `userAgent`, redirect control, `throwOnError`,
`bodyBytes`, case-insensitive `header(name)`, and call-site validation of
every option — all backed by `HttpException` rather than a grab bag of
`TypeError`/`NetworkError` values.

The `network` feature gates the module; the runnable
[fetch demo](./examples/fetch_demo.x) parses its body with `response.json()`,
prints the first post through `toJSON`, catches `HttpException` by its full
hierarchy path, and degrades into its `catch` clause cleanly when the network
is unavailable:

```sh
x run examples/fetch_demo.x
```

## JSON output: System.utils.JSON.toJSON

`toJSON(value)` stringifies a value with JavaScript's `JSON.stringify`
semantics: compact by default, pretty-printed when given an indent
(`toJSON(value, 2)` spaces per level, or a literal string). Object keys are
quoted, functions and `undefined` members are omitted from objects, `undefined`
inside arrays renders as `null`, and circular structures are rejected with
`Converting circular structure to JSON`. Indent validation matches the
spec too: negative indents and boolean indents raise.

```x
import System.utils.JSON.toJSON

class Point {
    int x;
    public Point(int x) { this.x = x; }
}

any function main() {
    print(toJSON({ok: true, tags: ["http"], n: 200}));
    // {"ok":true,"tags":["http"],"n":200}
    print(toJSON({a: {b: 1}}, 2));
    // {
    //   "a": {
    //     "b": 1
    //   }
    // }
    print(toJSON(new Point(5)));
    // {"x":5}
}
```

Import forms: `import System.utils.JSON.toJSON` binds `toJSON`,
`import System.utils.JSON` binds `JSON` for `JSON.toJSON(...)`, and the
function needs no import at all as `System.utils.JSON.toJSON(...)`.

## Data Structures and Algorithms (DSA) Library

X provides a robust collection of data structures through the `System.utils.Collections` namespace. Every structure supports three usage styles — choose the one that fits your code best.

### Usage Styles

**1. OOP instance style (recommended)** — `new Stack()` returns an instance; call methods directly on it:

```x
import System.utils.Collections.Stack

let Stack<string> history = new Stack<string>()
history.push("first")
history.push("second")
print(history.peek())   // second
print(history.size())   // 2
history.pop()
```

**2. Inline import + short name** — import one structure and use it without a prefix:

```x
import System.utils.Collections.List

let List<string> names = new List<string>()
names.add("Alice")
names.add("Bob")
print(names.getFirst())  // Alice
```

**3. Namespace style** — import the whole module and prefix each call with the structure name:

```x
import System.utils.Collections

let stack = Collections.Stack.create()
Collections.Stack.push(stack, "item")
print(Collections.Stack.peek(stack))  // item
```

**4. Full path** — no import needed, reference via `System.utils.Collections.*`:

```x
let stack = System.utils.Collections.Stack.create()
System.utils.Collections.Stack.push(stack, "item")
```

### Generics

All structures accept a generic type parameter as a documentation/shape hint:

```x
let List<Student> students = new List<Student>()
let Stack<integer> ints    = new Stack<integer>()
let Queue<string>  names   = new Queue<string>()
```

The type parameter documents intent but is not enforced yet: `x check`
accepts a `List<string>` value in a `List<integer>` variable, so treat the
element type as a promise the code keeps, not a guarantee the toolchain
checks.

### Available Data Structures

| Structure | Alias | Description | Advanced Features |
|-----------|-------|-------------|-------------------|
| **HashMap** | — | True hash map with O(1) average-case operations | `computeIfAbsent`, `computeIfPresent`, `filter`, `map`, `reduce`, `merge`, functional operations |
| **LinkedList** | **List** | Doubly-linked list with O(1) insertions at ends | `addFirst`, `addLast`, `removeFirst`, `removeLast`, `reverse`, bidirectional traversal |
| **Stack** | — | LIFO stack with O(1) push/pop operations | OOP dot-call style, toArray conversion, isEmpty check |
| **Queue** | — | FIFO queue with O(1) enqueue/dequeue operations | OOP dot-call style, peek, toArray conversion |
| **PriorityQueue** | — | Min-heap based priority queue | Automatic ordering, peek at minimum element |
| **Trie** | — | Prefix tree for efficient string operations | `startsWith`, `getAllWords`, prefix search, word count |

`List` is a built-in alias for `LinkedList` — `new List()` and `new LinkedList()` are identical.

### List (LinkedList)

A doubly-linked list. Import as `List` or `LinkedList` — they are the same structure.

```x
import System.utils.Collections.List

interface Student {
    string name;
    integer age;
    string major;
    float gpa;
}

function main() {
    let List<Student> students = new List<Student>()

    students.add({ name: "Alice", age: 20, major: "CS",   gpa: 3.9 })
    students.add({ name: "Bob",   age: 22, major: "Math", gpa: 3.5 })
    students.add({ name: "Carol", age: 21, major: "Data", gpa: 3.8 })

    print(students.size())        // 3
    print(students.getFirst().name)  // Alice
    print(students.getLast().name)   // Carol

    // for...in with range — index-based
    let Student[] arr = students.toArray()
    for (integer i in range(0, students.size())) {
        print(`[{i}] {arr[i].name}`)
    }

    // for...of — element-based
    for (Student s of arr) {
        print(s.name)
    }
}
```

**List / LinkedList Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `add` | `add(value)` | Adds to end |
| `addFirst` | `addFirst(value)` | Adds to beginning |
| `addLast` | `addLast(value)` | Adds to end (alias for `add`) |
| `remove` | `remove(value)` | Removes first occurrence |
| `removeFirst` | `removeFirst()` | Removes and returns first |
| `removeLast` | `removeLast()` | Removes and returns last |
| `get` | `get(index)` | Gets element at index |
| `getFirst` | `getFirst()` | Gets first element |
| `getLast` | `getLast()` | Gets last element |
| `size` | `size()` | Returns size |
| `isEmpty` | `isEmpty()` | Checks if empty |
| `clear` | `clear()` | Removes all elements |
| `contains` | `contains(value)` | Checks if value exists |
| `indexOf` | `indexOf(value)` | Returns index or -1 |
| `toArray` | `toArray()` | Converts to array |
| `reverse` | `reverse()` | Reverses in place |

### HashMap

The HashMap implementation provides a true hash map with advanced functional programming capabilities:

```x
import System.utils.Collections

// Create and use
let map = Collections.HashMap.create()

// Basic operations
Collections.HashMap.set(map, "name", "Alice")
Collections.HashMap.set(map, "age", 30)
print(Collections.HashMap.get(map, "name"))  // Alice
print(Collections.HashMap.has(map, "age"))   // true
print(Collections.HashMap.size(map))        // 2

// Advanced operations
print(Collections.HashMap.getOrDefault(map, "missing", "default"))

// Lazy initialization
let cache = Collections.HashMap.create()
function compute(string key) {
    return key.length * 10
}
let value = Collections.HashMap.computeIfAbsent(cache, "test", compute)

// Functional operations
function isLong(string[] entry) {
    return entry[0].length > 3
}
let filtered = Collections.HashMap.filter(map, isLong)

function uppercase(string[] entry) {
    return [entry[0].toUpperCase(), entry[1]]
}
let mapped = Collections.HashMap.map(map, uppercase)

function sum(int acc, string[] entry) {
    if (typeof entry[1] === "number") {
        return acc + entry[1]
    }
    return acc
}
let total = Collections.HashMap.reduce(map, 0, sum)
```

**Note:** You can also use the full path without importing:
```x
let map = System.utils.Collections.HashMap.create()
System.utils.Collections.HashMap.set(map, "key", "value")
```

**HashMap Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `create` | `create(capacity?)` | Creates a new HashMap (optional initial capacity) |
| `set` | `set(map, key, value)` | Sets a key-value pair |
| `get` | `get(map, key)` | Gets value by key (returns null if not found) |
| `has` | `has(map, key)` | Checks if key exists |
| `remove` | `remove(map, key)` | Removes and returns value by key |
| `size` | `size(map)` | Returns number of entries |
| `isEmpty` | `isEmpty(map)` | Checks if map is empty |
| `clear` | `clear(map)` | Removes all entries |
| `keys` | `keys(map)` | Returns array of all keys |
| `values` | `values(map)` | Returns array of all values |
| `entries` | `entries(map)` | Returns array of [key, value] pairs |
| `getOrDefault` | `getOrDefault(map, key, default)` | Gets value or default if not found |
| `computeIfAbsent` | `computeIfAbsent(map, key, function)` | Computes value if key absent |
| `computeIfPresent` | `computeIfPresent(map, key, function)` | Computes new value if key present |
| `merge` | `merge(map, otherMap, ...)` | Merges multiple maps |
| `filter` | `filter(map, predicate)` | Filters entries by predicate |
| `map` | `map(map, mapper)` | Transforms entries |
| `reduce` | `reduce(map, initial, reducer)` | Reduces entries to single value |
| `putAll` | `putAll(target, source)` | Copies all entries from source to target |

### LinkedList

### LinkedList / List

A doubly-linked list with efficient operations at both ends. `List` is a built-in alias — `new List()` and `new LinkedList()` are identical. See the **[List (LinkedList)](#list-linkedlist)** section above for the full OOP-style documentation and example with generics and `for` loop traversal.

Namespace style (also still works):

```x
import System.utils.Collections

let list = Collections.LinkedList.create()

// Add elements
Collections.LinkedList.add(list, "middle")
Collections.LinkedList.addFirst(list, "first")
Collections.LinkedList.addLast(list, "last")

// Access
print(Collections.LinkedList.getFirst(list))  // first
print(Collections.LinkedList.getLast(list))   // last
print(Collections.LinkedList.get(list, 1))    // middle

// Remove
Collections.LinkedList.remove(list, "middle")
let removed = Collections.LinkedList.removeFirst(list)

// Utility
print(Collections.LinkedList.size(list))
print(Collections.LinkedList.contains(list, "last"))
Collections.LinkedList.reverse(list)
print(Collections.LinkedList.toArray(list))
```

### Stack

LIFO (Last-In-First-Out) stack implementation.

```x
import System.utils.Collections.Stack

// OOP instance style (recommended)
let Stack<string> history = new Stack<string>()
history.push("first")
history.push("second")
history.push("third")

print(history.peek())    // third
print(history.pop())     // third
print(history.size())    // 2
print(history.isEmpty()) // false
history.clear()

// Namespace style still works
import System.utils.Collections
let stack = Collections.Stack.create()
Collections.Stack.push(stack, "item")
print(Collections.Stack.peek(stack))  // item
```

**Stack Methods (OOP dot-call):**

| Method | Description |
|--------|-------------|
| `push(value)` | Pushes value onto the top |
| `pop()` | Removes and returns top value |
| `peek()` | Returns top value without removing |
| `size()` | Returns stack size |
| `isEmpty()` | Returns true if empty |
| `clear()` | Removes all elements |
| `toArray()` | Returns all elements as an array |

### Queue

FIFO (First-In-First-Out) queue implementation.

```x
import System.utils.Collections.Queue

// OOP instance style
let Queue<string> q = new Queue<string>()
q.enqueue("first")
q.enqueue("second")
q.enqueue("third")

print(q.peek())     // first
print(q.dequeue())  // first
print(q.dequeue())  // second
print(q.size())     // 1
```

**Queue Methods (OOP dot-call):**

| Method | Description |
|--------|-------------|
| `enqueue(value)` | Adds value to the back |
| `dequeue()` | Removes and returns the front value |
| `peek()` | Returns front value without removing |
| `size()` | Returns queue size |
| `isEmpty()` | Returns true if empty |
| `clear()` | Removes all elements |
| `toArray()` | Returns all elements as an array |
| `clear` | `clear(queue)` | Clears queue |
| `toArray` | `toArray(queue)` | Converts to array |

### PriorityQueue

Min-heap based priority queue (smallest element has highest priority):

```x
import System.utils.Collections

let pq = Collections.PriorityQueue.create()

Collections.PriorityQueue.enqueue(pq, 5)
Collections.PriorityQueue.enqueue(pq, 2)
Collections.PriorityQueue.enqueue(pq, 8)

print(Collections.PriorityQueue.peek(pq))     // 2
print(Collections.PriorityQueue.dequeue(pq))  // 2
print(Collections.PriorityQueue.dequeue(pq))  // 5
```

**PriorityQueue Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `create` | `create(comparator?)` | Creates a new PriorityQueue |
| `enqueue` | `enqueue(pq, value)` | Adds value (maintains order) |
| `dequeue` | `dequeue(pq)` | Removes and returns minimum |
| `peek` | `peek(pq)` | Returns minimum without removing |
| `size` | `size(pq)` | Returns queue size |
| `isEmpty` | `isEmpty(pq)` | Checks if empty |
| `clear` | `clear(pq)` | Clears queue |
| `toArray` | `toArray(pq)` | Converts to array |

### Trie

Prefix tree for efficient string operations:

```x
import System.utils.Collections

let trie = Collections.Trie.create()

Collections.Trie.insert(trie, "hello")
Collections.Trie.insert(trie, "world")
Collections.Trie.insert(trie, "hey")

print(Collections.Trie.search(trie, "hello"))     // true
print(Collections.Trie.search(trie, "hel"))        // false
print(Collections.Trie.startsWith(trie, "he"))    // true
print(Collections.Trie.getAllWords(trie))         // [hello, hey, world]
print(Collections.Trie.size(trie))                 // 3

Collections.Trie.remove(trie, "hey")
print(Collections.Trie.size(trie))                 // 2
```

**Trie Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `create` | `create()` | Creates a new Trie |
| `insert` | `insert(trie, word)` | Inserts a word |
| `search` | `search(trie, word)` | Checks if exact word exists |
| `startsWith` | `startsWith(trie, prefix)` | Checks if any word starts with prefix |
| `remove` | `remove(trie, word)` | Removes a word |
| `size` | `size(trie)` | Returns word count |
| `isEmpty` | `isEmpty(trie)` | Checks if empty |
| `clear` | `clear(trie)` | Clears all words |
| `getAllWords` | `getAllWords(trie)` | Returns all words |

### Running DSA Tests

Comprehensive test suites are available in the `examples/dsa_tests` directory:

```sh
# Run all DSA tests
x run examples/dsa_tests/all_tests.x

# Run individual structure tests
x run examples/dsa_tests/hashmap_test.x
x run examples/dsa_tests/linkedlist_test.x
x run examples/dsa_tests/stack_test.x
x run examples/dsa_tests/queue_test.x
x run examples/dsa_tests/priorityqueue_test.x
x run examples/dsa_tests/trie_test.x
```

### Collections Implementation Status

This checklist covers both what is implemented and what remains. Items added or fixed in the current session are marked **[new]**.

#### Core API styles **[new]** ✅
- [x] OOP instance style — `new Stack()` returns an instance; methods called as `stack.push(x)`
- [x] Inline import — `import System.utils.Collections.Stack` binds `Stack` directly
- [x] Namespace import — `import System.utils.Collections` then `Collections.Stack.create()`
- [x] Full path without import — `System.utils.Collections.Stack.create()` always works
- [x] `List` as a built-in alias for `LinkedList` — `new List()` and `new LinkedList()` are identical
- [x] Generic type annotations — `let List<Student> students = new List<Student>()` (hint only, not statically enforced yet)
- [x] Short names globally available — `Stack`, `Queue`, `HashMap`, `LinkedList`, `List`, `PriorityQueue`, `Trie` without any import
- [x] Re-importing an already-bound name does not crash — `import System.utils.Collections.Stack` is safe even when `Stack` is already in scope

#### HashMap ✅
- [x] Basic CRUD — `create`, `set`, `get`, `has`, `remove`
- [x] O(1) average-case get/set
- [x] String, number, and boolean key support
- [x] `getOrDefault` — safe access with fallback
- [x] `computeIfAbsent` — lazy initialization
- [x] `computeIfPresent` — conditional update
- [x] Functional operations — `filter`, `map`, `reduce`
- [x] `merge` — combine multiple maps **[fixed: now accepts XCollectionInstance]**
- [x] `putAll` — bulk copy from another map **[fixed: now accepts XCollectionInstance]**
- [x] `keys`, `values`, `entries` views
- [x] `size`, `isEmpty`, `clear`
- [x] Callbacks passed as X functions work correctly **[fixed: list[XFunction] normalized to OverloadedFunction]**

#### LinkedList / List ✅
- [x] OOP dot-call style — `list.add(x)`, `list.getFirst()`, `list.size()` **[new]**
- [x] O(1) insertions at both ends — `addFirst`, `addLast`
- [x] O(1) removals at both ends — `removeFirst`, `removeLast`
- [x] Random access by index — `get(index)`
- [x] Bidirectional access — `getFirst`, `getLast`
- [x] Contains and indexOf
- [x] Reverse in place
- [x] `toArray` conversion
- [x] `clear`
- [x] Create from initial array — `new List([1, 2, 3])`
- [ ] Iterator protocol (for…of directly on instance without `.toArray()` first)

#### Stack ✅
- [x] OOP dot-call style — `stack.push(x)`, `stack.pop()`, `stack.peek()` **[new]**
- [x] O(1) push and pop
- [x] Peek without removal
- [x] `size`, `isEmpty`, `clear`
- [x] `toArray`
- [x] Create from initial array
- [ ] Iterator protocol (for…of directly on instance)

#### Queue ✅
- [x] OOP dot-call style — `queue.enqueue(x)`, `queue.dequeue()` **[new]**
- [x] O(1) enqueue and dequeue
- [x] Peek without removal
- [x] `size`, `isEmpty`, `clear`
- [x] `toArray`
- [x] Create from initial array
- [ ] Iterator protocol (for…of directly on instance)

#### PriorityQueue ✅
- [x] OOP dot-call style **[new]**
- [x] Automatic ordering (min-heap via sort)
- [x] Peek at minimum element
- [x] `size`, `isEmpty`, `clear`, `toArray`
- [ ] True O(log n) binary heap — current implementation uses `list.sort()`, giving O(n log n) enqueue
- [ ] Custom comparator support
- [ ] Max-heap option

#### Trie ✅
- [x] OOP dot-call style **[new]**
- [x] O(k) insert/search (k = word length)
- [x] Exact word search
- [x] Prefix search — `startsWith`
- [x] Get all words
- [x] Remove
- [x] `size`, `isEmpty`, `clear`
- [x] Inline import — `import System.utils.Collections.Trie` **[fixed: no longer crashes on re-declaration]**
- [ ] Wildcard / regex search
- [ ] `getWordsWithPrefix(prefix)` — return only words starting with a given prefix

### Known Bugs Fixed This Session

| Bug | Status |
|-----|--------|
| Interpreter crashed on startup — `_create_wrapper_class` called `VariableDeclaration` with wrong arg count | ✅ Fixed |
| `Stack.create()` / bare short names undefined without import | ✅ Fixed — short names defined globally at startup |
| `import System.utils.Collections.Stack` caused "already declared" error | ✅ Fixed — re-import silently re-binds |
| `new Stack()` returned a raw list, not a callable instance | ✅ Fixed — returns `XCollectionInstance` with bound methods |
| `students.add(x)` style (OOP dot-call) not supported | ✅ Fixed — `_get_member` dispatches on `XCollectionInstance` |
| `HashMap.merge` / `putAll` rejected `XCollectionInstance` args | ✅ Fixed — `_unwrap_collection` normalizes before type check |
| `HashMap.computeIfAbsent/filter/map/reduce` rejected X function callbacks | ✅ Fixed — `_normalize_callable` wraps `list[XFunction]` into `OverloadedFunction` |
| `hashmap_test.x` used `typeof` (JS) instead of `typeOf` (X) | ✅ Fixed in test file |

### Remaining Work (Collections)

- [ ] **Iterator protocol** — `for (Student s of students)` should work directly on an instance without calling `.toArray()` first
- [ ] **True binary heap** for PriorityQueue — current sort-based approach is O(n log n) per enqueue
- [ ] **Custom comparator** for PriorityQueue — `new PriorityQueue((a, b) => a.priority - b.priority)`
- [ ] **Max-heap** option for PriorityQueue
- [ ] **Static type enforcement** for generics — `List<Student>` currently accepts any value
- [ ] **`new StructureName(initialArray)`** — constructing with data e.g. `new Stack([1,2,3])` works; `new List(existingArray)` also works; document clearly
- [ ] **Set** data structure — unique-value collection
- [ ] **TreeMap / TreeSet** — sorted key ordering
- [ ] **LinkedHashMap** — insertion-order preserving map
- [ ] **LRU Cache** — built on top of LinkedHashMap
- [ ] **Thread-safe wrappers** — concurrent access guards
- [ ] **Immutable/frozen variants**
- [ ] **Serialization** — `toJSON()` / `fromJSON()` round-trip
- [ ] **`groupBy` / `partition`** functional operators on List
- [ ] **Graph** — adjacency list and matrix representations
- [ ] **BST / AVL / Red-Black tree**
- [ ] **Union-Find (Disjoint Set)**
- [ ] **Bloom Filter**

## Asynchronous functions and threads

### Async/await

Import the asynchronous helpers and mark async functions with `async`:

```x
import System.concurrent.Async

async function loadName(string name, integer delayMilliseconds) {
    await Async.delay(delayMilliseconds);
    return name;
}

async function main() {
    let string[] names = await Async.all([
        loadName("Ada", 30),
        loadName("Grace", 10)
    ]);

    for (string name in names) {
        print(name);
    }
}
```

An async function call returns an awaitable result. `Async.all` starts the
provided awaitable operations concurrently and returns their results in input
order. `await` is valid only inside an `async` function and requires an
asynchronous operation; awaiting an ordinary value is an error. The built-in
`sleep(milliseconds)` returns an asynchronous operation that waits for the
specified non-negative number of milliseconds. Its API is:

| Method | Signature | Behavior |
| --- | --- | --- |
| `delay` | `delay(milliseconds, result?)` | Accepts a non-negative integer/float duration; resolves to the optional result, or `null`. |
| `all` | `all(operations)` | Accepts one array of values/awaitables; waits for every awaitable and returns results in input order. |
| `sleep` | `sleep(milliseconds)` | Waits asynchronously for the specified non-negative integer/float duration. |

An `async main` is awaited by the interpreter. Async function bodies execute on
Python worker threads because the current language interpreter evaluates
statements synchronously; each `await` suspends that body while the awaited
operation runs. This provides overlapping I/O-style work for awaitable
operations, but is an experimental prototype rather than TypeScript-compatible
Promise scheduling. CPU-heavy X code is not made faster by `async`.

### OS threads

Use `System.concurrent.Thread` to start an X function on a real operating
system thread:

```x
import System.concurrent.Thread

integer function add(integer left, integer right) {
    return left + right;
}

function main() {
    let ThreadHandle worker = Thread.start(add, [20, 22]);
    print(worker.join());
}
```

- `Thread.start(function, arguments?)` starts the function immediately. The
  optional second argument is an array; when omitted, the function receives no
  arguments.
- `worker.join()` waits until completion and returns the function result.
  `worker.join(timeoutSeconds)` waits at most that long and returns `null` if
  the worker is still running.
- `worker.isAlive()` reports whether the worker is currently running.
- A worker failure is reported when `join` is called after it has completed.

X threads share the same interpreter and object values. The prototype does not
provide locks, atomics, or thread-safe collection guarantees. Coordinate shared
mutable state yourself; prefer returning results and collecting them through
`join`.

## Function arguments

### Rest parameters

The X parameter convention places types before names, so rest parameters are
written as `Type ...name`. A rest parameter must be the final parameter and is
available inside the function as an array:

```x
integer function sum(integer ...values) {
    let integer total = 0;
    for (integer value in values) {
        total += value;
    }
    return total;
}
```

### Optional parameters

Parameters can also be optional by using a default value or a nullable type.
Default expressions are evaluated when the argument is omitted, in the
function's parameter scope, so they can refer to earlier parameters:

```x
User function getUsers(string id = "10001") {
    return User(id);
}

User? function findUser(string? id) {
    if (id == null) {
        return null;
    }
    return User(id);
}

getUsers();       // uses "10001"
getUsers("20002"); // uses "20002"
findUser();       // receives null
findUser("30003");
```

Required parameters must come before optional parameters. A nullable parameter
without a default may be omitted and receives `null`; a parameter with a
default uses that value when omitted.

### General error handling

For unknown failures, a broad catch can inspect the concrete exception name:

```x
try {
    performOperation();
}
catch (Throwable error) {
    print(error.name + ": " + error.message);
}
```

Uncaught division by zero is reported as
`Cannot divide by zero: Division by zero for '/'`.

### Spread values

Spread expands iterable values in array literals and function calls. Object
spread copies fields from an object value; later fields override earlier ones:

```x
let integer[] first = [1, 2];
let integer[] all = [0, ...first, 3];
print(sum(...all));

let object defaults = {name: "Ada", role: "Engineer"};
let object profile = {...defaults, role: "Architect"};
```

Typed arrays validate their elements when initialized or passed to a typed
parameter. Their element type is also enforced by indexed writes and `add()`;
for example, `integer[] values = [1, 2, "name"]` reports the invalid string.

## Strings, templates, and print

Single- and double-quoted strings remain single-line strings. Backticks create
multiline template literals. Interpolations contain X expressions, including
calls and arithmetic; calls are evaluated from left to right. Double braces
(`{{` and `}}`) produce literal braces. Interpolation is expression-based, so
it does not accept statement blocks.

`print` accepts zero or more comma-separated expressions. Each argument is
stringified and joined with one space; `+` concatenates values within an
argument:

```x
let string name = "Maya";
print("My Name " + "is", name); // My Name is Maya
print(`Hello {name}, the result is {1 + 2}.`);
print(`A multiline template:
line two has {name}.`);
```

Run the complete example with:

```sh
x run examples/templates_and_print.x
```

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

### HTTP fetch demo

```sh
x run examples/fetch_demo.x
```

The demo awaits `fetch("https://example.com/")` with a custom `userAgent`
and prints the status, content type, and body size. When the network is
unavailable the same program reports the `HttpException` and still runs its
`finally` block — see [HTTP client](#http-client-systemionetworkhttp).

### Object-oriented, rest/spread, async, and threading demos

```sh
x run examples/oop_demo.x
x run examples/rest_spread_demo.x
x run examples/async_demo.x
x run examples/thread_demo.x
```

These examples demonstrate `new`, overloaded constructor dispatch, explicit
`super` calls, rest/spread parameters and values, concurrent `Async.all`, and
OS thread creation and joining.

## Interpreter architecture

The execution pipeline is:

```text
CLI arguments and x.toml
  -> configuration validates feature switches and run profiles
  -> ModuleLoader resolves project imports and built-in modules
  -> Lexer produces positioned tokens
  -> Parser produces AST declarations, statements, and expressions
  -> Interpreter registers functions, classes, and enums in environments
  -> Evaluator executes statements and expressions
  -> Runtime values enforce class access rules and model functions, classes,
     instances, enums, and threads
  -> diagnostics render source locations and caret excerpts on failure
```

Configuration parsing and feature defaults live in `xlang/config.py`; terminal
diagnostics live in `xlang/diagnostics.py`. The AST is defined in
`xlang/ast_nodes.py`; tokenization and grammar parsing
live in `xlang/lexer.py` and `xlang/parser.py`; import resolution lives in
`xlang/module_loader.py`; evaluation and built-ins live in
`xlang/runtime.py`; command handling lives in `xlang/cli.py`.

Runtime scopes are chained `Environment` objects. Namespace and class scopes
are nested environments, allowing qualified access such as `App.Models.User`
and `Container.Item`. Function calls create a new
scope whose parent is the function's defining environment, implementing
lexical name lookup. Class construction allocates an instance, initializes
parent fields before child fields, then selects and invokes the matching
constructor. A derived constructor calls `super(arguments...)` explicitly to
run a parent constructor. `super.method()` resolves to a parent implementation.

The synchronous evaluator is the common execution engine. Async X functions
produce Python awaitables; the runtime uses `asyncio` for delays and
`Async.all`, and dispatches their synchronous statement execution through
Python's worker-thread executor. `Thread.start` instead creates a dedicated
`threading.Thread` handle. Both concurrency APIs are prototype runtime
facilities, not a static concurrency or memory-safety model.

## Tests

Run the interpreter tests from the project root:

```sh
python -m unittest discover -s tests -v
```

The tests cover parsing and execution of core syntax, functions, classes,
access control, final classes, decorators, nested types, namespaces,
exceptions, all loop forms, pattern matching, destructuring, ASI, equality,
objects, project configuration and feature flags, source diagnostics and
type diagnostics, string indexing, grouped project imports, filesystem
operations, rest/spread, async/await, and OS threads.

## Feature examples

Runnable feature examples are organized by topic:

```text
examples/
├── configuration/configured_args.x
├── control_flow/main.x
├── control_flow/main_file.x
├── decorators/trace.x
├── exceptions/try_catch_finally.x
├── namespaces/nested_classes.x
├── objects/destructuring.x
└── pattern_matching/match.x
```

For example:

```sh
x run examples/control_flow/main_file.x
x run examples/decorators/trace.x
x run examples/exceptions/try_catch_finally.x
x run examples/filesystem_async_demo.x
x run examples/namespaces/nested_classes.x
x run examples/objects/destructuring.x
x run examples/pattern_matching/match.x
x run --profile feature-tour examples/configuration/configured_args.x
```

The [`examples/dsa/`](./examples/dsa/README.md) folder contains 20 standalone
algorithm demonstrations grouped by common interview patterns, including
sliding windows, two pointers, binary search, stacks, recursion, matrix
traversal, and string encoding. Each `.x` file can be run independently.

`Object` currently operates on X object literals and dictionaries. Object
literals support identifier/string keys, shorthand properties, and spread;
computed keys, symbols, prototypes, getters/setters, and anonymous methods are
not implemented. Destructuring supports nested array/object bindings, defaults
in declarations, rest bindings, and variable-target assignment. It does not yet
support computed property targets or every JavaScript destructuring edge case.
ASI is statement-boundary insertion, not a complete ECMAScript parser rule
engine; semicolons remain necessary in classic `for` headers, and ambiguous
leading `[`/`(` continuations should be explicitly separated.

## Access control, final classes, and error reporting

Access modifiers are enforced by the type checker and the interpreter, not
just recorded as documentation. Members with no access modifier default to
public. Private and protected reads, writes, method lookups, and static
members follow the class rules above. `internal` is rejected because this
prototype does not yet have isolated module boundaries.

`final class` is checked when classes are registered; extending one fails
before `main` runs. Lexer, parser, type, runtime, and TOML configuration
errors use source-aware terminal diagnostics with file, line, column, the
relevant source line, and a caret, and type errors can add `= note:` and
`= help:` lines as shown above. Color is automatic for interactive terminals;
use `--color always`, `--color never`, or `NO_COLOR` to control it.

The following examples are deliberately invalid and demonstrate failure
output (`private_access.x`, `final_class_extension.x`, and `runtime_error.x`
are now rejected as type errors before the program starts):

```sh
x run examples/errors/private_access.x
x run examples/errors/final_class_extension.x
x run examples/errors/runtime_error.x
x check examples/errors/syntax_error.x
x check examples/errors/typed_array.x
```

## DSA examples and computational expressiveness

I’ve tried solving 20 data-structures-and-algorithms problems in X to show how
the language’s functions, loops, conditionals, arrays, objects, recursion, and
mutable state work together on practical problems. The collection includes
the longest substring without repeating characters, Container With Most
Water, and run-length encoding/decoding (`aaab` to `a3b`).

Browse the [DSA examples and pattern guide](./examples/dsa/README.md), then
run an individual problem from the repository root, for example:

```sh
x run examples/dsa/05_longest_unique_substring.x
x run examples/dsa/07_container_most_water.x
x run examples/dsa/20_run_length_codec.x
```

These programs are a hands-on demonstration of X's general-purpose
computational expressiveness and its Turing-completeness goal; the examples
themselves are not a formal proof of Turing completeness. The current Python
interpreter remains subject to practical memory, recursion, and execution-time
limits.

Strings are indexable and expose `.length`. Indexing follows Python sequence
semantics: indices count Unicode code points, negative indices count backward
from the end, and an out-of-range index reports a runtime error. It does not
count grapheme clusters, and this differs from JavaScript's UTF-16 code-unit
indexing for some characters.

## Current limitations

The specification includes features beyond this prototype. These are the
remaining implementation goals and documented constraints:

### Language / Compiler

- [ ] Native or bytecode compilation — `build` validates syntax, imports, and
  types, then reports that no executable was produced
- [ ] Generic type checking and type-parameter substitution — generic
  annotations parse and their type names are checked, but element types are
  not enforced (`List<string>` in a `List<integer>` slot passes `x check`)
- [ ] Union/nullable type semantics — `integer | null` does not exist and
  `null` is rejected for non-null types; inline `record{...}` annotations are
  checked structurally today
- [ ] Independent module namespaces — imports are resolved but declarations are not isolated behind module namespace objects
- [ ] Thread-safe collections, locks, atomics, cancellation, and full Promise-style async compatibility
- [ ] A broader standard library beyond the built-ins documented here

### Collections (see full list in [Collections Implementation Status](#collections-implementation-status))

- [ ] Iterator protocol — `for (T item of collectionInstance)` without `.toArray()` first
- [ ] True O(log n) binary heap for PriorityQueue
- [ ] Custom comparator and max-heap for PriorityQueue
- [ ] Set, TreeMap/TreeSet, LinkedHashMap, LRU Cache
- [ ] Thread-safe collection wrappers
- [ ] Serialization round-trip (`toJSON` / `fromJSON`)

### Known correctness edges

- `/` performs floating-point division — code needing an integer index must ensure the calculation is integral
- String indexing counts Unicode code points, not grapheme clusters or UTF-16 code units
- Parser recovery reports multiple recoverable errors but malformed constructs can prevent discovery of later errors; runtime failures stop at the first failure
- Recursive algorithms (flood fill, deep trees) can hit Python's default recursion limit on large inputs
- The run-length codec example is intended for letter-only input, not a general-purpose escaping format

The detailed syntax proposal is in [Draft.md](./Draft.md). Where the interpreter
behavior is narrower than that draft, this README describes what can currently
be relied upon.

## Editor support (VS Code)

A bundled extension in [`vscode-xlang/`](./vscode-xlang/) provides syntax
highlighting, real-time type checking, completions, hover and go-to-definition
for `.x` files. It is installed as `xlang.xlang@0.1.0` and activates
automatically when you open any `.x` file — no manual step, and nothing to
re-do after a reboot.

Editor diagnostics are produced by the same `Lexer` → `Parser` →
`TypeChecker` pipeline used by `x check`, and the server reads `x.toml` the
same way, so the squiggles in the editor and the command-line output match.
The checker also rejects a value returned from a `void` function or method —
previously that slipped through.

Go-to-definition (Ctrl+Click / F12) resolves functions, methods,
constructors, parameters, fields, variables and enum members inside the
current file, not just type names.

See **[`vscode-xlang/README.md`](./vscode-xlang/README.md)** for the full
report: architecture, every defect that was fixed, what was installed where,
how to rebuild it, and the current limitations (go-to-definition is
single-file only and does no scope analysis).
