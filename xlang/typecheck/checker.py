"""Walk an X program and emit compile-time type diagnostics."""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence
from dataclasses import fields, is_dataclass
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
    ImportDeclaration,
    ImportNamespaceAlias,
    Index,
    Literal,
    Member,
    MatchExpression,
    ModuleImport,
    NamespaceDeclaration,
    NewExpression,
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
    is_compatible,
    parse_type,
    split_union,
    substitute,
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
        self._enums: set[str] = set()
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
        self._try_depth = 0
        self._current_node: Any | None = None

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

    def check(self, program: Program, source_name: str | None = None, config=None) -> list[TypeCheckError]:
        """Type-check ``program`` and return all diagnostics (does not raise)."""
        self._reset(source_name, config)
        try:
            self._check_program(program)
        except RecursionError:
            self._record_depth_error()
        return self.errors

    def _check_program(self, program: Program) -> None:
        self._collect_types(program.declarations)
        for module_declarations in program.modules.values():
            self._collect_types(module_declarations)
        self._check_type_name_references(program.declarations)
        for module_declarations in program.modules.values():
            self._check_type_name_references(module_declarations)
        self._validate_interface_implementations()
        self._check_strict_typing(program.declarations, self._source_name)
        for module_declarations in program.modules.values():
            self._check_strict_typing(module_declarations, self._source_name)
        scope = self._builtin_scope()
        self._check_declarations(program.declarations, scope)
        for module_declarations in program.modules.values():
            self._check_declarations(module_declarations, scope.child())

    def check_or_raise(self, program: Program, source_name: str | None = None, config=None) -> None:
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
        self._collect_types(program.declarations)
        for module_declarations in program.modules.values():
            self._collect_types(module_declarations)
        self._check_type_name_references(program.declarations)
        for module_declarations in program.modules.values():
            self._check_type_name_references(module_declarations)
        self._validate_interface_implementations()
        self._check_strict_typing(program.declarations, self._source_name)
        for module_declarations in program.modules.values():
            self._check_strict_typing(module_declarations, self._source_name)

    # ------------------------------------------------------------------
    # Scopes and collection
    # ------------------------------------------------------------------

    def _builtin_scope(self) -> TypeScope:
        scope = TypeScope()
        for name in (
            "print",
            "range",
            "typeOf",
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
        ):
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
                self._enums.add(declaration.name)
            elif isinstance(declaration, TypeDeclaration):
                self._aliases[declaration.name] = parse_type(declaration.type_name)
            elif isinstance(declaration, NamespaceDeclaration):
                self._namespace_roots.add(declaration.name.split(".")[0])
                self._collect_types(declaration.declarations)
            elif isinstance(declaration, FunctionDeclaration):
                self._register_function(declaration)
                if declaration.generic_parameters:
                    registered = self._generic_params.setdefault(
                        declaration.name, []
                    )
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
            self._enums.add(node.name)
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
            elif isinstance(statement, (WhileStatement, DoWhileStatement, ForStatement, ClassicForStatement)):
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
            elif isinstance(statement, (WhileStatement, DoWhileStatement, ForStatement, ClassicForStatement)):
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
                    self._aliases.get(declaration.name, parse_type(declaration.type_name)),
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
            self._infer(declaration.iterable, scope)
            loop_scope = scope.child()
            if declaration.variable:
                loop_scope.define(
                    declaration.variable,
                    self._resolve_annotation(declaration.type_name),
                    True,
                )
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
        elif isinstance(
            declaration,
            (
                ModuleImport,
                ImportDeclaration,
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
            if expected is not None and not is_compatible(
                actual, expected, relations=self
            ):
                self._error(
                    f"Return type '{actual.display()}' is not compatible with "
                    f"'{expected.display()}'",
                    declaration,
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
            self._check_statements(declaration.body.statements, scope.child())
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
            self._check_statements(
                declaration.finally_body.statements, scope.child()
            )

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
        previous_expected = self._expected_return
        previous_saw = self._saw_value_return
        previous_in_constructor = self._in_constructor
        previous_void = self._returns_void
        previous_kind = self._callable_kind
        previous_name = self._callable_name
        is_constructor = (
            self._class_stack
            and declaration.name == self._class_stack[-1]
            and declaration.return_type is None
        )
        self._expected_return = expected
        self._saw_value_return = False
        self._in_constructor = is_constructor
        self._returns_void = self._is_void_annotation(declaration.return_type)
        self._callable_kind = callable_kind(
            declaration.name,
            self._class_stack[-1] if self._class_stack else None,
        )
        self._callable_name = declaration.name
        if declaration.body:
            self._collect_local_functions(declaration.body)
            self._check_statements(declaration.body, body_scope)
            if (
                expected is not None
                and not self._saw_value_return
                and not self._contains_throw(declaration.body)
            ):
                self._error(
                    f"{self._callable_kind} '{declaration.name}' must return a value of type "
                    f"'{expected.display()}'",
                    declaration,
                )
        self._expected_return = previous_expected
        self._saw_value_return = previous_saw
        self._in_constructor = previous_in_constructor
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
            if base_name not in self._interfaces:
                self._error(
                    f"Class '{declaration.name}' implements unknown interface "
                    f"'{interface_name}'",
                    declaration,
                )
        if declaration.parent_name:
            parent_name = declaration.parent_name.split("<")[0].strip()
            parent = self._classes.get(parent_name)
            if parent is not None and "final" in parent.modifiers:
                self._error(
                    f"Cannot extend final class '{parent_name}'", declaration
                )
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
                if isinstance(member, FunctionDeclaration) and "abstract" in member.modifiers:
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
                        if not is_compatible(actual_return, expected_return, relations=self):
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

    def _check_strict_typing(self, declarations: list[Any], source_name: str | None = None) -> None:
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
                self._check_strict_typing_statements(statement.then_branch.statements, source_name)
                else_branch = statement.else_branch
                if isinstance(else_branch, Block):
                    self._check_strict_typing_statements(else_branch.statements, source_name)
                elif else_branch is not None:
                    self._check_strict_typing_statement(else_branch, source_name)
            elif isinstance(statement, (WhileStatement, DoWhileStatement)):
                self._check_strict_typing_statements(statement.body.statements, source_name)
            elif isinstance(statement, ForStatement):
                self._check_strict_typing_statements(statement.body.statements, source_name)
            elif isinstance(statement, ClassicForStatement):
                self._check_strict_typing_statements(statement.body.statements, source_name)
            elif isinstance(statement, TryStatement):
                self._check_strict_typing_statements(statement.body.statements, source_name)
                for _, _, catch_body in statement.catches:
                    self._check_strict_typing_statements(catch_body.statements, source_name)
                if statement.finally_body is not None:
                    self._check_strict_typing_statements(
                        statement.finally_body.statements, source_name
                    )
            elif isinstance(statement, SwitchStatement):
                for case in statement.cases:
                    self._check_strict_typing_statements(case.body.statements, source_name)
            elif isinstance(
                statement, (ExpressionStatement, Assignment, FunctionDeclaration, VariableDeclaration)
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
                            helps=[
                                _parameter_type_help("Function", "", None)
                            ],
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
                self._check_strict_typing_statements(declaration.body, source_name=source_name)
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
            if not is_compatible(actual, annotated, relations=self):
                self._error(
                    f"Cannot assign '{actual.display()}' to '{declaration.name}' "
                    f"of type '{annotated.display()}'",
                    declaration,
                    notes=[
                        f"expected `{annotated.display()}`, found `{actual.display()}`"
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
    # Type resolution
    # ------------------------------------------------------------------

    def _resolve_annotation(
        self,
        type_name: str | None,
        generics: list[str] | set[str] | None = None,
        keep_generics: bool = False,
    ) -> XType:
        active = (
            set(generics) if generics is not None else set(self._active_generics)
        )
        resolved = self._resolve_named(parse_type(type_name), active, set())
        if active and not keep_generics:
            resolved = substitute(resolved, {name: ANY for name in active})
        return resolved

    def _resolve_named(
        self, type_value: XType, generics: set[str], seen: set[str]
    ) -> XType:
        if type_value.is_any:
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
            )
            return self._resolve_named(combined, generics, seen | {name})
        if (
            name in KNOWN_TYPE_NAMES
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
            )
        return ANY

    def _signature_type(
        self,
        type_name: str | None,
        generic_parameters: list[str],
        type_arguments: list[XType],
    ) -> XType:
        resolved = self._resolve_annotation(
            type_name, generics=generic_parameters, keep_generics=True
        )
        mapping: dict[str, XType] = {}
        for index, parameter in enumerate(generic_parameters):
            if index < len(type_arguments):
                mapping[parameter] = type_arguments[index]
            else:
                mapping[parameter] = ANY
        if mapping:
            resolved = substitute(resolved, mapping)
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
            self._infer(expression.value, scope)
            return ANY
        if isinstance(expression, Spread):
            self._infer(expression.value, scope)
            return ANY
        if isinstance(expression, OptionalChain):
            self._infer(expression.object, scope)
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
        return type_value

    def _infer_array_literal(
        self, expression: ArrayLiteral, scope: TypeScope
    ) -> XType:
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
        )

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
        fields: list[tuple[str, XType]] = []
        for key, value in expression.entries:
            if key is None:
                self._infer(value, scope)
                return OBJECT
            fields.append((key, self._infer(value, scope)))
        if fields:
            return XType("record", record_fields=tuple(fields))
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
            if isinstance(expression.operand, Identifier):
                scope.mark_assigned(expression.operand.name)
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
            if is_compatible(left, right, relations=self):
                return right
            if is_compatible(right, left, relations=self):
                return left
            return ANY
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

    def _infer_assignment(
        self, expression: Assignment, scope: TypeScope
    ) -> XType:
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
                    if not is_compatible(value_type, target_type, relations=self):
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
            self._check_member_write(target, value_type, scope, expression)
            return value_type
        if isinstance(target, Index):
            container = self._infer(target.object, scope)
            self._infer(target.index, scope)
            if container.is_array:
                element = XType(
                    container.name,
                    container.arguments,
                    is_array=False,
                    is_nullable=container.is_nullable,
                    union_parts=container.union_parts,
                    record_fields=container.record_fields,
                    is_any=container.is_any,
                )
                if not is_compatible(value_type, element, relations=self):
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
            if not is_compatible(value_type, field_type, relations=self):
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
                    if not is_compatible(value_type, field_type, relations=self):
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

    def _infer_member(self, expression: Member, scope: TypeScope) -> XType:
        object_type = self._infer(expression.object, scope)
        name = expression.name
        if object_type.name in self._classes or object_type.name in self._interfaces:
            found, owner = self._find_class_member(object_type.name, name)
            if found is not None and owner is not None:
                self._check_visibility(found, owner, expression, kind=None, verb="access")
                if isinstance(found, VariableDeclaration):
                    return self._resolve_annotation(found.type_name)
                if isinstance(found, FunctionDeclaration):
                    return FUNCTION
                if isinstance(found, ClassDeclaration):
                    return parse_type(found.name)
            if (
                found is None
                and owner is None
                and object_type.name in self._classes
            ):
                helps: Sequence[str] = ()
                suggestion = _closest_match(
                    name, self._member_names(object_type.name)
                )
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
                member_name == name
                for member_name, _ in enum_declaration.members
            ):
                return parse_type(object_type.name)
            return ANY
        if object_type.record_fields:
            for field_name, field_type in object_type.record_fields:
                if field_name == name:
                    return field_type
        return self._builtin_member(object_type, name)

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
        self._infer(callee, scope)
        argument_types = [
            self._infer(argument, scope) for argument in expression.arguments
        ]
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
                return self._check_constructor_call(
                    name, expression, argument_types
                )
            if name in self._interfaces:
                self._error(f"Cannot construct interface '{name}'", expression)
                return parse_type(name)
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
                        )
                    return XType("any", is_array=True, is_any=True)
            if callee.name == "filter":
                source = self._infer(callee.object, scope)
                if source.is_array:
                    return source
            return self._method_return(callee, scope, expression.type_arguments)
        return ANY

    def _method_return(
        self,
        callee: Member,
        scope: TypeScope,
        type_arguments: list[str],
    ) -> XType:
        object_type = self._infer(callee.object, scope)
        name = callee.name
        if object_type.name in self._classes or object_type.name in self._interfaces:
            found, owner = self._find_class_member(object_type.name, name)
            if found is not None and owner is not None:
                if isinstance(found, FunctionDeclaration):
                    explicit = [self._resolve_annotation(t) for t in type_arguments]
                    generic_parameters = list(found.generic_parameters or [])
                    return self._signature_type(
                        found.return_type, generic_parameters, explicit
                    )
                if isinstance(found, VariableDeclaration):
                    return self._resolve_annotation(found.type_name)
                if isinstance(found, ClassDeclaration):
                    return parse_type(found.name)
        if name == "toString":
            if (
                object_type.name in {"string", "integer", "float", "boolean"}
                or object_type.is_any
            ):
                return STRING
        return ANY

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
        container = self._infer(expression.object, scope)
        self._infer(expression.index, scope)
        if container.is_array:
            return XType(
                container.name,
                container.arguments,
                is_array=False,
                is_nullable=container.is_nullable,
                union_parts=container.union_parts,
                record_fields=container.record_fields,
                is_any=container.is_any,
            )
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
    ) -> XType:
        if explicit_type_arguments is not None:
            explicit = explicit_type_arguments
        else:
            explicit = [self._resolve_annotation(t) for t in type_arguments]
        first_arity_match: FunctionDeclaration | None = None
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
            failures = self._argument_failures(
                declaration, argument_types, generic_parameters, explicit
            )
            if not failures:
                return self._signature_type(
                    declaration.return_type, generic_parameters, explicit
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
                parameter.type_name, generic_parameters, explicit
            )
            if not is_compatible(actual, expected, relations=self):
                self._error(
                    f"Argument {index + 1} of '{name}' has type "
                    f"'{actual.display()}', expected '{expected.display()}'",
                    node,
                )
        return ANY

    def _argument_failures(
        self,
        declaration: FunctionDeclaration,
        argument_types: list[XType],
        generic_parameters: list[str],
        explicit: list[XType],
    ) -> list[int]:
        failures: list[int] = []
        for index, actual in enumerate(argument_types):
            parameter = self._parameter_for(declaration, index)
            if parameter is None:
                failures.append(index)
                continue
            expected = self._signature_type(
                parameter.type_name, generic_parameters, explicit
            )
            if not is_compatible(actual, expected, relations=self):
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
                parameter.type_name is not None
                and parameter.type_name.endswith("?")
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
        return None

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
            kind = (
                "method"
                if isinstance(member, FunctionDeclaration)
                else "field"
            )
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

    def _satisfies_interface(
        self, source: XType, interface: ClassDeclaration
    ) -> bool:
        if source.is_any:
            return True
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
                    if not is_compatible(
                        fields[member.name], expected, relations=self
                    ):
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
            if candidate.startswith("record"):
                remainder = candidate[len("record"):].lstrip()
                if remainder.startswith("{"):
                    candidate = remainder
            if candidate.startswith("{") and candidate.endswith("}"):
                for field_text in candidate[1:-1].split(";"):
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
                depth = 0
                current = ""
                for character in rest:
                    if character == "<":
                        depth += 1
                        current += character
                    elif character == ">":
                        depth -= 1
                        current += character
                    elif character == "," and depth == 0:
                        stack.append(current)
                        current = ""
                    else:
                        current += character
                stack.append(current)
                continue
            if candidate in known:
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

    def _format_signature(
        self, declaration: Any, kind: str = "Function"
    ) -> str:
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
        self.errors.append(
            TypeCheckError(
                message,
                source_name=source_name,
                line=line,
                column=column,
                notes=notes,
                helps=helps,
            )
        )
