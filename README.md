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
x --config path/to/x.toml --feature async=off check path/to/main.x
x run --profile development path/to/main.x -- --verbose "value with spaces"
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
- The process exit code is taken from an integer returned by `main`; a `void`
  or inferred-void `main` returns success.

## Project configuration

The CLI discovers `x.toml` in the current directory by default. Pass
`--config path/to/file.toml` to select another file, or `--no-config` to
disable discovery. Command-line `--feature NAME=on|off` settings override
feature values in TOML. The supported features are `async`, `classes`,
`decorators`, `destructuring`, `enums`, `equality`, `exceptions`, `filesystem`,
`loops`, `namespaces`, `object_literals`, `pattern_matching`, `spread`, and
`threads`. All default to enabled.

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
  Interface-typed values are checked structurally at runtime; a method must
  exist with a compatible signature and fields must satisfy their declared
  types. This is runtime validation, not a static type checker.
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
- [x] The `System.io.FileSystem`, `System.Environment`, and `System.concurrent`
  modules described below.

The interpreter executes code dynamically. It does **not** yet provide the
specification's promised static type checker; declared types are primarily
syntax and overload-resolution hints at runtime.

### Source diagnostics

Lexical errors identify invalid characters (for example,
`Unexpected character '$'`). Syntax errors identify tokens that cannot appear
in the current grammar position (for example,
`Unexpected token ')'; expected an expression`). The CLI prints each
recoverable source diagnostic with its own file location and excerpt, then
exits unsuccessfully without running the program. Runtime failures still stop
execution at the point of failure.

Run `x check examples/errors/syntax_error.x` to see an unexpected-token
diagnostic. The invalid `;` after `=` is a valid character, but it is not a
valid expression token; by contrast, a character such as `$` is reported by
the lexer as an unexpected character.

## Runtime types and typed objects

`typeOf(value)` is a built-in and needs no import. It returns JavaScript-style
runtime type names: `"string"`, `"number"` for both integers and floats,
`"boolean"`, `"function"` for X functions and classes, and `"object"` for
object literals, arrays, class instances, enums, `null`, and `undefined`.
Both `null`/`Null` and `undefined`/`Undefined` are accepted literal spellings.
Optional access that finds no value produces `undefined`, so
`typeOf(profile[0]?.x)` returns `"object"` while printing that value displays
`undefined`. `typeOf` requires exactly one argument.

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
variable named `object` annotated with type `profile`. Unknown non-generic
annotations are not yet consistently validated because X does not have its
static type checker yet; use the type-before-name order shown here.
For a dictionary whose keys and values are both strings, write
`let object<string, string> user = ...`; the key and value types are checked
when the value is created or assigned, passed to a typed parameter, or
mutated. This generic object type describes key/value types, not a fixed set
of named properties. X does not currently support TypeScript's
`let user: object<string, string>` annotation syntax or compile-time type
checking.

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
    │   └── FileSystemException
    └── DatabaseException
```

Catch a specific type first, then a parent type. `catch (Throwable error)` is
the broad fallback; `catch (Exception error)` catches checked and runtime
exceptions, while `Error` is a separate branch. Catch variables provide
`name`, `message`, `cause`, and `stack` properties. `stack` currently reports
the source location where the error was raised. Errors can preserve a cause:

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
`Exception`, or `Throwable`. See the runnable
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
objects, project configuration and feature flags, source diagnostics, string
indexing, grouped project imports, filesystem operations, rest/spread,
async/await, and OS threads.

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

Access modifiers are enforced by the interpreter, not just recorded as
documentation. Members with no access modifier default to public. Private and
protected reads, writes, method lookups, and static members follow the class
rules above. `internal` is rejected because this prototype does not yet have
isolated module boundaries.

`final class` is checked when classes are registered; extending one fails
before `main` runs. Lexer, parser, runtime, and TOML configuration errors use
source-aware terminal diagnostics with file, line, column, the relevant source
line, and a caret. Color is automatic for interactive terminals; use
`--color always`, `--color never`, or `NO_COLOR` to control it.

The following examples are deliberately invalid and demonstrate failure output:

```sh
x run examples/errors/private_access.x
x run examples/errors/final_class_extension.x
x run examples/errors/runtime_error.x
x check examples/errors/syntax_error.x
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

- [ ] Static type checking, definite assignment, and compile-time type diagnostics.
- [ ] Native or bytecode compilation; `build` is currently a syntax/import check.
- [ ] Interfaces as enforceable contracts and abstract-method validation.
- [ ] Generic type checking and type-parameter substitution.
- [ ] Union/nullable type semantics, structural type validation, and records.
- [ ] Independent module namespaces; imports are resolved, but declarations
  are not isolated behind module namespace objects.
- [ ] Thread-safe collections, locks, atomics, cancellation, and full TypeScript
  Promise compatibility.
- [ ] A broader standard library beyond the built-ins documented here.

Known limitations and correctness edges (not an exhaustive bug tracker):

- `/` currently performs floating-point division, so code needing an integer
  index must ensure the calculation is integral. The DSA binary-search
  examples use a logarithmic binary-lifting variant for that reason.
- String indexing counts Unicode code points, not grapheme clusters or
  JavaScript UTF-16 code units.
- Parser recovery reports multiple recoverable lexical and syntax errors, but
  malformed constructs can prevent discovery of later errors. Runtime
  failures stop execution at the first failure.
- Recursive algorithms such as flood fill can hit Python's recursion limit on
  sufficiently large inputs.
- The run-length codec example reserves digits for run counts and is intended
  for letter-only input; it is an instructional example, not a general-purpose
  escaping format.

The detailed syntax proposal remains in [Draft.md](./Draft.md). Where the
interpreter behavior is narrower than that draft, this README describes the
features that can currently be relied upon.
