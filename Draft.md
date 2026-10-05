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
```

Declarations are private to the module unless exported.

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

X uses qualified imports.

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

The final component is imported into the current namespace.

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
- async/await
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

One important thing I changed from the earlier draft is that **`range(0, 10, 1)` is now explicitly defined as `0` through `9`** (end-exclusive), so the language standard isn't ambiguous there.

The next logical step is to turn this from a **feature-level specification into an actual implementable X v0.1 specification**: define the complete grammar and then design the Rust compiler's `lexer → parser → AST → type checker → interpreter` in detail.
