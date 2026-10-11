/* Completion catalog for the X playground editor.
   Each entry: { text, displayText?, type, detail?, snippet? }
   type: keyword | type | builtin | class | method | property | namespace | snippet
*/

"use strict";

window.X_COMPLETIONS = {
  /* Primitive / declaration types — offered in type positions. */
  types: [
    { text: "integer", type: "type", detail: "whole number" },
    { text: "int", type: "type", detail: "alias for integer" },
    { text: "float", type: "type", detail: "decimal number" },
    { text: "string", type: "type", detail: "text" },
    { text: "boolean", type: "type", detail: "true / false" },
    { text: "any", type: "type", detail: "any value" },
    { text: "void", type: "type", detail: "no return value" },
    { text: "var", type: "type", detail: "inferred variable" }
  ],

  keywords: [
    { text: "abstract", type: "keyword", detail: "abstract class member" },
    { text: "as", type: "keyword", detail: "import alias" },
    { text: "async", type: "keyword", detail: "async function" },
    { text: "await", type: "keyword", detail: "wait for async result" },
    { text: "break", type: "keyword", detail: "exit loop / switch" },
    { text: "case", type: "keyword", detail: "switch branch" },
    { text: "catch", type: "keyword", detail: "handle exception" },
    { text: "class", type: "keyword", detail: "declare a class" },
    { text: "const", type: "keyword", detail: "immutable binding" },
    { text: "continue", type: "keyword", detail: "next loop iteration" },
    { text: "default", type: "keyword", detail: "switch default" },
    { text: "do", type: "keyword", detail: "do…while loop" },
    { text: "else", type: "keyword", detail: "alternate branch" },
    { text: "enum", type: "keyword", detail: "enumerate values" },
    { text: "export", type: "keyword", detail: "export declaration" },
    { text: "extends", type: "keyword", detail: "inherit a class" },
    { text: "finally", type: "keyword", detail: "always run block" },
    { text: "for", type: "keyword", detail: "for loop" },
    { text: "function", type: "keyword", detail: "declare a function" },
    { text: "if", type: "keyword", detail: "conditional" },
    { text: "import", type: "keyword", detail: "import a module" },
    { text: "implements", type: "keyword", detail: "implement interfaces" },
    { text: "in", type: "keyword", detail: "for-in / membership" },
    { text: "interface", type: "keyword", detail: "declare an interface" },
    { text: "let", type: "keyword", detail: "mutable binding" },
    { text: "match", type: "keyword", detail: "pattern match" },
    { text: "namespace", type: "keyword", detail: "namespace block" },
    { text: "new", type: "keyword", detail: "construct instance" },
    { text: "of", type: "keyword", detail: "for-of loop" },
    { text: "override", type: "keyword", detail: "override method" },
    { text: "private", type: "keyword", detail: "private access" },
    { text: "protected", type: "keyword", detail: "protected access" },
    { text: "public", type: "keyword", detail: "public access" },
    { text: "return", type: "keyword", detail: "return from function" },
    { text: "static", type: "keyword", detail: "static member" },
    { text: "super", type: "keyword", detail: "parent constructor / method" },
    { text: "switch", type: "keyword", detail: "switch statement" },
    { text: "this", type: "keyword", detail: "current instance" },
    { text: "throw", type: "keyword", detail: "raise exception" },
    { text: "try", type: "keyword", detail: "try block" },
    { text: "virtual", type: "keyword", detail: "virtual method" },
    { text: "while", type: "keyword", detail: "while loop" },
    { text: "with", type: "keyword", detail: "with statement" },
    { text: "null", type: "keyword", detail: "null value" },
    { text: "true", type: "keyword", detail: "boolean true" },
    { text: "false", type: "keyword", detail: "boolean false" }
  ],

  builtins: [
    { text: "print", type: "builtin", detail: "print(…values)", snippet: "print($1)$0" },
    { text: "println", type: "builtin", detail: "print with newline" },
    { text: "typeOf", type: "builtin", detail: "typeOf(value) → string" },
    { text: "length", type: "property", detail: "array / string length" },
    { text: "System", type: "namespace", detail: "standard library root" }
  ],

  /* Classes / constructors you can `new`. */
  classes: [
    { text: "List", type: "class", detail: "dynamic array", snippet: "new List()" },
    { text: "LinkedList", type: "class", detail: "linked list", snippet: "new LinkedList()" },
    { text: "HashMap", type: "class", detail: "key → value map", snippet: "new HashMap()" },
    { text: "LinkedHashMap", type: "class", detail: "ordered map", snippet: "new LinkedHashMap()" },
    { text: "TreeMap", type: "class", detail: "sorted map", snippet: "new TreeMap()" },
    { text: "Set", type: "class", detail: "unique values", snippet: "new Set()" },
    { text: "TreeSet", type: "class", detail: "sorted set", snippet: "new TreeSet()" },
    { text: "Stack", type: "class", detail: "LIFO stack", snippet: "new Stack()" },
    { text: "Queue", type: "class", detail: "FIFO queue", snippet: "new Queue()" },
    { text: "PriorityQueue", type: "class", detail: "priority queue", snippet: "new PriorityQueue()" },
    { text: "LinkedList", type: "class", detail: "linked list", snippet: "new LinkedList()" },
    { text: "Trie", type: "class", detail: "prefix tree", snippet: "new Trie()" },
    { text: "LRUCache", type: "class", detail: "LRU cache", snippet: "new LRUCache()" },
    { text: "Exception", type: "class", detail: "base exception", snippet: "new Exception(\"message\")" },
    { text: "IOException", type: "class", detail: "I/O exception", snippet: "new IOException(\"message\")" }
  ],

  snippets: [
    {
      text: "function",
      type: "snippet",
      detail: "function name(args) { … }",
      snippet: "function $1($2) {\n    $0\n}"
    },
    {
      text: "void function",
      type: "snippet",
      detail: "void function name(args) { … }",
      snippet: "void function $1($2) {\n    $0\n}"
    },
    {
      text: "class",
      type: "snippet",
      detail: "class Name { … }",
      snippet: "class $1 {\n    $0\n}"
    },
    {
      text: "interface",
      type: "snippet",
      detail: "interface Name { … }",
      snippet: "interface $1 {\n    $0\n}"
    },
    {
      text: "for",
      type: "snippet",
      detail: "for (let i = 0; …)",
      snippet: "for (let $1 = 0; $1 < $2; $1 = $1 + 1) {\n    $0\n}"
    },
    {
      text: "for-in",
      type: "snippet",
      detail: "for (item of items)",
      snippet: "for (let $1 of $2) {\n    $0\n}"
    },
    {
      text: "while",
      type: "snippet",
      detail: "while (cond) { … }",
      snippet: "while ($1) {\n    $0\n}"
    },
    {
      text: "if",
      type: "snippet",
      detail: "if (cond) { … }",
      snippet: "if ($1) {\n    $0\n}"
    },
    {
      text: "try",
      type: "snippet",
      detail: "try / catch / finally",
      snippet: "try {\n    $1\n} catch ($2) {\n    $0\n}"
    }
  ],

  /* After a `.` — members by receiver (matched loosely on the token name). */
  members: {
    "*": [
      { text: "length", type: "property", detail: "size of array/string" },
      { text: "size", type: "method", detail: "collection size()" },
      { text: "toString", type: "method", detail: "stringify value" },
      { text: "message", type: "property", detail: "exception message" },
      { text: "name", type: "property", detail: "type / exception name" }
    ],
    List: [
      { text: "add", type: "method", detail: "add(value)" },
      { text: "get", type: "method", detail: "get(index)" },
      { text: "set", type: "method", detail: "set(index, value)" },
      { text: "remove", type: "method", detail: "remove(index)" },
      { text: "size", type: "method", detail: "size()" },
      { text: "isEmpty", type: "method", detail: "isEmpty()" },
      { text: "contains", type: "method", detail: "contains(value)" },
      { text: "indexOf", type: "method", detail: "indexOf(value)" },
      { text: "clear", type: "method", detail: "clear()" },
      { text: "push", type: "method", detail: "push(value)" },
      { text: "pop", type: "method", detail: "pop()" },
      { text: "map", type: "method", detail: "map(callback)" },
      { text: "filter", type: "method", detail: "filter(callback)" },
      { text: "reduce", type: "method", detail: "reduce(callback, init)" },
      { text: "join", type: "method", detail: "join(separator)" },
      { text: "slice", type: "method", detail: "slice(start, end)" }
    ],
    LinkedList: [
      { text: "add", type: "method", detail: "add(value)" },
      { text: "get", type: "method", detail: "get(index)" },
      { text: "remove", type: "method", detail: "remove(index)" },
      { text: "size", type: "method", detail: "size()" },
      { text: "isEmpty", type: "method", detail: "isEmpty()" }
    ],
    HashMap: [
      { text: "put", type: "method", detail: "put(key, value)" },
      { text: "get", type: "method", detail: "get(key)" },
      { text: "remove", type: "method", detail: "remove(key)" },
      { text: "containsKey", type: "method", detail: "containsKey(key)" },
      { text: "keys", type: "method", detail: "keys()" },
      { text: "values", type: "method", detail: "values()" },
      { text: "size", type: "method", detail: "size()" },
      { text: "isEmpty", type: "method", detail: "isEmpty()" },
      { text: "clear", type: "method", detail: "clear()" }
    ],
    Set: [
      { text: "add", type: "method", detail: "add(value)" },
      { text: "remove", type: "method", detail: "remove(value)" },
      { text: "contains", type: "method", detail: "contains(value)" },
      { text: "size", type: "method", detail: "size()" },
      { text: "isEmpty", type: "method", detail: "isEmpty()" }
    ],
    Stack: [
      { text: "push", type: "method", detail: "push(value)" },
      { text: "pop", type: "method", detail: "pop()" },
      { text: "peek", type: "method", detail: "peek()" },
      { text: "size", type: "method", detail: "size()" },
      { text: "isEmpty", type: "method", detail: "isEmpty()" }
    ],
    Queue: [
      { text: "enqueue", type: "method", detail: "enqueue(value)" },
      { text: "dequeue", type: "method", detail: "dequeue()" },
      { text: "peek", type: "method", detail: "peek()" },
      { text: "size", type: "method", detail: "size()" },
      { text: "isEmpty", type: "method", detail: "isEmpty()" }
    ],
    Math: [
      { text: "sqrt", type: "method", detail: "sqrt(x)" },
      { text: "pow", type: "method", detail: "pow(base, exp)" },
      { text: "abs", type: "method", detail: "abs(x)" },
      { text: "max", type: "method", detail: "max(a, b, …)" },
      { text: "min", type: "method", detail: "min(a, b, …)" },
      { text: "floor", type: "method", detail: "floor(x)" },
      { text: "ceil", type: "method", detail: "ceil(x)" },
      { text: "round", type: "method", detail: "round(x)" },
      { text: "random", type: "method", detail: "random()" },
      { text: "randomInt", type: "method", detail: "randomInt(max)" },
      { text: "factorial", type: "method", detail: "factorial(n)" },
      { text: "gcd", type: "method", detail: "gcd(a, b)" },
      { text: "lcm", type: "method", detail: "lcm(a, b)" },
      { text: "sin", type: "method", detail: "sin(x)" },
      { text: "cos", type: "method", detail: "cos(x)" },
      { text: "tan", type: "method", detail: "tan(x)" },
      { text: "log", type: "method", detail: "log(x)" },
      { text: "log2", type: "method", detail: "log2(x)" },
      { text: "log10", type: "method", detail: "log10(x)" },
      { text: "exp", type: "method", detail: "exp(x)" },
      { text: "pi", type: "property", detail: "π constant" },
      { text: "e", type: "property", detail: "Euler's number" }
    ],
    string: [
      { text: "toUpperCase", type: "method", detail: "toUpperCase()" },
      { text: "toLowerCase", type: "method", detail: "toLowerCase()" },
      { text: "trim", type: "method", detail: "trim()" },
      { text: "includes", type: "method", detail: "includes(text)" },
      { text: "indexOf", type: "method", detail: "indexOf(text)" },
      { text: "slice", type: "method", detail: "slice(start, end)" },
      { text: "substring", type: "method", detail: "substring(start, end)" },
      { text: "split", type: "method", detail: "split(separator)" },
      { text: "replace", type: "method", detail: "replace(from, to)" },
      { text: "charAt", type: "method", detail: "charAt(index)" },
      { text: "length", type: "property", detail: "character count" }
    ],
    System: [
      { text: "io", type: "namespace", detail: "System.io" },
      { text: "utils", type: "namespace", detail: "System.utils" },
      { text: "process", type: "namespace", detail: "System.process" },
      { text: "concurrent", type: "namespace", detail: "System.concurrent" },
      { text: "Throwable", type: "class", detail: "base throwable" },
      { text: "Exception", type: "class", detail: "Exception" },
      { text: "IOException", type: "class", detail: "IOException" }
    ],
    utils: [
      { text: "Math", type: "namespace", detail: "import System.utils.Math" },
      { text: "JSON", type: "namespace", detail: "import System.utils.JSON" },
      { text: "Collections", type: "namespace", detail: "collections root" }
    ],
    io: [
      { text: "Console", type: "namespace", detail: "console helpers" },
      { text: "FileSystem", type: "namespace", detail: "file system" },
      { text: "Network", type: "namespace", detail: "HTTP client" }
    ],
    JSON: [
      { text: "toJSON", type: "method", detail: "toJSON(value, indent?)" }
    ],
    FileSystem: [
      { text: "readText", type: "method", detail: "readText(path)" },
      { text: "writeText", type: "method", detail: "writeText(path, text)" },
      { text: "appendText", type: "method", detail: "appendText(path, text)" },
      { text: "exists", type: "method", detail: "exists(path)" },
      { text: "isFile", type: "method", detail: "isFile(path)" },
      { text: "isDirectory", type: "method", detail: "isDirectory(path)" },
      { text: "listDirectory", type: "method", detail: "listDirectory(path)" },
      { text: "createDirectory", type: "method", detail: "createDirectory(path)" },
      { text: "deleteFile", type: "method", detail: "deleteFile(path)" },
      { text: "deleteDirectory", type: "method", detail: "deleteDirectory(path)" }
    ]
  },

  /* Tokens that should prefer type suggestions when typed as a prefix. */
  typeKeywords: ["integer", "int", "float", "string", "boolean", "any", "void", "var"]
};
