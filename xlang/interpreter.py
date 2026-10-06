"""
X language interpreter with module namespace support.

Module imports create Environment-backed namespace objects containing
exported declarations accessible via dot access. Flattened top-level
bindings are preserved only when they do not create collisions between
different declarations; when flattening would introduce a conflicting
binding for an existing name, a RuntimeErrorX is raised. This prevents
silent cross-module name collisions while maintaining backward
compatibility where safe.
"""

from __future__ import annotations

import asyncio
import functools
import heapq
import inspect
import os
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable

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
    FunctionExpression,
    ImportDeclaration,
    ImportAlias,
    ImportNamespaceAlias,
    ImportNamespaceAlias,
    Identifier,
    IfStatement,
    Index,
    Literal,
    LiteralPattern,
    MatchExpression,
    Member,
    NewExpression,
    NamespaceDeclaration,
    ObjectLiteral,
    OptionalChain,
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
from .config import XConfig
from .diagnostics import SourceWarning
from .runtime import (
    BuiltinFunction,
    Environment,
    LoopSignal,
    OverloadedFunction,
    ReturnSignal,
    RuntimeErrorX,
    ThrownValue,
    UNDEFINED,
    XArray,
    XClass,
    XCollectionInstance,
    XEnumMember,
    XExceptionValue,
    XFunction,
    XInstance,
    XObject,
    XSuper,
    XThreadHandle,
)


class ComparatorItem:
    """Wrapper that makes arbitrary X-language values heap-orderable.

    When a custom comparator function is supplied to PriorityQueue.create,
    each enqueued value is wrapped in a ComparatorItem.  Python's heapq
    module calls ``__lt__`` to determine heap order, so we delegate the
    comparison to the user-supplied X function via ``call_fn``.
    """

    def __init__(
        self,
        value: Any,
        comparator_fn: Any,
        call_fn: Any,
    ) -> None:
        """Store the wrapped value, the comparator function, and the call dispatch."""
        self.value = value
        self.comparator_fn = comparator_fn
        self.call_fn = call_fn

    def __lt__(self, other: "ComparatorItem") -> bool:
        """Return True when self should be popped before other (i.e. self < other)."""
        result = self.call_fn(self.comparator_fn, [self.value, other.value])
        return (result or 0) < 0

    def __le__(self, other: "ComparatorItem") -> bool:
        """Return True when self <= other (heapq may call this in Python 3.12+)."""
        result = self.call_fn(self.comparator_fn, [self.value, other.value])
        return (result or 0) <= 0

    def __eq__(self, other: object) -> bool:
        """Equality by wrapped value identity."""
        if not isinstance(other, ComparatorItem):
            return NotImplemented
        return self.value == other.value  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return f"ComparatorItem({self.value!r})"


#: Dot-callable methods on plain X arrays (``myArray.map(cb)``).
#: Maps method name -> ``Interpreter`` method implementing the call.  Every
#: implementation receives the receiver as ``arguments[0]`` — the same shape
#: the HashMap/LinkedList builtins use — so ``List.map(array, cb)`` works too.
_ARRAY_METHODS: dict[str, str] = {
    "map": "_array_map",
    "filter": "_array_filter",
    "reduce": "_array_reduce",
    "forEach": "_array_for_each",
    "find": "_array_find",
    "some": "_array_some",
    "every": "_array_every",
    "indexOf": "_array_index_of",
    "contains": "_array_contains",
    "sort": "_array_sort",
    "reverse": "_array_reverse",
    "slice": "_array_slice",
    "concat": "_array_concat",
    "join": "_array_join",
    "first": "_array_first",
    "last": "_array_last",
    "isEmpty": "_array_is_empty",
    "clear": "_array_clear",
    "push": "_array_push",
    "pop": "_array_pop",
}

#: Dot-callable methods on X strings (``text.toUpperCase()``), keyed the same
#: way as ``_ARRAY_METHODS``.  Index arguments count Unicode code points,
#: matching the language's documented string-indexing behavior.
_STRING_METHODS: dict[str, str] = {
    "toUpperCase": "_string_to_upper_case",
    "toLowerCase": "_string_to_lower_case",
    "trim": "_string_trim",
    "startsWith": "_string_starts_with",
    "endsWith": "_string_ends_with",
    "contains": "_string_contains",
    "indexOf": "_string_index_of",
    "replace": "_string_replace",
    "replaceAll": "_string_replace_all",
    "split": "_string_split",
    "charAt": "_string_char_at",
    "substring": "_string_substring",
    "slice": "_string_slice",
    "repeat": "_string_repeat",
    "padStart": "_string_pad_start",
    "padEnd": "_string_pad_end",
    "isEmpty": "_string_is_empty",
    "toCharArray": "_string_to_char_array",
}


class Interpreter:
    EXCEPTION_PARENTS = {
        "Error": "Throwable",
        "Exception": "Throwable",
        "RuntimeException": "Exception",
        "ArithmeticException": "RuntimeException",
        "TypeException": "RuntimeException",
        "IllegalArgumentException": "RuntimeException",
        "IndexOutOfBoundsException": "RuntimeException",
        "IOException": "Exception",
        "FileSystemException": "IOException",
        "DatabaseException": "Exception",
        "DatabaseError": "Error",
    }

    #: Global names that only exist while a ``[features]`` flag is enabled.
    #: Used to turn "Name 'x' is not defined" into an actionable message.
    FEATURE_GLOBALS: dict[str, tuple[str, ...]] = {
        "collections": (
            "Collections",
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
            "ThreadSafeMap",
            "ThreadSafeSet",
        ),
        "threads": ("Thread",),
        "async": ("Async", "sleep"),
        "filesystem": ("FileSystem",),
        "object_literals": ("Object",),
        "decorators": ("trace",),
    }

    def __init__(
        self,
        arguments: list[str] | None = None,
        output: Callable[[str], None] = print,
        config: XConfig | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        self.config = config or XConfig()
        self.environment = dict(os.environ)
        if environment is not None:
            self.environment.update(environment)
        self.current_location: tuple[str | None, int | None, int | None] | None = None
        self.warnings: list[SourceWarning] = []
        self._warning_keys: set[tuple[str, str | None, int | None, int | None]] = set()
        self.function_stack: list[XFunction] = []
        self.globals = Environment()
        self.output = output
        self._install_builtins(arguments or [])

    def _validate_declarations(self, program: Program) -> None:
        """Pre-execution gate: unknown type names and interface conformance.

        Runs the checker's lightweight declaration pass and re-raises the
        first diagnostic as a ``RuntimeErrorX`` carrying ``line``/``column``/
        ``source_name`` so the CLI renders it like any other runtime error.
        """
        from .typecheck import TypeChecker

        errors = TypeChecker().check_declarations(program)
        if not errors:
            return
        first = errors[0]
        failure = RuntimeErrorX(first.message)
        failure.line = first.line
        failure.column = first.column
        failure.source_name = first.source_name
        raise failure

    def interpret(self, program: Program) -> Any:
        if self.config.enabled("type_checker"):
            self._validate_declarations(program)
        declarations = [declaration for declaration in program.declarations if declaration]
        has_top_level_statements = any(
            not isinstance(
                declaration,
                (
                    FunctionDeclaration,
                    ClassDeclaration,
                    EnumDeclaration,
                    NamespaceDeclaration,
                    ImportAlias,
                    ImportNamespaceAlias,
                    ImportDeclaration,
                    TypeDeclaration,
                    VariableDeclaration,
                ),
            )
            and not (
                isinstance(declaration, ExpressionStatement)
                and isinstance(declaration.expression, Identifier)
            )
            for declaration in declarations
        )
        for declaration in declarations:
            if isinstance(declaration, FunctionDeclaration):
                self._define_function(declaration, self.globals)
            elif isinstance(declaration, ClassDeclaration):
                self._define_class(declaration, self.globals)
            elif isinstance(declaration, EnumDeclaration):
                self._define_enum(declaration, self.globals)
            elif isinstance(declaration, NamespaceDeclaration):
                self._define_namespace(declaration, self.globals)

        for declaration in declarations:
            if isinstance(declaration, ImportAlias):
                imported_value = self._resolve_import(declaration.source_name)
                alias = declaration.alias_name
                # If the name already exists in globals (e.g. a builtin collection
                # short-name) allow the import to silently re-bind it.
                if alias in self.globals.values:
                    self.globals.values[alias] = imported_value
                else:
                    self.globals.define(alias, imported_value)
            elif isinstance(declaration, ImportNamespaceAlias):
                exported_values = {}
                for name in declaration.exported_names:
                    value = self.globals.get(name)
                    if isinstance(value, list) and all(
                        isinstance(function, XFunction) for function in value
                    ):
                        value = OverloadedFunction(name, value)
                    exported_values[name] = value
                self.globals.define(declaration.alias_name, exported_values)
            elif isinstance(declaration, VariableDeclaration):
                self._execute(declaration, self.globals)
            elif isinstance(declaration, TypeDeclaration):
                continue
            elif isinstance(
                declaration,
                (
                    FunctionDeclaration,
                    ClassDeclaration,
                    EnumDeclaration,
                    NamespaceDeclaration,
                    ImportDeclaration,
                ),
            ):
                continue
            else:
                self._execute(declaration, self.globals)

        if has_top_level_statements:
            return None
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
                result = self._select_overload("main", [main_function], [arguments]).call(
                    [arguments]
                )
                if inspect.isawaitable(result):
                    return asyncio.run(self._await_result(result))
                return result
            if main_function.declaration.parameters:
                raise RuntimeErrorX("main may accept zero parameters or one string[] parameter")
            result = main_function.call([])
            if inspect.isawaitable(result):
                return asyncio.run(self._await_result(result))
            return result
        return None

    async def _await_result(self, awaitable: Awaitable[Any]) -> Any:
        return await awaitable

    def _resolve_import(self, qualified_name: str) -> Any:
        parts = qualified_name.split(".")
        value = self._lookup(self.globals, parts[0])
        for part in parts[1:]:
            value = self._get_member(value, part)
        return value

    def _install_builtins(self, arguments: list[str]) -> None:
        self.globals.define("args", arguments)
        self.globals.define("print", BuiltinFunction("print", self._builtin_print))
        self.globals.define("range", BuiltinFunction("range", self._builtin_range))
        self.globals.define("typeOf", BuiltinFunction("typeOf", self._builtin_type_of))
        if self.config.enabled("async"):
            self.globals.define("sleep", BuiltinFunction("sleep", self._builtin_sleep))
        throwable = XClass(
            ClassDeclaration("Throwable", []),
            self,
            self.globals,
            is_exception_base=True,
        )
        self.globals.define("Throwable", throwable)
        for name in ("Exception", "Error"):
            self.globals.define(
                name,
                XClass(
                    ClassDeclaration(name, [], parent_name="Throwable"),
                    self,
                    self.globals,
                    throwable,
                    is_exception_base=True,
                ),
            )

        exception_types = (
            "RuntimeException",
            "ArithmeticException",
            "TypeException",
            "IllegalArgumentException",
            "IndexOutOfBoundsException",
            "FileSystemException",
            "IOException",
            "DatabaseException",
            "DatabaseError",
        )
        for exception_type in exception_types:
            self.globals.define(
                exception_type,
                BuiltinFunction(
                    exception_type,
                    lambda arguments, name=exception_type: self._builtin_exception(
                        name, arguments
                    ),
                ),
            )
        if self.config.enabled("decorators"):
            self.globals.define("trace", BuiltinFunction("trace", self._builtin_trace))
        if self.config.enabled("object_literals"):
            self.globals.define("Object", self._object_members())
        system_namespace = Environment()
        io_namespace = Environment(system_namespace)
        if self.config.enabled("filesystem"):
            io_namespace.define("FileSystem", self._filesystem_members())
        system_namespace.define("io", io_namespace)
        concurrent_namespace = Environment(system_namespace)
        if self.config.enabled("threads"):
            concurrent_namespace.define("Thread", self._thread_members())
        if self.config.enabled("async"):
            concurrent_namespace.define("Async", self._async_members())
        system_namespace.define("concurrent", concurrent_namespace)
        utils_namespace = Environment(system_namespace)
        collections_namespace = Environment(utils_namespace)
        if self.config.enabled("collections"):
            hashmap_ns       = self._make_collection_ns("HashMap",       self._hashmap_members())
            linkedlist_ns    = self._make_collection_ns("LinkedList",     self._linkedlist_members())
            stack_ns         = self._make_collection_ns("Stack",          self._stack_members())
            queue_ns         = self._make_collection_ns("Queue",          self._queue_members())
            priorityqueue_ns = self._make_collection_ns("PriorityQueue",  self._priorityqueue_members())
            trie_ns          = self._make_collection_ns("Trie",           self._trie_members())
            set_ns           = self._make_collection_ns("Set",            self._set_members())
            collections_namespace.define("HashMap",       hashmap_ns)
            collections_namespace.define("LinkedList",    linkedlist_ns)
            collections_namespace.define("List",          linkedlist_ns)      # alias
            collections_namespace.define("Stack",         stack_ns)
            collections_namespace.define("Queue",         queue_ns)
            collections_namespace.define("PriorityQueue", priorityqueue_ns)
            collections_namespace.define("Trie",          trie_ns)
            collections_namespace.define("Set",           set_ns)
            from .stdlib.extended_collections import build_namespaces

            for collection_name, collection_members in build_namespaces().items():
                collection_ns = self._make_collection_ns(
                    collection_name, collection_members
                )
                collections_namespace.define(collection_name, collection_ns)
                self.globals.define(collection_name, collection_ns)
            # Expose short names globally so Stack.create() works without import
            self.globals.define("HashMap",       hashmap_ns)
            self.globals.define("LinkedList",    linkedlist_ns)
            self.globals.define("List",          linkedlist_ns)      # List is an alias for LinkedList
            self.globals.define("Stack",         stack_ns)
            self.globals.define("Queue",         queue_ns)
            self.globals.define("PriorityQueue", priorityqueue_ns)
            self.globals.define("Trie",          trie_ns)
            self.globals.define("Set",           set_ns)
        utils_namespace.define("Collections", collections_namespace)
        system_namespace.define("utils", utils_namespace)
        environment_namespace = Environment(system_namespace)
        environment_namespace.define(
            "has", BuiltinFunction("Environment.has", self._environment_has)
        )
        environment_namespace.define(
            "all", BuiltinFunction("Environment.all", self._environment_all)
        )
        for name, value in self.environment.items():
            environment_namespace.values[name] = value
        system_namespace.define("Environment", environment_namespace)
        self.globals.define("System", system_namespace)

    def _environment_has(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1 or not isinstance(arguments[0], str):
            raise RuntimeErrorX("Environment.has expects one string key")
        return arguments[0] in self.environment

    def _environment_all(self, arguments: list[Any]) -> dict[str, str]:
        if arguments:
            raise RuntimeErrorX("Environment.all expects no arguments")
        return dict(self.environment)

    def _create_wrapper_class(self, name: str, python_class: type) -> XClass:
        """Create an X class that wraps a Python class"""
        from .ast_nodes import ClassDeclaration, FunctionDeclaration, VariableDeclaration, Block
        
        # Create a minimal X class declaration
        declaration = ClassDeclaration(name, [])
        
        # Add constructor
        constructor_decl = FunctionDeclaration("constructor", [], None, [], Block([]), False, False)
        declaration.members.append(constructor_decl)
        
        # Get all methods from Python class
        import inspect
        methods = inspect.getmembers(python_class, predicate=inspect.isfunction)
        
        for method_name, method_func in methods:
            if method_name.startswith('_'):
                continue
            
            # Get method signature
            sig = inspect.signature(method_func)
            params = []
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                params.append(VariableDeclaration(param_name, None, None, None, [], None, None))
            
            method_decl = FunctionDeclaration(method_name, params, None, [], Block([]), False, False)
            declaration.members.append(method_decl)
        
        # Create X class
        xclass = XClass(declaration, self, self.globals)
        
        # Store Python class reference
        xclass.python_class = python_class
        
        # Override construct to create Python instance
        def construct(this: XInstance, arguments: list[Any]) -> None:
            # Create Python instance
            python_instance = python_class(*arguments)
            this.fields["__python_instance__"] = python_instance
        
        # Store constructor
        xclass.constructor_impl = construct
        
        # Store method implementations
        xclass.method_impls = {}
        for method_name, method_func in methods:
            if method_name.startswith('_'):
                continue
            
            def make_method(func):
                def method_impl(this: XInstance, arguments: list[Any]) -> Any:
                    python_instance = this.fields.get("__python_instance__")
                    if python_instance is None:
                        raise RuntimeErrorX(f"{name} instance not properly initialized")
                    return func(python_instance, *arguments)
                return method_impl
            
            xclass.method_impls[method_name] = make_method(method_func)
        
        return xclass

    def annotate_error(self, error: RuntimeErrorX | ThrownValue) -> None:
        if self.current_location is None or error.line is not None:
            return
        source_name, line, column = self.current_location
        error.source_name = source_name
        error.line = line
        error.column = column

    def warn(self, message: str) -> None:
        """Record a yellow warning at the current source location.

        Warnings are deduplicated by message and location so that a warning
        raised inside a hot loop is reported once instead of once per turn.
        """
        source_name, line, column = self.current_location or (None, None, None)
        key = (message, source_name, line, column)
        if key in self._warning_keys:
            return
        self._warning_keys.add(key)
        self.warnings.append(
            SourceWarning(message, source_name or "<unknown>", line, column)
        )

    def _disabled_feature_for(self, name: str) -> str | None:
        """Return the disabled feature that would provide ``name``, if any."""
        for feature, names in self.FEATURE_GLOBALS.items():
            if name in names and not self.config.enabled(feature):
                return feature
        return None

    def undefined_name_error(self, name: str) -> RuntimeErrorX:
        """Build the "name is not defined" error, mentioning a disabled feature."""
        feature = self._disabled_feature_for(name)
        message = f"Name '{name}' is not defined"
        if feature is not None:
            message += f" because the '{feature}' feature is disabled in x.toml"
        error = RuntimeErrorX(message)
        self.annotate_error(error)
        return error

    def _lookup(self, environment: Environment, name: str) -> Any:
        try:
            return environment.get(name)
        except RuntimeErrorX as error:
            raise self.undefined_name_error(name) from error

    def _source_stack(
        self, source_name: str | None, line: int | None, column: int | None
    ) -> str:
        if source_name is None or line is None:
            return ""
        return f"at {source_name}:{line}:{column or 1}"

    def _builtin_trace(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("@trace expects one function or class")
        target = arguments[0]
        if isinstance(target, XFunction):
            target.traced = True
            return target
        if isinstance(target, XClass):
            target.traced = True
            return target
        raise RuntimeErrorX("@trace can only decorate a function or class")

    def _object_members(self) -> Environment:
        object_namespace = Environment()
        object_namespace.define("keys", BuiltinFunction("Object.keys", self._object_keys))
        object_namespace.define(
            "values", BuiltinFunction("Object.values", self._object_values)
        )
        object_namespace.define(
            "entries", BuiltinFunction("Object.entries", self._object_entries)
        )
        object_namespace.define(
            "assign", BuiltinFunction("Object.assign", self._object_assign)
        )
        object_namespace.define(
            "hasOwn", BuiltinFunction("Object.hasOwn", self._object_has_own)
        )
        return object_namespace

    def _object_record(self, operation: str, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) != 1 or not isinstance(arguments[0], dict):
            raise RuntimeErrorX(f"Object.{operation} expects one object")
        return arguments[0]

    def _object_keys(self, arguments: list[Any]) -> list[str]:
        return list(self._object_record("keys", arguments).keys())

    def _object_values(self, arguments: list[Any]) -> list[Any]:
        return list(self._object_record("values", arguments).values())

    def _object_entries(self, arguments: list[Any]) -> list[list[Any]]:
        return [
            [key, value]
            for key, value in self._object_record("entries", arguments).items()
        ]

    def _object_assign(self, arguments: list[Any]) -> dict[str, Any]:
        if not arguments or not isinstance(arguments[0], dict):
            raise RuntimeErrorX("Object.assign expects a target object")
        target = arguments[0]
        for source in arguments[1:]:
            if not isinstance(source, dict):
                raise RuntimeErrorX("Object.assign sources must be objects")
            target.update(source)
        return target

    def _object_has_own(self, arguments: list[Any]) -> bool:
        if (
            len(arguments) != 2
            or not isinstance(arguments[0], dict)
            or not isinstance(arguments[1], str)
        ):
            raise RuntimeErrorX("Object.hasOwn expects an object and a string key")
        return arguments[1] in arguments[0]

    def _thread_members(self) -> dict[str, BuiltinFunction]:
        return {
            "start": BuiltinFunction("Thread.start", self._thread_start),
        }

    def _async_members(self) -> dict[str, BuiltinFunction]:
        return {
            "delay": BuiltinFunction("Async.delay", self._async_delay),
            "all": BuiltinFunction("Async.all", self._async_all),
        }

    def _builtin_sleep(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX(f"sleep expects one argument, got {len(arguments)}")
        milliseconds = arguments[0]
        self._validate_milliseconds("sleep", milliseconds)

        async def wait() -> None:
            await asyncio.sleep(milliseconds / 1000)

        return wait()

    def _thread_start(self, arguments: list[Any]) -> XThreadHandle:
        if len(arguments) not in (1, 2):
            raise RuntimeErrorX("Thread.start expects a function and optional argument array")
        function = arguments[0]
        function_arguments = [] if len(arguments) == 1 else arguments[1]
        if not isinstance(function, (XFunction, OverloadedFunction)):
            raise RuntimeErrorX("Thread.start expects an X function")
        if not isinstance(function_arguments, list):
            raise RuntimeErrorX("Thread.start arguments must be an array")

        handle = XThreadHandle(threading.Thread())

        def run_thread() -> None:
            try:
                thread_result = self._call(function, function_arguments)
                if inspect.isawaitable(thread_result):
                    thread_result = asyncio.run(self._await_result(thread_result))
                handle.result_value = thread_result
            except Exception as error:
                handle.error = error

        handle.thread = threading.Thread(target=run_thread, daemon=False)
        handle.thread.start()
        return handle

    def _async_delay(self, arguments: list[Any]) -> Any:
        if len(arguments) not in (1, 2):
            raise RuntimeErrorX("Async.delay expects milliseconds and optional result")
        milliseconds = arguments[0]
        self._validate_milliseconds("Async.delay", milliseconds)
        result = None if len(arguments) == 1 else arguments[1]

        async def delay() -> Any:
            await asyncio.sleep(milliseconds / 1000)
            return result

        return delay()

    def _validate_milliseconds(self, operation: str, milliseconds: Any) -> None:
        if not isinstance(milliseconds, (int, float)) or isinstance(milliseconds, bool):
            raise RuntimeErrorX(
                f"{operation} duration must be a number of milliseconds"
            )
        if milliseconds < 0:
            raise RuntimeErrorX(f"{operation} duration cannot be negative")

    def _async_all(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1 or not isinstance(arguments[0], list):
            raise RuntimeErrorX("Async.all expects one array of async results")
        tasks = arguments[0]

        async def wait_for_all() -> list[Any]:
            resolved_values: list[Any] = []
            for task in tasks:
                if inspect.isawaitable(task):
                    resolved_values.append(task)
                else:
                    async def resolved(value: Any = task) -> Any:
                        return value
                    resolved_values.append(resolved())
            return list(await asyncio.gather(*resolved_values))

        return wait_for_all()

    def _filesystem_members(self) -> dict[str, BuiltinFunction]:
        members = {
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
        asynchronous_operations = {
            "existsAsync": ("exists", self._filesystem_exists),
            "isFileAsync": ("isFile", self._filesystem_is_file),
            "isDirectoryAsync": ("isDirectory", self._filesystem_is_directory),
            "readTextAsync": ("readText", self._filesystem_read_text),
            "writeTextAsync": ("writeText", self._filesystem_write_text),
            "appendTextAsync": ("appendText", self._filesystem_append_text),
            "createDirectoryAsync": (
                "createDirectory",
                self._filesystem_create_directory,
            ),
            "listDirectoryAsync": ("listDirectory", self._filesystem_list_directory),
            "deleteFileAsync": ("deleteFile", self._filesystem_delete_file),
            "deleteDirectoryAsync": (
                "deleteDirectory",
                self._filesystem_delete_directory,
            ),
        }
        for asynchronous_name, (operation_name, operation) in (
            asynchronous_operations.items()
        ):
            members[asynchronous_name] = BuiltinFunction(
                f"FileSystem.{asynchronous_name}",
                lambda arguments, sync_operation=operation: self._filesystem_async_call(
                    sync_operation, arguments
                ),
            )
        return members

    async def _filesystem_async_call(
        self,
        operation: Callable[[list[Any]], Any],
        arguments: list[Any],
    ) -> Any:
        return await asyncio.to_thread(operation, arguments)

    def _filesystem_path(
        self, operation: str, arguments: list[Any]
    ) -> Path:
        self._validate_argument_count(operation, arguments, 1)
        path_value = arguments[0]
        if not isinstance(path_value, str):
            raise RuntimeErrorX(
                f"FileSystem.{operation} expects a string path",
                "TypeException",
            )
        return Path(path_value)

    def _filesystem_exists(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("exists", arguments)
        try:
            return path.exists()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot check whether '{path}' exists: {error}",
                "FileSystemException",
            ) from error

    def _filesystem_is_file(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("isFile", arguments)
        try:
            return path.is_file()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot check whether '{path}' is a file: {error}",
                "FileSystemException",
            ) from error

    def _filesystem_is_directory(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("isDirectory", arguments)
        try:
            return path.is_dir()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot check whether '{path}' is a directory: {error}",
                "FileSystemException",
            ) from error

    def _filesystem_read_text(self, arguments: list[Any]) -> str:
        path = self._filesystem_path("readText", arguments)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(
                f"Cannot read text file '{path}': {error}",
                "FileSystemException",
            ) from error

    def _filesystem_write_text(self, arguments: list[Any]) -> None:
        self._validate_argument_count("writeText", arguments, 2)
        path_value, text = arguments
        if not isinstance(path_value, str):
            raise RuntimeErrorX(
                "FileSystem.writeText expects a string path", "TypeException"
            )
        if not isinstance(text, str):
            raise RuntimeErrorX(
                "FileSystem.writeText expects string content", "TypeException"
            )
        path = Path(path_value)
        try:
            path.write_text(text, encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(
                f"Cannot write text file '{path}': {error}",
                "FileSystemException",
            ) from error
        return None

    def _filesystem_append_text(self, arguments: list[Any]) -> None:
        self._validate_argument_count("appendText", arguments, 2)
        path_value, text = arguments
        if not isinstance(path_value, str):
            raise RuntimeErrorX(
                "FileSystem.appendText expects a string path", "TypeException"
            )
        if not isinstance(text, str):
            raise RuntimeErrorX(
                "FileSystem.appendText expects string content", "TypeException"
            )
        path = Path(path_value)
        try:
            with path.open("a", encoding="utf-8") as output_file:
                output_file.write(text)
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(
                f"Cannot append to text file '{path}': {error}",
                "FileSystemException",
            ) from error
        return None

    def _filesystem_create_directory(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("createDirectory", arguments)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot create directory '{path}': {error}",
                "FileSystemException",
            ) from error
        return None

    def _filesystem_list_directory(self, arguments: list[Any]) -> list[str]:
        path = self._filesystem_path("listDirectory", arguments)
        try:
            return sorted(entry.name for entry in path.iterdir())
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot list directory '{path}': {error}",
                "FileSystemException",
            ) from error

    def _filesystem_delete_file(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("deleteFile", arguments)
        try:
            path.unlink()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot delete file '{path}': {error}",
                "FileSystemException",
            ) from error
        return None

    def _filesystem_delete_directory(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("deleteDirectory", arguments)
        try:
            path.rmdir()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot delete directory '{path}'; it must be empty: {error}",
                "FileSystemException",
            ) from error
        return None

    def _hashmap_members(self) -> dict[str, BuiltinFunction]:
        return {
            "create": BuiltinFunction("HashMap.create", self._hashmap_create),
            "set": BuiltinFunction("HashMap.set", self._hashmap_set),
            "get": BuiltinFunction("HashMap.get", self._hashmap_get),
            "has": BuiltinFunction("HashMap.has", self._hashmap_has),
            "remove": BuiltinFunction("HashMap.remove", self._hashmap_remove),
            "size": BuiltinFunction("HashMap.size", self._hashmap_size),
            "isEmpty": BuiltinFunction("HashMap.isEmpty", self._hashmap_is_empty),
            "clear": BuiltinFunction("HashMap.clear", self._hashmap_clear),
            "keys": BuiltinFunction("HashMap.keys", self._hashmap_keys),
            "values": BuiltinFunction("HashMap.values", self._hashmap_values),
            "entries": BuiltinFunction("HashMap.entries", self._hashmap_entries),
            "merge": BuiltinFunction("HashMap.merge", self._hashmap_merge),
            "filter": BuiltinFunction("HashMap.filter", self._hashmap_filter),
            "map": BuiltinFunction("HashMap.map", self._hashmap_map),
            "reduce": BuiltinFunction("HashMap.reduce", self._hashmap_reduce),
            "getOrDefault": BuiltinFunction("HashMap.getOrDefault", self._hashmap_get_or_default),
            "computeIfAbsent": BuiltinFunction("HashMap.computeIfAbsent", self._hashmap_compute_if_absent),
            "computeIfPresent": BuiltinFunction("HashMap.computeIfPresent", self._hashmap_compute_if_present),
            "putAll": BuiltinFunction("HashMap.putAll", self._hashmap_put_all),
        }

    def _hashmap_create(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("HashMap.create accepts at most one argument (initial capacity)")
        initial_capacity = arguments[0] if arguments else 16
        if not isinstance(initial_capacity, int) or initial_capacity < 1:
            raise RuntimeErrorX("HashMap.create initial capacity must be a positive integer")
        return {}  # Python dict already provides hash map functionality

    def _hashmap_set(self, arguments: list[Any]) -> None:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.set expects hashmap, key, and value arguments")
        hashmap, key, value = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.set expects a HashMap instance")
        if not isinstance(key, (str, int, float, bool)):
            raise RuntimeErrorX("HashMap keys must be strings, numbers, or booleans")
        hashmap[str(key)] = value
        return None

    def _hashmap_get(self, arguments: list[Any]) -> Any:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.get expects key argument")
        hashmap, key = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.get expects a HashMap instance")
        return hashmap.get(str(key))

    def _hashmap_has(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.has expects key argument")
        hashmap, key = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.has expects a HashMap instance")
        return str(key) in hashmap

    def _hashmap_remove(self, arguments: list[Any]) -> Any:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.remove expects key argument")
        hashmap, key = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.remove expects a HashMap instance")
        return hashmap.pop(str(key), None)

    def _hashmap_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.size expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.size expects a HashMap instance")
        return len(hashmap)

    def _hashmap_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.isEmpty expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.isEmpty expects a HashMap instance")
        return len(hashmap) == 0

    def _hashmap_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.clear expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.clear expects a HashMap instance")
        hashmap.clear()
        return None

    def _hashmap_keys(self, arguments: list[Any]) -> list[str]:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.keys expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.keys expects a HashMap instance")
        return list(hashmap.keys())

    def _hashmap_values(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.values expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.values expects a HashMap instance")
        return list(hashmap.values())

    def _hashmap_entries(self, arguments: list[Any]) -> list[list[Any]]:
        if len(arguments) != 1:
            raise RuntimeErrorX("HashMap.entries expects no arguments")
        hashmap = arguments[0]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.entries expects a HashMap instance")
        return [[key, value] for key, value in hashmap.items()]

    def _hashmap_merge(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) < 2:
            raise RuntimeErrorX("HashMap.merge expects at least one other HashMap")
        hashmap = self._unwrap_collection(arguments[0])
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.merge expects a HashMap instance")
        result = dict(hashmap)
        for other in arguments[1:]:
            other = self._unwrap_collection(other)
            if not isinstance(other, dict):
                raise RuntimeErrorX("HashMap.merge all arguments must be HashMaps")
            result.update(other)
        return result

    def _normalize_callable(self, value: Any, context: str) -> Any:
        """Normalize a callable value: unwrap list[XFunction] into OverloadedFunction."""
        if isinstance(value, list) and value and all(isinstance(f, XFunction) for f in value):
            return OverloadedFunction(context, value)
        return value

    def _unwrap_collection(self, value: Any) -> Any:
        """Unwrap an XCollectionInstance to its underlying data (list or dict)."""
        if isinstance(value, XCollectionInstance):
            return value._data
        return value

    def _make_collection_ns(self, type_name: str, members: dict) -> dict:
        """Wrap a collection method dict so that `new Stack()` returns an
        XCollectionInstance and instance dot-calls work on it.

        The raw `create` builtin receives a plain list/dict as first argument
        from the functional API.  We replace it with one that returns an
        XCollectionInstance wrapping that data, and also wrap every other
        method so it transparently unpacks the instance's _data before
        delegating to the original builtin.
        """
        raw_create = members["create"]

        def instance_create(arguments: list) -> XCollectionInstance:
            data = raw_create.call(arguments)
            return XCollectionInstance(type_name, data, wrapped)

        wrapped: dict = {}
        for method_name, builtin in members.items():
            if method_name == "create":
                continue
            original = builtin

            def make_wrapper(orig: BuiltinFunction, mname: str) -> BuiltinFunction:
                def dispatch(arguments: list) -> Any:
                    # If first arg is an XCollectionInstance, unwrap it
                    if arguments and isinstance(arguments[0], XCollectionInstance):
                        return orig.call([arguments[0]._data] + arguments[1:])
                    return orig.call(arguments)
                return BuiltinFunction(f"{type_name}.{mname}", dispatch)

            wrapped[method_name] = make_wrapper(original, method_name)

        wrapped["create"] = BuiltinFunction(f"{type_name}.create", instance_create)
        return wrapped

    def _hashmap_filter(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.filter expects a predicate function")
        hashmap, predicate = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.filter expects a HashMap instance")
        predicate = self._normalize_callable(predicate, "filter")
        if not isinstance(predicate, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.filter predicate must be a function")
        result = {}
        for key, value in hashmap.items():
            try:
                if predicate.call([[key, value]]) if isinstance(predicate, (XFunction, BuiltinFunction)) else self._call(predicate, [[key, value]]):
                    result[key] = value
            except Exception:
                pass
        return result

    def _hashmap_map(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.map expects a mapper function")
        hashmap, mapper = arguments[0], arguments[1]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.map expects a HashMap instance")
        mapper = self._normalize_callable(mapper, "map")
        if not isinstance(mapper, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.map mapper must be a function")
        result = {}
        for key, value in hashmap.items():
            try:
                mapped = self._call(mapper, [[key, value]])
                if isinstance(mapped, list) and len(mapped) == 2:
                    result[str(mapped[0])] = mapped[1]
            except Exception:
                pass
        return result

    def _hashmap_reduce(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.reduce expects an initial value and reducer function")
        hashmap, initial, reducer = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.reduce expects a HashMap instance")
        reducer = self._normalize_callable(reducer, "reduce")
        if not isinstance(reducer, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.reduce reducer must be a function")
        accumulator = initial
        for key, value in hashmap.items():
            try:
                accumulator = self._call(reducer, [accumulator, [key, value]])
            except Exception:
                pass
        return accumulator

    def _hashmap_get_or_default(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.getOrDefault expects key and default value")
        hashmap, key, default = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.getOrDefault expects a HashMap instance")
        return hashmap.get(str(key), default)

    def _hashmap_compute_if_absent(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.computeIfAbsent expects key and mapping function")
        hashmap, key, mapping_func = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.computeIfAbsent expects a HashMap instance")
        mapping_func = self._normalize_callable(mapping_func, "computeIfAbsent")
        if not isinstance(mapping_func, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.computeIfAbsent mapping function must be a function")
        key_str = str(key)
        if key_str not in hashmap:
            try:
                hashmap[key_str] = self._call(mapping_func, [key])
            except Exception:
                pass
        return hashmap.get(key_str)

    def _hashmap_compute_if_present(self, arguments: list[Any]) -> Any:
        if len(arguments) != 3:
            raise RuntimeErrorX("HashMap.computeIfPresent expects key and remapping function")
        hashmap, key, remapping_func = arguments[0], arguments[1], arguments[2]
        if not isinstance(hashmap, dict):
            raise RuntimeErrorX("HashMap.computeIfPresent expects a HashMap instance")
        remapping_func = self._normalize_callable(remapping_func, "computeIfPresent")
        if not isinstance(remapping_func, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("HashMap.computeIfPresent remapping function must be a function")
        key_str = str(key)
        if key_str in hashmap:
            try:
                new_value = self._call(remapping_func, [key, hashmap[key_str]])
                if new_value is not None:
                    hashmap[key_str] = new_value
                else:
                    del hashmap[key_str]
            except Exception:
                pass
        return hashmap.get(key_str)

    def _hashmap_put_all(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("HashMap.putAll expects another HashMap")
        hashmap = self._unwrap_collection(arguments[0])
        other = self._unwrap_collection(arguments[1])
        if not isinstance(hashmap, dict) or not isinstance(other, dict):
            raise RuntimeErrorX("HashMap.putAll expects HashMap instances")
        hashmap.update(other)
        return None

    # ------------------------------------------------------------------
    # Array methods (myArray.map(cb), List.map(array, cb))
    # ------------------------------------------------------------------

    def _array_receiver(self, arguments: list[Any], name: str) -> list[Any]:
        """Return the array bound as ``arguments[0]`` for method *name*."""
        if not arguments:
            raise RuntimeErrorX(f"Array.{name} expects an array instance")
        receiver = self._unwrap_collection(arguments[0])
        if not isinstance(receiver, list):
            raise RuntimeErrorX(f"Array.{name} expects an array instance")
        return receiver

    def _require_callback(self, value: Any, message: str) -> Any:
        """Normalize *value* (overload lists) and require a callable result."""
        callback = self._normalize_callable(value, "callback")
        if isinstance(callback, (XFunction, BuiltinFunction, OverloadedFunction)):
            return callback
        raise RuntimeErrorX(message)

    def _call_callback(self, callback: Any, arguments: list[Any], context: str) -> Any:
        """Call *callback* with *arguments*, offering only what it declares.

        ``XFunction.call`` rejects surplus arguments, so a one-parameter
        callback such as ``(int n) => n * 2`` must not be handed the index
        argument that two-parameter callbacks accept.
        """
        if isinstance(callback, BuiltinFunction):
            return callback.call(arguments)
        if isinstance(callback, XFunction):
            parameters = callback.declaration.parameters
            if parameters and parameters[-1].is_rest:
                return callback.call(arguments)
            return callback.call(arguments[: len(parameters)])
        if isinstance(callback, OverloadedFunction):
            for count in range(len(arguments), -1, -1):
                if any(
                    self._accepts_argument_count(function.declaration.parameters, count)
                    for function in callback.functions
                ):
                    return self._call(callback, arguments[:count])
            raise RuntimeErrorX(
                f"No overload of {context} accepts {len(arguments)} argument(s)"
            )
        raise RuntimeErrorX(f"{context} must be a function")

    def _natural_sort_key(self, value: Any) -> tuple[int, Any]:
        """Natural ordering key used by ``sort()`` without a callback.

        Numbers sort numerically, then booleans, then strings lexicographically;
        anything else falls back to its printed form so a mixed array never
        fails to compare.
        """
        if isinstance(value, bool):
            return (1, float(value))
        if isinstance(value, (int, float)):
            return (0, float(value))
        if isinstance(value, str):
            return (2, value)
        return (3, self._stringify(value))

    def _slice_bounds(
        self, start_value: Any, end_value: Any, length: int, label: str
    ) -> tuple[int, int]:
        """Normalize JS-style slice bounds: negatives count from the end and
        both bounds clamp into ``[0, length]``."""
        def normalize(value: Any, default: int) -> int:
            if value is None:
                return default
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuntimeErrorX(f"{label} indices must be integers")
            index = value if value >= 0 else length + value
            return max(0, min(length, index))

        return normalize(start_value, 0), normalize(end_value, length)

    def _array_map(self, arguments: list[Any]) -> list[Any]:
        """``map(callback)`` — a new array of ``callback(value, index)`` results."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.map expects a callback function")
        array = self._array_receiver(arguments, "map")
        mapper = self._require_callback(
            arguments[1], "Array.map callback must be a function"
        )
        return [
            self._call_callback(mapper, [value, index], "Array.map callback")
            for index, value in enumerate(array)
        ]

    def _array_filter(self, arguments: list[Any]) -> list[Any]:
        """``filter(callback)`` — elements whose callback result is truthy."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.filter expects a callback function")
        array = self._array_receiver(arguments, "filter")
        predicate = self._require_callback(
            arguments[1], "Array.filter callback must be a function"
        )
        return [
            value
            for index, value in enumerate(array)
            if self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.filter callback")
            )
        ]

    def _array_reduce(self, arguments: list[Any]) -> Any:
        """``reduce(callback, initialValue?)`` — fold the array into one value.

        Without an initial value the first element seeds the accumulator, so
        reducing an empty array that way is an error.
        """
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX(
                "Array.reduce expects a callback function and an optional initial value"
            )
        array = self._array_receiver(arguments, "reduce")
        reducer = self._require_callback(
            arguments[1], "Array.reduce callback must be a function"
        )
        if len(arguments) == 3:
            accumulator = arguments[2]
            start = 0
        else:
            if not array:
                raise RuntimeErrorX(
                    "Array.reduce of an empty array requires an initial value"
                )
            accumulator = array[0]
            start = 1
        for index in range(start, len(array)):
            accumulator = self._call_callback(
                reducer, [accumulator, array[index], index], "Array.reduce callback"
            )
        return accumulator

    def _array_for_each(self, arguments: list[Any]) -> None:
        """``forEach(callback)`` — run the callback for its side effects."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.forEach expects a callback function")
        array = self._array_receiver(arguments, "forEach")
        visitor = self._require_callback(
            arguments[1], "Array.forEach callback must be a function"
        )
        for index, value in enumerate(array):
            self._call_callback(visitor, [value, index], "Array.forEach callback")
        return None

    def _array_find(self, arguments: list[Any]) -> Any:
        """``find(callback)`` — first matching element, or null when none match."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.find expects a callback function")
        array = self._array_receiver(arguments, "find")
        predicate = self._require_callback(
            arguments[1], "Array.find callback must be a function"
        )
        for index, value in enumerate(array):
            if self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.find callback")
            ):
                return value
        return None

    def _array_some(self, arguments: list[Any]) -> bool:
        """``some(callback)`` — true when at least one element matches."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.some expects a callback function")
        array = self._array_receiver(arguments, "some")
        predicate = self._require_callback(
            arguments[1], "Array.some callback must be a function"
        )
        for index, value in enumerate(array):
            if self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.some callback")
            ):
                return True
        return False

    def _array_every(self, arguments: list[Any]) -> bool:
        """``every(callback)`` — true when all elements match (vacuously on [])."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.every expects a callback function")
        array = self._array_receiver(arguments, "every")
        predicate = self._require_callback(
            arguments[1], "Array.every callback must be a function"
        )
        for index, value in enumerate(array):
            if not self._is_truthy(
                self._call_callback(predicate, [value, index], "Array.every callback")
            ):
                return False
        return True

    def _array_index_of(self, arguments: list[Any]) -> int:
        """``indexOf(value)`` — index of the first strict match, or -1."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.indexOf expects a value argument")
        array = self._array_receiver(arguments, "indexOf")
        sought = arguments[1]
        for index, value in enumerate(array):
            if self._strict_equal(value, sought):
                return index
        return -1

    def _array_contains(self, arguments: list[Any]) -> bool:
        """``contains(value)`` — whether a strict match exists."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.contains expects a value argument")
        array = self._array_receiver(arguments, "contains")
        sought = arguments[1]
        return any(self._strict_equal(value, sought) for value in array)

    def _array_sort(self, arguments: list[Any]) -> list[Any]:
        """Stable in-place sort; returns the array, like JavaScript.

        With no callback, values order naturally (numbers numerically, then
        booleans, then strings, then printed forms).  With a two-argument
        callback the result must be a number: negative/zero/positive, like
        ``Array.prototype.sort``.
        """
        if len(arguments) > 2:
            raise RuntimeErrorX("Array.sort accepts at most one callback")
        array = self._array_receiver(arguments, "sort")
        if len(arguments) == 2:
            comparator = self._require_callback(
                arguments[1], "Array.sort callback must be a function"
            )

            def compare(left: Any, right: Any) -> int:
                outcome = self._call_callback(
                    comparator, [left, right], "Array.sort callback"
                )
                if isinstance(outcome, bool) or not isinstance(outcome, (int, float)):
                    raise RuntimeErrorX("Array.sort callback must return a number")
                if outcome < 0:
                    return -1
                if outcome > 0:
                    return 1
                return 0

            array.sort(key=functools.cmp_to_key(compare))
        else:
            array.sort(key=self._natural_sort_key)
        return array

    def _array_reverse(self, arguments: list[Any]) -> list[Any]:
        """``reverse()`` — reverse in place and return the array."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.reverse expects no arguments")
        array = self._array_receiver(arguments, "reverse")
        array.reverse()
        return array

    def _array_slice(self, arguments: list[Any]) -> list[Any]:
        """``slice(start?, end?)`` — sub-array; negatives count from the end."""
        if len(arguments) > 3:
            raise RuntimeErrorX("Array.slice accepts a start and an end index")
        array = self._array_receiver(arguments, "slice")
        start, end = self._slice_bounds(
            arguments[1] if len(arguments) > 1 else None,
            arguments[2] if len(arguments) > 2 else None,
            len(array),
            "Array.slice",
        )
        return array[start:end]

    def _array_concat(self, arguments: list[Any]) -> list[Any]:
        """``concat(other)`` — a new array with *other* appended."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.concat expects one array argument")
        array = self._array_receiver(arguments, "concat")
        other = self._unwrap_collection(arguments[1])
        if not isinstance(other, list):
            raise RuntimeErrorX("Array.concat expects an array argument")
        return list(array) + list(other)

    def _array_join(self, arguments: list[Any]) -> str:
        """``join(separator?)`` — stringify elements and join them.

        The default separator is ``,``; null and undefined elements become
        empty strings, as in JavaScript.
        """
        if len(arguments) > 2:
            raise RuntimeErrorX("Array.join accepts at most one separator")
        array = self._array_receiver(arguments, "join")
        separator = ","
        if len(arguments) == 2:
            separator = arguments[1]
            if not isinstance(separator, str):
                raise RuntimeErrorX("Array.join separator must be a string")
        return separator.join(
            ""
            if element is None or element is UNDEFINED
            else self._stringify(element)
            for element in array
        )

    def _array_first(self, arguments: list[Any]) -> Any:
        """``first()`` — first element, or null when the array is empty."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.first expects no arguments")
        array = self._array_receiver(arguments, "first")
        return array[0] if array else None

    def _array_last(self, arguments: list[Any]) -> Any:
        """``last()`` — last element, or null when the array is empty."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.last expects no arguments")
        array = self._array_receiver(arguments, "last")
        return array[-1] if array else None

    def _array_is_empty(self, arguments: list[Any]) -> bool:
        """``isEmpty()`` — whether the array has no elements."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.isEmpty expects no arguments")
        array = self._array_receiver(arguments, "isEmpty")
        return len(array) == 0

    def _array_clear(self, arguments: list[Any]) -> None:
        """``clear()`` — remove every element in place."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.clear expects no arguments")
        array = self._array_receiver(arguments, "clear")
        array.clear()
        return None

    def _array_push(self, arguments: list[Any]) -> None:
        """``push(value)`` — append one element in place (returns nothing)."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Array.push expects one value")
        array = self._array_receiver(arguments, "push")
        array.append(arguments[1])
        return None

    def _array_pop(self, arguments: list[Any]) -> Any:
        """``pop()`` — remove and return the last element."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Array.pop expects no arguments")
        array = self._array_receiver(arguments, "pop")
        if not array:
            raise RuntimeErrorX("Array.pop: array is empty")
        return array.pop()

    # ------------------------------------------------------------------
    # String methods (text.toUpperCase())
    # ------------------------------------------------------------------

    def _string_receiver(self, arguments: list[Any], name: str) -> str:
        """Return the string bound as ``arguments[0]`` for method *name*."""
        if not arguments or not isinstance(arguments[0], str):
            raise RuntimeErrorX(f"String.{name} expects a string instance")
        return arguments[0]

    def _string_index_argument(
        self, arguments: list[Any], position: int, label: str
    ) -> int:
        """Validate an integer index argument at *position*."""
        if len(arguments) <= position:
            raise RuntimeErrorX(f"{label} expects an index argument")
        value = arguments[position]
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeErrorX(f"{label} index must be an integer")
        return value

    def _string_to_upper_case(self, arguments: list[Any]) -> str:
        """``toUpperCase()`` — Unicode-aware upper-casing."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.toUpperCase expects no arguments")
        return self._string_receiver(arguments, "toUpperCase").upper()

    def _string_to_lower_case(self, arguments: list[Any]) -> str:
        """``toLowerCase()`` — Unicode-aware lower-casing."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.toLowerCase expects no arguments")
        return self._string_receiver(arguments, "toLowerCase").lower()

    def _string_trim(self, arguments: list[Any]) -> str:
        """``trim()`` — drop leading and trailing whitespace."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.trim expects no arguments")
        return self._string_receiver(arguments, "trim").strip()

    def _string_starts_with(self, arguments: list[Any]) -> bool:
        """``startsWith(prefix)`` — whether the string begins with *prefix*."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.startsWith expects a prefix argument")
        text = self._string_receiver(arguments, "startsWith")
        prefix = arguments[1]
        if not isinstance(prefix, str):
            raise RuntimeErrorX("String.startsWith prefix must be a string")
        return text.startswith(prefix)

    def _string_ends_with(self, arguments: list[Any]) -> bool:
        """``endsWith(suffix)`` — whether the string ends with *suffix*."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.endsWith expects a suffix argument")
        text = self._string_receiver(arguments, "endsWith")
        suffix = arguments[1]
        if not isinstance(suffix, str):
            raise RuntimeErrorX("String.endsWith suffix must be a string")
        return text.endswith(suffix)

    def _string_contains(self, arguments: list[Any]) -> bool:
        """``contains(part)`` — whether *part* occurs anywhere in the string."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.contains expects a part argument")
        text = self._string_receiver(arguments, "contains")
        part = arguments[1]
        if not isinstance(part, str):
            raise RuntimeErrorX("String.contains part must be a string")
        return part in text

    def _string_index_of(self, arguments: list[Any]) -> int:
        """``indexOf(part)`` — code-point index of the first match, or -1."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.indexOf expects a part argument")
        text = self._string_receiver(arguments, "indexOf")
        part = arguments[1]
        if not isinstance(part, str):
            raise RuntimeErrorX("String.indexOf part must be a string")
        return text.find(part)

    def _string_replace(self, arguments: list[Any]) -> str:
        """``replace(old, new)`` — replace only the first occurrence."""
        if len(arguments) != 3:
            raise RuntimeErrorX("String.replace expects old and new string arguments")
        text = self._string_receiver(arguments, "replace")
        old, new = arguments[1], arguments[2]
        if not isinstance(old, str) or not isinstance(new, str):
            raise RuntimeErrorX("String.replace expects old and new to be strings")
        return text.replace(old, new, 1)

    def _string_replace_all(self, arguments: list[Any]) -> str:
        """``replaceAll(old, new)`` — replace every occurrence."""
        if len(arguments) != 3:
            raise RuntimeErrorX("String.replaceAll expects old and new string arguments")
        text = self._string_receiver(arguments, "replaceAll")
        old, new = arguments[1], arguments[2]
        if not isinstance(old, str) or not isinstance(new, str):
            raise RuntimeErrorX("String.replaceAll expects old and new to be strings")
        return text.replace(old, new)

    def _string_split(self, arguments: list[Any]) -> list[str]:
        """``split(separator?)`` — split into an array of strings.

        With no separator the string splits on whitespace runs (Python
        ``str.split``); ``""`` splits into individual Unicode code points.
        """
        if len(arguments) > 2:
            raise RuntimeErrorX("String.split accepts at most one separator")
        text = self._string_receiver(arguments, "split")
        if len(arguments) == 1:
            return text.split()
        separator = arguments[1]
        if not isinstance(separator, str):
            raise RuntimeErrorX("String.split separator must be a string")
        if separator == "":
            return list(text)
        return text.split(separator)

    def _string_char_at(self, arguments: list[Any]) -> str:
        """``charAt(index)`` — the one-character string at *index*.

        Indexing counts Unicode code points (negatives count backward from the
        end, like all X string indexing); out-of-range indices raise.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("String.charAt expects an index argument")
        text = self._string_receiver(arguments, "charAt")
        index = self._string_index_argument(arguments, 1, "String.charAt")
        try:
            return text[index]
        except IndexError:
            raise RuntimeErrorX("String.charAt index out of bounds") from None

    def _string_substring(self, arguments: list[Any]) -> str:
        """``substring(start?, end?)`` — JS-style bounds in code points.

        Negative indices clamp to 0 and the bounds swap when *start* > *end*,
        unlike ``slice`` where negatives count from the end.
        """
        if len(arguments) > 3:
            raise RuntimeErrorX("String.substring accepts a start and an end index")
        text = self._string_receiver(arguments, "substring")
        if len(arguments) > 1:
            start = self._string_index_argument(arguments, 1, "String.substring")
        else:
            start = 0
        if len(arguments) > 2:
            end = self._string_index_argument(arguments, 2, "String.substring")
        else:
            end = len(text)
        start = max(0, start)
        end = max(0, end)
        if start > end:
            start, end = end, start
        return text[start:end]

    def _string_slice(self, arguments: list[Any]) -> str:
        """``slice(start?, end?)`` — code-point slice; negatives count from
        the end and out-of-range bounds clamp."""
        if len(arguments) > 3:
            raise RuntimeErrorX("String.slice accepts a start and an end index")
        text = self._string_receiver(arguments, "slice")
        start, end = self._slice_bounds(
            arguments[1] if len(arguments) > 1 else None,
            arguments[2] if len(arguments) > 2 else None,
            len(text),
            "String.slice",
        )
        return text[start:end]

    def _string_repeat(self, arguments: list[Any]) -> str:
        """``repeat(count)`` — concatenate the string *count* times."""
        if len(arguments) != 2:
            raise RuntimeErrorX("String.repeat expects a count argument")
        text = self._string_receiver(arguments, "repeat")
        count = arguments[1]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RuntimeErrorX("String.repeat count must be a non-negative integer")
        return text * count

    def _pad_text(self, text: str, length: int, pad: str, left: bool) -> str:
        """Pad *text* out to *length* with *pad* cycled (JS ``padStart``/``padEnd``).

        The padding is built from repetitions of *pad* truncated to the exact
        number of missing characters; an empty pad leaves *text* unchanged.
        """
        if len(text) >= length or pad == "":
            return text
        missing = length - len(text)
        fill = (pad * (missing // len(pad) + 1))[:missing]
        return fill + text if left else text + fill

    def _string_pad_start(self, arguments: list[Any]) -> str:
        """``padStart(length, pad?)`` — left-pad to *length* (default pad ``" "``).

        A multi-character pad repeats, as in JavaScript; an empty pad leaves
        the text unchanged because there is nothing to fill with.
        """
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX("String.padStart expects a length argument")
        text = self._string_receiver(arguments, "padStart")
        length = arguments[1]
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise RuntimeErrorX("String.padStart length must be a non-negative integer")
        pad = " " if len(arguments) == 2 else arguments[2]
        if not isinstance(pad, str):
            raise RuntimeErrorX("String.padStart pad must be a string")
        return self._pad_text(text, length, pad, left=True)

    def _string_pad_end(self, arguments: list[Any]) -> str:
        """``padEnd(length, pad?)`` — right-pad to *length* (default pad ``" "``)."""
        if len(arguments) not in (2, 3):
            raise RuntimeErrorX("String.padEnd expects a length argument")
        text = self._string_receiver(arguments, "padEnd")
        length = arguments[1]
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise RuntimeErrorX("String.padEnd length must be a non-negative integer")
        pad = " " if len(arguments) == 2 else arguments[2]
        if not isinstance(pad, str):
            raise RuntimeErrorX("String.padEnd pad must be a string")
        return self._pad_text(text, length, pad, left=False)

    def _string_is_empty(self, arguments: list[Any]) -> bool:
        """``isEmpty()`` — whether the string has no characters."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.isEmpty expects no arguments")
        return self._string_receiver(arguments, "isEmpty") == ""

    def _string_to_char_array(self, arguments: list[Any]) -> list[str]:
        """``toCharArray()`` — one-character strings, one per code point."""
        if len(arguments) != 1:
            raise RuntimeErrorX("String.toCharArray expects no arguments")
        return list(self._string_receiver(arguments, "toCharArray"))

    def _linkedlist_members(self) -> dict[str, BuiltinFunction]:
        members: dict[str, BuiltinFunction] = {
            "create": BuiltinFunction("LinkedList.create", self._linkedlist_create),
            "add": BuiltinFunction("LinkedList.add", self._linkedlist_add),
            "addFirst": BuiltinFunction("LinkedList.addFirst", self._linkedlist_add_first),
            "addLast": BuiltinFunction("LinkedList.addLast", self._linkedlist_add_last),
            "remove": BuiltinFunction("LinkedList.remove", self._linkedlist_remove),
            "removeFirst": BuiltinFunction("LinkedList.removeFirst", self._linkedlist_remove_first),
            "removeLast": BuiltinFunction("LinkedList.removeLast", self._linkedlist_remove_last),
            "get": BuiltinFunction("LinkedList.get", self._linkedlist_get),
            "getFirst": BuiltinFunction("LinkedList.getFirst", self._linkedlist_get_first),
            "getLast": BuiltinFunction("LinkedList.getLast", self._linkedlist_get_last),
            "size": BuiltinFunction("LinkedList.size", self._linkedlist_size),
            "isEmpty": BuiltinFunction("LinkedList.isEmpty", self._linkedlist_is_empty),
            "clear": BuiltinFunction("LinkedList.clear", self._linkedlist_clear),
            "contains": BuiltinFunction("LinkedList.contains", self._linkedlist_contains),
            "indexOf": BuiltinFunction("LinkedList.indexOf", self._linkedlist_index_of),
            "toArray": BuiltinFunction("LinkedList.toArray", self._linkedlist_to_array),
            "reverse": BuiltinFunction("LinkedList.reverse", self._linkedlist_reverse),
            "groupBy": BuiltinFunction("LinkedList.groupBy", self._linkedlist_group_by),
            "partition": BuiltinFunction("LinkedList.partition", self._linkedlist_partition),
        }
        # Array methods double as the functional API: List.map(array, cb).
        # LinkedList-specific entries above (indexOf, reverse, ...) keep their
        # own behavior.
        for method_name, implementation_name in _ARRAY_METHODS.items():
            members.setdefault(
                method_name,
                BuiltinFunction(
                    f"List.{method_name}", getattr(self, implementation_name)
                ),
            )
        return members

    def _linkedlist_create(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("LinkedList.create accepts at most one argument (initial array)")
        if len(arguments) == 1:
            if not isinstance(arguments[0], list):
                raise RuntimeErrorX("LinkedList.create initial value must be an array")
            return list(arguments[0])
        return []

    def _linkedlist_add(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.add expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.add expects a LinkedList instance")
        linkedlist.append(value)
        return None

    def _linkedlist_add_first(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.addFirst expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.addFirst expects a LinkedList instance")
        linkedlist.insert(0, value)
        return None

    def _linkedlist_add_last(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.addLast expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.addLast expects a LinkedList instance")
        linkedlist.append(value)
        return None

    def _linkedlist_remove(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.remove expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.remove expects a LinkedList instance")
        try:
            linkedlist.remove(value)
            return True
        except ValueError:
            return False

    def _linkedlist_remove_first(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.removeFirst expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.removeFirst expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.removeFirst: list is empty")
        return linkedlist.pop(0)

    def _linkedlist_remove_last(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.removeLast expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.removeLast expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.removeLast: list is empty")
        return linkedlist.pop()

    def _linkedlist_get(self, arguments: list[Any]) -> Any:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.get expects an index argument")
        linkedlist, index = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.get expects a LinkedList instance")
        if not isinstance(index, int) or index < 0 or index >= len(linkedlist):
            raise RuntimeErrorX("LinkedList.get index out of bounds")
        return linkedlist[index]

    def _linkedlist_get_first(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.getFirst expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.getFirst expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.getFirst: list is empty")
        return linkedlist[0]

    def _linkedlist_get_last(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.getLast expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.getLast expects a LinkedList instance")
        if not linkedlist:
            raise RuntimeErrorX("LinkedList.getLast: list is empty")
        return linkedlist[-1]

    def _linkedlist_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.size expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.size expects a LinkedList instance")
        return len(linkedlist)

    def _linkedlist_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.isEmpty expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.isEmpty expects a LinkedList instance")
        return len(linkedlist) == 0

    def _linkedlist_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.clear expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.clear expects a LinkedList instance")
        linkedlist.clear()
        return None

    def _linkedlist_contains(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.contains expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.contains expects a LinkedList instance")
        return value in linkedlist

    def _linkedlist_index_of(self, arguments: list[Any]) -> int:
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.indexOf expects a value argument")
        linkedlist, value = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.indexOf expects a LinkedList instance")
        try:
            return linkedlist.index(value)
        except ValueError:
            return -1

    def _linkedlist_to_array(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.toArray expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.toArray expects a LinkedList instance")
        return list(linkedlist)

    def _linkedlist_reverse(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("LinkedList.reverse expects no arguments")
        linkedlist = arguments[0]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.reverse expects a LinkedList instance")
        linkedlist.reverse()
        return None

    def _linkedlist_group_by(self, arguments: list[Any]) -> dict[str, list[Any]]:
        """Group list elements by the string key returned by *fn(item)*.

        Returns a dict whose keys are the stringified results of calling *fn*
        on each element and whose values are lists of the matching elements.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.groupBy expects a list and a key function")
        linkedlist, fn = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.groupBy expects a LinkedList instance")
        if not isinstance(fn, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("LinkedList.groupBy: second argument must be a function")
        groups: dict[str, list[Any]] = {}
        for item in linkedlist:
            key = str(self._call(fn, [item]))
            groups.setdefault(key, []).append(item)
        return groups

    def _linkedlist_partition(self, arguments: list[Any]) -> list[list[Any]]:
        """Split the list into two sub-lists based on a predicate function.

        Returns ``[[truthy_items], [falsy_items]]`` where *fn(item)* decides
        which partition each element falls into.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("LinkedList.partition expects a list and a predicate function")
        linkedlist, fn = arguments[0], arguments[1]
        if not isinstance(linkedlist, list):
            raise RuntimeErrorX("LinkedList.partition expects a LinkedList instance")
        if not isinstance(fn, (XFunction, BuiltinFunction, OverloadedFunction)):
            raise RuntimeErrorX("LinkedList.partition: second argument must be a function")
        truthy: list[Any] = []
        falsy: list[Any] = []
        for item in linkedlist:
            (truthy if self._is_truthy(self._call(fn, [item])) else falsy).append(item)
        return [truthy, falsy]

    def _stack_members(self) -> dict[str, BuiltinFunction]:
        return {
            "create": BuiltinFunction("Stack.create", self._stack_create),
            "push": BuiltinFunction("Stack.push", self._stack_push),
            "pop": BuiltinFunction("Stack.pop", self._stack_pop),
            "peek": BuiltinFunction("Stack.peek", self._stack_peek),
            "size": BuiltinFunction("Stack.size", self._stack_size),
            "isEmpty": BuiltinFunction("Stack.isEmpty", self._stack_is_empty),
            "clear": BuiltinFunction("Stack.clear", self._stack_clear),
            "toArray": BuiltinFunction("Stack.toArray", self._stack_to_array),
        }

    def _stack_create(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("Stack.create accepts at most one argument (initial array)")
        if len(arguments) == 1:
            if not isinstance(arguments[0], list):
                raise RuntimeErrorX("Stack.create initial value must be an array")
            return list(arguments[0])
        return []

    def _stack_push(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("Stack.push expects a value argument")
        stack, value = arguments[0], arguments[1]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.push expects a Stack instance")
        stack.append(value)
        return None

    def _stack_pop(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.pop expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.pop expects a Stack instance")
        if not stack:
            raise RuntimeErrorX("Stack.pop: stack is empty")
        return stack.pop()

    def _stack_peek(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.peek expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.peek expects a Stack instance")
        if not stack:
            raise RuntimeErrorX("Stack.peek: stack is empty")
        return stack[-1]

    def _stack_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.size expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.size expects a Stack instance")
        return len(stack)

    def _stack_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.isEmpty expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.isEmpty expects a Stack instance")
        return len(stack) == 0

    def _stack_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.clear expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.clear expects a Stack instance")
        stack.clear()
        return None

    def _stack_to_array(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("Stack.toArray expects no arguments")
        stack = arguments[0]
        if not isinstance(stack, list):
            raise RuntimeErrorX("Stack.toArray expects a Stack instance")
        return list(stack)

    def _queue_members(self) -> dict[str, BuiltinFunction]:
        return {
            "create": BuiltinFunction("Queue.create", self._queue_create),
            "enqueue": BuiltinFunction("Queue.enqueue", self._queue_enqueue),
            "dequeue": BuiltinFunction("Queue.dequeue", self._queue_dequeue),
            "peek": BuiltinFunction("Queue.peek", self._queue_peek),
            "size": BuiltinFunction("Queue.size", self._queue_size),
            "isEmpty": BuiltinFunction("Queue.isEmpty", self._queue_is_empty),
            "clear": BuiltinFunction("Queue.clear", self._queue_clear),
            "toArray": BuiltinFunction("Queue.toArray", self._queue_to_array),
        }

    def _queue_create(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) > 1:
            raise RuntimeErrorX("Queue.create accepts at most one argument (initial array)")
        if len(arguments) == 1:
            if not isinstance(arguments[0], list):
                raise RuntimeErrorX("Queue.create initial value must be an array")
            return list(arguments[0])
        return []

    def _queue_enqueue(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("Queue.enqueue expects a value argument")
        queue, value = arguments[0], arguments[1]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.enqueue expects a Queue instance")
        queue.append(value)
        return None

    def _queue_dequeue(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.dequeue expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.dequeue expects a Queue instance")
        if not queue:
            raise RuntimeErrorX("Queue.dequeue: queue is empty")
        return queue.pop(0)

    def _queue_peek(self, arguments: list[Any]) -> Any:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.peek expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.peek expects a Queue instance")
        if not queue:
            raise RuntimeErrorX("Queue.peek: queue is empty")
        return queue[0]

    def _queue_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.size expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.size expects a Queue instance")
        return len(queue)

    def _queue_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.isEmpty expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.isEmpty expects a Queue instance")
        return len(queue) == 0

    def _queue_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.clear expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.clear expects a Queue instance")
        queue.clear()
        return None

    def _queue_to_array(self, arguments: list[Any]) -> list[Any]:
        if len(arguments) != 1:
            raise RuntimeErrorX("Queue.toArray expects no arguments")
        queue = arguments[0]
        if not isinstance(queue, list):
            raise RuntimeErrorX("Queue.toArray expects a Queue instance")
        return list(queue)

    def _priorityqueue_members(self) -> dict[str, BuiltinFunction]:
        """Return the method table for PriorityQueue collection namespace."""
        return {
            "create":   BuiltinFunction("PriorityQueue.create",   self._priorityqueue_create),
            "enqueue":  BuiltinFunction("PriorityQueue.enqueue",  self._priorityqueue_enqueue),
            "dequeue":  BuiltinFunction("PriorityQueue.dequeue",  self._priorityqueue_dequeue),
            "peek":     BuiltinFunction("PriorityQueue.peek",     self._priorityqueue_peek),
            "size":     BuiltinFunction("PriorityQueue.size",     self._priorityqueue_size),
            "isEmpty":  BuiltinFunction("PriorityQueue.isEmpty",  self._priorityqueue_is_empty),
            "clear":    BuiltinFunction("PriorityQueue.clear",    self._priorityqueue_clear),
            "toArray":  BuiltinFunction("PriorityQueue.toArray",  self._priorityqueue_to_array),
        }

    def _priorityqueue_create(self, arguments: list[Any]) -> dict[str, Any]:
        """Create a new PriorityQueue dict.

        Accepts an optional single argument:
        - ``'max'`` (string)  → max-heap (largest value dequeued first).
        - A callable X function → custom comparator; called as ``fn(a, b)``
          and must return a negative number when ``a`` sorts before ``b``.
        """
        if len(arguments) > 1:
            raise RuntimeErrorX(
                "PriorityQueue.create accepts at most one argument ('max' or comparator fn)"
            )
        mode: str = "min"
        comparator: Any = None
        if len(arguments) == 1:
            arg = arguments[0]
            if arg == "max":
                mode = "max"
            elif isinstance(arg, (XFunction, BuiltinFunction, OverloadedFunction)):
                comparator = arg
            elif arg is not None:
                raise RuntimeErrorX(
                    "PriorityQueue.create argument must be 'max' or a comparator function"
                )
        return {"heap": [], "comparator": comparator, "mode": mode}

    def _priorityqueue_unwrap_item(self, item: Any) -> Any:
        """Unwrap a ComparatorItem or max-heap negation tuple to the original value."""
        if isinstance(item, ComparatorItem):
            return item.value
        # max-heap without comparator stores (-value, value)
        if isinstance(item, tuple) and len(item) == 2:
            return item[1]
        return item

    def _priorityqueue_enqueue(self, arguments: list[Any]) -> None:
        """Push *value* onto the heap in O(log n) time using heapq."""
        if len(arguments) != 2:
            raise RuntimeErrorX("PriorityQueue.enqueue expects exactly one value argument")
        queue, value = arguments[0], arguments[1]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.enqueue expects a PriorityQueue instance")
        heap: list = queue["heap"]
        comparator = queue["comparator"]
        mode: str = queue["mode"]
        if comparator is not None:
            heapq.heappush(heap, ComparatorItem(value, comparator, self._call))
        elif mode == "max":
            # Negate numeric values; fall back to ComparatorItem for non-numeric
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                heapq.heappush(heap, (-value, value))
            else:
                # Wrap with a reversed comparator so largest is popped first
                def _reverse_cmp(a: Any, b: Any) -> int:
                    if a < b:
                        return 1
                    if a > b:
                        return -1
                    return 0

                dummy_fn = BuiltinFunction(
                    "__max_cmp",
                    lambda args: _reverse_cmp(args[0], args[1]),
                )
                heapq.heappush(heap, ComparatorItem(value, dummy_fn, self._call))
        else:
            heapq.heappush(heap, value)
        return None

    def _priorityqueue_dequeue(self, arguments: list[Any]) -> Any:
        """Pop and return the highest-priority element in O(log n) time."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.dequeue expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.dequeue expects a PriorityQueue instance")
        heap: list = queue["heap"]
        if not heap:
            raise RuntimeErrorX("PriorityQueue.dequeue: queue is empty")
        return self._priorityqueue_unwrap_item(heapq.heappop(heap))

    def _priorityqueue_peek(self, arguments: list[Any]) -> Any:
        """Return the highest-priority element without removing it."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.peek expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.peek expects a PriorityQueue instance")
        heap: list = queue["heap"]
        if not heap:
            raise RuntimeErrorX("PriorityQueue.peek: queue is empty")
        return self._priorityqueue_unwrap_item(heap[0])

    def _priorityqueue_size(self, arguments: list[Any]) -> int:
        """Return the number of elements currently in the queue."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.size expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.size expects a PriorityQueue instance")
        return len(queue["heap"])

    def _priorityqueue_is_empty(self, arguments: list[Any]) -> bool:
        """Return True when the queue contains no elements."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.isEmpty expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.isEmpty expects a PriorityQueue instance")
        return len(queue["heap"]) == 0

    def _priorityqueue_clear(self, arguments: list[Any]) -> None:
        """Remove all elements from the queue in place."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.clear expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.clear expects a PriorityQueue instance")
        queue["heap"].clear()
        return None

    def _priorityqueue_to_array(self, arguments: list[Any]) -> list[Any]:
        """Return a sorted list of all elements (does not modify the queue)."""
        if len(arguments) != 1:
            raise RuntimeErrorX("PriorityQueue.toArray expects no extra arguments")
        queue = arguments[0]
        if not (isinstance(queue, dict) and "heap" in queue):
            raise RuntimeErrorX("PriorityQueue.toArray expects a PriorityQueue instance")
        heap: list = queue["heap"]
        sorted_items = heapq.nsmallest(len(heap), heap)
        return [self._priorityqueue_unwrap_item(item) for item in sorted_items]

    def _trie_members(self) -> dict[str, BuiltinFunction]:
        """Return the method table for Trie collection namespace."""
        return {
            "create":            BuiltinFunction("Trie.create",            self._trie_create),
            "insert":            BuiltinFunction("Trie.insert",            self._trie_insert),
            "search":            BuiltinFunction("Trie.search",            self._trie_search),
            "startsWith":        BuiltinFunction("Trie.startsWith",        self._trie_starts_with),
            "remove":            BuiltinFunction("Trie.remove",            self._trie_remove),
            "size":              BuiltinFunction("Trie.size",              self._trie_size),
            "isEmpty":           BuiltinFunction("Trie.isEmpty",           self._trie_is_empty),
            "clear":             BuiltinFunction("Trie.clear",             self._trie_clear),
            "getAllWords":        BuiltinFunction("Trie.getAllWords",       self._trie_get_all_words),
            "getWordsWithPrefix": BuiltinFunction("Trie.getWordsWithPrefix", self._trie_get_words_with_prefix),
        }

    def _trie_create(self, arguments: list[Any]) -> dict[str, Any]:
        if len(arguments) > 0:
            raise RuntimeErrorX("Trie.create accepts no arguments")
        return {"children": {}, "is_end": False, "count": 0}

    def _trie_insert(self, arguments: list[Any]) -> None:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.insert expects a word argument")
        trie, word = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.insert expects a Trie instance")
        if not isinstance(word, str):
            raise RuntimeErrorX("Trie.insert word must be a string")
        node = trie
        for char in word:
            if char not in node["children"]:
                node["children"][char] = {"children": {}, "is_end": False}
            node = node["children"][char]
        if not node["is_end"]:
            node["is_end"] = True
            trie["count"] = trie.get("count", 0) + 1
        return None

    def _trie_search(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.search expects a word argument")
        trie, word = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.search expects a Trie instance")
        if not isinstance(word, str):
            raise RuntimeErrorX("Trie.search word must be a string")
        node = trie
        for char in word:
            if char not in node["children"]:
                return False
            node = node["children"][char]
        return node.get("is_end", False)

    def _trie_starts_with(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.startsWith expects a prefix argument")
        trie, prefix = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.startsWith expects a Trie instance")
        if not isinstance(prefix, str):
            raise RuntimeErrorX("Trie.startsWith prefix must be a string")
        node = trie
        for char in prefix:
            if char not in node["children"]:
                return False
            node = node["children"][char]
        return True

    def _trie_remove(self, arguments: list[Any]) -> bool:
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.remove expects a word argument")
        trie, word = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.remove expects a Trie instance")
        if not isinstance(word, str):
            raise RuntimeErrorX("Trie.remove word must be a string")
        
        def _remove_helper(node: dict[str, Any], word: str, index: int) -> bool:
            if index == len(word):
                if not node.get("is_end", False):
                    return False
                node["is_end"] = False
                trie["count"] = trie.get("count", 0) - 1
                return len(node["children"]) == 0
            char = word[index]
            if char not in node["children"]:
                return False
            should_delete = _remove_helper(node["children"][char], word, index + 1)
            if should_delete:
                del node["children"][char]
                return len(node["children"]) == 0 and not node.get("is_end", False)
            return False
        
        return _remove_helper(trie, word, 0)

    def _trie_size(self, arguments: list[Any]) -> int:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.size expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.size expects a Trie instance")
        return trie.get("count", 0)

    def _trie_is_empty(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.isEmpty expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.isEmpty expects a Trie instance")
        return trie.get("count", 0) == 0

    def _trie_clear(self, arguments: list[Any]) -> None:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.clear expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.clear expects a Trie instance")
        trie["children"] = {}
        trie["is_end"] = False
        trie["count"] = 0
        return None

    def _trie_get_all_words(self, arguments: list[Any]) -> list[str]:
        if len(arguments) != 1:
            raise RuntimeErrorX("Trie.getAllWords expects no arguments")
        trie = arguments[0]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.getAllWords expects a Trie instance")
        
        words = []
        
        def _collect_words(node: dict[str, Any], prefix: str) -> None:
            if node.get("is_end", False):
                words.append(prefix)
            for char, child in node["children"].items():
                _collect_words(child, prefix + char)
        
        _collect_words(trie, "")
        return words

    def _trie_get_words_with_prefix(self, arguments: list[Any]) -> list[str]:
        """Return all words stored in the trie that begin with *prefix*.

        Traverses to the prefix node character by character; returns ``[]``
        if any character in the prefix is missing.  Then runs a DFS from
        that node, seeding each collected word with the prefix string.
        """
        if len(arguments) != 2:
            raise RuntimeErrorX("Trie.getWordsWithPrefix expects a prefix argument")
        trie, prefix = arguments[0], arguments[1]
        if not isinstance(trie, dict) or "children" not in trie:
            raise RuntimeErrorX("Trie.getWordsWithPrefix expects a Trie instance")
        if not isinstance(prefix, str):
            raise RuntimeErrorX("Trie.getWordsWithPrefix: prefix must be a string")

        # Walk to the node at the end of the prefix
        node: dict[str, Any] = trie
        for char in prefix:
            if char not in node["children"]:
                return []
            node = node["children"][char]

        # DFS from that node, collecting every complete word
        words: list[str] = []

        def _collect(current_node: dict[str, Any], current_prefix: str) -> None:
            if current_node.get("is_end", False):
                words.append(current_prefix)
            for char, child in current_node["children"].items():
                _collect(child, current_prefix + char)

        _collect(node, prefix)
        return words

    # ──────────────────────────────────────────────────────────────────────────
    # Set methods
    # ──────────────────────────────────────────────────────────────────────────

    def _set_members(self) -> dict[str, BuiltinFunction]:
        """Return the method table for Set collection namespace."""
        return {
            "create":       BuiltinFunction("Set.create",       self._set_create),
            "add":          BuiltinFunction("Set.add",          self._set_add),
            "has":          BuiltinFunction("Set.has",          self._set_has),
            "remove":       BuiltinFunction("Set.remove",       self._set_remove),
            "size":         BuiltinFunction("Set.size",         self._set_size),
            "isEmpty":      BuiltinFunction("Set.isEmpty",      self._set_is_empty),
            "clear":        BuiltinFunction("Set.clear",        self._set_clear),
            "toArray":      BuiltinFunction("Set.toArray",      self._set_to_array),
            "union":        BuiltinFunction("Set.union",        self._set_union),
            "intersection": BuiltinFunction("Set.intersection", self._set_intersection),
            "difference":   BuiltinFunction("Set.difference",  self._set_difference),
        }

    def _set_create(self, arguments: list[Any]) -> set[Any]:
        """Create a new empty Set, optionally initialised from an iterable."""
        if len(arguments) > 1:
            raise RuntimeErrorX("Set.create accepts at most one argument (initial iterable)")
        if len(arguments) == 1:
            init = arguments[0]
            if not hasattr(init, "__iter__"):
                raise RuntimeErrorX("Set.create initial value must be iterable")
            return set(init)
        return set()

    def _set_add(self, arguments: list[Any]) -> None:
        """Add *value* to the set (no-op if already present)."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.add expects exactly one value argument")
        s, value = arguments[0], arguments[1]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.add expects a Set instance")
        s.add(value)
        return None

    def _set_has(self, arguments: list[Any]) -> bool:
        """Return True when *value* is a member of the set."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.has expects exactly one value argument")
        s, value = arguments[0], arguments[1]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.has expects a Set instance")
        return value in s

    def _set_remove(self, arguments: list[Any]) -> bool:
        """Remove *value* from the set; returns True if it was present."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.remove expects exactly one value argument")
        s, value = arguments[0], arguments[1]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.remove expects a Set instance")
        if value in s:
            s.discard(value)
            return True
        return False

    def _set_size(self, arguments: list[Any]) -> int:
        """Return the number of elements in the set."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.size expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.size expects a Set instance")
        return len(s)

    def _set_is_empty(self, arguments: list[Any]) -> bool:
        """Return True when the set contains no elements."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.isEmpty expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.isEmpty expects a Set instance")
        return len(s) == 0

    def _set_clear(self, arguments: list[Any]) -> None:
        """Remove all elements from the set in place."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.clear expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.clear expects a Set instance")
        s.clear()
        return None

    def _set_to_array(self, arguments: list[Any]) -> list[Any]:
        """Return a sorted list of the set's elements (sort key: str representation)."""
        if len(arguments) != 1:
            raise RuntimeErrorX("Set.toArray expects no extra arguments")
        s = arguments[0]
        if not isinstance(s, set):
            raise RuntimeErrorX("Set.toArray expects a Set instance")
        return sorted(s, key=str)

    def _set_union(self, arguments: list[Any]) -> set[Any]:
        """Return a new set containing elements from both sets."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.union expects exactly two Set arguments")
        s1 = arguments[0]
        s2 = arguments[1]
        # Allow the second arg to be an XCollectionInstance (instance dot-call pattern)
        if isinstance(s2, XCollectionInstance):
            s2 = s2._data
        if not isinstance(s1, set):
            raise RuntimeErrorX("Set.union: first argument must be a Set instance")
        if not isinstance(s2, set):
            raise RuntimeErrorX("Set.union: second argument must be a Set instance")
        return s1 | s2

    def _set_intersection(self, arguments: list[Any]) -> set[Any]:
        """Return a new set containing only elements present in both sets."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.intersection expects exactly two Set arguments")
        s1 = arguments[0]
        s2 = arguments[1]
        if isinstance(s2, XCollectionInstance):
            s2 = s2._data
        if not isinstance(s1, set):
            raise RuntimeErrorX("Set.intersection: first argument must be a Set instance")
        if not isinstance(s2, set):
            raise RuntimeErrorX("Set.intersection: second argument must be a Set instance")
        return s1 & s2

    def _set_difference(self, arguments: list[Any]) -> set[Any]:
        """Return a new set with elements in *s1* that are not in *s2*."""
        if len(arguments) != 2:
            raise RuntimeErrorX("Set.difference expects exactly two Set arguments")
        s1 = arguments[0]
        s2 = arguments[1]
        if isinstance(s2, XCollectionInstance):
            s2 = s2._data
        if not isinstance(s1, set):
            raise RuntimeErrorX("Set.difference: first argument must be a Set instance")
        if not isinstance(s2, set):
            raise RuntimeErrorX("Set.difference: second argument must be a Set instance")
        return s1 - s2

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

    def _builtin_type_of(self, arguments: list[Any]) -> str:
        """Report the X-level type name of the single argument.

        Mapping:

        - ``boolean`` for booleans, ``number`` for integers/floats,
          ``string`` for strings
        - ``function`` for functions, builtins, overloads, and class objects
        - ``Array`` for every array value (plain lists and typed ``XArray``)
        - the class name for instances of user classes and exceptions
          (for example ``User`` or ``CustomException``)
        - the collection name for OOP collection instances
          (``HashMap``, ``Stack``, ``Queue``, ...)
        - ``object`` for object literals, typed objects, null, undefined,
          enum members, and any other unclassified value
        """
        if len(arguments) != 1:
            raise RuntimeErrorX(
                f"typeOf expects one argument, got {len(arguments)}"
            )
        value = arguments[0]
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(
            value, (BuiltinFunction, OverloadedFunction, XClass, XFunction)
        ):
            return "function"
        if isinstance(value, list):
            return "Array"
        if isinstance(value, XCollectionInstance):
            return value.collection_type
        if isinstance(value, XExceptionValue):
            return value.name
        if isinstance(value, XInstance):
            return value.xclass.name
        if isinstance(value, XThreadHandle):
            return "ThreadHandle"
        return "object"

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

    def _builtin_exception(
        self, name: str, arguments: list[Any]
    ) -> XExceptionValue:
        if len(arguments) not in (1, 2):
            raise RuntimeErrorX(f"{name} expects a message and optional cause")
        return XExceptionValue(
            self._stringify(arguments[0]),
            name,
            arguments[1] if len(arguments) == 2 else None,
        )

    def _initialize_exception_instance(
        self, instance: XInstance, arguments: list[Any]
    ) -> None:
        if len(arguments) not in (0, 1, 2):
            raise RuntimeErrorX(
                f"{instance.xclass.name} expects a message and optional cause"
            )
        if arguments:
            instance.fields["message"] = self._stringify(arguments[0])
        instance.fields["name"] = instance.xclass.name
        if len(arguments) == 2:
            instance.fields["cause"] = arguments[1]
        instance.fields.setdefault("cause", None)
        instance.fields.setdefault("stack", "")

    def _define_function(self, declaration: FunctionDeclaration, environment: Environment) -> None:
        self._set_declaration_location(declaration)
        function = XFunction(declaration, environment, self)
        function = self._apply_function_decorators(
            declaration.decorators, function, environment
        )
        existing = environment.values.get(declaration.name)
        if existing is None:
            environment.define(declaration.name, [function])
        else:
            if not isinstance(existing, list) or any(
                not isinstance(item, XFunction) for item in existing
            ):
                raise RuntimeErrorX(f"'{declaration.name}' is already declared")
            existing.append(function)

    def _apply_function_decorators(
        self, decorators: list[Any], function: XFunction, environment: Environment
    ) -> XFunction:
        decorated_function = function
        for decorator_expression in reversed(decorators):
            decorator = self._evaluate(decorator_expression, environment)
            decorated_value = self._call(decorator, [decorated_function])
            if not isinstance(decorated_value, XFunction):
                raise RuntimeErrorX(
                    f"Decorator for '{function.declaration.name}' must return a function"
                )
            decorated_function = decorated_value
        return decorated_function

    def _define_namespace(
        self, declaration: NamespaceDeclaration, environment: Environment
    ) -> None:
        namespace_environment = environment
        for name in declaration.name.split("."):
            existing_value = namespace_environment.values.get(name)
            if existing_value is None:
                nested_environment = Environment(namespace_environment)
                namespace_environment.define(name, nested_environment)
                namespace_environment = nested_environment
            elif isinstance(existing_value, Environment):
                namespace_environment = existing_value
            else:
                raise RuntimeErrorX(
                    f"Cannot declare namespace '{declaration.name}': '{name}' is not a namespace"
                )

        for nested_declaration in declaration.declarations:
            if isinstance(nested_declaration, FunctionDeclaration):
                self._define_function(nested_declaration, namespace_environment)
            elif isinstance(nested_declaration, ClassDeclaration):
                self._define_class(nested_declaration, namespace_environment)
            elif isinstance(nested_declaration, EnumDeclaration):
                self._define_enum(nested_declaration, namespace_environment)
            elif isinstance(nested_declaration, NamespaceDeclaration):
                self._define_namespace(nested_declaration, namespace_environment)
            elif isinstance(nested_declaration, ImportDeclaration):
                raise RuntimeErrorX(
                    "Imports inside namespace blocks are not supported; import at module scope"
                )

        for nested_declaration in declaration.declarations:
            if isinstance(nested_declaration, VariableDeclaration):
                self._execute(nested_declaration, namespace_environment)

    def _reject_final_overrides(
        self, declaration: ClassDeclaration, parent: XClass
    ) -> None:
        """Reject a subclass member that redefines a final member of a base."""
        for member in declaration.members:
            if not isinstance(member, FunctionDeclaration):
                continue
            if member.name == declaration.name or member.name == "constructor":
                continue  # constructors do not override inherited methods
            for ancestor in self._class_hierarchy(parent):
                for inherited in ancestor.declaration.members:
                    if (
                        isinstance(inherited, FunctionDeclaration)
                        and inherited.name == member.name
                        and "final" in inherited.modifiers
                    ):
                        self._set_declaration_location(member)
                        override_error = RuntimeErrorX(
                            f"Cannot override final method "
                            f"'{ancestor.name}.{inherited.name}'"
                        )
                        self.annotate_error(override_error)
                        raise override_error

    def _inside_defining_constructor(self, owner: XClass) -> bool:
        """True while a constructor of ``owner`` or one of its subclasses runs.

        ``final`` properties may be assigned exactly once, during
        construction; every other assignment is rejected.
        """
        for function in reversed(self.function_stack):
            if function.parent_class is None:
                continue
            if function.declaration.name != function.parent_class.name:
                continue  # not a constructor
            if owner in self._class_hierarchy(function.parent_class):
                return True
        return False

    def _define_class(
        self,
        declaration: ClassDeclaration,
        environment: Environment,
        enclosing_class: XClass | None = None,
    ) -> None:
        self._set_declaration_location(declaration)
        parent = None
        if declaration.parent_name:
            parent_value = self._resolve_name(environment, declaration.parent_name)
            if not isinstance(parent_value, XClass):
                raise RuntimeErrorX(f"Parent type '{declaration.parent_name}' is not a class")
            if "final" in parent_value.declaration.modifiers:
                final_class_error = RuntimeErrorX(
                    f"Cannot extend final class '{parent_value.name}'"
                )
                self.annotate_error(final_class_error)
                raise final_class_error
            parent = parent_value
        if parent is not None:
            self._reject_final_overrides(declaration, parent)
        class_environment = Environment(environment)
        xclass = XClass(
            declaration,
            self,
            class_environment,
            parent,
            enclosing_class=enclosing_class,
        )
        environment.define(declaration.name, xclass)
        class_environment.define(declaration.name, xclass)
        class_environment.define("__x_current_class__", xclass)
        for member in declaration.members:
            if isinstance(member, ClassDeclaration):
                self._define_class(member, class_environment, xclass)
                nested_class = class_environment.get(member.name)
                if isinstance(nested_class, XClass):
                    xclass.nested_types[member.name] = nested_class
            elif isinstance(member, VariableDeclaration) and "static" in member.modifiers:
                value = None if member.initializer is None else self._evaluate(
                    member.initializer,
                    self._field_initializer_environment(xclass, member),
                )
                if (
                    member.type_name is not None
                    and member.type_name.endswith("[]")
                    and member.initializer is not None
                ):
                    value = self._coerce_typed_array(
                        member.type_name,
                        value,
                        f"property '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.type_name.startswith("object<")
                    and member.initializer is not None
                ):
                    value = self._coerce_typed_object(
                        member.type_name,
                        value,
                        f"property '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.initializer is not None
                    and self._needs_runtime_type_check(member.type_name)
                ):
                    value = self._coerce_runtime_checked_type(
                        member.type_name,
                        value,
                        f"property '{xclass.name}.{member.name}'",
                    )
                xclass.static_fields[member.name] = value

        decorated_class = xclass
        for decorator_expression in reversed(declaration.decorators):
            decorator = self._evaluate(decorator_expression, environment)
            decorated_value = self._call(decorator, [decorated_class])
            if not isinstance(decorated_value, XClass):
                raise RuntimeErrorX(
                    f"Decorator for class '{declaration.name}' must return a class"
                )
            decorated_class = decorated_value
        environment.values[declaration.name] = decorated_class
        class_environment.values[declaration.name] = decorated_class

    def _resolve_name(self, environment: Environment, qualified_name: str) -> Any:
        parts = qualified_name.split(".")
        value = self._lookup(environment, parts[0])
        for part in parts[1:]:
            value = self._get_member(value, part)
        return value

    def _define_enum(self, declaration: EnumDeclaration, environment: Environment) -> None:
        self._set_declaration_location(declaration)
        enum_values = Environment()
        enum_identity = object()
        for index, (name, expression) in enumerate(declaration.members):
            value = index if expression is None else self._evaluate(expression, environment)
            enum_values.define(
                name,
                XEnumMember(declaration.name, name, value, enum_identity),
            )
        environment.define(declaration.name, enum_values)

    def _set_declaration_location(self, declaration: Any) -> None:
        declaration_line = getattr(declaration, "line", None)
        if declaration_line is None:
            return
        self.current_location = (
            getattr(declaration, "source_name", None),
            declaration_line,
            getattr(declaration, "column", None),
        )

    def _execute(self, statement: Any, environment: Environment) -> None:
        statement_line = getattr(statement, "line", None)
        if statement_line is not None:
            self.current_location = (
                getattr(statement, "source_name", None),
                statement_line,
                getattr(statement, "column", None),
            )
        if isinstance(statement, Block):
            self._execute_block(statement.statements, Environment(environment))
        elif isinstance(statement, FunctionDeclaration):
            self._define_function(statement, environment)
        elif isinstance(statement, VariableDeclaration):
            value = None if statement.initializer is None else self._evaluate(statement.initializer, environment)
            if statement.pattern is not None:
                self._bind_destructuring(
                    statement.pattern, value, environment, statement.constant
                )
            else:
                array_type = (
                    statement.type_name
                    if statement.type_name is not None
                    and statement.type_name.endswith("[]")
                    else None
                )
                if array_type is not None and statement.initializer is not None:
                    value = self._coerce_typed_array(
                        array_type, value, f"variable '{statement.name}'"
                    )
                object_type = (
                    statement.type_name
                    if statement.type_name is not None
                    and statement.type_name.startswith("object<")
                    else None
                )
                if object_type is not None and statement.initializer is not None:
                    value = self._coerce_typed_object(
                        object_type, value, f"variable '{statement.name}'"
                    )
                value_type = (
                    statement.type_name
                    if statement.type_name is not None
                    and self._needs_runtime_type_check(statement.type_name)
                    else None
                )
                if value_type is not None and statement.initializer is not None:
                    value = self._coerce_runtime_checked_type(
                        value_type, value, f"variable '{statement.name}'"
                    )
                environment.define(
                    statement.name,
                    value,
                    statement.constant,
                    array_type=array_type,
                    object_type=object_type,
                    value_type=value_type,
                )
        elif isinstance(statement, EnumDeclaration):
            self._define_enum(statement, environment)
        elif isinstance(statement, ExpressionStatement):
            self._evaluate(statement.expression, environment)
        elif isinstance(statement, IfStatement):
            if self._is_truthy(self._evaluate(statement.condition, environment)):
                self._execute_block(statement.then_branch.statements, Environment(environment))
            elif statement.else_branch is not None:
                self._execute(statement.else_branch, environment)
        elif isinstance(statement, WhileStatement):
            self._execute_while(statement, environment)
        elif isinstance(statement, DoWhileStatement):
            self._execute_do_while(statement, environment)
        elif isinstance(statement, ForStatement):
            self._execute_for(statement, environment)
        elif isinstance(statement, ClassicForStatement):
            self._execute_classic_for(statement, environment)
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

    def _execute_do_while(
        self, statement: DoWhileStatement, environment: Environment
    ) -> None:
        while True:
            should_continue = True
            try:
                self._execute_block(statement.body.statements, Environment(environment))
            except LoopSignal as loop_signal:
                should_continue = loop_signal.is_continue
            if not should_continue:
                break
            if not self._is_truthy(self._evaluate(statement.condition, environment)):
                break

    def _execute_for(self, statement: ForStatement, environment: Environment) -> None:
        iterable = self._evaluate(statement.iterable, environment)
        if statement.iteration_mode == "in":
            # Unwrap XCollectionInstance so we can iterate its raw _data
            if isinstance(iterable, XCollectionInstance):
                iterable = iterable._data
            if isinstance(iterable, dict):
                iterator = iter(iterable.keys())
            elif isinstance(iterable, XInstance):
                iterator = iter(iterable.fields.keys())
            else:
                try:
                    iterator = iter(iterable)
                except TypeError as error:
                    raise RuntimeErrorX(
                        "for-in requires an object or iterable value"
                    ) from error
        else:
            # Unwrap XCollectionInstance — PriorityQueue uses a dict with 'heap'
            if isinstance(iterable, XCollectionInstance):
                inner = iterable._data
                iterable = inner["heap"] if isinstance(inner, dict) and "heap" in inner else inner
            try:
                iterator = iter(iterable)
            except TypeError as error:
                raise RuntimeErrorX("Value in for loop is not iterable") from error
        for value in iterator:
            loop_environment = Environment(environment)
            if statement.binding_pattern is not None:
                self._bind_destructuring(
                    statement.binding_pattern,
                    value,
                    loop_environment,
                    statement.constant,
                )
            else:
                loop_environment.define(
                    statement.variable, value, constant=statement.constant
                )
            try:
                self._execute_block(statement.body.statements, loop_environment)
            except LoopSignal as loop_signal:
                if not loop_signal.is_continue:
                    break

    def _execute_classic_for(
        self, statement: ClassicForStatement, environment: Environment
    ) -> None:
        loop_environment = Environment(environment)
        if statement.initializer is not None:
            self._execute(statement.initializer, loop_environment)
        while statement.condition is None or self._is_truthy(
            self._evaluate(statement.condition, loop_environment)
        ):
            should_break = False
            try:
                self._execute_block(statement.body.statements, loop_environment)
            except LoopSignal as loop_signal:
                should_break = not loop_signal.is_continue
            if should_break:
                break
            if statement.increment is not None:
                self._evaluate(statement.increment, loop_environment)

    def _execute_try(self, statement: TryStatement, environment: Environment) -> None:
        pending_error: BaseException | None = None
        try:
            self._execute_block(statement.body.statements, Environment(environment))
        except ThrownValue as thrown:
            self.annotate_error(thrown)
            if isinstance(thrown.value, XExceptionValue) and not thrown.value.stack:
                thrown.value.stack = self._source_stack(
                    thrown.source_name, thrown.line, thrown.column
                )
            elif (
                isinstance(thrown.value, XInstance)
                and self._is_throwable_instance(thrown.value)
                and not thrown.value.fields.get("stack")
            ):
                thrown.value.fields["stack"] = self._source_stack(
                    thrown.source_name, thrown.line, thrown.column
                )
            pending_error = thrown
            self._run_matching_catch(
                thrown.value, statement.catches, environment, thrown
            )
            pending_error = None
        except RuntimeErrorX as error:
            self.annotate_error(error)
            cause = (
                XExceptionValue(str(error.__cause__), "Exception")
                if error.__cause__ is not None
                else None
            )
            runtime_value = XExceptionValue(
                str(error),
                error.exception_name,
                cause,
                self._source_stack(
                    error.source_name, error.line, error.column
                ),
            )
            pending_error = error
            self._run_matching_catch(
                runtime_value, statement.catches, environment, error
            )
            pending_error = None
        except (ArithmeticError, TypeError, ValueError, IndexError, KeyError) as error:
            exception_name = self._native_exception_name(error)
            wrapped_error = RuntimeErrorX(str(error), exception_name)
            self.annotate_error(wrapped_error)
            runtime_value = XExceptionValue(
                str(error),
                exception_name,
                stack=self._source_stack(
                    wrapped_error.source_name,
                    wrapped_error.line,
                    wrapped_error.column,
                ),
            )
            pending_error = wrapped_error
            self._run_matching_catch(
                runtime_value, statement.catches, environment, wrapped_error
            )
            pending_error = None
        finally:
            if statement.finally_body is not None:
                self._execute_block(statement.finally_body.statements, Environment(environment))

        if pending_error is not None:
            raise pending_error

    def _run_matching_catch(
        self,
        value: Any,
        catches: list[tuple[str | None, str, Block]],
        environment: Environment,
        source_error: RuntimeErrorX | ThrownValue | None = None,
    ) -> None:
        for catch_type, catch_name, catch_body in catches:
            if self._exception_matches(value, catch_type):
                catch_environment = Environment(environment)
                catch_environment.define(catch_name, value)
                self._execute_block(catch_body.statements, catch_environment)
                return
        if isinstance(value, XExceptionValue):
            raise ThrownValue(
                value,
                getattr(source_error, "source_name", None)
                or getattr(value.cause, "source_name", None),
                getattr(source_error, "line", None)
                or getattr(value.cause, "line", None),
                getattr(source_error, "column", None)
                or getattr(value.cause, "column", None),
            )
        raise ThrownValue(
            value,
            getattr(source_error, "source_name", None),
            getattr(source_error, "line", None),
            getattr(source_error, "column", None),
        )

    def _exception_matches(self, value: Any, type_name: str | None) -> bool:
        if type_name is None:
            return True
        requested_types = type_name.split("|")
        if isinstance(value, XExceptionValue):
            for requested_type in requested_types:
                current_type: str | None = value.name
                while current_type is not None:
                    if current_type == requested_type:
                        return True
                    current_type = self.EXCEPTION_PARENTS.get(current_type)
            return False
        if "Throwable" in requested_types:
            return True
        if isinstance(value, XInstance):
            for requested_type in requested_types:
                current_class: XClass | None = value.xclass
                while current_class is not None:
                    if current_class.name == requested_type:
                        return True
                    current_class = current_class.parent
        return False

    def _is_throwable_instance(self, value: XInstance) -> bool:
        current_class: XClass | None = value.xclass
        while current_class is not None:
            if current_class.is_exception_base:
                return True
            current_class = current_class.parent
        return False

    def _native_exception_name(self, error: BaseException) -> str:
        if isinstance(error, ArithmeticError):
            return "ArithmeticException"
        if isinstance(error, (TypeError, ValueError)):
            return "TypeException"
        if isinstance(error, (IndexError, KeyError)):
            return "IndexOutOfBoundsException"
        if isinstance(error, OSError):
            return "FileSystemException"
        return "RuntimeException"

    def _arrow_function(
        self, expression: FunctionExpression, environment: Environment
    ) -> XFunction:
        """Evaluate an arrow function into a closured function value."""
        declaration = FunctionDeclaration(
            "<arrow>",
            expression.parameters,
            expression.body,
            expression.return_type,
            set(),
            [],
            expression.is_async,
            [],
        )
        return XFunction(declaration, environment, self)

    def _evaluate(self, expression: Any, environment: Environment) -> Any:
        if isinstance(expression, Literal):
            return expression.value
        if isinstance(expression, UndefinedLiteral):
            return UNDEFINED
        if isinstance(expression, TemplateLiteral):
            return "".join(
                part
                if isinstance(part, str)
                else self._stringify(self._evaluate(part, environment))
                for part in expression.parts
            )
        if isinstance(expression, Identifier):
            value = self._lookup(environment, expression.name)
            if (
                isinstance(value, list)
                and value
                and all(isinstance(item, XFunction) for item in value)
            ):
                return OverloadedFunction(expression.name, value)
            return value
        if isinstance(expression, ArrayLiteral):
            items: list[Any] = []
            for item in expression.items:
                if isinstance(item, Spread):
                    items.extend(self._spread_values(self._evaluate(item.value, environment)))
                else:
                    items.append(self._evaluate(item, environment))
            return items
        if isinstance(expression, ObjectLiteral):
            fields: dict[str, Any] = {}
            for name, value in expression.entries:
                if name is None:
                    spread_fields = self._evaluate(value.value, environment)
                    if isinstance(spread_fields, XInstance):
                        spread_fields = spread_fields.fields
                    if not isinstance(spread_fields, dict):
                        raise RuntimeErrorX("Object spread requires an object value")
                    fields.update(spread_fields)
                else:
                    fields[name] = self._evaluate(value, environment)
            return fields
        if isinstance(expression, FunctionExpression):
            return self._arrow_function(expression, environment)
        if isinstance(expression, AwaitExpression):
            value = self._evaluate(expression.value, environment)
            if not inspect.isawaitable(value):
                raise RuntimeErrorX(
                    "await requires an asynchronous operation; "
                    "use it with an async function or async API"
                )
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self._await_result(value))
            raise RuntimeErrorX(
                "Cannot await inside an active Python event loop in this interpreter"
            )
        if isinstance(expression, MatchExpression):
            return self._evaluate_match(expression, environment)
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
            arguments = self._evaluate_call_arguments(expression.arguments, environment)
            return self._call(callee, arguments)
        if isinstance(expression, OptionalChain):
            return self._evaluate_optional_chain(expression, environment)
        if isinstance(expression, NewExpression):
            class_name = expression.class_name.split("<", 1)[0]
            class_value = self._resolve_name(environment, class_name)
            arguments = self._evaluate_call_arguments(expression.arguments, environment)
            if isinstance(class_value, BuiltinFunction):
                return self._call(class_value, arguments)
            # Support `new Stack()`, `new Collections.Stack()` etc. —
            # collection namespaces are dicts of BuiltinFunctions with a "create" entry.
            if isinstance(class_value, dict) and "create" in class_value:
                return self._call(class_value["create"], arguments)
            if not isinstance(class_value, XClass):
                raise RuntimeErrorX(f"'{expression.class_name}' is not a constructible class")
            return class_value.construct(arguments)
        if isinstance(expression, Member):
            object_value = self._evaluate(expression.object, environment)
            access_context = self._access_context(environment)
            return self._get_member(object_value, expression.name, access_context)
        if isinstance(expression, Index):
            object_value = self._evaluate(expression.object, environment)
            index = self._evaluate(expression.index, environment)
            try:
                return object_value[index]
            except (IndexError, KeyError, TypeError) as error:
                raise RuntimeErrorX(f"Cannot access index {self._stringify(index)}") from error
        raise RuntimeErrorX(f"Unsupported expression '{type(expression).__name__}'")

    def _evaluate_optional_chain(
        self, expression: OptionalChain, environment: Environment
    ) -> Any:
        value = self._evaluate(expression.object, environment)
        for segment in expression.segments:
            if value is None or value is UNDEFINED:
                if segment.optional:
                    return UNDEFINED
                nullish_name = "undefined" if value is UNDEFINED else "null"
                raise RuntimeErrorX(
                    f"Cannot continue optional chain from {nullish_name}"
                )
            if segment.kind == "member":
                value = (
                    self._get_optional_member(
                        value, segment.value, self._access_context(environment)
                    )
                    if segment.optional
                    else self._get_member(
                        value, segment.value, self._access_context(environment)
                    )
                )
            elif segment.kind == "index":
                index = self._evaluate(segment.value, environment)
                try:
                    value = value[index]
                except (IndexError, KeyError) as error:
                    if segment.optional:
                        return UNDEFINED
                    raise RuntimeErrorX(
                        f"Cannot access index {self._stringify(index)}"
                    ) from error
                except TypeError as error:
                    raise RuntimeErrorX(
                        f"Cannot access index {self._stringify(index)}"
                    ) from error
            elif segment.kind == "call":
                arguments = segment.value[0]
                if segment.optional and (value is None or value is UNDEFINED):
                    return UNDEFINED
                evaluated_arguments = self._evaluate_call_arguments(
                    arguments, environment
                )
                value = self._call(value, evaluated_arguments)
            else:
                raise RuntimeErrorX(
                    f"Unsupported optional chain segment '{segment.kind}'"
                )
        return value

    def _get_optional_member(
        self, object_value: Any, name: str, access_context: XClass | None
    ) -> Any:
        if isinstance(object_value, dict):
            return object_value.get(name, UNDEFINED)
        try:
            return self._get_member(object_value, name, access_context)
        except RuntimeErrorX as error:
            if any(
                message in error.message
                for message in (
                    "Object has no field",
                    "has no member",
                    "has no field",
                    "has no method",
                    "Value has no member",
                    "is not defined",
                )
            ):
                return UNDEFINED
            raise

    def _evaluate_match(
        self, expression: MatchExpression, environment: Environment
    ) -> Any:
        value = self._evaluate(expression.value, environment)
        for arm in expression.arms:
            bindings = self._match_pattern(arm.pattern, value, environment)
            if bindings is None:
                continue
            arm_environment = Environment(environment)
            for name, binding_value in bindings.items():
                arm_environment.define(name, binding_value)
            if arm.guard is not None and not self._is_truthy(
                self._evaluate(arm.guard, arm_environment)
            ):
                continue
            if isinstance(arm.body, Block):
                self._execute_block(arm.body.statements, Environment(arm_environment))
                return None
            return self._evaluate(arm.body, arm_environment)
        raise RuntimeErrorX("No pattern matched the value")

    def _match_pattern(
        self, pattern: Any, value: Any, environment: Environment
    ) -> dict[str, Any] | None:
        if isinstance(pattern, WildcardPattern):
            return {}
        if isinstance(pattern, BindingPattern):
            return {pattern.name: value}
        if isinstance(pattern, LiteralPattern):
            if self._strict_equal(value, pattern.value):
                return {}
            return None
        if isinstance(pattern, UndefinedPattern):
            return {} if value is UNDEFINED else None
        if isinstance(pattern, EnumPattern):
            try:
                enum_value = environment.get(pattern.enum_name)
            except RuntimeErrorX:
                return None
            if not isinstance(enum_value, Environment):
                return None
            try:
                expected_member = enum_value.get(pattern.member_name)
            except RuntimeErrorX:
                return None
            if self._strict_equal(value, expected_member):
                return {}
            return None
        if isinstance(pattern, tuple) and pattern and pattern[0] == "or":
            for alternative in pattern[1]:
                alternative_bindings = self._match_pattern(
                    alternative, value, environment
                )
                if alternative_bindings is not None:
                    return alternative_bindings
            return None
        if isinstance(pattern, ArrayPattern):
            if not isinstance(value, (list, tuple, str)):
                return None
            if len(value) < len(pattern.items):
                return None
            if pattern.rest_name is None and len(value) != len(pattern.items):
                return None
            array_bindings: dict[str, Any] = {}
            for index, child_pattern in enumerate(pattern.items):
                child_bindings = self._match_pattern(
                    child_pattern, value[index], environment
                )
                if child_bindings is None:
                    return None
                array_bindings.update(child_bindings)
            if pattern.rest_name is not None:
                array_bindings[pattern.rest_name] = list(value[len(pattern.items):])
            return array_bindings
        if isinstance(pattern, ObjectPattern):
            object_value = value.fields if isinstance(value, XInstance) else value
            if not isinstance(object_value, dict):
                return None
            object_bindings: dict[str, Any] = {}
            for name, child_pattern in pattern.fields:
                if name not in object_value:
                    return None
                child_bindings = self._match_pattern(
                    child_pattern, object_value[name], environment
                )
                if child_bindings is None:
                    return None
                object_bindings.update(child_bindings)
            if pattern.rest_name is not None:
                object_bindings[pattern.rest_name] = {
                    name: field_value
                    for name, field_value in object_value.items()
                    if name not in {field_name for field_name, _ in pattern.fields}
                }
            return object_bindings
        return None

    def _bind_destructuring(
        self,
        pattern: Any,
        value: Any,
        environment: Environment,
        constant: bool,
        declare: bool = True,
    ) -> None:
        if isinstance(pattern, DefaultPattern):
            selected_value = value
            if selected_value is None:
                selected_value = self._evaluate(pattern.default_value, environment)
            self._bind_destructuring(
                pattern.pattern, selected_value, environment, constant, declare
            )
            return
        if isinstance(pattern, BindingPattern):
            if declare:
                environment.define(pattern.name, value, constant)
            else:
                environment.assign(pattern.name, value)
            return
        if isinstance(pattern, ArrayPattern):
            if not isinstance(value, (list, tuple, str)):
                raise RuntimeErrorX("Array destructuring requires an array-like value")
            for item_index, item_pattern in enumerate(pattern.items):
                item_value = value[item_index] if item_index < len(value) else None
                self._bind_destructuring(
                    item_pattern, item_value, environment, constant, declare
                )
            if pattern.rest_name is not None:
                rest_value = list(value[len(pattern.items):])
                if declare:
                    environment.define(pattern.rest_name, rest_value, constant)
                else:
                    environment.assign(pattern.rest_name, rest_value)
            return
        if isinstance(pattern, ObjectPattern):
            if isinstance(value, XInstance):
                source_fields = value.fields
            elif isinstance(value, dict):
                source_fields = value
            else:
                raise RuntimeErrorX("Object destructuring requires an object value")
            used_names: set[str] = set()
            for field_name, field_pattern in pattern.fields:
                used_names.add(field_name)
                self._bind_destructuring(
                    field_pattern,
                    source_fields.get(field_name),
                    environment,
                    constant,
                    declare,
                )
            if pattern.rest_name is not None:
                remaining_fields = {
                    field_name: field_value
                    for field_name, field_value in source_fields.items()
                    if field_name not in used_names
                }
                if declare:
                    environment.define(pattern.rest_name, remaining_fields, constant)
                else:
                    environment.assign(pattern.rest_name, remaining_fields)
            return
        raise RuntimeErrorX("Unsupported destructuring pattern")

    def _evaluate_call_arguments(
        self, expressions: list[Any], environment: Environment
    ) -> list[Any]:
        arguments: list[Any] = []
        for expression in expressions:
            if isinstance(expression, Spread):
                spread_value = self._evaluate(expression.value, environment)
                arguments.extend(self._spread_values(spread_value))
            else:
                arguments.append(self._evaluate(expression, environment))
        return arguments

    def _spread_values(self, value: Any) -> list[Any]:
        if isinstance(value, (list, tuple, str)):
            return list(value)
        raise RuntimeErrorX("Spread value must be an array, tuple, or string")

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
                return self._loose_equal(left, right)
            if operator == "!=":
                return not self._loose_equal(left, right)
            if operator == "===":
                return self._strict_equal(left, right)
            if operator == "!==":
                return not self._strict_equal(left, right)
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
        except ZeroDivisionError as error:
            raise RuntimeErrorX(
                f"Division by zero for '{operator}'", "ArithmeticException"
            ) from error
        except TypeError as error:
            raise RuntimeErrorX(
                f"Invalid operands for '{operator}'", "TypeException"
            ) from error
        raise RuntimeErrorX(f"Unknown binary operator '{operator}'")

    def _strict_equal(self, left: Any, right: Any) -> bool:
        if isinstance(left, XEnumMember) or isinstance(right, XEnumMember):
            return (
                isinstance(left, XEnumMember)
                and isinstance(right, XEnumMember)
                and left.enum_identity is right.enum_identity
                and left.name == right.name
            )
        if self._is_number(left) and self._is_number(right):
            return left == right
        if type(left) is not type(right):
            return False
        if isinstance(left, (list, dict, XInstance, XClass, XFunction)):
            return left is right
        return left == right

    def _loose_equal(self, left: Any, right: Any) -> bool:
        if isinstance(left, XEnumMember) or isinstance(right, XEnumMember):
            return self._strict_equal(left, right)
        if left is None or right is None or left is UNDEFINED or right is UNDEFINED:
            return (left is None or left is UNDEFINED) and (
                right is None or right is UNDEFINED
            )
        if self._is_number(left) and self._is_number(right):
            return left == right
        if type(left) is type(right):
            return self._strict_equal(left, right)
        if isinstance(left, bool):
            return self._loose_equal(int(left), right)
        if isinstance(right, bool):
            return self._loose_equal(left, int(right))
        if isinstance(left, str) and self._is_number(right):
            converted_left = self._string_to_number(left)
            return converted_left is not None and converted_left == right
        if isinstance(right, str) and self._is_number(left):
            converted_right = self._string_to_number(right)
            return converted_right is not None and left == converted_right
        return False

    def _is_number(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _string_to_number(self, value: str) -> int | float | None:
        stripped_value = value.strip()
        if stripped_value == "":
            return 0
        try:
            if "." not in stripped_value:
                return int(stripped_value)
            return float(stripped_value)
        except ValueError:
            return None

    def _assign(self, target: Any, operator: str, value: Any, environment: Environment) -> Any:
        if isinstance(target, (ArrayPattern, ObjectPattern)):
            if operator != "=":
                raise RuntimeErrorX("Destructuring assignment only supports '='")
            self._bind_destructuring(
                target, value, environment, constant=False, declare=False
            )
            return value
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
            access_context = self._access_context(environment)
            return self._get_member(
                self._evaluate(target.object, environment),
                target.name,
                access_context,
            )
        if isinstance(target, Index):
            return self._evaluate(target.object, environment)[self._evaluate(target.index, environment)]
        raise RuntimeErrorX("Invalid assignment target")

    def _write_target(self, target: Any, value: Any, environment: Environment) -> None:
        if isinstance(target, Identifier):
            array_type = environment.get_array_type(target.name)
            if array_type is not None:
                value = self._coerce_typed_array(
                    array_type, value, f"variable '{target.name}'"
                )
            object_type = environment.get_object_type(target.name)
            if object_type is not None:
                value = self._coerce_typed_object(
                    object_type, value, f"variable '{target.name}'"
                )
            value_type = environment.get_value_type(target.name)
            if value_type is not None:
                value = self._coerce_runtime_checked_type(
                    value_type, value, f"variable '{target.name}'"
                )
            environment.assign(target.name, value)
            return
        if isinstance(target, Member):
            object_value = self._evaluate(target.object, environment)
            access_context = self._access_context(environment)
            self._set_member(object_value, target.name, value, access_context)
            return
        if isinstance(target, Index):
            object_value = self._evaluate(target.object, environment)
            index = self._evaluate(target.index, environment)
            object_value[index] = value
            return
        raise RuntimeErrorX("Invalid assignment target")

    def _access_context(self, environment: Environment) -> XClass | None:
        current_environment: Environment | None = environment
        while current_environment is not None:
            declaring_class = current_environment.values.get("__x_current_class__")
            if isinstance(declaring_class, XClass):
                return declaring_class
            current_environment = current_environment.parent
        return None

    def _class_is_or_extends(self, candidate: XClass | None, target: XClass) -> bool:
        current_class = candidate
        while current_class is not None:
            if current_class is target:
                return True
            current_class = current_class.parent
        return False

    def _can_access_member(
        self, modifiers: set[str], owner: XClass, requester: XClass | None
    ) -> bool:
        visibility = self._visibility(modifiers)
        if visibility == "public":
            return True
        if visibility == "private":
            return requester is owner
        return self._class_is_or_extends(requester, owner)

    def _visibility(self, modifiers: set[str]) -> str:
        for visibility in ("private", "protected", "public"):
            if visibility in modifiers:
                return visibility
        return "public"

    def _find_field_owner(
        self, xclass: XClass, name: str, is_static: bool = False
    ) -> tuple[XClass, VariableDeclaration] | None:
        current_class: XClass | None = xclass
        while current_class is not None:
            for member in current_class.declaration.members:
                if (
                    isinstance(member, VariableDeclaration)
                    and member.name == name
                    and ("static" in member.modifiers) == is_static
                ):
                    return current_class, member
            current_class = current_class.parent
        return None

    def _find_method_owner(
        self, xclass: XClass, method: FunctionDeclaration
    ) -> XClass | None:
        current_class: XClass | None = xclass
        while current_class is not None:
            if any(member is method for member in current_class.declaration.members):
                return current_class
            current_class = current_class.parent
        return None

    def _static_member_via_instance(
        self, xclass: XClass, name: str, access_context: XClass | None
    ) -> tuple[str, Any] | None:
        """Resolve a static field or method reached through an instance.

        Returns ``(owner class name, value)`` or ``None`` when the class
        hierarchy declares no static member with that name.  Callers use this
        to emit a warning instead of failing, so that legacy code that calls
        static members on instances keeps running.
        """
        field_definition = self._find_field_owner(xclass, name, is_static=True)
        if field_definition is not None:
            field_owner, field_declaration = field_definition
            if not self._can_access_member(
                field_declaration.modifiers, field_owner, access_context
            ):
                visibility = self._visibility(field_declaration.modifiers)
                raise RuntimeErrorX(
                    f"Cannot access {visibility} property '{field_owner.name}.{name}'"
                )
            return field_owner.name, field_owner.static_fields[name]
        for candidate_class in self._class_hierarchy(xclass):
            for member in candidate_class.declaration.members:
                if (
                    isinstance(member, FunctionDeclaration)
                    and member.name == name
                    and "static" in member.modifiers
                ):
                    if not self._can_access_member(
                        member.modifiers, candidate_class, access_context
                    ):
                        visibility = self._visibility(member.modifiers)
                        raise RuntimeErrorX(
                            f"Cannot access {visibility} method "
                            f"'{candidate_class.name}.{name}'"
                        )
                    function = XFunction(
                        member,
                        candidate_class.closure,
                        self,
                        parent_class=candidate_class,
                    )
                    return candidate_class.name, self._apply_function_decorators(
                        member.decorators, function, candidate_class.closure
                    )
        return None

    def _get_member(
        self,
        object_value: Any,
        name: str,
        access_context: XClass | None = None,
    ) -> Any:
        # OOP-style dot access on a collection instance: students.add(x)
        if isinstance(object_value, XCollectionInstance):
            methods = object_value._methods
            if name not in methods:
                raise RuntimeErrorX(
                    f"{object_value.collection_type} has no method '{name}'"
                )
            original = methods[name]
            data = object_value._data
            return BuiltinFunction(
                f"{object_value.collection_type}.{name}",
                lambda arguments, orig=original, d=data: orig.call([d] + arguments),
            )
        if isinstance(object_value, XExceptionValue):
            if name == "message":
                return object_value.message
            if name == "name":
                return object_value.name
            if name == "cause":
                return object_value.cause
            if name == "stack":
                return object_value.stack
            raise RuntimeErrorX(
                f"{object_value.name} has no property '{name}'"
            )
        if isinstance(object_value, XThreadHandle):
            if name == "join":
                return BuiltinFunction(
                    "ThreadHandle.join",
                    lambda arguments: self._thread_join(object_value, arguments),
                )
            if name == "isAlive":
                return BuiltinFunction(
                    "ThreadHandle.isAlive",
                    lambda arguments: self._thread_is_alive(object_value, arguments),
                )
        if isinstance(object_value, XInstance):
            # Check for Python class wrapper methods
            if hasattr(object_value.xclass, 'method_impls') and name in object_value.xclass.method_impls:
                method_impl = object_value.xclass.method_impls[name]
                return BuiltinFunction(
                    f"{object_value.xclass.name}.{name}",
                    lambda arguments, this=object_value, impl=method_impl: impl(this, arguments)
                )
            
            if name in object_value.fields:
                field_definition = self._find_field_owner(object_value.xclass, name)
                if field_definition is not None:
                    field_owner, field_declaration = field_definition
                    if not self._can_access_member(
                        field_declaration.modifiers, field_owner, access_context
                    ):
                        visibility = self._visibility(field_declaration.modifiers)
                        raise RuntimeErrorX(
                            f"Cannot access {visibility} property "
                            f"'{object_value.xclass.name}.{name}'"
                        )
                return object_value.fields[name]
            methods = object_value.xclass.find_methods(name)
            if methods:
                bound_methods: list[XFunction] = []
                denied_visibility: str | None = None
                for method in methods:
                    method_owner = self._find_method_owner(object_value.xclass, method)
                    if method_owner is not None and not self._can_access_member(
                        method.modifiers, method_owner, access_context
                    ):
                        denied_visibility = self._visibility(method.modifiers)
                        continue
                    bound_function = XFunction(
                        method,
                        method_owner.closure if method_owner is not None else object_value.xclass.closure,
                        self,
                        object_value,
                        method_owner or object_value.xclass,
                    )
                    bound_function = self._apply_function_decorators(
                        method.decorators, bound_function, object_value.xclass.closure
                    )
                    bound_methods.append(bound_function)
                if not bound_methods and denied_visibility is not None:
                    raise RuntimeErrorX(
                        f"Cannot access {denied_visibility} method "
                        f"'{object_value.xclass.name}.{name}'"
                    )
                return OverloadedFunction(
                    name,
                    bound_methods,
                )
            static_member = self._static_member_via_instance(
                object_value.xclass, name, access_context
            )
            if static_member is not None:
                owner_name, value = static_member
                self.warn(
                    f"'{name}' is a static member of '{owner_name}' and must be "
                    f"accessed through the class; calling it on an instance is "
                    f"deprecated"
                )
                return value
            raise RuntimeErrorX(f"'{object_value.xclass.name}' has no member '{name}'")
        if isinstance(object_value, XSuper):
            methods = object_value.parent_class.find_methods(name)
            if methods:
                bound_methods: list[XFunction] = []
                denied_visibility: str | None = None
                for method in methods:
                    method_owner = self._find_method_owner(
                        object_value.parent_class, method
                    )
                    if method_owner is not None and not self._can_access_member(
                        method.modifiers, method_owner, access_context
                    ):
                        denied_visibility = self._visibility(method.modifiers)
                        continue
                    bound_function = XFunction(
                        method,
                        method_owner.closure if method_owner is not None else object_value.parent_class.closure,
                        self,
                        object_value.instance,
                        method_owner or object_value.parent_class,
                    )
                    bound_function = self._apply_function_decorators(
                        method.decorators,
                        bound_function,
                        object_value.parent_class.closure,
                    )
                    bound_methods.append(bound_function)
                if not bound_methods and denied_visibility is not None:
                    raise RuntimeErrorX(
                        f"Cannot access {denied_visibility} method "
                        f"'{object_value.parent_class.name}.{name}'"
                    )
                return OverloadedFunction(
                    name,
                    bound_methods,
                )
            raise RuntimeErrorX(f"Parent class has no method '{name}'")
        if isinstance(object_value, Environment):
            return self._lookup(object_value, name)
        if isinstance(object_value, list):
            if name == "length":
                return len(object_value)
            if name == "add":
                return BuiltinFunction(
                    "add", lambda arguments: self._list_add(object_value, arguments)
                )
            array_member = self._array_member(object_value, name)
            if array_member is not None:
                return array_member
        elif isinstance(object_value, str):
            if name == "length":
                return len(object_value)
            if name == "toString":
                return BuiltinFunction(
                    "toString",
                    lambda arguments: self._no_argument_string(object_value, arguments),
                )
            string_member = self._string_member(object_value, name)
            if string_member is not None:
                return string_member
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
        if isinstance(object_value, XClass):
            if name in object_value.nested_types:
                nested_declaration = next(
                    (
                        member
                        for member in object_value.declaration.members
                        if isinstance(member, ClassDeclaration) and member.name == name
                    ),
                    None,
                )
                if nested_declaration is not None and not self._can_access_member(
                    nested_declaration.modifiers, object_value, access_context
                ):
                    visibility = self._visibility(nested_declaration.modifiers)
                    raise RuntimeErrorX(
                        f"Cannot access {visibility} nested class "
                        f"'{object_value.name}.{name}'"
                    )
                return object_value.nested_types[name]
            static_field = self._find_field_owner(object_value, name, is_static=True)
            if static_field is not None:
                field_owner, field_declaration = static_field
                if not self._can_access_member(
                    field_declaration.modifiers, field_owner, access_context
                ):
                    visibility = self._visibility(field_declaration.modifiers)
                    raise RuntimeErrorX(
                        f"Cannot access {visibility} property '{field_owner.name}.{name}'"
                    )
                return field_owner.static_fields[name]
            for candidate_class in self._class_hierarchy(object_value):
                for member in candidate_class.declaration.members:
                    if (
                        isinstance(member, FunctionDeclaration)
                        and member.name == name
                        and "static" in member.modifiers
                    ):
                        if not self._can_access_member(
                            member.modifiers, candidate_class, access_context
                        ):
                            visibility = self._visibility(member.modifiers)
                            raise RuntimeErrorX(
                                f"Cannot access {visibility} method "
                                f"'{candidate_class.name}.{name}'"
                            )
                        function = XFunction(
                            member, candidate_class.closure, self, parent_class=candidate_class
                        )
                        return self._apply_function_decorators(
                            member.decorators, function, candidate_class.closure
                        )
        if object_value is UNDEFINED:
            raise RuntimeErrorX(f"Cannot access member '{name}' on undefined")
        if object_value is None:
            raise RuntimeErrorX(f"Cannot access member '{name}' on null")
        raise RuntimeErrorX(f"Value has no member '{name}'")

    def _array_member(self, array: list[Any], name: str) -> BuiltinFunction | None:
        """Bound dot-callable for array method *name*, or None if not one.

        ``myArray.map(cb)`` binds *array* as the receiver argument, so the
        same implementation also serves the functional ``List.map(array, cb)``
        form.
        """
        implementation_name = _ARRAY_METHODS.get(name)
        if implementation_name is None:
            return None
        implementation = getattr(self, implementation_name)
        return BuiltinFunction(
            f"Array.{name}",
            lambda arguments, receiver=array, call=implementation: call(
                [receiver] + arguments
            ),
        )

    def _string_member(self, text: str, name: str) -> BuiltinFunction | None:
        """Bound dot-callable for string method *name*, or None if not one.

        Strings are sequences of Unicode code points: every index argument
        (``charAt``, ``substring``, ``slice``, ...) counts code points exactly
        like Python ``str`` indexing — not UTF-16 code units, and not grapheme
        clusters — matching the documented behavior of ``text[index]``.
        """
        implementation_name = _STRING_METHODS.get(name)
        if implementation_name is None:
            return None
        implementation = getattr(self, implementation_name)
        return BuiltinFunction(
            f"String.{name}",
            lambda arguments, receiver=text, call=implementation: call(
                [receiver] + arguments
            ),
        )

    def _class_hierarchy(self, xclass: XClass) -> list[XClass]:
        hierarchy: list[XClass] = []
        current_class: XClass | None = xclass
        while current_class is not None:
            hierarchy.append(current_class)
            current_class = current_class.parent
        return hierarchy

    def _set_member(
        self,
        object_value: Any,
        name: str,
        value: Any,
        access_context: XClass | None = None,
    ) -> None:
        if isinstance(object_value, XInstance):
            field_definition = self._find_field_owner(object_value.xclass, name)
            if field_definition is not None:
                field_owner, field_declaration = field_definition
                if not self._can_access_member(
                    field_declaration.modifiers, field_owner, access_context
                ):
                    visibility = self._visibility(field_declaration.modifiers)
                    raise RuntimeErrorX(
                        f"Cannot modify {visibility} property "
                        f"'{object_value.xclass.name}.{name}'"
                    )
                if "final" in field_declaration.modifiers and not (
                    self._inside_defining_constructor(field_owner)
                ):
                    self._set_declaration_location(field_declaration)
                    final_error = RuntimeErrorX(
                        f"Cannot assign to final property "
                        f"'{field_owner.name}.{name}'"
                    )
                    self.annotate_error(final_error)
                    raise final_error
                if (
                    field_declaration.type_name is not None
                    and field_declaration.type_name.endswith("[]")
                ):
                    value = self._coerce_typed_array(
                        field_declaration.type_name,
                        value,
                        f"property '{field_owner.name}.{name}'",
                    )
                if (
                    field_declaration.type_name is not None
                    and field_declaration.type_name.startswith("object<")
                ):
                    value = self._coerce_typed_object(
                        field_declaration.type_name,
                        value,
                        f"property '{field_owner.name}.{name}'",
                    )
                if (
                    field_declaration.type_name is not None
                    and self._needs_runtime_type_check(field_declaration.type_name)
                ):
                    value = self._coerce_runtime_checked_type(
                        field_declaration.type_name,
                        value,
                        f"property '{field_owner.name}.{name}'",
                    )
            object_value.fields[name] = value
            return
        if isinstance(object_value, XClass):
            field_definition = self._find_field_owner(object_value, name, is_static=True)
            if field_definition is None:
                raise RuntimeErrorX(f"'{object_value.name}' has no static field '{name}'")
            field_owner, field_declaration = field_definition
            if not self._can_access_member(
                field_declaration.modifiers, field_owner, access_context
            ):
                visibility = self._visibility(field_declaration.modifiers)
                raise RuntimeErrorX(
                    f"Cannot modify {visibility} property '{field_owner.name}.{name}'"
                )
            if "final" in field_declaration.modifiers:
                self._set_declaration_location(field_declaration)
                final_error = RuntimeErrorX(
                    f"Cannot assign to final static field '{field_owner.name}.{name}'"
                )
                self.annotate_error(final_error)
                raise final_error
            if (
                field_declaration.type_name is not None
                and field_declaration.type_name.endswith("[]")
            ):
                value = self._coerce_typed_array(
                    field_declaration.type_name,
                    value,
                    f"property '{field_owner.name}.{name}'",
                )
            if (
                field_declaration.type_name is not None
                and field_declaration.type_name.startswith("object<")
            ):
                value = self._coerce_typed_object(
                    field_declaration.type_name,
                    value,
                    f"property '{field_owner.name}.{name}'",
                )
            if (
                field_declaration.type_name is not None
                and self._needs_runtime_type_check(field_declaration.type_name)
            ):
                value = self._coerce_runtime_checked_type(
                    field_declaration.type_name,
                    value,
                    f"property '{field_owner.name}.{name}'",
                )
            field_owner.static_fields[name] = value
            return
        if isinstance(object_value, dict):
            object_value[name] = value
            return
        raise RuntimeErrorX(f"Cannot assign member '{name}'")

    def _initialize_fields(self, instance: XInstance, xclass: XClass) -> None:
        if xclass.parent is not None:
            self._initialize_fields(instance, xclass.parent)
        if xclass.is_exception_base:
            instance.fields.setdefault("message", "")
            instance.fields.setdefault("name", instance.xclass.name)
            instance.fields.setdefault("cause", None)
            instance.fields.setdefault("stack", "")
        for member in xclass.declaration.members:
            if isinstance(member, VariableDeclaration):
                if "static" in member.modifiers:
                    continue
                value = None if member.initializer is None else self._evaluate(
                    member.initializer, self._field_initializer_environment(xclass, member)
                )
                if (
                    member.type_name is not None
                    and member.type_name.endswith("[]")
                    and member.initializer is not None
                ):
                    value = self._coerce_typed_array(
                        member.type_name,
                        value,
                        f"property '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.type_name.startswith("object<")
                    and member.initializer is not None
                ):
                    value = self._coerce_typed_object(
                        member.type_name,
                        value,
                        f"property '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.initializer is not None
                    and self._needs_runtime_type_check(member.type_name)
                ):
                    value = self._coerce_runtime_checked_type(
                        member.type_name,
                        value,
                        f"property '{xclass.name}.{member.name}'",
                    )
                instance.fields[member.name] = value

    def _field_initializer_environment(
        self, xclass: XClass, member: VariableDeclaration
    ) -> Environment:
        field_environment = Environment(xclass.closure)
        field_environment.define("__x_current_class__", xclass)
        member_line = getattr(member, "line", None)
        if member_line is not None:
            self.current_location = (
                getattr(member, "source_name", None),
                member_line,
                getattr(member, "column", None),
            )
        return field_environment

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
            if callee.parent_class.is_exception_base:
                self._initialize_exception_instance(callee.instance, arguments)
                return None
            constructors = callee.parent_class.find_constructors()
            if constructors:
                constructor = self._select_overload(
                    callee.parent_class.name, constructors, arguments
                )
                constructor_function = XFunction(
                    constructor,
                    callee.parent_class.closure,
                    self,
                    callee.instance,
                    callee.parent_class,
                )
                constructor_function = self._apply_function_decorators(
                    constructor.decorators,
                    constructor_function,
                    callee.parent_class.closure,
                )
                constructor_function.call(arguments)
            elif arguments:
                raise RuntimeErrorX(
                    f"Parent class '{callee.parent_class.name}' has no matching constructor"
                )
            return None
        raise RuntimeErrorX("Value is not callable")

    def _thread_join(self, handle: XThreadHandle, arguments: list[Any]) -> Any:
        if len(arguments) > 1:
            raise RuntimeErrorX("ThreadHandle.join accepts at most one timeout")
        timeout = None
        if arguments:
            timeout_value = arguments[0]
            if not isinstance(timeout_value, (int, float)) or isinstance(timeout_value, bool):
                raise RuntimeErrorX("ThreadHandle.join timeout must be a number of seconds")
            if timeout_value < 0:
                raise RuntimeErrorX("ThreadHandle.join timeout cannot be negative")
            timeout = timeout_value
        handle.thread.join(timeout)
        if handle.thread.is_alive():
            return None
        if handle.error is not None:
            # Convert Python exceptions to X language errors to avoid exposing implementation details
            error_message = str(handle.error)
            raise RuntimeErrorX(f"Thread failed: {error_message}", "RuntimeException")
        return handle.result_value

    def _thread_is_alive(self, handle: XThreadHandle, arguments: list[Any]) -> bool:
        if arguments:
            raise RuntimeErrorX("ThreadHandle.isAlive expects no arguments")
        return handle.thread.is_alive()

    def _select_overload(
        self, name: str, functions: list[Any], arguments: list[Any]
    ) -> Any:
        def declaration_for(function: Any) -> FunctionDeclaration:
            if isinstance(function, XFunction):
                return function.declaration
            return function

        matches = [
            function for function in functions
            if self._accepts_argument_count(
                declaration_for(function).parameters, len(arguments)
            )
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
        scored_matches: list[tuple[int, Any]] = []
        for function in matches:
            score = 0
            compatible = True
            declaration = declaration_for(function)
            argument_index = 0
            for parameter in declaration.parameters:
                if parameter.is_rest:
                    while argument_index < len(arguments):
                        parameter_score = self._type_match_score(
                            parameter.type_name, arguments[argument_index]
                        )
                        if parameter_score is None:
                            compatible = False
                            break
                        score += parameter_score
                        argument_index += 1
                    break
                if argument_index >= len(arguments):
                    continue
                parameter_score = self._type_match_score(
                    parameter.type_name, arguments[argument_index]
                )
                if parameter_score is None:
                    compatible = False
                    break
                score += parameter_score
                argument_index += 1
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

    def _accepts_argument_count(self, parameters: list[Any], argument_count: int) -> bool:
        has_rest_parameter = bool(parameters and parameters[-1].is_rest)
        required_count = sum(
            not parameter.is_rest
            and not parameter.has_default
            and not (
                parameter.type_name is not None
                and parameter.type_name.endswith("?")
            )
            for parameter in parameters
        )
        if has_rest_parameter:
            return argument_count >= required_count
        return required_count <= argument_count <= len(parameters)

    def _type_match_score(self, type_name: str | None, value: Any) -> int | None:
        if type_name is None or type_name == "var":
            return 0
        if type_name.endswith("?"):
            if value is None or value is UNDEFINED:
                return 3
            type_name = type_name[:-1]
        if value is UNDEFINED:
            return 1 if type_name in ("undefined", "Object", "object") else None
        if value is None:
            return 1 if type_name in ("null", "Object", "object") else None
        if type_name.startswith("object<"):
            return 3 if self._typed_object_matches(type_name, value) else None
        if type_name.endswith("[]"):
            if not isinstance(value, list):
                return None
            element_type = type_name[:-2]
            for element in value:
                if self._type_match_score(element_type, element) is None:
                    return None
            return 3
        if type_name.casefold() == "function":
            return 3 if self._is_function_value(value) else None
        interface = self._interface_type(type_name)
        if interface is not None:
            return 3 if self._interface_matches(interface, value) else None
        if type_name in ("integer", "int", "byte"):
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

    def _is_function_value(self, value: Any) -> bool:
        return isinstance(value, (XFunction, BuiltinFunction, OverloadedFunction))

    def _interface_type(self, type_name: str) -> XClass | None:
        try:
            value = self._resolve_name(self.globals, type_name)
        except RuntimeErrorX:
            return None
        if isinstance(value, XClass) and value.declaration.is_interface:
            return value
        return None

    def _interface_members(self, interface: XClass) -> list[Any]:
        members = (
            self._interface_members(interface.parent)
            if interface.parent is not None
            and interface.parent.declaration.is_interface
            else []
        )
        members.extend(interface.declaration.members)
        return members

    def _interface_matches(self, interface: XClass, value: Any) -> bool:
        if isinstance(value, dict):
            def get_member(name: str) -> Any:
                return value.get(name, UNDEFINED)

            class_methods: dict[str, list[FunctionDeclaration]] = {}
        elif isinstance(value, XInstance):
            def get_member(name: str) -> Any:
                return value.fields.get(name, UNDEFINED)

            class_methods = {}
            for parent in self._class_hierarchy(value.xclass):
                for member in parent.declaration.members:
                    if (
                        isinstance(member, FunctionDeclaration)
                        and "static" not in member.modifiers
                        and not {"private", "protected"}.intersection(
                            member.modifiers
                        )
                        and member.name != parent.name
                    ):
                        class_methods.setdefault(member.name, []).append(member)
        else:
            return False

        for member in self._interface_members(interface):
            if isinstance(member, FunctionDeclaration):
                if isinstance(value, XInstance):
                    implementations = class_methods.get(member.name, [])
                    if not any(
                        self._function_declaration_matches(actual, member)
                        for actual in implementations
                    ):
                        return False
                    continue
                candidate = get_member(member.name)
                if not self._is_function_value(candidate):
                    return False
                if not self._function_value_matches(candidate, member):
                    return False
            elif isinstance(member, VariableDeclaration):
                if isinstance(value, XInstance):
                    field_definition = self._find_field_owner(
                        value.xclass, member.name
                    )
                    if (
                        field_definition is None
                        or {"private", "protected"}.intersection(
                            field_definition[1].modifiers
                        )
                    ):
                        return False
                candidate = get_member(member.name)
                if candidate is UNDEFINED or self._type_match_score(
                    member.type_name, candidate
                ) is None:
                    return False
        return True

    def _function_value_matches(
        self, value: Any, signature: FunctionDeclaration
    ) -> bool:
        if isinstance(value, XFunction):
            return self._function_declaration_matches(value.declaration, signature)
        if isinstance(value, OverloadedFunction):
            return any(
                self._function_declaration_matches(function.declaration, signature)
                for function in value.functions
            )
        return True

    def _function_declaration_matches(
        self,
        implementation: FunctionDeclaration,
        signature: FunctionDeclaration,
    ) -> bool:
        implementation_parameters = implementation.parameters
        signature_parameters = signature.parameters
        implementation_required = sum(
            not parameter.has_default
            and not parameter.is_rest
            and not (
                parameter.type_name is not None
                and parameter.type_name.endswith("?")
            )
            for parameter in implementation_parameters
        )
        signature_required = sum(
            not parameter.has_default
            and not parameter.is_rest
            and not (
                parameter.type_name is not None
                and parameter.type_name.endswith("?")
            )
            for parameter in signature_parameters
        )
        if (
            implementation_required > signature_required
            or (
                not any(parameter.is_rest for parameter in implementation_parameters)
                and len(implementation_parameters) < len(signature_parameters)
            )
        ):
            return False
        for actual, expected in zip(
            implementation_parameters, signature_parameters
        ):
            if (
                actual.type_name is not None
                and expected.type_name is not None
                and actual.type_name.casefold() != expected.type_name.casefold()
            ):
                return False
        return not (
            implementation.return_type is not None
            and signature.return_type is not None
            and implementation.return_type.casefold()
            != signature.return_type.casefold()
        )

    def _needs_runtime_type_check(self, type_name: str) -> bool:
        return (
            type_name.casefold() == "function"
            or self._interface_type(type_name) is not None
        )

    def _coerce_runtime_checked_type(
        self, type_name: str, value: Any, context: str
    ) -> Any:
        if self._type_match_score(type_name, value) is None:
            raise RuntimeErrorX(
                f"Expected '{type_name}' for {context}, "
                f"got '{self._value_type_name(value)}'",
                "TypeException",
            )
        return value

    def _generic_type_arguments(self, type_name: str) -> list[str]:
        opening = type_name.find("<")
        if opening < 0 or not type_name.endswith(">"):
            return []
        arguments: list[str] = []
        depth = 0
        argument_start = opening + 1
        for index in range(opening + 1, len(type_name) - 1):
            character = type_name[index]
            if character == "<":
                depth += 1
            elif character == ">":
                depth -= 1
            elif character == "," and depth == 0:
                arguments.append(type_name[argument_start:index])
                argument_start = index + 1
        arguments.append(type_name[argument_start:-1])
        return arguments

    def _typed_object_matches(self, type_name: str, value: Any) -> bool:
        type_arguments = self._generic_type_arguments(type_name)
        if len(type_arguments) != 2:
            raise RuntimeErrorX(
                f"Type '{type_name}' must specify object key and value types",
                "TypeException",
            )
        if not isinstance(value, dict):
            return False
        key_type, value_type = type_arguments
        return all(
            self._type_match_score(key_type, key) is not None
            and self._type_match_score(value_type, item) is not None
            for key, item in value.items()
        )

    def _coerce_typed_object(self, type_name: str, value: Any, context: str) -> Any:
        if not type_name.startswith("object<"):
            return value
        type_arguments = self._generic_type_arguments(type_name)
        if len(type_arguments) != 2:
            raise RuntimeErrorX(
                f"Type '{type_name}' must specify object key and value types",
                "TypeException",
            )
        if not isinstance(value, dict):
            raise RuntimeErrorX(
                f"Expected an object for {context} of type '{type_name}'",
                "TypeException",
            )
        key_type, value_type = type_arguments
        if (
            isinstance(value, XObject)
            and value.key_type == key_type
            and value.value_type == value_type
        ):
            return value
        return XObject(
            value,
            key_type,
            value_type,
            lambda expected_type, item, item_context: self._coerce_typed_object_value(
                expected_type, item, f"{context}: {item_context}"
            ),
        )

    def _coerce_typed_object_value(
        self, type_name: str, value: Any, context: str
    ) -> Any:
        if type_name.startswith("object<"):
            return self._coerce_typed_object(type_name, value, context)
        if type_name.endswith("[]"):
            return self._coerce_typed_array(type_name, value, context)
        if self._type_match_score(type_name, value) is None:
            raise RuntimeErrorX(
                f"Expected '{type_name}' for {context}, "
                f"got '{self._value_type_name(value)}'",
                "TypeException",
            )
        return value

    def _coerce_typed_array(
        self, type_name: str, value: Any, context: str
    ) -> Any:
        if not type_name.endswith("[]"):
            return value
        if not isinstance(value, list):
            raise RuntimeErrorX(
                f"Expected an array for {context} of type '{type_name}'",
                "TypeException",
            )

        element_type = type_name[:-2]
        if isinstance(value, XArray) and value.element_type == element_type:
            return value
        checked_values: list[Any] = []
        for index, element in enumerate(value):
            item_context = f"{context} at index {index}"
            if element_type.endswith("[]"):
                checked_value = self._coerce_typed_array(
                    element_type, element, item_context
                )
            elif element_type.startswith("object<"):
                checked_value = self._coerce_typed_object(
                    element_type, element, item_context
                )
            else:
                if self._type_match_score(element_type, element) is None:
                    actual_type = self._value_type_name(element)
                    raise RuntimeErrorX(
                        f"Expected '{element_type}' for {item_context}, "
                        f"got '{actual_type}'",
                        "TypeException",
                    )
                checked_value = element
            checked_values.append(checked_value)

        return XArray(checked_values, element_type, self._validate_array_element)

    def _validate_array_element(self, type_name: str, value: Any) -> Any:
        if type_name.endswith("[]"):
            return self._coerce_typed_array(type_name, value, "array item")
        if type_name.startswith("object<"):
            return self._coerce_typed_object(type_name, value, "array item")
        if self._type_match_score(type_name, value) is None:
            actual_type = self._value_type_name(value)
            raise RuntimeErrorX(
                f"Expected '{type_name}' for array item, got '{actual_type}'",
                "TypeException",
            )
        return value

    def _value_type_name(self, value: Any) -> str:
        if value is UNDEFINED:
            return "undefined"
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, XInstance):
            return value.xclass.name
        return "object"

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
        if value is UNDEFINED:
            return False
        return bool(value)

    def _stringify(self, value: Any) -> str:
        if value is UNDEFINED:
            return "undefined"
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, XCollectionInstance):
            return self._stringify(value._data)
        if isinstance(value, list):
            return "[" + ", ".join(self._stringify(item) for item in value) + "]"
        if isinstance(value, set):
            return "{" + ", ".join(self._stringify(item) for item in sorted(value, key=str)) + "}"
        if isinstance(value, dict):
            fields = ", ".join(
                f"{name}: {self._stringify(item)}"
                for name, item in value.items()
            )
            return "{" + fields + "}"
        if isinstance(value, XInstance):
            return f"[object {value.xclass.name}]"
        if isinstance(value, XClass):
            return f"[class {value.name}]"
        if isinstance(value, XEnumMember):
            return value.name
        if isinstance(value, XExceptionValue):
            return value.message
        return str(value)