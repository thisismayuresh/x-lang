"""Walk an X program and emit compile-time type diagnostics."""

from __future__ import annotations

import difflib
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any

from ..ast_nodes import (
    ArrayLiteral,
    Assignment,
    AwaitExpression,
    Binary,
    Block,
    Call,
    ClassDeclaration,
    ClassicForStatement,
    DoWhileStatement,
    EnumDeclaration,
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
    Member,
    MatchExpression,
    ModuleImport,
    NamespaceDeclaration,
    NewExpression,
    ObjectEntry,
    ObjectLiteral,
    OptionalChain,
    Program,
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
    VariableDeclaration,
    WhileStatement,
)
from ..diagnostics import callable_kind, member_noun
from .errors import TypeCheckError
from .types import (
    ANY,
    BOOLEAN,
    BUILTIN_TYPE_NAMES,
    FLOAT,
    FUNCTION,
    INTEGER,
    KNOWN_TYPE_NAMES,
    NULL,
    OBJECT,
    STRING,
    UNDEFINED,
    VOID,
    TypeScope,
    XType,
    _strip_array,
    _strip_nullable,
    canonical_primitive_alias,
    is_compatible,
    parse_type,
    split_top_level,
    split_union,
    substitute,
    _collection_alias,
)

#: Names the builtin scope predefines (see ``TypeChecker._builtin_scope``).
#: Never import-gated: a project module declaring ``print`` must not rename
#: the language's own ``print`` for every other file.
BUILTIN_SCOPE_NAMES = frozenset(
    {
        "print",
        "range",
        "typeOf",
        "parseFloat",
        "parseInt",
        # delete(...) comes from Object.delete (see DELETE_BUILTIN_NAME in
        # xlang/interpreter/_native_builtins.py) but is callable unqualified.
        "delete",
        "sleep",
        "args",
        "Object",
        "System",
        "HashMap",
        "LinkedList",
        "List",
        "Stack",
        "Queue",
        "PriorityQueue",
        "Trie",
        "Set",
        "TreeMap",
        "TreeSet",
        "LinkedHashMap",
        "LRUCache",
        "ConcurrentHashMap",
        "ConcurrentList",
    }
)

#: Dot-callable methods on arrays, mirroring the interpreter's table.
ARRAY_METHOD_NAMES = frozenset(
    {
        "map",
        "filter",
        "reduce",
        "forEach",
        "find",
        "some",
        "every",
        "indexOf",
        "contains",
        "sort",
        "reverse",
        "slice",
        "concat",
        "join",
        "first",
        "last",
        "isEmpty",
        "clear",
        "add",
        "push",
        "pop",
    }
)

#: Dot-callable methods on strings, mirroring the interpreter's table.
STRING_METHOD_NAMES = frozenset(
    {
        "toUpperCase",
        "toLowerCase",
        "trim",
        "startsWith",
        "endsWith",
        "contains",
        "indexOf",
        "replace",
        "replaceAll",
        "split",
        "charAt",
        "substring",
        "slice",
        "repeat",
        "padStart",
        "padEnd",
        "isEmpty",
        "toCharArray",
        "toString",
    }
)

_VISIBILITY_ORDER = ("private", "protected", "public")

#: Python-backed collection families and the argument roles their instance
#: methods check.  These collections have no X declarations, so their
#: methods never reach ``_check_overloads``; the table below type-checks the
#: positions that mutate or query typed slots.  Roles resolve against the
#: receiver's type arguments: ``element``/``key`` = argument 0, ``value`` =
#: argument 1, ``index`` = ``integer``.
COLLECTION_ELEMENT_FAMILIES = frozenset(
    {
        "LinkedList",
        "Stack",
        "Queue",
        "PriorityQueue",
        "HashSet",
        "Set",
        "TreeSet",
        "LinkedHashSet",
        "ThreadSafeSet",
        "ConcurrentList",
    }
)
COLLECTION_MAP_FAMILIES = frozenset(
    {
        "HashMap",
        "Map",
        "TreeMap",
        "LinkedHashMap",
        "LruCache",
        "ConcurrentHashMap",
    }
)
COLLECTION_METHOD_ROLES: dict[str, tuple[str, ...]] = {
    "add": ("element",),
    "addFirst": ("element",),
    "addLast": ("element",),
    "push": ("element",),
    "enqueue": ("element",),
    "remove": ("element",),
    "contains": ("element",),
    "indexOf": ("element",),
    "has": ("element",),
    "get": ("index",),
}
COLLECTION_METHOD_ROLES_MAP: dict[str, tuple[str, ...]] = {
    "set": ("key", "value"),
    "get": ("key",),
    "has": ("key",),
    "remove": ("key",),
    "getOrDefault": ("key", "value"),
    "computeIfAbsent": ("key",),
    "computeIfPresent": ("key",),
}


def _return_type_help(kind: str) -> str:
    """Concrete ``= help:`` text for a missing return-type annotation."""
    if kind == "Method":
        return "add an explicit return type, e.g. `string getName()`"
    return "add an explicit return type, e.g. `int function add(int a, int b)`"


def _parameter_type_help(kind: str, name: str, return_type: str | None) -> str:
    """Concrete ``= help:`` text for an untyped parameter."""
    if kind == "Constructor":
        return f"type the parameter, e.g. `public {name}(int x)`"
    if kind == "Function":
        declared = return_type or "int"
        return f"type the parameter, e.g. `{declared} function {name}(int xp)`"
    return f"type the parameter, e.g. `{return_type or 'void'} {name}(int xp)`"


def _closest_match(candidate: str, options: Iterable[str]) -> str | None:
    """Return the closest spelling to *candidate* among *options*, if any."""
    ranked = difflib.get_close_matches(candidate, sorted(set(options)), n=1, cutoff=0.7)
    if not ranked:
        return None
    match = ranked[0]
    if match == candidate:
        return None
    return match


class TypeChecker:
    """Static checker for types, interfaces, generics, and definite assignment.

    The public API is:

    ``check(program, source_name=None, config=None) -> list[TypeCheckError]``
        Type-check ``program`` and return every diagnostic.  This method never
        raises; parseable programs with type errors simply yield a non-empty
        list.  Diagnostics carry ``message``, ``line``, ``column`` and
        ``source_name`` so they can be rendered by ``render_diagnostic``.

    ``check_or_raise(program, source_name=None, config=None) -> None``
        Convenience wrapper that raises the first diagnostic when any exist.

    ``check_declarations(program, source_name=None, config=None) -> list[TypeCheckError]``
        Lightweight declaration-level validation: unknown type names and
        concrete classes that do not implement every interface member.
        Used by the interpreter as a pre-execution gate; it skips body
        checking entirely.
    """

    def __init__(self) -> None:
        self._reset(None)
        self._config = None

    def _reset(self, source_name: str | None, config=None) -> None:
        self.errors: list[TypeCheckError] = []
        self._seen: set[tuple[Any, ...]] = set()
        self._config = config
        self._classes: dict[str, ClassDeclaration] = {}
        self._interfaces: dict[str, ClassDeclaration] = {}
        self._enums: dict[str, EnumDeclaration] = {}
        self._aliases: dict[str, XType] = {}
        self._functions: dict[str, list[FunctionDeclaration]] = {}
        self._generic_params: dict[str, list[str]] = {}
        self._namespace_roots: set[str] = set()
        self._import_names: set[str] = set()
        self._known_names: set[str] | None = None
        self._source_name = source_name
        self._location: tuple[int | None, int | None, str | None] | None = None
        self._active_generics: set[str] = set()
        self._class_stack: list[str] = []
        self._expected_return: XType | None = None
        self._saw_value_return = False
        self._returns_void = False
        self._callable_kind: str | None = None
        self._callable_name: str | None = None
        self._in_constructor = False
        self._in_async_body = False
        self._try_depth = 0
        self._current_node: Any | None = None
        # Import-scoping state, filled from Program by _apply_program_info.
        self._module_visibility: dict[str, frozenset[str]] | None = None
        self._name_provenance: dict[str, str] | None = None
        self._root_scope: TypeScope | None = None
        # Node whose "is a type, not a value" check is waived: the object of
        # `x.y` (`Gender.MALE`) or the callee of `x()` (`IFoo()`).
        self._deferred_type_value: Any | None = None

    def _apply_program_info(self, program: Program) -> None:
        """Pick up the loader's per-file import visibility, if present."""
        self._module_visibility = getattr(program, "module_visibility", None)
        self._name_provenance = getattr(program, "name_provenance", None)

    def _record_depth_error(self) -> None:
        """Turn a stack overflow into a diagnostic on the deepest known node."""
        node = self._current_node
        self.errors.append(
            TypeCheckError(
                "Program nests too deeply to type check",
                node,
                source_name=getattr(node, "source_name", None) or self._source_name,
                notes=("split the expression into several statements",),
            )
        )

    def check(
        self, program: Program, source_name: str | None = None, config=None
    ) -> list[TypeCheckError]:
        """Type-check ``program`` and return all diagnostics (does not raise)."""
        self._reset(source_name, config)
        try:
            self._check_program(program)
        except RecursionError:
            self._record_depth_error()
        return self.errors

    def _check_program(self, program: Program) -> None:
        self._apply_program_info(program)
        # The checker walks the flat declaration list exactly once: names
        # resolve against one shared scope, and `module_visibility` gates
        # which file may reference each name.  `program.modules` is the
        # runtime's per-file grouping — re-checking it here would only
        # duplicate every diagnostic.
        self._collect_types(program.declarations)
        self._check_type_name_references(program.declarations)
        self._validate_interface_implementations()
        self._check_strict_typing(program.declarations, self._source_name)
        scope = self._builtin_scope()
        self._root_scope = scope
        self._check_declarations(program.declarations, scope)

    def check_or_raise(
        self, program: Program, source_name: str | None = None, config=None
    ) -> None:
        """Type-check and raise the first error when diagnostics exist."""
        errors = self.check(program, source_name, config)
        if errors:
            raise errors[0]

    def check_declarations(
        self, program: Program, source_name: str | None = None, config=None
    ) -> list[TypeCheckError]:
        """Validate declaration-level type names and interface conformance only.

        Reports unknown type names in annotations/``new`` targets and concrete
        classes that omit interface members, without checking method bodies.
        """
        self._reset(source_name, config)
        try:
            self._check_program_declarations(program)
        except RecursionError:
            self._record_depth_error()
        return self.errors

    def _check_program_declarations(self, program: Program) -> None:
        self._apply_program_info(program)
        # See `_check_program`: one pass over the flat list; `program.modules`
        # is the runtime's grouping and must not re-emit diagnostics.
        self._collect_types(program.declarations)
        self._check_type_name_references(program.declarations)
        self._validate_interface_implementations()
        self._check_strict_typing(program.declarations, self._source_name)

    # ------------------------------------------------------------------
    # Scopes and collection
    # ------------------------------------------------------------------

    def _builtin_scope(self) -> TypeScope:
        scope = TypeScope()
        for name in BUILTIN_SCOPE_NAMES:
            scope.define(name, ANY, True)
        return scope

    def _collect_types(self, declarations: list[Any]) -> None:
        for declaration in declarations:
            if isinstance(declaration, ClassDeclaration):
                if declaration.is_interface:
                    self._interfaces[declaration.name] = declaration
                else:
                    self._classes[declaration.name] = declaration
                if declaration.generic_parameters:
                    self._generic_params[declaration.name] = list(
                        declaration.generic_parameters
                    )
                nested = [
                    member
                    for member in declaration.members
                    if isinstance(member, ClassDeclaration)
                ]
                if nested:
                    self._collect_types(nested)
            elif isinstance(declaration, EnumDeclaration):
                self._enums[declaration.name] = declaration
            elif isinstance(declaration, TypeDeclaration):
                self._aliases[declaration.name] = parse_type(declaration.type_name)
            elif isinstance(declaration, NamespaceDeclaration):
                self._namespace_roots.add(declaration.name.split(".")[0])
                self._collect_types(declaration.declarations)
            elif isinstance(declaration, FunctionDeclaration):
                self._register_function(declaration)
                if declaration.generic_parameters:
                    registered = self._generic_params.setdefault(declaration.name, [])
                    for parameter in declaration.generic_parameters:
                        if parameter not in registered:
                            registered.append(parameter)
            elif isinstance(declaration, ImportDeclaration):
                for path, alias in declaration.targets:
                    if alias is not None:
                        self._import_names.add(alias)
                    parts = path.split(".")
                    self._import_names.add(parts[0])
                    self._import_names.add(parts[-1])
            elif isinstance(declaration, ImportAlias):
                self._import_names.add(declaration.alias_name)
                parts = declaration.source_name.split(".")
                self._import_names.add(parts[0])
                self._import_names.add(parts[-1])
            elif isinstance(declaration, ImportNamespaceAlias):
                self._import_names.add(declaration.alias_name)
            elif isinstance(declaration, ModuleImport):
                if declaration.alias is not None:
                    self._import_names.add(declaration.alias)
                if declaration.source_name:
                    parts = declaration.source_name.split(".")
                    self._import_names.add(parts[0])
                    self._import_names.add(parts[-1])
                self._import_names.update(declaration.exported_names)
            self._collect_nested_types(declaration)

    def _collect_nested_types(self, node: Any) -> None:
        """Collect type declarations from nested scopes (function bodies,
        blocks, match arms, ...).

        Only type-level information is recorded (classes, interfaces, enums,
        type aliases, namespace roots, generic parameters); functions are
        registered solely at declaration-list scope by ``_collect_types``.
        """
        if node is None or isinstance(node, (str, bytes, int, float, bool)):
            return
        if isinstance(node, dict):
            for value in node.values():
                self._collect_nested_types(value)
            return
        if isinstance(node, (list, tuple, set)):
            for item in node:
                self._collect_nested_types(item)
            return
        if not is_dataclass(node):
            return
        if getattr(node, "line", None):
            self._current_node = node
        if isinstance(node, ClassDeclaration):
            if node.is_interface:
                self._interfaces[node.name] = node
            else:
                self._classes[node.name] = node
            if node.generic_parameters:
                self._generic_params[node.name] = list(node.generic_parameters)
        elif isinstance(node, EnumDeclaration):
            self._enums[node.name] = node
        elif isinstance(node, TypeDeclaration):
            self._aliases[node.name] = parse_type(node.type_name)
        elif isinstance(node, FunctionDeclaration):
            if node.generic_parameters:
                registered = self._generic_params.setdefault(node.name, [])
                for parameter in node.generic_parameters:
                    if parameter not in registered:
                        registered.append(parameter)
        elif isinstance(node, NamespaceDeclaration):
            self._namespace_roots.add(node.name.split(".")[0])
        for field in fields(node):
            self._collect_nested_types(getattr(node, field.name))

    def _register_function(self, declaration: FunctionDeclaration) -> None:
        registered = self._functions.setdefault(declaration.name, [])
        if not any(existing is declaration for existing in registered):
            registered.append(declaration)

    def _collect_local_functions(self, statements: list[Any]) -> None:
        """Register nested functions so calls resolve regardless of position."""
        for statement in statements:
            if isinstance(statement, FunctionDeclaration):
                self._register_function(statement)
                self._collect_local_functions(statement.body)
            elif isinstance(statement, Block):
                self._collect_local_functions(statement.statements)
            elif isinstance(statement, IfStatement):
                self._collect_local_functions(statement.then_branch.statements)
                if statement.else_branch is not None:
                    if isinstance(statement.else_branch, Block):
                        self._collect_local_functions(statement.else_branch.statements)
                    else:
                        self._collect_local_functions([statement.else_branch])
            elif isinstance(
                statement,
                (WhileStatement, DoWhileStatement, ForStatement, ClassicForStatement),
            ):
                self._collect_local_functions(statement.body.statements)
            elif isinstance(statement, TryStatement):
                self._collect_local_functions(statement.body.statements)
                for _, _, catch_body in statement.catches:
                    self._collect_local_functions(catch_body.statements)
                if statement.finally_body is not None:
                    self._collect_local_functions(statement.finally_body.statements)
            elif isinstance(statement, ExpressionStatement):
                match_expression = statement.expression
                if isinstance(match_expression, MatchExpression):
                    for arm in match_expression.arms:
                        if isinstance(arm.body, Block):
                            self._collect_local_functions(arm.body.statements)

    def _contains_throw(self, statements: list[Any]) -> bool:
        for statement in statements:
            if isinstance(statement, ThrowStatement):
                return True
            if isinstance(statement, FunctionDeclaration):
                continue
            if isinstance(statement, Block):
                if self._contains_throw(statement.statements):
                    return True
            elif isinstance(statement, IfStatement):
                if self._contains_throw(statement.then_branch.statements):
                    return True
                if isinstance(statement.else_branch, Block):
                    if self._contains_throw(statement.else_branch.statements):
                        return True
                elif statement.else_branch is not None:
                    if self._contains_throw([statement.else_branch]):
                        return True
            elif isinstance(
                statement,
                (WhileStatement, DoWhileStatement, ForStatement, ClassicForStatement),
            ):
                if self._contains_throw(statement.body.statements):
                    return True
            elif isinstance(statement, TryStatement):
                if self._contains_throw(statement.body.statements):
                    return True
                for _, _, catch_body in statement.catches:
                    if self._contains_throw(catch_body.statements):
                        return True
                if statement.finally_body is not None:
                    if self._contains_throw(statement.finally_body.statements):
                        return True
            elif isinstance(statement, ExpressionStatement):
                if isinstance(statement.expression, MatchExpression):
                    for arm in statement.expression.arms:
                        if isinstance(arm.body, Block):
                            if self._contains_throw(arm.body.statements):
                                return True
        return False

    # ------------------------------------------------------------------
    # Declaration checking
    # ------------------------------------------------------------------

    def _check_declarations(self, declarations: list[Any], scope: TypeScope) -> None:
        for declaration in declarations:
            if isinstance(declaration, FunctionDeclaration):
                scope.define(declaration.name, FUNCTION, True)
            elif isinstance(declaration, ClassDeclaration):
                class_type = parse_type(declaration.name)
                scope.define(declaration.name, class_type, True)
            elif isinstance(declaration, EnumDeclaration):
                scope.define(declaration.name, parse_type(declaration.name), True)
            elif isinstance(declaration, TypeDeclaration):
                scope.define(
                    declaration.name,
                    self._aliases.get(
                        declaration.name, parse_type(declaration.type_name)
                    ),
                    True,
                )
        for declaration in declarations:
            self._check_declaration(declaration, scope)

    def _check_declaration(self, declaration: Any, scope: TypeScope) -> None:
        previous_location = None
        if getattr(declaration, "line", None) is not None:
            previous_location = self._location
            self._location = (
                declaration.line,
                getattr(declaration, "column", None),
                getattr(declaration, "source_name", None),
            )
        try:
            self._dispatch_declaration(declaration, scope)
        finally:
            if previous_location is not None:
                self._location = previous_location

    def _dispatch_declaration(self, declaration: Any, scope: TypeScope) -> None:
        if isinstance(declaration, FunctionDeclaration):
            scope.define(declaration.name, FUNCTION, True)
            self._register_function(declaration)
            self._check_function(declaration, scope)
        elif isinstance(declaration, ClassDeclaration):
            self._check_class(declaration, scope)
        elif isinstance(declaration, NamespaceDeclaration):
            self._check_declarations(declaration.declarations, scope.child())
        elif isinstance(declaration, VariableDeclaration):
            self._check_variable(declaration, scope)
        elif isinstance(declaration, Block):
            self._check_statements(declaration.statements, scope.child())
        elif isinstance(declaration, IfStatement):
            self._infer(declaration.condition, scope)
            self._check_statements(declaration.then_branch.statements, scope.child())
            if declaration.else_branch is not None:
                body = (
                    declaration.else_branch.statements
                    if isinstance(declaration.else_branch, Block)
                    else [declaration.else_branch]
                )
                self._check_statements(body, scope.child())
        elif isinstance(declaration, (WhileStatement, DoWhileStatement)):
            self._infer(declaration.condition, scope)
            self._check_statements(declaration.body.statements, scope.child())
        elif isinstance(declaration, ForStatement):
            iterable_type = self._infer(declaration.iterable, scope)
            element_type = self._iterable_element_type(iterable_type)
            loop_scope = scope.child()
            if declaration.variable:
                if declaration.type_name:
                    declared = self._resolve_annotation(declaration.type_name)
                    if (
                        not element_type.is_any
                        and not is_compatible(element_type, declared, relations=self)
                    ):
                        self._error(
                            f"Cannot assign '{element_type.display()}' to "
                            f"'{declaration.variable}' of type "
                            f"'{declared.display()}'",
                            declaration,
                            notes=[
                                f"expected `{declared.display()}`, "
                                f"found `{element_type.display()}`"
                            ],
                        )
                    loop_scope.define(declaration.variable, declared, True)
                else:
                    # `for (v of ...)` with no annotation: the element type
                    # flows into the loop variable.
                    loop_scope.define(declaration.variable, element_type, True)
            self._check_statements(declaration.body.statements, loop_scope)
        elif isinstance(declaration, ClassicForStatement):
            loop_scope = scope.child()
            if declaration.initializer is not None:
                self._check_declaration(declaration.initializer, loop_scope)
            if declaration.condition is not None:
                self._infer(declaration.condition, loop_scope)
            if declaration.increment is not None:
                self._infer(declaration.increment, loop_scope)
            self._check_statements(declaration.body.statements, loop_scope)
        elif isinstance(declaration, ReturnStatement):
            self._check_return(declaration, scope)
        elif isinstance(declaration, ThrowStatement):
            self._infer(declaration.value, scope)
        elif isinstance(declaration, TryStatement):
            self._check_try(declaration, scope)
        elif isinstance(declaration, SwitchStatement):
            self._check_switch(declaration, scope)
        elif isinstance(declaration, ExpressionStatement):
            self._infer(declaration.expression, scope)
        elif isinstance(declaration, Assignment):
            self._infer(declaration, scope)
        elif isinstance(declaration, ImportDeclaration):
            if declaration.statement is not None:
                self._check_declaration(declaration.statement, scope)
            return
        elif isinstance(
            declaration,
            (
                ModuleImport,
                ImportAlias,
                ImportNamespaceAlias,
                EnumDeclaration,
                TypeDeclaration,
            ),
        ):
            return

    def _check_statements(self, statements: list[Any], scope: TypeScope) -> None:
        for statement in statements:
            self._check_declaration(statement, scope)

    def _check_return(self, declaration: ReturnStatement, scope: TypeScope) -> None:
        if declaration.value is not None:
            if self._in_constructor:
                self._error(
                    "Constructors cannot return a value",
                    declaration,
                )
                return
            actual = self._infer(declaration.value, scope)
            self._saw_value_return = True
            if self._returns_void:
                self._error(self._void_return_message(), declaration)
                return
            expected = self._expected_return
            comparable = actual
            if (
                self._in_async_body
                and actual.name == "Promise"
                and len(actual.arguments) == 1
            ):
                # An async body may `return somePromise` (implicitly awaited)
                # exactly as TypeScript allows; only the unwrapped type is
                # compared against the body's expected return type.
                comparable = actual.arguments[0]
            if expected is not None and not self._value_matches(
                declaration.value, comparable, expected
            ):
                self._error(
                    f"Return type '{actual.display()}' is not compatible with "
                    f"'{expected.display()}'",
                    declaration,
                    notes=self._incompatibility_notes(actual, expected),
                )
        elif self._expected_return is not None:
            self._saw_value_return = True
            self._error(
                f"Missing return value of type '{self._expected_return.display()}'",
                declaration,
            )

    def _check_try(self, declaration: TryStatement, scope: TypeScope) -> None:
        self._try_depth += 1
        try:
            body_scope = scope.child()
            for binding in declaration.resources:
                annotated = self._resolve_annotation(binding.type_name)
                if binding.value is not None:
                    actual = self._infer(binding.value, body_scope)
                    if not self._value_matches(binding.value, actual, annotated):
                        self._error(
                            f"Cannot assign '{actual.display()}' to "
                            f"'{binding.name}' of type '{annotated.display()}'",
                            declaration,
                            notes=[
                                f"expected `{annotated.display()}`, "
                                f"found `{actual.display()}`"
                            ],
                        )
                    if (
                        annotated.is_any
                        and not actual.is_any
                        and actual.name not in {"null", "undefined", "void"}
                    ):
                        annotated = actual
                body_scope.define(
                    binding.name,
                    annotated,
                    binding.value is not None,
                    constant=binding.constant,
                )
            self._check_statements(declaration.body.statements, body_scope)
        finally:
            self._try_depth -= 1
        for catch_name, catch_type, catch_body in declaration.catches:
            catch_scope = scope.child()
            if catch_name:
                catch_scope.define(
                    catch_name, self._resolve_annotation(catch_type), True
                )
            self._check_statements(catch_body.statements, catch_scope)
        if declaration.finally_body is not None:
            self._check_statements(declaration.finally_body.statements, scope.child())

    def _check_switch(self, declaration: SwitchStatement, scope: TypeScope) -> None:
        self._infer(declaration.expression, scope)
        for case in declaration.cases:
            if case.value is not None:
                self._infer(case.value, scope)
            self._check_statements(case.body.statements, scope.child())

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _check_function(
        self,
        declaration: FunctionDeclaration,
        scope: TypeScope,
        this_type: XType | None = None,
    ) -> None:
        previous_generics = self._active_generics
        self._active_generics = previous_generics | set(
            declaration.generic_parameters or []
        )
        body_scope = scope.child()
        if this_type is not None:
            body_scope.define("this", this_type, True)
        for parameter in declaration.parameters:
            body_scope.define(
                parameter.name,
                self._resolve_annotation(parameter.type_name),
                True,
            )
        expected = self._resolve_return_type(declaration.return_type)
        declared_void = self._is_void_annotation(declaration.return_type)
        body_expected = expected
        if (
            declaration.is_async
            and expected is not None
            and expected.name == "Promise"
            and len(expected.arguments) == 1
        ):
            # TS-style `Promise<T> async function`: the body returns the
            # unwrapped T; call sites still see the declared Promise<T>.
            inner = expected.arguments[0]
            if inner.name == "void":
                body_expected = None
                declared_void = True
            elif inner.is_any:
                body_expected = None
            else:
                body_expected = inner
        previous_expected = self._expected_return
        previous_saw = self._saw_value_return
        previous_in_constructor = self._in_constructor
        previous_void = self._returns_void
        previous_async = self._in_async_body
        previous_kind = self._callable_kind
        previous_name = self._callable_name
        is_constructor = (
            self._class_stack
            and declaration.name == self._class_stack[-1]
            and declaration.return_type is None
        )
        self._expected_return = body_expected
        self._saw_value_return = False
        self._in_constructor = is_constructor
        self._in_async_body = bool(declaration.is_async)
        self._returns_void = declared_void
        self._callable_kind = callable_kind(
            declaration.name,
            self._class_stack[-1] if self._class_stack else None,
        )
        self._callable_name = declaration.name
        if declaration.body:
            self._collect_local_functions(declaration.body)
            self._check_statements(declaration.body, body_scope)
            if (
                body_expected is not None
                and not self._saw_value_return
                and not self._contains_throw(declaration.body)
            ):
                self._error(
                    f"{self._callable_kind} '{declaration.name}' must return a value of type "
                    f"'{body_expected.display()}'",
                    declaration,
                )
        self._expected_return = previous_expected
        self._saw_value_return = previous_saw
        self._in_constructor = previous_in_constructor
        self._in_async_body = previous_async
        self._returns_void = previous_void
        self._callable_kind = previous_kind
        self._callable_name = previous_name
        self._active_generics = previous_generics

    def _resolve_return_type(self, type_name: str | None) -> XType | None:
        if type_name is None:
            return None
        resolved = self._resolve_annotation(type_name)
        if resolved.is_any or resolved.name == "void":
            return None
        return resolved

    def _is_void_annotation(self, type_name: str | None) -> bool:
        """True when a declared return type is exactly ``void`` (unlike ``any``)."""
        if type_name is None:
            return False
        resolved = self._resolve_annotation(type_name)
        return resolved.name == "void" and not resolved.is_any

    def _void_return_message(self) -> str:
        kind = self._callable_kind or "Function"
        if self._callable_name:
            return (
                f"{kind} '{self._callable_name}' is declared 'void' "
                "and cannot return a value"
            )
        return f"A 'void' {kind.lower()} cannot return a value"

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def _check_class(self, declaration: ClassDeclaration, scope: TypeScope) -> None:
        if declaration.is_interface:
            return
        class_type = parse_type(declaration.name)
        class_scope = scope.child()
        class_scope.define(declaration.name, class_type, True)
        self._validate_class(declaration)
        self._class_stack.append(declaration.name)
        previous_generics = self._active_generics
        self._active_generics = previous_generics | set(
            declaration.generic_parameters or []
        )
        for member in declaration.members:
            if isinstance(member, FunctionDeclaration):
                if "static" in member.modifiers:
                    self._check_function(member, class_scope)
                else:
                    self._check_function(member, class_scope, this_type=class_type)
            elif isinstance(member, VariableDeclaration):
                self._check_variable(member, class_scope, force_assigned=True)
            elif isinstance(member, ClassDeclaration):
                self._check_class(member, class_scope)
        self._active_generics = previous_generics
        self._class_stack.pop()

    def _validate_class(self, declaration: ClassDeclaration) -> None:
        for interface_name in declaration.implemented_types:
            base_name = interface_name.split("<")[0].strip()
            # Namespace chains (MyNamespace.Shape, util.Mod.Shape) index the
            # interface under its bare name — the same flat table flat member
            # imports populate — so resolve the last path component.
            lookup_name = base_name.split(".")[-1]
            if lookup_name not in self._interfaces:
                self._error(
                    f"Class '{declaration.name}' implements unknown interface "
                    f"'{interface_name}'",
                    declaration,
                )
            elif self._map_interface_view(self._interfaces[lookup_name]) is not None:
                self._error(
                    f"Class '{declaration.name}' cannot implement map interface "
                    f"'{interface_name}'; use it as a variable or parameter type",
                    declaration,
                )
        if declaration.parent_name:
            parent_name = declaration.parent_name.split("<")[0].strip()
            parent = self._classes.get(parent_name)
            if parent is not None and "final" in parent.modifiers:
                self._error(f"Cannot extend final class '{parent_name}'", declaration)
        if "abstract" in declaration.modifiers:
            return
        for member in declaration.members:
            if (
                isinstance(member, FunctionDeclaration)
                and "abstract" in member.modifiers
            ):
                self._error(
                    f"Class '{declaration.name}' must be abstract to declare "
                    f"abstract method '{member.name}'",
                    member,
                )
        for name, signature in self._inherited_abstract_methods(declaration).items():
            if not self._class_has_compatible_method(declaration, signature):
                self._error(
                    f"Class '{declaration.name}' does not implement abstract method "
                    f"'{name}'",
                    declaration,
                    helps=[
                        f"implement `{self._format_signature(signature, 'Method')}` "
                        f"on class `{declaration.name}`"
                    ],
                )

    def _inherited_abstract_methods(
        self, declaration: ClassDeclaration
    ) -> dict[str, FunctionDeclaration]:
        methods: dict[str, FunctionDeclaration] = {}
        parent_name = declaration.parent_name
        while parent_name:
            parent = self._classes.get(parent_name.split("<")[0])
            if parent is None:
                break
            for member in parent.members:
                if (
                    isinstance(member, FunctionDeclaration)
                    and "abstract" in member.modifiers
                ):
                    methods[member.name] = member
                elif isinstance(member, FunctionDeclaration) and member.name in methods:
                    del methods[member.name]
            parent_name = parent.parent_name
        return methods

    def _class_has_compatible_method(
        self,
        declaration: ClassDeclaration,
        signature: FunctionDeclaration,
    ) -> bool:
        current: ClassDeclaration | None = declaration
        while current is not None:
            for member in current.members:
                if (
                    isinstance(member, FunctionDeclaration)
                    and member.name == signature.name
                    and "abstract" not in member.modifiers
                ):
                    # Check return type compatibility
                    expected_return = self._resolve_return_type(signature.return_type)
                    actual_return = self._resolve_return_type(member.return_type)
                    if expected_return is not None and actual_return is not None:
                        if not is_compatible(
                            actual_return, expected_return, relations=self
                        ):
                            return False
                    return True
            if current.parent_name is None:
                break
            current = self._classes.get(current.parent_name.split("<")[0])
        return False

    def _class_has_property(self, declaration: ClassDeclaration, name: str) -> bool:
        current: ClassDeclaration | None = declaration
        while current is not None:
            for member in current.members:
                if isinstance(member, VariableDeclaration) and member.name == name:
                    return True
            if current.parent_name is None:
                break
            current = self._classes.get(current.parent_name.split("<")[0])
        return False

    def _validate_interface_implementations(self) -> None:
        """Require concrete classes to provide every member of each interface.

        Abstract classes are exempt (they may leave interface methods
        unimplemented for their concrete subclasses).  Interface members
        inherited through ``extends`` are included via ``_interface_members``.
        """
        for declaration in self._classes.values():
            if not declaration.implemented_types:
                continue
            if "abstract" in declaration.modifiers:
                continue
            for interface_ref in declaration.implemented_types:
                interface_name = interface_ref.split("<")[0].strip()
                interface = self._interfaces.get(interface_name)
                if interface is None:
                    continue
                for member in self._interface_members(interface):
                    if isinstance(member, FunctionDeclaration):
                        if "static" in member.modifiers:
                            continue
                        if not self._class_has_compatible_method(declaration, member):
                            self._error(
                                f"Class '{declaration.name}' does not implement "
                                f"'{member.name}()' from interface '{interface_name}'",
                                declaration,
                                helps=[
                                    f"implement `{self._format_signature(member, 'Method')}` "
                                    f"on class `{declaration.name}`"
                                ],
                            )
                    elif isinstance(member, VariableDeclaration):
                        if not self._class_has_property(declaration, member.name):
                            self._error(
                                f"Class '{declaration.name}' does not implement "
                                f"property '{member.name}' from interface "
                                f"'{interface_name}'",
                                declaration,
                                helps=[
                                    f"add a `{member.type_name or 'any'} {member.name}` "
                                    f"property to class `{declaration.name}`"
                                ],
                            )

    def _check_strict_typing(
        self, declarations: list[Any], source_name: str | None = None
    ) -> None:
        """Check that all types are explicitly specified when strict_typing is enabled.

        Traverses top-level declarations, class members, function bodies and all
        nested statement blocks so that return types, parameters and local
        variables cannot be omitted.
        """
        if not self._config or not self._config.enabled("strict_typing"):
            return

        for declaration in declarations:
            self._check_strict_typing_declaration(declaration, source_name=source_name)

    def _check_strict_typing_statements(
        self, statements: list[Any], source_name: str | None = None
    ) -> None:
        """Recurse through a block, checking local variable declarations."""
        for statement in statements:
            self._check_strict_typing_statement(statement, source_name)

    def _check_strict_typing_statement(
        self, statement: Any, source_name: str | None = None
    ) -> None:
        if statement is None:
            return

        previous_location = None
        if getattr(statement, "line", None) is not None:
            previous_location = self._location
            self._location = (
                statement.line,
                getattr(statement, "column", None),
                getattr(statement, "source_name", None) or source_name,
            )

        try:
            if isinstance(statement, Block):
                self._check_strict_typing_statements(statement.statements, source_name)
            elif isinstance(statement, IfStatement):
                self._check_strict_typing_statements(
                    statement.then_branch.statements, source_name
                )
                else_branch = statement.else_branch
                if isinstance(else_branch, Block):
                    self._check_strict_typing_statements(
                        else_branch.statements, source_name
                    )
                elif else_branch is not None:
                    self._check_strict_typing_statement(else_branch, source_name)
            elif isinstance(statement, (WhileStatement, DoWhileStatement)):
                self._check_strict_typing_statements(
                    statement.body.statements, source_name
                )
            elif isinstance(statement, ForStatement):
                self._check_strict_typing_statements(
                    statement.body.statements, source_name
                )
            elif isinstance(statement, ClassicForStatement):
                self._check_strict_typing_statements(
                    statement.body.statements, source_name
                )
            elif isinstance(statement, TryStatement):
                for resource in statement.resources:
                    if resource.type_name is None:
                        self._error(
                            f"Resource variable '{resource.name}' must have an "
                            "explicit type (strict_typing enabled)",
                            statement,
                        )
                self._check_strict_typing_statements(
                    statement.body.statements, source_name
                )
                for _, _, catch_body in statement.catches:
                    self._check_strict_typing_statements(
                        catch_body.statements, source_name
                    )
                if statement.finally_body is not None:
                    self._check_strict_typing_statements(
                        statement.finally_body.statements, source_name
                    )
            elif isinstance(statement, SwitchStatement):
                for case in statement.cases:
                    self._check_strict_typing_statements(
                        case.body.statements, source_name
                    )
            elif isinstance(
                statement,
                (
                    ExpressionStatement,
                    Assignment,
                    FunctionDeclaration,
                    VariableDeclaration,
                ),
            ):
                self._check_strict_typing_declaration(
                    statement, class_name=None, source_name=source_name, local=True
                )
            elif isinstance(statement, FunctionExpression):
                for param in statement.parameters:
                    if param.type_name is None:
                        self._error(
                            f"Parameter '{param.name}' in arrow function must have "
                            "an explicit type (strict_typing enabled)",
                            statement,
                            helps=[_parameter_type_help("Function", "", None)],
                        )
        finally:
            if previous_location is not None:
                self._location = previous_location

    def _check_strict_typing_declaration(
        self,
        declaration: Any,
        class_name: str | None = None,
        is_interface: bool = False,
        source_name: str | None = None,
        local: bool = False,
    ) -> None:
        """Check a single declaration for missing type annotations.

        ``class_name`` is the enclosing class (or interface) when the
        declaration is a member of one, so the diagnostic can say
        ``Method``/``Constructor``/``property`` instead of ``Function``/
        ``Variable``.  ``local`` marks a variable declared inside a function
        body.
        """
        if declaration is None:
            return

        if isinstance(declaration, FunctionDeclaration):
            kind = callable_kind(declaration.name, class_name, is_interface)
            # Check return type.  Constructors return nothing, so the
            # strict-typing return-type rule does not apply to them.
            if declaration.return_type is None and kind != "Constructor":
                self._error(
                    f"{kind} '{declaration.name}' must have an explicit return type (strict_typing enabled)",
                    declaration,
                    helps=[_return_type_help(kind)],
                )
            # Check parameter types
            for param in declaration.parameters:
                if param.type_name is None:
                    self._error(
                        f"Parameter '{param.name}' in {kind.lower()} '{declaration.name}' must have an explicit type (strict_typing enabled)",
                        declaration,
                        helps=[
                            _parameter_type_help(
                                kind, declaration.name, declaration.return_type
                            )
                        ],
                    )
            if declaration.body:
                self._check_strict_typing_statements(
                    declaration.body, source_name=source_name
                )
        elif isinstance(declaration, VariableDeclaration):
            if declaration.type_name is None:
                if local:
                    label = "Local variable"
                elif class_name is None:
                    label = "Variable"
                else:
                    label = member_noun(declaration.modifiers).capitalize()
                self._error(
                    f"{label} '{declaration.name}' must have an explicit type (strict_typing enabled)",
                    declaration,
                )
        elif isinstance(declaration, ClassDeclaration):
            for member in declaration.members:
                self._check_strict_typing_declaration(
                    member,
                    class_name=declaration.name,
                    is_interface=declaration.is_interface,
                )

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _check_variable(
        self,
        declaration: VariableDeclaration,
        scope: TypeScope,
        force_assigned: bool = False,
    ) -> None:
        annotated = self._resolve_annotation(declaration.type_name)
        assigned = declaration.initializer is not None or force_assigned
        if declaration.initializer is not None:
            actual = self._infer(declaration.initializer, scope)
            if not self._value_matches(declaration.initializer, actual, annotated):
                reported = self._report_typed_object_literal(
                    declaration.initializer,
                    actual,
                    annotated,
                    label=f"'{declaration.name}'",
                    subject=f"'{declaration.name}'",
                    spelling=declaration.type_name,
                )
                if not reported:
                    gap = self._incompatibility_notes(actual, annotated)
                    self._error(
                        f"Cannot assign '{actual.display()}' to "
                        f"'{declaration.name}' of type '{annotated.display()}'",
                        declaration,
                        notes=gap
                        or [
                            f"expected `{annotated.display()}`, "
                            f"found `{actual.display()}`"
                        ],
                    )
            if (
                annotated.is_any
                and not actual.is_any
                and actual.name not in {"null", "undefined", "void"}
            ):
                annotated = actual
        name = declaration.name
        if name:
            scope.define(name, annotated, assigned, constant=declaration.constant)

    # ------------------------------------------------------------------
    # Typed-object literal diagnostics (object<K, V>)
    # ------------------------------------------------------------------

    @staticmethod
    def _allowed_key_names(key_type: XType) -> list[str] | None:
        """Human-readable members of a literal-union key type, if it is one."""
        if not key_type.union_parts:
            return None
        names = [
            f'"{part.literal}"'
            for part in key_type.union_parts
            if part.literal is not None
        ]
        return names or None

    @staticmethod
    def _object_entry_key_type(entry: ObjectEntry) -> XType:
        """Key type of one object-literal entry.

        ``200: value`` is an integer key (``1.5: value`` a float key) so it
        checks against ``object<integer, ...>``; identifier/string keys keep
        their string-literal type.
        """
        if entry.key is None:
            return ANY
        if entry.key_is_number:
            try:
                if "." in entry.key:
                    return XType("float", literal=float(entry.key))
                return XType("integer", literal=int(entry.key))
            except ValueError:
                pass
        return XType("string", literal=entry.key)

    def _report_typed_object_literal(
        self,
        initializer: Any,
        actual: XType,
        annotated: XType,
        *,
        label: str,
        subject: str,
        spelling: str | None = None,
    ) -> bool:
        """Emit per-key diagnostics for a literal against ``object<K, V>``.

        A map interface (``integer key { ... }``) is viewed as the
        equivalent ``object<K, V>`` and diagnosed the same way.

        Returns True when at least one problem was reported, so the caller
        can suppress its generic assignability error.  ``label`` reads after
        "in " (``'settings'``, ``argument 1 of 'describe'``); ``subject`` is
        what the "is typed" note is about.
        """
        if not isinstance(initializer, ObjectLiteral):
            return False
        view = self._typed_object_view(annotated)
        if view is None:
            return False
        key_type, value_type, view_spelling = view
        spelling = (spelling or view_spelling).strip()
        if annotated.name == "object":
            # The parser stores generics without spaces; put them back for humans.
            spelling = re.sub(r"\s*,\s*", ", ", spelling)
        allowed = self._allowed_key_names(key_type)
        value_types = dict(actual.record_fields)
        reported = False
        for entry in initializer.entries:
            if entry.key is None:
                # Spread: the checker cannot see every key; stay permissive.
                continue
            if not is_compatible(
                self._object_entry_key_type(entry), key_type, relations=self
            ):
                notes = [f"{subject} is typed `{spelling}`"]
                if allowed is not None:
                    notes.append("allowed keys: " + ", ".join(allowed))
                self._error(
                    f"Object key '{entry.key}' is not allowed in {label}",
                    entry,
                    notes=notes,
                    helps=[
                        f"remove the '{entry.key}' entry, or allow "
                        f"'{entry.key}' in the key type"
                    ],
                )
                reported = True
                continue
            value_actual = value_types.get(entry.key)
            if value_actual is None:
                continue
            if not self._value_matches(entry.value, value_actual, value_type):
                self._error(
                    f"Value for key '{entry.key}' in {label} has the wrong type",
                    entry.value,
                    notes=[
                        f"expected `{value_type.display()}`, "
                        f"found `{value_actual.display()}`"
                    ],
                )
                reported = True
        return reported

    # ------------------------------------------------------------------
    # Type resolution
    # ------------------------------------------------------------------

    def _primitive_aliases_enabled(self) -> bool:
        return self._config is not None and self._config.enabled("primitive_aliases")

    def _resolve_annotation(
        self,
        type_name: str | None,
        generics: list[str] | set[str] | None = None,
        keep_generics: bool = False,
    ) -> XType:
        active = set(generics) if generics is not None else set(self._active_generics)
        resolved = self._resolve_named(parse_type(type_name), active, set())
        if active and not keep_generics:
            resolved = substitute(resolved, {name: ANY for name in active})
        return resolved

    def _resolve_named(
        self, type_value: XType, generics: set[str], seen: set[str]
    ) -> XType:
        if type_value.is_any:
            return type_value
        if type_value.literal is not None:
            return type_value
        if type_value.union_parts:
            return XType(
                "union",
                arguments=tuple(
                    self._resolve_named(part, generics, seen)
                    for part in type_value.arguments
                ),
                is_array=type_value.is_array,
                is_nullable=type_value.is_nullable,
                union_parts=tuple(
                    self._resolve_named(part, generics, seen)
                    for part in type_value.union_parts
                ),
                record_fields=tuple(
                    (name, self._resolve_named(field_type, generics, seen))
                    for name, field_type in type_value.record_fields
                ),
                is_any=type_value.is_any,
                dimensions=type_value.dimensions,
            )
        arguments = tuple(
            self._resolve_named(argument, generics, seen)
            for argument in type_value.arguments
        )
        fields = tuple(
            (name, self._resolve_named(field_type, generics, seen))
            for name, field_type in type_value.record_fields
        )
        name = type_value.name
        if name in generics:
            return XType(
                name,
                arguments,
                is_array=type_value.is_array,
                is_nullable=type_value.is_nullable,
                union_parts=type_value.union_parts,
                record_fields=fields,
                is_any=type_value.is_any,
                dimensions=type_value.dimensions,
            )
        if name in self._aliases and not arguments and name not in seen:
            alias = self._aliases[name]
            combined = XType(
                alias.name,
                alias.arguments,
                is_array=type_value.is_array or alias.is_array,
                is_nullable=type_value.is_nullable or alias.is_nullable,
                union_parts=alias.union_parts,
                record_fields=alias.record_fields,
                is_any=alias.is_any,
                dimensions=max(type_value.dimensions, alias.dimensions),
            )
            return self._resolve_named(combined, generics, seen | {name})
        if (
            name in BUILTIN_TYPE_NAMES
            or name == "record"
            or name in self._classes
            or name in self._interfaces
            or name in self._enums
        ):
            return XType(
                name,
                arguments,
                is_array=type_value.is_array,
                is_nullable=type_value.is_nullable,
                union_parts=type_value.union_parts,
                record_fields=fields,
                is_any=type_value.is_any,
                dimensions=type_value.dimensions,
            )
        if self._primitive_aliases_enabled():
            canonical = canonical_primitive_alias(name)
            if canonical is not None:
                return XType(
                    canonical,
                    arguments,
                    is_array=type_value.is_array,
                    is_nullable=type_value.is_nullable,
                    union_parts=type_value.union_parts,
                    record_fields=fields,
                    is_any=canonical == "any" or type_value.is_any,
                    dimensions=type_value.dimensions,
                )
        return ANY

    def _signature_type(
        self,
        type_name: str | None,
        generic_parameters: list[str],
        type_arguments: list[XType],
        base_mapping: dict[str, XType] | None = None,
    ) -> XType:
        generics: list[str] | set[str] = generic_parameters
        if base_mapping:
            # Keep the receiver's type parameters (`T` on `Box<integer>`)
            # resolvable while parsing the annotation — otherwise unknown
            # names collapse to `any` before the substitution below.
            generics = list(generic_parameters) + list(base_mapping)
        resolved = self._resolve_annotation(
            type_name, generics=generics, keep_generics=True
        )
        if base_mapping:
            # Receiver-supplied bindings (the class's own `<T>` arguments on
            # `Box<integer>`) are applied first; the call's method-level type
            # arguments then override same-named parameters.
            resolved = substitute(resolved, base_mapping)
        mapping: dict[str, XType] = {}
        for index, parameter in enumerate(generic_parameters):
            if index < len(type_arguments):
                mapping[parameter] = type_arguments[index]
            else:
                mapping[parameter] = ANY
        if mapping:
            resolved = substitute(resolved, mapping)
        return resolved

    def _receiver_mapping(self, object_type: XType) -> dict[str, XType]:
        """Map a generic class's type-parameter names to the receiver's
        concrete type arguments (`Box<integer>` → `{"T": integer}`)."""
        params = self._generic_params.get(object_type.name)
        if not params or not object_type.arguments:
            return {}
        count = min(len(params), len(object_type.arguments))
        return {params[index]: object_type.arguments[index] for index in range(count)}

    def _unify_generic(
        self,
        pattern: XType,
        actual: XType | None,
        names: list[str] | set[str],
        mapping: dict[str, XType],
    ) -> None:
        """Bind type-parameter names appearing in *pattern* to the matching
        parts of the argument type *actual* (first binding wins).

        Handles the shapes a parameter annotation can take: bare `T`, arrays
        `T[]`, nullable `T?`, generic arguments `Box<T>`, and record fields
        whose types mention T.  Unions and other constructs simply leave
        parameters unbound (they default to `any`, staying permissive).
        """
        if actual is None:
            return
        if pattern.is_array:
            if not actual.is_array:
                return
            self._unify_generic(
                _strip_array(pattern), _strip_array(actual), names, mapping
            )
            return
        if pattern.name in names:
            mapping.setdefault(pattern.name, actual)
            return
        if (
            pattern.arguments
            and actual.arguments
            and len(pattern.arguments) == len(actual.arguments)
        ):
            for sub_pattern, sub_actual in zip(pattern.arguments, actual.arguments):
                self._unify_generic(sub_pattern, sub_actual, names, mapping)
            return
        if pattern.record_fields and actual.record_fields:
            actual_fields = dict(actual.record_fields)
            for field_name, field_type in pattern.record_fields:
                if field_name in actual_fields:
                    self._unify_generic(
                        field_type, actual_fields[field_name], names, mapping
                    )

    def _infer_generic_arguments(
        self,
        declaration: Any,
        generic_parameters: list[str],
        argument_types: list[XType],
        base_mapping: dict[str, XType] | None = None,
    ) -> list[XType]:
        """Infer a declaration's type arguments positionally from the actual
        argument types.  Parameters that stay unbound become `any`."""
        mapping: dict[str, XType] = {}
        for index, actual in enumerate(argument_types):
            parameter = self._parameter_for(declaration, index)
            if parameter is None:
                continue
            generics: list[str] | set[str] = generic_parameters
            if base_mapping:
                generics = list(generic_parameters) + list(base_mapping)
            pattern = self._resolve_annotation(
                parameter.type_name,
                generics=generics,
                keep_generics=True,
            )
            if base_mapping:
                pattern = substitute(pattern, base_mapping)
            self._unify_generic(pattern, actual, generic_parameters, mapping)
        return [mapping.get(name, ANY) for name in generic_parameters]

    def _call_result_type(
        self,
        declaration: Any,
        generic_parameters: list[str],
        type_arguments: list[XType],
        base_mapping: dict[str, XType] | None = None,
    ) -> XType:
        """Result type of *calling* `declaration`.

        Non-async functions return their declared annotation.  An `async`
        function always produces an awaitable at runtime, so its call type is
        `Promise<T>` where T is the declared annotation — unless the
        annotation is already a `Promise<T>` (the `Promise<T> async function`
        spelling, whose body returns the unwrapped T) or `void`/`any`.
        """
        resolved = self._signature_type(
            declaration.return_type, generic_parameters, type_arguments, base_mapping
        )
        if getattr(declaration, "is_async", False) and not resolved.is_any:
            if resolved.name == "Promise":
                return resolved
            if resolved.name not in {"void", "null", "undefined"}:
                return XType("Promise", arguments=(resolved,))
        return resolved

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _infer(self, expression: Any, scope: TypeScope) -> XType:
        if expression is None:
            return ANY
        if getattr(expression, "line", None):
            self._current_node = expression
        if isinstance(expression, Literal):
            return self._literal_type(expression.value)
        if isinstance(expression, UndefinedLiteral):
            return UNDEFINED
        if isinstance(expression, Identifier):
            return self._infer_identifier(expression, scope)
        if isinstance(expression, ArrayLiteral):
            return self._infer_array_literal(expression, scope)
        if isinstance(expression, ObjectLiteral):
            return self._infer_object_literal(expression, scope)
        if isinstance(expression, FunctionExpression):
            return self._infer_function_expression(expression, scope)
        if isinstance(expression, Unary):
            return self._infer_unary(expression, scope)
        if isinstance(expression, Binary):
            return self._infer_binary(expression, scope)
        if isinstance(expression, Assignment):
            return self._infer_assignment(expression, scope)
        if isinstance(expression, Member):
            return self._infer_member(expression, scope)
        if isinstance(expression, ImportCall):
            # Checked as an ordinary call to the imported name: the loader
            # flattens the module, so the target is registered already.
            local_name = expression.alias or expression.import_path.split(".")[-1]
            call = Call(Identifier(local_name), expression.arguments)
            for attribute in (
                "line",
                "column",
                "source_name",
                "end_line",
                "end_column",
            ):
                if hasattr(expression, attribute):
                    setattr(call, attribute, getattr(expression, attribute))
            return self._infer_call(call, scope)
        if isinstance(expression, Call):
            return self._infer_call(expression, scope)
        if isinstance(expression, NewExpression):
            return self._infer_new(expression, scope)
        if isinstance(expression, Index):
            return self._infer_index(expression, scope)
        if isinstance(expression, ThisExpression):
            found = scope.lookup("this")
            return found[0] if found else ANY
        if isinstance(expression, TemplateLiteral):
            for part in expression.parts:
                if not isinstance(part, str):
                    self._infer(part, scope)
            return STRING
        if isinstance(expression, MatchExpression):
            return self._infer_match(expression, scope)
        if isinstance(expression, AwaitExpression):
            inner = self._infer(expression.value, scope)
            if inner.is_any:
                return ANY
            if inner.name == "Promise":
                return inner.arguments[0] if inner.arguments else ANY
            # JavaScript semantics: awaiting a non-promise yields the value
            # itself, so the static type is simply the operand's type.
            return inner
        if isinstance(expression, Spread):
            self._infer(expression.value, scope)
            return ANY
        if isinstance(expression, OptionalChain):
            self._infer_qualified_object(expression.object, scope)
            for segment in expression.segments:
                if not isinstance(segment.value, str):
                    self._infer(segment.value, scope)
            return ANY
        return ANY

    def _infer_identifier(self, expression: Identifier, scope: TypeScope) -> XType:
        found = scope.lookup(expression.name)
        if found is None:
            return ANY
        type_value, assigned = found
        if not assigned:
            self._error(
                f"Variable '{expression.name}' is used before it is definitely "
                f"assigned",
                expression,
            )
        if (
            self._root_scope is not None
            and scope.lookup_owner(expression.name) is self._root_scope
        ):
            # A name this file never imported: it only reaches here because a
            # module import flattened the whole module into the shared scope.
            if self._report_not_imported(expression.name, expression):
                return type_value
            if expression is not self._deferred_type_value:
                if (
                    expression.name in self._interfaces
                    and type_value.name == expression.name
                ):
                    self._error(
                        f"Interface '{expression.name}' is a type, not a value",
                        expression,
                    )
                    return ANY
                if (
                    expression.name in self._enums
                    and type_value.name == expression.name
                ):
                    self._error(
                        f"Enum '{expression.name}' is a type, not a value",
                        expression,
                    )
                    return ANY
        return type_value

    def _infer_array_literal(self, expression: ArrayLiteral, scope: TypeScope) -> XType:
        if not expression.items:
            return XType("any", is_array=True, is_any=True)
        element_types: list[XType] = []
        has_spread = False
        for item in expression.items:
            if isinstance(item, Spread):
                self._infer(item.value, scope)
                has_spread = True
                continue
            element_types.append(self._infer(item, scope))
        if has_spread:
            return XType("any", is_array=True, is_any=True)
        element = self._collapse(element_types)
        return XType(
            element.name,
            element.arguments,
            is_array=True,
            is_nullable=element.is_nullable,
            union_parts=element.union_parts,
            record_fields=element.record_fields,
            is_any=element.is_any,
            dimensions=element.dimensions + 1,
        )

    @staticmethod
    def _strip_nullish(type_value: XType) -> XType | None:
        """Remove ``null``/``undefined`` from a type; ``None`` when nothing remains."""
        stripped = type_value
        if stripped.is_nullable:
            stripped = replace(stripped, is_nullable=False)
        if stripped.union_parts:
            kept = tuple(
                part
                for part in stripped.union_parts
                if part.name not in {"null", "undefined"}
            )
            if not kept:
                return None
            stripped = (
                XType("union", union_parts=kept)
                if len(kept) > 1
                else kept[0]
            )
            if stripped.is_nullable:
                stripped = replace(stripped, is_nullable=False)
        elif stripped.name in {"null", "undefined"}:
            return None
        return stripped

    def _collapse(self, types: list[XType]) -> XType:
        if not types:
            return ANY
        distinct: list[XType] = []
        for type_value in types:
            if type_value not in distinct:
                distinct.append(type_value)
        if len(distinct) == 1:
            return distinct[0]
        if any(type_value.is_any for type_value in distinct):
            return ANY
        return XType("union", union_parts=tuple(distinct))

    def _infer_object_literal(
        self, expression: ObjectLiteral, scope: TypeScope
    ) -> XType:
        fields: dict[str, XType] = {}
        opaque_spread = False
        for entry in expression.entries:
            key = entry.key
            value = entry.value
            if key is None:
                spread_type = self._infer(value.value, scope)
                if spread_type.record_fields:
                    for name, field_type in spread_type.record_fields:
                        fields[name] = field_type
                else:
                    # The spread source has no visible shape; the literal's
                    # overall type degrades to a bare object, as before.
                    opaque_spread = True
                continue
            fields[key] = self._infer(value, scope)
        if fields and not opaque_spread:
            return XType("record", record_fields=tuple(fields.items()))
        return OBJECT

    def _infer_function_expression(
        self, expression: FunctionExpression, scope: TypeScope
    ) -> XType:
        lambda_scope = scope.child()
        for parameter in expression.parameters:
            lambda_scope.define(
                parameter.name,
                self._resolve_annotation(parameter.type_name),
                True,
            )
        expected = self._resolve_return_type(expression.return_type)
        previous_expected = self._expected_return
        previous_saw = self._saw_value_return
        previous_void = self._returns_void
        previous_kind = self._callable_kind
        previous_name = self._callable_name
        self._expected_return = expected
        self._saw_value_return = False
        self._returns_void = self._is_void_annotation(expression.return_type)
        self._callable_kind = "Function expression"
        self._callable_name = None
        if expression.body:
            self._collect_local_functions(expression.body)
            self._check_statements(expression.body, lambda_scope)
            if (
                expected is not None
                and not self._saw_value_return
                and not self._contains_throw(expression.body)
            ):
                self._error(
                    "Function expression must return a value of type "
                    f"'{expected.display()}'",
                    expression,
                )
        self._expected_return = previous_expected
        self._saw_value_return = previous_saw
        self._returns_void = previous_void
        self._callable_kind = previous_kind
        self._callable_name = previous_name
        return FUNCTION

    def _infer_unary(self, expression: Unary, scope: TypeScope) -> XType:
        operand = self._infer(expression.operand, scope)
        operator = expression.operator
        if operator in {"!", "not"}:
            return BOOLEAN
        if operator == "typeof":
            return STRING
        if operator in {"++", "--"}:
            target = expression.operand
            if isinstance(target, Identifier):
                found = scope.lookup(target.name)
                if found is not None and found[1] and scope.is_constant(target.name):
                    self._error(
                        f"Cannot reassign constant '{target.name}'",
                        expression,
                        helps=[
                            f"declare '{target.name}' with `let` instead of `const` "
                            "to allow reassignment"
                        ],
                    )
                scope.mark_assigned(target.name)
            elif isinstance(target, (Member, Index)):
                self._check_const_container_write(target, scope, expression)
            return operand
        if operator in {"-", "+"}:
            if operand.name == "integer":
                return INTEGER
            if operand.name == "float":
                return FLOAT
            return ANY
        return operand

    @staticmethod
    def _is_literal_zero(expression: Any) -> bool:
        return (
            isinstance(expression, Literal)
            and isinstance(expression.value, (int, float))
            and not isinstance(expression.value, bool)
            and expression.value == 0
        )

    def _infer_binary(self, expression: Binary, scope: TypeScope) -> XType:
        operator = expression.operator
        if operator == "?:":
            left_type = self._infer(expression.left, scope)
            true_value, false_value = expression.right
            true_type = self._infer(true_value, scope)
            false_type = self._infer(false_value, scope)
            if is_compatible(true_type, false_type, relations=self):
                return false_type
            if is_compatible(false_type, true_type, relations=self):
                return true_type
            return self._collapse([true_type, false_type])
        left = self._infer(expression.left, scope)
        right = self._infer(expression.right, scope)
        if operator == "+":
            if left.name == "string" or right.name == "string":
                return STRING
            if left.is_any or right.is_any:
                return ANY
            if left.name in {"integer", "float"} and right.name in {"integer", "float"}:
                if left.name == "float" or right.name == "float":
                    return FLOAT
                return INTEGER
            return ANY
        if operator in {"-", "*", "%"}:
            if left.is_any or right.is_any:
                return ANY
            if left.name in {"integer", "float"} and right.name in {"integer", "float"}:
                if left.name == "integer" and right.name == "integer":
                    return INTEGER
                return FLOAT
            return ANY
        if operator == "/":
            if self._is_literal_zero(expression.right):
                # Division by a literal zero always throws at runtime, so the
                # expression never yields a value.  Report it only when no try
                # block can catch it, and treat the result as `any` either way
                # to avoid cascading diagnostics on the surrounding code.
                if self._try_depth == 0:
                    self._error("Cannot divide by zero", expression)
                return ANY
            if left.is_any or right.is_any:
                return ANY
            if left.name in {"integer", "float"} and right.name in {"integer", "float"}:
                return FLOAT
            return ANY
        if operator == "??":
            # TypeScript's rule: NonNullable<typeof left> | typeof right.
            stripped = self._strip_nullish(left)
            if stripped is None:
                return right
            return self._collapse([stripped, right])
        if operator in {
            "==",
            "!=",
            "===",
            "!==",
            "<",
            ">",
            "<=",
            ">=",
            "&&",
            "||",
            "and",
            "or",
            "in",
            "instanceof",
        }:
            return BOOLEAN
        return ANY

    def _infer_assignment(self, expression: Assignment, scope: TypeScope) -> XType:
        value_type = self._infer(expression.value, scope)
        target = expression.target
        if isinstance(target, Identifier):
            found = scope.lookup(target.name)
            if found is not None:
                target_type, assigned = found
                if scope.is_constant(target.name) and assigned:
                    self._error(
                        f"Cannot reassign constant '{target.name}'",
                        expression,
                        helps=[
                            f"declare '{target.name}' with `let` instead of `const` "
                            "to allow reassignment"
                        ],
                    )
                elif expression.operator == "=":
                    if not self._value_matches(
                        expression.value, value_type, target_type
                    ):
                        reported = self._report_typed_object_literal(
                            expression.value,
                            value_type,
                            target_type,
                            label=f"'{target.name}'",
                            subject=f"'{target.name}'",
                        )
                        if not reported:
                            self._error(
                                f"Cannot assign '{value_type.display()}' to "
                                f"'{target.name}' of type '{target_type.display()}'",
                                expression,
                                notes=[
                                    f"expected `{target_type.display()}`, "
                                    f"found `{value_type.display()}`"
                                ],
                            )
                else:
                    self._infer(target, scope)
                scope.mark_assigned(target.name)
                return target_type
            return value_type
        if isinstance(target, Member):
            self._check_const_container_write(target, scope, expression)
            self._check_member_write(target, value_type, scope, expression)
            return value_type
        if isinstance(target, Index):
            self._check_const_container_write(target, scope, expression)
            container = self._infer(target.object, scope)
            self._infer(target.index, scope)
            if container.is_array:
                element = _strip_array(container)
                if not self._value_matches(expression.value, value_type, element):
                    self._error(
                        f"Cannot assign '{value_type.display()}' to array element "
                        f"of type '{element.display()}'",
                        expression,
                        notes=[
                            f"expected `{element.display()}`, "
                            f"found `{value_type.display()}`"
                        ],
                    )
            return value_type
        return value_type

    @staticmethod
    def _assignment_root_name(target: Any) -> str | None:
        """Return the variable an assignment target ultimately writes into.

        ``matrix[0][1]`` and ``settings.port`` both trace back to one binding;
        calls and ``this`` do not trace to a name at all.
        """
        while isinstance(target, (Member, Index)):
            target = target.object
        if isinstance(target, Identifier):
            return target.name
        return None

    def _check_const_container_write(
        self, target: Any, scope: TypeScope, node: Any
    ) -> None:
        """Report writes through a ``const`` binding (deep immutability)."""
        root = self._assignment_root_name(target)
        if root is None or not scope.is_constant(root):
            return
        noun = "member" if isinstance(target, Member) else "element"
        self._error(
            f"Cannot modify {noun} of constant '{root}'",
            node,
            helps=[f"declare '{root}' with `let` instead of `const` to allow mutation"],
        )

    def _check_member_write(
        self,
        target: Member,
        value_type: XType,
        scope: TypeScope,
        node: Any,
    ) -> None:
        object_type = self._infer(target.object, scope)
        if object_type.name in self._classes or object_type.name in self._interfaces:
            found, owner = self._find_class_member(object_type.name, target.name)
            if found is None or owner is None:
                return
            if isinstance(found, FunctionDeclaration):
                return
            self._check_visibility(found, owner, target, kind="field", verb="modify")
            field_type = self._resolve_annotation(found.type_name)
            if not self._value_matches(node.value, value_type, field_type):
                self._error(
                    f"Cannot assign '{value_type.display()}' to "
                    f"'{owner}.{target.name}' of type '{field_type.display()}'",
                    node,
                    notes=[
                        f"expected `{field_type.display()}`, "
                        f"found `{value_type.display()}`"
                    ],
                )
            return
        if object_type.record_fields:
            for field_name, field_type in object_type.record_fields:
                if field_name == target.name:
                    if not self._value_matches(node.value, value_type, field_type):
                        self._error(
                            f"Cannot assign '{value_type.display()}' to "
                            f"'{target.name}' of type '{field_type.display()}'",
                            node,
                            notes=[
                                f"expected `{field_type.display()}`, "
                                f"found `{value_type.display()}`"
                            ],
                        )
                    return

    def _infer_qualified_object(
        self, object_expression: Any, scope: TypeScope
    ) -> XType:
        """Infer the object of ``x.y`` / ``x[..]`` / ``x?.y``.

        Waives the "is a type, not a value" diagnostic for bare enum/
        interface identifiers, since ``Gender.MALE`` is a value even though
        ``Gender`` alone is only a type.
        """
        previous = self._deferred_type_value
        if isinstance(object_expression, Identifier):
            self._deferred_type_value = object_expression
        try:
            return self._infer(object_expression, scope)
        finally:
            self._deferred_type_value = previous

    def _iterable_element_type(self, iterable_type: XType) -> XType:
        """Element type produced by `for (T v of iterable)` for *iterable_type*.

        Covers the shapes `for-of` actually iterates: arrays (one dimension
        per loop), strings (characters), and the generic collections/maps —
        lists yield their element, maps yield their keys.  Anything else
        stays `any`, so dynamic iterables keep their permissive behaviour.
        """
        if iterable_type.is_any:
            return ANY
        if iterable_type.union_parts or iterable_type.record_fields:
            return ANY
        if iterable_type.is_nullable:
            iterable_type = _strip_nullable(iterable_type)
        if iterable_type.is_array:
            return _strip_array(iterable_type)
        if iterable_type.name == "string":
            return STRING
        alias = _collection_alias(iterable_type.name)
        if alias in {
            "LinkedList",
            "Stack",
            "Queue",
            "PriorityQueue",
            "HashSet",
            "Set",
            "TreeSet",
            "LinkedHashSet",
            "ThreadSafeSet",
        }:
            return iterable_type.arguments[0] if iterable_type.arguments else ANY
        if alias in {"HashMap", "Map", "TreeMap", "LinkedHashMap", "LruCache"} or (
            iterable_type.name == "object" and iterable_type.arguments
        ):
            # `for (k of someMap)` walks the keys, matching Python/dict order.
            return iterable_type.arguments[0] if iterable_type.arguments else ANY
        return ANY

    def _infer_member(self, expression: Member, scope: TypeScope) -> XType:
        object_type = self._infer_qualified_object(expression.object, scope)
        name = expression.name
        if object_type.name in self._classes or object_type.name in self._interfaces:
            found, owner = self._find_class_member(object_type.name, name)
            if found is not None and owner is not None:
                self._check_visibility(
                    found, owner, expression, kind=None, verb="access"
                )
                if isinstance(found, VariableDeclaration):
                    receiver_map = self._receiver_mapping(object_type)
                    resolved = self._resolve_annotation(
                        found.type_name,
                        generics=list(receiver_map) if receiver_map else None,
                        keep_generics=True,
                    )
                    if receiver_map:
                        # `Box<integer>.item` where the field is declared `T`
                        resolved = substitute(resolved, receiver_map)
                    return resolved
                if isinstance(found, FunctionDeclaration):
                    return FUNCTION
                if isinstance(found, ClassDeclaration):
                    return parse_type(found.name)
            if found is None and owner is None and object_type.name in self._classes:
                helps: Sequence[str] = ()
                suggestion = _closest_match(name, self._member_names(object_type.name))
                if suggestion is not None:
                    helps = [f"did you mean `{suggestion}`?"]
                self._error(
                    f"'{object_type.name}' has no member '{name}'",
                    expression,
                    helps=helps,
                )
                return ANY
            if found is None:
                return self._builtin_member(object_type, name)
        if object_type.name in self._enums and not object_type.is_array:
            enum_declaration = self._find_enum(object_type.name)
            if name in {"name", "value"}:
                return STRING if name == "name" else ANY
            if enum_declaration is not None and any(
                member_name == name for member_name, _ in enum_declaration.members
            ):
                return parse_type(object_type.name)
            return ANY
        if object_type.record_fields:
            for field_name, field_type in object_type.record_fields:
                if field_name == name:
                    return field_type
        fallback = self._builtin_member(object_type, name)
        if (
            isinstance(expression.object, Identifier)
            and not object_type.is_any
            and fallback.is_any
            and self._report_alias_member(expression, scope)
        ):
            return ANY
        return fallback

    def _report_alias_member(self, expression: Member, scope: TypeScope) -> bool:
        """Report member access through a type alias whose target has no such
        member (`Participants.Gender`).

        Returns False when the object isn't a (non-shadowed) type alias, so
        ordinary unresolved members keep their old silent-ANY behaviour.
        Accesses that DO resolve through the alias target (class statics,
        enum members, record fields, string/array builtins) never get here.
        """
        alias_name = expression.object.name
        alias_type = self._aliases.get(alias_name)
        if alias_type is None or self._root_scope is None:
            return False
        if scope.lookup_owner(alias_name) is not self._root_scope:
            return False
        found = scope.lookup(alias_name)
        if found is None or found[0] != alias_type:
            return False
        # When this file never imported the alias's module, import visibility
        # already reported the real problem; don't pile on.
        if self._visibility_gap(alias_name, expression.object) is not None:
            return True
        helps: Sequence[str] = ()
        member_source = getattr(expression, "source_name", None)
        declaring = self._visibility_gap(expression.name, expression)
        if member_source is not None and declaring is not None:
            helps = [
                "add `import "
                f"{self._import_suggestion(declaring, member_source)}."
                f"{expression.name}`"
            ]
        self._error(
            f"Type alias '{alias_name}' has no member '{expression.name}'",
            expression,
            helps=helps,
        )
        return True

    def _builtin_member(self, object_type: XType, name: str) -> XType:
        if name in {"length", "size"}:
            if (
                object_type.is_array
                or object_type.name == "string"
                or object_type.is_any
            ):
                return INTEGER
            return ANY
        if name == "toString":
            if (
                object_type.name in {"string", "integer", "float", "boolean"}
                or object_type.is_any
            ):
                return STRING
            return ANY
        if object_type.is_array and name in ARRAY_METHOD_NAMES:
            return FUNCTION
        if object_type.name == "string" and name in STRING_METHOD_NAMES:
            return FUNCTION
        if object_type.is_any and (
            name in ARRAY_METHOD_NAMES or name in STRING_METHOD_NAMES
        ):
            return FUNCTION
        return ANY

    def _infer_call(self, expression: Call, scope: TypeScope) -> XType:
        callee = expression.callee
        previous_deferred = self._deferred_type_value
        if isinstance(callee, Identifier):
            # `IFoo()` — the interface-construct error below owns this line.
            self._deferred_type_value = callee
        try:
            self._infer(callee, scope)
        finally:
            self._deferred_type_value = previous_deferred
        # typeOf is introspection: passing a type name (typeOf(Bar),
        # typeOf(Gender)) is the whole point, so waive the
        # "is a type, not a value" check for its direct arguments.
        introspection = isinstance(callee, Identifier) and callee.name == "typeOf"
        argument_types = []
        for argument in expression.arguments:
            if introspection and isinstance(argument, Identifier):
                self._deferred_type_value = argument
                try:
                    argument_types.append(self._infer(argument, scope))
                finally:
                    self._deferred_type_value = previous_deferred
            else:
                argument_types.append(self._infer(argument, scope))
        if isinstance(callee, Identifier):
            name = callee.name
            registered = self._functions.get(name)
            if registered:
                return self._check_overloads(
                    name,
                    registered,
                    expression,
                    argument_types,
                    expression.type_arguments,
                )
            if name in self._classes:
                return self._check_constructor_call(name, expression, argument_types)
            if name in self._interfaces:
                self._error(f"Cannot construct interface '{name}'", expression)
                return parse_type(name)
            # Language builtins with fixed result types (see the
            # BUILTIN_SCOPE_NAMES entries and the interpreter's
            # _parse_float/_parse_int builtins).
            if name == "parseFloat":
                return FLOAT
            if name == "parseInt":
                return INTEGER
            return ANY
        if isinstance(callee, Member):
            if callee.name == "map" and expression.arguments:
                callback = expression.arguments[0]
                if isinstance(callback, FunctionExpression) and callback.return_type:
                    mapped = self._resolve_annotation(callback.return_type)
                    if mapped.name != "void":
                        return XType(
                            mapped.name,
                            mapped.arguments,
                            is_array=True,
                            is_nullable=mapped.is_nullable,
                            union_parts=mapped.union_parts,
                            record_fields=mapped.record_fields,
                            is_any=mapped.is_any,
                            dimensions=mapped.dimensions + 1,
                        )
                    return XType("any", is_array=True, is_any=True)
            if callee.name == "filter":
                source = self._infer_qualified_object(callee.object, scope)
                if source.is_array:
                    return source
            return self._method_return(callee, scope, expression)
        return ANY

    def _method_return(
        self,
        callee: Member,
        scope: TypeScope,
        call: Any,
    ) -> XType:
        type_arguments: list[str] = list(getattr(call, "type_arguments", None) or [])
        object_type = self._infer_qualified_object(callee.object, scope)
        name = callee.name
        if object_type.name in self._classes or object_type.name in self._interfaces:
            found, owner = self._find_class_member(object_type.name, name)
            if found is not None and owner is not None:
                if isinstance(found, FunctionDeclaration):
                    # Check the arguments too: method calls go through the
                    # same overload machinery as free functions, with the
                    # receiver's `Box<integer>` arguments bound to the class's
                    # type parameters.
                    receiver_map = self._receiver_mapping(object_type)
                    argument_types = [
                        self._infer(argument, scope)
                        for argument in call.arguments
                    ]
                    return self._check_overloads(
                        name,
                        [found],
                        call,
                        argument_types,
                        type_arguments,
                        kind="Method",
                        base_mapping=receiver_map,
                    )
                if isinstance(found, VariableDeclaration):
                    receiver_map = self._receiver_mapping(object_type)
                    resolved = self._resolve_annotation(
                        found.type_name,
                        generics=list(receiver_map) if receiver_map else None,
                        keep_generics=True,
                    )
                    if receiver_map:
                        resolved = substitute(resolved, receiver_map)
                    return resolved
                if isinstance(found, ClassDeclaration):
                    return parse_type(found.name)
        expectations = self._collection_method_expectations(object_type, name)
        if expectations is not None:
            argument_types = [
                self._infer(argument, scope) for argument in call.arguments
            ]
            for index, expected in enumerate(expectations):
                if index >= len(argument_types):
                    break
                actual = argument_types[index]
                expression = call.arguments[index]
                matched = (
                    self._value_matches(expression, actual, expected)
                    if expression is not None
                    else is_compatible(actual, expected, relations=self)
                )
                if not matched:
                    self._error(
                        f"Argument {index + 1} of '{name}' has type "
                        f"'{actual.display()}', expected '{expected.display()}'",
                        call,
                        notes=self._incompatibility_notes(actual, expected),
                    )
            return ANY
        if name == "toString":
            if (
                object_type.name in {"string", "integer", "float", "boolean"}
                or object_type.is_any
            ):
                return STRING
        return ANY

    def _collection_method_expectations(
        self, object_type: XType, name: str
    ) -> list[XType] | None:
        """Argument expectations for a Python-backed collection method.

        Returns the expected type per argument position, or ``None`` when
        the receiver is not a typed collection or the method has no rule
        (callbacks and helper methods stay unchecked).  Receivers without
        type arguments stay unchecked so dynamic collections keep their
        permissive behaviour.
        """
        if object_type.is_any or not object_type.arguments:
            return None
        alias = _collection_alias(object_type.name)
        roles: tuple[str, ...] | None = None
        if alias in COLLECTION_ELEMENT_FAMILIES:
            roles = COLLECTION_METHOD_ROLES.get(name)
            type_arguments = object_type.arguments[:1]
        elif alias in COLLECTION_MAP_FAMILIES:
            roles = COLLECTION_METHOD_ROLES_MAP.get(name)
            type_arguments = object_type.arguments[:2]
        if roles is None or not type_arguments:
            return None
        role_types = {
            "element": type_arguments[0],
            "key": type_arguments[0],
            "index": INTEGER,
        }
        if len(type_arguments) > 1:
            role_types["value"] = type_arguments[1]
        if "value" in roles and "value" not in role_types:
            return None
        return [role_types[role] for role in roles]

    def _infer_new(self, expression: NewExpression, scope: TypeScope) -> XType:
        argument_types = [
            self._infer(argument, scope) for argument in expression.arguments
        ]
        constructed = self._resolve_annotation(expression.class_name)
        base_name = expression.class_name.split("<")[0].strip()
        if base_name in self._interfaces:
            self._error(f"Cannot construct interface '{base_name}'", expression)
            return constructed
        if base_name in self._classes:
            declaration = self._classes[base_name]
            if "abstract" in declaration.modifiers:
                self._error(
                    f"Cannot construct abstract class '{base_name}'", expression
                )
            type_arguments = list(constructed.arguments)
            class_params = list(declaration.generic_parameters or [])
            if class_params and not type_arguments:
                # `new Box(1)` on `class Box<T>`: bind T from the
                # constructor's parameter types so the result types as
                # `Box<integer>` rather than a bare, argument-less `Box`.
                constructor = next(
                    (
                        member
                        for member in declaration.members
                        if isinstance(member, FunctionDeclaration)
                        and member.name == base_name
                    ),
                    None,
                )
                if constructor is not None:
                    mapping: dict[str, XType] = {}
                    for index, actual in enumerate(argument_types):
                        parameter = self._parameter_for(constructor, index)
                        if parameter is None:
                            continue
                        pattern = self._resolve_annotation(
                            parameter.type_name,
                            generics=class_params,
                            keep_generics=True,
                        )
                        self._unify_generic(pattern, actual, class_params, mapping)
                    if mapping:
                        constructed = XType(
                            base_name,
                            arguments=tuple(
                                mapping.get(param, ANY) for param in class_params
                            ),
                        )
                        type_arguments = list(constructed.arguments)
            self._check_constructor_call(
                base_name, expression, argument_types, type_arguments=type_arguments
            )
        return constructed

    EXCEPTION_ROOTS = frozenset({"Throwable", "Exception", "Error"})

    def _accepts_implicit_exception_arguments(self, declaration: Any) -> bool:
        """Exception roots take ``(message, cause)`` without a constructor.

        Mirrors ``XClass.construct``: an exception base, or a class deriving
        directly from one, initializes its message fields from the arguments
        instead of requiring a declared constructor.
        """
        if declaration.name in self.EXCEPTION_ROOTS:
            return True
        parent_name = (declaration.parent_name or "").split("<")[0].strip()
        return parent_name in self.EXCEPTION_ROOTS

    def _check_constructor_call(
        self,
        class_name: str,
        node: Any,
        argument_types: list[XType],
        type_arguments: list[XType] | None = None,
    ) -> XType:
        declaration = self._classes.get(class_name)
        if declaration is None:
            return parse_type(class_name)
        constructors = [
            member
            for member in declaration.members
            if isinstance(member, FunctionDeclaration) and member.name == class_name
        ]
        if not constructors:
            if argument_types:
                if self._accepts_implicit_exception_arguments(declaration):
                    if len(argument_types) > 2:
                        self._error(
                            f"{class_name} expects a message and optional cause",
                            node,
                        )
                else:
                    self._error(
                        f"No overload of '{class_name}' accepts "
                        f"{len(argument_types)} argument(s)",
                        node,
                    )
            return parse_type(class_name)
        return self._check_overloads(
            class_name,
            constructors,
            node,
            argument_types,
            type_arguments=[],
            class_generics=list(declaration.generic_parameters or []),
            explicit_type_arguments=type_arguments,
            kind="Constructor",
        )

    def _infer_index(self, expression: Index, scope: TypeScope) -> XType:
        container = self._infer_qualified_object(expression.object, scope)
        self._infer(expression.index, scope)
        if container.is_array:
            return _strip_array(container)
        if container.name == "string":
            return STRING
        return ANY

    def _infer_match(self, expression: MatchExpression, scope: TypeScope) -> XType:
        self._infer(expression.value, scope)
        arm_types: list[XType] = []
        for arm in expression.arms:
            if arm.guard is not None:
                self._infer(arm.guard, scope)
            body = arm.body
            if isinstance(body, Block):
                self._check_statements(body.statements, scope.child())
                arm_types.append(ANY)
            elif isinstance(body, list):
                self._check_statements(body, scope.child())
                arm_types.append(ANY)
            else:
                arm_types.append(self._infer(body, scope))
        return self._collapse(arm_types)

    def _literal_type(self, value: Any) -> XType:
        if value is None:
            return NULL
        if isinstance(value, bool):
            return BOOLEAN
        if isinstance(value, int):
            return INTEGER
        if isinstance(value, float):
            return FLOAT
        if isinstance(value, str):
            return STRING
        return ANY

    @staticmethod
    def _string_literal_type(expression: Any) -> XType | None:
        """Return the literal-string type for a string literal, else ``None``."""
        if isinstance(expression, Literal) and isinstance(expression.value, str):
            return XType("string", literal=expression.value)
        return None

    @staticmethod
    def _references_literal(type_value: XType) -> bool:
        """Whether an annotation contains any string-literal member."""
        if type_value.literal is not None:
            return True
        if any(
            TypeChecker._references_literal(part) for part in type_value.union_parts
        ):
            return True
        if any(TypeChecker._references_literal(arg) for arg in type_value.arguments):
            return True
        if any(
            TypeChecker._references_literal(field_type)
            for _, field_type in type_value.record_fields
        ):
            return True
        return False

    def _value_matches(
        self,
        expression: Any,
        inferred: XType,
        target: XType,
    ) -> bool:
        """Compatibility for a concrete expression against *target*.

        When the target names string-literal members, a literal expression is
        compared by value (``"theme"`` only fits ``"theme"``); otherwise the
        inferred type is used as before.  An object literal checks its own
        entries so a numeric key (``200:``) can satisfy
        ``object<integer, ...>`` while the inferred shape still has to hold.
        """
        literal = self._string_literal_type(expression)
        if literal is not None and self._references_literal(target):
            return is_compatible(literal, target, relations=self)
        if isinstance(expression, ObjectLiteral):
            view = self._typed_object_view(target)
            if view is not None:
                key_type, value_type, _ = view
                object_view = XType("object", arguments=(key_type, value_type))
                return self._object_literal_matches(expression, inferred, object_view)
        return is_compatible(inferred, target, relations=self)

    def _object_literal_matches(
        self,
        expression: ObjectLiteral,
        inferred: XType,
        target: XType,
    ) -> bool:
        """Per-entry check of a literal against ``object<K, V>``.

        Key and value entries are checked individually (numeric keys against
        ``integer``/``float``, string keys against their literal type), then
        the inferred record type still has to be compatible so fields coming
        from an opaque or wider spread keep their strictness.
        """
        key_type, value_type = target.arguments
        value_types = dict(inferred.record_fields)
        for entry in expression.entries:
            if entry.key is None:
                continue
            if not is_compatible(
                self._object_entry_key_type(entry), key_type, relations=self
            ):
                return False
            value_actual = value_types.get(entry.key)
            if value_actual is None:
                continue
            if not self._value_matches(entry.value, value_actual, value_type):
                return False
        return is_compatible(inferred, target, relations=self)

    # ------------------------------------------------------------------
    # Overload resolution
    # ------------------------------------------------------------------

    def _check_overloads(
        self,
        name: str,
        declarations: list[FunctionDeclaration],
        node: Any,
        argument_types: list[XType],
        type_arguments: list[str],
        class_generics: list[str] | None = None,
        explicit_type_arguments: list[XType] | None = None,
        kind: str = "Function",
        base_mapping: dict[str, XType] | None = None,
    ) -> XType:
        if explicit_type_arguments is not None:
            explicit = explicit_type_arguments
        else:
            explicit = [self._resolve_annotation(t) for t in type_arguments]
        first_arity_match: FunctionDeclaration | None = None
        first_explicit: list[XType] = explicit
        for declaration in declarations:
            if not self._arity_matches(declaration.parameters, len(argument_types)):
                continue
            if first_arity_match is None:
                first_arity_match = declaration
            generic_parameters = (
                class_generics
                if class_generics is not None
                else list(declaration.generic_parameters or [])
            )
            declared_explicit = explicit
            if (
                explicit_type_arguments is None
                and not type_arguments
                and generic_parameters
            ):
                # `identity(5)` with no `identity<integer>(...)`: bind T from
                # the argument types before checking and before typing the
                # call's result.
                declared_explicit = self._infer_generic_arguments(
                    declaration, generic_parameters, argument_types, base_mapping
                )
                if first_arity_match is declaration:
                    first_explicit = declared_explicit
            failures = self._argument_failures(
                declaration,
                argument_types,
                generic_parameters,
                declared_explicit,
                getattr(node, "arguments", []),
                base_mapping=base_mapping,
            )
            if not failures:
                return self._call_result_type(
                    declaration, generic_parameters, declared_explicit, base_mapping
                )
        if first_arity_match is None:
            available = ", ".join(
                f"`{self._format_signature(declaration, kind)}`"
                for declaration in declarations
            )
            helps: Sequence[str] = ()
            if available:
                helps = [f"available overloads: {available}"]
            self._error(
                f"No overload of '{name}' accepts {len(argument_types)} "
                f"argument(s)",
                node,
                helps=helps,
            )
            return ANY
        generic_parameters = (
            class_generics
            if class_generics is not None
            else list(first_arity_match.generic_parameters or [])
        )
        for index, actual in enumerate(argument_types):
            parameter = self._parameter_for(first_arity_match, index)
            if parameter is None:
                continue
            expected = self._signature_type(
                parameter.type_name, generic_parameters, first_explicit, base_mapping
            )
            expression = (
                node.arguments[index]
                if index < len(getattr(node, "arguments", []))
                else None
            )
            matched = (
                self._value_matches(expression, actual, expected)
                if expression is not None
                else is_compatible(actual, expected, relations=self)
            )
            if not matched:
                reported = False
                if expression is not None:
                    reported = self._report_typed_object_literal(
                        expression,
                        actual,
                        expected,
                        label=f"argument {index + 1} of '{name}'",
                        subject=f"parameter '{parameter.name}'",
                        spelling=parameter.type_name,
                    )
                if not reported:
                    self._error(
                        f"Argument {index + 1} of '{name}' has type "
                        f"'{actual.display()}', expected '{expected.display()}'",
                        node,
                        notes=self._incompatibility_notes(actual, expected),
                    )
        return ANY

    def _argument_failures(
        self,
        declaration: FunctionDeclaration,
        argument_types: list[XType],
        generic_parameters: list[str],
        explicit: list[XType],
        arguments: list[Any] | None = None,
        base_mapping: dict[str, XType] | None = None,
    ) -> list[int]:
        failures: list[int] = []
        arguments = arguments or []
        for index, actual in enumerate(argument_types):
            parameter = self._parameter_for(declaration, index)
            if parameter is None:
                failures.append(index)
                continue
            expected = self._signature_type(
                parameter.type_name, generic_parameters, explicit, base_mapping
            )
            expression = arguments[index] if index < len(arguments) else None
            matched = (
                self._value_matches(expression, actual, expected)
                if expression is not None
                else is_compatible(actual, expected, relations=self)
            )
            if not matched:
                failures.append(index)
        return failures

    def _parameter_for(
        self, declaration: FunctionDeclaration, index: int
    ) -> Any | None:
        parameters = declaration.parameters
        if index < len(parameters):
            return parameters[index]
        if parameters and parameters[-1].is_rest:
            return parameters[-1]
        return None

    def _arity_matches(self, parameters: list[Any], argument_count: int) -> bool:
        has_rest = bool(parameters and parameters[-1].is_rest)
        required = sum(
            1
            for parameter in parameters
            if not parameter.is_rest
            and not parameter.has_default
            and not (
                parameter.type_name is not None and parameter.type_name.endswith("?")
            )
        )
        if has_rest:
            return argument_count >= required
        return required <= argument_count <= len(parameters)

    # ------------------------------------------------------------------
    # Member lookup, visibility
    # ------------------------------------------------------------------

    def _find_class_member(
        self, type_name: str, member_name: str
    ) -> tuple[Any, str | None] | tuple[None, None]:
        current: str | None = type_name
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            declaration = self._classes.get(current) or self._interfaces.get(current)
            if declaration is None:
                return None, None
            for member in declaration.members:
                if not hasattr(member, "name") or member.name != member_name:
                    continue
                if (
                    isinstance(member, FunctionDeclaration)
                    and member.name == declaration.name
                ):
                    continue
                return member, current
            parent = declaration.parent_name
            if parent:
                base = parent.split("<")[0].strip()
                if base in self._classes or base in self._interfaces:
                    current = base
                    continue
                return None, "?unknown-parent"
            current = None
        return None, None

    def _member_names(self, type_name: str) -> set[str]:
        """Every member name reachable from ``type_name``, including parents."""
        names: set[str] = set()
        current: str | None = type_name
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            declaration = self._classes.get(current) or self._interfaces.get(current)
            if declaration is None:
                break
            for member in declaration.members:
                name = getattr(member, "name", None)
                if name and name != declaration.name:
                    names.add(name)
            parent = declaration.parent_name
            current = parent.split("<")[0].strip() if parent else None
        return names

    def _find_enum(self, name: str) -> EnumDeclaration | None:
        return self._enums.get(name)

    def _check_visibility(
        self,
        member: Any,
        owner_name: str,
        node: Any,
        kind: str | None,
        verb: str,
    ) -> None:
        modifiers = getattr(member, "modifiers", None) or set()
        visibility = "public"
        for candidate in _VISIBILITY_ORDER:
            if candidate in modifiers:
                visibility = candidate
                break
        if visibility == "public":
            return
        requester = self._class_stack[-1] if self._class_stack else None
        if visibility == "private":
            allowed = requester is not None and requester == owner_name
        else:
            allowed = requester is not None and (
                requester == owner_name or self._extends(requester, owner_name)
            )
        if allowed:
            return
        if kind is None:
            kind = "method" if isinstance(member, FunctionDeclaration) else "field"
        self._error(
            f"Cannot {verb} {visibility} {kind} '{owner_name}.{node.name}'",
            node,
        )

    def _extends(self, descendant: str, ancestor: str) -> bool:
        visited: set[str] = set()
        current: str | None = descendant
        while current and current not in visited:
            if current == ancestor:
                return True
            visited.add(current)
            declaration = self._classes.get(current) or self._interfaces.get(current)
            if declaration is None or not declaration.parent_name:
                if declaration is not None and declaration.parent_name:
                    return True
                return False
            base = declaration.parent_name.split("<")[0].strip()
            if base not in self._classes and base not in self._interfaces:
                return True
            current = base
        return False

    # ------------------------------------------------------------------
    # Relations (nominal / structural subtyping)
    # ------------------------------------------------------------------

    def is_subtype(self, source: XType, target: XType) -> bool | None:
        if source.is_any or target.is_any:
            return True
        if target.name in self._interfaces:
            interface = self._interfaces[target.name]
            return self._satisfies_interface(source, interface)
        if target.name in self._classes:
            return self._satisfies_class(source, target)
        if target.name in self._enums:
            return source.name == target.name
        return None

    def _satisfies_class(self, source: XType, target: XType) -> bool:
        if source.name in self._classes:
            if source.name == target.name:
                return True
            return self._ancestry_reaches(source.name, target.name)
        if source.name in {"record", "object"}:
            return True
        if source.name in self._interfaces or source.name in self._enums:
            return False
        if source.name in KNOWN_TYPE_NAMES:
            return False
        if source.name in {"null", "undefined"}:
            return False
        return True

    def _ancestry_reaches(self, class_name: str, target_name: str) -> bool:
        visited: set[str] = set()
        current: str | None = class_name
        while current and current not in visited:
            if current == target_name:
                return True
            visited.add(current)
            declaration = self._classes.get(current) or self._interfaces.get(current)
            if declaration is None:
                return True
            if not declaration.parent_name:
                return False
            base = declaration.parent_name.split("<")[0].strip()
            if base not in self._classes and base not in self._interfaces:
                return True
            current = base
        return False

    def _map_interface_view(self, interface: ClassDeclaration) -> XType | None:
        """``object<K, V>`` view of a map interface (``integer key { ... }``).

        Returns None for ordinary member interfaces.  The value shape is a
        record type built from the entry's field declarations.
        """
        entry = next(
            (
                member
                for member in interface.members
                if isinstance(member, InterfaceMapEntry)
            ),
            None,
        )
        if entry is None:
            return None
        key_type = self._resolve_annotation(entry.key_type)
        value_fields = tuple(
            (member.name, self._resolve_annotation(member.type_name))
            for member in entry.members
            if isinstance(member, VariableDeclaration)
        )
        return XType(
            "object", arguments=(key_type, XType("record", record_fields=value_fields))
        )

    def _typed_object_view(
        self, annotated: XType
    ) -> tuple[XType, XType, str] | None:
        """Key type, value type, and spelling for ``object<K, V>`` or a map interface."""
        if annotated.name == "object" and len(annotated.arguments) == 2:
            key_type, value_type = annotated.arguments
            spelling = re.sub(r"\s*,\s*", ", ", annotated.display().strip())
            return key_type, value_type, spelling
        interface = self._interfaces.get(annotated.name or "")
        if interface is not None:
            view = self._map_interface_view(interface)
            if view is not None:
                key_type, value_type = view.arguments
                return key_type, value_type, annotated.display().strip()
        return None

    def _satisfies_interface(self, source: XType, interface: ClassDeclaration) -> bool:
        if source.is_any:
            return True
        map_view = self._map_interface_view(interface)
        if map_view is not None:
            if source.name == interface.name:
                return True
            return is_compatible(source, map_view, relations=self)
        required = self._interface_members(interface)
        if source.record_fields or source.name == "object":
            if source.name == "object":
                return True
            fields = dict(source.record_fields)
            for member in required:
                if isinstance(member, FunctionDeclaration):
                    field_type = fields.get(member.name)
                    if field_type is None:
                        return False
                    if not is_compatible(field_type, FUNCTION, relations=self):
                        return False
                elif isinstance(member, VariableDeclaration):
                    if member.name not in fields:
                        return False
                    expected = self._resolve_annotation(member.type_name)
                    if not is_compatible(fields[member.name], expected, relations=self):
                        return False
            return True
        if source.name in self._classes:
            hierarchy_ok = True
            for member in required:
                found, owner = self._find_class_member(source.name, member.name)
                if found is None:
                    if owner == "?unknown-parent":
                        hierarchy_ok = True
                        break
                    return False
                if isinstance(member, FunctionDeclaration):
                    if not isinstance(found, FunctionDeclaration):
                        return False
                    modifiers = getattr(found, "modifiers", None) or set()
                    if {"private", "protected"} & set(modifiers):
                        return False
                    if "static" in modifiers:
                        return False
                elif isinstance(member, VariableDeclaration):
                    if not isinstance(found, VariableDeclaration):
                        return False
                    modifiers = getattr(found, "modifiers", None) or set()
                    if {"private", "protected"} & set(modifiers):
                        return False
                    expected = self._resolve_annotation(member.type_name)
                    declared = self._resolve_annotation(found.type_name)
                    if not is_compatible(declared, expected, relations=self):
                        return False
            return hierarchy_ok
        if source.name in self._interfaces:
            provided = {
                member.name: member
                for member in self._interface_members_for(source.name)
            }
            for member in required:
                match = provided.get(member.name)
                if match is None:
                    return False
                if isinstance(member, VariableDeclaration) and isinstance(
                    match, VariableDeclaration
                ):
                    expected = self._resolve_annotation(member.type_name)
                    declared = self._resolve_annotation(match.type_name)
                    if not is_compatible(declared, expected, relations=self):
                        return False
            return True
        return False

    def _interface_members(self, interface: ClassDeclaration) -> list[Any]:
        members: list[Any] = []
        parent_name = interface.parent_name
        while parent_name:
            parent = self._interfaces.get(parent_name.split("<")[0].strip())
            if parent is None:
                break
            members.extend(parent.members)
            parent_name = parent.parent_name
        members.extend(interface.members)
        return members

    def _interface_members_for(self, name: str) -> list[Any]:
        interface = self._interfaces.get(name)
        if interface is None:
            return []
        return self._interface_members(interface)

    def _incompatibility_notes(
        self, inferred: XType, target: XType
    ) -> list[str]:
        """Explain why *inferred* failed *target*, naming the exact gaps.

        Only a structural view can be explained: an object literal checked
        against an interface or a record annotation lists the members it is
        missing and the ones whose type does not match.  Opaque or nominal
        mismatches return no notes and keep the caller's generic message.
        """
        if not inferred.record_fields or inferred.name == "object":
            return []
        fields = dict(inferred.record_fields)
        notes: list[str] = []
        if target.name in self._interfaces:
            for member in self._interface_members(self._interfaces[target.name]):
                if isinstance(member, FunctionDeclaration):
                    found = fields.get(member.name)
                    if found is None:
                        notes.append(f"missing required method `{member.name}()`")
                    elif not is_compatible(found, FUNCTION, relations=self):
                        notes.append(
                            f"member `{member.name}`: expected a function, "
                            f"found `{found.display()}`"
                        )
                elif isinstance(member, VariableDeclaration):
                    expected = self._resolve_annotation(member.type_name)
                    found = fields.get(member.name)
                    if found is None:
                        notes.append(
                            f"missing required member "
                            f"`{member.name}: {expected.display()}`"
                        )
                    elif not is_compatible(found, expected, relations=self):
                        notes.append(
                            f"member `{member.name}`: expected "
                            f"`{expected.display()}`, found `{found.display()}`"
                        )
        elif target.record_fields:
            for field_name, field_type in target.record_fields:
                found = fields.get(field_name)
                if found is None:
                    notes.append(
                        f"missing field `{field_name}: {field_type.display()}`"
                    )
                elif not is_compatible(found, field_type, relations=self):
                    notes.append(
                        f"field `{field_name}`: expected "
                        f"`{field_type.display()}`, found `{found.display()}`"
                    )
        return notes

    # ------------------------------------------------------------------
    # Declaration-level type-name validation
    # ------------------------------------------------------------------

    def _known_type_names(self) -> set[str]:
        """Every name accepted in a type position for the current program."""
        if self._known_names is None:
            names = set(BUILTIN_TYPE_NAMES)
            names.update(self._classes)
            names.update(self._interfaces)
            names.update(self._enums)
            names.update(self._aliases)
            names.update(self._namespace_roots)
            names.update(self._import_names)
            for parameter_names in self._generic_params.values():
                names.update(parameter_names)
            self._known_names = names
        return self._known_names

    def _check_type_name_references(self, declarations: list[Any]) -> None:
        for declaration in declarations:
            self._walk_type_references(declaration, declaration)

    def _walk_type_references(self, node: Any, anchor: Any) -> None:
        """Recursively validate every type-name string reachable from *node*.

        *anchor* is the nearest located declaration; it is used for
        diagnostics because some nodes (for example ``Parameter``) carry no
        position information of their own.
        """
        if node is None or isinstance(node, (str, bytes, int, float, bool)):
            return
        if isinstance(node, dict):
            for value in node.values():
                self._walk_type_references(value, anchor)
            return
        if isinstance(node, (list, tuple, set)):
            for item in node:
                self._walk_type_references(item, anchor)
            return
        if not is_dataclass(node):
            return
        if getattr(node, "line", None) is not None:
            anchor = node
        type_name = getattr(node, "type_name", None)
        if isinstance(type_name, str):
            self._check_type_string(type_name, anchor)
        key_type = getattr(node, "key_type", None)
        if isinstance(key_type, str):
            self._check_type_string(key_type, anchor)
        return_type = getattr(node, "return_type", None)
        if isinstance(return_type, str):
            self._check_type_string(return_type, anchor)
        parent_name = getattr(node, "parent_name", None)
        if isinstance(parent_name, str):
            self._check_type_string(parent_name, anchor)
        implemented_types = getattr(node, "implemented_types", None)
        if implemented_types:
            for implemented in implemented_types:
                self._check_type_string(implemented, anchor)
        if isinstance(node, NewExpression):
            self._check_type_string(node.class_name, anchor)
        if isinstance(node, Call) and node.type_arguments:
            for argument in node.type_arguments:
                self._check_type_string(argument, anchor)
        if isinstance(node, TryStatement):
            for catch in node.catches:
                if isinstance(catch, tuple) and catch:
                    self._check_type_string(catch[0], anchor)
        for field in fields(node):
            self._walk_type_references(getattr(node, field.name), anchor)

    def _check_type_string(self, text: str | None, anchor: Any) -> None:
        """Validate one annotation string (union/array/nullable/generic aware)."""
        if not text:
            return
        known = self._known_type_names()
        stack = [text.strip()]
        while stack:
            candidate = stack.pop()
            if not candidate:
                continue
            if "|" in candidate:
                union_parts = split_union(candidate)
                if len(union_parts) > 1:
                    stack.extend(union_parts)
                    continue
            while candidate.endswith("?"):
                candidate = candidate[:-1].strip()
            while candidate.endswith("[]"):
                candidate = candidate[:-2].strip()
            if not candidate:
                continue
            if len(candidate) >= 2 and candidate[0] == '"' and candidate[-1] == '"':
                continue
            if candidate.startswith("record"):
                remainder = candidate[len("record") :].lstrip()
                if remainder.startswith("{"):
                    candidate = remainder
            if candidate.startswith("{") and candidate.endswith("}"):
                for field_text in split_top_level(candidate[1:-1], ";"):
                    field_text = field_text.strip()
                    if not field_text:
                        continue
                    pieces = field_text.rsplit(None, 1)
                    stack.append(pieces[0] if len(pieces) == 2 else field_text)
                continue
            if "<" in candidate:
                base, _, rest = candidate.partition("<")
                stack.append(base.strip())
                if rest.endswith(">"):
                    rest = rest[:-1]
                stack.extend(split_top_level(rest, ","))
                continue
            if candidate in known:
                # The type registry is flat, so a sibling module's type is
                # always "known" — visibility decides whether it may be used
                # here without an import.
                if "." not in candidate:
                    self._report_not_imported(candidate, anchor, noun="Type")
                continue
            if (
                self._primitive_aliases_enabled()
                and canonical_primitive_alias(candidate) is not None
            ):
                continue
            # Exception-hierarchy paths are exact: a typo'd intermediate
            # segment would otherwise fall through to the leaf-name rule
            # below and typecheck as valid.
            is_exception_path = candidate == "System.Throwable" or (
                candidate.startswith("System.Throwable.")
            )
            segments = [segment.strip() for segment in candidate.split(".")]
            if not is_exception_path and segments[0] in known:
                continue
            if not is_exception_path and any(
                segment in known for segment in segments[1:]
            ):
                continue
            helps: Sequence[str] = ()
            suggestion = _closest_match(candidate, known)
            if suggestion is not None:
                helps = [f"did you mean `{suggestion}`?"]
            self._error(f"Unknown type '{candidate}'", anchor, helps=helps)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @staticmethod
    def _format_parameter(parameter: Any) -> str:
        """Render one parameter as it would be written in a signature."""
        if parameter.is_rest:
            return f"{parameter.type_name or 'any'} ...{parameter.name}"
        return f"{parameter.type_name or 'any'} {parameter.name}"

    def _format_signature(self, declaration: Any, kind: str = "Function") -> str:
        """Render a copy-pasteable signature for a function-like node.

        ``kind`` follows :func:`callable_kind`: a top-level ``Function`` needs
        the ``function`` keyword, a class ``Method``/``Constructor`` does not.
        """
        parameters = ", ".join(
            self._format_parameter(parameter) for parameter in declaration.parameters
        )
        if kind == "Constructor":
            return f"{declaration.name}({parameters})"
        if kind == "Function":
            keyword = (
                f"{declaration.return_type} function"
                if declaration.return_type
                else "function"
            )
            return f"{keyword} {declaration.name}({parameters})"
        prefix = f"{declaration.return_type} " if declaration.return_type else ""
        return f"{prefix}{declaration.name}({parameters})"

    def _import_suggestion(self, declaring_path: str, source_name: str) -> str:
        """How the source file should spell an import of the module at
        *declaring_path* (sibling-relative, matching loader resolution)."""
        try:
            relative = os.path.relpath(declaring_path, str(Path(source_name).parent))
        except (OSError, ValueError):
            relative = None
        if relative is not None and not relative.startswith(".."):
            return ".".join(Path(relative).with_suffix("").parts)
        return Path(declaring_path).stem

    def _visibility_gap(self, name: str, node: Any) -> str | None:
        """Declaring module of *name* when node's file may not see *name*.

        Returns the declaring file's path (for the import suggestion) or
        ``None`` when the name is visible, not project-declared, or there is
        no import information (hand-built programs keep the flat behaviour).
        """
        if not self._name_provenance or not self._module_visibility:
            return None
        if name in self._active_generics:
            return None
        if any(name in params for params in self._generic_params.values()):
            return None
        source = getattr(node, "source_name", None)
        if source is None:
            return None
        visible = self._module_visibility.get(source)
        if visible is None or name in visible:
            return None
        return self._name_provenance.get(name)

    def _report_not_imported(self, name: str, node: Any, noun: str = "Name") -> bool:
        # Language builtins can be shadowed by a project declaration
        # (`let string string = "Maya"`); that must not turn every other
        # file's use of the builtin into an import error.
        if noun == "Name" and name in BUILTIN_SCOPE_NAMES:
            return False
        if noun == "Type" and (
            name in BUILTIN_TYPE_NAMES or canonical_primitive_alias(name) is not None
        ):
            return False
        declaring = self._visibility_gap(name, node)
        if declaring is None:
            return False
        helps: Sequence[str] = ()
        source = getattr(node, "source_name", None)
        if source is not None:
            helps = [
                "add `import " f"{self._import_suggestion(declaring, source)}.{name}`"
            ]
        self._error(
            f"{noun} '{name}' is not defined in this module",
            node,
            helps=helps,
        )
        return True

    def _error(
        self,
        message: str,
        node: Any,
        *,
        notes: Sequence[str] = (),
        helps: Sequence[str] = (),
    ) -> None:
        line = getattr(node, "line", None)
        column = getattr(node, "column", None)
        source_name = getattr(node, "source_name", None)
        if line is None and self._location is not None:
            line, column, source_name = self._location
        if source_name is None:
            source_name = self._source_name
        key = (message, line, column, source_name)
        if key in self._seen:
            return
        self._seen.add(key)
        end_line = getattr(node, "end_line", None)
        end_column = getattr(node, "end_column", None)
        if end_column is None and line is not None and self._location is not None:
            end_line = getattr(self, "_location_end_line", None)
            end_column = getattr(self, "_location_end_column", None)
        self.errors.append(
            TypeCheckError(
                message,
                source_name=source_name,
                line=line,
                column=column,
                notes=notes,
                helps=helps,
                end_line=end_line,
                end_column=end_column,
            )
        )
