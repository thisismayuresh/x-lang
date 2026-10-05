from __future__ import annotations

from typing import Any

from .ast_nodes import (
    ArrayLiteral,
    Assignment,
    Binary,
    Block,
    BreakStatement,
    Call,
    ClassDeclaration,
    EnumDeclaration,
    ExpressionStatement,
    ForStatement,
    FunctionDeclaration,
    ImportDeclaration,
    Identifier,
    IfStatement,
    Index,
    Literal,
    Member,
    NewExpression,
    ObjectLiteral,
    Parameter,
    Program,
    ReturnStatement,
    ThisExpression,
    ThrowStatement,
    TryStatement,
    TypeDeclaration,
    Unary,
    VariableDeclaration,
    WhileStatement,
)
from .lexer import Token


class ParseError(Exception):
    def __init__(self, message: str, token: Token) -> None:
        super().__init__(f"{token.line}:{token.column}: {message}")
        self.token = token


class Parser:
    PRECEDENCE = {
        "=": 1, "+=": 1, "-=": 1, "*=": 1, "/=": 1,
        "||": 2, "&&": 3,
        "==": 4, "!=": 4,
        "<": 5, ">": 5, "<=": 5, ">=": 5, "in": 5,
        "+": 6, "-": 6,
        "*": 7, "/": 7, "%": 7,
    }

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.position = 0

    def parse(self) -> Program:
        declarations: list[Any] = []
        while not self._check("EOF"):
            declarations.append(self._declaration())
        return Program(declarations)

    def _declaration(self) -> Any:
        if self._match("package"):
            self._qualified_name()
            self._match(";")
            return None
        if self._match("import"):
            return self._import_declaration()

        exported = self._match("export")
        modifiers = self._modifiers()
        if exported:
            modifiers.add("export")
        if self._match("class", "interface", "abstract"):
            token = self._previous()
            if token.kind == "abstract":
                self._consume("class", "Expected 'class' after 'abstract'")
                modifiers.add("abstract")
                return self._class_declaration(modifiers)
            return self._class_declaration(modifiers, is_interface=token.kind == "interface")
        if self._match("enum"):
            return self._enum_declaration(modifiers)
        if self._match("type"):
            return self._type_declaration(modifiers)

        return_type = None
        if self._match("function"):
            return self._function_declaration(modifiers, None)
        if self._looks_like_return_type_function():
            return_type = self._parse_type()
            self._consume("function", "Expected 'function' after return type")
            return self._function_declaration(modifiers, return_type)
        if self._check("let") or self._check("const"):
            declaration = self._variable_declaration(require_semicolon=True)
            return declaration
        if modifiers:
            raise ParseError("Expected a declaration after modifiers", self._peek())
        if exported:
            raise ParseError("'export' must precede a declaration", self._peek())
        raise ParseError("Expected a declaration", self._peek())

    def _import_declaration(self) -> ImportDeclaration:
        parts = [self._consume("IDENTIFIER", "Expected import path").value]
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
                self._match(";")
                raise ParseError(
                    "Wildcard imports are not supported by this interpreter yet",
                    self._previous(),
                )
            parts.append(
                self._consume("IDENTIFIER", "Expected name after '.'").value
            )
        alias = None
        if self._match("as"):
            alias = self._consume("IDENTIFIER", "Expected import alias").value
        self._match(";")
        return ImportDeclaration([(".".join(parts), alias)])

    def _modifiers(self) -> set[str]:
        modifiers: set[str] = set()
        modifier_names = {"public", "private", "protected", "internal", "static", "virtual", "override", "abstract"}
        while self._peek().kind in modifier_names:
            modifiers.add(self._advance().kind)
        return modifiers

    def _class_declaration(
        self, modifiers: set[str], is_interface: bool = False
    ) -> ClassDeclaration:
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
        return ClassDeclaration(name, members, parent_name, modifiers, is_interface)

    def _class_member(self, class_name: str, is_interface: bool) -> Any:
        modifiers = self._modifiers()
        if self._match("class", "interface", "enum"):
            kind = self._previous().kind
            if kind == "enum":
                return self._enum_declaration(modifiers)
            return self._class_declaration(modifiers, is_interface=kind == "interface")

        if self._check("IDENTIFIER") and self._peek().value == class_name and self._peek(1).kind == "(":
            self._advance()
            parameters = self._parameters()
            body = self._block().statements
            return FunctionDeclaration(class_name, parameters, body, None, modifiers)

        type_name = self._parse_type()
        name = self._consume("IDENTIFIER", "Expected a member name").value
        if self._check("("):
            parameters = self._parameters()
            body = [] if is_interface and self._match(";") else self._block().statements
            return FunctionDeclaration(name, parameters, body, type_name, modifiers)
        if self._match("{"):
            while not self._check("}") and not self._check("EOF"):
                if self._check("get") or self._check("set"):
                    self._advance()
                    self._match(";")
                else:
                    self._advance()
            self._consume("}", "Expected '}' after property")
            return VariableDeclaration(name, type_name, None)
        initializer = self._expression() if self._match("=") else None
        self._consume(";", "Expected ';' after field declaration")
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
                self._consume(";", "Expected ';' after type field")
            self._consume("}", "Expected '}' after type fields")
            type_name = "record{" + ";".join(fields) + "}"
        else:
            type_name = self._parse_type()
        self._match(";")
        return TypeDeclaration(name, type_name, modifiers)

    def _function_declaration(
        self, modifiers: set[str], return_type: str | None
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
        body = self._block().statements
        return FunctionDeclaration(name, parameters, body, return_type, modifiers, generic_parameters)

    def _parameters(self) -> list[Parameter]:
        self._consume("(", "Expected '(' before parameters")
        parameters: list[Parameter] = []
        if not self._check(")"):
            while True:
                first = self._parse_type()
                if self._check("IDENTIFIER"):
                    name = self._advance().value
                    parameters.append(Parameter(name, first))
                else:
                    parameters.append(Parameter(first, None))
                if not self._match(","):
                    break
        self._consume(")", "Expected ')' after parameters")
        return parameters

    def _variable_declaration(self, require_semicolon: bool) -> VariableDeclaration:
        constant = self._match("const")
        if not constant:
            self._consume("let", "Expected 'let' or 'const'")
        first = self._consume("IDENTIFIER", "Expected variable name or type")
        type_suffix = ""
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
        name = first.value
        if self._check("IDENTIFIER"):
            type_name = name + type_suffix
            name = self._advance().value
            while self._match("["):
                self._consume("]", "Expected ']' in array type")
                type_name += "[]"
            if self._match("?"):
                type_name += "?"
        initializer = self._expression() if self._match("=") else None
        if initializer is None and type_name is None:
            raise ParseError("A variable without a type needs an initial value", self._peek())
        if require_semicolon:
            self._consume(";", "Expected ';' after variable declaration")
        return VariableDeclaration(name, type_name, initializer, constant)

    def _statement(self) -> Any:
        if self._match("{"):
            return Block(self._block_contents())
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
            self._consume("(", "Expected '(' after 'while'")
            condition = self._expression()
            self._consume(")", "Expected ')' after condition")
            return WhileStatement(condition, self._as_block(self._statement()))
        if self._match("for"):
            self._consume("(", "Expected '(' after 'for'")
            first = self._parse_type()
            if self._match("in"):
                type_name = None
                variable_name = first
            else:
                type_name = first
                variable_name = self._consume("IDENTIFIER", "Expected loop variable").value
                self._consume("in", "Expected 'in' in for loop")
            iterable = self._expression()
            self._consume(")", "Expected ')' after for loop")
            return ForStatement(variable_name, type_name, iterable, self._as_block(self._statement()))
        if self._match("return"):
            value = None if self._check(";") else self._expression()
            self._consume(";", "Expected ';' after return")
            return ReturnStatement(value)
        if self._match("break", "continue"):
            is_continue = self._previous().kind == "continue"
            self._consume(";", "Expected ';' after loop control statement")
            return BreakStatement(is_continue)
        if self._match("throw"):
            value = self._expression()
            self._consume(";", "Expected ';' after throw")
            return ThrowStatement(value)
        if self._match("try"):
            body = self._as_block(self._statement())
            catches: list[tuple[str | None, str, Block]] = []
            while self._match("catch"):
                self._consume("(", "Expected '(' after 'catch'")
                first = self._parse_type()
                if self._check("IDENTIFIER"):
                    catch_name = self._advance().value
                    catch_type = first
                else:
                    catch_name = "error"
                    catch_type = None
                self._consume(")", "Expected ')' after catch parameter")
                catches.append((catch_type, catch_name, self._as_block(self._statement())))
            finally_body = self._as_block(self._statement()) if self._match("finally") else None
            if not catches and finally_body is None:
                raise ParseError("A try statement needs catch or finally", self._peek())
            return TryStatement(body, catches, finally_body)
        if self._match(";"):
            return ExpressionStatement(Literal(None))
        expression = self._expression()
        self._consume(";", "Expected ';' after expression")
        return ExpressionStatement(expression)

    def _block(self) -> Block:
        self._consume("{", "Expected '{' before block")
        return Block(self._block_contents())

    def _block_contents(self) -> list[Any]:
        statements: list[Any] = []
        while not self._check("}") and not self._check("EOF"):
            statements.append(self._statement())
        self._consume("}", "Expected '}' after block")
        return statements

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
            self._advance()
            next_precedence = precedence if precedence == 1 else precedence + 1
            right = self._expression(next_precedence)
            if precedence == 1:
                expression = Assignment(expression, operator, right)
            else:
                expression = Binary(expression, operator, right)
        if minimum_precedence == 1 and self._match("?"):
            true_value = self._expression()
            self._consume(":", "Expected ':' in conditional expression")
            false_value = self._expression()
            expression = Binary(expression, "?:", (true_value, false_value))
        return expression

    def _unary(self) -> Any:
        if self._match("!", "-", "+", "++", "--"):
            operator = self._previous().kind
            return Unary(operator, self._unary())
        expression = self._primary()
        while True:
            if self._check("<") and self._looks_like_generic_call():
                self._advance()
                type_arguments = [self._parse_type()]
                while self._match(","):
                    type_arguments.append(self._parse_type())
                self._consume(">", "Expected '>' after generic call types")
                self._consume("(", "Expected '(' after generic call types")
                expression = Call(
                    expression,
                    self._arguments_after_open_paren(),
                    type_arguments,
                )
            elif self._match("("):
                arguments = self._arguments_after_open_paren()
                expression = Call(expression, arguments)
            elif self._match("."):
                name = self._consume("IDENTIFIER", "Expected member name after '.'").value
                expression = Member(expression, name)
            elif self._match("["):
                index = self._expression()
                self._consume("]", "Expected ']' after index")
                expression = Index(expression, index)
            elif self._match("++", "--"):
                expression = Unary(self._previous().kind, expression, postfix=True)
            else:
                break
        return expression

    def _primary(self) -> Any:
        if self._match("false"):
            return Literal(False)
        if self._match("true"):
            return Literal(True)
        if self._match("null"):
            return Literal(None)
        if self._match("NUMBER"):
            text = self._previous().value
            return Literal(float(text) if "." in text else int(text))
        if self._match("STRING"):
            return Literal(self._previous().value)
        if self._match("this"):
            return ThisExpression()
        if self._match("super"):
            return ThisExpression(is_super=True)
        if self._match("new"):
            class_name = self._parse_type()
            self._consume("(", "Expected '(' after type name")
            return NewExpression(class_name, self._arguments_after_open_paren())
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
                    items.append(self._expression())
                    if not self._match(","):
                        break
            self._consume("]", "Expected ']' after array literal")
            return ArrayLiteral(items)
        if self._match("{"):
            fields: dict[str, Any] = {}
            while not self._check("}") and not self._check("EOF"):
                key = self._consume("IDENTIFIER", "Expected object field name").value
                self._consume(":", "Expected ':' after object field name")
                fields[key] = self._expression()
                if not self._match(","):
                    break
            self._consume("}", "Expected '}' after object literal")
            return ObjectLiteral(fields)
        raise ParseError("Expected an expression", self._peek())

    def _arguments_after_open_paren(self) -> list[Any]:
        arguments: list[Any] = []
        if not self._check(")"):
            while True:
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
