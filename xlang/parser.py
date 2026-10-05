from __future__ import annotations

from typing import Any, Mapping

from .ast_nodes import (
    ArrayLiteral,
    Assignment,
    AwaitExpression,
    Binary,
    Block,
    BreakStatement,
    Call,
    ClassDeclaration,
    ClassicForStatement,
    DoWhileStatement,
    DefaultPattern,
    EnumDeclaration,
    ExpressionStatement,
    ForStatement,
    FunctionDeclaration,
    ImportDeclaration,
    Identifier,
    IfStatement,
    Index,
    Literal,
    LiteralPattern,
    MatchArm,
    MatchExpression,
    Member,
    NewExpression,
    NamespaceDeclaration,
    ObjectLiteral,
    OptionalChain,
    OptionalChainSegment,
    Parameter,
    Program,
    ReturnStatement,
    Spread,
    ArrayPattern,
    BindingPattern,
    EnumPattern,
    ObjectPattern,
    ThisExpression,
    TemplateLiteral,
    ThrowStatement,
    TryStatement,
    TypeDeclaration,
    UndefinedPattern,
    UndefinedLiteral,
    Unary,
    VariableDeclaration,
    WhileStatement,
    WildcardPattern,
)
from .lexer import Lexer, Token


class ParseError(Exception):
    def __init__(
        self, message: str, token: Token, source_name: str | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.token = token
        self.line = token.line
        self.column = token.column
        self.source_name = source_name


class Parser:
    PRECEDENCE = {
        "=": 1, "+=": 1, "-=": 1, "*=": 1, "/=": 1,
        "||": 2, "&&": 3,
        "==": 4, "!=": 4, "===": 4, "!==": 4,
        "<": 5, ">": 5, "<=": 5, ">=": 5, "in": 5,
        "+": 6, "-": 6,
        "*": 7, "/": 7, "%": 7,
    }

    def __init__(
        self,
        tokens: list[Token],
        features: Mapping[str, bool] | None = None,
        source_name: str | None = None,
        recover_errors: bool = False,
    ) -> None:
        self.tokens = tokens
        self.position = 0
        self.features = features or {}
        self.source_name = source_name
        self.in_async_function = False
        self.recover_errors = recover_errors
        self.errors: list[ParseError] = []

    def parse(self) -> Program:
        declarations: list[Any] = []
        while not self._check("EOF"):
            start_position = self.position
            try:
                declarations.append(self._declaration())
            except ParseError as error:
                if error.source_name is None:
                    error.source_name = self.source_name
                if not self.recover_errors:
                    raise
                self.errors.append(error)
                self._synchronize(start_position, stop_at_block_end=False)
        return Program(declarations)

    def _declaration(self) -> Any:
        start = self._peek()
        declaration = self._parse_declaration()
        return self._attach_location(declaration, start)

    def _parse_declaration(self) -> Any:
        decorators = self._decorators()
        if self._match("package"):
            if decorators:
                raise ParseError("Decorators cannot be applied to package declarations", self._peek())
            self._qualified_name()
            self._match(";")
            return None
        if self._match("import"):
            if decorators:
                raise ParseError("Decorators cannot be applied to imports", self._peek())
            return self._import_declaration()
        if self._match("namespace"):
            self._require_feature("namespaces", self._previous())
            if decorators:
                raise ParseError("Decorators cannot be applied to namespaces", self._peek())
            namespace_name = self._qualified_name()
            self._consume("{", "Expected '{' after namespace name")
            declarations: list[Any] = []
            while not self._check("}") and not self._check("EOF"):
                declarations.append(self._declaration())
            self._consume("}", "Expected '}' after namespace declarations")
            return NamespaceDeclaration(namespace_name, declarations)

        exported = self._match("export")
        modifiers = self._modifiers()
        if "final" in modifiers and not self._check("class"):
            raise ParseError(
                "'final' is supported only on class declarations",
                self._peek(),
                self.source_name,
            )
        if exported:
            modifiers.add("export")
        if self._match("class", "interface", "abstract"):
            self._require_feature("classes", self._previous())
            token = self._previous()
            if token.kind == "abstract":
                self._consume("class", "Expected 'class' after 'abstract'")
                modifiers.add("abstract")
                return self._class_declaration(modifiers, decorators=decorators)
            return self._class_declaration(
                modifiers,
                is_interface=token.kind == "interface",
                decorators=decorators,
            )
        if self._match("enum"):
            self._require_feature("enums", self._previous())
            if decorators:
                raise ParseError("Enum decorators are not implemented yet", self._peek())
            return self._enum_declaration(modifiers)
        if self._match("type"):
            if decorators:
                raise ParseError("Type-alias decorators are not implemented yet", self._peek())
            return self._type_declaration(modifiers)

        is_async = self._match("async")
        if is_async:
            self._require_feature("async", self._previous())
        return_type = None
        if self._match("function"):
            return self._function_declaration(modifiers, None, is_async, decorators)
        if self._looks_like_return_type_function():
            return_type = self._parse_type()
            self._consume("function", "Expected 'function' after return type")
            return self._function_declaration(
                modifiers, return_type, is_async, decorators
            )
        if is_async:
            raise ParseError("'async' must precede a function declaration", self._peek())
        if self._check("let") or self._check("const"):
            if decorators:
                raise ParseError("Variable decorators are not implemented yet", self._peek())
            declaration = self._variable_declaration(require_semicolon=True)
            return declaration
        if modifiers:
            raise ParseError("Expected a declaration after modifiers", self._peek())
        if exported:
            raise ParseError("'export' must precede a declaration", self._peek())
        if decorators:
            raise ParseError("Decorators must precede a declaration", self._peek())
        return self._statement()

    def _import_declaration(self) -> ImportDeclaration:
        parts = [self._consume("IDENTIFIER", "Expected import path").value]
        wildcard = False
        while self._match("."):
            if self._match("{"):
                targets: list[tuple[str, str | None]] = []
                while True:
                    imported_name = self._consume(
                        "IDENTIFIER", "Expected imported name"
                    ).value
                    alias = None
                    if self._match("as"):
                        alias = self._consume(
                            "IDENTIFIER", "Expected import alias"
                        ).value
                    module_path = ".".join(parts + [imported_name])
                    targets.append((module_path, alias))
                    if not self._match(","):
                        break
                self._consume("}", "Expected '}' after grouped imports")
                self._match(";")
                return ImportDeclaration(targets)
            if self._match("*"):
                wildcard = True
                break
            parts.append(
                self._consume("IDENTIFIER", "Expected name after '.'").value
            )
        alias = None
        if self._match("as"):
            alias = self._consume("IDENTIFIER", "Expected import alias").value
        self._match(";")
        if wildcard and alias is None and self._peek().kind not in (";", "EOF"):
            if not self._line_terminator_before_current():
                raise ParseError("Unexpected token after wildcard import", self._peek())
        return ImportDeclaration([(".".join(parts), alias)], wildcard)

    def _modifiers(self) -> set[str]:
        modifiers: set[str] = set()
        modifier_names = {
            "public", "private", "protected", "internal", "static", "virtual",
            "override", "abstract", "final",
        }
        while self._peek().kind in modifier_names:
            modifiers.add(self._advance().kind)
        return modifiers

    def _decorators(self) -> list[Any]:
        decorators: list[Any] = []
        while self._match("@"):
            self._require_feature("decorators", self._previous())
            parts = [self._consume("IDENTIFIER", "Expected decorator name").value]
            while self._match("."):
                parts.append(
                    self._consume("IDENTIFIER", "Expected name after decorator '.'").value
                )
            decorator: Any = Identifier(parts[0])
            for part in parts[1:]:
                decorator = Member(decorator, part)
            if self._match("("):
                decorator = Call(decorator, self._arguments_after_open_paren())
            decorators.append(decorator)
        return decorators

    def _class_declaration(
        self,
        modifiers: set[str],
        is_interface: bool = False,
        decorators: list[Any] | None = None,
    ) -> ClassDeclaration:
        if "final" in modifiers and is_interface:
            raise ParseError(
                "'final' can only be applied to a class", self._peek(), self.source_name
            )
        if "final" in modifiers and "abstract" in modifiers:
            raise ParseError(
                "A class cannot be both final and abstract",
                self._peek(),
                self.source_name,
            )
        name = self._consume("IDENTIFIER", "Expected a type name").value
        self._skip_generic_parameters()
        parent_name = None
        if self._match("extends"):
            parent_name = self._parse_type()
        if self._match("implements"):
            self._parse_type_list()
        self._consume("{", "Expected '{' before type body")
        members: list[Any] = []
        while not self._check("}") and not self._check("EOF"):
            members.append(self._class_member(name, is_interface))
        self._consume("}", "Expected '}' after type body")
        return ClassDeclaration(
            name, members, parent_name, modifiers, is_interface, decorators or []
        )

    def _class_member(self, class_name: str, is_interface: bool) -> Any:
        start = self._peek()
        member = self._parse_class_member(class_name, is_interface)
        return self._attach_location(member, start)

    def _parse_class_member(self, class_name: str, is_interface: bool) -> Any:
        decorators = self._decorators()
        modifiers = self._modifiers()
        visibility_modifiers = modifiers.intersection(
            {"private", "protected", "public", "internal"}
        )
        if "internal" in modifiers:
            raise ParseError(
                "'internal' access is not implemented; use public, protected, or private",
                self._peek(),
                self.source_name,
            )
        if len(visibility_modifiers) > 1:
            raise ParseError(
                "A class member can have only one access modifier",
                self._peek(),
                self.source_name,
            )
        if "final" in modifiers and not self._check("class"):
            raise ParseError(
                "'final' is currently supported only on classes",
                self._peek(),
                self.source_name,
            )
        is_async = self._match("async")
        if is_async:
            self._require_feature("async", self._previous())
        if self._match("class", "interface", "enum"):
            kind = self._previous().kind
            if kind == "enum":
                self._require_feature("enums", self._previous())
                return self._enum_declaration(modifiers)
            self._require_feature("classes", self._previous())
            return self._class_declaration(
                modifiers,
                is_interface=kind == "interface",
                decorators=decorators,
            )

        if self._check("IDENTIFIER") and self._peek().value == class_name and self._peek(1).kind == "(":
            self._advance()
            parameters = self._parameters()
            body = self._function_body(is_async=False)
            if is_async:
                raise ParseError("Constructors cannot be async", self._previous())
            declaration = FunctionDeclaration(
                class_name, parameters, body, None, modifiers
            )
            declaration.decorators = decorators
            return declaration

        type_name = self._parse_type()
        name = self._consume("IDENTIFIER", "Expected a member name").value
        if self._check("("):
            parameters = self._parameters()
            declaration_only = is_interface or "abstract" in modifiers
            if declaration_only and self._match(";"):
                body = []
            else:
                body = self._function_body(is_async)
            return FunctionDeclaration(
                name,
                parameters,
                body,
                type_name,
                modifiers,
                is_async=is_async,
                decorators=decorators,
            )
        if decorators:
            raise ParseError("Decorators can only be applied to methods and nested classes", self._peek())
        if self._match("{"):
            while not self._check("}") and not self._check("EOF"):
                if self._check("get") or self._check("set"):
                    self._advance()
                    self._match(";")
                else:
                    self._advance()
            self._consume("}", "Expected '}' after property")
            return VariableDeclaration(
                name, type_name, None, modifiers=modifiers
            )
        initializer = self._expression() if self._match("=") else None
        self._consume_statement_terminator("Expected ';' after field declaration")
        return VariableDeclaration(name, type_name, initializer, modifiers=modifiers)

    def _enum_declaration(self, modifiers: set[str]) -> EnumDeclaration:
        name = self._consume("IDENTIFIER", "Expected enum name").value
        self._consume("{", "Expected '{' before enum members")
        members: list[tuple[str, Any | None]] = []
        while not self._check("}") and not self._check("EOF"):
            member_name = self._consume("IDENTIFIER", "Expected enum member name").value
            value = self._expression() if self._match("=") else None
            members.append((member_name, value))
            if not self._match(",") and not self._check("}"):
                raise ParseError("Expected ',' or '}' after enum member", self._peek())
        self._consume("}", "Expected '}' after enum members")
        return EnumDeclaration(name, members, modifiers)

    def _type_declaration(self, modifiers: set[str]) -> TypeDeclaration:
        name = self._consume("IDENTIFIER", "Expected type alias name").value
        self._consume("=", "Expected '=' after type alias name")
        if self._match("{"):
            fields: list[str] = []
            while not self._check("}") and not self._check("EOF"):
                field_type = self._parse_type()
                field_name = self._consume("IDENTIFIER", "Expected field name").value
                fields.append(f"{field_type} {field_name}")
                self._consume_statement_terminator("Expected ';' after type field")
            self._consume("}", "Expected '}' after type fields")
            type_name = "record{" + ";".join(fields) + "}"
        else:
            type_name = self._parse_type()
        self._match(";")
        return TypeDeclaration(name, type_name, modifiers)

    def _function_declaration(
        self,
        modifiers: set[str],
        return_type: str | None,
        is_async: bool = False,
        decorators: list[Any] | None = None,
    ) -> FunctionDeclaration:
        generic_parameters: list[str] = []
        if self._match("<"):
            while True:
                generic_parameters.append(
                    self._consume("IDENTIFIER", "Expected generic parameter").value
                )
                if not self._match(","):
                    break
            self._consume(">", "Expected '>' after generic parameters")
            if return_type is None:
                return_type = self._parse_type()
        name = self._consume("IDENTIFIER", "Expected function name").value
        parameters = self._parameters()
        body = self._function_body(is_async)
        return FunctionDeclaration(
            name,
            parameters,
            body,
            return_type,
            modifiers,
            generic_parameters,
            is_async,
            decorators or [],
        )

    def _function_body(self, is_async: bool) -> list[Any]:
        previous_async_context = self.in_async_function
        self.in_async_function = is_async
        try:
            return self._block().statements
        finally:
            self.in_async_function = previous_async_context

    def _parameters(self) -> list[Parameter]:
        self._consume("(", "Expected '(' before parameters")
        parameters: list[Parameter] = []
        optional_parameter_seen = False
        if not self._check(")"):
            while True:
                first = self._parse_type()
                is_rest = self._match("...")
                if is_rest:
                    self._require_feature("spread", self._previous())
                name = None
                if self._check("IDENTIFIER"):
                    name = self._advance().value
                elif is_rest:
                    raise ParseError(
                        "Expected a name after rest parameter type", self._peek()
                    )
                else:
                    name = first
                    first = None

                has_default = self._match("=")
                if is_rest and has_default:
                    raise ParseError(
                        "Rest parameters cannot have default values", self._previous()
                    )
                default_value = self._expression() if has_default else None
                optional_parameter = has_default or (
                    first is not None and first.endswith("?")
                )
                if optional_parameter_seen and not (optional_parameter or is_rest):
                    raise ParseError(
                        "Required parameters cannot follow optional parameters",
                        self._peek(),
                    )
                optional_parameter_seen = optional_parameter_seen or optional_parameter
                parameters.append(
                    Parameter(name, first, is_rest, default_value, has_default)
                )
                if is_rest and not self._check(")"):
                    raise ParseError("Rest parameter must be last", self._peek())
                if not self._match(","):
                    break
        self._consume(")", "Expected ')' after parameters")
        return parameters

    def _variable_declaration(
        self,
        require_semicolon: bool,
        allow_uninitialized: bool = False,
    ) -> VariableDeclaration:
        constant = self._match("const")
        if not constant:
            self._consume("let", "Expected 'let' or 'const'")
        if self._check("[") or self._check("{"):
            self._require_feature("destructuring", self._peek())
            pattern = self._binding_pattern()
            initializer = self._expression() if self._match("=") else None
            if initializer is None and not allow_uninitialized:
                raise ParseError(
                    "A destructuring declaration needs an initial value", self._peek()
                )
            if require_semicolon:
                self._consume_statement_terminator("Expected ';' after variable declaration")
            return VariableDeclaration(
                "", None, initializer, constant=constant, pattern=pattern
            )
        first = self._consume("IDENTIFIER", "Expected variable name or type")
        type_suffix = ""
        type_name_parts = [first.value]
        while self._match("."):
            type_name_parts.append(
                self._consume("IDENTIFIER", "Expected type name after '.'").value
            )
        if self._match("<"):
            type_arguments = [self._parse_type()]
            while self._match(","):
                type_arguments.append(self._parse_type())
            self._consume(">", "Expected '>' after generic type arguments")
            type_suffix = "<" + ",".join(type_arguments) + ">"
        while self._match("["):
            self._consume("]", "Expected ']' in array type")
            type_suffix += "[]"
        if self._match("?"):
            type_suffix += "?"
        type_name = None
        name = ".".join(type_name_parts)
        if self._check("IDENTIFIER"):
            type_name = name + type_suffix
            name = self._advance().value
            while self._match("["):
                self._consume("]", "Expected ']' in array type")
                type_name += "[]"
            if self._match("?"):
                type_name += "?"
        initializer = self._expression() if self._match("=") else None
        if initializer is None and type_name is None and not allow_uninitialized:
            raise ParseError("A variable without a type needs an initial value", self._peek())
        if require_semicolon:
            self._consume_statement_terminator("Expected ';' after variable declaration")
        return VariableDeclaration(name, type_name, initializer, constant)

    def _binding_pattern(self) -> Any:
        self._require_feature("destructuring", self._peek())
        if self._match("["):
            items: list[Any] = []
            rest_name = None
            while not self._check("]") and not self._check("EOF"):
                if self._match("..."):
                    self._require_feature("spread", self._previous())
                    rest_name = self._consume(
                        "IDENTIFIER", "Expected name after array rest pattern"
                    ).value
                    if not self._check("]"):
                        raise ParseError("Array rest binding must be last", self._peek())
                    break
                items.append(self._binding_pattern_item())
                if not self._match(","):
                    break
            self._consume("]", "Expected ']' after array binding")
            return ArrayPattern(items, rest_name)
        if self._match("{"):
            fields: list[tuple[str, Any]] = []
            rest_name = None
            while not self._check("}") and not self._check("EOF"):
                if self._match("..."):
                    self._require_feature("spread", self._previous())
                    rest_name = self._consume(
                        "IDENTIFIER", "Expected name after object rest binding"
                    ).value
                    if not self._check("}"):
                        raise ParseError("Object rest binding must be last", self._peek())
                    break
                if self._match("STRING"):
                    field_name = self._previous().value
                else:
                    field_name = self._consume(
                        "IDENTIFIER", "Expected object binding field"
                    ).value
                if self._match(":"):
                    field_pattern = self._binding_pattern_item()
                else:
                    field_pattern = BindingPattern(field_name)
                fields.append((field_name, field_pattern))
                if not self._match(","):
                    break
            self._consume("}", "Expected '}' after object binding")
            return ObjectPattern(fields, rest_name)
        raise ParseError("Expected an array or object binding pattern", self._peek())

    def _binding_pattern_item(self) -> Any:
        if self._check("[") or self._check("{"):
            pattern = self._binding_pattern()
        else:
            name = self._consume("IDENTIFIER", "Expected binding name").value
            pattern = BindingPattern(name)
        if self._match("="):
            return DefaultPattern(pattern, self._expression())
        return pattern

    def _statement(self) -> Any:
        start = self._peek()
        statement = self._parse_statement()
        return self._attach_location(statement, start)

    def _parse_statement(self) -> Any:
        if self._match("{"):
            return Block(self._block_contents())
        is_async = False
        if self._match("async"):
            self._require_feature("async", self._previous())
            is_async = True
        if self._match("function"):
            return self._function_declaration(set(), None, is_async)
        if self._looks_like_return_type_function():
            return_type = self._parse_type()
            self._consume("function", "Expected 'function' after return type")
            return self._function_declaration(set(), return_type, is_async)
        if is_async:
            raise ParseError("'async' must precede a function declaration", self._peek())
        if self._match("enum"):
            self._require_feature("enums", self._previous())
            return self._enum_declaration(set())
        if self._match("let", "const"):
            self.position -= 1
            return self._variable_declaration(require_semicolon=True)
        if self._match("if"):
            self._consume("(", "Expected '(' after 'if'")
            condition = self._expression()
            self._consume(")", "Expected ')' after condition")
            then_branch = self._as_block(self._statement())
            else_branch = None
            if self._match("else"):
                if self._match("if"):
                    self.position -= 1
                    else_branch = self._statement()
                else:
                    else_branch = self._as_block(self._statement())
            return IfStatement(condition, then_branch, else_branch)
        if self._match("while"):
            self._require_feature("loops", self._previous())
            self._consume("(", "Expected '(' after 'while'")
            condition = self._expression()
            self._consume(")", "Expected ')' after condition")
            return WhileStatement(condition, self._as_block(self._statement()))
        if self._match("do"):
            self._require_feature("loops", self._previous())
            body = self._as_block(self._statement())
            self._consume("while", "Expected 'while' after do-while body")
            self._consume("(", "Expected '(' after 'while'")
            condition = self._expression()
            self._consume(")", "Expected ')' after do-while condition")
            self._consume_statement_terminator("Expected ';' after do-while loop")
            return DoWhileStatement(body, condition)
        if self._match("for"):
            self._require_feature("loops", self._previous())
            self._consume("(", "Expected '(' after 'for'")
            if self._check(";"):
                return self._classic_for_statement(None)
            if self._check("let") or self._check("const"):
                initializer = self._variable_declaration(
                    require_semicolon=False, allow_uninitialized=True
                )
                return self._parse_for_tail(initializer)
            if self._looks_like_typed_for_initializer():
                initializer = self._typed_for_initializer()
                return self._parse_for_tail(initializer)
            expression = self._expression()
            if self._match(";"):
                return self._classic_for_statement(expression)
            if self._match("of"):
                if not isinstance(expression, Identifier):
                    raise ParseError("For-in/of loop needs a variable name", self._previous())
                iterable = self._expression()
                self._consume(")", "Expected ')' after for-in/of loop")
                return ForStatement(
                    expression.name,
                    None,
                    iterable,
                    self._as_block(self._statement()),
                    iteration_mode="of",
                )
            raise ParseError("Expected ';', 'in', or 'of' in for loop", self._peek())

        if self._match("match"):
            self._require_feature("pattern_matching", self._previous())
            self.position -= 1
            expression = self._match_expression()
            return ExpressionStatement(expression)

        if self._match("return"):
            value = (
                None
                if self._check(";")
                or self._check("}")
                or self._check("EOF")
                or self._line_terminator_before_current()
                else self._expression()
            )
            self._consume_statement_terminator("Expected ';' after return")
            return ReturnStatement(value)
        if self._match("break", "continue"):
            self._require_feature("loops", self._previous())
            is_continue = self._previous().kind == "continue"
            self._consume_statement_terminator("Expected ';' after loop control statement")
            return BreakStatement(is_continue)
        if self._match("throw"):
            self._require_feature("exceptions", self._previous())
            if self._line_terminator_before_current():
                raise ParseError("A line break cannot follow 'throw'", self._peek())
            value = self._expression()
            self._consume_statement_terminator("Expected ';' after throw")
            return ThrowStatement(value)
        if self._match("try"):
            self._require_feature("exceptions", self._previous())
            body = self._as_block(self._statement())
            catches: list[tuple[str | None, str, Block]] = []
            while self._match("catch"):
                catch_types: list[str] = []
                catch_name = "error"
                if self._match("("):
                    first = self._parse_type()
                    if self._check("IDENTIFIER"):
                        catch_types.append(first)
                        while self._match("|"):
                            catch_types.append(self._parse_type())
                        catch_name = self._consume(
                            "IDENTIFIER", "Expected catch variable"
                        ).value
                    else:
                        catch_name = first
                    self._consume(")", "Expected ')' after catch parameter")
                catch_body = self._as_block(self._statement())
                catches.append(
                    ("|".join(catch_types) if catch_types else None, catch_name, catch_body)
                )
            finally_body = self._as_block(self._statement()) if self._match("finally") else None
            if not catches and finally_body is None:
                raise ParseError("A try statement needs catch or finally", self._peek())
            return TryStatement(body, catches, finally_body)
        if self._match(";"):
            return ExpressionStatement(Literal(None))
        expression = self._expression()
        self._consume_statement_terminator("Expected ';' after expression")
        return ExpressionStatement(expression)

    def _parse_for_tail(self, initializer: Any | None) -> Any:
        if self._match(";"):
            return self._classic_for_statement(initializer)
        if self._match("in", "of"):
            mode = self._previous().kind
            if not isinstance(initializer, VariableDeclaration):
                raise ParseError("For-in/of loop needs a variable declaration", self._peek())
            if mode == "in" and initializer.type_name is not None:
                mode = "legacy"
            iterable = self._expression()
            self._consume(")", "Expected ')' after for-in/of loop")
            return ForStatement(
                initializer.name,
                initializer.type_name,
                iterable,
                self._as_block(self._statement()),
                initializer.constant,
                mode,
                initializer.pattern,
            )
        raise ParseError("Expected ';', 'in', or 'of' in for loop", self._peek())

    def _typed_for_initializer(self) -> VariableDeclaration:
        type_name = self._parse_type()
        name = self._consume("IDENTIFIER", "Expected loop variable").value
        initializer = self._expression() if self._match("=") else None
        return VariableDeclaration(name, type_name, initializer)

    def _classic_for_statement(self, initializer: Any | None) -> ClassicForStatement:
        condition = None if self._check(";") else self._expression()
        self._consume(";", "Expected ';' after for-loop condition")
        increment = None if self._check(")") else self._expression()
        self._consume(")", "Expected ')' after for-loop clauses")
        body = self._as_block(self._statement())
        return ClassicForStatement(initializer, condition, increment, body)

    def _looks_like_typed_for_initializer(self) -> bool:
        if not self._check("IDENTIFIER"):
            return False
        return self._peek(1).kind == "IDENTIFIER" or (
            self._peek(1).kind == "[" and self._peek(2).kind == "]"
        )

    def _match_expression(self) -> MatchExpression:
        self._require_feature("pattern_matching", self._peek())
        self._consume("match", "Expected 'match'")
        value = self._expression()
        self._consume("{", "Expected '{' before match arms")
        arms: list[MatchArm] = []
        while not self._check("}") and not self._check("EOF"):
            pattern = self._pattern()
            guard = self._expression() if self._match("if") else None
            self._consume("=>", "Expected '=>' after pattern")
            if self._check("{"):
                body: Any = self._block()
            else:
                body = self._expression()
            arms.append(MatchArm(pattern, guard, body))
            if not self._match(",") and not self._check("}"):
                raise ParseError("Expected ',' between match arms", self._peek())
        self._consume("}", "Expected '}' after match arms")
        if not arms:
            raise ParseError("A match expression needs at least one arm", self._peek())
        return MatchExpression(value, arms)

    def _pattern(self) -> Any:
        patterns = [self._single_pattern()]
        while self._match("|"):
            patterns.append(self._single_pattern())
        if len(patterns) == 1:
            return patterns[0]
        return ("or", patterns)

    def _single_pattern(self) -> Any:
        if self._match("NUMBER"):
            text = self._previous().value
            return LiteralPattern(float(text) if "." in text else int(text))
        if self._match("STRING"):
            return LiteralPattern(self._previous().value)
        if self._match("true"):
            return LiteralPattern(True)
        if self._match("false"):
            return LiteralPattern(False)
        if self._match("null", "Null"):
            return LiteralPattern(None)
        if self._match("undefined", "Undefined"):
            return UndefinedPattern()
        if self._match("["):
            items: list[Any] = []
            rest_name = None
            while not self._check("]") and not self._check("EOF"):
                if self._match("..."):
                    self._require_feature("spread", self._previous())
                    rest_name = self._consume(
                        "IDENTIFIER", "Expected name after array rest pattern"
                    ).value
                    break
                items.append(self._pattern())
                if not self._match(","):
                    break
            self._consume("]", "Expected ']' after array pattern")
            return ArrayPattern(items, rest_name)
        if self._match("{"):
            fields: list[tuple[str, Any]] = []
            rest_name = None
            while not self._check("}") and not self._check("EOF"):
                if self._match("..."):
                    self._require_feature("spread", self._previous())
                    rest_name = self._consume(
                        "IDENTIFIER", "Expected name after object rest pattern"
                    ).value
                    if not self._check("}"):
                        raise ParseError("Object rest pattern must be last", self._peek())
                    break
                name = self._consume("IDENTIFIER", "Expected object pattern field").value
                if self._match(":"):
                    pattern = self._pattern()
                else:
                    pattern = BindingPattern(name)
                fields.append((name, pattern))
                if not self._match(","):
                    break
            self._consume("}", "Expected '}' after object pattern")
            return ObjectPattern(fields, rest_name)
        if self._match("IDENTIFIER"):
            name = self._previous().value
            if name == "_":
                return WildcardPattern()
            if self._match("."):
                member = self._consume("IDENTIFIER", "Expected enum member").value
                return EnumPattern(name, member)
            return BindingPattern(name)
        raise ParseError("Expected a supported match pattern", self._peek())

    def _block(self) -> Block:
        self._consume("{", "Expected '{' before block")
        return Block(self._block_contents())

    def _block_contents(self) -> list[Any]:
        statements: list[Any] = []
        while not self._check("}") and not self._check("EOF"):
            start_position = self.position
            try:
                statements.append(self._statement())
            except ParseError as error:
                if error.source_name is None:
                    error.source_name = self.source_name
                if not self.recover_errors:
                    raise
                self.errors.append(error)
                self._synchronize(start_position, stop_at_block_end=True)
        if self._check("EOF"):
            raise ParseError(
                "Unexpected end of file; expected '}' to close block",
                self._peek(),
                self.source_name,
            )
        self._consume("}", "Expected '}' after block")
        return statements

    def _synchronize(self, start_position: int, stop_at_block_end: bool) -> None:
        if self.position <= start_position and not self._check("EOF"):
            if not (stop_at_block_end and self._check("}")):
                self._advance()
        while not self._check("EOF"):
            if stop_at_block_end and self._check("}"):
                return
            if self._check(";"):
                self._advance()
                return
            if self.position > start_position:
                previous = self.tokens[self.position - 1]
                current = self._peek()
                if current.line > previous.line:
                    return
            self._advance()

    def _as_block(self, statement: Any) -> Block:
        if isinstance(statement, Block):
            return statement
        return Block([statement])

    def _expression(self, minimum_precedence: int = 1) -> Any:
        expression = self._unary()
        while True:
            operator = self._peek().kind
            precedence = self.PRECEDENCE.get(operator, 0)
            if precedence < minimum_precedence:
                break
            if operator in {"==", "!=", "===", "!=="}:
                self._require_feature("equality", self._peek())
            self._advance()
            next_precedence = precedence if precedence == 1 else precedence + 1
            right = self._expression(next_precedence)
            if precedence == 1:
                if operator == "=" and isinstance(expression, (ArrayLiteral, ObjectLiteral)):
                    expression = self._assignment_pattern(expression)
                expression = Assignment(expression, operator, right)
            else:
                expression = Binary(expression, operator, right)
        if minimum_precedence == 1 and self._match("?"):
            true_value = self._expression()
            self._consume(":", "Expected ':' in conditional expression")
            false_value = self._expression()
            expression = Binary(expression, "?:", (true_value, false_value))
        return expression

    def _assignment_pattern(self, expression: Any) -> Any:
        if isinstance(expression, ArrayLiteral):
            items: list[Any] = []
            rest_name = None
            for item in expression.items:
                if isinstance(item, Spread):
                    if not isinstance(item.value, Identifier):
                        raise ParseError("Array rest assignment needs a variable", self._peek())
                    rest_name = item.value.name
                    if item is not expression.items[-1]:
                        raise ParseError("Array rest assignment must be last", self._peek())
                elif isinstance(item, Identifier):
                    items.append(BindingPattern(item.name))
                elif isinstance(item, (ArrayLiteral, ObjectLiteral)):
                    items.append(self._assignment_pattern(item))
                else:
                    raise ParseError(
                        "Destructuring assignment targets must be variables or patterns",
                        self._peek(),
                    )
            return ArrayPattern(items, rest_name)
        if isinstance(expression, ObjectLiteral):
            fields: list[tuple[str, Any]] = []
            rest_name = None
            for key, target in expression.entries:
                if key is None and isinstance(target, Spread):
                    if not isinstance(target.value, Identifier):
                        raise ParseError("Object rest assignment needs a variable", self._peek())
                    rest_name = target.value.name
                    if expression.entries[-1] != (key, target):
                        raise ParseError("Object rest assignment must be last", self._peek())
                    continue
                if key is None:
                    raise ParseError("Invalid object destructuring assignment", self._peek())
                if isinstance(target, Identifier):
                    target_pattern = BindingPattern(target.name)
                elif isinstance(target, (ArrayLiteral, ObjectLiteral)):
                    target_pattern = self._assignment_pattern(target)
                else:
                    raise ParseError(
                        "Object destructuring targets must be variables or patterns",
                        self._peek(),
                    )
                fields.append((key, target_pattern))
            return ObjectPattern(fields, rest_name)
        return expression

    def _unary(self) -> Any:
        if self._match("!", "-", "+", "++", "--"):
            operator = self._previous().kind
            return Unary(operator, self._unary())
        expression = self._primary()
        chain_segments: list[OptionalChainSegment] = []
        optional_chain_started = False
        chain_object = expression
        while True:
            if self._check("<") and self._looks_like_generic_call():
                self._advance()
                type_arguments = [self._parse_type()]
                while self._match(","):
                    type_arguments.append(self._parse_type())
                self._consume(">", "Expected '>' after generic call types")
                self._consume("(", "Expected '(' after generic call types")
                arguments = self._arguments_after_open_paren()
                if optional_chain_started:
                    chain_segments.append(
                        OptionalChainSegment(
                            "call", (arguments, type_arguments)
                        )
                    )
                else:
                    expression = Call(expression, arguments, type_arguments)
            elif self._match("("):
                arguments = self._arguments_after_open_paren()
                if optional_chain_started:
                    chain_segments.append(
                        OptionalChainSegment("call", (arguments, []))
                    )
                else:
                    expression = Call(expression, arguments)
            elif self._match("?."):
                optional_chain_started = True
                if not chain_segments:
                    chain_object = expression
                if self._match("("):
                    chain_segments.append(
                        OptionalChainSegment(
                            "call",
                            (self._arguments_after_open_paren(), []),
                            optional=True,
                        )
                    )
                else:
                    name = self._consume(
                        "IDENTIFIER", "Expected member name after '?.'"
                    ).value
                    chain_segments.append(
                        OptionalChainSegment("member", name, optional=True)
                    )
            elif self._match("?["):
                optional_chain_started = True
                if not chain_segments:
                    chain_object = expression
                index = self._expression()
                self._consume("]", "Expected ']' after optional index")
                chain_segments.append(
                    OptionalChainSegment("index", index, optional=True)
                )
            elif self._match("."):
                name = self._consume("IDENTIFIER", "Expected member name after '.'").value
                if optional_chain_started:
                    chain_segments.append(OptionalChainSegment("member", name))
                else:
                    expression = Member(expression, name)
            elif self._match("["):
                index = self._expression()
                self._consume("]", "Expected ']' after index")
                if optional_chain_started:
                    chain_segments.append(OptionalChainSegment("index", index))
                else:
                    expression = Index(expression, index)
            elif (
                not self._line_terminator_before_current()
                and self._match("++", "--")
            ):
                if optional_chain_started:
                    expression = OptionalChain(chain_object, chain_segments)
                expression = Unary(self._previous().kind, expression, postfix=True)
                optional_chain_started = False
                chain_segments = []
            else:
                break
        if optional_chain_started:
            expression = OptionalChain(chain_object, chain_segments)
        return expression

    def _primary(self) -> Any:
        if self._match("false"):
            return Literal(False)
        if self._match("true"):
            return Literal(True)
        if self._match("null", "Null"):
            return Literal(None)
        if self._match("undefined", "Undefined"):
            return UndefinedLiteral()
        if self._match("NUMBER"):
            text = self._previous().value
            return Literal(float(text) if "." in text else int(text))
        if self._match("STRING"):
            return Literal(self._previous().value)
        if self._match("TEMPLATE_STRING"):
            return self._parse_template_literal(self._previous())
        if self._match("this"):
            return ThisExpression()
        if self._match("super"):
            return ThisExpression(is_super=True)
        if self._match("new"):
            self._require_feature("classes", self._previous())
            class_name = self._parse_type()
            self._consume("(", "Expected '(' after type name")
            return NewExpression(class_name, self._arguments_after_open_paren())
        if self._match("match"):
            self._require_feature("pattern_matching", self._previous())
            self.position -= 1
            return self._match_expression()
        if self._match("IDENTIFIER"):
            return Identifier(self._previous().value)
        if self._match("("):
            expression = self._expression()
            self._consume(")", "Expected ')' after expression")
            return expression
        if self._match("["):
            items: list[Any] = []
            if not self._check("]"):
                while True:
                    if self._match("..."):
                        self._require_feature("spread", self._previous())
                        items.append(Spread(self._expression()))
                    else:
                        items.append(self._expression())
                    if not self._match(","):
                        break
            self._consume("]", "Expected ']' after array literal")
            return ArrayLiteral(items)
        if self._match("{"):
            self._require_feature("object_literals", self._previous())
            entries: list[tuple[str | None, Any]] = []
            while not self._check("}") and not self._check("EOF"):
                if self._match("..."):
                    self._require_feature("spread", self._previous())
                    entries.append((None, Spread(self._expression())))
                    if not self._match(","):
                        break
                    continue
                if self._match("STRING"):
                    key = self._previous().value
                    self._consume(":", "Expected ':' after object field name")
                    entries.append((key, self._expression()))
                else:
                    key = self._consume(
                        "IDENTIFIER", "Expected object field name"
                    ).value
                    if self._match(":"):
                        entries.append((key, self._expression()))
                    else:
                        entries.append((key, Identifier(key)))
                if not self._match(","):
                    break
            self._consume("}", "Expected '}' after object literal")
            return ObjectLiteral(entries)
        if self._match("..."):
            self._require_feature("spread", self._previous())
            return Spread(self._expression())
        if self._match("await"):
            self._require_feature("async", self._previous())
            if not self.in_async_function:
                raise ParseError(
                    "'await' is only valid inside an async function",
                    self._previous(),
                    self.source_name,
                )
            return AwaitExpression(self._unary())
        token = self._peek()
        token_description = repr(token.value) if token.value else repr(token.kind)
        raise ParseError(
            f"Unexpected token {token_description}; expected an expression",
            token,
            self.source_name,
        )

    def _parse_template_literal(self, token: Token) -> TemplateLiteral:
        raw = token.value
        parts: list[str | Any] = []
        text: list[str] = []
        position = 0

        def flush_text() -> None:
            if text:
                parts.append("".join(text))
                text.clear()

        while position < len(raw):
            if raw.startswith("{{", position):
                text.append("{")
                position += 2
                continue
            if raw.startswith("}}", position):
                text.append("}")
                position += 2
                continue
            if raw[position] != "{":
                text.append(raw[position])
                position += 1
                continue

            flush_text()
            expression_start = position + 1
            expression_end = self._template_expression_end(
                raw, expression_start, token
            )
            expression_source = raw[expression_start:expression_end]
            if not expression_source.strip():
                line, column = self._template_source_position(
                    raw, expression_start, token
                )
                raise ParseError(
                    "Template interpolation cannot be empty",
                    Token("{", "{", line, column),
                    self.source_name,
                )
            line, column = self._template_source_position(
                raw, expression_start, token
            )
            expression_tokens = Lexer(
                expression_source,
                self.source_name,
                initial_line=line,
                initial_column=column,
            ).tokenize()
            expression_parser = Parser(
                expression_tokens, self.features, self.source_name
            )
            expression = expression_parser._expression()
            if not expression_parser._check("EOF"):
                raise ParseError(
                    "Expected '}' after template expression",
                    expression_parser._peek(),
                    self.source_name,
                )
            parts.append(expression)
            position = expression_end + 1

        flush_text()
        return TemplateLiteral(parts)

    def _template_expression_end(
        self, raw: str, start: int, token: Token
    ) -> int:
        depth = 1
        quote: str | None = None
        escaped = False
        line_comment = False
        block_comment = False
        position = start
        while position < len(raw):
            character = raw[position]
            following = raw[position + 1] if position + 1 < len(raw) else ""
            if line_comment:
                if character == "\n":
                    line_comment = False
            elif block_comment:
                if character == "*" and following == "/":
                    block_comment = False
                    position += 1
            elif quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in ("'", '"', "`"):
                quote = character
            elif character == "/" and following == "/":
                line_comment = True
                position += 1
            elif character == "/" and following == "*":
                block_comment = True
                position += 1
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return position
            position += 1

        line, column = self._template_source_position(raw, start - 1, token)
        raise ParseError(
            "Unterminated template interpolation",
            Token("{", "{", line, column),
            self.source_name,
        )

    def _template_source_position(
        self, raw: str, offset: int, token: Token
    ) -> tuple[int, int]:
        line = token.line
        column = token.column + 1
        for character in raw[:offset]:
            if character == "\n":
                line += 1
                column = 1
            else:
                column += 1
        return line, column

    def _arguments_after_open_paren(self) -> list[Any]:
        arguments: list[Any] = []
        if not self._check(")"):
            while True:
                if self._match("..."):
                    self._require_feature("spread", self._previous())
                    arguments.append(Spread(self._expression()))
                else:
                    arguments.append(self._expression())
                if not self._match(","):
                    break
        self._consume(")", "Expected ')' after arguments")
        return arguments

    def _parse_type(self) -> str:
        if self._match("void"):
            type_name = "void"
        else:
            type_name = self._qualified_name()
            if self._match("<"):
                arguments: list[str] = []
                while True:
                    arguments.append(self._parse_type())
                    if not self._match(","):
                        break
                self._consume(">", "Expected '>' after generic types")
                type_name += "<" + ",".join(arguments) + ">"
        while self._match("["):
            self._consume("]", "Expected ']' in array type")
            type_name += "[]"
        if self._match("?"):
            type_name += "?"
        if self._match("|"):
            type_name += "|" + self._parse_type()
        return type_name

    def _qualified_name(self) -> str:
        parts = [self._consume("IDENTIFIER", "Expected a name").value]
        while self._match("."):
            if self._match("*"):
                parts.append("*")
                break
            parts.append(self._consume("IDENTIFIER", "Expected name after '.'").value)
        return ".".join(parts)

    def _parse_type_list(self) -> None:
        self._parse_type()
        while self._match(","):
            self._parse_type()

    def _skip_generic_parameters(self) -> None:
        if not self._match("<"):
            return
        depth = 1
        while depth and not self._check("EOF"):
            if self._match("<"):
                depth += 1
            elif self._match(">"):
                depth -= 1
            else:
                self._advance()

    def _looks_like_generic_call(self) -> bool:
        if self._peek().kind != "<":
            return False
        depth = 0
        offset = 0
        while True:
            kind = self._peek(offset).kind
            if kind == "EOF":
                return False
            if kind == "<":
                depth += 1
            elif kind == ">":
                depth -= 1
                if depth == 0:
                    return self._peek(offset + 1).kind == "("
            offset += 1

    def _looks_like_return_type_function(self) -> bool:
        offset = 0
        if not self._check("IDENTIFIER") and not self._check("void"):
            return False
        while self._peek(offset).kind == "IDENTIFIER":
            offset += 1
            while self._peek(offset).kind == ".":
                offset += 2
            if self._peek(offset).kind == "<":
                depth = 0
                while True:
                    kind = self._peek(offset).kind
                    if kind == "EOF":
                        return False
                    if kind == "<":
                        depth += 1
                    elif kind == ">":
                        depth -= 1
                        if depth == 0:
                            offset += 1
                            break
                    offset += 1
            while self._peek(offset).kind == "[" and self._peek(offset + 1).kind == "]":
                offset += 2
            if self._peek(offset).kind == "?":
                offset += 1
            if self._peek(offset).kind == "|":
                offset += 1
                continue
            break
        return self._peek(offset).kind == "function"

    def _consume(self, kind: str, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        raise ParseError(message, self._peek())

    def _line_terminator_before_current(self) -> bool:
        return self.position > 0 and self._peek().line > self._previous().line

    def _consume_statement_terminator(self, message: str) -> None:
        if self._match(";"):
            return
        if self._check("}") or self._check("EOF") or self._line_terminator_before_current():
            return
        raise ParseError(message, self._peek())

    def _require_feature(self, feature_name: str, token: Token) -> None:
        if not self.features.get(feature_name, True):
            raise ParseError(
                f"Language feature '{feature_name}' is disabled in x.toml",
                token,
                self.source_name,
            )

    def _attach_location(self, node: Any, token: Token) -> Any:
        if node is None:
            return None
        node.line = token.line
        node.column = token.column
        node.source_name = self.source_name
        return node

    def _match(self, *kinds: str) -> bool:
        if self._peek().kind in kinds:
            self._advance()
            return True
        return False

    def _check(self, kind: str) -> bool:
        return self._peek().kind == kind

    def _advance(self) -> Token:
        if not self._check("EOF"):
            self.position += 1
        return self._previous()

    def _peek(self, offset: int = 0) -> Token:
        index = min(self.position + offset, len(self.tokens) - 1)
        return self.tokens[index]

    def _previous(self) -> Token:
        return self.tokens[self.position - 1]
