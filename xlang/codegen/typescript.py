"""TypeScript backend: lower a checked X ``Program`` to a single ``.ts`` file.

The backend receives the *flattened* program the :class:`ModuleLoader` builds,
so every reachable X module has already been merged into one declaration list.
The output is therefore a single self-contained translation unit rather than a
tree of modules — there are no ``import``/``export module`` statements to emit,
and ``export`` is preserved only where the X source asked for it.

Design notes
------------
* **Types.** X annotations are parsed with :func:`xlang.typecheck.types.parse_type`
  and mapped structurally, so ``integer``, ``integer[]``, ``object<string, V>``
  and ``record{id; string name}`` all become their TypeScript equivalents rather
  than being copied verbatim.
* **Nested classes.** X nests class/interface/enum declarations inside other
  declarations and refers to them as ``Outer.Inner``. TypeScript has no nested
  class syntax, so nested types are hoisted into a merging ``namespace`` with
  the same name, which keeps ``Outer.Inner`` and ``new Outer.Inner()`` valid.
* **Operators.** X encodes a ternary as ``Binary(operator="?:", right=(a, b))``
  with a 2-tuple, and or-patterns as ``("or", [...])`` — neither has a
  dedicated node, so both are special-cased here.
* **Precedence.** Expressions are emitted with an explicit precedence walk so
  the output keeps the source's grouping without sprinkling redundant
  parentheses everywhere.
* **Template literals.** X interpolates with ``${expr}``; the parser leaves the
  ``$`` at the end of the preceding text part, so re-emission writes the text
  part verbatim and follows it with ``{expr}``.

Known divergences are documented in the repository README under the ``x
compile`` section; the goal is a faithful, readable translation, not a
byte-identical runtime.
"""

from __future__ import annotations

import json
from typing import Any

from ..ast_nodes import (
    ArrayLiteral,
    ArrayPattern,
    Assignment,
    AwaitExpression,
    Binary,
    BindingPattern,
    Block,
    BreakStatement,
    Call,
    ClassicForStatement,
    ClassDeclaration,
    DefaultPattern,
    DoWhileStatement,
    EnumDeclaration,
    EnumPattern,
    ExpressionStatement,
    ForStatement,
    FunctionDeclaration,
    FunctionExpression,
    Identifier,
    IfStatement,
    ImportAlias,
    ImportCall,
    ImportDeclaration,
    ImportNamespaceAlias,
    Index,
    InterfaceMapEntry,
    Literal,
    LiteralPattern,
    MatchArm,
    MatchExpression,
    Member,
    NamespaceDeclaration,
    NewExpression,
    ObjectLiteral,
    ObjectPattern,
    OptionalChain,
    Program,
    ResourceBinding,
    ReturnStatement,
    Spread,
    SwitchCase,
    SwitchStatement,
    TemplateLiteral,
    ThisExpression,
    ThrowStatement,
    TryStatement,
    TypeDeclaration,
    Unary,
    UndefinedLiteral,
    UndefinedPattern,
    VariableDeclaration,
    WhileStatement,
    WildcardPattern,
)
from ..typecheck.types import XType, parse_type
from . import CodegenError

# ── operator precedence (higher binds tighter) ───────────────────────────
_ASSIGN = 1
_ARROW = 1
_TERNARY = 2
_OR = 3
_AND = 4
_EQUALITY = 5
_RELATIONAL = 6
_ADDITIVE = 7
_MULTIPLICATIVE = 8
_UNARY = 9
_POSTFIX = 9
_CALL = 11

_BINARY_PREC: dict[str, int] = {
    "||": _OR,
    "or": _OR,
    "&&": _AND,
    "and": _AND,
    "==": _EQUALITY,
    "!=": _EQUALITY,
    "===": _EQUALITY,
    "!==": _EQUALITY,
    "<": _RELATIONAL,
    ">": _RELATIONAL,
    "<=": _RELATIONAL,
    ">=": _RELATIONAL,
    "instanceof": _RELATIONAL,
    "in": _RELATIONAL,
    "+": _ADDITIVE,
    "-": _ADDITIVE,
    "*": _MULTIPLICATIVE,
    "/": _MULTIPLICATIVE,
    "%": _MULTIPLICATIVE,
}

# X global builtin callables that map onto JavaScript globals.
_BUILTIN_CALLEES: dict[str, str] = {
    "print": "console.log",
    "input": "prompt",
}

# ``Console.<member>`` -> the JavaScript console member to emit.
_CONSOLE_MEMBERS: dict[str, str] = {
    "print": "log",
    "input": "prompt",
}

# X primitive spellings -> TypeScript primitives.
_PRIMITIVE_TYPES: dict[str, str] = {
    "integer": "number",
    "int": "number",
    "short": "number",
    "long": "number",
    "float": "number",
    "double": "number",
    "decimal": "number",
    "number": "number",
    "string": "string",
    "char": "string",
    "boolean": "boolean",
    "bool": "boolean",
    "void": "void",
    "any": "any",
    "null": "null",
    "undefined": "undefined",
    "object": "Record<string, any>",
    "function": "(...args: any[]) => any",
}

# X standard-library collection *types* grouped by the TypeScript type they
# map onto. ``PriorityQueue`` is deliberately absent: it has no TypeScript
# equivalent, so it stays an (unresolved) named type.
_ARRAY_COLLECTION_TYPES: frozenset[str] = frozenset(
    {"List", "ArrayList", "LinkedList", "Stack", "Queue"}
)
_MAP_COLLECTION_TYPES: frozenset[str] = frozenset(
    {"HashMap", "TreeMap", "LinkedHashMap", "LRUCache"}
)
_SET_COLLECTION_TYPES: frozenset[str] = frozenset({"Set", "TreeSet"})

# ``new <Name>(...)`` for a collection is lowered to the matching JavaScript
# construction, because the X class itself does not exist at runtime. The
# shapes mirror the interpreter's ``create`` functions: array-backed
# collections copy their optional initial array, maps take an (ignored)
# capacity, sets take an optional initial iterable.
_NEW_REDIRECTS: dict[str, str] = {
    "List": "array",
    "ArrayList": "array",
    "LinkedList": "array",
    "Stack": "array",
    "Queue": "array",
    "HashMap": "map",
    "TreeMap": "map",
    "LinkedHashMap": "map",
    "LRUCache": "map",
    "Set": "set",
    "TreeSet": "set",
}

# X builtin helpers that have no JavaScript equivalent and are emitted into the
# prelude on demand.
_HELPER_NAMES: frozenset[str] = frozenset(
    {"range", "typeOf", "sleep", "delete", "xKeys"}
)

_HELPER_SOURCES: dict[str, str] = {
    "range": (
        "function range(...args: number[]): number[] {\n"
        "  if (args.length === 1) {\n"
        "    return Array.from({ length: args[0] }, (_, index) => index);\n"
        "  }\n"
        "  const [start, end] = args;\n"
        "  const step = args.length > 2 ? args[2] : 1;\n"
        "  const result: number[] = [];\n"
        "  if (step >= 0) {\n"
        "    for (let index = start; index < end; index += step) result.push(index);\n"
        "  } else {\n"
        "    for (let index = start; index > end; index += step) result.push(index);\n"
        "  }\n"
        "  return result;\n"
        "}"
    ),
    "typeOf": (
        "function typeOf(value: any): string {\n"
        "  if (value === null) return 'null';\n"
        "  if (value === undefined) return 'undefined';\n"
        "  if (Array.isArray(value)) return 'array';\n"
        "  if (value instanceof Map) return 'map';\n"
        "  if (value instanceof Set) return 'set';\n"
        "  if (typeof value === 'function') return 'function';\n"
        "  if (typeof value === 'number') {\n"
        "    return Number.isInteger(value) ? 'integer' : 'float';\n"
        "  }\n"
        "  if (typeof value === 'object') return 'object';\n"
        "  return typeof value;\n"
        "}"
    ),
    "sleep": (
        "async function sleep(milliseconds: number): Promise<void> {\n"
        "  return new Promise((resolve) => setTimeout(resolve, milliseconds));\n"
        "}"
    ),
    "delete": (
        "function xDelete(container: any, key: any): boolean {\n"
        "  if (container instanceof Map || container instanceof Set) {\n"
        "    if (!container.has(key)) {\n"
        "      throw new Error('delete: key not found: ' + String(key));\n"
        "    }\n"
        "    container.delete(key);\n"
        "    return true;\n"
        "  }\n"
        "  if (Array.isArray(container) && typeof key === 'number') {\n"
        "    if (key < 0 || key >= container.length) {\n"
        "      throw new Error('delete: index out of bounds: ' + key);\n"
        "    }\n"
        "    container.splice(key, 1);\n"
        "    return true;\n"
        "  }\n"
        "  if (container == null || !(key in container)) {\n"
        "    throw new Error('delete: key not found: ' + String(key));\n"
        "  }\n"
        "  delete container[key];\n"
        "  return true;\n"
        "}"
    ),
    "xKeys": (
        "// X's `for (k in container)` iterates the keys of a map or the own\n"
        "// enumerable keys of an object; neither maps nor objects share a single\n"
        "// JavaScript iteration form, so both are normalised here.\n"
        "function xKeys(container: any): any[] {\n"
        "  if (container instanceof Map || container instanceof Set) {\n"
        "    return Array.from(container.keys());\n"
        "  }\n"
        "  return Object.keys(container);\n"
        "}"
    ),
}

_INDENT = "  "


def emit_typescript(
    program: Any, source_name: str | None = None, config: Any = None
) -> str:
    """Translate *program* into a single TypeScript source string."""
    return TypeScriptEmitter(program, source_name=source_name).emit()


class TypeScriptEmitter:
    """Walk an X ``Program`` and build TypeScript source text."""

    def __init__(self, program: Program, source_name: str | None = None) -> None:
        self.program = program
        self.source_name = source_name
        self._lines: list[str] = []
        self._indent = 0
        self._used_helpers: set[str] = set()
        # Container path (class/namespace names) currently open, used to
        # qualify bare references to nested types as ``Outer.Inner``.
        self._scope: list[str] = []
        # container name -> names of types nested directly inside it
        self._nested_types: dict[str, set[str]] = {}
        self._fresh_names: set[str] = set()
        self._analyse(program)

    # ── analysis ─────────────────────────────────────────────────────────

    def _analyse(self, program: Program) -> None:
        for declaration in program.declarations:
            if isinstance(declaration, ClassDeclaration):
                self._index_nested(declaration)

    def _index_nested(self, declaration: ClassDeclaration) -> None:
        nested = {
            member.name
            for member in declaration.members
            if isinstance(member, (ClassDeclaration, EnumDeclaration))
            and getattr(member, "name", None)
        }
        if nested:
            self._nested_types[declaration.name] = nested
            for member in declaration.members:
                if isinstance(member, ClassDeclaration):
                    self._index_nested(member)

    # ── output helpers ───────────────────────────────────────────────────

    def _line(self, text: str = "") -> None:
        if text:
            self._lines.append(f"{_INDENT * self._indent}{text}")
        else:
            self._lines.append("")

    def _open(self, header: str) -> None:
        self._line(f"{header} {{")
        self._indent += 1

    def _close(self, suffix: str = "}") -> None:
        self._indent -= 1
        self._line(suffix)

    def _statements(self, statements: list[Any]) -> None:
        for statement in statements:
            if statement is None:
                continue
            self._statement(statement)

    # ── entry point ──────────────────────────────────────────────────────

    def emit(self) -> str:
        self._lines = []
        for declaration in self.program.declarations:
            if declaration is None:
                continue
            if self._lines:
                # Separate top-level declarations with a blank line.
                self._line()
            self._declaration(declaration)

        body = "\n".join(self._lines).rstrip()
        sections: list[str] = [self._header()]
        prelude = self._prelude()
        if prelude:
            sections.append(prelude)
        if body:
            sections.append(body)
        return "\n\n".join(sections).rstrip() + "\n"

    def _header(self) -> str:
        origin = self.source_name or "X program"
        return (
            "// Generated by `x compile --target typescript`.\n"
            f"// Source: {origin}\n"
            "//\n"
            "// This is a direct translation of the X source. See the X README\n"
            "// (the `x compile` section) for known divergences from the\n"
            "// interpreter's semantics."
        )

    def _prelude(self) -> str:
        return "\n\n".join(
            _HELPER_SOURCES[name] for name in sorted(self._used_helpers)
        )

    # ── declarations ─────────────────────────────────────────────────────

    def _declaration(self, declaration: Any) -> None:
        if isinstance(declaration, ClassDeclaration):
            self._emit_type_with_namespace(declaration, declaration.name)
            return
        if isinstance(declaration, EnumDeclaration):
            prefix = self._declaration_modifiers(declaration.modifiers)
            self._emit_enum(declaration, prefix)
            return
        if isinstance(declaration, FunctionDeclaration):
            self._function(declaration)
            return
        if isinstance(declaration, VariableDeclaration):
            self._line(self._variable_statement(declaration) + ";")
            return
        if isinstance(declaration, TypeDeclaration):
            prefix = self._declaration_modifiers(declaration.modifiers)
            rendered = self._ts_type(declaration.type_name)
            self._line(f"{prefix}type {declaration.name} = {rendered};")
            return
        if isinstance(declaration, ImportDeclaration):
            self._import_declaration(declaration)
            return
        if isinstance(declaration, ImportAlias):
            if declaration.alias_name != declaration.source_name:
                self._line(
                    f"const {declaration.alias_name} = {declaration.source_name};"
                )
            return
        if isinstance(declaration, ImportNamespaceAlias):
            members = ", ".join(declaration.exported_names)
            self._line(f"const {declaration.alias_name} = {{ {members} }};")
            return
        if isinstance(declaration, NamespaceDeclaration):
            self._namespace_declaration(declaration)
            return
        if isinstance(declaration, ExpressionStatement):
            # X allows top-level statements; they run in declaration order.
            self._statement(declaration)
            return
        raise CodegenError(
            f"cannot translate declaration of type {type(declaration).__name__}",
            self.source_name,
        )

    def _import_declaration(self, declaration: ImportDeclaration) -> None:
        """Skip the import itself; emit only a call the import carries.

        The loader has already inlined the imported module's declarations and
        any alias bindings (``ImportAlias`` / ``ImportNamespaceAlias``) as
        sibling declarations, so ``import B.greet("Maya")`` reduces to the
        bare call.
        """
        if declaration.statement is not None:
            self._statement(declaration.statement)

    def _namespace_declaration(self, declaration: NamespaceDeclaration) -> None:
        names: list[str] = []
        for member in declaration.declarations:
            name = getattr(member, "name", None)
            if isinstance(name, str) and name and name not in names:
                names.append(name)
        if not names:
            return
        joined = ", ".join(names)
        self._line(f"const {declaration.name} = {{ {joined} }};")

    # ── classes, interfaces, enums ───────────────────────────────────────

    def _emit_type_with_namespace(
        self, declaration: ClassDeclaration, ts_name: str
    ) -> None:
        self._emit_class(declaration, ts_name)
        nested = [
            member
            for member in declaration.members
            if isinstance(member, (ClassDeclaration, EnumDeclaration))
        ]
        if not nested:
            return
        self._open(f"namespace {ts_name}")
        self._scope.append(ts_name)
        for index, member in enumerate(nested):
            if index:
                self._line()
            self._emit_namespace_member(member)
        self._scope.pop()
        self._close()

    def _emit_namespace_member(self, member: Any) -> None:
        if isinstance(member, EnumDeclaration):
            self._emit_enum(member, "export ")
            return
        if isinstance(member, ClassDeclaration):
            self._scope.append(member.name)
            self._open(f"export {self._class_header(member, member.name)}")
            self._class_body(member)
            self._close()
            self._scope.pop()
            nested = [
                inner
                for inner in member.members
                if isinstance(inner, (ClassDeclaration, EnumDeclaration))
            ]
            if nested:
                self._line()
                self._open(f"export namespace {member.name}")
                self._scope.append(member.name)
                for index, inner in enumerate(nested):
                    if index:
                        self._line()
                    self._emit_namespace_member(inner)
                self._scope.pop()
                self._close()

    def _class_header(self, declaration: ClassDeclaration, ts_name: str) -> str:
        keyword = "interface" if declaration.is_interface else "class"
        generics = self._type_parameters(declaration.generic_parameters)
        header = f"{keyword} {ts_name}{generics}"
        if declaration.is_interface:
            extends = [declaration.parent_name] if declaration.parent_name else []
            extends.extend(declaration.implemented_types)
            if extends:
                rendered = ", ".join(self._resolve_type_name(n) for n in extends)
                header += f" extends {rendered}"
            return header
        if declaration.parent_name:
            header += f" extends {self._resolve_type_name(declaration.parent_name)}"
        if declaration.implemented_types:
            rendered = ", ".join(
                self._resolve_type_name(name) for name in declaration.implemented_types
            )
            header += f" implements {rendered}"
        return header

    def _emit_class(self, declaration: ClassDeclaration, ts_name: str) -> None:
        modifiers = self._declaration_modifiers(declaration.modifiers)
        self._scope.append(ts_name)
        self._open(f"{modifiers}{self._class_header(declaration, ts_name)}")
        self._class_body(declaration)
        self._close()
        self._scope.pop()

    def _class_body(self, declaration: ClassDeclaration) -> None:
        emitted = 0
        for member in declaration.members:
            if isinstance(member, (ClassDeclaration, EnumDeclaration)):
                # Hoisted into the merging namespace; skip it here.
                continue
            if emitted:
                self._line()
            emitted += 1
            self._class_member(member, declaration)

    def _class_member(self, member: Any, owner: ClassDeclaration) -> None:
        if isinstance(member, FunctionDeclaration):
            if not owner.is_interface and self._is_constructor(member, owner):
                self._constructor(member)
                return
            self._function(member, is_method=True, is_interface=owner.is_interface)
            return
        if isinstance(member, VariableDeclaration):
            self._line(self._class_field(member, owner) + ";")
            return
        if isinstance(member, InterfaceMapEntry):
            self._line(self._map_entry_field(member) + ";")
            return

    def _map_entry_field(self, entry: InterfaceMapEntry) -> str:
        fields = "; ".join(
            f"{field.name}: {self._ts_type(field.type_name)}"
            if field.type_name
            else field.name
            for field in entry.members
        )
        shape = "{ " + fields + " }" if fields else "{}"
        return f"[key: {self._ts_type(entry.key_type)}]: {shape}"

    def _is_constructor(
        self, member: FunctionDeclaration, owner: ClassDeclaration
    ) -> bool:
        # A function named exactly like its enclosing class, with no declared
        # return type, is the constructor — the convention the parser and
        # interpreter both use.
        return member.name == owner.name and member.return_type is None

    def _constructor(self, member: FunctionDeclaration) -> None:
        parameters = self._parameters(member.parameters)
        modifiers = self._method_modifiers(member.modifiers)
        self._open(f"{modifiers}constructor({parameters})")
        self._statements(member.body)
        self._close()

    def _class_field(
        self, member: VariableDeclaration, owner: ClassDeclaration
    ) -> str:
        prefix = self._field_modifiers(member.modifiers)
        if member.pattern is not None:
            target = self._destructuring_target(member.pattern)
        else:
            target = member.name
        annotation = f": {self._ts_type(member.type_name)}" if member.type_name else ""
        if member.initializer is not None:
            value = self._expr(member.initializer, 0)
            return f"{prefix}{target}{annotation} = {value}"
        return f"{prefix}{target}{annotation}"

    def _emit_enum(self, declaration: EnumDeclaration, prefix: str = "") -> None:
        if not declaration.members:
            self._line(f"{prefix}enum {declaration.name} {{}}")
            return
        self._line(f"{prefix}enum {declaration.name} {{")
        self._indent += 1
        for name, value in declaration.members:
            if value is None:
                self._line(f"{name},")
            else:
                self._line(f"{name} = {self._expr(value, 0)},")
        self._indent -= 1
        self._line("}")

    # ── functions ────────────────────────────────────────────────────────

    def _function(
        self,
        declaration: FunctionDeclaration,
        is_method: bool = False,
        is_interface: bool = False,
    ) -> None:
        parameters = self._parameters(declaration.parameters)
        returns = (
            f": {self._ts_type(declaration.return_type)}"
            if declaration.return_type
            else ""
        )
        if is_interface:
            self._line(f"{declaration.name}({parameters}){returns};")
            return
        if is_method:
            modifiers = self._method_modifiers(declaration.modifiers)
            async_ = "async " if declaration.is_async else ""
            generics = self._type_parameters(declaration.generic_parameters)
            self._open(
                f"{modifiers}{async_}{generics}{declaration.name}"
                f"({parameters}){returns}"
            )
            self._statements(declaration.body)
            self._close()
            return
        export = self._declaration_modifiers(declaration.modifiers)
        async_ = "async " if declaration.is_async else ""
        generics = self._type_parameters(declaration.generic_parameters)
        self._open(
            f"{export}{async_}function {generics}{declaration.name}"
            f"({parameters}){returns}"
        )
        self._statements(declaration.body)
        self._close()

    def _type_parameters(self, parameters: list[str]) -> str:
        if not parameters:
            return ""
        return f"<{', '.join(parameters)}>"

    def _parameters(self, parameters: list[Any]) -> str:
        rendered: list[str] = []
        for parameter in parameters:
            text = parameter.name
            if parameter.type_name:
                text += f": {self._ts_type(parameter.type_name)}"
            if parameter.is_rest:
                text = f"...{text}"
            if parameter.has_default and parameter.default_value is not None:
                text += f" = {self._expr(parameter.default_value, 0)}"
            rendered.append(text)
        return ", ".join(rendered)

    def _variable_statement(self, declaration: VariableDeclaration) -> str:
        export = (
            "export " if "export" in (declaration.modifiers or set()) else ""
        )
        keyword = "const" if declaration.constant else "let"
        if declaration.pattern is not None:
            target = self._destructuring_target(declaration.pattern)
        else:
            target = declaration.name
        annotation = (
            f": {self._ts_type(declaration.type_name)}" if declaration.type_name else ""
        )
        if declaration.initializer is not None:
            value = self._expr(declaration.initializer, 0)
            return f"{export}{keyword} {target}{annotation} = {value}"
        return f"{export}{keyword} {target}{annotation}"

    def _destructuring_target(self, pattern: Any) -> str:
        """Render a binding pattern as a TypeScript destructuring target."""
        if isinstance(pattern, BindingPattern):
            return pattern.name
        if isinstance(pattern, WildcardPattern):
            return "_"
        if isinstance(pattern, ArrayPattern):
            parts: list[str] = []
            for item in pattern.items:
                if isinstance(item, WildcardPattern):
                    parts.append("")
                else:
                    parts.append(self._destructuring_target(item))
            if pattern.rest_name:
                parts.append(f"...{pattern.rest_name}")
            return "[" + ", ".join(parts) + "]"
        if isinstance(pattern, ObjectPattern):
            fields: list[str] = []
            for field_name, field_pattern in pattern.fields:
                if isinstance(field_pattern, WildcardPattern):
                    continue
                rendered = self._destructuring_target(field_pattern)
                if isinstance(field_pattern, BindingPattern) and (
                    field_pattern.name == field_name
                ):
                    fields.append(field_name)
                else:
                    fields.append(f"{field_name}: {rendered}")
            if pattern.rest_name:
                fields.append(f"...{pattern.rest_name}")
            return "{ " + ", ".join(fields) + " }"
        return "_"

    # ── modifiers ────────────────────────────────────────────────────────

    def _declaration_modifiers(self, modifiers: set[str] | None) -> str:
        parts: list[str] = []
        if modifiers and "export" in modifiers:
            parts.append("export")
        if modifiers and "abstract" in modifiers:
            parts.append("abstract")
        return f"{' '.join(parts)} " if parts else ""

    def _method_modifiers(self, modifiers: set[str] | None) -> str:
        parts: list[str] = []
        if not modifiers:
            return ""
        if "private" in modifiers:
            parts.append("private")
        elif "protected" in modifiers:
            parts.append("protected")
        if "static" in modifiers:
            parts.append("static")
        if "abstract" in modifiers:
            parts.append("abstract")
        return f"{' '.join(parts)} " if parts else ""

    def _field_modifiers(self, modifiers: set[str] | None) -> str:
        parts: list[str] = []
        if not modifiers:
            return ""
        if "private" in modifiers:
            parts.append("private")
        elif "protected" in modifiers:
            parts.append("protected")
        if "static" in modifiers:
            parts.append("static")
        if "final" in modifiers or "readonly" in modifiers:
            parts.append("readonly")
        return f"{' '.join(parts)} " if parts else ""

    # ── statements ───────────────────────────────────────────────────────

    def _statement(self, statement: Any) -> None:
        if statement is None:
            return
        if isinstance(statement, Block):
            self._open("")
            self._statements(statement.statements)
            self._close()
            return
        if isinstance(statement, ExpressionStatement):
            self._expression_statement(statement.expression)
            return
        if isinstance(statement, VariableDeclaration):
            self._line(self._variable_statement(statement) + ";")
            return
        if isinstance(statement, IfStatement):
            self._if(statement)
            return
        if isinstance(statement, WhileStatement):
            self._open(
                f"while ({self._expr(statement.condition, 0)})"
            )
            self._statements(statement.body.statements)
            self._close()
            return
        if isinstance(statement, DoWhileStatement):
            self._open("do")
            self._statements(statement.body.statements)
            self._close(f"}} while ({self._expr(statement.condition, 0)});")
            return
        if isinstance(statement, ClassicForStatement):
            self._classic_for(statement)
            return
        if isinstance(statement, ForStatement):
            self._for(statement)
            return
        if isinstance(statement, ReturnStatement):
            if statement.value is None:
                self._line("return;")
            else:
                self._line(f"return {self._expr(statement.value, 0)};")
            return
        if isinstance(statement, BreakStatement):
            self._line("continue;" if statement.is_continue else "break;")
            return
        if isinstance(statement, ThrowStatement):
            self._line(f"throw {self._expr(statement.value, 0)};")
            return
        if isinstance(statement, TryStatement):
            self._try(statement)
            return
        if isinstance(statement, SwitchStatement):
            self._switch(statement)
            return
        if isinstance(statement, MatchExpression):
            self._match_statement(statement)
            return
        if isinstance(statement, ClassDeclaration):
            self._declaration(statement)
            return
        raise CodegenError(
            f"cannot translate statement of type {type(statement).__name__}",
            self.source_name,
        )

    def _expression_statement(self, expression: Any) -> None:
        if isinstance(expression, MatchExpression):
            # A match in statement position must not become an IIFE, or a
            # `return` inside an arm would return from the arrow instead of
            # the enclosing function.
            self._match_statement(expression)
            return
        self._line(f"{self._expr(expression, 0)};")

    def _if(self, statement: IfStatement) -> None:
        self._open(f"if ({self._expr(statement.condition, 0)})")
        self._statements(statement.then_branch.statements)
        self._close()
        branch = statement.else_branch
        while isinstance(branch, IfStatement):
            self._open(f"else if ({self._expr(branch.condition, 0)})")
            self._statements(branch.then_branch.statements)
            self._close()
            branch = branch.else_branch
        if branch is not None:
            self._open("else")
            self._statements(branch.statements)
            self._close()

    def _classic_for(self, statement: ClassicForStatement) -> None:
        if statement.initializer is None:
            initializer = ""
        elif isinstance(statement.initializer, VariableDeclaration):
            initializer = self._variable_statement(statement.initializer)
        else:
            initializer = self._expr(statement.initializer, 0)
        condition = (
            self._expr(statement.condition, 0)
            if statement.condition is not None
            else ""
        )
        increment = (
            self._expr(statement.increment, 0)
            if statement.increment is not None
            else ""
        )
        self._open(f"for ({initializer}; {condition}; {increment})")
        self._statements(statement.body.statements)
        self._close()

    def _for(self, statement: ForStatement) -> None:
        keyword = "const" if statement.constant else "let"
        if statement.binding_pattern is not None:
            variable = self._destructuring_target(statement.binding_pattern)
        else:
            variable = statement.variable or "_"
        annotation = (
            f": {self._ts_type(statement.type_name)}" if statement.type_name else ""
        )
        iterable = self._expr(statement.iterable, 0)
        if statement.iteration_mode == "in":
            # X's `in` iterates a map's keys or an object's own keys; neither
            # maps nor objects share a single JavaScript iteration form.
            self._used_helpers.add("xKeys")
            header = f"for ({keyword} {variable}{annotation} of xKeys({iterable}))"
        else:
            header = f"for ({keyword} {variable}{annotation} of {iterable})"
        self._open(header)
        self._statements(statement.body.statements)
        self._close()

    def _try(self, statement: TryStatement) -> None:
        """Lower ``try (let r = ...)`` and ordinary try/catch/finally.

        Resources have no TypeScript equivalent, so they are closed by an inner
        ``finally`` wrapped around the body — which is where the interpreter
        closes them, before any ``catch``/``finally`` of the outer statement.
        The outer statement's own ``catch``/``finally`` therefore attach to the
        outer ``try`` that carries the bindings, not to the inner one.
        """
        if statement.resources:
            self._open("try")
            self._resource_bindings(statement.resources)
            self._open("try")
            self._statements(statement.body.statements)
            self._close()
            self._open("finally")
            for binding in reversed(statement.resources):
                self._line(f"{binding.name}.close();")
            self._close()
            self._close()
            self._catch_clauses(statement)
            return
        self._open("try")
        self._statements(statement.body.statements)
        self._close()
        self._catch_clauses(statement)

    def _resource_bindings(self, resources: list[ResourceBinding]) -> None:
        for binding in resources:
            keyword = "const" if binding.constant else "let"
            annotation = (
                f": {self._ts_type(binding.type_name)}" if binding.type_name else ""
            )
            self._line(
                f"{keyword} {binding.name}{annotation} = {self._expr(binding.value, 0)};"
            )

    def _catch_clauses(self, statement: TryStatement) -> None:
        for catch_type, variable, body in statement.catches:
            name = variable or "error"
            annotation = f": {self._ts_type(catch_type)}" if catch_type else ""
            self._open(f"catch ({name}{annotation})")
            self._statements(body.statements)
            self._close()
        if statement.finally_body is not None:
            self._open("finally")
            self._statements(statement.finally_body.statements)
            self._close()

    def _switch(self, statement: SwitchStatement) -> None:
        self._open(f"switch ({self._expr(statement.expression, 0)})")
        for case in statement.cases:
            if case.value is None:
                header = "default:"
            else:
                header = f"case {self._expr(case.value, 0)}:"
            self._open(header)
            self._statements(case.body.statements)
            self._close()
        self._close()

    # ── match ────────────────────────────────────────────────────────────

    def _match_statement(self, expression: MatchExpression) -> None:
        """Lower a statement-position ``match`` to an ``if``/``else`` chain.

        A statement-position match becomes a block so that ``return`` and
        ``break`` inside an arm still reach the enclosing function.
        """
        subject = self._fresh_variable("match")
        self._line(f"const {subject} = {self._expr(expression.value, 0)};")
        self._match_chain(expression, subject, returns=False)

    def _match_expression(self, node: MatchExpression) -> str:
        subject = self._fresh_variable("match")
        lines: list[str] = []
        saved_indent = self._indent
        saved_lines = self._lines
        self._lines = lines
        self._indent = saved_indent + 1
        try:
            self._line(f"const {subject} = {self._expr(node.value, 0)};")
            self._match_chain(node, subject, returns=True)
        finally:
            self._indent = saved_indent
            self._lines = saved_lines
        body = "\n".join(lines)
        return f"(() => {{\n{body}\n{'  ' * saved_indent}}})()"

    def _match_chain(
        self, expression: MatchExpression, subject: str, returns: bool
    ) -> None:
        first = True
        has_default = False
        for arm in expression.arms:
            condition, bindings = self._pattern_condition(arm.pattern, subject)
            guarded = arm.guard is not None
            # A pattern that matches everything with no guard is the chain's
            # default arm; a binding pattern *with* a guard is a normal arm
            # gated by the guard.
            if condition is None or (condition == "true" and not guarded):
                has_default = True
                if first:
                    self._open("if (true)")
                else:
                    self._open("else")
                for binding in bindings:
                    self._line(binding)
                self._arm_body(arm, returns)
                self._close()
                break
            if guarded:
                condition = self._guarded_condition(condition, arm, subject)
            header = f"if ({condition})" if first else f"else if ({condition})"
            self._open(header)
            for binding in bindings:
                self._line(binding)
            self._arm_body(arm, returns)
            self._close()
            first = False
        if not has_default:
            # A match with no default falls through silently, mirroring the
            # interpreter, so an empty else closes the chain.
            self._open("else")
            self._close()

    def _guarded_condition(
        self, condition: str, arm: MatchArm, subject: str
    ) -> str:
        """Build the ``if`` condition for a guarded arm.

        The guard may reference the names the pattern binds, and those names
        are not in scope in a plain ``if`` condition, so a binding guard is
        applied through a one-parameter arrow that receives the subject.
        """
        guard_text = self._expr(arm.guard, 0)
        names = self._pattern_bound_names(arm.pattern)
        if names:
            parameters = ", ".join(names)
            guard_text = f"(({parameters}) => {guard_text})({subject})"
        if condition == "true":
            return guard_text
        return f"({condition}) && ({guard_text})"

    def _pattern_bound_names(self, pattern: Any) -> list[str]:
        """Names a match pattern binds, in declaration order."""
        if isinstance(pattern, BindingPattern):
            return [pattern.name]
        if isinstance(pattern, ArrayPattern):
            names: list[str] = []
            for item in pattern.items:
                names.extend(self._pattern_bound_names(item))
            if pattern.rest_name:
                names.append(pattern.rest_name)
            return names
        if isinstance(pattern, ObjectPattern):
            names = []
            for _field_name, field_pattern in pattern.fields:
                names.extend(self._pattern_bound_names(field_pattern))
            if pattern.rest_name:
                names.append(pattern.rest_name)
            return names
        if isinstance(pattern, DefaultPattern):
            return self._pattern_bound_names(pattern.pattern)
        if isinstance(pattern, tuple) and len(pattern) == 2 and pattern[0] == "or":
            names = []
            for alternative in pattern[1]:
                names.extend(self._pattern_bound_names(alternative))
            return names
        return []

    def _arm_body(self, arm: MatchArm, returns: bool) -> None:
        if isinstance(arm.body, Block):
            self._statements(arm.body.statements)
        elif returns:
            self._line(f"return {self._expr(arm.body, 0)};")
        else:
            self._line(f"{self._expr(arm.body, 0)};")

    def _fresh_variable(self, hint: str) -> str:
        base = f"__{hint}"
        candidate = base
        counter = 0
        while candidate in self._fresh_names:
            counter += 1
            candidate = f"{base}{counter}"
        self._fresh_names.add(candidate)
        return candidate

    def _pattern_condition(
        self, pattern: Any, subject: str
    ) -> tuple[str | None, list[str]]:
        """Return ``(condition, bindingStatements)`` for *pattern*.

        ``None`` as the condition means the arm is the default arm.
        """
        if pattern is None:
            return None, []
        if isinstance(pattern, WildcardPattern):
            return "true", []
        if isinstance(pattern, BindingPattern):
            return "true", [f"const {pattern.name} = {subject};"]
        if isinstance(pattern, LiteralPattern):
            return f"{subject} === {self._literal(pattern.value)}", []
        if isinstance(pattern, UndefinedPattern):
            return f"{subject} === undefined", []
        if isinstance(pattern, EnumPattern):
            qualified = self._resolve_type_name(
                f"{pattern.enum_name}.{pattern.member_name}"
            )
            return f"{subject} === {qualified}", []
        if isinstance(pattern, DefaultPattern):
            condition, bindings = self._pattern_condition(pattern.pattern, subject)
            if condition is None:
                return None, bindings
            return condition, bindings
        if isinstance(pattern, ArrayPattern):
            return self._array_pattern_condition(pattern, subject)
        if isinstance(pattern, ObjectPattern):
            return self._object_pattern_condition(pattern, subject)
        if isinstance(pattern, tuple) and len(pattern) == 2 and pattern[0] == "or":
            conditions: list[str] = []
            for alternative in pattern[1]:
                condition, _ = self._pattern_condition(alternative, subject)
                if condition is None:
                    return None, []
                conditions.append(condition)
            return f"({' || '.join(conditions)})", []
        return None, []

    def _array_pattern_condition(
        self, pattern: ArrayPattern, subject: str
    ) -> tuple[str, list[str]]:
        minimum = len(pattern.items)
        condition = f"Array.isArray({subject}) && {subject}.length >= {minimum}"
        bindings: list[str] = []
        destructured = self._fresh_variable("array")
        bindings.append(f"const {destructured} = {subject};")
        for index, item in enumerate(pattern.items):
            element = f"{destructured}[{index}]"
            if isinstance(item, BindingPattern):
                bindings.append(f"const {item.name} = {element};")
            elif isinstance(item, WildcardPattern):
                continue
            else:
                nested, nested_bindings = self._pattern_condition(item, element)
                bindings.extend(nested_bindings)
                if nested is not None:
                    condition = f"{condition} && ({nested})"
        if pattern.rest_name:
            bindings.append(
                f"const {pattern.rest_name} = {destructured}.slice({minimum});"
            )
        return condition, bindings

    def _object_pattern_condition(
        self, pattern: ObjectPattern, subject: str
    ) -> tuple[str, list[str]]:
        condition = f"{subject} != null"
        bindings: list[str] = []
        destructured = self._fresh_variable("object")
        bindings.append(f"const {destructured} = {subject};")
        for field_name, field_pattern in pattern.fields:
            value = f"{destructured}.{field_name}"
            condition = f"{condition} && {value} !== undefined"
            if isinstance(field_pattern, BindingPattern):
                bindings.append(f"const {field_pattern.name} = {value};")
            elif isinstance(field_pattern, WildcardPattern):
                continue
            else:
                nested, nested_bindings = self._pattern_condition(field_pattern, value)
                bindings.extend(nested_bindings)
                if nested is not None:
                    condition = f"{condition} && ({nested})"
        if pattern.rest_name:
            bindings.append(f"const {pattern.rest_name} = {{ ...{destructured} }};")
        return condition, bindings

    # ── expressions ──────────────────────────────────────────────────────

    def _expr(self, node: Any, min_precedence: int = 0) -> str:
        text, precedence = self._expression(node)
        if precedence < min_precedence:
            return f"({text})"
        return text

    def _expression(self, node: Any) -> tuple[str, int]:
        if node is None:
            return "undefined", _CALL
        if isinstance(node, Literal):
            return self._literal(node.value), _CALL
        if isinstance(node, UndefinedLiteral):
            return "undefined", _CALL
        if isinstance(node, Identifier):
            return node.name, _CALL
        if isinstance(node, ThisExpression):
            return "super" if node.is_super else "this", _CALL
        if isinstance(node, TemplateLiteral):
            return self._template(node), _CALL
        if isinstance(node, ArrayLiteral):
            items = ", ".join(self._expr(item, 0) for item in node.items)
            return f"[{items}]", _CALL
        if isinstance(node, ObjectLiteral):
            return self._object_literal(node), _CALL
        if isinstance(node, Spread):
            return f"...{self._expr(node.value, 0)}", _CALL
        if isinstance(node, Unary):
            return self._unary(node)
        if isinstance(node, AwaitExpression):
            return f"await {self._expr(node.value, _UNARY)}", _UNARY
        if isinstance(node, Binary):
            return self._binary(node)
        if isinstance(node, Assignment):
            return self._assignment(node)
        if isinstance(node, Call):
            return self._call(node)
        if isinstance(node, Member):
            return self._member_text(node), _CALL
        if isinstance(node, Index):
            return (
                f"{self._expr(node.object, _CALL)}[{self._expr(node.index, 0)}]",
                _CALL,
            )
        if isinstance(node, OptionalChain):
            return self._optional_chain(node), _CALL
        if isinstance(node, NewExpression):
            return self._new(node), _CALL
        if isinstance(node, FunctionExpression):
            return self._function_expression(node)
        if isinstance(node, MatchExpression):
            return self._match_expression(node), _TERNARY
        if isinstance(node, ImportCall):
            return self._import_call(node), _CALL
        raise CodegenError(
            f"cannot translate expression of type {type(node).__name__}",
            self.source_name,
        )

    def _literal(self, value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, float):
            if value != value:  # NaN
                return "Number.NaN"
            if value == float("inf"):
                return "Number.POSITIVE_INFINITY"
            if value == float("-inf"):
                return "Number.NEGATIVE_INFINITY"
            return repr(value)
        return str(value)

    def _template(self, node: TemplateLiteral) -> str:
        parts: list[str] = ["`"]
        for part in node.parts:
            if isinstance(part, str):
                parts.append(
                    part.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\$")
                )
            else:
                # The parser leaves a preceding ``$`` in the text part, so only
                # the braces are added here.
                parts.append(f"{{{self._expr(part, 0)}}}")
        parts.append("`")
        return "".join(parts)

    def _object_literal(self, node: ObjectLiteral) -> str:
        entries: list[str] = []
        for entry in node.entries:
            if entry.key is None:
                # A spread entry; its value is already a Spread node that
                # renders with the leading ``...``.
                entries.append(self._expr(entry.value, 0))
            else:
                entries.append(f"{entry.key}: {self._expr(entry.value, 0)}")
        if not entries:
            return "{}"
        return "{ " + ", ".join(entries) + " }"

    def _unary(self, node: Unary) -> tuple[str, int]:
        operator = node.operator
        if operator in ("++", "--"):
            operand = self._expr(node.operand, _POSTFIX)
            if node.postfix:
                return f"{operand}{operator}", _POSTFIX
            return f"{operator}{operand}", _UNARY
        if operator in ("typeof", "void", "delete"):
            operand = self._expr(node.operand, _UNARY)
            return f"{operator} {operand}", _UNARY
        operand = self._expr(node.operand, _UNARY + 1)
        return f"{operator}{operand}", _UNARY

    def _binary(self, node: Binary) -> tuple[str, int]:
        if node.operator == "?:":
            true_value, false_value = node.right
            text = (
                f"{self._expr(node.left, _AND + 1)} ? "
                f"{self._expr(true_value, _TERNARY)} : "
                f"{self._expr(false_value, _TERNARY)}"
            )
            return text, _TERNARY
        precedence = _BINARY_PREC.get(node.operator)
        if precedence is None:
            raise CodegenError(
                f"unknown binary operator '{node.operator}'",
                self.source_name,
            )
        left = self._expr(node.left, precedence)
        right = self._expr(node.right, precedence + 1)
        if node.operator == "and":
            operator = " && "
        elif node.operator == "or":
            operator = " || "
        else:
            operator = f" {node.operator} "
        return f"{left}{operator}{right}", precedence

    def _assignment(self, node: Assignment) -> tuple[str, int]:
        target = self._expr(node.target, _CALL)
        value = self._expr(node.value, _ASSIGN)
        return f"{target} {node.operator} {value}", _ASSIGN

    def _call(self, node: Call) -> tuple[str, int]:
        callee = node.callee
        if isinstance(callee, Identifier):
            if callee.name == "delete":
                return self._delete_call(node)
            if callee.name in _BUILTIN_CALLEES:
                callee_text = _BUILTIN_CALLEES[callee.name]
            elif callee.name in ("range", "typeOf", "sleep"):
                self._used_helpers.add(callee.name)
                callee_text = callee.name
            else:
                callee_text = callee.name
        elif isinstance(callee, Member):
            callee_text = self._member_text(callee)
        else:
            callee_text = self._expr(callee, _CALL)
        arguments = ", ".join(self._expr(argument, 0) for argument in node.arguments)
        return f"{callee_text}({arguments})", _CALL

    def _delete_call(self, node: Call) -> tuple[str, int]:
        """Lower ``delete(o.p)`` / ``delete(o[i])`` to the polymorphic helper."""
        if len(node.arguments) == 1:
            target = node.arguments[0]
            if isinstance(target, Member):
                container = self._expr(target.object, 0)
                key = json.dumps(target.name)
                self._used_helpers.add("delete")
                return f"xDelete({container}, {key})", _CALL
            if isinstance(target, Index):
                container = self._expr(target.object, 0)
                key = self._expr(target.index, 0)
                self._used_helpers.add("delete")
                return f"xDelete({container}, {key})", _CALL
        arguments = ", ".join(self._expr(argument, 0) for argument in node.arguments)
        return f"delete({arguments})", _CALL

    def _member_text(self, node: Member) -> str:
        if isinstance(node.object, Identifier) and node.object.name == "Console":
            mapped = _CONSOLE_MEMBERS.get(node.name, node.name)
            return f"console.{mapped}"
        return f"{self._expr(node.object, _CALL)}.{node.name}"

    def _optional_chain(self, node: OptionalChain) -> str:
        text = self._expr(node.object, _CALL)
        for segment in node.segments:
            if segment.kind == "member":
                connector = "?." if segment.optional else "."
                text += f"{connector}{segment.value}"
            elif segment.kind == "index":
                if segment.optional:
                    text += f"?.[{self._expr(segment.value, 0)}]"
                else:
                    text += f"[{self._expr(segment.value, 0)}]"
            elif segment.kind == "call":
                arguments, _type_arguments = segment.value
                rendered = ", ".join(self._expr(argument, 0) for argument in arguments)
                # An optional *call* is `?.(...)`; a plain call in a chain
                # needs no dot before the parentheses.
                connector = "?." if segment.optional else ""
                text += f"{connector}({rendered})"
        return text

    def _new(self, node: NewExpression) -> str:
        arguments = ", ".join(self._expr(argument, 0) for argument in node.arguments)
        try:
            parsed = parse_type(node.class_name)
            base_name = parsed.name
        except Exception:
            base_name = node.class_name.split("<", 1)[0].strip()
            parsed = None
        redirect = _NEW_REDIRECTS.get(base_name)
        if redirect == "array":
            # The interpreter's create copies an optional initial array, so a
            # literal can be emitted directly and anything else is spread into
            # a fresh array.
            if not node.arguments:
                return "[]"
            if len(node.arguments) == 1 and isinstance(node.arguments[0], ArrayLiteral):
                return self._expr(node.arguments[0], 0)
            return f"[{arguments}]"
        if redirect == "map":
            # The interpreter accepts an initial capacity it then ignores.
            return "new Map()"
        if redirect == "set":
            if not node.arguments:
                return "new Set()"
            return f"new Set({arguments})"
        if parsed is not None and parsed.arguments:
            type_arguments = ", ".join(
                self._map_type(argument) for argument in parsed.arguments
            )
            return f"new {base_name}<{type_arguments}>({arguments})"
        return f"new {self._resolve_type_name(base_name)}({arguments})"

    def _function_expression(self, node: FunctionExpression) -> tuple[str, int]:
        parameters = self._parameters(node.parameters)
        returns = (
            f": {self._ts_type(node.return_type)}" if node.return_type else ""
        )
        async_ = "async " if node.is_async else ""
        if not node.is_arrow:
            saved_indent = self._indent
            saved_lines = self._lines
            body_lines: list[str] = []
            self._lines = body_lines
            self._indent = saved_indent + 1
            try:
                self._statements(node.body)
            finally:
                self._lines = saved_lines
                self._indent = saved_indent
            body = "\n".join(body_lines)
            text = f"{async_}function ({parameters}){returns} {{\n{body}\n{'  ' * saved_indent}}}"
            return text, _ARROW
        # Arrow: collapse a single return into a concise body.
        if (
            len(node.body) == 1
            and isinstance(node.body[0], ReturnStatement)
            and node.body[0].value is not None
        ):
            expression = self._expr(node.body[0].value, _ARROW)
            # A concise body that starts with `{` would be parsed as a block
            # rather than an object literal, so parenthesize it.
            if expression.lstrip().startswith("{"):
                expression = f"({expression})"
            return f"{async_}({parameters}){returns} => {expression}", _ARROW
        saved_indent = self._indent
        saved_lines = self._lines
        body_lines = []
        self._lines = body_lines
        self._indent = saved_indent + 1
        try:
            self._statements(node.body)
        finally:
            self._lines = saved_lines
            self._indent = saved_indent
        body = "\n".join(body_lines)
        text = f"{async_}({parameters}){returns} => {{\n{body}\n{'  ' * saved_indent}}}"
        return text, _ARROW

    def _import_call(self, node: ImportCall) -> str:
        local_name = node.alias or node.import_path.split(".")[-1]
        callee_text = _BUILTIN_CALLEES.get(local_name, local_name)
        arguments = ", ".join(self._expr(argument, 0) for argument in node.arguments)
        return f"{callee_text}({arguments})"

    # ── type mapping ─────────────────────────────────────────────────────

    def _ts_type(self, type_name: str | None) -> str:
        if not type_name or not type_name.strip():
            return "any"
        try:
            return self._map_type(parse_type(type_name))
        except CodegenError:
            raise
        except Exception:
            return type_name.strip()

    def _map_type(self, xtype: XType) -> str:
        if xtype.is_any:
            return "any"
        if xtype.literal is not None:
            return json.dumps(xtype.literal, ensure_ascii=False)
        if xtype.union_parts:
            rendered = list(
                dict.fromkeys(self._map_type(part) for part in xtype.union_parts)
            )
            text = " | ".join(rendered)
            return self._apply_array(text, xtype)
        if xtype.record_fields:
            fields = "; ".join(
                f"{name}: {self._map_type(field_type)}"
                for name, field_type in xtype.record_fields
            )
            return self._apply_array(f"{{ {fields} }}", xtype)
        base = self._collection_type(xtype) or self._named_type(xtype)
        return self._apply_array(base, xtype)

    def _collection_type(self, xtype: XType) -> str | None:
        """Map an X standard-library collection type, else return ``None``.

        ``List<T>``/``Stack<T>``/... become ``T[]``, the map family becomes
        ``Map<K, V>``, and the set family becomes ``Set<T>``. Types without a
        TypeScript equivalent (``PriorityQueue``, ``Trie``) return ``None`` so
        they fall through as named types.
        """
        name = xtype.name
        if name in _ARRAY_COLLECTION_TYPES:
            if not xtype.arguments:
                return "any[]"
            return f"{self._map_type(xtype.arguments[0])}[]"
        if name in _MAP_COLLECTION_TYPES:
            if len(xtype.arguments) == 2:
                key = self._map_type(xtype.arguments[0])
                value = self._map_type(xtype.arguments[1])
                return f"Map<{key}, {value}>"
            return "Map<any, any>"
        if name in _SET_COLLECTION_TYPES:
            if not xtype.arguments:
                return "Set<any>"
            return f"Set<{self._map_type(xtype.arguments[0])}>"
        return None

    def _named_type(self, xtype: XType) -> str:
        name = xtype.name
        if name in _PRIMITIVE_TYPES:
            return _PRIMITIVE_TYPES[name]
        if name in _ARRAY_COLLECTION_TYPES:
            return "any[]"
        if name in _MAP_COLLECTION_TYPES:
            return "Map<any, any>"
        if name in _SET_COLLECTION_TYPES:
            return "Set<any>"
        return self._resolve_type_name(name)

    def _apply_array(self, base: str, xtype: XType) -> str:
        if not xtype.is_array or xtype.dimensions <= 0:
            return base
        # A union or function element needs parentheses before the brackets.
        if " | " in base or "=>" in base:
            base = f"({base})"
        return base + "[]" * xtype.dimensions

    def _resolve_type_name(self, name: str) -> str:
        """Qualify a bare reference to a nested type as ``Outer.Inner``."""
        if "." in name:
            return name
        for index in range(len(self._scope) - 1, -1, -1):
            container = self._scope[index]
            if name in self._nested_types.get(container, set()):
                return ".".join([*self._scope[: index + 1], name])
        return name
