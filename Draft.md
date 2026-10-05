Yes. Let's lock those decisions into the specification.

I'll treat **X** as the language name, `.x` as the source-file extension, and `x x.x` as the basic compilation command where the first `x` is the compiler/program and the second `x.x` is the source file.

I've also added a proper command-line argument model to the language.

# X Programming Language Specification

## Draft 0.1

**Language:** X\
 **Source Extension:** `.x`\
 **Compiler Command:** `x`\
 **Specification Status:** Experimental\
 **Specification Version:** 0.1

---

# 1\. Introduction

X is a statically typed, general-purpose programming language designed around a combination of:

- Java/C#-style object-oriented programming
- TypeScript-inspired type features
- First-class functions
- Static typing
- Type inference
- Generic programming
- Interfaces
- Enums
- Structural types
- True nested classes
- Constructor overloading
- Method overloading
- Inheritance
- Explicit module imports and exports
- Iterable-based loops
- Command-line applications
- A simple compiler and runtime model

X is intended to provide the power of languages such as Java and C# while maintaining a concise syntax.

---

# 2\. Language Philosophy

X follows these principles:

1. Strong static typing.
2. Type inference where explicit types are unnecessary.
3. Powerful classes.
4. First-class functions.
5. Simple module semantics.
6. Explicit exports.
7. Predictable imports.
8. Familiar syntax.
9. True nested types.
10. A standard library implemented using the same language mechanisms available to users.
11. A compiler architecture suitable for both interpretation and native compilation.

---

# 3\. Source Files

X source files use the `.x` extension.

Example:

```
hello.x
main.x
server.x
User.x
```

A program can contain multiple `.x` files.

Example project:

```
myapp/
├── main.x
├── users.x
├── database.x
└── utils.x
```

---

# 4\. X Compiler

The X compiler executable is named:

```
x
```

The basic compilation command is:

```
x x.x
```

Here:

- `x` is the X compiler executable.
- `x.x` is the source file.
- the first `x` is the compiler/program name.
- the second `x.x` is the source filename.

For example:

```
x main.x
```

compiles `main.x`.

---

# 5\. Running Programs

The compiler may support a direct run command:

```
x run main.x
```

Compilation and execution are conceptually separate operations.

For example:

```
x build main.x
```

builds the program.

```
x run main.x
```

builds and runs the program.

The exact output-file conventions are implementation-defined in version 0.1.

---

# 6\. Program Entry Point

An executable X program may define:

```
function main() {
    ...
}
```

The compiler identifies `main` as the program entry point.

Example:

```
function main() {
    print("Hello, world!");
}
```

An explicit return type may also be used:

```
integer function main() {
    print("Hello, world!");
    return 0;
}
```

A `main` function returning `void` may omit the return type:

```
function main() {
    ...
}
```

---

# 7\. Command-Line Arguments

X provides command-line arguments to the program through the `args` value.

A basic program can access arguments using:

```
function main() {

    print(args);
}
```

`args` is an array of strings:

```
string[] args
```

Therefore individual arguments can be accessed using indexing:

```
function main() {

    print(args[0]);
    print(args[1]);
}
```

The exact convention for whether the executable name is included in `args` is defined by the runtime.

---

# 8\. Explicit Command-Line Arguments

The type of `args` may be explicitly declared through a parameterized main function.

```
function main(string[] args) {

    print(args[0]);
}
```

This is the preferred explicit form.

Both forms represent the same underlying command-line argument collection.

---

# 9\. Example Command-Line Program

Source:

```
function main(string[] args) {

    for (string argument in args) {
        print(argument);
    }
}
```

Execution:

```
x run main.x hello world 123
```

The program receives:

```
hello
world
123
```

as command-line arguments according to the runtime's argument convention.

---

# 10\. Argument Count

The number of arguments can be obtained using the array length:

```
function main(string[] args) {

    print(args.length);
}
```

Example:

```
if (args.length == 0) {
    print("No arguments provided.");
}
```

---

# 11\. Command-Line Argument Parsing

X does not require users to manually parse every argument.

The standard library should provide a command-line argument parser.

Example:

```
import cli.Arguments

function main(string[] args) {

    let Arguments arguments = Arguments.parse(args);

    print(arguments.get("name"));
}
```

The exact API is part of the standard library rather than the core language.

---

# 12\. Comments

Single-line comments:

```
// comment
```

Multi-line comments:

```
/*
    comment
*/
```

---

# 13\. Identifiers

Identifiers consist of letters, digits, and underscores.

Valid examples:

```
User
user
userName
user_name
calculateTotal
HTTPServer
```

Identifiers cannot begin with a digit.

---

# 14\. Primitive Types

X provides the following primitive types:

```
integer
float
double
boolean
string
char
byte
void
```

Example:

```
let integer age = 25;
let float percentage = 95.5;
let double price = 19.95;
let boolean active = true;
let string name = "Alice";
let char initial = 'A';
let byte value = 255;
```

---

# 15\. Variables

Variables use `let`.

Explicit type:

```
let integer age = 25;
```

Type inference:

```
let age = 25;
```

Variables can be reassigned:

```
let integer age = 25;

age = 30;
```

---

# 16\. Constants

Constants use `const`.

```
const integer MAX_USERS = 100;
const string VERSION = "1.0";
```

Constants cannot be reassigned.

---

# 17\. Null

X provides the value:

```
null
```

A nullable type uses `?`.

```
string? name;
User? user;
```

Nullable types represent:

```
Type | null
```

Example:

```
User? function findUser(integer id) {

    if (id == 1) {
        return User("Alice");
    }

    return null;
}
```

---

# 18\. Arrays

Array types use postfix `[]`.

```
integer[]
string[]
User[]
```

Examples:

```
let integer[] numbers = [1, 2, 3];

let string[] names = [
    "Alice",
    "Bob"
];

let User[] users = [];
```

Array indexing is zero-based:

```
numbers[0]
numbers[1]
```

---

# 19\. Functions

Standalone functions may omit their return type.

```
function greet(string name) {
    return "Hello " + name;
}
```

The compiler infers the return type.

A return type may be explicitly specified.

The return type appears **before** `function`:

```
string function greet(string name) {
    return "Hello " + name;
}
```

X does **not** use:

```
function greet(string name) -> string
```

The left-sided return-type syntax is the standard X syntax.

---

# 20\. Void Functions

A function with no return value may explicitly specify `void`:

```
void function log(string message) {
    print(message);
}
```

A standalone function may also simply omit its return type:

```
function log(string message) {
    print(message);
}
```

---

# 21\. Function Parameters

Parameters use:

```
Type name
```

Example:

```
function add(integer a, integer b) {
    return a + b;
}
```

Multiple parameters are separated by commas.

Defaulted parameters and nullable parameters are optional:

```
User function getUsers(string id = "10001") {
    return User(id);
}

User? function findUser(string? id) {
    if (id == null) {
        return null;
    }
    return User(id);
}
```

Calling `getUsers()` uses the default `"10001"`; providing an argument
overrides it. Omitting `id` in `findUser()` binds `null`. Default expressions
are evaluated at call time and can use earlier parameters. Required parameters
cannot follow optional parameters.

A broad catch can inspect the concrete exception when the caller does not know
which error may occur:

```
catch (Throwable error) {
    print(error.name + ": " + error.message);
}
```

---

# 22\. First-Class Functions

Functions are first-class values.

A function can be:

- assigned to a variable
- passed as an argument
- returned from another function
- stored in collections

Example:

```
function add(integer a, integer b) {
    return a + b;
}

let operation = add;

let result = operation(10, 20);
```

---

# 23\. Classes

Classes are reference types.

Example:

```
class User {

    private string name;
    private integer age;

    public User(string name, integer age) {
        this.name = name;
        this.age = age;
    }

    public string greet() {
        return "Hello " + this.name;
    }
}
```

Classes may contain:

- fields
- properties
- constructors
- methods
- static members
- nested classes
- nested interfaces
- nested enums
- nested types

---

# 24\. Class Methods

Class methods require an explicit return type.

```
class Calculator {

    public integer add(integer a, integer b) {
        return a + b;
    }

    public void reset() {
        ...
    }
}
```

This is invalid:

```
class Calculator {

    public function add(integer a, integer b) {
        ...
    }
}
```

The correct syntax is:

```
public integer add(integer a, integer b) {
    ...
}
```

Unlike standalone functions, methods cannot omit their return type.

---

# 25\. Constructors

Constructors have the same name as their containing class.

Constructors have no return type.

```
class User {

    public User(string name) {
        this.name = name;
    }
}
```

Construction:

```
let User user = User("Alice");
```

---

# 26\. Constructor Overloading

Constructors may be overloaded.

```
class User {

    public User(integer id) {
        ...
    }

    public User(string name) {
        ...
    }

    public User(string name, integer age) {
        ...
    }
}
```

The compiler chooses the appropriate constructor based on the arguments.

---

# 27\. True Nested Classes

Classes may contain other classes.

These are genuine nested types, not merely syntactic namespaces.

```
class Foo {

    class Bar {

        public Bar(integer x) {
            ...
        }

        public Bar(string x) {
            ...
        }
    }
}
```

The qualified type name is:

```
Foo.Bar
```

Nested classes can contain their own members.

---

# 28\. Deeply Nested Classes

Nested classes may themselves contain nested classes.

```
class Outer {

    class Middle {

        class Inner {

            public Inner() {
                ...
            }
        }
    }
}
```

A class can extend a nested class through a dotted type path at any nesting
depth, for example `class Child extends Outer.Middle.Deep.Base {}`. The same
qualified path can be used with `new` and in a declared variable type.

The fully qualified type is:

```
Outer.Middle.Inner
```

---

# 29\. Fields

Fields store object state.

```
class User {

    private integer id;
    public string name;
}
```

Fields may have initial values:

```
class User {

    private integer id = 0;
    public boolean active = true;
}
```

---

# 30\. Properties

Properties provide controlled access to state.

```
class User {

    public string name { get; set; }

    public integer id { get; }
}
```

Properties may be read-only:

```
public integer id { get; }
```

or read/write:

```
public string name { get; set; }
```

---

# 31\. Access Modifiers

X supports:

```
public
private
protected
internal
```

Example:

```
class User {

    private string password;

    public string name;

    protected void validate() {
        ...
    }
}
```

Members are private by default.

---

# 32\. Static Members

Classes may contain static fields and methods.

```
class Math {

    public static integer add(integer a, integer b) {
        return a + b;
    }
}
```

Usage:

```
Math.add(10, 20);
```

---

# 33\. Inheritance

A class may extend one class.

```
class Animal {

    public virtual string speak() {
        return "...";
    }
}

class Dog extends Animal {

    public override string speak() {
        return "Woof";
    }
}
```

X does not support multiple class inheritance.

---

# 34\. Interfaces

Interfaces define contracts.

```
interface Serializable {

    string serialize();
}
```

A class implements an interface using `implements`.

```
class User implements Serializable {

    public string serialize() {
        return this.name;
    }
}
```

A class can implement multiple interfaces:

```
class User implements Serializable, Comparable<User> {
    ...
}
```

---

# 35\. Interface Inheritance

Interfaces may extend other interfaces.

```
interface Animal {

    string speak();
}

interface Pet extends Animal {

    string getName();
}
```

---

# 36\. Abstract Classes

Abstract classes cannot be instantiated directly.

```
abstract class Animal {

    public abstract string speak();

    public void sleep() {
        ...
    }
}
```

Derived classes must implement abstract members.

---

# 37\. Enums

Enums define a fixed collection of values.

```
enum Color {

    RED,
    GREEN,
    BLUE
}
```

Usage:

```
let Color color = Color.RED;
```

---

# 38\. Explicit Enum Values

Enums may specify values.

```
enum Status {

    PENDING = 0,
    ACTIVE = 1,
    DISABLED = 2
}
```

String values may also be supported:

```
enum Role {

    ADMIN = "admin",
    USER = "user",
    GUEST = "guest"
}
```

---

# 39\. Type Declarations

X supports structural type declarations.

```
type User = {
    string name;
    integer age;
}
```

Usage:

```
let User user = {
    name: "Alice",
    age: 25
};
```

A `type` primarily describes data structure.

A `class` describes an object type with identity and behavior.

---

# 40\. Union Types

Multiple types can be represented using `|`.

```
type ID = string | integer;
```

Example:

```
let ID id;

id = "user-123";
id = 123;
```

Functions may also use union types:

```
integer | string function parse(string value) {
    ...
}
```

---

# 41\. Nullable Types

Nullable types use `?`.

```
User?
string?
integer?
```

For example:

```
User? function findUser(integer id) {
    ...
}
```

is equivalent to:

```
User | null function findUser(integer id) {
    ...
}
```

---

# 42\. Generics

Classes may use generic parameters.

```
class Box<T> {

    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return this.value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

Usage:

```
let Box<string> box = Box<string>("hello");
```

---

# 43\. Generic Functions

Functions may use generic parameters.

```
function<T> T identity(T value) {
    return value;
}
```

Example:

```
let value = identity("hello");
```

The compiler may infer `T`.

---

# 44\. Control Flow

Conditional statements use `if`.

```
if (condition) {
    ...
}
```

`else` is supported:

```
if (condition) {
    ...
}
else {
    ...
}
```

Multiple conditions:

```
if (x > 10) {
    ...
}
else if (x > 5) {
    ...
}
else {
    ...
}
```

---

# 45\. While Loops

```
while (condition) {
    ...
}
```

Example:

```
while (x < 10) {
    x++;
}
```

---

# 46\. For Loops

X uses an iterable-based `for ... in` syntax.

```
for (integer i in range(0, 10, 1)) {
    print(i);
}
```

The general syntax is:

```
for (Type variable in iterable) {
    ...
}
```

Example:

```
for (User user in users) {
    print(user.greet());
}
```

---

# 47\. Range

X uses the `range` function to create sequences.

The syntax is:

```
range(start, end, step)
```

There is **no `..` range operator**.

Example:

```
range(0, 10, 1)
```

Typical usage:

```
for (integer i in range(0, 10, 1)) {
    print(i);
}
```

Other examples:

```
range(0, 10, 2)
range(10, 0, -1)
```

The exact endpoint semantics are:

> `start` is included and `end` is excluded.

Therefore:

```
range(0, 10, 1)
```

produces:

```
0
1
2
3
4
5
6
7
8
9
```

---

# 48\. Break

`break` exits the nearest loop.

```
for (integer i in range(0, 100, 1)) {

    if (i == 50) {
        break;
    }
}
```

---

# 49\. Continue

`continue` skips the remainder of the current iteration.

```
for (integer i in range(0, 100, 1)) {

    if (i % 2 == 0) {
        continue;
    }

    print(i);
}
```

---

# 50\. Exception Handling

X supports exceptions.

```
try {

    riskyOperation();

}
catch (Exception e) {

    print(e.message);

}
finally {

    cleanup();
}
```

Exceptions may be thrown using:

```
throw new Exception("Something went wrong");
```

Built-in exception values follow a small catchable hierarchy:

```
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

Specific exceptions can be thrown and caught by a parent type. A catch binding
exposes `name`, `message`, `cause`, and `stack`; `stack` currently reports the
source location where the error was raised. Supply a cause as the optional
second constructor argument:

```
throw new DatabaseException(
    "query failed",
    new IOException("connection unavailable")
);
```

`catch (Throwable error)` is the broad fallback for any thrown value.
`Exception` catches runtime and file-system exceptions; `Error` is its
separate sibling branch. Runtime errors produced by arithmetic and
file-system operations retain their type when caught.

Applications may define their own exception classes by extending `Exception`
or `Error`. Call `super(message)` in a custom constructor to initialize the
standard exception properties; custom fields and parent classes can represent
domain-specific details:

```
class BadRequestException extends Exception {
    public integer statusCode;
    public BadRequestException(string message) {
        super(message);
        this.statusCode = 400;
    }
}

throw new BadRequestException("invalid user id");
```

Custom thrown instances match catches for their own class, custom ancestors,
their `Exception` or `Error` base, and `Throwable`.

---

# 51\. Multiple Catch Blocks

Multiple exception types may be caught.

```
try {

    operation();

}
catch (IOException e) {

    print("IO error");

}
catch (Exception e) {

    print("Unknown error");
}
```

Catch blocks are evaluated from most specific to most general.

---

# 52\. Modules

Each `.x` source file is a module.

A module can contain:

```
class
interface
enum
type
function
const
top-level executable statements
```

Declarations are private to the module unless exported.
Top-level statements execute in source order when the entry module is run.
When the entry module contains executable statements, the interpreter does not
also invoke a function named `main` implicitly.

---

# 53\. Packages

A module may declare its package.

```
package myapp.users
```

Packages provide hierarchical organization.

Example:

```
myapp
├── users
├── database
└── http
```

Qualified names may therefore be:

```
myapp.users.User
myapp.database.Postgres
myapp.http.Server
```

---

# 54\. Export

Declarations become publicly available to other modules using `export`.

```
export class User {
    ...
}
```

```
export function createUser(string name) {
    ...
}
```

```
export interface Serializable {
    string serialize();
}
```

```
export enum Role {
    ADMIN,
    USER
}
```

```
export type UserData = {
    string name;
    integer age;
}
```

Declarations without `export` remain module-private.

---

# 55\. Import

X imports declarations from files. A path first checks beside the importing
file and then from the project root. Dotted path components before the final
component map to folders. For `import greeting.sayGreet`, X loads `greeting.x`
and selects its exported `sayGreet` declaration.

```
import users.User
```

```
import database.Postgres
```

After importing:

```
import users.User

let User user = User("Alice");
```

The selected declaration is imported into the current namespace.

Multiple declarations in a file can be selected independently:

```
import greeting.sayGreet
import greeting.sayHello
```

Use `*` to import every exported declaration from a file. Add `as` to bind the
exports under one namespace-like value:

```
import greeting.*
import greeting.* as Greet

Greet.sayGreet()
Greet.sayHello()
```

The aliased wildcard namespace only exposes declarations marked `export`.
Project imports currently share the interpreter's global environment;
namespace aliases do not create isolated module scopes.

An imported module executes its top-level statements once, in source order. If
the module calls its exported `main()` at the top level, import alone executes
that call. Keep the importing entry file named differently from the imported
`main.x` module:

```
control_flow/
├── main.x
└── main_file.x
```

```
// main.x
export function main() {
    print("Hello");
}
main()
```

```
// main_file.x
import main
```

Run `main_file.x`; importing `main.x` executes its top-level `main()` call
once. If `main.x` only exports the function and does not call it, the importing
file can instead contain both `import main` and `main()` to invoke it
explicitly. The interpreter does not implicitly invoke an exported `main`
again when top-level executable code has already run.

If an imported module calls `main()` at top level, each top-level `main()` call
in the importer runs it again. The CLI warns at every such call site; warnings
are informational and do not suppress execution. `//` begins a line comment:
`main//()` is parsed as a bare `main` reference followed by a comment, not as
a call or syntax error. The CLI warns about this no-op form and suggests
`main()` or `// main()`.

---

# 56\. Import Aliases

An import can have an alias.

```
import database.Postgres as DB
```

Usage:

```
let db = DB(...);
```

---

# 57\. Grouped Imports

Multiple declarations may be imported from the same module:

```
import database.{Postgres, MySQL, SQLite}
```

This is equivalent to:

```
import database.Postgres
import database.MySQL
import database.SQLite
```

Aliases are allowed:

```
import database.{
    Postgres as DB,
    MySQL,
    SQLite
}
```

---

# 58\. Wildcard Imports

All exported declarations can be imported using `*`.

```
import database.*
```

Only exported declarations are imported.

---

# 59\. Nested Type Imports

Nested types may be imported using their qualified names.

For:

```
class Http {

    public class Request {
        ...
    }
}
```

the nested type can be imported:

```
import http.Http.Request
```

and used as:

```
let Request request = Request(...);
```

---

# 60\. Name Resolution

Qualified names are resolved hierarchically.

For:

```
myapp.users.User
```

the resolver identifies:

```
myapp
    ↓
users
    ↓
User
```

The final declaration may be a:

- class
- nested class
- interface
- enum
- type
- function
- constant

---

# 61\. Scope

X has:

- global scope
- package scope
- module scope
- class scope
- nested-class scope
- function scope
- block scope
- loop scope

Local declarations shadow outer declarations according to normal lexical-scope rules.

---

# 62\. Records

Records provide concise data-oriented declarations.

```
record User(
    string name,
    integer age
);
```

Records are value-oriented types.

The compiler may automatically generate:

- constructors
- equality
- field access
- string representation

The exact generated members are defined by the record specification.

---

# 63\. Object Literals

Structural types can use object literals.

```
type UserData = {
    string name;
    integer age;
}

let UserData user = {
    name: "Alice",
    age: 25
};
```

Object literals must satisfy the expected structural type.

---

# 64\. Collections

The X standard library provides generic collection types.

Initial standard collections include:

```
List<T>
Set<T>
Map<K, V>
Queue<T>
Stack<T>
```

Example:

```
let List<User> users;
let Map<string, User> usersByName;
```

Collections that implement iteration can be used with `for ... in`.

---

# 65\. Iterable Values

Any value implementing the language's iterable protocol can be used in:

```
for (Type value in iterable) {
    ...
}
```

Examples include:

```
User[]
List<User>
range(0, 10, 1)
```

---

# 66\. Main and Command-Line Arguments

The preferred command-line program form is:

```
function main(string[] args) {

    for (string argument in args) {
        print(argument);
    }
}
```

Running:

```
x run main.x hello world
```

provides the program with the arguments.

`args` is a normal `string[]` value and therefore supports:

```
args.length
args[0]
args[1]
```

and iteration:

```
for (string arg in args) {
    print(arg);
}
```

---

# 67\. Example CLI Application

```
function main(string[] args) {

    if (args.length == 0) {
        print("Usage: app <name>");
        return;
    }

    let string name = args[0];

    print("Hello " + name);
}
```

Execution:

```
x run app.x Alice
```

Output:

```
Hello Alice
```

---

# 68\. Example: CLI Argument Parser

A future standard-library API may provide:

```
import cli.Arguments

function main(string[] args) {

    let Arguments options = Arguments.parse(args);

    if (options.has("verbose")) {
        print("Verbose mode enabled.");
    }

    let string? name = options.get("name");

    if (name != null) {
        print("Hello " + name);
    }
}
```

The argument parser is a library feature rather than a special language construct.

---

# 69\. Operators

X provides standard arithmetic operators:

```
+
-
*
/
%
```

Comparison:

```
==
!=
<
>
<=
>=
```

Logical:

```
&&
||
!
```

Assignment:

```
=
+=
-=
*=
/=
```

Increment/decrement:

```
++
--
```

Operator precedence follows conventional C/Java/C#-style precedence.

The ternary conditional operator is supported:

```
let string label = isReady ? "ready" : "waiting";
```

Null-safe chains use `?.member`, `?.(arguments)`, and `?[index]`. An optional
segment whose receiver is `null` short-circuits the remainder of that chain to
`null`; safe indexing also returns `null` for an out-of-range sequence index or
missing dictionary key. Invalid index types still report errors.

```
let name = user?.profile?.getName?.();
let first = users?[0];
let maybeName = profiles?[0]?.name;
```

Optional member access on a dictionary returns `null` when the property is
absent. Optional calls do not evaluate their arguments when the callee is
`null`.

The lexer recognizes `?[` as its own operator, distinct from a ternary `?`.
Thus `condition ? [value] : fallback` remains a ternary expression.

A complete precedence table will be included in a future formal grammar revision.

---

# 70\. Strings

Strings use double quotes:

```
"Hello"
"Hello world"
```

Character literals use single quotes:

```
'A'
'X'
```

String concatenation uses `+`:

```
let string message = "Hello " + name;
```

The built-in `typeOf(value)` function returns a JavaScript-style type name.
Integers and floats return `"number"`; strings, booleans, and functions return
`"string"`, `"boolean"`, and `"function"`. Object literals, arrays, class
instances, and `null` return `"object"`.

Generic object annotations describe the key and value types:

```
let object<string, string> user = {
    "name": "Maya",
    "age": "21"
};
```

In X, annotations precede the variable name. The TypeScript-style
`let user: object<string, string>` form is not supported.

Backtick template literals may contain newlines and interpolate expressions
using braces without a `$` prefix:

```
let string greeting = `Hello {name}`;
let string report = `User: {getUserName()}
Status: {1 + 1}`;
```

Template interpolation evaluates expressions from left to right. `{{` and
`}}` produce literal braces. Interpolation is expression-based, not a statement
block. `print` accepts comma-separated expressions and joins their string
representations with spaces; `+` concatenates values inside an argument:

```
print("My Name " + "is", "Maya");
```

The standard library should provide additional string operations.

---

# 71\. Object Member Access

Members are accessed using `.`.

```
user.name
user.greet()
```

Static members:

```
Math.add(10, 20)
```

Nested types:

```
Http.Request
```

---

# 72\. `this`

Inside an instance member, `this` refers to the current object.

```
class User {

    private string name;

    public User(string name) {
        this.name = name;
    }
}
```

---

# 73\. `super`

Inside a derived class, `super` refers to the parent implementation.

```
class Dog extends Animal {

    public Dog(string name) {
        super(name);
    }
}
```

A parent method may be invoked using:

```
super.speak()
```

---

# 74\. Type Inference

X performs static type inference.

```
let integer x = 10;
```

can be written:

```
let x = 10;
```

Likewise:

```
let user = User("Alice");
```

The compiler infers the type as:

```
User
```

Inference does not make the language dynamically typed.

---

# 75\. Static Type Checking

The compiler rejects incompatible types.

Invalid:

```
integer x = "hello";
```

Invalid:

```
string function greet(integer value) {
    return value;
}
```

Valid:

```
string function greet(integer value) {
    return value.toString();
}
```

---

# 76\. Generic Constraints

Generic parameters may eventually support constraints.

Example reserved syntax:

```
class Box<T extends Comparable<T>> {
    ...
}
```

The exact constraint syntax is reserved for a future revision.

---

# 77\. Function Types

Function values are supported.

The formal function-type syntax is reserved for the next specification revision.

Conceptually:

```
(integer, integer) -> integer
```

represents a function accepting two integers and returning an integer.

This notation is descriptive only and does not change the established function declaration syntax.

---

# 78\. Compiler Architecture

An X implementation should use a pipeline similar to:

```
Source
   |
   v
Lexer
   |
   v
Parser
   |
   v
AST
   |
   v
Name Resolution
   |
   v
Type Checking
   |
   v
Semantic Analysis
   |
   v
Intermediate Representation
   |
   +----------------+
   |                |
   v                v
Interpreter      Compiler
                    |
                    v
              Native / Bytecode
```

---

# 79\. Lexer

The lexer converts source text into tokens.

For:

```
string function greet(string name) {
    return "Hello " + name;
}
```

the lexer produces tokens corresponding to:

```
STRING
FUNCTION
IDENTIFIER
LPAREN
STRING
IDENTIFIER
RPAREN
LBRACE
RETURN
STRING_LITERAL
PLUS
IDENTIFIER
SEMICOLON
RBRACE
```

---

# 80\. Parser

The parser transforms tokens into an Abstract Syntax Tree.

For:

```
string function greet(string name) {
    return "Hello " + name;
}
```

the AST conceptually contains:

```
FunctionDeclaration
├── returnType: string
├── name: greet
├── parameters
│   └── name: string
└── body
    └── ReturnStatement
        └── BinaryExpression
            ├── StringLiteral
            ├── +
            └── Identifier
```

---

# 81\. AST Representation

An implementation may represent declarations approximately as:

```
Declaration
├── ClassDeclaration
├── InterfaceDeclaration
├── EnumDeclaration
├── TypeDeclaration
├── FunctionDeclaration
├── VariableDeclaration
└── ConstantDeclaration
```

Types may be represented approximately as:

```
Type
├── Integer
├── Float
├── Double
├── Boolean
├── String
├── Char
├── Byte
├── Void
├── Named
├── Array
├── Nullable
├── Union
└── Generic
```

---

# 82\. Name Resolver

The resolver maps identifiers to declarations.

For:

```
import users.User
```

the resolver searches for:

```
users
    ↓
User
```

It then creates a local binding for `User`.

---

# 83\. Type Checker

The type checker verifies:

- assignments
- function calls
- method calls
- constructor calls
- inheritance
- interface implementation
- generic arguments
- nullable values
- union types
- return statements
- operators

---

# 84\. Overload Resolution

Given:

```
class User {

    public User(integer id) {
        ...
    }

    public User(string name) {
        ...
    }
}
```

the compiler resolves:

```
User(10)
```

to:

```
User(integer)
```

and:

```
User("Alice")
```

to:

```
User(string)
```

Ambiguous overloads are compile-time errors.

---

# 85\. Runtime

The runtime provides:

- object allocation
- memory management
- arrays
- strings
- exceptions
- method dispatch
- iterators
- command-line arguments
- standard library integration

The initial implementation may use garbage collection.

The memory-management strategy may be replaced or expanded in future versions.

---

# 86\. Standard Library

The X standard library is expected to provide modules such as:

```
collections
io
filesystem
math
time
cli
network
concurrency
text
serialization
reflection
```

Example:

```
import math.Math
import collections.List
import cli.Arguments
```

The Python reference interpreter additionally provides the following initial
file-system module:

```
import System.io.FileSystem
```

Its initial API is:

```
boolean exists(string path)
boolean isFile(string path)
boolean isDirectory(string path)
string readText(string path)
void writeText(string path, string content)
void appendText(string path, string content)
void createDirectory(string path)
string[] listDirectory(string path)
void deleteFile(string path)
void deleteDirectory(string path)
```

Every filesystem operation also has an awaitable version with an `Async`
suffix, such as `readTextAsync` and `writeTextAsync`. Async methods perform
blocking filesystem work on a worker thread; sync methods remain synchronous.
`await` is permitted only inside an `async` function and rejects non-async
values. The built-in `sleep(milliseconds)` returns an awaitable that resolves
after a non-negative integer or floating-point duration in milliseconds.

Text is UTF-8. Relative paths are resolved from the process working directory.
`writeText` replaces an existing file, while `appendText` creates the file if
it does not exist. `createDirectory` also creates missing parent directories.
`listDirectory` returns sorted immediate entry names. `deleteDirectory` only
removes an empty directory; neither delete operation recursively removes
content. The reference interpreter currently accesses files using the host
process permissions and does not sandbox X programs.

---

# 87\. File and Module Organization

A typical project may look like:

```
myapp/
│
├── main.x
├── users/
│   ├── User.x
│   └── Admin.x
│
├── database/
│   └── Postgres.x
│
└── utils/
    └── Logger.x
```

The package structure may correspond to:

```
myapp.users
myapp.database
myapp.utils
```

---

# 88\. Complete Example

## `main.x`

```
package myapp

import users.User
import users.Role
import collections.List

function main(string[] args) {

    if (args.length == 0) {
        print("Usage: app <name>");
        return;
    }

    let string name = args[0];

    let User[] users = [];

    for (integer i in range(0, 10, 1)) {

        let User user = User(
            i,
            name + i,
            Role.USER
        );

        users.add(user);
    }

    for (User user in users) {
        print(user.greet());
    }
}
```

## `users/User.x`

```
package users

export enum Role {

    ADMIN,
    USER,
    GUEST
}

export class User {

    private integer id;

    public string name;
    public Role role;

    public User(
        integer id,
        string name,
        Role role
    ) {
        this.id = id;
        this.name = name;
        this.role = role;
    }

    public string greet() {
        return "Hello " + this.name;
    }

    public class Metadata {

        public string source;

        public Metadata(string source) {
            this.source = source;
        }
    }
}
```

---

# 89\. Compilation Example

Given:

```
main.x
```

the basic compiler invocation is:

```
x main.x
```

A build command may be:

```
x build main.x
```

A run command may be:

```
x run main.x
```

With command-line arguments:

```
x run main.x Alice 123
```

The program receives:

```
args[0] = "Alice"
args[1] = "123"
```

subject to the implementation's executable-name convention.

---

# 90\. Complete Syntax Example

The following demonstrates several major X features together:

```
package example

import database.Postgres
import collections.List

export enum Role {

    ADMIN,
    USER
}

export interface Serializable {

    string serialize();
}

export type UserData = {

    string name;
    integer age;
}

export class User implements Serializable {

    private integer id;

    public string name;
    public integer age;
    public Role role;

    public User(integer id) {
        this.id = id;
        this.name = "Unknown";
        this.age = 0;
        this.role = Role.USER;
    }

    public User(
        integer id,
        string name
    ) {
        this.id = id;
        this.name = name;
        this.age = 0;
        this.role = Role.USER;
    }

    public User(
        integer id,
        string name,
        integer age,
        Role role
    ) {
        this.id = id;
        this.name = name;
        this.age = age;
        this.role = role;
    }

    public string greet() {
        return "Hello " + this.name;
    }

    public string serialize() {
        return this.name;
    }

    public class Metadata {

        public string source;

        public Metadata(string source) {
            this.source = source;
        }
    }
}

User? function findUser(integer id) {

    if (id == 1) {
        return User(
            1,
            "Alice",
            25,
            Role.USER
        );
    }

    return null;
}

function main(string[] args) {

    if (args.length == 0) {
        print("Please provide a name.");
        return;
    }

    let string name = args[0];

    let User[] users = [];

    for (integer i in range(0, 10, 1)) {

        let User user = User(
            i,
            name
        );

        users.add(user);
    }

    for (User user in users) {
        print(user.greet());
    }
}
```

---

# 91\. Formal Grammar

The following is the beginning of the X grammar.

```
program
    := declaration*

declaration
    := packageDeclaration
     | importDeclaration
     | exportDeclaration
     | classDeclaration
     | interfaceDeclaration
     | enumDeclaration
     | typeDeclaration
     | functionDeclaration
     | variableDeclaration
     | constantDeclaration

packageDeclaration
    := "package" qualifiedName

importDeclaration
    := "import" importPath
     | "import" importPath "as" identifier
     | "import" importPath "." "{"
            importList
       "}"
     | "import" importPath ".*"

functionDeclaration
    := optional(type)
       "function"
       identifier
       "(" parameterList? ")"
       block

methodDeclaration
    := modifier*
       type
       identifier
       "(" parameterList? ")"
       block

constructorDeclaration
    := modifier*
       identifier
       "(" parameterList? ")"
       block

classDeclaration
    := modifier*
       "class"
       identifier
       genericParameters?
       inheritanceClause?
       classBody

interfaceDeclaration
    := modifier*
       "interface"
       identifier
       genericParameters?
       interfaceInheritance?
       interfaceBody

enumDeclaration
    := modifier*
       "enum"
       identifier
       "{"
       enumMembers?
       "}"

typeDeclaration
    := modifier*
       "type"
       identifier
       "="
       type

forStatement
    := "for"
       "("
       type
       identifier
       "in"
       expression
       ")"
       block
```

The grammar will be expanded to cover every expression, operator, statement, declaration, and type construct in a future formal specification.

---

# 92\. Reserved Keywords

The initial reserved keyword set is:

```
abstract
as
break
catch
class
const
continue
else
enum
extends
false
finally
for
function
if
implements
import
in
interface
internal
let
new
null
package
private
protected
public
return
static
super
this
throw
true
try
type
void
while
export
override
virtual
record
```

Additional keywords may be added in future versions.

---

# 93\. Design Compatibility

X intentionally borrows familiar concepts from Java, C#, and TypeScript.

However, X does not attempt to be source-compatible with any of them.

Examples:

Java/C#-style classes:

```
class User {
    ...
}
```

TypeScript-style structural types:

```
type User = {
    string name;
}
```

C#/Java-style interfaces:

```
interface User {
    ...
}
```

TypeScript-like type unions:

```
type ID = string | integer;
```

Java/C#-style inheritance:

```
class Dog extends Animal {
    ...
}
```

X-specific function syntax:

```
string function greet(string name) {
    ...
}
```

---

# 94\. Implementation Strategy

The recommended implementation architecture is:

```
             X Source
                 |
                 v
              Lexer
                 |
                 v
              Parser
                 |
                 v
                AST
                 |
                 v
          Name Resolution
                 |
                 v
            Type Checker
                 |
                 v
        Semantic Analysis
                 |
                 v
               HIR
                 |
                 v
               MIR
                 |
          +------+------+
          |             |
          v             v
      Interpreter    Compiler
                        |
                        v
                 Native / Bytecode
```

The first X implementation should preferably begin with an interpreter.

Once the language semantics are stable, a compiler backend can be added.

---

# 95\. Recommended Implementation Language

The X compiler is independent of the language used to implement it.

A recommended implementation language is Rust because it provides:

- strong memory safety
- excellent performance
- algebraic data types useful for ASTs
- pattern matching
- good tooling
- suitable performance for compiler workloads
- a mature ecosystem for compiler development

A prototype may alternatively be implemented in TypeScript, C#, Kotlin, or Java.

---

# 96\. Compiler Commands

The initial command-line interface is:

```
x <file>.x
```

Recommended commands include:

```
x build main.x
x run main.x
x check main.x
x fmt main.x
x test
x version
x help
```

Compilation:

```
x build main.x
```

Run:

```
x run main.x
```

Type-check without producing an executable:

```
x check main.x
```

Format source:

```
x fmt main.x
```

Run tests:

```
x test
```

Display compiler version:

```
x version
```

---

# 97\. Exit Codes

X programs may return an integer exit code.

Example:

```
integer function main(string[] args) {

    if (args.length == 0) {
        return 1;
    }

    return 0;
}
```

The runtime passes the resulting value to the operating system as the process exit code.

A `void`/inferred-void `main` function returns a default success status.

---

# 98\. Versioning

This document represents:

```
X Language Specification 0.1
```

Version 0.x specifications are experimental.

Before X 1.0, syntax and semantics may change.

After X 1.0, breaking language changes should require a new language edition or major specification version.

---

# 99\. Features Reserved for Future Specifications

Potential future features include:

- lambda expressions
- closures
- generators
- pattern matching
- destructuring
- tuples
- operator overloading
- extension methods
- decorators/annotations
- reflection
- attributes
- advanced generic constraints
- concurrency primitives
- channels
- native interoperability
- foreign-function interfaces
- package manager
- build configuration
- macros
- compile-time execution
- dependency management

---

# 100\. Summary

The fundamental X syntax is:

### Variables

```
let integer x = 10;
let name = "Alice";
```

### Functions

```
function greet(string name) {
    return "Hello " + name;
}
```

or:

```
string function greet(string name) {
    return "Hello " + name;
}
```

### Methods

```
class User {

    public string greet() {
        return "Hello";
    }
}
```

### Constructors

```
class User {

    public User(integer id) {
        ...
    }

    public User(string name) {
        ...
    }
}
```

### Nested classes

```
class Foo {

    class Bar {

        public Bar(integer x) {
            ...
        }
    }
}
```

### Arrays

```
let User[] users;
```

### Interfaces

```
interface User {

    string getName();
}
```

### Types

```
type User = {

    string name;
    integer age;
}
```

### Enums

```
enum Role {

    ADMIN,
    USER
}
```

### Generics

```
class Box<T> {
    ...
}
```

### Loops

```
for (integer i in range(0, 10, 1)) {
    ...
}
```

### Imports

```
import something.Something
```

### Multiple imports

```
import something.{Something, SomethingElse}
```

### Wildcard imports

```
import something.*
```

### Exports

```
export class Something {
    ...
}
```

### Command-line arguments

```
function main(string[] args) {

    for (string argument in args) {
        print(argument);
    }
}
```

### Compilation

```
x main.x
```

### Running

```
x run main.x argument1 argument2
```

---

# End of X Language Specification — Draft 0.1

---

# Reference Interpreter Implementation Addendum

This addendum documents experimental features implemented by the Python
reference interpreter after the Draft 0.1 language proposal. These additions
describe the current interpreter; they do not claim source compatibility with
TypeScript or JavaScript and may change before a future X language edition.
Project setup, the full implemented-feature list, and runnable command examples
are maintained in `README.md`.

## A.1 Implementation Architecture

The interpreter follows this pipeline:

```text
CLI arguments and project root
    |
    v
ModuleLoader: resolve project imports and recognize built-in modules
    |
    v
Lexer: source text -> positioned tokens
    |
    v
Parser: tokens -> AST
    |
    v
Interpreter: register declarations and initialize module values
    |
    v
Evaluator: execute statements and evaluate expressions
    |
    v
Runtime values: environments, functions, classes, objects, enums, tasks, threads
```

The source responsibilities are:

- `xlang/cli.py`: command parsing, source execution, diagnostics, exit status.
- `xlang/module_loader.py`: project-relative import expansion and built-in
  standard-library imports.
- `xlang/lexer.py`: tokenization, keyword recognition, and source positions.
- `xlang/parser.py`: recursive-descent declarations and statements, and
  precedence-based expression parsing.
- `xlang/ast_nodes.py`: dataclasses representing source syntax.
- `xlang/runtime.py`: lexical environments, evaluation, class construction,
  built-ins, filesystem operations, asynchronous work, and thread handles.

The parser produces AST nodes. The interpreter first registers top-level
functions, classes, and enums so declarations can refer to each other, then
binds imports and initializes top-level variables. An environment stores local
names and a link to its parent environment. Function-call environments link to
the function's defining environment, providing lexical name lookup.

The implementation is an interpreter, not a native compiler. `x check` parses
the entry source and imports; `x build` currently performs this same check and
does not emit machine code or bytecode. Declared X types guide syntax and
runtime overload matching but are not checked by a static type checker.

## A.2 Constructor and Parent-Class Semantics

`new Type(arguments)` constructs a class instance. Construction allocates the
instance, initializes parent fields before child fields, resolves the
constructor by argument count and runtime argument types, executes it, and
returns the instance.

```x
class User {
    private string name;

    public User(string name) {
        this.name = name;
    }
}

let User user = new User("Ada");
```

Calling a class as `User("Ada")` is also supported as a convenience and uses
the same constructor dispatch.

A derived constructor explicitly calls its parent constructor through
`super(arguments...)`. A parent method is called through
`super.method(arguments...)`.

```x
class Animal {
    private string name;

    public Animal(string name) {
        this.name = name;
    }

    public string getName() {
        return this.name;
    }
}

class Dog extends Animal {
    public Dog(string name) {
        super(name);
    }

    public string speak() {
        return super.getName() + " says woof";
    }
}

let Dog dog = new Dog("Rex");
```

Parent constructor calls are explicit; the interpreter does not implicitly
invoke a parent constructor. Abstract-class instantiation checks and full
override validation are not implemented.

## A.3 Rest and Spread

X keeps its type-before-name parameter convention. The final parameter may be
variadic by putting `...` before its name. The body receives that parameter as
an array, including when no remaining arguments were passed.

```x
integer function sum(integer ...values) {
    let integer total = 0;
    for (integer value in values) {
        total += value;
    }
    return total;
}
```

Spread syntax expands arrays, tuples, or strings in array literals and call
arguments. Strings expand to their characters.

```x
let integer[] values = [1, 2, 3];
let integer[] combined = [0, ...values, 4];
let integer total = sum(...combined);
```

Object literals support `...object` entries. Object spread copies fields from
the source object; properties written later override earlier copied
properties.

```x
let object defaults = {name: "Ada", role: "Engineer"};
let object profile = {...defaults, role: "Architect"};
```

Object spread accepts object-literal maps and X instances' current fields. It
does not invoke getters, copy methods, or clone nested values.

## A.4 Iterable Loop Bindings

The iterable loop accepts explicit type syntax and inferred declaration syntax:

```x
for (integer value in values) {
    print(value);
}

for (let value in values) {
    print(value);
}

for (const value in values) {
    print(value);
}
```

`const` loop bindings cannot be reassigned within their iteration body.

## A.5 Asynchronous Functions

`async function` declares an asynchronous function. Calling it returns an
awaitable result. `await` evaluates an awaitable to its resolved value. An
async `main` is automatically awaited by the interpreter.

The built-in module is imported with:

```x
import System.concurrent.Async
```

`Async.delay(milliseconds, result?)` accepts a non-negative integer or
floating-point duration, waits for it, and resolves to `result`, or `null` when
no result is provided. `Async.all(awaitables)` accepts one array, waits for
every awaitable concurrently, and returns values in the original input order.
Non-awaitable values in that array pass through unchanged. `awaitable` is
descriptive runtime terminology here, not a statically checked X type.
The built-in `sleep(milliseconds)` is the direct sleep operation and resolves
after that many milliseconds. `await` may only appear inside an async function
and the awaited value must be asynchronous.

```x
import System.concurrent.Async

async function load(string label, integer milliseconds) {
    await Async.delay(milliseconds);
    return label;
}

async function main() {
    let string[] results = await Async.all([
        load("first", 30),
        load("second", 10)
    ]);
    print(results[0]);
    print(results[1]);
}
```

The interpreter's statement evaluator is synchronous. To support concurrent
awaitables without making every evaluator operation asynchronous, an X async
function's synchronous body runs on Python's worker-thread executor. Awaiting
an X awaitable runs the Python asyncio coroutine; `Async.all` schedules all
provided awaitables together. This is a prototype execution model, not the
ECMAScript event loop, Promise job queue, or TypeScript type system. Async code
is intended for overlapping awaitable/I/O-style work; it does not promise CPU
parallelism.

## A.6 OS Threads

The built-in thread module is imported with:

```x
import System.concurrent.Thread
```

`Thread.start(function, arguments?)` starts a real Python operating-system
thread that invokes an X function. The optional arguments value is an array;
omitting it invokes the function with no arguments. It returns a thread handle.

- `handle.join()` waits and returns the worker function's result.
- `handle.join(timeoutSeconds)` waits for at most the timeout and returns
  `null` if the thread is still running.
- `handle.isAlive()` returns whether the thread is still active.
- A worker failure is surfaced as an X runtime error when joining a completed
  worker.

Threads share the interpreter, environments, and mutable object instances. The
runtime does not add synchronization around shared values and currently has no
locks, atomics, cancellation, or thread-safe collection guarantees. Programs
must avoid unsynchronized shared mutable state.

## A.7 Demo Programs

The repository's executable examples are:

```text
examples/
├── configuration/
│   └── configured_args.x
├── control_flow/main.x
├── control_flow/main_file.x
├── decorators/trace.x
├── exceptions/exception_hierarchy.x
├── exceptions/try_catch_finally.x
├── namespaces/nested_classes.x
├── objects/destructuring.x
├── pattern_matching/match.x
├── errors/                  # deliberately failing diagnostic demonstrations
├── async_demo.x
├── filesystem_demo.x
├── oop_demo.x
├── queue_tests.x
├── rest_spread_demo.x
├── thread_demo.x
└── queue/
    ├── Queue.x
    └── QueueDemo.x
```

Run from the repository root:

```sh
x run --profile feature-tour examples/configuration/configured_args.x
x run examples/control_flow/main_file.x
x run examples/decorators/trace.x
x run examples/exceptions/exception_hierarchy.x examples/errors/missing.txt
x run examples/exceptions/try_catch_finally.x
x run examples/namespaces/nested_classes.x
x run examples/objects/destructuring.x
x run examples/pattern_matching/match.x
x run examples/queue_tests.x Ada
x run examples/filesystem_demo.x
x run examples/oop_demo.x
x run examples/rest_spread_demo.x
x run examples/async_demo.x
x run examples/thread_demo.x
```

These examples demonstrate grouped imports, generic classes, arrays,
loop forms, matching and destructuring, decorators, namespaces, nested
classes, enums, command-line arguments, queue tests, UTF-8 file operations,
`new`, constructors, inheritance, `super`, rest and spread, async/await, and
OS threads. Each example is implemented in X source and executed by the
Python interpreter.

## A.8 Current Boundaries

The runtime features in this addendum do not imply implementation of every
feature from the proposal. In particular, there is no static type checker,
native backend, isolated module namespace, full generic substitution,
enforced interfaces/abstract methods, thread
synchronization API, task cancellation, Promise rejection model, or
binary-file API. Refer to `README.md` for the current tested feature inventory
and API signatures.

One important thing I changed from the earlier draft is that **`range(0, 10, 1)` is now explicitly defined as `0` through `9`** (end-exclusive), so the language standard isn't ambiguous there.

## A.9 Additional Implemented Syntax and Runtime Contracts

This section documents the implemented interpreter subset, rather than
promising all ECMAScript, TypeScript, Java, or Rust semantics.

### A.9.1 Integer alias and automatic statement termination

`int` and `integer` are accepted as numeric type names and receive the same
runtime overload score. A statement may omit `;` when the next token begins on
a later source line, when the next token is `}`, or at EOF. Semicolons are
still required between the clauses of a classic `for` loop. This is a
statement-boundary rule, not a full ECMAScript ASI implementation. In
particular, a following `(` or `[` may continue the previous expression;
write an explicit semicolon when such a line could be ambiguous.

```x
int function main() {
    let int count = 2
    print(count)
    return count
}
```

### A.9.2 Destructuring, object literals, and Object helpers

Array and object destructuring declarations support nesting, defaults for
missing/null values, and rest bindings. Plain variable targets are supported
in destructuring assignment; assignment targets such as `object.field` are
not. Object literals accept identifier keys, quoted string keys, shorthand
properties, and spread. Spread copies enumerable dictionary fields into a new
object literal. They do not have JavaScript prototypes or property descriptors.

```x
const [head, fallback = 0, ...tail] = [10]
const {name, role: title, ...metadata} = {
    name: "Ada",
    role: "engineer",
    active: true
}
let first = 0
let second = 0
[first, second] = [1, 2]
```

The built-in `Object` namespace exposes `keys(object)`, `values(object)`,
`entries(object)`, `assign(target, source...)`, and `hasOwn(object, key)`.
These operations accept X object-literal dictionaries only. Computed keys,
symbols, object prototypes, anonymous methods, getters/setters, and complete
ECMAScript destructuring behavior are outside this implementation.

### A.9.3 Loops and matching

Supported loops are `while`, `do { ... } while (condition)`, classic
`for (initializer; condition; increment)`, `for (let item of values)`, and
`for (let key in object)`. In an `in` loop, maps and instances yield field
names; other iterable values yield their values for compatibility with X's
original typed `for (Type value in iterable)` form. `of` yields iterable
values. Loop bindings may use array/object destructuring. `break` and
`continue` are supported.

`match expression { pattern => expression, ... }` supports `_`, bindings,
primitive literals, enum members, array/object patterns, array/object rest,
alternatives with `|`, and `if` guards. A match expression must include at
least one arm; runtime selection is first-match-wins. The interpreter does not
perform exhaustiveness or unreachable-arm analysis, and enum variants do not
carry payloads.

Enums may be declared at module scope, in class bodies, inside functions, and
inside nested blocks. Their names follow lexical scope: a nested declaration
can shadow an outer enum, and enum values from distinct declarations remain
distinct even if the enum names and member names are identical. Enum patterns
resolve their enum name from the active lexical scope.

### A.9.4 Exceptions and equality

`try` may have multiple ordered `catch` clauses, each optionally typed, and an
optional `finally`. Catch types may be listed as a union using `|`. Thrown X
values retain their value; supported interpreter/runtime failures are wrapped
as `RuntimeException` values exposing `name`, `message`, `cause`, and `stack`.
The first matching catch executes. Unmatched errors propagate, and `finally`
runs during normal completion, thrown errors, and control-flow returns. This
runtime exception hierarchy is intentionally smaller than Java's.

`==` performs a limited conversion among `null`, booleans, numbers, and numeric
strings. `===` does not convert types; arrays, dictionaries, instances,
classes, and functions compare by reference identity. Enum members compare
equal only when both the enum name and member name match, including for `==`;
equal payload values from different enums are not equal.

### A.9.5 Decorators, namespaces, and nested classes

Decorators use `@decorator` syntax on functions, classes, constructors, and
methods. They are evaluated when the declaration is registered, applied from
bottom to top, and must return a function or class of the corresponding kind.
The built-in `@trace` logs function calls and class construction. The runtime
does not yet implement decorator metadata or property/field decorators.

`namespace A.B { ... }` creates reopenable nested namespace scopes. Names are
accessed by qualified member syntax, such as `A.B.make()`. Nested class
declarations are members of an enclosing class and support lookup/construction
as `Outer.Inner` and `new Outer.Inner(...)`. These scopes use the interpreter's
chained `Environment` objects; they are not isolated compiled modules or
access-control boundaries.

### A.9.6 Interpreter architecture update

Declaration registration builds top-level and nested `Environment` scopes.
Function and class decorators execute during registration; class registration
recursively registers nested classes and captures the class environment.
Enum declarations are also valid statements, so they are defined in the
environment of the block where they appear; enum patterns use that same
environment for name resolution.

Project imports resolve beside the importing source before falling back to
the configured project root. Entry modules may contain executable top-level
statements; the interpreter executes them and skips implicit `main` dispatch
so an explicitly imported `main()` call is not repeated.

#### Language change principle

When an example exposes unexpected behavior or an error, first define the
intended language rule and its scope, then fix the grammar and semantic path
that enforce that rule. Do not special-case the example or patch only one
runtime symptom. Add regression tests for the underlying rule, including
related scope and interaction cases, and update this specification and runnable
examples. This keeps one language feature consistent across parsing, runtime
behavior, and diagnostics.

Statement execution dispatches loops and try/catch/finally nodes through the
same evaluator. Destructuring uses pattern AST nodes shared with `match`, but
has a separate binding phase because declarations create names while
assignments update existing names. Object helpers are built-in runtime
functions, and ASI decisions use the source line/column positions retained on
lexer tokens. The full implementation and runnable tests are in `xlang/` and
`tests/test_interpreter.py`.

## A.10 TOML Project Configuration and CLI Arguments

The interpreter loads `x.toml` by searching upward from the working
directory. An explicit `--config path/to/file.toml` selects a configuration;
`--no-config` disables both explicit and discovered configuration. TOML is
validated strictly: unknown section keys, unknown feature names, invalid
value types, invalid color modes, and missing run profiles are reported as
configuration errors. Python 3.11+ reads TOML with `tomllib`; Python 3.10 uses
the conditional `tomli` dependency.

The supported schema is:

```toml
[cli]
default-command = "run" # run, check, or build; used by x file.x shorthand
color = "auto"          # auto, always, or never

[features]
classes = true
pattern_matching = false

[run]
args = ["configured", "value with spaces"]

[run.environment]
APP_MODE = "development"

[run.profiles.test]
args = ["test-only"]

[run.profiles.test.environment]
APP_MODE = "test"
```

Feature flags available in this implementation are `async`, `classes`,
`decorators`, `destructuring`, `enums`, `equality`, `exceptions`, `filesystem`,
`loops`, `namespaces`, `object_literals`, `pattern_matching`, `spread`, and
`threads`; each is enabled by default. A flag set to `false` makes the parser
reject corresponding syntax or prevents loading its standard-library module.
For example, `--feature classes=off` overrides a TOML setting for one CLI
invocation. `--feature NAME=on|off` may be repeated to set multiple flags.

At runtime, arguments are concatenated in this order: `[run].args`, selected
profile arguments, then command-line arguments after the `--` delimiter.
Array entries are preserved as individual strings, including spaces.
Configured environment values overlay the process environment, and profile
values overlay base run values. X code reads an effective environment value
directly as `System.Environment.NAME`, without importing the environment
module or mutating the parent process. `System.Environment.has(name)` and
`System.Environment.all()` are also available. Profiles are selected with
`--profile NAME`.
Explicit `run`, `check`, or `build` commands override `default-command`.

## A.11 Access Modifiers, Final Classes, and Diagnostics

Class properties and methods support enforced `public`, `protected`, and
`private` access. No modifier means `public`. Private members are accessible
only from code executing in their declaring class. Protected members are
accessible from the declaring class and derived classes. These checks cover
instance and static properties, assignments, method lookup, and nested class
lookup. The prototype rejects `internal`: its module loader currently merges
project declarations and has no module/package visibility boundary.

`final class Name { ... }` prevents any later class declaration from extending
`Name`; class registration reports the error before `main` begins. Static
type-checking and access diagnostics at compile time are not provided; the
interpreter detects illegal member access at runtime.

Lexer, parser, runtime, and TOML errors are rendered with an error heading,
source path, line and column when known, the relevant source line, and a
caret. ANSI colors are enabled automatically on a terminal, can be forced
with `--color always`, and can be disabled with `--color never` or `NO_COLOR`.
Runtime errors use the beginning of the active statement as their location;
the current AST does not track token spans for each expression.

The intentionally invalid programs under `examples/errors/` show private
member access, final-class extension, runtime arithmetic failure, and syntax
error diagnostics.

String values support integer indexing and `.length`. Indexes follow Python
sequence behavior: each index is a Unicode code point, negative indexes count
from the end, and out-of-range indexes raise a runtime error. Grapheme
clusters are not counted, and this differs from JavaScript UTF-16 indexing for
some Unicode characters.

The next logical step is to turn this from a **feature-level specification into an actual implementable X v0.1 specification**: define the complete grammar and then design the Rust compiler's `lexer → parser → AST → type checker → interpreter` in detail.
