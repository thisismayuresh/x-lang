#!/usr/bin/env python3
"""Regenerate the regression corpus module tests/corpus_data.py.

Usage (from the repository root):

    .venv/bin/python tests/generate_corpus.py [--sample N] [--no-verify]

Every authored case optionally carries expectations (Python-mirrored where the
semantics were verified to match, hand-written elsewhere); every case is then
executed through the real X pipeline.  Authored expectations that disagree with
the pipeline abort generation (unless ``--no-verify``), and ``--sample N``
prints N rows per group for manual review before the generated rows are
trusted.

The single generated file is tests/corpus_data.py (a ROWS list consumed by
tests/test_corpus.py).
"""

from __future__ import annotations

import argparse
import re
import signal
import sys
import tempfile
from dataclasses import asdict, dataclass
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for _extra in (str(HERE), str(ROOT)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from corpus_lib import CaseResult, execute_case, write_module
from xlang.config import XConfig
from xlang.lexer import LexError, Lexer
from xlang.module_loader import ModuleLoader
from xlang.parser import ParseError
from xlang.runtime import Interpreter
from xlang.typecheck import TypeChecker

ID_PREFIX = {"run": "R", "check": "C", "error": "E", "format": "F"}
KIND_ORDER = ("run", "check", "error", "format")


@dataclass
class Case:
    kind: str
    category: str
    name: str
    source: str
    expect_stdout: str | None = None
    expect_error: str | None = None
    expect_exit: int | None = None
    phase: str = ""
    notes: str = ""


def main_src(body: str) -> str:
    return "function main() {\n" + body + "\n}\n"


class _Timeout(Exception):
    """Raised when a generated source runs past the per-case time budget."""


@contextmanager
def time_limit(seconds: int = 6):
    def _handler(_signum, _frame):
        raise _Timeout()

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def try_execute(kind: str, source: str, workdir: Path) -> CaseResult | None:
    """Execute *source*, returning None when it exceeds the time budget."""
    try:
        with time_limit():
            return execute_case(kind, source, workdir)
    except _Timeout:
        return None


def py_eval(expression: str):
    return eval(expression, {"__builtins__": {}}, {})


def py_str(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def safe_py(expression: str) -> str | None:
    """Python-rendered expectation, or None when the form is not portable."""
    try:
        text = py_str(py_eval(expression))
    except Exception:  # noqa: BLE001 - any unevaluable form falls back to golden
        return None
    lowered = text.lower()
    if "e+" in lowered or "e-" in lowered:
        return None
    return text


def auth(
    cases: list[Case],
    category: str,
    name: str,
    expression: str,
    expected: str,
) -> None:
    """Append a run case asserting ``print(<expression>)`` prints *expected*."""
    cases.append(
        Case("run", category, name, main_src(f"print({expression});"),
             expect_stdout=expected)
    )


def golden(cases: list[Case], category: str, name: str, source: str) -> None:
    """Append a run case whose output is captured from the live pipeline."""
    cases.append(Case("run", category, name, source))


INT_PAIRS = [
    (7, 3), (10, 5), (-7, 3), (2, 10), (0, 5), (12, 4), (9, 2),
    (1000000, 1000000), (1, 1),
]
FLOAT_PAIRS = [(-7.5, 2), (0.5, 0.25), (1.5, 4), (0.1, 0.2), (9.75, 0.25)]
NUMBER_OPS = ("+", "-", "*", "/", "%")


def arith_cases() -> list[Case]:
    cases: list[Case] = []
    for op in NUMBER_OPS:
        for left, right in [*INT_PAIRS, *FLOAT_PAIRS]:
            if right == 0 and op in ("/", "%"):
                continue
            source_expression = f"{left!r} {op} {right!r}"
            expected = safe_py(f"{left} {op} {right}")
            if expected is None:
                golden(cases, "arith", source_expression,
                       main_src(f"print({source_expression});"))
            else:
                auth(cases, "arith", source_expression, source_expression, expected)
    auth(cases, "arith", "print float with integral value", "2.0", "2.0")
    auth(cases, "arith", "arbitrary precision addition",
         "9223372036854775807 + 1", "9223372036854775808")
    auth(cases, "arith", "float rounding of 0.1 + 0.2", "0.1 + 0.2",
         "0.30000000000000004")
    auth(cases, "arith", "unary minus before literal", "-3 + 5", "2")
    auth(cases, "arith", "modulus by negative divisor", "7 % -3", "-2")
    golden(cases, "arith", "string to number coercion via arithmetic",
           main_src('print("5" + 1);'))
    return cases


PRECEDENCE_EXPRESSIONS = (
    "2 + 3 * 4",
    "(2 + 3) * 4",
    "2 * 3 + 4",
    "10 - 2 - 3",
    "100 / 10 / 2",
    "2 + 3 * 4 - 6 / 2",
    "2 * -3",
    "3 % 4 + 5",
    "1 + 2 * 3 % 4",
    "2 * (3 + 4) - 5",
    "(1 + 2) * (3 + 4)",
    "-(2 + 3) * 2",
)


def precedence_cases() -> list[Case]:
    cases: list[Case] = []
    for expression in PRECEDENCE_EXPRESSIONS:
        expected = safe_py(expression)
        if expected is None:
            golden(cases, "precedence", expression,
                   main_src(f"print({expression});"))
        else:
            auth(cases, "precedence", expression, expression, expected)
    auth(cases, "precedence", "string concatenation chain",
         '"a" + "b" + "c"', "abc")
    auth(cases, "precedence", "number then string concatenation",
         '1 + " file(s)"', "1 file(s)")
    return cases


CMP_OPS = ("<", ">", "<=", ">=", "==", "!=")
CMP_PAIRS = [(1, 2), (2, 2), (3, 2), (-1, 1), (0, 0), (1.5, 1), (10, 10.0)]

AUTHORED_COMPARE = (
    ('1 == "1"', "true"),
    ('1 === "1"', "false"),
    ('1 != "1"', "false"),
    ('1 !== "1"', "true"),
    ("null == 0", "false"),
    ("null == false", "false"),
    ("null == null", "true"),
    ("null === null", "true"),
    ("3 > 2 > 1", "false"),
    ('"a" == "a"', "true"),
    ('"a" === "a"', "true"),
    ("true == 1", "true"),
    ("true === 1", "false"),
)


def compare_cases() -> list[Case]:
    cases: list[Case] = []
    for op in CMP_OPS:
        for left, right in CMP_PAIRS:
            expression = f"{left!r} {op} {right!r}"
            expected = safe_py(f"{left} {op} {right}")
            if expected is None:
                golden(cases, "compare", expression,
                       main_src(f"print({expression});"))
            else:
                auth(cases, "compare", expression, expression, expected)
    for expression, expected in AUTHORED_COMPARE:
        auth(cases, "compare", expression, expression, expected)
    golden(cases, "compare", "string less-than ordering",
           main_src('print("a" < "b");'))
    golden(cases, "compare", "mixed number string numeric order",
           main_src('print("10" < "9");'))
    return cases


LOGIC_AUTHORED = (
    ("!true", "false"),
    ("!false", "true"),
    ("!0", "true"),
    ('!""', "true"),
    ("!1", "false"),
    ('!"x"', "false"),
    ("!null", "true"),
    ("true || false && false", "true"),
    ("(true || false) && false", "false"),
    ("!(true && false)", "true"),
)


def logic_cases() -> list[Case]:
    cases: list[Case] = []
    for left in (True, False):
        for right in (True, False):
            for op, py_op in (("&&", "and"), ("||", "or")):
                expression = f"{str(left).lower()} {op} {str(right).lower()}"
                expected = py_str(py_eval(f"{left} {py_op} {right}"))
                auth(cases, "logic", expression, expression, expected)
    for expression, expected in LOGIC_AUTHORED:
        auth(cases, "logic", expression, expression, expected)
    golden(cases, "logic", "truthy number combined with string",
           main_src('print(1 && "x");'))
    golden(cases, "logic", "falsy number falls through to string",
           main_src('print(0 || "fallback");'))
    return cases


TRUTHY_LITERALS = ("1", '"x"', "2", "-1", '"0"', "0.5")
FALSY_LITERALS = ("0", '""', "null", "[]", "0.0")


def truthiness_cases() -> list[Case]:
    cases: list[Case] = []
    for literal in [*TRUTHY_LITERALS, *FALSY_LITERALS]:
        expected = "truthy" if literal in TRUTHY_LITERALS else "falsy"
        source = main_src(
            f"if ({literal}) {{\n"
            f'  print("truthy");\n'
            f"}} else {{\n"
            f'  print("falsy");\n'
            f"}}"
        )
        cases.append(Case("run", "truthiness", literal, source,
                          expect_stdout=expected))
    golden(cases, "truthiness", "non-empty array literal",
           main_src('if ([0]) {\n  print("truthy");\n} else {\n  print("falsy");\n}'))
    return cases


STRING_RECEIVERS = (
    '"Hello, world"',
    '"  padded  "',
    '"a,b,c"',
    '"héllo"',
)
STRING_CALLS = (
    "toUpperCase()", "toLowerCase()", "trim()", "strip()",
    "stripLeading()", "stripTrailing()",
    "isEmpty()", "isBlank()",
    'startsWith("Hello")', 'startsWith("world")',
    'endsWith("world")', 'endsWith("Hello")',
    'contains("o, w")', 'contains("zzz")',
    'indexOf("o")', 'indexOf("z")', 'lastIndexOf("o")',
    'replace("world", "there")', 'replaceAll("l", "L")',
    "charAt(1)", "codePointAt(1)",
    "substring(0, 5)", "substring(2, 7)",
    "slice(7, 11)", "slice(1, 4)",
    "repeat(2)",
    'padStart(11, "ab")', 'padEnd(11, "ab")',
    "toCharArray()", "chars()",
)

STRING_AUTHORED = (
    ('"Hello, world".toUpperCase()', "HELLO, WORLD"),
    ('"Hello, world".toLowerCase()', "hello, world"),
    ('"  padded  ".trim()', "padded"),
    ('"  padded  ".strip()', "padded"),
    ('"  padded  ".stripLeading()', "padded  "),
    ('"  padded  ".stripTrailing()', "  padded"),
    ('"Hello, world".isEmpty()', "false"),
    ('"".isEmpty()', "true"),
    ('"   ".isBlank()', "true"),
    ('"Hello, world".isBlank()', "false"),
    ('"Hello, world".startsWith("Hello")', "true"),
    ('"Hello, world".endsWith("world")', "true"),
    ('"Hello, world".contains("o, w")', "true"),
    ('"Hello, world".indexOf("o")', "4"),
    ('"Hello, world".indexOf("z")', "-1"),
    ('"Hello, world".lastIndexOf("o")', "8"),
    ('"Hello, world".replace("world", "there")', "Hello, there"),
    ('"Hello, world".replaceAll("l", "L")', "HeLLo, worLd"),
    ('"Hello, world".charAt(1)', "e"),
    ('"Hello, world".substring(0, 5)', "Hello"),
    ('"Hello, world".slice(7, 12)', "world"),
    ('"ab".repeat(3)', "ababab"),
    ('"x".padStart(5, "ab")', "ababx"),
    ('"x".padEnd(5, "ab")', "xabab"),
    ('"abc".toCharArray()', "[a, b, c]"),
    ('"abc".chars()', "[a, b, c]"),
    ('"abc"[-1]', "c"),
    ('"héllo".length', "5"),
    ('"".length', "0"),
    ('"é".codePointAt(0)', "233"),
    ('"".join(",", "a", "b")', "a,b"),
    ('["a", "b"].join(",")', "a,b"),
    ('"1" + 2', "12"),
)


def string_cases() -> list[Case]:
    cases: list[Case] = []
    seen: set[str] = set()
    for expression, expected in STRING_AUTHORED:
        seen.add(expression)
        auth(cases, "strings", expression, expression, expected)
    for receiver in STRING_RECEIVERS:
        for call in STRING_CALLS:
            expression = f"{receiver}.{call}"
            if expression in seen:
                continue
            seen.add(expression)
            golden(cases, "strings", expression,
                   main_src(f"print({expression});"))
    return cases


ARRAY_NUMERIC = ("[1, 2, 3]", "[3, 1, 2]", "[1, 1, 2]")
ARRAY_STRING = ('["a", "b", "c"]',)
ARRAY_NUMERIC_CALLS = (
    "length",
    'join("-")',
    "slice(1)",
    "slice(0, 2)",
    "concat([9])",
    "reverse()",
    "first()",
    "last()",
    "isEmpty()",
    "contains(2)",
    "indexOf(2)",
    "indexOf(99)",
    "map((x) => x * 2)",
    "filter((x) => x > 1)",
    "reduce((acc, x) => acc + x, 0)",
    "find((x) => x > 1)",
    "some((x) => x > 2)",
    "every((x) => x > 0)",
)
ARRAY_STRING_CALLS = (
    "length",
    'join("-")',
    "slice(1)",
    "slice(0, 2)",
    'concat(["d"])',
    "reverse()",
    "first()",
    "last()",
    "isEmpty()",
    'contains("a")',
    'indexOf("b")',
    'indexOf("z")',
    'map((x) => x + "!")',
    'filter((x) => x == "a")',
    'reduce((acc, x) => acc + x, "")',
    'find((x) => x == "b")',
    'some((x) => x == "c")',
    'every((x) => x != "z")',
)

ARRAY_AUTHORED = (
    ("[1, 2].join(\",\")", "1,2"),
    ("[1, 2].length", "2"),
    ("[1, 2].isEmpty()", "false"),
    ("[].isEmpty()", "true"),
    ("[1, 2].contains(2)", "true"),
    ("[1, 2].contains(9)", "false"),
    ("[1, 2].indexOf(2)", "1"),
    ("[1, 2, 3].slice(1)", "[2, 3]"),
    ("[1, 2, 3].reduce((acc, x) => acc + x, 0)", "6"),
    ("[1, 2, 3].map((x) => x * 2)", "[2, 4, 6]"),
    ('[1, 2].map((x) => x * 2).join(",")', "2,4"),
)


def array_cases() -> list[Case]:
    cases: list[Case] = []
    seen: set[str] = set()
    for expression, expected in ARRAY_AUTHORED:
        seen.add(expression)
        auth(cases, "arrays", expression, expression, expected)
    for receiver, calls in (
        [(r, ARRAY_NUMERIC_CALLS) for r in ARRAY_NUMERIC]
        + [(r, ARRAY_STRING_CALLS) for r in ARRAY_STRING]
    ):
        for call in calls:
            expression = f"{receiver}.{call}"
            if expression in seen:
                continue
            seen.add(expression)
            golden(cases, "arrays", expression,
                   main_src(f"print({expression});"))
    cases.append(Case(
        "run", "arrays", "arrays share references",
        main_src("let a = [1];\nlet b = a;\nb.push(2);\nprint(a.length);"),
        expect_stdout="2",
    ))
    cases.append(Case(
        "run", "arrays", "push then pop mutates in place",
        main_src("let a = [1];\na.push(2);\na.push(3);\nprint(a.pop());\nprint(a.length);"),
        expect_stdout="3\n2",
    ))
    cases.append(Case(
        "run", "arrays", "spread concatenation",
        main_src("print([0, ...[1, 2], 3].length);"),
        expect_stdout="4",
    ))
    golden(cases, "arrays", "negative array index from end",
           main_src("let a = [1, 2, 3];\nprint(a[-1]);"))
    cases.append(Case(
        "run", "arrays", "sort without comparator orders ascending",
        main_src("let a = [3, 1, 2];\na.sort();\nprint(a);"),
        expect_stdout="[1, 2, 3]",
    ))
    cases.append(Case(
        "run", "arrays", "sort with comparator mutates the receiver",
        main_src('let a = [3, 1, 2];\na.sort((x, y) => y - x);\nprint(a);\nprint(a.join(","));'),
        expect_stdout="[3, 2, 1]\n3,2,1",
    ))
    return cases


def control_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "control", "c-style for loop",
        main_src("for (let i = 0; i < 3; i++) {\n  print(i);\n}"),
        expect_stdout="0\n1\n2",
    ))
    cases.append(Case(
        "run", "control", "while loop with counter",
        main_src("let i = 0;\nwhile (i < 3) {\n  print(i);\n  i = i + 1;\n}"),
        expect_stdout="0\n1\n2",
    ))
    cases.append(Case(
        "run", "control", "break and continue inside while",
        main_src(
            "let i = 0;\n"
            "while (true) {\n"
            "  i = i + 1;\n"
            "  if (i > 3) {\n"
            "    break;\n"
            "  }\n"
            "  if (i == 2) {\n"
            "    continue;\n"
            "  }\n"
            "  print(i);\n"
            "}"
        ),
        expect_stdout="1\n3",
    ))
    cases.append(Case(
        "run", "control", "nested for loops",
        main_src(
            "for (let i = 0; i < 2; i++) {\n"
            "  for (let j = 0; j < 2; j++) {\n"
            "    print(i * 10 + j);\n"
            "  }\n"
            "}"
        ),
        expect_stdout="0\n1\n10\n11",
    ))
    cases.append(Case(
        "run", "control", "for-in over array yields values",
        main_src('for (let v in [10, 20]) {\n  print(v);\n}'),
        expect_stdout="10\n20",
    ))
    cases.append(Case(
        "run", "control", "for-of over array yields values",
        main_src('for (let v of [10, 20]) {\n  print(v);\n}'),
        expect_stdout="10\n20",
    ))
    cases.append(Case(
        "run", "control", "switch falls through to later cases",
        main_src(
            "let x = 1;\n"
            "switch (x) {\n"
            "  case 1: {\n"
            '    print("one");\n'
            "  }\n"
            "  case 2: {\n"
            '    print("two");\n'
            "  }\n"
            "  default: {\n"
            '    print("other");\n'
            "  }\n"
            "}"
        ),
        expect_stdout="one\ntwo\nother",
    ))
    cases.append(Case(
        "run", "control", "switch matching the second case",
        main_src(
            "let x = 2;\n"
            "switch (x) {\n"
            "  case 1: {\n"
            '    print("one");\n'
            "  }\n"
            "  case 2: {\n"
            '    print("two");\n'
            "  }\n"
            "  default: {\n"
            '    print("other");\n'
            "  }\n"
            "}"
        ),
        expect_stdout="two\nother",
    ))
    cases.append(Case(
        "run", "control", "switch with no matching case runs default",
        main_src(
            "let x = 99;\n"
            "switch (x) {\n"
            "  case 1: {\n"
            '    print("one");\n'
            "  }\n"
            "  default: {\n"
            '    print("other");\n'
            "  }\n"
            "}"
        ),
        expect_stdout="other",
    ))
    cases.append(Case(
        "run", "control", "switch compares case values by exact type",
        main_src(
            "switch (1.0) {\n"
            "  case 1: {\n"
            '    print("int match");\n'
            "  }\n"
            "  default: {\n"
            '    print("default");\n'
            "  }\n"
            "}"
        ),
        expect_stdout="default",
    ))
    cases.append(Case(
        "run", "control", "match expression selects a branch",
        main_src('print(match 2 {\n  1 => "one",\n  2 => "two",\n  _ => "other"\n});'),
        expect_stdout="two",
    ))
    cases.append(Case(
        "run", "control", "match expression wildcard branch",
        main_src('print(match 7 {\n  1 => "one",\n  _ => "other"\n});'),
        expect_stdout="other",
    ))
    golden(cases, "control", "for loop over range",
           main_src("for (let i in range(1, 5)) {\n  print(i);\n}"))
    golden(cases, "control", "do-while loop",
           main_src("let n = 0;\ndo {\n  print(n);\n  n = n + 1;\n} while (n < 3);"))
    golden(cases, "control", "for-in over object yields keys",
           main_src('for (let k in {a: 1, b: 2}) {\n  print(k);\n}'))
    golden(cases, "control", "nested while with early exit",
           main_src(
               "let i = 0;\n"
               "while (i < 3) {\n"
               "  let j = 0;\n"
               "  while (j < 3) {\n"
               "    if (j == 1) {\n"
               "      break;\n"
               "    }\n"
               "    print(i * 10 + j);\n"
               "    j = j + 1;\n"
               "  }\n"
               "  i = i + 1;\n"
               "}"
           ))
    return cases


def function_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "functions", "rest parameters collect trailing arguments",
        main_src(
            "function sum(integer first, integer ...rest) {\n"
            "  let integer total = first;\n"
            "  for (let v in rest) {\n"
            "    total = total + v;\n"
            "  }\n"
            "  return total;\n"
            "}\n"
            "print(sum(1, 2, 3));"
        ),
        expect_stdout="6",
    ))
    cases.append(Case(
        "run", "functions", "recursive factorial",
        main_src(
            "function fact(integer n) {\n"
            "  if (n <= 1) {\n"
            "    return 1;\n"
            "  }\n"
            "  return n * fact(n - 1);\n"
            "}\n"
            "print(fact(5));"
        ),
        expect_stdout="120",
    ))
    cases.append(Case(
        "run", "functions", "arrow function passed to map",
        main_src('print([1, 2, 3].map((x) => x * 2).join(","));'),
        expect_stdout="2,4,6",
    ))
    cases.append(Case(
        "run", "functions", "optional chaining reads an existing member",
        main_src("let o = {a: 1};\nprint(o?.a);"),
        expect_stdout="1",
    ))
    cases.append(Case(
        "run", "functions", "optional chaining yields undefined when missing",
        main_src("let o = {a: 1};\nprint(o?.missing);"),
        expect_stdout="undefined",
    ))
    cases.append(Case(
        "run", "functions", "ternary expression",
        main_src('print(1 < 2 ? "yes" : "no");'),
        expect_stdout="yes",
    ))
    cases.append(Case(
        "run", "functions", "named function reference passed to map",
        main_src(
            "function double(integer x) {\n"
            "  return x * 2;\n"
            "}\n"
            'print([1, 2].map(double).join(","));'
        ),
        expect_stdout="2,4",
    ))
    golden(cases, "functions", "default parameter value",
           main_src(
               "function greet(string name, string greeting = \"hi\") {\n"
               "  return greeting + \" \" + name;\n"
               "}\n"
               "print(greet(\"Ada\"));\n"
               "print(greet(\"Ada\", \"yo\"));"
           ))
    golden(cases, "functions", "nested closure captures its environment",
           main_src(
               "function counter() {\n"
               "  let c = 0;\n"
               "  function inc() {\n"
               "    c = c + 1;\n"
               "    return c;\n"
               "  }\n"
               "  inc();\n"
               "  return inc();\n"
               "}\n"
               "print(counter());"
           ))
    golden(cases, "functions", "early return guard clause",
           main_src(
               "function pick(integer n) {\n"
               "  if (n < 0) {\n"
               "    return \"neg\";\n"
               "  }\n"
               "  if (n == 0) {\n"
               "    return \"zero\";\n"
               "  }\n"
               "  return \"pos\";\n"
               "}\n"
               "print(pick(-2));\n"
               "print(pick(0));\n"
               "print(pick(8));"
           ))
    return cases


def oop_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "oop", "class field method and constructor",
        "class Point {\n"
        "  integer x;\n"
        "  integer y;\n"
        "  public Point(integer x, integer y) {\n"
        "    this.x = x;\n"
        "    this.y = y;\n"
        "  }\n"
        "  public integer sum() {\n"
        "    return this.x + this.y;\n"
        "  }\n"
        "}\n"
        "function main() {\n"
        "  let Point p = new Point(2, 3);\n"
        "  print(p.sum());\n"
        "}",
        expect_stdout="5",
    ))
    cases.append(Case(
        "run", "oop", "child constructor calls super",
        "class Parent {\n"
        "  private string name;\n"
        "  public Parent(string name) {\n"
        "    this.name = name;\n"
        "  }\n"
        "  public string getName() {\n"
        "    return this.name;\n"
        "  }\n"
        "}\n"
        "class Child extends Parent {\n"
        "  public Child(string name) {\n"
        "    super(name);\n"
        "  }\n"
        "  public string describe() {\n"
        '    return "child " + this.getName();\n'
        "  }\n"
        "}\n"
        'function main() {\n  print(new Child("ada").describe());\n}',
        expect_stdout="child ada",
    ))
    cases.append(Case(
        "run", "oop", "static method call",
        "class Calc {\n"
        "  static integer twice(integer n) {\n"
        "    return n * 2;\n"
        "  }\n"
        "}\n"
        "function main() {\n  print(Calc.twice(4));\n}",
        expect_stdout="8",
    ))
    cases.append(Case(
        "run", "oop", "static field read",
        "class Config {\n  static integer limit = 5;\n}\n"
        "function main() {\n  print(Config.limit);\n}",
        expect_stdout="5",
    ))
    cases.append(Case(
        "run", "oop", "enum member prints its name",
        main_src("enum Color {\n  RED,\n  GREEN\n}\nprint(Color.RED);"),
        expect_stdout="RED",
    ))
    cases.append(Case(
        "run", "oop", "same enum member equals itself",
        main_src(
            "enum Foo {\n  SAME\n}\n"
            "print(Foo.SAME == Foo.SAME);\n"
            "print(Foo.SAME === Foo.SAME);"
        ),
        expect_stdout="true\ntrue",
    ))
    cases.append(Case(
        "run", "oop", "equal members of different enums are distinct",
        main_src(
            "enum Foo {\n  SAME\n}\n"
            "enum Bar {\n  SAME\n}\n"
            "print(Foo.SAME == Bar.SAME);\n"
            "print(Foo.SAME === Bar.SAME);"
        ),
        expect_stdout="false\nfalse",
    ))
    cases.append(Case(
        "run", "oop", "match on enum member",
        main_src(
            "enum Status {\n  READY,\n  DONE\n}\n"
            "let Status status = Status.DONE;\n"
            'print(match status {\n  Status.READY => "ready",\n  Status.DONE => "done"\n});'
        ),
        expect_stdout="done",
    ))
    cases.append(Case(
        "run", "oop", "interface implementation dispatches",
        "interface I {\n  integer value();\n}\n"
        "class C implements I {\n"
        "  integer v;\n"
        "  public C(integer n) {\n    this.v = n;\n  }\n"
        "  public integer value() {\n    return this.v;\n  }\n"
        "}\n"
        "function main() {\n  print(new C(7).value());\n}",
        expect_stdout="7",
    ))
    cases.append(Case(
        "run", "oop", "object literal property access",
        main_src('let o = {name: "Ada", age: 30};\nprint(o.name);\nprint(o.age);'),
        expect_stdout="Ada\n30",
    ))
    cases.append(Case(
        "run", "oop", "pattern matching binds array and object members",
        main_src(
            "function describe(object value) {\n"
            "  return match value {\n"
            '    null => "empty",\n'
            '    [first, second, ...remaining] if first == 1 =>\n'
            '      "array " + second + " tail " + remaining.length,\n'
            '    {name: person, active: true} => "person " + person,\n'
            '    _ => "other"\n'
            "  };\n"
            "}\n"
            "print(describe(null));\n"
            "print(describe([1, 2, 3, 4]));\n"
            'print(describe({name: "Ada", active: true}));'
        ),
        expect_stdout="empty\narray 2 tail 2\nperson Ada",
    ))
    cases.append(Case(
        "run", "oop", "namespace scoped class construction",
        "namespace App.Models {\n"
        "  class User {\n"
        "    public string name;\n"
        "    public User(string name) {\n      this.name = name;\n    }\n"
        "  }\n"
        "}\n"
        "function main() {\n"
        '  let App.Models.User u = new App.Models.User("ada");\n'
        "  print(u.name);\n"
        "}",
        expect_stdout="ada",
    ))
    cases.append(Case(
        "run", "oop", "printing a class object",
        "class Crate {\n}\nfunction main() {\n  print(Crate);\n}",
        expect_stdout="[class Crate]",
    ))
    return cases


HASHMAP_LIFECYCLE = (
    "import System.utils.Collections.HashMap;\n"
    "function main() {\n"
    "  let HashMap m = new HashMap();\n"
    '  m.set("a", 1);\n'
    '  m.set("b", 2);\n'
    '  print(m.get("a"));\n'
    '  print(m.has("b"));\n'
    '  print(m.has("z"));\n'
    "  print(m.size());\n"
    '  print(m.get("z"));\n'
    '  print(m.getOrDefault("zz", -1));\n'
    '  m.remove("a");\n'
    "  print(m.size());\n"
    "  m.clear();\n"
    "  print(m.isEmpty());\n"
    "  print(m.keys());\n"
    "  print(m.values());\n"
    "  print(m.entries());\n"
    "}"
)


def collection_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "collections", "hashmap lifecycle",
        HASHMAP_LIFECYCLE,
        expect_stdout="1\ntrue\nfalse\n2\nnull\n-1\n1\ntrue\n[]\n[]\n[]",
    ))
    cases.append(Case(
        "run", "collections", "hashmap namespace style calls",
        (
            "import System.utils.Collections\n"
            "function main() {\n"
            "  let map = new Collections.HashMap()\n"
            '  map.set("key1", "value1")\n'
            '  print(map.get("key1"))\n'
            "  print(map.size())\n"
            "}"
        ),
        expect_stdout="value1\n1",
    ))
    cases.append(Case(
        "run", "collections", "stack push pop peek",
        (
            "import System.utils.Collections.Stack;\n"
            "function main() {\n"
            "  let s = new Stack();\n"
            "  s.push(1);\n"
            "  s.push(2);\n"
            "  print(s.pop());\n"
            "  print(s.peek());\n"
            "  print(s.size());\n"
            "  print(s.isEmpty());\n"
            "  print(s.toArray());\n"
            "}"
        ),
        expect_stdout="2\n1\n1\nfalse\n[1]",
    ))
    cases.append(Case(
        "run", "collections", "queue enqueue dequeue",
        (
            "import System.utils.Collections.Queue;\n"
            "function main() {\n"
            "  let q = new Queue();\n"
            "  q.enqueue(1);\n"
            "  q.enqueue(2);\n"
            "  print(q.dequeue());\n"
            "  print(q.peek());\n"
            "  print(q.size());\n"
            "  print(q.isEmpty());\n"
            "  print(q.toArray());\n"
            "}"
        ),
        expect_stdout="1\n2\n1\nfalse\n[2]",
    ))
    cases.append(Case(
        "run", "collections", "linked list add and read",
        (
            "import System.utils.Collections.LinkedList;\n"
            "function main() {\n"
            "  let l = new LinkedList();\n"
            "  l.add(1);\n"
            "  l.addFirst(0);\n"
            "  l.addLast(9);\n"
            "  print(l.toArray());\n"
            "  print(l.get(0));\n"
            "  print(l.getFirst());\n"
            "  print(l.getLast());\n"
            "  print(l.size());\n"
            "  print(l.contains(9));\n"
            "  print(l.indexOf(9));\n"
            "  print(l.removeFirst());\n"
            "  print(l.size());\n"
            "}"
        ),
        expect_stdout="[0, 1, 9]\n0\n0\n9\n3\ntrue\n2\n0\n2",
    ))
    cases.append(Case(
        "run", "collections", "set add has union remove",
        (
            "import System.utils.Collections.Set;\n"
            "function main() {\n"
            "  let s = new Set();\n"
            "  s.add(1);\n"
            "  s.add(2);\n"
            "  print(s.size());\n"
            "  print(s.has(1));\n"
            "  print(s.has(3));\n"
            "  print(s.toArray());\n"
            "  let u = new Set();\n"
            "  u.add(3);\n"
            "  let t = s.union(u);\n"
            "  print(t.size());\n"
            "  s.remove(1);\n"
            "  print(s.size());\n"
            "}"
        ),
        expect_stdout="2\ntrue\nfalse\n[1, 2]\n3\n1",
    ))
    cases.append(Case(
        "run", "collections", "priority queue orders by dequeue",
        (
            "import System.utils.Collections.PriorityQueue;\n"
            "function main() {\n"
            "  let p = new PriorityQueue();\n"
            "  p.enqueue(3);\n"
            "  p.enqueue(1);\n"
            "  p.enqueue(2);\n"
            "  print(p.dequeue());\n"
            "  print(p.peek());\n"
            "  print(p.size());\n"
            "  print(p.isEmpty());\n"
            "  print(p.toArray());\n"
            "}"
        ),
        expect_stdout="1\n2\n2\nfalse\n[2, 3]",
    ))
    cases.append(Case(
        "run", "collections", "trie insert search prefix remove",
        (
            "import System.utils.Collections.Trie;\n"
            "function main() {\n"
            "  let t = new Trie();\n"
            '  t.insert("car");\n'
            '  t.insert("card");\n'
            '  print(t.search("car"));\n'
            '  print(t.search("cab"));\n'
            '  print(t.startsWith("ca"));\n'
            "  print(t.size());\n"
            "  print(t.getAllWords());\n"
            '  print(t.getWordsWithPrefix("car"));\n'
            '  print(t.remove("car"));\n'
            '  print(t.search("car"));\n'
            "}"
        ),
        expect_stdout=(
            "true\nfalse\ntrue\n2\n[car, card]\n[car, card]\nfalse\nfalse"
        ),
    ))
    return cases


def misc_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "misc", "thread start and join",
        (
            "import System.concurrent.Thread\n"
            "integer function add(integer left, integer right) {\n"
            "  return left + right;\n"
            "}\n"
            "integer function getAnswer() {\n"
            "  return 42;\n"
            "}\n"
            "function main() {\n"
            "  let ThreadHandle worker = Thread.start(add, [20, 22]);\n"
            "  print(worker.join());\n"
            "  print(worker.isAlive());\n"
            "  let ThreadHandle solo = Thread.start(getAnswer);\n"
            "  print(solo.join());\n"
            "}"
        ),
        expect_stdout="42\nfalse\n42",
    ))
    cases.append(Case(
        "run", "misc", "exit from main with status 7",
        main_src("System.process.exit(7);"),
        expect_stdout="",
        expect_exit=7,
    ))
    cases.append(Case(
        "run", "misc", "exit from worker thread propagates on join",
        (
            "import System.concurrent.Thread\n"
            "function bail() {\n"
            "  System.process.exit(7);\n"
            "}\n"
            "function main() {\n"
            "  let ThreadHandle worker = Thread.start(bail);\n"
            "  worker.join();\n"
            '  print("unreachable");\n'
            "}"
        ),
        expect_stdout="",
        expect_exit=7,
        notes="SystemExit crosses the thread-join boundary",
    ))
    cases.append(Case(
        "run", "misc", "exit after printing",
        main_src('print("bye");\nSystem.process.exit(0);'),
        expect_stdout="bye",
        expect_exit=0,
    ))
    cases.append(Case(
        "run", "misc", "normal completion has no exit code",
        main_src('print("done");'),
        expect_stdout="done",
    ))
    cases.append(Case(
        "run", "misc", "try catch captures a thrown exception",
        main_src(
            "try {\n"
            '  throw new Exception("expected");\n'
            "} catch (Exception e) {\n"
            '  print("caught " + e.message);\n'
            "}"
        ),
        expect_stdout="caught expected",
    ))
    cases.append(Case(
        "run", "misc", "multi argument print joins with spaces",
        main_src('print("Size:", 2);\nprint("a", "b", "c");'),
        expect_stdout="Size: 2\na b c",
    ))
    cases.append(Case(
        "run", "misc", "compound addition assignment",
        main_src("let i = 5;\ni += 2;\nprint(i);"),
        expect_stdout="7",
    ))
    cases.append(Case(
        "run", "misc", "increment operators update the variable",
        main_src("let i = 5;\ni++;\nprint(i);\n++i;\nprint(i);"),
        expect_stdout="6\n7",
    ))
    cases.append(Case(
        "run", "misc", "typeOf on a primitive",
        main_src("print(typeOf(1));"),
        expect_stdout="number",
    ))
    cases.append(Case(
        "run", "misc", "explicit return null",
        main_src("function f() {\n  return null;\n}\nprint(f());"),
        expect_stdout="null",
    ))
    cases.append(Case(
        "run", "misc", "bare return in main",
        main_src("return;"),
        expect_stdout="",
    ))
    golden(cases, "misc", "decrement operators",
           main_src("let i = 5;\ni--;\nprint(i);\n--i;\nprint(i);"))
    golden(cases, "misc", "string escape sequences",
           main_src('print("tab:\\there");\nprint("line:\\nbreak");'))
    golden(cases, "misc", "nested function declarations",
           main_src(
               "function outer() {\n"
               "  function inner() {\n"
               '    return "deep";\n'
               "  }\n"
               "  return inner();\n"
               "}\n"
               "print(outer());"
           ))
    golden(cases, "misc", "backtick string with dollar brace",
           main_src("let n = 1;\nprint(`hi ${n}`);"))
    golden(cases, "misc", "braces inside a plain string are literal",
           main_src('let n = 1;\nprint("hi {n}");'))
    return cases


CHECK_SNIPPETS = (
    ("class with fields and methods", (
        "class Greeter {\n"
        "  private string name;\n"
        "  public Greeter(string name) {\n    this.name = name;\n  }\n"
        "  public string greet() {\n    return \"hi \" + this.name;\n  }\n"
        "}\n"
        "function main() {\n  print(new Greeter(\"Ada\").greet());\n}"
    )),
    ("static members", (
        "class Util {\n"
        "  static integer count = 0;\n"
        "  static integer bump() {\n    Util.count = Util.count + 1;\n    return Util.count;\n  }\n"
        "}\n"
        "function main() {\n  print(Util.bump());\n}"
    )),
    ("enum declaration and match", (
        "enum Level {\n  LOW,\n  HIGH\n}\n"
        "function main() {\n"
        "  print(match Level.HIGH {\n    Level.LOW => \"low\",\n    Level.HIGH => \"high\"\n  });\n}"
    )),
    ("interface implementation", (
        "interface Shape {\n  integer area();\n}\n"
        "class Square implements Shape {\n"
        "  integer side;\n"
        "  public Square(integer side) {\n    this.side = side;\n  }\n"
        "  public integer area() {\n    return this.side * this.side;\n  }\n"
        "}\n"
        "function main() {\n  print(new Square(3).area());\n}"
    )),
    ("decorators on function class and method", (
        "function identity(var target) {\n  return target;\n}\n"
        "@trace\n"
        "function greet() {\n  return \"hello\";\n}\n"
        "@identity\n"
        "function unchanged() {\n  return \"unchanged\";\n}\n"
        "@trace\n"
        "class Box {\n"
        "  public Box() {}\n"
        "  @trace\n"
        "  public string value() {\n    return \"box\";\n  }\n"
        "}\n"
        "function main() {\n  print(greet());\n  print(unchanged());\n  print(new Box().value());\n}"
    )),
    ("optional chaining and ternary", (
        "function main() {\n"
        "  let o = {a: 1};\n"
        "  print(o?.a);\n"
        "  print(o?.gone);\n"
        '  print(o == null ? "y" : "n");\n}'
    )),
    ("string methods", (
        "function main() {\n"
        '  print("Hello".toUpperCase());\n'
        '  print("  x  ".trim());\n'
        '  print("a,b".split(","));\n'
        '  print("ab".repeat(2));\n'
        '  print("abc".contains("b"));\n}'
    )),
    ("array higher order functions", (
        "function main() {\n"
        "  let a = [1, 2, 3];\n"
        "  print(a.map((x) => x + 1));\n"
        "  print(a.filter((x) => x > 1));\n"
        "  print(a.reduce((acc, x) => acc + x, 0));\n}"
    )),
    ("switch statement", (
        "function main() {\n"
        "  let x = 2;\n"
        "  switch (x) {\n"
        "    case 1: {\n      print(\"one\");\n    }\n"
        "    case 2: {\n      print(\"two\");\n    }\n"
        "    default: {\n      print(\"other\");\n    }\n  }\n}"
    )),
    ("threads", (
        "import System.concurrent.Thread\n"
        "integer function work(integer n) {\n  return n * 2;\n}\n"
        "function main() {\n"
        "  let ThreadHandle h = Thread.start(work, [21]);\n"
        "  print(h.join());\n}"
    )),
    ("exceptions", (
        "function main() {\n"
        "  try {\n    throw new Exception(\"boom\");\n  } catch (Exception e) {\n"
        '    print("caught");\n  } finally {\n    print("done");\n  }\n}'
    )),
    ("namespace", (
        "namespace Demo.App {\n"
        "  class Config {\n    public string name;\n    public Config(string name) {\n      this.name = name;\n    }\n  }\n"
        "}\n"
        "function main() {\n  let Demo.App.Config c = new Demo.App.Config(\"x\");\n  print(c.name);\n}"
    )),
    ("rest and default parameters", (
        "function tally(integer head, integer ...rest) {\n"
        "  let total = head;\n"
        "  for (let v in rest) {\n    total = total + v;\n  }\n"
        "  return total;\n}\n"
        "function hello(string name, string greeting = \"hi\") {\n  return greeting + \" \" + name;\n}\n"
        "function main() {\n  print(tally(1, 2, 3));\n  print(hello(\"Ada\"));\n}"
    )),
    ("spread and object literals", (
        "function main() {\n"
        "  let base = [1, 2];\n"
        "  print([0, ...base, 3]);\n"
        '  let config = {debug: true, level: 2};\n'
        "  print(config.debug);\n}"
    )),
    ("loops with break and continue", (
        "function main() {\n"
        "  for (let i = 0; i < 5; i++) {\n"
        "    if (i == 1) {\n      continue;\n    }\n"
        "    if (i == 3) {\n      break;\n    }\n"
        "    print(i);\n  }\n}"
    )),
    ("range based loop", (
        "function main() {\n"
        "  for (let i in range(0, 3)) {\n    print(i);\n  }\n}"
    )),
    ("do while loop", (
        "function main() {\n"
        "  let n = 0;\n  do {\n    n = n + 1;\n  } while (n < 3);\n  print(n);\n}"
    )),
    ("collections imports", (
        "import System.utils.Collections.HashMap;\n"
        "import System.utils.Collections.Stack;\n"
        "function main() {\n"
        "  let m = new HashMap();\n"
        '  m.set("k", 1);\n'
        "  print(m.get(\"k\"));\n"
        "  let s = new Stack();\n  s.push(1);\n  print(s.pop());\n}"
    )),
    ("async function declaration", (
        "async function fetchLater() {\n  return 1;\n}\n"
        "function main() {\n  print(\"registered\");\n}"
    )),
    ("compound assignment and increments", (
        "function main() {\n"
        "  let n = 1;\n  n += 4;\n  n++;\n  print(n);\n  let s = \"a\";\n  s += \"b\";\n  print(s);\n}"
    )),
)

IMPORT_RE = re.compile(r"^\s*import\s+([^\s;]+)", re.MULTILINE)


def _example_paths() -> list[Path]:
    examples = ROOT / "examples"
    if not examples.is_dir():
        return []
    return sorted(examples.rglob("*.x"))


def _portable_example(path: Path) -> bool:
    """True when *path* imports nothing outside the System package."""
    relative = path.relative_to(ROOT / "examples")
    if "build" in relative.parts:
        return False
    if relative.parts and relative.parts[0] == "errors":
        return False
    source = path.read_text(encoding="utf-8")
    for imported in IMPORT_RE.findall(source):
        if not imported.startswith("System"):
            return False
    return True


def example_cases(workdir: Path, problems: list[str]) -> tuple[list[Case], list[Case]]:
    """Split portable examples into clean check rows and failing error rows."""
    checks: list[Case] = []
    errors: list[Case] = []
    for path in _example_paths():
        if not _portable_example(path):
            continue
        relative = path.relative_to(ROOT / "examples")
        label = f"example {relative.as_posix()}"
        source = path.read_text(encoding="utf-8")
        outcome = try_execute("check", source, workdir)
        if outcome is None:
            problems.append(f"{label}: type-check timed out")
            continue
        if outcome.error:
            errors.append(Case(
                "error", "examples", label, source,
                expect_error=outcome.error,
                phase=classify_phase(source, workdir),
            ))
        else:
            checks.append(Case("check", "examples", label, source))
    return checks, errors


def classify_phase(source: str, workdir: Path) -> str:
    """Return the first pipeline stage that rejects *source*.

    Stages: ``lex`` -> ``parse`` -> ``load`` (import resolution) -> ``type``
    -> ``runtime``.
    """
    entry = workdir / "classify.x"
    entry.write_text(source, encoding="utf-8")
    try:
        program = ModuleLoader(workdir).load_program(entry)
    except LexError:
        return "lex"
    except ParseError:
        return "parse"
    except Exception:  # noqa: BLE001 - import resolution failures are load errors
        return "load"
    try:
        errors = TypeChecker().check(program, source_name=str(entry))
    except Exception:  # noqa: BLE001 - depth errors count as type failures
        return "type"
    if errors:
        return "type"
    try:
        with time_limit():
            Interpreter([], lambda _text: None, config=XConfig()).interpret(program)
    except _Timeout:
        return "runtime"
    except Exception:  # noqa: BLE001 - every runtime failure lands here
        return "runtime"
    return ""


AUTHORED_ERRORS: tuple[tuple[str, str, str, str], ...] = (
    ("arith", "division by zero literal", "function main() {\n  print(1 / 0);\n}",
     "Cannot divide by zero"),
    ("arith", "division by zero variable",
     "function main() {\n  let a = 10;\n  let b = 0;\n  print(a / b);\n}",
     "Division by zero for '/'"),
    ("arith", "modulus by zero variable",
     "function main() {\n  let a = 10;\n  let b = 0;\n  print(a % b);\n}",
     "Division by zero for '%'"),
    ("strings", "string index out of range",
     'function main() {\n  print("ab"[5]);\n}',
     "Cannot access index 5: out of range for string of length 2"),
    ("strings", "string index before start",
     'function main() {\n  print("abc"[-4]);\n}',
     "Cannot access index -4: out of range for string of length 3"),
    ("strings", "split rejects a limit argument",
     'function main() {\n  print("a b".split(" ", 1));\n}',
     "String.split accepts at most one separator"),
    ("arrays", "array index out of range",
     "function main() {\n  let a = [1, 2];\n  print(a[5]);\n}",
     "Cannot access index 5: out of range for array of length 2"),
    ("arrays", "pop on empty array",
     "function main() {\n  let a = [];\n  print(a.pop());\n}",
     "Array.pop: array is empty"),
    ("functions", "call to undefined function",
     "function main() {\n  missing();\n}",
     "Name 'missing' is not defined"),
    ("functions", "read of undefined variable",
     "function main() {\n  print(nope);\n}",
     "Name 'nope' is not defined"),
    ("functions", "value is not callable",
     "function main() {\n  let x = 1;\n  x();\n}",
     "Value is not callable"),
    ("functions", "wrong argument count",
     "function f(integer a) {\n  return a;\n}\nfunction main() {\n  print(f());\n}",
     "No overload of 'f' accepts 0 argument(s)"),
    ("functions", "null is not indexable",
     "function main() {\n  print(null[0]);\n}",
     "Cannot access index 0: null values are not indexable"),
    ("control", "break outside a loop",
     "function main() {\n  break;\n}",
     "'break' used outside of a loop"),
    ("control", "break inside a switch case",
     "function main() {\n  switch (1) {\n    case 1: {\n      break;\n    }\n  }\n}",
     "'break' used outside of a loop"),
    ("control", "return outside a function",
     "return 5;",
     "'return' is only valid inside a function"),
    ("control", "await outside an async function",
     "function main() {\n  await 1;\n}",
     "'await' is only valid inside an async function"),
    ("oop", "private field accessed from outside",
     "class C {\n  private integer v;\n}\nfunction main() {\n  let C c = new C();\n  print(c.v);\n}",
     "Cannot access private field 'C.v'"),
    ("oop", "constructor without a name",
     "function main() {\n  print(new 5);\n}",
     "Expected a name"),
    ("types", "assign string to integer variable",
     'function main() {\n  let integer x = "s";\n  print(x);\n}',
     "Cannot assign 'string' to 'x' of type 'integer'"),
    ("types", "redeclare a variable",
     "function main() {\n  let x = 1;\n  let x = 2;\n  print(x);\n}",
     "'x' is already declared in this scope"),
    ("types", "assign to undeclared name",
     "function main() {\n  x = 5;\n  print(x);\n}",
     "Cannot assign to undefined name 'x'"),
    ("types", "reassign a constant",
     "function main() {\n  const c = 1;\n  c = 2;\n  print(c);\n}",
     "Cannot reassign constant 'c'"),
    ("runtime", "recursion past the depth limit",
     "function down(integer n) {\n  return down(n + 1);\n}\nfunction main() {\n  print(down(0));\n}",
     "Maximum recursion depth exceeded"),
    ("runtime", "uncaught thrown string",
     'function main() {\n  throw "boom";\n}',
     "boom"),
    ("runtime", "uncaught thrown number",
     "function main() {\n  throw 42;\n}",
     "42"),
    ("runtime", "exit rejects a boolean code",
     "function main() {\n  System.process.exit(true);\n}",
     "System.process.exit expects an integer exit code"),
    ("runtime", "exit rejects two arguments",
     "function main() {\n  System.process.exit(1, 2);\n}",
     "System.process.exit expects 0 or 1 argument"),
    ("lex", "unknown escape sequence",
     'function main() {\n  print("\\u0041");\n}',
     "Unknown escape sequence"),
    ("lex", "unexpected ampersand",
     "function main() {\n  print(1 & 2);\n}",
     "Unexpected character"),
    ("parse", "scientific notation literal",
     "function main() {\n  print(1e15);\n}",
     "Expected"),
    ("parse", "instanceof operator is unsupported",
     "function main() {\n  print(1 instanceof Number);\n}",
     "Expected"),
    ("parse", "exponent operator is unsupported",
     "function main() {\n  print(2 ** 10);\n}",
     "expected an expression"),
    ("parse", "getter syntax is unsupported",
     "class C {\n  private integer v;\n  public C() {\n    this.v = 3;\n  }\n  public integer get v() {\n    return this.v;\n  }\n}\nfunction main() {\n  print(1);\n}",
     "Expected ';' after field declaration"),
    ("parse", "function typed parameter is unsupported",
     "function apply(integer n, integer f(integer value)) {\n  return f(n);\n}\nfunction main() {\n  print(1);\n}",
     "Expected ')' after parameters"),
    ("parse", "generic function parameters are unsupported",
     "function first<T>(list<T> items) {\n  return items[0];\n}\nfunction main() {\n  print(1);\n}",
     "Expected '(' before parameters"),
    ("parse", "record declaration keyword placement",
     "record Point(int x, int y);\nfunction main() {\n  print(1);\n}",
     "Declarations must start with"),
    ("imports", "unknown bare import",
     "import NotAModule\nfunction main() {\n  print(1);\n}",
     "Imported source file 'NotAModule.x' does not exist"),
    ("imports", "missing local import path",
     "import ./nope.x\nfunction main() {\n  print(1);\n}",
     "Expected import path"),
)

MUTATION_TEMPLATES = (
    ("class", (
        "class Point {\n"
        "  integer x;\n"
        "  public Point(integer x) {\n    this.x = x;\n  }\n"
        "  public integer get() {\n    return this.x;\n  }\n"
        "}\n"
        "function main() {\n  print(new Point(4).get());\n}"
    )),
    ("control", (
        "function main() {\n"
        "  for (let i = 0; i < 3; i++) {\n"
        "    if (i == 1) {\n      continue;\n    }\n"
        "    print(i);\n  }\n}"
    )),
    ("switch", (
        "function main() {\n"
        "  let x = 2;\n  switch (x) {\n"
        "    case 1: {\n      print(\"one\");\n    }\n"
        "    default: {\n      print(\"other\");\n    }\n  }\n}"
    )),
    ("match", (
        "function main() {\n"
        "  print(match 2 {\n    1 => \"one\",\n    _ => \"other\"\n  });\n}"
    )),
    ("strings", (
        "function main() {\n"
        '  let s = "hello";\n'
        "  print(s.toUpperCase());\n"
        "  print(s.length);\n}"
    )),
    ("collections", (
        "import System.utils.Collections.HashMap\n"
        "function main() {\n"
        "  let m = new HashMap()\n"
        "  m.set(\"k\", 1)\n"
        "  print(m.get(\"k\"))\n}"
    )),
)
MUTATION_BUDGET = 25


def mutation_error_cases(workdir: Path) -> list[Case]:
    cases: list[Case] = []
    for template_name, template_source in MUTATION_TEMPLATES:
        try:
            tokens = Lexer(template_source, "mutation").tokenize()
        except LexError:
            continue
        seen_errors: set[str] = set()
        kept = 0
        for index, token in enumerate(tokens):
            if kept >= MUTATION_BUDGET:
                break
            if token.start < 0 or token.end <= token.start:
                continue
            reduced = template_source[: token.start] + template_source[token.end:]
            outcome = try_execute("error", reduced, workdir)
            if outcome is None or not outcome.error or outcome.error in seen_errors:
                continue
            if outcome.stdout or len(outcome.error) > 4000:
                # Looping mutations or runaway diagnostics make poor fixtures.
                continue
            seen_errors.add(outcome.error)
            kept += 1
            cases.append(Case(
                "error", "mutations",
                f"{template_name} drop token {index} ({token.kind})",
                reduced,
                expect_error=outcome.error,
                phase=classify_phase(reduced, workdir),
                notes=f"template {template_name}",
            ))
    return cases


def errors_dir_cases(workdir: Path, problems: list[str]) -> list[Case]:
    cases: list[Case] = []
    errors_dir = ROOT / "examples" / "errors"
    if not errors_dir.is_dir():
        return cases
    for path in sorted(errors_dir.glob("*.x")):
        source = path.read_text(encoding="utf-8")
        outcome = try_execute("error", source, workdir)
        if outcome is None:
            problems.append(f"example errors/{path.name}: execution timed out")
            continue
        if not outcome.error:
            continue
        cases.append(Case(
            "error", "examples", f"example errors/{path.name}", source,
            expect_error=outcome.error,
            phase=classify_phase(source, workdir),
        ))
    return cases


FORMAT_SEEDS = (
    ("compact if else", 'function main(){ if(1){print("a");}else{print("b");} }'),
    ("if else chain", (
        "function main(){\n"
        '  if(1){print("one");}else if(2){print("two");}else{print("other");}\n}'
    )),
    ("for loop compact", "function main(){for(let i=0;i<3;i++){print(i);}}"),
    ("while loop compact", "function main(){let i=0;while(i<3){print(i);i++;}}"),
    ("do while compact", "function main(){let n=0;do{n++;}while(n<3);print(n);}"),
    ("class compact", (
        "class Point{integer x;integer y;"
        "public Point(integer x,integer y){this.x=x;this.y=y;}"
        "public integer sum(){return this.x+y;}}"
    )),
    ("enum compact", "enum Color{RED,GREEN}\nfunction main(){print(Color.RED);}"),
    ("interface compact", (
        "interface I{integer value();}"
        "class C implements I{integer v;public C(integer n){this.v=n;}"
        "public integer value(){return this.v;}}"
    )),
    ("match compact", 'function main(){print(match 1{1=>"one",_=>"other"});}'),
    ("switch compact", (
        "function main(){let x=1;switch(x){case 1:{print(1);break;}default:{print(2);}}}"
    )),
    ("import and namespace", (
        "import System.utils.Math\n"
        "namespace A.B{class C{public integer n;public C(){this.n=1;}}}"
    )),
    ("thread block", (
        "import System.concurrent.Thread\n"
        "integer function work(){return 1;}\n"
        "function main(){let ThreadHandle h=Thread.start(work);print(h.join());}"
    )),
    ("try catch finally", (
        "function main(){try{throw new Exception(\"x\");}catch(Exception e){print(\"c\");}"
        "finally{print(\"f\");}}"
    )),
    ("decorator block", (
        "function wrap(var target){return target;}\n"
        "@wrap\nfunction greet(){return \"hi\";}\n"
        "@wrap\nclass Box{public Box(){}public string v(){return \"b\";}}"
    )),
    ("object literal", 'function main(){let o={a:1,b:"two",c:[1,2]};print(o.a);}'),
    ("arrow chain", "function main(){print([1,2,3].map((x)=>x*2).filter((x)=>x>2));}"),
    ("ternary and optional", 'function main(){let o={a:1};print(o?.a!=null?"y":"n");}'),
    ("rest default params", (
        "function f(integer a,integer ...rest){return a;}"
        "function g(string s=\"x\"){return s;}"
    )),
    ("spread call", "function main(){print([1,2]);}"),
    ("compound operators", "function main(){let n=1;n+=2;n++;n*=3;print(n);}"),
    ("nested functions", "function outer(){function inner(){return 1;}return inner();}"),
    ("let with type annotation", (
        "class Point{integer x;}\nfunction main(){let Point p=new Point();print(0);}"
    )),
    ("chained method calls", (
        'function main(){print("  Hello World  ".trim().toLowerCase().replace("world","there"));}'
    )),
)


def format_cases(run_cases: list[Case], check_cases_list: list[Case]) -> list[Case]:
    cases = [Case("format", "seeds", name, source)
             for name, source in FORMAT_SEEDS]
    seen = {source for _name, source in FORMAT_SEEDS}
    for case in [*run_cases, *check_cases_list]:
        if case.source in seen:
            continue
        seen.add(case.source)
        cases.append(Case("format", f"reuse {case.kind}", case.name, case.source))
    return cases


def decorator_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "decorators", "parametrized decorator via dotted static path",
        (
            "function load_test_cases() {\n"
            '  return ["a", "b"];\n'
            "}\n"
            "class MyDecorator {\n"
            "  static var foo = {bar: {parametrizedDecorator: (name, cases) => (target) => {\n"
            '    print("suite " + name + " with " + cases.length + " cases");\n'
            "    return target;\n"
            "  }}};\n"
            "}\n"
            '@MyDecorator.foo.bar.parametrizedDecorator("case", load_test_cases())\n'
            "function demo() {\n"
            "  return 0;\n"
            "}\n"
            "function main() {\n"
            "  print(demo());\n"
            "}"
        ),
        expect_stdout="suite case with 2 cases\n0",
    ))
    cases.append(Case(
        "run", "decorators", "factory decorator runs at load time",
        (
            "function load_test_cases() {\n"
            '  return ["login", "checkout"];\n'
            "}\n"
            "function suite(string name, string[] cases) {\n"
            "  return (target) => {\n"
            '    print("running " + name + " (" + cases.length + " cases)");\n'
            "    return target;\n"
            "  };\n"
            "}\n"
            '@suite("smoke", load_test_cases())\n'
            "function example() {\n"
            '  return "ok";\n'
            "}\n"
            "function main() {\n"
            "  print(example());\n"
            "}"
        ),
        expect_stdout="running smoke (2 cases)\nok",
    ))
    cases.append(Case(
        "run", "decorators", "decorator wraps the original with an arrow",
        (
            "function logged(var target) {\n"
            "  return (a, b) => {\n"
            '    print("calling add(" + a + ", " + b + ")");\n'
            "    return target(a, b);\n"
            "  };\n"
            "}\n"
            "@logged\n"
            "function add(integer a, integer b) {\n"
            "  return a + b;\n"
            "}\n"
            "function main() {\n"
            "  print(add(2, 3));\n"
            "}"
        ),
        expect_stdout="calling add(2, 3)\n5",
    ))
    cases.append(Case(
        "run", "decorators", "stacked decorators apply bottom up",
        (
            "function audit(var target) {\n"
            '  print("audit applies");\n'
            "  return target;\n"
            "}\n"
            "function memoize(var target) {\n"
            '  print("memoize applies");\n'
            "  return target;\n"
            "}\n"
            "@audit\n"
            "@memoize\n"
            "function compute() {\n"
            "  return 42;\n"
            "}\n"
            "function main() {\n"
            "  print(compute());\n"
            "}"
        ),
        expect_stdout="memoize applies\naudit applies\n42",
    ))
    cases.append(Case(
        "run", "decorators", "zero argument factory call form",
        (
            "function MyDecorator() {\n"
            "  return (target) => {\n"
            '    print("applying");\n'
            "    return target;\n"
            "  };\n"
            "}\n"
            "@MyDecorator()\n"
            "function sync() {\n"
            "  return 1;\n"
            "}\n"
            "function main() {\n"
            "  print(sync());\n"
            "}"
        ),
        expect_stdout="applying\n1",
    ))
    return cases


def switch_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "control", "six level nested switch runs every following body",
        (
            "function main() {\n"
            "  let integer a = 1;\n"
            "  let integer b = 2;\n"
            "  let integer c = 3;\n"
            "  let integer d = 4;\n"
            "  let integer e = 5;\n"
            "  let integer f = 6;\n"
            "  switch (a) {\n"
            "    case 1: {\n"
            "      switch (b) {\n"
            "        case 2: {\n"
            "          switch (c) {\n"
            "            case 3: {\n"
            "              switch (d) {\n"
            "                case 4: {\n"
            "                  switch (e) {\n"
            "                    case 5: {\n"
            "                      switch (f) {\n"
            "                        case 6: { print(\"deep6\"); }\n"
            "                        default: { print(\"f-other\"); }\n"
            "                      }\n"
            "                    }\n"
            "                    default: { print(\"e-other\"); }\n"
            "                  }\n"
            "                }\n"
            "                default: { print(\"d-other\"); }\n"
            "              }\n"
            "            }\n"
            "            default: { print(\"c-other\"); }\n"
            "          }\n"
            "        }\n"
            "        default: { print(\"b-other\"); }\n"
            "      }\n"
            "    }\n"
            "    default: { print(\"a-other\"); }\n"
            "  }\n"
            "  print(\"end\");\n"
            "}"
        ),
        expect_stdout=(
            "deep6\nf-other\ne-other\nd-other\nc-other\nb-other\na-other\nend"
        ),
    ))
    cases.append(Case(
        "run", "control",
        "loop around four nested switches with break leaving the loop",
        (
            "function main() {\n"
            '  let string channel = "web";\n'
            "  let integer tier = 2;\n"
            "  let integer attempt = 1;\n"
            '  let string receipt = "";\n'
            "  for (let i = 0; i < 2; i = i + 1) {\n"
            "    switch (channel) {\n"
            '      case "web": {\n'
            '        print("channel web");\n'
            "        switch (tier) {\n"
            "          case 1: {\n"
            '            print("tier basic");\n'
            "          }\n"
            "          case 2: {\n"
            '            print("tier pro");\n'
            "            switch (attempt) {\n"
            "              case 0: {\n"
            '                print("attempt zero");\n'
            "              }\n"
            "              case 1: {\n"
            '                print("attempt one");\n'
            "                switch (i) {\n"
            "                  case 0: {\n"
            '                    receipt = "first";\n'
            "                  }\n"
            "                  default: {\n"
            '                    receipt = "again";\n'
            "                  }\n"
            "                }\n"
            "                print(receipt);\n"
            "              }\n"
            "              default: {\n"
            '                print("attempt other");\n'
            "              }\n"
            "            }\n"
            "          }\n"
            "          default: {\n"
            '            print("tier other");\n'
            "          }\n"
            "        }\n"
            "        break;\n"
            "      }\n"
            "      default: {\n"
            '        print("channel other");\n'
            "      }\n"
            "    }\n"
            "  }\n"
            "  print(receipt);\n"
            "}"
        ),
        expect_stdout=(
            "channel web\ntier pro\nattempt one\nagain\nattempt other\n"
            "tier other\nagain"
        ),
    ))
    cases.append(Case(
        "run", "control", "default placed before the matching case starts there",
        (
            "function main() {\n"
            "  let integer x = 2;\n"
            "  switch (x) {\n"
            "    case 1: { print(\"one\"); }\n"
            "    default: { print(\"dflt\"); }\n"
            "    case 2: { print(\"two\"); }\n"
            "  }\n"
            "}"
        ),
        expect_stdout="dflt\ntwo",
    ))
    cases.append(Case(
        "run", "control", "switch case value may be an expression",
        (
            "function main() {\n"
            "  let integer x = 3;\n"
            "  switch (x) {\n"
            "    case 1 + 1: { print(\"no\"); }\n"
            "    case 3: { print(\"yes\"); }\n"
            "  }\n"
            "}"
        ),
        expect_stdout="yes",
    ))
    cases.append(Case(
        "run", "control", "string scrutinee with default listed first",
        (
            "function main() {\n"
            '  let string s = "b";\n'
            "  switch (s) {\n"
            '    default: { print("D"); }\n'
            '    case "a": { print("A"); }\n'
            '    case "b": { print("B"); }\n'
            "  }\n"
            "}"
        ),
        expect_stdout="D\nA\nB",
    ))
    cases.append(Case(
        "run", "control", "break inside switch inside for exits the for loop",
        (
            "function main() {\n"
            "  for (let i = 0; i < 3; i = i + 1) {\n"
            "    switch (i) {\n"
            '      case 0: { print("zero"); break; }\n'
            '      default: { print("other"); }\n'
            "    }\n"
            "  }\n"
            "}"
        ),
        expect_stdout="zero",
    ))
    cases.append(Case(
        "run", "control", "switch driven early exit of a for loop",
        (
            "function main() {\n"
            "  let integer result = 0;\n"
            "  for (let i = 0; i < 5; i = i + 1) {\n"
            "    switch (i) {\n"
            "      case 3: { result = 100; break; }\n"
            "      default: { result = i; }\n"
            "    }\n"
            "  }\n"
            "  print(result);\n"
            '  print("i-loop-done");\n'
            "}"
        ),
        expect_stdout="100\ni-loop-done",
    ))
    cases.append(Case(
        "run", "control", "switch nested inside a case body with an inner loop",
        (
            "function main() {\n"
            "  let integer hits = 0;\n"
            "  let integer kind = 2;\n"
            "  switch (kind) {\n"
            "    case 1: { print(\"one\"); }\n"
            "    case 2: {\n"
            "      for (let i = 0; i < 3; i = i + 1) {\n"
            "        switch (i) {\n"
            "          case 0: { hits = hits + 10; }\n"
            "          case 1: { hits = hits + 1; }\n"
            "          default: { hits = hits + 100; }\n"
            "        }\n"
            "      }\n"
            "      print(hits);\n"
            "    }\n"
            "    default: { print(\"other\"); }\n"
            "  }\n"
            '  print("done");\n'
            "}"
        ),
        expect_stdout="312\nother\ndone",
    ))
    cases.append(Case(
        "run", "control", "switch with no default and no match prints nothing",
        (
            "function main() {\n"
            "  let integer x = 5;\n"
            "  switch (x) {\n"
            '    case 1: { print("one"); }\n'
            "  }\n"
            '  print("end");\n'
            "}"
        ),
        expect_stdout="end",
    ))
    cases.append(Case(
        "error", "control", "break directly in a switch case without a loop",
        (
            "function main() {\n"
            "  let integer x = 1;\n"
            "  switch (x) {\n"
            '    case 1: { print("one"); break; }\n'
            '    default: { print("other"); }\n'
            "  }\n"
            "}"
        ),
        expect_error="'break' used outside of a loop",
    ))
    return cases


def advanced_oop_cases() -> list[Case]:
    cases: list[Case] = []
    cases.append(Case(
        "run", "oop", "abstract payment with interface gateway composition",
        (
            "interface Gateway {\n"
            "  integer process(integer amount);\n"
            "  string name();\n"
            "}\n"
            "class StripeGateway implements Gateway {\n"
            '  public integer process(integer amount) { return amount + 10; }\n'
            '  public string name() { return "stripe"; }\n'
            "}\n"
            "abstract class AbstractPayment {\n"
            "  protected Gateway gateway;\n"
            "  public AbstractPayment(Gateway gateway) { this.gateway = gateway; }\n"
            "  public abstract integer makePayment(integer amount);\n"
            "  public integer configurePaymentGateway() {\n"
            "    return this.gateway.name().length;\n"
            "  }\n"
            "}\n"
            "class CardPayment extends AbstractPayment {\n"
            "  public CardPayment(Gateway gateway) { super(gateway); }\n"
            "  public integer makePayment(integer amount) {\n"
            "    return this.gateway.process(amount);\n"
            "  }\n"
            "}\n"
            "function main() {\n"
            "  let Gateway g = new StripeGateway();\n"
            "  let payments = [new CardPayment(g)];\n"
            "  for (let payment of payments) {\n"
            "    print(payment.makePayment(5));\n"
            "    print(payment.configurePaymentGateway());\n"
            "  }\n"
            "}"
        ),
        expect_stdout="15\n6",
    ))
    cases.append(Case(
        "run", "oop", "super constructor chaining with super method in override",
        (
            "class Base {\n"
            "  integer size;\n"
            "  public Base(integer size) { this.size = size; }\n"
            "  public virtual integer fee() { return this.size; }\n"
            "}\n"
            "class Child extends Base {\n"
            "  integer bonus;\n"
            "  public Child(integer size, integer bonus) {\n"
            "    super(size);\n"
            "    this.bonus = bonus;\n"
            "  }\n"
            "  public override integer fee() {\n"
            "    return super.fee() + this.bonus;\n"
            "  }\n"
            "}\n"
            "function main() {\n"
            "  let Child c = new Child(10, 5);\n"
            "  print(c.fee());\n"
            "}"
        ),
        expect_stdout="15",
    ))
    cases.append(Case(
        "run", "oop", "for of dispatches virtual methods over subclasses",
        (
            "class Shape { public virtual integer area() { return 0; } }\n"
            "class Square extends Shape {\n"
            "  integer side;\n"
            "  public Square(integer side) { this.side = side; }\n"
            "  public override integer area() { return this.side * this.side; }\n"
            "}\n"
            "class Rect extends Shape {\n"
            "  integer w;\n"
            "  integer h;\n"
            "  public Rect(integer w, integer h) { this.w = w; this.h = h; }\n"
            "  public override integer area() { return this.w * this.h; }\n"
            "}\n"
            "function main() {\n"
            "  let shapes = [new Square(3), new Rect(2, 5)];\n"
            "  let integer total = 0;\n"
            "  for (let s of shapes) {\n"
            "    total = total + s.area();\n"
            "  }\n"
            "  print(total);\n"
            "}"
        ),
        expect_stdout="19",
    ))
    cases.append(Case(
        "run", "oop", "static registry counts updates from subclass instances",
        (
            "class Base {\n"
            "  static integer processed = 0;\n"
            "}\n"
            "class Child extends Base {\n"
            "  public integer work() {\n"
            "    Child.processed = Child.processed + 1;\n"
            "    return Child.processed;\n"
            "  }\n"
            "}\n"
            "function main() {\n"
            "  let Child c = new Child();\n"
            "  c.work();\n"
            "  c.work();\n"
            "  print(Base.processed);\n"
            "}"
        ),
        expect_stdout="2",
    ))
    cases.append(Case(
        "error", "oop", "private field is invisible outside its class",
        (
            "class Wallet {\n"
            "  private integer balance = 100;\n"
            "  public integer get() { return this.balance; }\n"
            "}\n"
            "function main() {\n"
            "  let Wallet w = new Wallet();\n"
            "  print(w.balance);\n"
            "}"
        ),
        expect_error="Cannot access private field 'Wallet.balance'",
    ))
    cases.append(Case(
        "error", "oop", "final class cannot be extended",
        (
            "final class Ledger {}\n"
            "class Broken extends Ledger {}\n"
            'function main() { print("never"); }'
        ),
        expect_error="Cannot extend final class 'Ledger'",
    ))
    return cases


@dataclass
class Resolved:
    id: str = ""
    kind: str = ""
    phase: str = ""
    category: str = ""
    name: str = ""
    source: str = ""
    expected_stdout: str = ""
    expected_error: str = ""
    expected_exit: str = ""
    notes: str = ""


def _cell(value: int | None) -> str:
    return "" if value is None else str(value)


def resolve_kind(
    cases: list[Case],
    kind: str,
    workdir: Path,
    problems: list[str],
    no_verify: bool,
) -> list[Resolved]:
    rows: list[Resolved] = []
    for case in cases:
        outcome = try_execute(case.kind, case.source, workdir)
        label = f"{kind} {case.category}/{case.name}"
        if outcome is None:
            problems.append(f"{label}: execution timed out (possible infinite loop)")
            continue
        for what, text in (("stdout", outcome.stdout), ("error", outcome.error)):
            if " at 0x" in text:
                problems.append(f"{label}: non-deterministic {what} (memory address)")
        row = Resolved(
            kind=kind, category=case.category, name=case.name,
            source=case.source, notes=case.notes,
        )
        if kind == "run":
            if outcome.error:
                problems.append(f"{label}: unexpected error: {outcome.error}")
                continue
            if case.expect_stdout is not None and case.expect_stdout != outcome.stdout:
                problems.append(
                    f"{label}: stdout mismatch\n"
                    f"      authored: {case.expect_stdout!r}\n"
                    f"      pipeline: {outcome.stdout!r}"
                )
            if case.expect_exit is not None and case.expect_exit != outcome.exit_code:
                problems.append(
                    f"{label}: exit mismatch authored {case.expect_exit} "
                    f"pipeline {outcome.exit_code}"
                )
            row.expected_stdout = outcome.stdout
            row.expected_exit = _cell(outcome.exit_code)
        elif kind == "check":
            if outcome.error:
                problems.append(f"{label}: expected clean, got: {outcome.error}")
                continue
        elif kind == "error":
            if not outcome.error:
                problems.append(f"{label}: expected failure but the pipeline succeeded")
                continue
            if case.expect_error and case.expect_error not in outcome.error:
                problems.append(
                    f"{label}: error mismatch\n"
                    f"      authored: {case.expect_error!r}\n"
                    f"      pipeline: {outcome.error!r}"
                )
            row.expected_error = outcome.error
            row.expected_stdout = outcome.stdout
            row.phase = case.phase or classify_phase(case.source, workdir)
        elif kind == "format":
            if outcome.error:
                problems.append(f"{label}: format_source failed: {outcome.error}")
                continue
            again = try_execute("format", outcome.stdout, workdir)
            if again is None:
                problems.append(f"{label}: idempotence check timed out")
                continue
            if again.error or again.stdout != outcome.stdout:
                detail = again.error or f"got {again.stdout!r}"
                problems.append(f"{label}: formatter is not idempotent: {detail}")
                continue
            row.expected_stdout = outcome.stdout
        rows.append(row)
    return rows


def collect_cases(workdir: Path, problems: list[str]) -> dict[str, list[Case]]:
    run_cases: list[Case] = []
    builder_errors: list[Case] = []
    for builder in (
        arith_cases, precedence_cases, compare_cases, logic_cases,
        truthiness_cases, string_cases, array_cases, control_cases,
        function_cases, oop_cases, collection_cases, misc_cases,
        decorator_cases, switch_cases, advanced_oop_cases,
    ):
        for case in builder():
            if case.kind == "error":
                builder_errors.append(case)
            else:
                run_cases.append(case)
    checks, example_errors = example_cases(workdir, problems)
    check = [
        Case("check", "features", name, source)
        for name, source in CHECK_SNIPPETS
    ] + checks
    error = [
        Case("error", category, name, source, expect_error=message)
        for category, name, source, message in AUTHORED_ERRORS
    ]
    error.extend(builder_errors)
    error.extend(mutation_error_cases(workdir))
    error.extend(errors_dir_cases(workdir, problems))
    error.extend(example_errors)
    return {
        "run": run_cases,
        "check": check,
        "error": error,
        "format": format_cases(run_cases, check),
    }


def print_sample(rows: list[Resolved], limit: int) -> None:
    shown: dict[str, int] = {}
    for row in rows:
        if shown.get(row.kind, 0) >= limit:
            continue
        shown[row.kind] = shown.get(row.kind, 0) + 1
        detail = ""
        if row.kind == "format":
            detail = f" -> {row.expected_stdout[:60]!r}"
        elif row.kind == "error":
            detail = f" [{row.phase}] {row.expected_error[:70]!r}"
        else:
            detail = f" out={row.expected_stdout[:70]!r}"
            if row.expected_exit:
                detail += f" exit={row.expected_exit}"
        print(f"  {row.id} {row.category}/{row.name}{detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=0, metavar="N",
                        help="print the first N rows of each kind")
    parser.add_argument("--no-verify", action="store_true",
                        help="write rows even when authored expectations fail")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="x-corpus-") as tmp:
        workdir = Path(tmp)
        problems: list[str] = []
        cases_by_kind = collect_cases(workdir, problems)
        resolved: list[Resolved] = []
        for kind in KIND_ORDER:
            rows = resolve_kind(cases_by_kind[kind], kind, workdir, problems,
                                args.no_verify)
            for index, row in enumerate(rows, start=1):
                row.id = f"{ID_PREFIX[kind]}{index:04d}"
            resolved.extend(rows)

    if problems:
        print(f"{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        if not args.no_verify:
            print("generation aborted (use --no-verify to write anyway)",
                  file=sys.stderr)
            return 1

    counts = {kind: 0 for kind in KIND_ORDER}
    ordered: list[Resolved] = []
    for kind in KIND_ORDER:
        rows = [row for row in resolved if row.kind == kind]
        counts[kind] = len(rows)
        ordered.extend(rows)
    write_module(HERE / "corpus_data.py", [asdict(row) for row in ordered])
    for kind in KIND_ORDER:
        print(f"{kind}: {counts[kind]} rows")
    print(f"total: {sum(counts.values())} rows in corpus_data.py")

    if args.sample:
        print(f"\nsample ({args.sample} per kind):")
        print_sample(resolved, args.sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
