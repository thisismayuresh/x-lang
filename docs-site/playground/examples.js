/* Starter programs for the X playground. */

"use strict";

window.X_PLAYGROUND_EXAMPLES = [
  {
    id: "hello",
    label: "Hello, world",
    code: [
      "function greet(name) {",
      "    return `Hello, {name}!`;",
      "}",
      "",
      "print(greet(\"world\"));"
    ].join("\n")
  },
  {
    id: "fibonacci",
    label: "Fibonacci",
    code: [
      "integer function fib(integer n) {",
      "    if (n <= 1) {",
      "        return n;",
      "    }",
      "    return fib(n - 1) + fib(n - 2);",
      "}",
      "",
      "for (let i = 0; i < 10; i = i + 1) {",
      "    print(`fib({i}) = {fib(i)}`);",
      "}"
    ].join("\n")
  },
  {
    id: "classes",
    label: "Classes & exceptions",
    code: [
      "class BankAccount {",
      "    string owner;",
      "    float balance;",
      "",
      "    public BankAccount(string owner, float balance) {",
      "        this.owner = owner;",
      "        this.balance = balance;",
      "    }",
      "",
      "    public void deposit(float amount) {",
      "        if (amount <= 0) {",
      "            throw new Exception(\"Deposit must be positive\");",
      "        }",
      "        this.balance = this.balance + amount;",
      "    }",
      "",
      "    public void describe() {",
      "        print(`{this.owner} owns {this.balance}`);",
      "    }",
      "}",
      "",
      "let account = new BankAccount(\"Ada\", 100.0);",
      "account.deposit(50.0);",
      "account.describe();",
      "",
      "try {",
      "    account.deposit(-5);",
      "} catch (error) {",
      "    print(`Error: {error.message}`);",
      "} finally {",
      "    print(\"Done.\");",
      "}"
    ].join("\n")
  },
  {
    id: "pattern-matching",
    label: "Pattern matching",
    code: [
      "enum Result {",
      "    SUCCESS,",
      "    FAILURE",
      "}",
      "",
      "any function describe(object value) {",
      "    return match value {",
      "        null => \"no result\",",
      "        [code, ...details] if code == 200 =>",
      "            \"success with \" + details.length + \" detail(s)\",",
      "        {kind: \"error\", message: message} => \"error: \" + message,",
      "        Result.SUCCESS => \"success enum\",",
      "        _ => \"unrecognized\"",
      "    };",
      "}",
      "",
      "print(describe([200, \"cached\", \"fast\"]));",
      "print(describe({kind: \"error\", message: \"offline\"}));",
      "print(describe(Result.SUCCESS));",
      "print(describe(42));"
    ].join("\n")
  },
  {
    id: "collections",
    label: "Collections",
    code: [
      "let names = new List();",
      "names.add(\"ada\");",
      "names.add(\"grace\");",
      "names.add(\"alan\");",
      "",
      "print(`size: {names.size()}`);",
      "for (let i = 0; i < names.size(); i = i + 1) {",
      "    print(`- {names.get(i)}`);",
      "}",
      "",
      "let scores = new HashMap();",
      "scores.put(\"ada\", 10);",
      "scores.put(\"grace\", 20);",
      "print(scores.get(\"grace\"));"
    ].join("\n")
  },
  {
    id: "math",
    label: "Math library",
    code: [
      "import System.utils.Math",
      "",
      "print(\"sqrt(16):\", Math.sqrt(16));",
      "print(\"pow(2, 10):\", Math.pow(2, 10));",
      "print(\"max(1, 5, 3):\", Math.max(1, 5, 3));",
      "print(\"factorial(5):\", Math.factorial(5));"
    ].join("\n")
  },
  {
    id: "errors",
    label: "Type error demo",
    code: [
      "// The playground type-checks before running.",
      "// Fix the annotation (or the value) and press Run again.",
      "let int count = \"many\";",
      "print(count);"
    ].join("\n")
  },
  {
    id: "multi-file",
    label: "Multi-file project",
    code: [
      "import util.greet;",
      "",
      "print(greet(\"Ada\"));"
    ].join("\n"),
    files: [
      {
        name: "main.x",
        content: [
          "import util.greet;",
          "",
          "print(greet(\"Ada\"));"
        ].join("\n")
      },
      {
        name: "util.x",
        content: [
          "export string function greet(string name) {",
          "    return `Hello, {name}!`;",
          "}"
        ].join("\n")
      }
    ]
  }
];
