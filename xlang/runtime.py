from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .ast_nodes import (
    ClassDeclaration,
    FunctionDeclaration,
)


class _UndefinedValue:
    __slots__ = ()


UNDEFINED = _UndefinedValue()


class RuntimeErrorX(Exception):
    def __init__(self, message: str, exception_name: str = "RuntimeException") -> None:
        super().__init__(message)
        self.message = message
        self.exception_name = exception_name
        self.line: int | None = None
        self.column: int | None = None
        self.source_name: str | None = None


class ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class LoopSignal(Exception):
    def __init__(self, is_continue: bool) -> None:
        self.is_continue = is_continue


class ThrownValue(Exception):
    def __init__(
        self,
        value: Any,
        source_name: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        self.value = value
        self.line = line
        self.column = column
        self.source_name = source_name


class Environment:
    def __init__(self, parent: Environment | None = None) -> None:
        self.parent = parent
        self.values: dict[str, Any] = {}
        self.constants: set[str] = set()
        self.array_types: dict[str, str] = {}
        self.object_types: dict[str, str] = {}
        self.value_types: dict[str, str] = {}

    def define(
        self,
        name: str,
        value: Any,
        constant: bool = False,
        array_type: str | None = None,
        object_type: str | None = None,
        value_type: str | None = None,
    ) -> None:
        if name in self.values:
            raise RuntimeErrorX(f"'{name}' is already declared in this scope")
        self.values[name] = value
        if constant:
            self.constants.add(name)
        if array_type is not None:
            self.array_types[name] = array_type
        if object_type is not None:
            self.object_types[name] = object_type
        if value_type is not None:
            self.value_types[name] = value_type

    def get(self, name: str) -> Any:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise RuntimeErrorX(f"Name '{name}' is not defined")

    def get_array_type(self, name: str) -> str | None:
        if name in self.values:
            return self.array_types.get(name)
        if self.parent is not None:
            return self.parent.get_array_type(name)
        return None

    def get_object_type(self, name: str) -> str | None:
        if name in self.values:
            return self.object_types.get(name)
        if self.parent is not None:
            return self.parent.get_object_type(name)
        return None

    def get_value_type(self, name: str) -> str | None:
        if name in self.values:
            return self.value_types.get(name)
        if self.parent is not None:
            return self.parent.get_value_type(name)
        return None

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


class XArray(list[Any]):
    def __init__(
        self,
        values: list[Any],
        element_type: str,
        validate_value: Callable[[str, Any], Any],
    ) -> None:
        super().__init__(values)
        self.element_type = element_type
        self.validate_value = validate_value

    def append(self, value: Any) -> None:
        super().append(self.validate_value(self.element_type, value))

    def extend(self, values: Any) -> None:
        for value in values:
            self.append(value)

    def insert(self, index: int, value: Any) -> None:
        super().insert(index, self.validate_value(self.element_type, value))

    def __setitem__(self, index: Any, value: Any) -> None:
        if isinstance(index, slice):
            validated_values = [
                self.validate_value(self.element_type, item) for item in value
            ]
            super().__setitem__(index, validated_values)
            return
        super().__setitem__(index, self.validate_value(self.element_type, value))

    def __iadd__(self, values: Any) -> XArray:
        self.extend(values)
        return self


class XObject(dict[str, Any]):
    def __init__(
        self,
        values: dict[str, Any],
        key_type: str,
        value_type: str,
        validate_value: Callable[[str, Any, str], Any],
    ) -> None:
        super().__init__()
        self.key_type = key_type
        self.value_type = value_type
        self.validate_value = validate_value
        for key, value in values.items():
            self[key] = value

    def __setitem__(self, key: str, value: Any) -> None:
        checked_key = self.validate_value(
            self.key_type, key, f"object key '{key}'"
        )
        checked_value = self.validate_value(
            self.value_type, value, f"object value at key '{key}'"
        )
        super().__setitem__(checked_key, checked_value)

    def update(self, values: Any = (), /, **kwargs: Any) -> None:
        entries = dict(values, **kwargs)
        for key, value in entries.items():
            self[key] = value

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return self[key]

    def __ior__(self, values: Any) -> XObject:
        self.update(values)
        return self


@dataclass
class XFunction:
    declaration: FunctionDeclaration
    closure: Environment
    interpreter: Interpreter
    bound_this: Any = None
    parent_class: XClass | None = None
    traced: bool = False

    def call(self, arguments: list[Any]) -> Any:
        if self.declaration.is_async:
            return self._call_async(arguments)
        return self._call_sync(arguments)

    async def _call_async(self, arguments: list[Any]) -> Any:
        result = await asyncio.to_thread(self._call_sync, arguments)
        if inspect.isawaitable(result):
            return await result
        return result

    def _call_sync(self, arguments: list[Any]) -> Any:
        if self.traced:
            self.interpreter.output(f"Calling {self.declaration.name}")
        self.interpreter.function_stack.append(self)
        try:
            return self._invoke(arguments)
        finally:
            self.interpreter.function_stack.pop()

    def _invoke(self, arguments: list[Any]) -> Any:
        parameters = self.declaration.parameters
        has_rest_parameter = bool(parameters and parameters[-1].is_rest)
        required_count = sum(
            not parameter.is_rest
            and not parameter.has_default
            and not (
                parameter.type_name is not None and parameter.type_name.endswith("?")
            )
            for parameter in parameters
        )
        if len(arguments) < required_count or (
            not has_rest_parameter and len(arguments) > len(parameters)
        ):
            raise RuntimeErrorX(
                f"'{self.declaration.name}' expects "
                f"{required_count}"
                f"{' or more' if has_rest_parameter else ''} argument(s), "
                f"got {len(arguments)}"
            )
        call_environment = Environment(self.closure)
        if self.parent_class is not None:
            call_environment.define("__x_current_class__", self.parent_class)
        if self.bound_this is not None:
            call_environment.define("this", self.bound_this)
            if self.parent_class is not None and self.parent_class.parent is not None:
                call_environment.define(
                    "super", XSuper(self.bound_this, self.parent_class.parent)
                )
        for parameter_index, parameter in enumerate(parameters):
            if parameter.is_rest:
                call_environment.define(parameter.name, arguments[parameter_index:])
            else:
                if parameter_index < len(arguments):
                    argument_value = arguments[parameter_index]
                elif parameter.has_default:
                    argument_value = self.interpreter._evaluate(
                        parameter.default_value, call_environment
                    )
                else:
                    argument_value = None
                if parameter.type_name is not None:
                    argument_value = self.interpreter._coerce_typed_array(
                        parameter.type_name,
                        argument_value,
                        f"parameter '{parameter.name}'",
                    )
                    if self.interpreter._needs_runtime_type_check(
                        parameter.type_name
                    ):
                        argument_value = self.interpreter._coerce_runtime_checked_type(
                            parameter.type_name,
                            argument_value,
                            f"parameter '{parameter.name}'",
                        )
                    argument_value = self.interpreter._coerce_typed_object(
                        parameter.type_name,
                        argument_value,
                        f"parameter '{parameter.name}'",
                    )
                parameter_array_type = (
                    parameter.type_name
                    if parameter.type_name is not None
                    and parameter.type_name.endswith("[]")
                    else None
                )
                call_environment.define(
                    parameter.name,
                    argument_value,
                    array_type=parameter_array_type,
                    object_type=(
                        parameter.type_name
                        if parameter.type_name is not None
                        and parameter.type_name.startswith("object<")
                        else None
                    ),
                    value_type=(
                        parameter.type_name
                        if parameter.type_name is not None
                        and self.interpreter._needs_runtime_type_check(
                            parameter.type_name
                        )
                        else None
                    ),
                )
        try:
            self.interpreter._execute_block(self.declaration.body, call_environment)
        except ReturnSignal as returned:
            return returned.value
        except (RuntimeErrorX, ThrownValue) as error:
            self.interpreter.annotate_error(error)
            raise
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
    nested_types: dict[str, XClass] = field(default_factory=dict)
    traced: bool = False
    enclosing_class: XClass | None = None
    is_exception_base: bool = False

    @property
    def name(self) -> str:
        return self.declaration.name

    def find_methods(self, name: str) -> list[FunctionDeclaration]:
        methods = [
            member
            for member in self.declaration.members
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
                method
                for method in inherited_methods
                if tuple(parameter.type_name for parameter in method.parameters)
                not in own_signatures
            )
        return methods

    def find_constructors(self) -> list[FunctionDeclaration]:
        return [
            member
            for member in self.declaration.members
            if isinstance(member, FunctionDeclaration) and member.name == self.name
        ]

    def construct(self, arguments: list[Any]) -> XInstance:
        if self.traced:
            self.interpreter.output(f"Constructing {self.name}")
        instance = XInstance(self)
        self.interpreter._initialize_fields(instance, self)
        
        # Check for custom constructor implementation (for Python class wrappers)
        if hasattr(self, 'constructor_impl'):
            self.constructor_impl(instance, arguments)
            return instance
        
        if self.is_exception_base:
            self.interpreter._initialize_exception_instance(instance, arguments)
            return instance
        constructors = self.find_constructors()
        if constructors:
            constructor = self.interpreter._select_overload(
                self.name, constructors, arguments
            )
            constructor_function = XFunction(
                constructor, self.closure, self.interpreter, instance, self
            )
            constructor_function = self.interpreter._apply_function_decorators(
                constructor.decorators, constructor_function, self.closure
            )
            constructor_function.call(arguments)
        elif self.parent is not None and self.parent.is_exception_base:
            self.interpreter._initialize_exception_instance(instance, arguments)
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
    enum_identity: object


class XCollectionInstance:
    """An OOP-style collection instance that supports dot-method calls.
    
    `students.add(x)` is sugar for `List.add(students, x)`.
    The underlying data is a plain list or dict stored in `_data`.
    The `_methods` dict maps method names to BuiltinFunctions that
    already expect (instance, arguments) style — the interpreter
    pre-binds `_data` when dispatching.
    """

    def __init__(self, collection_type: str, data: Any, methods: dict) -> None:
        self.collection_type = collection_type  # e.g. "Stack", "List"
        self._data = data                        # the underlying list / dict
        self._methods = methods                  # name -> BuiltinFunction


@dataclass
class XExceptionValue:
    message: str
    name: str = "Exception"
    cause: Any = None
    stack: str = ""


@dataclass
class XThreadHandle:
    thread: threading.Thread
    result_value: Any = None
    error: BaseException | None = None


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


if TYPE_CHECKING:
    from .interpreter import Interpreter


def __getattr__(name: str) -> Any:
    if name == "Interpreter":
        from .interpreter import Interpreter

        return Interpreter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
