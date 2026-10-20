# X Language project

This project is an experimental Python interpreter for **X Language
Specification Draft 0.1**. It is intended as a working language prototype and
learning project, not as a production compiler. The implementation requires
Python 3.10 or newer. Python 3.11+ uses the standard-library TOML reader;
Python 3.10 installs the small `tomli` compatibility dependency.

The documentation site is published at
<https://thisismayuresh.github.io/x-lang/>, including the
**[browser playground](https://thisismayuresh.github.io/x-lang/playground.html)**
— it runs this interpreter compiled to WebAssembly through Pyodide, so you can
try X without installing anything.

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
x format path/to/main.x
x compile path/to/main.x --target typescript --out dist/main.ts
x --watch format path/to/main.x
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
- `compile` type-checks the program like `check`, then emits a TypeScript
  translation of the entry file and its imports. It runs after type-checking
  succeeds, so type errors abort compilation before any output is written. The
  target language defaults to `typescript` (currently the only supported
  target); the output path defaults to the source file's name with a `.ts`
  extension. Both can be overridden with `--target`/`--out` flags or the
  `[compile]` table in `x.toml` (see below). Missing output directories are
  created automatically.
- `format` rewrites the source file in place with canonical formatting
  (implemented by `xlang/formatter.py`): two-space indentation, normalized
  spacing around operators and commas, `if`/`else` and `try`/`catch` kept on
  one line, one statement per line, comments and string literals preserved
  verbatim, and at most one blank line between statements. Object literals
  that do not fit in 80 columns are broken one `key: value` field per line
  with a trailing comma; match-arm patterns are never broken. Formatting is
  idempotent; a file that is already formatted is left untouched. Files with
  syntax errors are diagnosed instead of rewritten.
- `-w`/`--watch` (also spelled `-watch`) runs the command once and re-runs it
  whenever the entry file, one of its imported files, or `x.toml` changes;
  press Ctrl+C to stop. Errors keep the watcher alive, so saving a fix
  triggers the next run. Watch mode works with `run`, `check`, `build`,
  `compile`, and `format` and must appear before the source file. Combined
  with `format` (`x --watch format file.x`), the file is automatically
  reformatted every time you save it while typing.
- Commands listed in the `[scripts]` table of `x.toml` run with `x <name>`,
  similar to `pnpm start` and package.json scripts.
- The process exit code is taken from an integer returned by `main`; a `void`
  or inferred-void `main` returns success. `System.process.exit(code)` stops
  immediately with that status from anywhere — in the REPL, `exit(code)` and
  `quit(code)` do the same. Inside a thread the exit takes effect when the
  thread handle is joined.

## Project configuration

The CLI discovers `x.toml` in the current directory by default, falling back
to the source file's directory when the current directory has none. Pass
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
default to disabled. `primitive_aliases` is also off by default; enabling it
makes built-in type spellings case-insensitive (`String` → `string`).

### Turning language features on and off

Feature flags are a core part of the language: every optional syntax and
standard-library area is gated by a boolean in `[features]`, so a project can
restrict itself to exactly the subset it needs. Disabling a feature makes its
syntax a **compile-time** diagnostic, reported before any statement executes.

```toml
[features]
classes = false
pattern_matching = false
primitive_aliases = true
```

Resolution runs in three layers, later ones winning:

1. **Interpreter defaults**: most features are on; the experimental
   `url_imports`, `package_manager` and `strict_typing` are off, as is
   `primitive_aliases`.
2. **`[features]` in `x.toml`**, discovered upward from the working directory
   (or the source file's directory), overrides those defaults.
3. **`--feature NAME=on|off`** on the command line overrides TOML. Repeat the
   flag for several features; it applies to `run`, `check`, `build`, `repl`,
   and `format`.

Values must be TOML booleans (`true` / `false`). An unknown feature name
fails with the list of supported features, and a program that uses a disabled
feature is stopped with a diagnostic naming the feature:

```text
error: Language feature 'classes' is disabled in x.toml
 --> main.x:1:1
  |
1 | class Point {
  | ^^^^^ Language feature 'classes' is disabled in x.toml
```

`--no-config` ignores `x.toml` entirely (defaults only) and
`--config path/to/file.toml` selects a specific file, so a single project can
keep several feature profiles.

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

[compile]
target = "typescript"
out = "dist/main.ts"
```

`[run].args` are passed to the program first, followed by profile arguments
and then any CLI arguments. Use `--` to mark the end of X CLI options and begin
program arguments. Each TOML array entry remains one argument; spaces are not
split. Environment values from the operating system are overlaid by
`[run].environment`, then by the selected profile. X code can read a value
directly as `System.process.Environment.APP_MODE`; the built-in `System` namespace is
available without an import. `System.process.Environment.has("APP_MODE")` and
`System.process.Environment.all()` are also available. Configured environment values
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
(`run`, `check`, `build`, `compile`, `install`). `--watch` cannot be combined
with scripts because a shell command does not expose the files it depends on.

`[compile]` sets the defaults for the `compile` command. Both keys are
optional strings: `target` selects the output language (currently only
`"typescript"`) and `out` sets the output file path (relative to the current
directory). The `--target` and `--out` command-line flags override these
values; when neither is provided, the target falls back to `"typescript"` and
the output to the source file's name with a `.ts` extension. An unknown
target or an invalid key in `[compile]` is a configuration error reported
before compilation begins.

The CLI also loads a project-root `.env` file when running a program. Copy the
safe demo values in [.env.example](./.env.example) to `.env`, then run the
configuration example:

```sh
cp .env.example .env
x run examples/configuration/configured_args.x
```

Read values directly as `System.process.Environment.VARIABLE_NAME`; no import or
`get()` call is needed. `.env` assignments support `KEY=VALUE`, optional
`export`, blank lines, full-line comments, and single- or double-quoted values.
The file is not loaded for `check` or `build`. When the script lives outside
the config root, `x run` also reads a `.env` next to the script, and those
values win over the project-root file; `x repl` loads the same files for the
session. Existing operating-system
variables take precedence over matching `.env` values; TOML run environment
settings and then the selected profile override both. `.env` is ignored by
Git, so keep credentials and machine-specific values there, never in the
tracked example.

An explicit subcommand (`run`, `check`, `build`, or `compile`) always wins.
The `[cli].default-command` setting applies to the shorthand `x file.x` form.
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
  `int` as an alias for `integer` (built-in type spellings are case-sensitive;
  the optional `primitive_aliases` feature makes them case-insensitive),
  array literals/indexing, JavaScript-like
  object literals, array/object destructuring declarations and assignments,
  defaults, rest properties, and object spread.
- [x] `delete(target)` removes an object key *and* its value, splices out an
  array element (the array gets shorter), or drops a class-instance field.
  It is declared in Python as `Object.delete`, is available unqualified with
  no import, returns `true`, and reports a target that is not there with the
  same error reading it would raise.
- [x] Standalone functions, typed parameters, inferred/explicit return types,
  first-class function references, generic declaration/call syntax, and
  overload resolution by argument count and runtime value types. Generic
  `object<K, V>` annotations validate dictionary key/value types at runtime
  and in `x check`, where an object literal is checked key by key and an
  unknown key names the key, lists the allowed keys, and points at the entry.
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
  function or class by returning the target they receive. The accepted forms
  and how to write your own are documented in
  [Decorators](#decorators).
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
  string-literal union type aliases (`type SettingsKey = "theme" | "backup";`)
  with value checking, the TypeScript-style colon annotation
  (`let n: integer = 1;`), array `.push(...)`, an `export` prefix on
  declarations (`export type`, `export const`, `export let`, `export function`,
  `export class`, `export enum`), bulk `export { ... };` lists, and typed
  `input()` validation when `enhanced_input` is enabled.
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
- [x] Project-relative named imports, grouped imports, wildcard imports,
  import aliases, and calling an imported function from the import itself.
- [x] The `System.io` modules (Console, FileSystem, and the awaitable
  `Network.http` `fetch`), `System.process.Environment`, `System.concurrent`, and
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
the lexer as an unexpected character. Contextual keywords are checked the
same way: a `return` outside any function body (for example at the top level
or inside a top-level loop) is a parse error —
`'return' is only valid inside a function` — in the same family as
`'await' is only valid inside an async function`.

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

When the target is an interface or a record annotation, the notes name
exactly what does not line up instead of only showing the two types: each
missing member is listed (``= note: missing required member `age: integer` ``,
``= note: missing required method `greet()` ``) and each mismatched one
(``member `name`: expected `string`, found `integer` ``). This applies to
returns, variable initialisers, and call arguments alike.

`x check` and `x run` report a type error identically, block for block, and
one run can report several errors at once:
`x check examples/test/test_multiple_errors.x` prints two independent
blocks — each with its own header, location, excerpt, and caret — followed
by the single line `x: found 2 type error(s)`. The excerpt is dropped by
`--no-context` (the location and hints stay), and `--color always`,
`--color never`, or `NO_COLOR` control whether the block carries ANSI
colours.

## The any and var annotations

 `any` and `var` are two spellings of the same escape hatch. The checker
maps both to one `any` type — diagnostics print `any` for either spelling —
and both are accepted in every annotation position: locals, parameters,
fields, return types, arrays (`any[]` / `var[]`), and nullable forms
(`any?` / `var?`).

```x any-vs-var.x
function store(any value) {
    return typeOf(value);
}

function main() {
    let var a = null;   // null leaves the variable open
    let any b;          // no initializer: stays any
    a = 5;
    a = "text";
    b = true;
    b = [1, 2];
    print(typeOf(a), typeOf(b));
    print(store(42), store("s"));
}
```

```output
string Array
number string
```

One sharp edge applies to **both**: a local initialized with a concrete,
non-null value narrows to that type for every later assignment —
`let var x = 5; x = "text";` fails with
`Cannot assign 'string' to 'x' of type 'integer'`. Declare the local
without an initializer, or start it from `null`, to keep it fully dynamic.
Parameters and fields are never narrowed: a `var`/`any` parameter or field
accepts every value you store through it.

They are interchangeable everywhere — `var` reads like "variable of any
type", `any` matches the TypeScript habit. Pick one and use it consistently;
internally there is no other difference.

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
of named properties. The TypeScript-style colon form
(`let user: object<string, string> = ...`) is also accepted for variables and
fields, and a union of string literals (`type SettingsKey = "theme" |
"backup";`) pins the value to its members.

An object literal checked against a generic object type is validated key by
key, and each problem gets its own diagnostic instead of a generic
assignment error:

```text
error: Object key 'd' is not allowed in 'DEFAULT_SETTINGS'
 --> settings.x:4:5
  |
4 |     d: "e",
  |     ^^ Object key 'd' is not allowed in 'DEFAULT_SETTINGS'
  = note: 'DEFAULT_SETTINGS' is typed `object<SettingsKey, string>`
  = note: allowed keys: "theme", "backup_interval_min", "last_backup_at"
  = help: remove the 'd' entry, or allow 'd' in the key type
```

A value of the wrong type reports
`Value for key 'theme' in 'settings' has the wrong type` with a
`= note: expected \`string\`, found \`integer\`` line. The same message appears for literals passed
to typed parameters (`... in argument 1 of 'update'`) and for assignment
literals; the caret underlines the offending key or value, and the browser
playground renders the `note`/`help` lines the same way as `x check`.

Run the complete sample with:

```sh
x run examples/type_of.x
```

### Deleting keys, indices and fields

`delete(target)` removes exactly one entry and returns `true`. It is a
builtin, so it needs no import: the Python side declares its origin as
`Object.delete` (`DELETE_BUILTIN_NAME` in
`xlang/interpreter/_native_builtins.py`), and — while the `object_literals`
feature is enabled — the qualified `Object.delete(target)` spelling works the
same way. `typeOf(delete)` reports `"function"`.

```x
let object<string, integer> freqMap = {};
freqMap.p = 34;
delete(freqMap.p);          // the key AND the value are gone
print("p" in freqMap);      // false

let integer[] values = [10, 20, 30];
delete(values[1]);          // spliced out: [10, 30], length 2

class Box {
    string label;
    public Box(string label) { this.label = label; }
}
let Box box = new Box("hi");
delete(box.label);          // that instance loses the field
```

| Target | What `delete` does |
| --- | --- |
| `object.key` / `object["key"]` | Removes the key and its value; `in`, `Object.keys`, and `Object.values` stop reporting it. |
| `array[index]` | Splices the element out — the array shrinks and later elements shift left. Negative indices work. |
| `instance.field` | Removes the field from that instance only; visibility rules still apply. |

Delete is as strict as reading, which is what makes a deleted value report an
error instead of quietly coming back:

- deleting a key, index, or field that is not there raises the error its read
  would raise — `Cannot delete key p: object has no such key`,
  `Cannot delete index 3: out of range for array of length 2`,
  `'Box' has no member 'label'` — so a second `delete(freqMap.p)` is
  reported rather than allowed to do nothing;
- reading something that was deleted raises the same errors
  (`Object has no field 'p'`, `'Box' has no member 'label'`, out of range);
- `delete` takes exactly one key or index expression: `delete(x)`, `delete(5)`,
  and `delete(f())` report `delete expects an object key or array index`, and
  `delete()` / `delete(a, b)` report the argument count;
- containers that cannot lose an entry refuse with `TypeException`:
  `strings are immutable`, `tuples do not support index deletion`,
  `class members are shared by every instance`, `imports declare their own
  members`, and `builtins are declared in the standard library and cannot be
  removed` (so `delete(Math.abs)` fails).

Because `for (let key in object)` iterates a snapshot of the keys, deleting
inside the loop is safe and empties the object:

```x
for (let key in counts) {
    delete(counts[key]);
}
print(counts); // {}
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

`export` marks a declaration as public. It may prefix the declaration —
`export type`, `export const`, `export let`, `export function`, `export class`,
`export enum`, `export namespace` — or be a bulk list,
`export { name, other as alias };`, which also exports variables and names
declared inside a top-level namespace. A file cannot re-export a name it only
imported. A member import (`import tools.Greeting`) binds only the named
declaration; the imported module's other declarations stay private to that
module, and using one is a type error that suggests the missing import line. The
[settings types example](./examples/settings_types/) declares types in one file,
imports them into a second, and uses them from a third.

Namespace chains work in member imports too: when the prefix before the last
dot is not a file, the loader looks for the shortest existing prefix file and
walks the remaining parts as exported namespaces inside it (see
`examples/namespace_demo`):

```x
// util.x
export namespace MyNamespace {
    export string function greet(string who) {
        return "hi, " + who;
    }
}

export { greet };   // also valid: export members declared without `export`

// main.x
import util.MyNamespace.greet   // binds greet directly
print(greet("Ada"));            // "hi, Ada"
```

Every namespace in the chain and the final member must be exported.
`import util.MyNamespace` binds the namespace itself, and whole-module
`import util` still exposes `util.MyNamespace.greet()` through the module
object. `import util.MyNamespace.*` wildcard-imports every exported member
of the namespace (the alias form `import util.MyNamespace.* as N` collects
them under `N` instead).

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

An imported function can be invoked straight from the import, which keeps
one-off helper calls to a single line (see `examples/import_function`):

```x
// import_function/B.x
export string function greet(string name, string greeting = "Hello") {
    print(greeting + ", " + name + "!");
    return greeting + ", " + name + "!";
}
```

```x
// import_function/A.x
import B.greet("Maya");   // imports greet and calls it -> "Hello, Maya!"
greet("Ada");             // the import stays bound, so greet is reusable
```

The import behaves exactly like `import B.greet`; the call runs where the
import is written, so statement order is kept, and it counts as a top-level
statement (no extra automatic `main()` on top of it). Aliases work too:
`import B.greet as hello("Maya")`. The result of the call is discarded — write
`greet("Maya")` if you need the value. A wrong argument count, a target that is
not callable, and the grouped/wildcard forms (`import B.{greet}(...)`,
`import B.*(...)`) are all rejected with a normal diagnostic.

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
`typeOf`, `delete`, and `args`, plus `sleep` (when `async` is enabled), `input` (when
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

### Try with resources

`try (let name = resource) { ... }` binds a resource and calls its `close()`
method automatically when the block exits — on normal completion, on `return`,
and on throw (before any `catch`/`finally` runs). The resource type is
optional; the bound value just needs a `close()` method. Multiple bindings are
closed last-in-first-out.

```x
class Connection {
    private string id;

    public Connection(string id) {
        this.id = id;
        print("open   " + this.id);
    }

    public string getId() { return this.id; }

    public void close() {
        print("close  " + this.id);
    }
}

try (let Connection db = new Connection("db")) {
    print("using " + db.getId());
}
// prints: open db / using db / close db
```

See the runnable [try-with-resources example](./examples/exceptions/try_with_resources.x)
for the throw-before-catch and multi-resource LIFO cases.

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

All structures are constructed with `new` and used through instance methods —
there is no static call style (`HashMap.set(map, key, value)` raises an error).
The four spellings below differ only in how you *import* and *name* the type:

**1. Inline import + short name** — import one structure and use it directly:

```x
import System.utils.Collections.Stack

let Stack<string> history = new Stack<string>()
history.push("first")
history.push("second")
print(history.peek())   // second
print(history.size())   // 2
history.pop()
```

**2. Namespace import** — import the whole module; prefix the type name in `new`:

```x
import System.utils.Collections

let stack = new Collections.Stack()
stack.push("item")
print(stack.peek())  // item
```

**3. Full path** — no import needed:

```x
let stack = new System.utils.Collections.Stack()
stack.push("item")
print(stack.peek())  // item
```

**4. Alias** — `List` is a built-in alias for `LinkedList`:

```x
import System.utils.Collections.List

let List<string> names = new List<string>()
names.add("Alice")
names.add("Bob")
print(names.getFirst())  // Alice
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
| **Stack** | — | LIFO stack with O(1) push/pop operations | Dot-call style, toArray conversion, isEmpty check |
| **Queue** | — | FIFO queue with O(1) enqueue/dequeue operations | Dot-call style, peek, toArray conversion |
| **PriorityQueue** | — | Min-heap based priority queue | Automatic ordering, peek at minimum element |
| **Set** | — | Hash set with O(1) average-case operations | `union`, `intersection`, `difference`, `toArray` |
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
let map = new Collections.HashMap()

// Basic operations
map.set("name", "Alice")
map.set("age", 30)
print(map.get("name"))  // Alice
print(map.has("age"))   // true
print(map.size())       // 2

// Advanced operations
print(map.getOrDefault("missing", "default"))

// Lazy initialization
let cache = new Collections.HashMap()
function compute(string key) {
    return key.length * 10
}
let value = cache.computeIfAbsent("test", compute)

// Functional operations — filter/map/reduce return fresh HashMaps,
// so they chain
function isLong(string[] entry) {
    return entry[0].length > 3
}
let filtered = map.filter(isLong)

function uppercase(string[] entry) {
    return [entry[0].toUpperCase(), entry[1]]
}
let mapped = map.map(uppercase)

function sum(any acc, any entry) {
    if (typeOf(entry[1]) === "number") {
        return acc + entry[1]
    }
    return acc
}
let total = map.reduce(0, sum)
```

**Note:** You can also use the full path without importing:
```x
let map = new System.utils.Collections.HashMap()
map.set("key", "value")
```

**HashMap Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `set` | `set(key, value)` | Sets a key-value pair |
| `get` | `get(key)` | Gets value by key (returns null if not found) |
| `has` | `has(key)` | Checks if key exists |
| `remove` | `remove(key)` | Removes and returns value by key |
| `size` | `size()` | Returns number of entries |
| `isEmpty` | `isEmpty()` | Checks if map is empty |
| `clear` | `clear()` | Removes all entries |
| `keys` | `keys()` | Returns array of all keys |
| `values` | `values()` | Returns array of all values |
| `entries` | `entries()` | Returns array of [key, value] pairs |
| `getOrDefault` | `getOrDefault(key, default)` | Gets value or default if not found |
| `computeIfAbsent` | `computeIfAbsent(key, function)` | Computes value if key absent |
| `computeIfPresent` | `computeIfPresent(key, function)` | Computes new value if key present |
| `merge` | `merge(otherMap, ...)` | Merges into a fresh HashMap |
| `filter` | `filter(predicate)` | Filters entries into a fresh HashMap |
| `map` | `map(mapper)` | Transforms entries into a fresh HashMap |
| `reduce` | `reduce(initial, reducer)` | Reduces entries to single value |
| `putAll` | `putAll(other)` | Copies all entries from other into this map |

### LinkedList

### LinkedList / List

A doubly-linked list with efficient operations at both ends. `List` is a built-in alias — `new List()` and `new LinkedList()` are identical. See the **[List (LinkedList)](#list-linkedlist)** section above for the full OOP-style documentation and example with generics and `for` loop traversal.

Namespace-import style for construction (methods are always called on the instance):

```x
import System.utils.Collections

let list = new Collections.LinkedList()

// Add elements
list.add("middle")
list.addFirst("first")
list.addLast("last")

// Access
print(list.getFirst())  // first
print(list.getLast())   // last
print(list.get(1))      // middle

// Remove
list.remove("middle")
let removed = list.removeFirst()

// Utility
print(list.size())
print(list.contains("last"))
list.reverse()
print(list.toArray())
```

### Stack

LIFO (Last-In-First-Out) stack implementation.

```x
import System.utils.Collections.Stack

let Stack<string> history = new Stack<string>()
history.push("first")
history.push("second")
history.push("third")

print(history.peek())    // third
print(history.pop())     // third
print(history.size())    // 2
print(history.isEmpty()) // false
history.clear()
```

**Stack Methods:**

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

let Queue<string> q = new Queue<string>()
q.enqueue("first")
q.enqueue("second")
q.enqueue("third")

print(q.peek())     // first
print(q.dequeue())  // first
print(q.dequeue())  // second
print(q.size())     // 1
```

**Queue Methods:**

| Method | Description |
|--------|-------------|
| `enqueue(value)` | Adds value to the back |
| `dequeue()` | Removes and returns the front value |
| `peek()` | Returns front value without removing |
| `size()` | Returns queue size |
| `isEmpty()` | Returns true if empty |
| `clear()` | Removes all elements |
| `toArray()` | Returns all elements as an array |

### PriorityQueue

Min-heap based priority queue (smallest element has highest priority):

```x
import System.utils.Collections

let pq = new Collections.PriorityQueue()

pq.enqueue(5)
pq.enqueue(2)
pq.enqueue(8)

print(pq.peek())     // 2
print(pq.dequeue())  // 2
print(pq.dequeue())  // 5
```

**PriorityQueue Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `enqueue` | `enqueue(value)` | Adds value (maintains order) |
| `dequeue` | `dequeue()` | Removes and returns minimum |
| `peek` | `peek()` | Returns minimum without removing |
| `size` | `size()` | Returns queue size |
| `isEmpty` | `isEmpty()` | Checks if empty |
| `clear` | `clear()` | Clears queue |
| `toArray` | `toArray()` | Converts to array |

### Trie

Prefix tree for efficient string operations:

```x
import System.utils.Collections

let trie = new Collections.Trie()

trie.insert("hello")
trie.insert("world")
trie.insert("hey")

print(trie.search("hello"))     // true
print(trie.search("hel"))       // false
print(trie.startsWith("he"))    // true
print(trie.getAllWords())       // [hello, hey, world]
print(trie.size())              // 3

trie.remove("hey")
print(trie.size())              // 2
```

**Trie Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `insert` | `insert(word)` | Inserts a word |
| `search` | `search(word)` | Checks if exact word exists |
| `startsWith` | `startsWith(prefix)` | Checks if any word starts with prefix |
| `remove` | `remove(word)` | Removes a word |
| `size` | `size()` | Returns word count |
| `isEmpty` | `isEmpty()` | Checks if empty |
| `clear` | `clear()` | Clears all words |
| `getAllWords` | `getAllWords()` | Returns all words |

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
- [x] OOP instance style — `new Stack()` returns an instance; methods called as `stack.push(x)` (the only style — static calls are removed)
- [x] Inline import — `import System.utils.Collections.Stack` binds `Stack` directly
- [x] Namespace import — `import System.utils.Collections` then `new Collections.Stack()`
- [x] Full path without import — `new System.utils.Collections.Stack()` always works
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
- [ ] **Immutable/frozen variants**
- [ ] **`fromJSON()` reachable from X** for the extended collections (TreeMap/TreeSet/LinkedHashMap/LRUCache) — currently only callable from the Python embedding API
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

## Decorators

Decorators attach behaviour to a function, class, constructor, or method.
Write `@` and a decorator expression directly above the declaration; the
`decorators` feature (enabled by default) turns them on. Four syntactic forms
are accepted, from a plain lower-case name to a parametrised call on a nested
member path:

```x
function mydecorator(var target) {
    return target;
}

function Mydecorator(var target) {
    return target;
}

function MyDecorator() {
    return (target) => target;
}

@mydecorator                    // 1. lower-case, no parentheses
function greet() {
    return "hi";
}

@Mydecorator                    // 2. capitalised, no parentheses
function save() {
    return "saved";
}

@MyDecorator()                  // 3. with parentheses
function sync() {
    return 1;
}

function main() {
    print(greet());
    print(save());
    print(sync());
}
```

```x
function load_test_cases() {
    return ["a", "b"];
}

class MyDecorator {
    static var foo = {bar: {parametrizedDecorator: (name, cases) => (target) => target}};
}

@MyDecorator.foo.bar.parametrizedDecorator("case", load_test_cases())  // 4. dotted path + arguments
function demo() {
    return 0;
}

function main() {
    print(demo());
}
```

The grammar behind those shapes:

- `@name` — a bare identifier. Capitalisation is purely a naming choice; X is
  case-sensitive, so the spelling must match a declaration in scope.
- `@a.b.c.name` — a dotted member chain. Each segment is an identifier.
- `@decorator(...)` — at most one argument list. Arguments are ordinary
  expressions (literals, arrays, dictionaries, and calls such as
  `load_test_cases()`) evaluated **once when the declaration runs** — that is,
  at program load, before `main` starts. `@dec()()` (two argument lists) is a
  parse error.

### What a custom decorator must do

A decorator is an ordinary function that receives the decorated declaration
and **must return the replacement**. Returning anything that is not a
function (or a class, for class decorators) fails when the declaration loads:

```x
function identity(var target) {
    return target;
}

@identity
function twice(integer n) {
    return n * 2;
}

function main() {
    print(twice(21)); // 42
}
```

For a function, method, or constructor the return value must be a function
(`Decorator for 'f' must return a function`); for a class it must be a class
(`Decorator for class 'Thing' must return a class`). A decorator without a
`return` produces the same error because it returns `null`.

### Wrapping the original

To change what the decorated function does, return an arrow function that
closes over the value you received (X has no anonymous `function`
expressions, so arrows are the tool for wrappers):

```x
function logged(var target) {
    return (a, b) => {
        print("calling add(" + a + ", " + b + ")");
        return target(a, b);
    };
}

@logged
function add(integer a, integer b) {
    return a + b;
}

function main() {
    print(add(2, 3)); // calling add(2, 3) then 5
}
```

### Parametrised decorators (factories)

`@dec(args...)` evaluates `dec(args...)` first and uses whatever it returns
as the decorator. A function that returns the real decorator is therefore a
factory — and because arguments are evaluated at load time, the factory runs
once, before `main`:

```x
function load_test_cases() {
    return ["login", "checkout"];
}

function suite(string name, string[] cases) {
    return (target) => {
        print("running " + name + " (" + cases.length + " cases)");
        return target;
    };
}

@suite("smoke", load_test_cases())
function example() {
    return "ok";
}

function main() {
    print(example()); // running smoke (2 cases), then ok
}
```

### Dotted paths

The chain can resolve through static class fields, static class methods, and
namespace members. Class fields need an explicit type — use `var` for
dictionaries — and class methods need an explicit return type. This is the
full parametrised form:

```x
function load_test_cases() {
    return ["a", "b"];
}

class MyDecorator {
    static var foo = {bar: {parametrizedDecorator: (name, cases) => (target) => {
        print("suite " + name + " with " + cases.length + " cases");
        return target;
    }}};
}

@MyDecorator.foo.bar.parametrizedDecorator("case", load_test_cases())
function demo() {
    return 0;
}

function main() {
    print(demo()); // suite case with 2 cases, then 0
}
```

Namespaces work the same way:

```x
namespace Suite {
    function parametrized(string name) {
        return (target) => {
            print("checking " + name);
            return target;
        };
    }
}

@Suite.parametrized("case")
function demo() {
    return 0;
}

function main() {
    print(demo()); // checking case, then 0
}
```

### Placement

Decorators may appear above a top-level `function` (including `async`
functions), above a `class`, and above methods and constructors inside a
class — the decorator line comes before `public`, `static`, and the other
modifiers:

```x
function deco(var target) {
    return target;
}

class Widget {
    @deco
    public Widget() {}

    @deco
    public integer count() {
        return 1;
    }

    @deco
    static integer total() {
        return 2;
    }
}

function main() {
    print(new Widget().count()); // 1
    print(Widget.total());       // 2
}
```

Enums, type aliases, and variables do not accept decorators and raise a
parse error such as `Enum decorators are not implemented yet` or
`Variable decorators are not implemented yet`.

### Stacking

Several decorators may stack; they are applied bottom-up, so the one closest
to the declaration runs first:

```x
function audit(var target) {
    print("audit applies");
    return target;
}

function memoize(var target) {
    print("memoize applies");
    return target;
}

@audit
@memoize
function compute() {
    return 42;
}

function main() {
    print(compute());
    // memoize applies
    // audit applies
    // 42
}
```

### The built-in `@trace`

With the `decorators` feature enabled, `trace` is predefined: it flags a
function so every call logs `Calling <name>`, and flags a class so every
construction logs `Constructing <name>`:

```x
@trace
function greet() {
    return "hello";
}

@trace
class Greeter {
    public Greeter() {}
}

function main() {
    print(greet()); // Calling greet, hello
    let g = new Greeter(); // Constructing Greeter
    print("built");
}
```

Common mistakes and the exact failures they produce:

- Decorator name not in scope — `Name 'nope' is not defined`.
- Using a plain function where a factory is needed (`@Logged()` with
  `function Logged(var target)`) — `No overload of 'Logged' accepts 0
  argument(s)`.
- Forgetting to return the target — `Decorator for 'f' must return a
  function` or `Decorator for class 'Thing' must return a class`.
- Decorating an enum or a variable — a parse error, see Placement above.

A larger, fully commented example combining factories with arguments,
stateful `memoize` caching, validation guards, multi-argument wrappers,
load-time side effects, stacking order, composing one decorator out of
another (`@retry` over `@flaky`), method decorators, and class decorators
lives in
[`examples/decorators/complex.x`](./examples/decorators/complex.x):

```sh
x run examples/decorators/complex.x
```

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

## Loops

Three loop forms plus the iterating pair. `break` leaves the nearest loop,
`continue` starts the next iteration.

```x loops.x
function main() {
    for (let i = 0; i < 3; i = i + 1) {
        print("tick", i);
    }

    let remaining = 2;
    while (remaining > 0) {
        print("wait", remaining);
        remaining = remaining - 1;
    }

    for (let step of ["start", "stop"]) {
        print(step);
    }
}
```

```output
tick 0
tick 1
tick 2
wait 2
wait 1
start
stop
```

`do ... while` runs the body at least once; `for ... in` walks an object's
keys, an array's elements, or a range's values:

```x iteration.x
function main() {
    let integer n = 0;
    do {
        print("do", n);
        n = n + 1;
    } while (n < 2);

    for (let k in {a: 1, b: 2}) {
        print("in", k);
    }

    for (let v in ["x", "y"]) {
        print("v", v);
    }
}
```

```output
do 0
do 1
in a
in b
v x
v y
```

`range(start, end, step)` is an end-exclusive range you can iterate — it
prints as `range(0, 5)` because it is a lazy sequence, not an array:

```x range.x
function main() {
    print(range(0, 5));
    for (let i of range(0, 6, 2)) {
        print("r", i);
    }
}
```

```output
range(0, 5)
r 0
r 2
r 4
```

Because `for ... in` over an object walks a snapshot of the keys, deleting
inside the loop is safe.

`for ... in` works the same way over a range — it yields the values:

```x for-in-range.x
function main() {
    for (let i in range(0, 3)) {
        print("in", i);
    }
}
```

```output
in 0
in 1
in 2
```

`break` leaves the nearest loop early and `continue` skips to the next
iteration:

```x break-continue.x
function main() {
    for (let i = 0; i < 5; i = i + 1) {
        if (i == 2) {
            continue;
        }
        if (i == 4) {
            break;
        }
        print("i", i);
    }

    let integer first = -1;
    for (let n of range(1, 100)) {
        if (n > 10) {
            first = n;
            break;
        }
    }
    print(first);
}
```

```output
i 0
i 1
i 3
11
```

## Switch statements

`switch` runs case bodies starting from the first `case` whose value equals
the scrutinee, then continues through every following body to the closing
brace. Each body is a block — `case` and `default` require `{ ... }`:

```x
function main() {
    let integer code = 2;
    switch (code) {
        case 1: {
            print("one");
        }
        case 2: {
            print("two");
        }
        default: {
            print("other");
        }
    }
    print("after");
}
// two
// other
// after
```

The rules, each covered by the regression corpus:

- Scanning is **positional**: execution starts at the first matching `case`,
  or at `default` when `default` appears first. A `default` placed before the
  matching case therefore wins, and a later matching case still runs its body
  after the default's body.
- From the start point, execution **falls through to the end** of the switch —
  every following body runs, including `default`. Order cases so the likely
  match comes last, or accept the fallthrough.
- There is no switch-level `break`. `break` only ever leaves a **loop**, so
  `break` directly inside a switch fails at runtime with
  `'break' used outside of a loop`. Inside a loop, `break` in a switch case
  exits the enclosing loop — that is the only early exit.
- Case values are ordinary expressions, compared with exact type matching
  (`1.0` does not match `1`). With no match and no `default`, nothing runs.

Bodies nest arbitrarily deep. This six-level example and its fallthrough
output are pinned by the corpus row `six level nested switch runs every
following body`:

```x
function main() {
    let integer a = 1;
    let integer b = 6;
    switch (a) {
        case 1: {
            print("level 1");
            switch (b) {
                case 6: {
                    print("level 2");
                    switch (b) {
                        case 6: {
                            print("level 3");
                        }
                        default: { print("inner other"); }
                    }
                }
                default: { print("mid other"); }
            }
        }
        default: { print("outer other"); }
    }
}
// level 1
// level 2
// level 3
// inner other
// mid other
// outer other
```

To stop early, wrap the switch in a loop and break the loop:

```x
function main() {
    let integer result = 0;
    for (let i = 0; i < 5; i = i + 1) {
        switch (i) {
            case 3: { result = 100; break; }
            default: { result = i; }
        }
    }
    print(result); // 100
}
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

The multi-file [payment project](./examples/payment_project/) exercises the
whole object model in one runnable program: an `interface` (`Gateway`), an
`abstract class` (`AbstractPayment` with abstract `makePayment` and concrete
`configurePaymentGateway`), `private` fields holding configuration read from
the project `.env` file, `extends`/`super` constructor chaining,
`virtual`/`override` dispatch, a `static` registry counter, a `final` class,
a custom `Exception` thrown and caught, an `enum` status, and polymorphic
`for ... of` iteration over mixed subclasses:

```sh
x run examples/payment_project/main.x
x check examples/payment_project/main.x
```

Copy `examples/payment_project/.env.example` to
`examples/payment_project/.env` to feed the demo credentials through the
loader; the program runs with safe fallback values either way.

The multi-file [banking platform](./examples/banking_platform/) is a
Java-to-X translation of a Spring-flavoured codebase: a five-level-deep
nested `PlatformConfig` hierarchy built with explicit getters, generic
interfaces (`EventHandler<E, C>`, `ProcessingStage<I, O>`, `Box`-style
hints), interface-typed arrays, a composition-root `TransactionConfiguration`
in place of `@Configuration`, and top-level `async` functions standing in
for `CompletionStage` results. Its README documents every adaptation
(`HashMap` instead of `Map`, underscore-prefixed backing fields where Java
records clash with X's no-field/method-name-clash rule, backtick string
interpolation, and more).

```sh
x run examples/banking_platform/main.x
```

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

## Documentation site and browser playground

`docs-site/` is a static website (no build step) whose playground runs the
**real** interpreter compiled to WebAssembly through Pyodide. Because the
playground `fetch`es the Pyodide runtime and the interpreter wheel and loads a
module Web Worker, it must be served over **HTTP** — opening the files with
`file://` will not work. Serve the repository root with any static server:

```sh
python3 -m http.server 8080
```

Then open the docs at `http://127.0.0.1:8080/docs-site/` and the playground at
`http://127.0.0.1:8080/docs-site/playground.html`. The docs shell is plain
HTML/CSS/JS (no build step); the playground uses a **vendored** Monaco editor
and the same WebAssembly runtime. Release notes live at
`http://127.0.0.1:8080/docs-site/?page=about/changelog.md` (source:
`docs-site/about/changelog.md`). The interpreter itself does need a rebuild
after changing anything under `xlang/`: rebuild
the wheel the playground loads with

```sh
x playground           # rebuild the wheel once
x playground-watch     # rebuild automatically on every xlang/ edit
x playground-check     # exit 1 if the wheel is stale (CI)
```

The build fingerprints `xlang/**` + `pyproject.toml`, writes the wheel and the
fingerprint into `docs-site/playground/wheels/manifest.json`, and the worker
requests the wheel with `?v=<fingerprint>` — so the next page reload always
fetches the new interpreter. Skipping the rebuild (or a stale
`playground-check`) means the browser silently runs the old Python code.
See `docs-site/README.md` for the full pipeline.

The site is published to GitHub Pages by
`.github/workflows/deploy-docs.yml`, which uploads `docs-site/` as the Pages
artifact. GitHub Pages' branch-based picker only offers `/` or `/docs`, so
`docs-site/` is not selectable there — the Actions deploy is what ships the
folder and its WebAssembly playground. Enable it once under **Settings → Pages
→ Source = GitHub Actions**. The deployed site lives at
<https://thisismayuresh.github.io/x-lang/> (playground:
<https://thisismayuresh.github.io/x-lang/playground.html>).

## Tests

There are two test suites: the interpreter test suite under `tests/`, and the
CSV regression corpus under `csv_tests/`.

### Running the interpreter tests

From the project root (with the virtual environment activated, or prefix the
commands with `.venv/bin/`):

```sh
python -m pytest tests/ -q
```

The equivalent standard-library command is:

```sh
python -m unittest discover -s tests -v
```

The tests cover parsing and execution of core syntax, functions, classes,
access control, final classes, decorators, nested types, namespaces,
exceptions, all loop forms, pattern matching, destructuring, ASI, equality,
objects, project configuration and feature flags, source diagnostics and
type diagnostics, string indexing, grouped project imports, filesystem
operations, rest/spread, async/await, and OS threads.

### Running the CSV test corpus

[`csv_tests/`](./csv_tests/) holds 1381 generated regression rows split across
four CSV files (`run_tests.csv`, `check_tests.csv`, `error_tests.csv`,
`format_tests.csv`). Each row is one source program plus its expected stdout,
error, or formatted output, and the runner executes every row as a subtest:

```sh
python -m pytest csv_tests/test_corpus.py -q
```

The runner also works without pytest:

```sh
python csv_tests/test_corpus.py
```

Keep a subset of rows with `X_CORPUS_FILTER`, which matches against the row
id, file, category, or name:

```sh
X_CORPUS_FILTER=switch python csv_tests/test_corpus.py
```

Rows are generated, not hand-written. Regenerating rewrites all four CSVs and
aborts if any authored expectation disagrees with what the interpreter
actually produces:

```sh
python csv_tests/generate_corpus.py            # regenerate and verify
python csv_tests/generate_corpus.py --sample 5 # print sample rows per kind
python csv_tests/generate_corpus.py --no-verify # write without verifying
```

Regeneration is deterministic: running the generator twice produces
byte-identical CSVs, so a diff after regeneration means the corpus or the
interpreter changed.

### Continuous integration

`.github/workflows/tests.yml` runs on every push and pull request to
`development` and `main` with three jobs:

- **pytest** on Python **3.10** and **3.14**: installs the package with the
  dev extra (`python -m pip install -e ".[dev]"` — pytest plus the
  `pygls`/`lsprotocol` dependencies the LSP tests need), installs `tsc` for
  the TypeScript-compile tests, then runs
  `python -m pytest tests/ csv_tests/ -q`. A commented `--deselect` list keeps
  the known typeOf/showcase failures from turning CI red — remove an entry as
  soon as its test is fixed.
- **playground wheel freshness**: `python docs-site/playground/build.py --check`
  fails when anything under `xlang/` changed but the wheel in
  `docs-site/playground/wheels/` was not rebuilt, so the browser playground
  can never silently run an old interpreter.
- **docs-site JS syntax**: `node --check` over every authored `.js` file,
  skipping the vendored `monaco/` and `pyodide/` trees.

The dev extra (defined in `pyproject.toml`) installs pytest and the LSP
test dependencies:

```sh
python -m pip install -e ".[dev]"
```

Docs are deployed separately by `.github/workflows/deploy-docs.yml`.

## Feature examples

Runnable feature examples are organized by topic:

```text
examples/
├── configuration/configured_args.x
├── control_flow/main.x
├── control_flow/main_file.x
├── decorators/trace.x
├── exceptions/try_catch_finally.x
├── exceptions/try_with_resources.x
├── namespaces/nested_classes.x
├── objects/destructuring.x
├── pattern_matching/match.x
├── settings_types/main.x
└── payment_project/main.x
```

For example:

```sh
x run examples/control_flow/main_file.x
x run examples/decorators/trace.x
x run examples/exceptions/try_catch_finally.x
x run examples/exceptions/try_with_resources.x
x run examples/filesystem_async_demo.x
x run examples/namespaces/nested_classes.x
x run examples/objects/destructuring.x
x run examples/pattern_matching/match.x
x run examples/settings_types/main.x
x run examples/payment_project/main.x
x run --profile feature-tour examples/configuration/configured_args.x
```

The [`examples/settings_types/`](./examples/settings_types/) project declares
types in one file, imports them into a second, and uses them from a third — the
X equivalent of a TypeScript `export type`/`export const` settings module. The
shared key type is a union of string literals (`type SettingsKey = "theme" |
"backup_interval_min" | "last_backup_at"`), the defaults object uses the
`object<SettingsKey, string>` form, and the middle file exposes a generic
lookup, `lookup<KeyT, ValueT>(object<KeyT, ValueT> store, KeyT key)`, next to
the concrete settings helpers.

The [`examples/dsa/`](./examples/dsa/README.md) folder contains 20 standalone
algorithm demonstrations grouped by common interview patterns, including
sliding windows, two pointers, binary search, stacks, recursion, matrix
traversal, and string encoding. Each `.x` file can be run independently.

`Object` currently operates on X object literals and dictionaries. Object
literals support identifier/string keys plus integer and float keys
(`{ 200: "a" }`, accessed as `m.200` or `m[200]` — integer and string keys
are distinct: `m[200]` and `m["200"]` are different entries), shorthand
properties, and spread; computed keys, symbols,
prototypes, getters/setters, and anonymous methods are not implemented.
Destructuring supports nested array/object bindings, defaults
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

- [ ] `??` nullish coalescing — the JS-style operator does not parse
  (`a ?? b` is a syntax error); use `a == null ? b : a` until it lands
- [ ] Native or bytecode compilation — `build` validates syntax, imports, and
  types, then reports that no executable was produced
- [ ] Generic type checking and type-parameter substitution — generic
  annotations parse and their type names are checked, but element types are
  not enforced (`List<string>` in a `List<integer>` slot passes `x check`)
- [ ] Union/nullable type semantics — `integer | null` does not exist and
  `null` is rejected for non-null types; inline `record{...}` annotations are
  checked structurally today
- [ ] Independent module namespaces — imports are resolved but declarations are not isolated behind module namespace objects (this manifesting as a scope collision is documented under [Known issue: `import B.greet` leaks the whole module scope](#known-issue-import-bgreet-leaks-the-whole-module-scope))
- Interfaces have no TypeScript-style index signatures — a TS-style
  `[key: number]: IParticipant` member reports `Expected a name`; declare the
  map as an alias over the builtin instead:
  `type Participants = object<integer, IParticipant>`
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

- `&&` and `||` always produce a boolean (`0 || "x"` is `true`, not `"x"`),
  unlike JavaScript's operand-returning operators — conditions themselves do
  accept truthy values (see the documentation site's truthiness table)
- `/` performs floating-point division — code needing an integer index must ensure the calculation is integral
- String indexing counts Unicode code points, not grapheme clusters or UTF-16 code units
- Parser recovery reports multiple recoverable errors but malformed constructs can prevent discovery of later errors; runtime failures stop at the first failure
- Recursive algorithms (flood fill, deep trees) can hit Python's default recursion limit on large inputs
- The run-length codec example is intended for letter-only input, not a general-purpose escaping format

### Fixed: `import B.greet` no longer exposes the whole module scope

**Status:** fixed. A member import (`import lib.greet`) now binds only the
declaration it names. Sibling declarations of the imported module are no
longer visible in the importing file; using one is a type error that suggests
the exact import line to add:

```text
$ x check app.x
error: Name 'Marker' is not defined in this module
 --> app.x:3:1
  |
3 | interface Marker {
  | ^ Name 'Marker' is not defined in this module
  |
  = help: add `import lib.Marker`
```

Whole-module (`import lib`), grouped (`import lib.{A, B as C}`), alias
(`import lib.A as X`), and wildcard (`import lib.*`) imports behave as
before: they expose exactly what they name. Enum and interface names imported
by any form are types, not values — `print(Gender)` reports
`Enum 'Gender' is a type, not a value`, while `typeOf(Gender)` and
`Gender.MALE` are accepted. The runtime still shares one namespace across
modules (helpers used by an imported function resolve through that shared
scope), but the type checker gates what user-visible code can reference, so
the old silent leak and its confusing `'X' is already declared` collisions
are gone.

Historical note: this used to be an open limitation — the loader flattened
every imported module's declarations into the importer, so `import
main_tests.greet` also pulled in `main_tests`' interfaces, classes, and
helpers, colliding with any same-named local declaration. The fix records
per-module visibility in the loader and enforces it in the checker.

The detailed syntax proposal is in [Draft.md](./Draft.md). Where the interpreter
behavior is narrower than that draft, this README describes what can currently
be relied upon.

## Editor support (VS Code)

A bundled extension in [`vscode-xlang/`](./vscode-xlang/) provides syntax
highlighting, real-time type checking, completions, hover, go-to-definition and
Find All References for `.x` files. It is installed as `xlang.xlang@0.1.0` and
activates automatically when you open any `.x` file — no manual step, and
nothing to re-do after a reboot.

Editor diagnostics are produced by the same `Lexer` → `Parser` →
`TypeChecker` pipeline used by `x check`, and the server reads `x.toml` the
same way, so the squiggles in the editor and the command-line output match.
The document is loaded through `ModuleLoader`, so interfaces and classes
brought in through `import` are visible — a class implementing an interface
declared in another file no longer reports a false
`implements unknown interface` error. The checker also rejects a value
returned from a `void` function or method — previously that slipped through.

Go-to-definition (Ctrl+Click / F12) resolves functions, methods,
constructors, parameters, fields, variables and enum members inside the
current file, not just type names, and crosses direct `import` statements:
Ctrl+Click on an imported interface jumps to its `export interface` line in
the declaring file. Find All References lists every whole-word use of the
clicked name in the current document.

Completions are type-aware: every `let`/`const` binding is offered with its
type in the popup (inferred from the initializer when un-annotated), and after
`let p = new Point();` the popup for `p.` lists only `Point`'s fields and
methods. The same holds for built-in types — `s.` on a `string` offers
`toUpperCase`/`trim`/`split`, `names.` on an array offers `push`/`map`/`filter`,
and `obj.` on an object offers `keys`/`values`/`entries` — so the popup follows
the declared or inferred type of the receiver, not just classes. Import paths
after `import System.` are filtered to what exists on disk.

The extension's server is a Python script the editor spawns at startup. After
editing [`vscode-xlang/server/server.py`](./vscode-xlang/server/server.py) the
running editor still has the old copy, so repackage and reinstall it, then
reload the window:

```sh
cd vscode-xlang
npm run compile
npx --yes @vscode/vsce package --allow-missing-repository --skip-license \
    -o /tmp/opencode/xlang-0.1.0.vsix
code --install-extension /tmp/opencode/xlang-0.1.0.vsix
```

Then `Ctrl/Cmd+Shift+P` → **Developer: Reload Window**. The reload is what
makes VS Code drop the old server process and start the new one; without it
the editor keeps running the copy it launched with. While developing you can
skip packaging entirely: open `vscode-xlang/` and press `F5` to launch an
Extension Development Host against the source tree.

See **[`vscode-xlang/README.md`](./vscode-xlang/README.md)** for the full
report: architecture, every defect that was fixed, what was installed where,
how to rebuild it, and the current limitations (go-to-definition resolves
direct imports but does no scope analysis; Find All References is
single-file and word-based).

**[`INTROSPECTION.md`](./INTROSPECTION.md)** documents the proposed next step:
the interpreter, the typechecker and the LSP each carry their own handwritten
list of builtin methods and the copies have drifted (the editor currently
offers 11 of the string type's 32 methods). The design replaces all copies
with one public `xlang.introspect` module the server already has the means to
call in-process, with the research, phased plan, industry comparison, and
trade-offs.
