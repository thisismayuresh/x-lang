from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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
    ImportAlias,
    Identifier,
    IfStatement,
    Index,
    Literal,
    Member,
    NewExpression,
    ObjectLiteral,
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


class RuntimeErrorX(Exception):
    pass


class ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class LoopSignal(Exception):
    def __init__(self, is_continue: bool) -> None:
        self.is_continue = is_continue


class ThrownValue(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class Environment:
    def __init__(self, parent: Environment | None = None) -> None:
        self.parent = parent
        self.values: dict[str, Any] = {}
        self.constants: set[str] = set()

    def define(self, name: str, value: Any, constant: bool = False) -> None:
        if name in self.values:
            raise RuntimeErrorX(f"'{name}' is already declared in this scope")
        self.values[name] = value
        if constant:
            self.constants.add(name)

    def get(self, name: str) -> Any:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise RuntimeErrorX(f"Name '{name}' is not defined")

    def assign(self, name: str, value: Any) -> None:
        if name in self.values:
            if name in self.constants:
                raise RuntimeErrorX(f"Cannot reassign constant '{name}'")
            self.values[name] = value
            return
        if self.parent is not None:
            self.parent.assign(name, value)
            return
        raise RuntimeErrorX(f"Cannot assign to undefined name '{name}'")


@dataclass
class XFunction:
    declaration: FunctionDeclaration
    closure: Environment
    interpreter: Interpreter
    bound_this: Any = None
    parent_class: XClass | None = None

    def call(self, arguments: list[Any]) -> Any:
        if len(arguments) != len(self.declaration.parameters):
            raise RuntimeErrorX(
                f"'{self.declaration.name}' expects "
                f"{len(self.declaration.parameters)} argument(s), got {len(arguments)}"
            )
        call_environment = Environment(self.closure)
        if self.bound_this is not None:
            call_environment.define("this", self.bound_this)
            if self.parent_class is not None and self.parent_class.parent is not None:
                call_environment.define(
                    "super", XSuper(self.bound_this, self.parent_class.parent)
                )
        for parameter, argument in zip(self.declaration.parameters, arguments):
            call_environment.define(parameter.name, argument)
        try:
            self.interpreter._execute_block(self.declaration.body, call_environment)
        except ReturnSignal as returned:
            return returned.value
        return None

@dataclass
class XSuper:
    instance: XInstance
    parent_class: XClass


@dataclass
class XClass:
    declaration: ClassDeclaration
    interpreter: Interpreter
    closure: Environment
    parent: XClass | None = None
    static_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.declaration.name

    def find_methods(self, name: str) -> list[FunctionDeclaration]:
        methods = [
            member for member in self.declaration.members
            if isinstance(member, FunctionDeclaration)
            and member.name == name
            and member.name != self.name
            and "static" not in member.modifiers
        ]
        if self.parent is not None:
            own_signatures = {
                tuple(parameter.type_name for parameter in method.parameters)
                for method in methods
            }
            inherited_methods = self.parent.find_methods(name)
            methods.extend(
                method for method in inherited_methods
                if tuple(parameter.type_name for parameter in method.parameters)
                not in own_signatures
            )
        return methods

    def find_constructors(self) -> list[FunctionDeclaration]:
        return [
            member for member in self.declaration.members
            if isinstance(member, FunctionDeclaration) and member.name == self.name
        ]

    def construct(self, arguments: list[Any]) -> XInstance:
        instance = XInstance(self)
        self.interpreter._initialize_fields(instance, self)
        constructors = self.find_constructors()
        if constructors:
            constructor = self.interpreter._select_overload(self.name, constructors, arguments)
            XFunction(constructor, self.closure, self.interpreter, instance, self).call(arguments)
        elif arguments:
            raise RuntimeErrorX(
                f"'{self.name}' has no constructor accepting {len(arguments)} argument(s)"
            )
        return instance


@dataclass
class XInstance:
    xclass: XClass
    fields: dict[str, Any]

    def __init__(self, xclass: XClass) -> None:
        self.xclass = xclass
        self.fields = {}


@dataclass
class XEnumMember:
    enum_name: str
    name: str
    value: Any


@dataclass
class XExceptionValue:
    message: str


class Interpreter:
    def __init__(
        self,
        arguments: list[str] | None = None,
        output: Callable[[str], None] = print,
    ) -> None:
        self.globals = Environment()
        self.output = output
        self._install_builtins(arguments or [])

    def interpret(self, program: Program) -> Any:
        declarations = [declaration for declaration in program.declarations if declaration]
        for declaration in declarations:
            if isinstance(declaration, FunctionDeclaration):
                self._define_function(declaration, self.globals)
            elif isinstance(declaration, ClassDeclaration):
                self._define_class(declaration, self.globals)
            elif isinstance(declaration, EnumDeclaration):
                self._define_enum(declaration, self.globals)

        for declaration in declarations:
            if isinstance(declaration, ImportAlias):
                imported_value = self._resolve_import(declaration.source_name)
                self.globals.define(declaration.alias_name, imported_value)
            elif isinstance(declaration, VariableDeclaration):
                self._execute(declaration, self.globals)
            elif isinstance(declaration, TypeDeclaration):
                continue

        main_value = self.globals.values.get("main")
        if main_value is not None:
            main_functions = main_value if isinstance(main_value, list) else [main_value]
            valid_entries = [
                function for function in main_functions
                if len(function.declaration.parameters) in (0, 1)
            ]
            if len(valid_entries) != 1:
                if not valid_entries:
                    raise RuntimeErrorX(
                        "main may accept zero parameters or one string[] parameter"
                    )
                raise RuntimeErrorX("Program declares multiple main functions")
            main_function = valid_entries[0]
            if len(main_function.declaration.parameters) == 1:
                arguments = self.globals.get("args")
                return self._select_overload("main", [main_function], [arguments]).call(
                    [arguments]
                )
            if main_function.declaration.parameters:
                raise RuntimeErrorX("main may accept zero parameters or one string[] parameter")
            return main_function.call([])
        return None

    def _resolve_import(self, qualified_name: str) -> Any:
        parts = qualified_name.split(".")
        value = self.globals.get(parts[0])
        for part in parts[1:]:
            value = self._get_member(value, part)
        return value

    def _install_builtins(self, arguments: list[str]) -> None:
        self.globals.define("args", arguments)
        self.globals.define("print", BuiltinFunction("print", self._builtin_print))
        self.globals.define("range", BuiltinFunction("range", self._builtin_range))
        self.globals.define("Exception", BuiltinFunction("Exception", self._builtin_exception))
        system_namespace = Environment()
        io_namespace = Environment(system_namespace)
        io_namespace.define("FileSystem", self._filesystem_members())
        system_namespace.define("io", io_namespace)
        self.globals.define("System", system_namespace)

    def _filesystem_members(self) -> dict[str, BuiltinFunction]:
        return {
            "exists": BuiltinFunction("FileSystem.exists", self._filesystem_exists),
            "isFile": BuiltinFunction("FileSystem.isFile", self._filesystem_is_file),
            "isDirectory": BuiltinFunction(
                "FileSystem.isDirectory", self._filesystem_is_directory
            ),
            "readText": BuiltinFunction("FileSystem.readText", self._filesystem_read_text),
            "writeText": BuiltinFunction("FileSystem.writeText", self._filesystem_write_text),
            "appendText": BuiltinFunction("FileSystem.appendText", self._filesystem_append_text),
            "createDirectory": BuiltinFunction(
                "FileSystem.createDirectory", self._filesystem_create_directory
            ),
            "listDirectory": BuiltinFunction(
                "FileSystem.listDirectory", self._filesystem_list_directory
            ),
            "deleteFile": BuiltinFunction(
                "FileSystem.deleteFile", self._filesystem_delete_file
            ),
            "deleteDirectory": BuiltinFunction(
                "FileSystem.deleteDirectory", self._filesystem_delete_directory
            ),
        }

    def _filesystem_path(
        self, operation: str, arguments: list[Any]
    ) -> Path:
        self._validate_argument_count(operation, arguments, 1)
        path_value = arguments[0]
        if not isinstance(path_value, str):
            raise RuntimeErrorX(f"FileSystem.{operation} expects a string path")
        return Path(path_value)

    def _filesystem_exists(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("exists", arguments)
        try:
            return path.exists()
        except OSError as error:
            raise RuntimeErrorX(f"Cannot check whether '{path}' exists: {error}") from error

    def _filesystem_is_file(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("isFile", arguments)
        try:
            return path.is_file()
        except OSError as error:
            raise RuntimeErrorX(f"Cannot check whether '{path}' is a file: {error}") from error

    def _filesystem_is_directory(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("isDirectory", arguments)
        try:
            return path.is_dir()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot check whether '{path}' is a directory: {error}"
            ) from error

    def _filesystem_read_text(self, arguments: list[Any]) -> str:
        path = self._filesystem_path("readText", arguments)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(f"Cannot read text file '{path}': {error}") from error

    def _filesystem_write_text(self, arguments: list[Any]) -> None:
        self._validate_argument_count("writeText", arguments, 2)
        path_value, text = arguments
        if not isinstance(path_value, str):
            raise RuntimeErrorX("FileSystem.writeText expects a string path")
        if not isinstance(text, str):
            raise RuntimeErrorX("FileSystem.writeText expects string content")
        path = Path(path_value)
        try:
            path.write_text(text, encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(f"Cannot write text file '{path}': {error}") from error
        return None

    def _filesystem_append_text(self, arguments: list[Any]) -> None:
        self._validate_argument_count("appendText", arguments, 2)
        path_value, text = arguments
        if not isinstance(path_value, str):
            raise RuntimeErrorX("FileSystem.appendText expects a string path")
        if not isinstance(text, str):
            raise RuntimeErrorX("FileSystem.appendText expects string content")
        path = Path(path_value)
        try:
            with path.open("a", encoding="utf-8") as output_file:
                output_file.write(text)
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(f"Cannot append to text file '{path}': {error}") from error
        return None

    def _filesystem_create_directory(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("createDirectory", arguments)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RuntimeErrorX(f"Cannot create directory '{path}': {error}") from error
        return None

    def _filesystem_list_directory(self, arguments: list[Any]) -> list[str]:
        path = self._filesystem_path("listDirectory", arguments)
        try:
            return sorted(entry.name for entry in path.iterdir())
        except OSError as error:
            raise RuntimeErrorX(f"Cannot list directory '{path}': {error}") from error

    def _filesystem_delete_file(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("deleteFile", arguments)
        try:
            path.unlink()
        except OSError as error:
            raise RuntimeErrorX(f"Cannot delete file '{path}': {error}") from error
        return None

    def _filesystem_delete_directory(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("deleteDirectory", arguments)
        try:
            path.rmdir()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot delete directory '{path}'; it must be empty: {error}"
            ) from error
        return None

    def _validate_argument_count(
        self, operation: str, arguments: list[Any], expected: int
    ) -> None:
        if len(arguments) != expected:
            raise RuntimeErrorX(
                f"FileSystem.{operation} expects {expected} argument(s), "
                f"got {len(arguments)}"
            )

    def _builtin_print(self, arguments: list[Any]) -> None:
        self.output(" ".join(self._stringify(value) for value in arguments))
        return None

    def _builtin_range(self, arguments: list[Any]) -> range:
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX("range expects two or three integer arguments")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in arguments):
            raise RuntimeErrorX("range arguments must be integers")
        if len(arguments) == 2:
            start, stop = arguments
            step = 1
        else:
            start, stop, step = arguments
        if step == 0:
            raise RuntimeErrorX("range step cannot be zero")
        return range(start, stop, step)

    def _builtin_exception(self, arguments: list[Any]) -> XExceptionValue:
        if len(arguments) != 1:
            raise RuntimeErrorX("Exception expects one message")
        return XExceptionValue(self._stringify(arguments[0]))

    def _define_function(self, declaration: FunctionDeclaration, environment: Environment) -> None:
        function = XFunction(declaration, environment, self)
        existing = environment.values.get(declaration.name)
        if existing is None:
            environment.define(declaration.name, [function])
        else:
            if not isinstance(existing, list) or any(not isinstance(item, XFunction) for item in existing):
                raise RuntimeErrorX(f"'{declaration.name}' is already declared")
            existing.append(function)

    def _define_class(self, declaration: ClassDeclaration, environment: Environment) -> None:
        parent = None
        if declaration.parent_name:
            parent_value = environment.get(declaration.parent_name.split(".")[-1])
            if not isinstance(parent_value, XClass):
                raise RuntimeErrorX(f"Parent type '{declaration.parent_name}' is not a class")
            parent = parent_value
        environment.define(
            declaration.name,
            XClass(declaration, self, environment, parent),
        )
        xclass = environment.get(declaration.name)
        if isinstance(xclass, XClass):
            for member in declaration.members:
                if (
                    isinstance(member, VariableDeclaration)
                    and "static" in member.modifiers
                ):
                    value = None if member.initializer is None else self._evaluate(
                        member.initializer, environment
                    )
                    xclass.static_fields[member.name] = value

    def _define_enum(self, declaration: EnumDeclaration, environment: Environment) -> None:
        enum_values = Environment()
        for index, (name, expression) in enumerate(declaration.members):
            value = index if expression is None else self._evaluate(expression, environment)
            enum_values.define(name, XEnumMember(declaration.name, name, value))
        environment.define(declaration.name, enum_values)

    def _execute(self, statement: Any, environment: Environment) -> None:
        if isinstance(statement, Block):
            self._execute_block(statement.statements, Environment(environment))
        elif isinstance(statement, VariableDeclaration):
            value = None if statement.initializer is None else self._evaluate(statement.initializer, environment)
            environment.define(statement.name, value, statement.constant)
        elif isinstance(statement, ExpressionStatement):
            self._evaluate(statement.expression, environment)
        elif isinstance(statement, IfStatement):
            if self._is_truthy(self._evaluate(statement.condition, environment)):
                self._execute_block(statement.then_branch.statements, Environment(environment))
            elif statement.else_branch is not None:
                self._execute(statement.else_branch, environment)
        elif isinstance(statement, WhileStatement):
            self._execute_while(statement, environment)
        elif isinstance(statement, ForStatement):
            self._execute_for(statement, environment)
        elif isinstance(statement, ReturnStatement):
            value = None if statement.value is None else self._evaluate(statement.value, environment)
            raise ReturnSignal(value)
        elif isinstance(statement, BreakStatement):
            raise LoopSignal(statement.is_continue)
        elif isinstance(statement, ThrowStatement):
            raise ThrownValue(self._evaluate(statement.value, environment))
        elif isinstance(statement, TryStatement):
            self._execute_try(statement, environment)
        else:
            raise RuntimeErrorX(f"Unsupported statement '{type(statement).__name__}'")

    def _execute_block(self, statements: list[Any], environment: Environment) -> None:
        for statement in statements:
            self._execute(statement, environment)

    def _execute_while(self, statement: WhileStatement, environment: Environment) -> None:
        while self._is_truthy(self._evaluate(statement.condition, environment)):
            try:
                self._execute_block(statement.body.statements, Environment(environment))
            except LoopSignal as loop_signal:
                if not loop_signal.is_continue:
                    break

    def _execute_for(self, statement: ForStatement, environment: Environment) -> None:
        iterable = self._evaluate(statement.iterable, environment)
        try:
            iterator = iter(iterable)
        except TypeError as error:
            raise RuntimeErrorX("Value in for loop is not iterable") from error
        for value in iterator:
            loop_environment = Environment(environment)
            loop_environment.define(statement.variable, value)
            try:
                self._execute_block(statement.body.statements, loop_environment)
            except LoopSignal as loop_signal:
                if not loop_signal.is_continue:
                    break

    def _execute_try(self, statement: TryStatement, environment: Environment) -> None:
        try:
            self._execute_block(statement.body.statements, Environment(environment))
        except ThrownValue as thrown:
            handled = False
            for catch_type, catch_name, catch_body in statement.catches:
                if self._exception_matches(thrown.value, catch_type):
                    catch_environment = Environment(environment)
                    catch_environment.define(catch_name, thrown.value)
                    self._execute_block(catch_body.statements, catch_environment)
                    handled = True
                    break
            if not handled:
                raise
        finally:
            if statement.finally_body is not None:
                self._execute_block(statement.finally_body.statements, Environment(environment))

    def _exception_matches(self, value: Any, type_name: str | None) -> bool:
        if type_name is None or type_name in ("Exception", "Throwable"):
            return True
        if type_name == "RuntimeError":
            return isinstance(value, XExceptionValue)
        return isinstance(value, XExceptionValue) and type_name.endswith("Exception")

    def _evaluate(self, expression: Any, environment: Environment) -> Any:
        if isinstance(expression, Literal):
            return expression.value
        if isinstance(expression, Identifier):
            value = environment.get(expression.name)
            if isinstance(value, list) and all(isinstance(item, XFunction) for item in value):
                return OverloadedFunction(expression.name, value)
            return value
        if isinstance(expression, ArrayLiteral):
            return [self._evaluate(item, environment) for item in expression.items]
        if isinstance(expression, ObjectLiteral):
            return {
                name: self._evaluate(value, environment)
                for name, value in expression.fields.items()
            }
        if isinstance(expression, ThisExpression):
            if expression.is_super:
                return environment.get("super")
            return environment.get("this")
        if isinstance(expression, Unary):
            return self._evaluate_unary(expression, environment)
        if isinstance(expression, Binary):
            return self._evaluate_binary(expression, environment)
        if isinstance(expression, Assignment):
            value = self._evaluate(expression.value, environment)
            return self._assign(expression.target, expression.operator, value, environment)
        if isinstance(expression, Call):
            callee = self._evaluate(expression.callee, environment)
            arguments = [self._evaluate(argument, environment) for argument in expression.arguments]
            return self._call(callee, arguments)
        if isinstance(expression, NewExpression):
            class_value = environment.get(expression.class_name.split(".")[-1])
            arguments = [self._evaluate(argument, environment) for argument in expression.arguments]
            if isinstance(class_value, BuiltinFunction):
                return self._call(class_value, arguments)
            if not isinstance(class_value, XClass):
                raise RuntimeErrorX(f"'{expression.class_name}' is not a constructible class")
            return class_value.construct(arguments)
        if isinstance(expression, Member):
            object_value = self._evaluate(expression.object, environment)
            return self._get_member(object_value, expression.name)
        if isinstance(expression, Index):
            object_value = self._evaluate(expression.object, environment)
            index = self._evaluate(expression.index, environment)
            try:
                return object_value[index]
            except (IndexError, KeyError, TypeError) as error:
                raise RuntimeErrorX(f"Cannot access index {self._stringify(index)}") from error
        raise RuntimeErrorX(f"Unsupported expression '{type(expression).__name__}'")

    def _evaluate_unary(self, expression: Unary, environment: Environment) -> Any:
        if expression.operator in ("++", "--"):
            current = self._read_target(expression.operand, environment)
            updated = current + (1 if expression.operator == "++" else -1)
            self._write_target(expression.operand, updated, environment)
            return current if expression.postfix else updated
        operand = self._evaluate(expression.operand, environment)
        if expression.operator == "!":
            return not self._is_truthy(operand)
        if expression.operator == "-":
            return -operand
        if expression.operator == "+":
            return +operand
        raise RuntimeErrorX(f"Unknown unary operator '{expression.operator}'")

    def _evaluate_binary(self, expression: Binary, environment: Environment) -> Any:
        operator = expression.operator
        left = self._evaluate(expression.left, environment)
        if operator == "&&":
            return self._is_truthy(left) and self._is_truthy(self._evaluate(expression.right, environment))
        if operator == "||":
            return self._is_truthy(left) or self._is_truthy(self._evaluate(expression.right, environment))
        if operator == "?:":
            true_expression, false_expression = expression.right
            selected = true_expression if self._is_truthy(left) else false_expression
            return self._evaluate(selected, environment)
        right = self._evaluate(expression.right, environment)
        try:
            if operator == "+":
                if isinstance(left, str) or isinstance(right, str):
                    return self._stringify(left) + self._stringify(right)
                return left + right
            if operator == "-":
                return left - right
            if operator == "*":
                return left * right
            if operator == "/":
                return left / right
            if operator == "%":
                return left % right
            if operator == "==":
                return left == right
            if operator == "!=":
                return left != right
            if operator == "<":
                return left < right
            if operator == ">":
                return left > right
            if operator == "<=":
                return left <= right
            if operator == ">=":
                return left >= right
            if operator == "in":
                return left in right
        except (TypeError, ZeroDivisionError) as error:
            raise RuntimeErrorX(f"Invalid operands for '{operator}'") from error
        raise RuntimeErrorX(f"Unknown binary operator '{operator}'")

    def _assign(self, target: Any, operator: str, value: Any, environment: Environment) -> Any:
        if operator != "=":
            current = self._read_target(target, environment)
            base_operator = operator[0]
            value = self._apply_compound_operator(current, base_operator, value)
        self._write_target(target, value, environment)
        return value

    def _apply_compound_operator(self, left: Any, operator: str, right: Any) -> Any:
        if operator == "+":
            if isinstance(left, str) or isinstance(right, str):
                return self._stringify(left) + self._stringify(right)
            return left + right
        if operator == "-":
            return left - right
        if operator == "*":
            return left * right
        if operator == "/":
            return left / right
        raise RuntimeErrorX(f"Unknown assignment operator '{operator}='")

    def _read_target(self, target: Any, environment: Environment) -> Any:
        if isinstance(target, Identifier):
            return environment.get(target.name)
        if isinstance(target, Member):
            return self._get_member(self._evaluate(target.object, environment), target.name)
        if isinstance(target, Index):
            return self._evaluate(target.object, environment)[self._evaluate(target.index, environment)]
        raise RuntimeErrorX("Invalid assignment target")

    def _write_target(self, target: Any, value: Any, environment: Environment) -> None:
        if isinstance(target, Identifier):
            environment.assign(target.name, value)
            return
        if isinstance(target, Member):
            object_value = self._evaluate(target.object, environment)
            self._set_member(object_value, target.name, value)
            return
        if isinstance(target, Index):
            object_value = self._evaluate(target.object, environment)
            index = self._evaluate(target.index, environment)
            object_value[index] = value
            return
        raise RuntimeErrorX("Invalid assignment target")

    def _get_member(self, object_value: Any, name: str) -> Any:
        if isinstance(object_value, XInstance):
            if name in object_value.fields:
                return object_value.fields[name]
            methods = object_value.xclass.find_methods(name)
            if methods:
                return OverloadedFunction(
                    name,
                    [
                        XFunction(
                            method,
                            object_value.xclass.closure,
                            self,
                            object_value,
                            object_value.xclass,
                        )
                        for method in methods
                    ],
                )
            raise RuntimeErrorX(f"'{object_value.xclass.name}' has no member '{name}'")
        if isinstance(object_value, XSuper):
            methods = object_value.parent_class.find_methods(name)
            if methods:
                return OverloadedFunction(
                    name,
                    [
                        XFunction(
                            method,
                            object_value.parent_class.closure,
                            self,
                            object_value.instance,
                            object_value.parent_class,
                        )
                        for method in methods
                    ],
                )
            raise RuntimeErrorX(f"Parent class has no method '{name}'")
        if isinstance(object_value, Environment):
            return object_value.get(name)
        if isinstance(object_value, list) and name == "length":
            return len(object_value)
        if isinstance(object_value, str) and name == "length":
            return len(object_value)
        if isinstance(object_value, (list, str)) and name == "add" and isinstance(object_value, list):
            return BuiltinFunction("add", lambda arguments: self._list_add(object_value, arguments))
        if isinstance(object_value, str) and name == "toString":
            return BuiltinFunction("toString", lambda arguments: self._no_argument_string(object_value, arguments))
        if isinstance(object_value, (int, float, bool)) and name == "toString":
            return BuiltinFunction(
                "toString",
                lambda arguments: self._no_argument_string(self._stringify(object_value), arguments),
            )
        if isinstance(object_value, dict):
            if name in object_value:
                return object_value[name]
            raise RuntimeErrorX(f"Object has no field '{name}'")
        if isinstance(object_value, XEnumMember):
            if name == "name":
                return object_value.name
            if name == "value":
                return object_value.value
        if isinstance(object_value, XExceptionValue) and name == "message":
            return object_value.message
        if isinstance(object_value, XClass):
            if name in object_value.static_fields:
                return object_value.static_fields[name]
            for member in object_value.declaration.members:
                if isinstance(member, FunctionDeclaration) and member.name == name and "static" in member.modifiers:
                    return XFunction(member, object_value.closure, self)
        if object_value is None:
            raise RuntimeErrorX(f"Cannot access member '{name}' on null")
        raise RuntimeErrorX(f"Value has no member '{name}'")

    def _set_member(self, object_value: Any, name: str, value: Any) -> None:
        if isinstance(object_value, XInstance):
            object_value.fields[name] = value
            return
        if isinstance(object_value, XClass):
            if name not in object_value.static_fields:
                raise RuntimeErrorX(f"'{object_value.name}' has no static field '{name}'")
            object_value.static_fields[name] = value
            return
        if isinstance(object_value, dict):
            object_value[name] = value
            return
        raise RuntimeErrorX(f"Cannot assign member '{name}'")

    def _initialize_fields(self, instance: XInstance, xclass: XClass) -> None:
        if xclass.parent is not None:
            self._initialize_fields(instance, xclass.parent)
        for member in xclass.declaration.members:
            if isinstance(member, VariableDeclaration):
                if "static" in member.modifiers:
                    continue
                value = None if member.initializer is None else self._evaluate(
                    member.initializer, Environment(xclass.closure)
                )
                instance.fields[member.name] = value

    def _call(self, callee: Any, arguments: list[Any]) -> Any:
        if isinstance(callee, BuiltinFunction):
            return callee.call(arguments)
        if isinstance(callee, XFunction):
            return callee.call(arguments)
        if isinstance(callee, OverloadedFunction):
            function = self._select_overload(callee.name, callee.functions, arguments)
            return function.call(arguments)
        if isinstance(callee, XClass):
            return callee.construct(arguments)
        if isinstance(callee, XSuper):
            constructors = callee.parent_class.find_constructors()
            if constructors:
                constructor = self._select_overload(
                    callee.parent_class.name, constructors, arguments
                )
                XFunction(
                    constructor,
                    callee.parent_class.closure,
                    self,
                    callee.instance,
                    callee.parent_class,
                ).call(arguments)
            elif arguments:
                raise RuntimeErrorX(
                    f"Parent class '{callee.parent_class.name}' has no matching constructor"
                )
            return None
        raise RuntimeErrorX("Value is not callable")

    def _select_overload(
        self, name: str, functions: list[Any], arguments: list[Any]
    ) -> Any:
        def declaration_for(function: Any) -> FunctionDeclaration:
            if isinstance(function, XFunction):
                return function.declaration
            return function

        matches = [
            function for function in functions
            if len(declaration_for(function).parameters) == len(arguments)
        ]
        if not matches:
            available = sorted({
                len(declaration_for(function).parameters) for function in functions
            })
            expected = ", ".join(str(count) for count in available)
            raise RuntimeErrorX(
                f"No overload of '{name}' accepts {len(arguments)} argument(s); "
                f"available argument counts: {expected}"
            )
        scored_matches: list[tuple[int, XFunction]] = []
        for function in matches:
            score = 0
            compatible = True
            declaration = declaration_for(function)
            for parameter, argument in zip(declaration.parameters, arguments):
                parameter_score = self._type_match_score(parameter.type_name, argument)
                if parameter_score is None:
                    compatible = False
                    break
                score += parameter_score
            if compatible:
                scored_matches.append((score, function))
        if not scored_matches:
            raise RuntimeErrorX(f"No overload of '{name}' matches the supplied argument types")
        highest_score = max(score for score, _ in scored_matches)
        best_matches = [
            function for score, function in scored_matches if score == highest_score
        ]
        if len(best_matches) != 1:
            raise RuntimeErrorX(
                f"Call to overloaded '{name}' is ambiguous for the supplied argument types"
            )
        return best_matches[0]

    def _type_match_score(self, type_name: str | None, value: Any) -> int | None:
        if type_name is None or type_name == "var":
            return 0
        if type_name.endswith("?"):
            if value is None:
                return 3
            type_name = type_name[:-1]
        if value is None:
            return 1 if type_name in ("null", "Object", "object") else None
        if type_name.endswith("[]"):
            return 3 if isinstance(value, list) else None
        if type_name in ("integer", "byte"):
            return 3 if isinstance(value, int) and not isinstance(value, bool) else None
        if type_name in ("float", "double"):
            if isinstance(value, float):
                return 3
            if isinstance(value, int) and not isinstance(value, bool):
                return 2
            return None
        if type_name == "boolean":
            return 3 if isinstance(value, bool) else None
        if type_name in ("string", "char"):
            return 3 if isinstance(value, str) else None
        if type_name in ("object", "Object"):
            return 1
        if isinstance(value, XInstance) and value.xclass.name == type_name.split(".")[-1]:
            return 3
        if isinstance(value, XEnumMember) and value.enum_name == type_name.split(".")[-1]:
            return 3
        return 0

    def _list_add(self, values: list[Any], arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("add expects one argument")
        values.append(arguments[0])
        return None

    def _no_argument_string(self, value: str, arguments: list[Any]) -> str:
        if arguments:
            raise RuntimeErrorX("toString expects no arguments")
        return value

    def _is_truthy(self, value: Any) -> bool:
        return bool(value)

    def _stringify(self, value: Any) -> str:
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, list):
            return "[" + ", ".join(self._stringify(item) for item in value) + "]"
        if isinstance(value, XEnumMember):
            return value.name
        if isinstance(value, XExceptionValue):
            return value.message
        return str(value)


@dataclass
class BuiltinFunction:
    name: str
    implementation: Callable[[list[Any]], Any]

    def call(self, arguments: list[Any]) -> Any:
        return self.implementation(arguments)


@dataclass
class OverloadedFunction:
    name: str
    functions: list[XFunction]
