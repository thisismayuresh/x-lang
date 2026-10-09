from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Program:
    declarations: list[Any]
    modules: dict[str, list[Any]] = field(default_factory=dict)


@dataclass
class TemplateLiteral:
    parts: list[str | Any]


@dataclass
class UndefinedLiteral:
    pass


@dataclass
class ImportDeclaration:
    targets: list[tuple[str, str | None]]
    wildcard: bool = False
    # `import B.greet("Maya")` is an import plus an immediate call: the parser
    # stores the ExpressionStatement to run here, after the import is bound.
    statement: Any | None = None


@dataclass
class ImportCall:
    """The imported target invoked inline: the callee of ``import B.greet(...)``.

    Only ever produced by the import parser; resolving it goes through the
    same import resolution a plain ``import B.greet`` uses.
    """

    # NB: not ``source_name`` — every located node carries ``source_name``
    # for diagnostics, and the parser overwrites it with the file name.
    import_path: str
    alias: str | None
    arguments: list[Any]


@dataclass
class ImportAlias:
    source_name: str
    alias_name: str


@dataclass
class ImportNamespaceAlias:
    exported_names: list[str]
    alias_name: str


@dataclass
class NamespaceDeclaration:
    name: str
    declarations: list[Any]


@dataclass
class Parameter:
    name: str
    type_name: str | None
    is_rest: bool = False
    default_value: Any | None = None
    has_default: bool = False


@dataclass
class FunctionDeclaration:
    name: str
    parameters: list[Parameter]
    body: list[Any]
    return_type: str | None = None
    modifiers: set[str] = field(default_factory=set)
    generic_parameters: list[str] = field(default_factory=list)
    is_async: bool = False
    decorators: list[Any] = field(default_factory=list)


@dataclass
class VariableDeclaration:
    name: str
    type_name: str | None
    initializer: Any | None
    constant: bool = False
    modifiers: set[str] = field(default_factory=set)
    pattern: Any | None = None


@dataclass
class ClassDeclaration:
    name: str
    members: list[Any]
    parent_name: str | None = None
    modifiers: set[str] = field(default_factory=set)
    is_interface: bool = False
    decorators: list[Any] = field(default_factory=list)
    implemented_types: list[str] = field(default_factory=list)
    generic_parameters: list[str] = field(default_factory=list)


@dataclass
class FunctionExpression:
    """An anonymous function: an arrow function such as ``(User u) => u.name``."""

    parameters: list[Parameter]
    body: list[Any]
    return_type: str | None = None
    is_async: bool = False
    is_arrow: bool = False


@dataclass
class ModuleImport:
    module_key: str
    kind: str
    source_name: str
    alias: str | None = None
    exported_names: list[str] = field(default_factory=list)


@dataclass
class EnumDeclaration:
    name: str
    members: list[tuple[str, Any | None]]
    modifiers: set[str] = field(default_factory=set)


@dataclass
class TypeDeclaration:
    name: str
    type_name: str
    modifiers: set[str] = field(default_factory=set)


@dataclass
class Block:
    statements: list[Any]


@dataclass
class ExpressionStatement:
    expression: Any


@dataclass
class IfStatement:
    condition: Any
    then_branch: Block
    else_branch: Any | None


@dataclass
class WhileStatement:
    condition: Any
    body: Block


@dataclass
class DoWhileStatement:
    body: Block
    condition: Any


@dataclass
class ForStatement:
    variable: str
    type_name: str | None
    iterable: Any
    body: Block
    constant: bool = False
    iteration_mode: str = "legacy"
    binding_pattern: Any | None = None


@dataclass
class ClassicForStatement:
    initializer: Any | None
    condition: Any | None
    increment: Any | None
    body: Block


@dataclass
class MatchArm:
    pattern: Any
    guard: Any | None
    body: Any


@dataclass
class MatchExpression:
    value: Any
    arms: list[MatchArm]


@dataclass
class WildcardPattern:
    pass


@dataclass
class BindingPattern:
    name: str


@dataclass
class LiteralPattern:
    value: Any


@dataclass
class UndefinedPattern:
    pass


@dataclass
class EnumPattern:
    enum_name: str
    member_name: str


@dataclass
class ArrayPattern:
    items: list[Any]
    rest_name: str | None = None


@dataclass
class ObjectPattern:
    fields: list[tuple[str, Any]]
    rest_name: str | None = None


@dataclass
class DefaultPattern:
    pattern: Any
    default_value: Any


@dataclass
class ReturnStatement:
    value: Any | None


@dataclass
class BreakStatement:
    is_continue: bool = False


@dataclass
class ThrowStatement:
    value: Any


@dataclass
class ResourceBinding:
    """One ``try (let name = expression)`` resource declaration."""

    name: str
    type_name: str | None
    value: Any
    constant: bool = False


@dataclass
class TryStatement:
    body: Block
    catches: list[tuple[str | None, str, Block]]
    finally_body: Block | None
    resources: list[ResourceBinding] = field(default_factory=list)


@dataclass
class SwitchCase:
    value: Any | None  # None for default case
    body: Block


@dataclass
class SwitchStatement:
    expression: Any
    cases: list[SwitchCase]


@dataclass
class Literal:
    value: Any


@dataclass
class Identifier:
    name: str


@dataclass
class ArrayLiteral:
    items: list[Any]


@dataclass
class ObjectLiteral:
    entries: list[tuple[str | None, Any]]


@dataclass
class Spread:
    value: Any


@dataclass
class AwaitExpression:
    value: Any


@dataclass
class Unary:
    operator: str
    operand: Any
    postfix: bool = False


@dataclass
class Binary:
    left: Any
    operator: str
    right: Any


@dataclass
class Assignment:
    target: Any
    operator: str
    value: Any


@dataclass
class Call:
    callee: Any
    arguments: list[Any]
    type_arguments: list[str] = field(default_factory=list)


@dataclass
class Member:
    object: Any
    name: str


@dataclass
class Index:
    object: Any
    index: Any


@dataclass
class OptionalChainSegment:
    kind: str
    value: Any
    optional: bool = False


@dataclass
class OptionalChain:
    object: Any
    segments: list[OptionalChainSegment]


@dataclass
class NewExpression:
    class_name: str
    arguments: list[Any]


@dataclass
class ThisExpression:
    is_super: bool = False
