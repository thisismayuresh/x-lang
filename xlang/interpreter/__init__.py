"""X language interpreter with module namespace support."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ._common import *  # noqa: F401,F403
from ._native_builtins import DELETE_BUILTIN_NAME
from ._common import MAX_STRING_LENGTH, ComparatorItem, _is_class_method, _EXCEPTION_PARENTS, _ARRAY_METHODS, _STRING_METHODS

from ._math_builtins import MathBuiltins
from ._native_builtins import NativeBuiltins
from ._collection_builtins import CollectionBuiltins


class Interpreter(MathBuiltins, NativeBuiltins, CollectionBuiltins):
    #: Builtin exception hierarchy (child -> parent); defined once in
    #: :mod:`xlang.runtime` so the loader and type checker agree with us.
    EXCEPTION_PARENTS = _EXCEPTION_PARENTS

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
        *,
        validate: bool = True,
        auto_call_main: bool = True,
    ) -> None:
        self.config = config or XConfig()
        self.environment = dict(os.environ)
        if environment is not None:
            self.environment.update(environment)
        self.current_location: tuple[str | None, int | None, int | None] | None = None
        #: End of the span diagnostics should underline (``end_line``,
        #: ``end_column``), kept next to :attr:`current_location`.
        self.current_span: tuple[int | None, int | None] | None = None
        self.warnings: list[SourceWarning] = []
        self._warning_keys: set[tuple[str, str | None, int | None, int | None]] = set()
        self.function_stack: list[XFunction] = []
        self.globals = Environment()
        self._builtin_bindings: dict[str, Any] = {}
        self.output = output
        #: The REPL type-checks each entry against the whole session before
        #: execution, so the per-program gate is skipped when this is False.
        self.validate = validate
        #: Skip the automatic ``main()`` invocation (the REPL runs entries as
        #: they are typed and must never fire a previously defined ``main``).
        self.auto_call_main = auto_call_main
        self._install_builtins(arguments or [])

    def _validate_declarations(self, program: Program) -> None:
        """Pre-execution gate: full type checking including method bodies.

        Raises ``TypeCheckFailure``, which carries every diagnostic so the CLI
        renders each one with its own source snippet — the same way lex and
        parse errors are rendered — instead of concatenating them into a
        single unreadable message.
        """
        from ..typecheck import TypeChecker, TypeCheckFailure

        errors = TypeChecker().check(program, config=self.config)
        if not errors:
            return
        raise TypeCheckFailure(errors)

    def interpret(self, program: Program) -> Any:
        """Run *program*, translating every escaped failure into ``RuntimeErrorX``.

        The wrapper is the last line of defence: users must never observe a
        Python traceback, a ``ReturnSignal``/``LoopSignal`` leaking out of a
        top level statement, or a bare ``RecursionError``.
        """
        try:
            return self._interpret_program(program)
        except ThrownValue:
            raise
        except ReturnSignal as returned:
            return returned.value
        except LoopSignal as loop_signal:
            name = "continue" if loop_signal.is_continue else "break"
            error = RuntimeErrorX(f"'{name}' used outside of a loop")
            self.annotate_error(error)
            raise error from None
        except RecursionError:
            error = RuntimeErrorX(
                "Maximum recursion depth exceeded; the program nests too deeply"
            )
            self.annotate_error(error)
            raise error from None
        except MemoryError:
            error = RuntimeErrorX("Out of memory while running the program")
            self.annotate_error(error)
            raise error from None
        except RuntimeErrorX as error:
            self.annotate_error(error)
            raise
        except Exception as error:
            message = str(error).strip()
            if message:
                wrapped = RuntimeErrorX(
                    f"Unexpected runtime failure: {message}",
                    self._native_exception_name(error),
                )
            else:
                wrapped = RuntimeErrorX(
                    f"Unexpected runtime failure ({type(error).__name__})",
                    self._native_exception_name(error),
                )
            self.annotate_error(wrapped)
            raise wrapped from None

    def _inject_default_imports(self, declarations: list[Any]) -> None:
        """Prepend ``ImportAlias`` nodes for every ``[imports].default`` entry.

        Acts exactly like a top-level ``import System.x`` line, so projects
        that rely on the same set of standard-library namespaces no longer
        repeat the import in every file.
        """
        from ..ast_nodes import ImportAlias, ImportNamespaceAlias

        bound_aliases = set()
        for declaration in declarations:
            if isinstance(declaration, ImportAlias):
                bound_aliases.add(declaration.alias_name)
            elif isinstance(declaration, ImportNamespaceAlias):
                bound_aliases.add(declaration.alias_name)
        injected: list[Any] = []
        for module_path in self.config.default_imports:
            alias = module_path.split(".")[-1]
            if alias in bound_aliases:
                continue
            injected.append(ImportAlias(module_path, alias))
            bound_aliases.add(alias)
        declarations[:0] = injected

    def _resolve_import_call_target(self, source_name: str, alias: str | None) -> Any:
        """Resolve the callee of ``import B.greet("Maya")``.

        The loader flattens the imported module's declarations, so the target
        is normally already bound under its (aliased) local name; the dotted
        import path is the fallback when flattening bound nothing.
        """
        local_name = alias or source_name.split(".")[-1]
        try:
            callee = self._lookup(self.globals, local_name)
        except RuntimeErrorX:
            callee = None
        if callee is None:
            try:
                callee = self._resolve_import(source_name)
            except RuntimeErrorX as error:
                # The dotted path is the fallback when nothing bound the
                # target (most often an import entered without its module,
                # such as in the REPL), so say which import failed.
                raise RuntimeErrorX(
                    f"Cannot call '{source_name}': {error.message}",
                    error.exception_name,
                ) from None
        if isinstance(callee, list) and callee and all(
            isinstance(function, XFunction) for function in callee
        ):
            callee = OverloadedFunction(local_name, callee)
        return callee

    def _interpret_program(self, program: Program) -> Any:
        if self.validate and self.config.enabled("type_checker"):
            self._validate_declarations(program)
        declarations = [declaration for declaration in program.declarations if declaration]
        self._inject_default_imports(declarations)
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
        ) or any(
            # `import B.greet("Maya")` runs code at the top level, so it counts
            # as a top-level statement just like a bare `greet("Maya");`.
            isinstance(declaration, ImportDeclaration)
            and declaration.statement is not None
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
                # short-name) allow the import to silently re-bind it.  One
                # exception: importing an exception namespace
                # (System.Throwable.Exception.IOException) over its own builtin
                # constructor keeps the constructor, so `throw IOException(...)`
                # still works after the import — the namespace stays reachable
                # through the full System... path, or via an alias.
                if alias in self.globals.values:
                    existing_value = self.globals.values[alias]
                    if isinstance(existing_value, (BuiltinFunction, XClass)) and (
                        isinstance(imported_value, (Environment, dict))
                    ):
                        pass
                    else:
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
                ),
            ):
                continue
            elif isinstance(declaration, ImportDeclaration):
                # `import B.greet("Maya")` is an import plus an immediate call,
                # so it runs here, in statement order, after the import has
                # been bound by the loader.
                if declaration.statement is not None:
                    self._execute(declaration.statement, self.globals)
                continue
            else:
                self._execute(declaration, self.globals)

        if has_top_level_statements or not self.auto_call_main:
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
        # delete(...) is the top-level spelling of Object.delete(...) — the
        # Python-side declaration of its origin lives next to DELETE_BUILTIN_NAME.
        self.globals.define(
            "delete", BuiltinFunction(DELETE_BUILTIN_NAME, self._delete_indirect)
        )
        if self.config.enabled("async"):
            self.globals.define("sleep", BuiltinFunction("sleep", self._builtin_sleep))
        if self.config.enabled("command_input"):
            self.globals.define("input", BuiltinFunction("input", self._builtin_input))
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
            "HttpException",
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
        io_namespace.define("Console", self._console_members())
        if self.config.enabled("network"):
            network_namespace = Environment(io_namespace)
            http_namespace = Environment(network_namespace)
            http_namespace.define(
                "fetch", BuiltinFunction("http.fetch", self._http_fetch)
            )
            network_namespace.define("http", http_namespace)
            io_namespace.define("Network", network_namespace)
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
            from ..stdlib.extended_collections import build_namespaces

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
        if self.config.enabled("math_library"):
            utils_namespace.define("Math", self._math_members())
        utils_namespace.define("JSON", self._json_members())
        system_namespace.define("utils", utils_namespace)
        if self.config.enabled("exceptions"):
            # System.Throwable.Exception.IOException.HttpException mirrors the
            # exception hierarchy so any node can be imported or named inline
            # in a catch clause.
            system_namespace.define("Throwable", self._exception_namespace("Throwable"))
        # System.process holds everything that talks to the host process:
        # environment variables and process termination.
        process_namespace = Environment(system_namespace)
        environment_namespace = Environment()
        for name, value in self.environment.items():
            environment_namespace.values[name] = value
        environment_namespace.define(
            "has", BuiltinFunction("process.Environment.has", self._environment_has)
        )
        environment_namespace.define(
            "all", BuiltinFunction("process.Environment.all", self._environment_all)
        )
        process_namespace.define("Environment", environment_namespace)
        process_namespace.define(
            "exit", BuiltinFunction("process.exit", self._process_exit)
        )
        system_namespace.define("process", process_namespace)
        self.globals.define("System", system_namespace)
        self._builtin_bindings = dict(self.globals.values)

    def _is_builtin_binding(self, environment: Environment, name: str) -> bool:
        """True when *name* in *environment* still holds its startup builtin."""
        return (
            environment is self.globals
            and name in self._builtin_bindings
            and environment.values.get(name) is self._builtin_bindings[name]
        )

    def _define_shadowing(
        self, environment: Environment, name: str, value: Any, **options: Any
    ) -> None:
        """Declare *name*, letting a program shadow an installed builtin.

        Short collection names such as ``Queue`` and ``Stack`` are preloaded
        into globals, so a program declaring its own ``class Queue`` replaces
        that builtin instead of failing with "already declared in this scope".
        A second user declaration of the same name still errors.
        """
        if self._is_builtin_binding(environment, name):
            environment.values[name] = value
            return
        environment.define(name, value, **options)

    def _environment_has(self, arguments: list[Any]) -> bool:
        if len(arguments) != 1 or not isinstance(arguments[0], str):
            raise RuntimeErrorX("Environment.has expects one string key")
        return arguments[0] in self.environment

    def _environment_all(self, arguments: list[Any]) -> dict[str, str]:
        if arguments:
            raise RuntimeErrorX("Environment.all expects no arguments")
        return dict(self.environment)

    def _process_exit(self, arguments: list[Any]) -> Any:
        """``System.process.exit([code])`` stops the interpreter immediately."""
        if len(arguments) > 1:
            raise RuntimeErrorX("System.process.exit expects 0 or 1 argument")
        if not arguments:
            raise SystemExit(0)
        code = arguments[0]
        if isinstance(code, bool):
            raise RuntimeErrorX("System.process.exit expects an integer exit code")
        if isinstance(code, int):
            raise SystemExit(code)
        if isinstance(code, float) and code.is_integer():
            raise SystemExit(int(code))
        raise RuntimeErrorX("System.process.exit expects an integer exit code")

    def _builtin_input(self, arguments: list[Any]) -> Any:
        if len(arguments) > 2:
            raise RuntimeErrorX("input expects at most two arguments (prompt, expected_type)")
        if len(arguments) >= 1:
            prompt = str(arguments[0])
            try:
                sys.stdout.write(prompt)
                sys.stdout.flush()
            except (OSError, ValueError) as error:
                raise RuntimeErrorX(
                    f"Cannot write input prompt: {error}", "IOException"
                ) from None
        stream = sys.stdin
        if stream is None:
            return ""
        try:
            line = stream.readline()
        except (EOFError, OSError, ValueError):
            return ""
        value = line.rstrip("\n")
        
        # If enhanced_input is enabled and a type is specified, validate
        if self.config.enabled("enhanced_input") and len(arguments) == 2:
            expected_type = arguments[1]
            if isinstance(expected_type, str):
                expected_type = expected_type.lower()
                if expected_type in ("int", "integer"):
                    try:
                        return int(value)
                    except ValueError:
                        raise RuntimeErrorX(f"Expected integer input, got '{value}'")
                elif expected_type in ("float", "number"):
                    try:
                        return float(value)
                    except ValueError:
                        raise RuntimeErrorX(f"Expected numeric input, got '{value}'")
                elif expected_type in ("bool", "boolean"):
                    if value.lower() in ("true", "1", "yes", "y"):
                        return True
                    elif value.lower() in ("false", "0", "no", "n"):
                        return False
                    else:
                        raise RuntimeErrorX(f"Expected boolean input (true/false), got '{value}'")
                elif expected_type in ("str", "string"):
                    return value
                else:
                    raise RuntimeErrorX(f"Unsupported input type: {expected_type}")
        return value


    def _create_wrapper_class(self, name: str, python_class: type) -> XClass:
        """Create an X class that wraps a Python class"""
        from ..ast_nodes import ClassDeclaration, FunctionDeclaration, VariableDeclaration, Block
        
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

    def _set_location(self, node: Any) -> None:
        """Point the next diagnostic at *node*'s span.

        Called before the operations that can fail (indexing, member access,
        arithmetic, calls) so a runtime error underlines the offending
        expression with ``^^^`` instead of the statement keyword.
        """
        line = getattr(node, "line", None)
        if line is None:
            return
        self.current_location = (
            getattr(node, "source_name", None),
            line,
            getattr(node, "column", None),
        )
        end_line = getattr(node, "end_line", None)
        end_column = getattr(node, "end_column", None)
        self.current_span = (end_line, end_column) if end_column is not None else None

    def annotate_error(self, error: RuntimeErrorX | ThrownValue) -> None:
        if self.current_location is None or error.line is not None:
            return
        source_name, line, column = self.current_location
        error.source_name = source_name
        error.line = line
        error.column = column
        if self.current_span is not None and getattr(error, "end_column", None) is None:
            error.end_line, error.end_column = self.current_span

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


    def _builtin_print(self, arguments: list[Any]) -> None:
        self.output(" ".join(self._stringify(value) for value in arguments))
        return None

    def _builtin_type_of(self, arguments: list[Any]) -> str:
        """Report the X-level type name of the single argument.

        Mapping:

        - ``boolean`` for booleans, ``number`` for integers/floats,
          ``string`` for strings
        - ``method`` for methods declared inside a class body (instance or
          static, single or overloaded)
        - ``function`` for top-level functions, builtins, and class objects
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
        if isinstance(value, XFunction):
            return "method" if _is_class_method(value) else "function"
        if isinstance(value, OverloadedFunction):
            if value.functions and all(
                _is_class_method(function) for function in value.functions
            ):
                return "method"
            return "function"
        if isinstance(value, BuiltinFunction):
            return "function"
        if isinstance(value, XClass):
            if value.declaration.is_interface:
                return "interface"
            return "class"
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
                        f"{member_noun(member.modifiers)} '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.type_name.startswith("object<")
                    and member.initializer is not None
                ):
                    value = self._coerce_typed_object(
                        member.type_name,
                        value,
                        f"{member_noun(member.modifiers)} '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.initializer is not None
                    and self._needs_runtime_type_check(member.type_name)
                ):
                    value = self._coerce_runtime_checked_type(
                        member.type_name,
                        value,
                        f"{member_noun(member.modifiers)} '{xclass.name}.{member.name}'",
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
        self._set_location(declaration)

    def _execute(self, statement: Any, environment: Environment) -> None:
        if getattr(statement, "line", None) is not None:
            self._set_location(statement)
        if isinstance(statement, Block):
            self._execute_block(statement.statements, Environment(environment))
        elif isinstance(statement, FunctionDeclaration):
            self._define_function(statement, environment)
        elif isinstance(statement, VariableDeclaration):
            self._define_variable(statement, environment)
        elif isinstance(statement, EnumDeclaration):
            self._define_enum(statement, environment)
        elif isinstance(statement, ExpressionStatement):
            value = self._evaluate(statement.expression, environment)
            if isinstance(value, FetchCall):
                raise RuntimeErrorX(
                    "The fetch() result was discarded — did you forget "
                    "'await' before fetch(...)?"
                )
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
        elif isinstance(statement, SwitchStatement):
            self._execute_switch(statement, environment)
        else:
            raise RuntimeErrorX(f"Unsupported statement '{type(statement).__name__}'")

    def _execute_block(self, statements: list[Any], environment: Environment) -> None:
        for statement in statements:
            self._execute(statement, environment)

    def _define_variable(
        self, statement: VariableDeclaration, environment: Environment
    ) -> None:
        """Bind one ``let``/``const`` declaration, coercing typed initializers."""
        value = (
            None
            if statement.initializer is None
            else self._evaluate(statement.initializer, environment)
        )
        if statement.pattern is not None:
            self._bind_destructuring(
                statement.pattern, value, environment, statement.constant
            )
            return
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
        if isinstance(iterable, XCollectionInstance) and isinstance(iterable._data, set):
            # Sets store wrapped members internally; iterate the raw values.
            iterable = self._set_values(iterable._data)
        elif isinstance(iterable, set):
            iterable = self._set_values(iterable)
        if statement.iteration_mode == "in":
            # Unwrap XCollectionInstance so we can iterate its raw _data
            if isinstance(iterable, XCollectionInstance):
                iterable = iterable._data
            if isinstance(iterable, dict):
                # Snapshot the keys: `delete(obj[key])` inside the loop must
                # not raise "dictionary changed size during iteration".
                iterator = iter(list(iterable.keys()))
            elif isinstance(iterable, XInstance):
                iterator = iter(list(iterable.fields.keys()))
            else:
                try:
                    iterator = iter(iterable)
                except TypeError as error:
                    raise RuntimeErrorX(
                        "for-in requires an object or iterable value"
                    )
        else:
            # Unwrap XCollectionInstance — PriorityQueue uses a dict with 'heap'
            if isinstance(iterable, XCollectionInstance):
                inner = iterable._data
                iterable = inner["heap"] if isinstance(inner, dict) and "heap" in inner else inner
            try:
                iterator = iter(iterable)
            except TypeError:
                raise RuntimeErrorX(
                    "Value in for loop is not iterable", "TypeException"
                ) from None
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
                self._execute_block(
                    statement.body.statements, Environment(loop_environment)
                )
            except LoopSignal as loop_signal:
                should_break = not loop_signal.is_continue
            if should_break:
                break
            if statement.increment is not None:
                self._evaluate(statement.increment, loop_environment)

    def _execute_try(self, statement: TryStatement, environment: Environment) -> None:
        body_environment = Environment(environment)
        resources = self._bind_resources(
            statement.resources, environment, body_environment
        )
        body_failed = False
        pending_error: BaseException | None = None
        try:
            try:
                self._execute_block(statement.body.statements, body_environment)
            except BaseException:
                body_failed = True
                raise
            finally:
                self._close_resources(resources, environment, body_failed)
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

    def _bind_resources(
        self,
        bindings: list[Any],
        environment: Environment,
        body_environment: Environment,
    ) -> list[tuple[str, Any]]:
        """Evaluate ``try (let r = ...)`` bindings into the try block scope."""
        resources: list[tuple[str, Any]] = []
        for binding in bindings:
            self._define_variable(
                VariableDeclaration(
                    binding.name, binding.type_name, binding.value, binding.constant
                ),
                body_environment,
            )
            resources.append((binding.name, body_environment.values[binding.name]))
        return resources

    def _close_resources(
        self,
        resources: list[tuple[str, Any]],
        environment: Environment,
        suppress_errors: bool,
    ) -> None:
        """Call ``close()`` on each resource, deepest last-in-first-out.

        When the try block already failed, a broken ``close()`` must not mask
        the original error, so those failures are swallowed.
        """
        for name, value in reversed(resources):
            if value is None:
                continue
            try:
                closer = self._get_member(
                    value, "close", self._access_context(environment)
                )
            except RuntimeErrorX as error:
                if suppress_errors:
                    continue
                raise RuntimeErrorX(
                    f"Resource '{name}' has no close() method: {error.message}"
                ) from None
            try:
                self._call(closer, [])
            except BaseException:
                if suppress_errors:
                    continue
                raise

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
                getattr(source_error, "end_line", None)
                or getattr(value.cause, "end_line", None),
                getattr(source_error, "end_column", None)
                or getattr(value.cause, "end_column", None),
            )
        raise ThrownValue(
            value,
            getattr(source_error, "source_name", None),
            getattr(source_error, "line", None),
            getattr(source_error, "column", None),
            getattr(source_error, "end_line", None),
            getattr(source_error, "end_column", None),
        )

    def _exception_matches(self, value: Any, type_name: str | None) -> bool:
        if type_name is None:
            return True
        # Catch types may be written inline with their full hierarchy path
        # (System.Throwable.Exception.IOException.HttpException); the thrown
        # value always carries the short name, so compare leaf names.
        requested_types = [
            requested.split(".")[-1].strip()
            for requested in type_name.split("|")
            if requested.split(".")[-1].strip()
        ]
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

    def _execute_switch(self, statement: SwitchStatement, environment: Environment) -> None:
        switch_value = self._evaluate(statement.expression, environment)
        matched = False
        for case in statement.cases:
            if matched:
                # Fall through - execute all subsequent cases
                self._execute_block(case.body.statements, environment)
            elif case.value is None:
                # Default case
                matched = True
                self._execute_block(case.body.statements, environment)
            else:
                case_value = self._evaluate(case.value, environment)
                if self._values_equal(switch_value, case_value):
                    matched = True
                    self._execute_block(case.body.statements, environment)

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Check equality for switch case matching."""
        if type(a) != type(b):
            return False
        if isinstance(a, (int, float, str, bool)) or a is None:
            return a == b
        if isinstance(a, list):
            if len(a) != len(b):
                return False
            return all(self._values_equal(x, y) for x, y in zip(a, b))
        if isinstance(a, dict):
            if set(a.keys()) != set(b.keys()):
                return False
            return all(self._values_equal(a[k], b[k]) for k in a.keys())
        return a == b

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
            self._set_location(expression)
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
            self._set_location(expression)
            return self._assign(expression.target, expression.operator, value, environment)
        if isinstance(expression, ImportCall):
            # `import B.greet("Maya")` — the loader already bound the import;
            # this only performs the call the import statement carries.
            self._set_location(expression)
            callee = self._resolve_import_call_target(
                expression.import_path, expression.alias
            )
            arguments = self._evaluate_call_arguments(expression.arguments, environment)
            self._set_location(expression)
            return self._call(callee, arguments)
        if isinstance(expression, Call):
            # delete(target) must see the key expression itself, so it runs
            # before arguments are evaluated (reading the value first would
            # raise on an already-missing key and lose the container).
            if self._resolve_delete_callee(expression.callee, environment) is not None:
                self._set_location(expression)
                return self._delete_builtin_call(expression.arguments, environment)
            callee = self._evaluate(expression.callee, environment)
            arguments = self._evaluate_call_arguments(expression.arguments, environment)
            self._set_location(expression)
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
            self._set_location(expression)
            return self._get_member(object_value, expression.name, access_context)
        if isinstance(expression, Index):
            object_value = self._evaluate(expression.object, environment)
            index = self._evaluate(expression.index, environment)
            self._set_location(expression)
            return self._read_indexed_value(object_value, index)
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
                if segment.optional and self._index_is_absent(value, index):
                    return UNDEFINED
                value = self._read_indexed_value(value, index)
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
        self._set_location(expression)
        if expression.operator in ("++", "--"):
            current = self._read_target(expression.operand, environment)
            delta = 1 if expression.operator == "++" else -1
            try:
                updated = current + delta
            except (TypeError, ValueError, OverflowError):
                raise RuntimeErrorX(
                    f"Invalid operands for '{expression.operator}'", "TypeException"
                ) from None
            self._write_target(expression.operand, updated, environment)
            return current if expression.postfix else updated
        operand = self._evaluate(expression.operand, environment)
        self._set_location(expression)
        if expression.operator == "!":
            return not self._is_truthy(operand)
        try:
            if expression.operator == "-":
                return -operand
            if expression.operator == "+":
                return +operand
        except (TypeError, ValueError, OverflowError):
            raise RuntimeErrorX(
                f"Invalid operand for '{expression.operator}'", "TypeException"
            ) from None
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
        self._set_location(expression)
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
                target = right
                if isinstance(target, XCollectionInstance) and isinstance(
                    target._data, set
                ):
                    target = target._data
                if isinstance(target, set):
                    return self._set_contains(target, left)
                return left in right
        except RuntimeErrorX:
            raise
        except ZeroDivisionError:
            raise RuntimeErrorX(
                f"Division by zero for '{operator}'", "ArithmeticException"
            ) from None
        except OverflowError:
            raise RuntimeErrorX(
                f"Result of '{operator}' is too large to represent",
                "ArithmeticException",
            ) from None
        except (TypeError, ValueError):
            raise RuntimeErrorX(
                f"Invalid operands for '{operator}'", "TypeException"
            ) from None
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
        except RuntimeErrorX:
            raise
        except ZeroDivisionError:
            raise RuntimeErrorX(
                f"Division by zero for '{operator}'", "ArithmeticException"
            ) from None
        except OverflowError:
            raise RuntimeErrorX(
                f"Result of '{operator}=' is too large to represent",
                "ArithmeticException",
            ) from None
        except (TypeError, ValueError):
            raise RuntimeErrorX(
                f"Invalid operands for '{operator}='", "TypeException"
            ) from None
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
            return self._read_indexed_value(
                self._evaluate(target.object, environment),
                self._evaluate(target.index, environment),
            )
        raise RuntimeErrorX("Invalid assignment target")

    def _index_is_absent(self, container: Any, index: Any) -> bool:
        """Whether ``container[index]`` is a well-typed miss.

        Only genuine misses (out of range or absent object key) count, so an
        optional chain cannot swallow an ill-typed index or a value that does
        not support indexing at all.
        """
        if isinstance(container, (list, tuple, str)) and isinstance(
            index, int
        ) and not isinstance(index, bool):
            return not (-len(container) <= index < len(container))
        if isinstance(container, dict) and isinstance(index, (int, str)) and not isinstance(
            index, bool
        ):
            return index not in container
        return False

    def _read_indexed_value(self, container: Any, index: Any) -> Any:
        if isinstance(container, str):
            if isinstance(index, bool) or not isinstance(index, int):
                raise RuntimeErrorX(
                    f"Cannot access index {self._stringify(index)}: "
                    "index must be an integer",
                    "IndexOutOfBoundsException",
                )
            if not (-len(container) <= index < len(container)):
                raise RuntimeErrorX(
                    f"Cannot access index {index}: out of range for string "
                    f"of length {len(container)}",
                    "IndexOutOfBoundsException",
                )
            return container[index]
        if isinstance(container, (list, tuple)):
            if isinstance(index, bool) or not isinstance(index, int):
                raise RuntimeErrorX(
                    f"Cannot access index {self._stringify(index)}: "
                    "index must be an integer",
                    "IndexOutOfBoundsException",
                )
            if not (-len(container) <= index < len(container)):
                raise RuntimeErrorX(
                    f"Cannot access index {index}: out of range for array "
                    f"of length {len(container)}",
                    "IndexOutOfBoundsException",
                )
            return container[index]
        if isinstance(container, dict):
            if isinstance(index, bool) or not isinstance(index, (int, str)):
                raise RuntimeErrorX(
                    f"Cannot access key {self._stringify(index)}: "
                    "object keys must be strings",
                    "IndexOutOfBoundsException",
                )
            if index not in container:
                raise RuntimeErrorX(
                    f"Cannot access key {self._stringify(index)}: "
                    "object has no such key",
                    "IndexOutOfBoundsException",
                )
            return container[index]
        raise RuntimeErrorX(
            f"Cannot access index {self._stringify(index)}: "
            f"{self._value_type_name(container)} values are not indexable",
            "IndexOutOfBoundsException",
        )

    def _write_indexed_value(self, container: Any, index: Any, value: Any) -> None:
        if isinstance(container, str):
            raise RuntimeErrorX(
                f"Cannot assign to index {self._stringify(index)}: "
                "strings are immutable",
                "TypeException",
            )
        if isinstance(container, tuple):
            raise RuntimeErrorX(
                f"Cannot assign to index {self._stringify(index)}: "
                "tuples do not support index assignment",
                "TypeException",
            )
        if isinstance(container, list):
            if isinstance(index, bool) or not isinstance(index, int):
                raise RuntimeErrorX(
                    f"Cannot assign to index {self._stringify(index)}: "
                    "index must be an integer",
                    "IndexOutOfBoundsException",
                )
            if not (-len(container) <= index < len(container)):
                raise RuntimeErrorX(
                    f"Cannot assign to index {index}: out of range for array "
                    f"of length {len(container)}",
                    "IndexOutOfBoundsException",
                )
            container[index] = value
            return
        if isinstance(container, dict):
            if isinstance(index, bool) or not isinstance(index, (int, str)):
                raise RuntimeErrorX(
                    f"Cannot assign to key {self._stringify(index)}: "
                    "object keys must be strings",
                    "IndexOutOfBoundsException",
                )
            container[index] = value
            return
        raise RuntimeErrorX(
            f"Cannot assign to index {self._stringify(index)}: "
            f"{self._value_type_name(container)} values do not support "
            "index assignment",
            "TypeException",
        )

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
            self._guard_const_container(target, environment, "member")
            object_value = self._evaluate(target.object, environment)
            access_context = self._access_context(environment)
            self._set_member(object_value, target.name, value, access_context)
            return
        if isinstance(target, Index):
            self._guard_const_container(target, environment, "element")
            self._write_indexed_value(
                self._evaluate(target.object, environment),
                self._evaluate(target.index, environment),
                value,
            )
            return
        raise RuntimeErrorX("Invalid assignment target")

    @staticmethod
    def _assignment_root_name(target: Any) -> str | None:
        """Return the variable an assignment target ultimately writes into.

        ``matrix[0][1]`` and ``settings.port`` both trace back to a single
        binding; calls and ``this`` do not trace to a name at all.
        """
        while isinstance(target, (Member, Index)):
            target = target.object
        if isinstance(target, Identifier):
            return target.name
        return None

    def _guard_const_container(
        self, target: Any, environment: Environment, noun: str
    ) -> None:
        """Reject writes through a ``const`` binding (deep immutability)."""
        root = self._assignment_root_name(target)
        if root is not None and environment.is_constant(root):
            raise RuntimeErrorX(f"Cannot modify {noun} of constant '{root}'")

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
                raise RuntimeErrorX(
                    f"Cannot access {member_noun(field_declaration.modifiers)} "
                    f"'{field_owner.name}.{name}'"
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
        # An unawaited fetch()/readTextAsync() coroutine: explain the real
        # problem instead of "Value has no member".
        if inspect.iscoroutine(object_value) or isinstance(object_value, FetchCall):
            raise RuntimeErrorX(
                f"Cannot read '{name}' from an asynchronous result — "
                f"did you forget 'await'?"
            )
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
                        raise RuntimeErrorX(
                            f"Cannot access {member_noun(field_declaration.modifiers)} "
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
            value = self._lookup(object_value, name)
            if isinstance(value, list) and value and all(
                isinstance(function, XFunction) for function in value
            ):
                return OverloadedFunction(name, value)
            return value
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
                lambda arguments: self._number_to_string(object_value, arguments),
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
                    raise RuntimeErrorX(
                        f"Cannot access {member_noun(field_declaration.modifiers)} "
                        f"'{field_owner.name}.{name}'"
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
                    raise RuntimeErrorX(
                        f"Cannot modify {member_noun(field_declaration.modifiers)} "
                        f"'{object_value.xclass.name}.{name}'"
                    )
                if "final" in field_declaration.modifiers and not (
                    self._inside_defining_constructor(field_owner)
                ):
                    self._set_declaration_location(field_declaration)
                    final_error = RuntimeErrorX(
                        f"Cannot assign to final "
                        f"{member_noun(field_declaration.modifiers)} "
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
                        f"{member_noun(field_declaration.modifiers)} '{field_owner.name}.{name}'",
                    )
                if (
                    field_declaration.type_name is not None
                    and field_declaration.type_name.startswith("object<")
                ):
                    value = self._coerce_typed_object(
                        field_declaration.type_name,
                        value,
                        f"{member_noun(field_declaration.modifiers)} '{field_owner.name}.{name}'",
                    )
                if (
                    field_declaration.type_name is not None
                    and self._needs_runtime_type_check(field_declaration.type_name)
                ):
                    value = self._coerce_runtime_checked_type(
                        field_declaration.type_name,
                        value,
                        f"{member_noun(field_declaration.modifiers)} '{field_owner.name}.{name}'",
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
                raise RuntimeErrorX(
                    f"Cannot modify {member_noun(field_declaration.modifiers)} "
                    f"'{field_owner.name}.{name}'"
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
                    f"{member_noun(field_declaration.modifiers)} '{field_owner.name}.{name}'",
                )
            if (
                field_declaration.type_name is not None
                and field_declaration.type_name.startswith("object<")
            ):
                value = self._coerce_typed_object(
                    field_declaration.type_name,
                    value,
                    f"{member_noun(field_declaration.modifiers)} '{field_owner.name}.{name}'",
                )
            if (
                field_declaration.type_name is not None
                and self._needs_runtime_type_check(field_declaration.type_name)
            ):
                value = self._coerce_runtime_checked_type(
                    field_declaration.type_name,
                    value,
                    f"{member_noun(field_declaration.modifiers)} '{field_owner.name}.{name}'",
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
                        f"{member_noun(member.modifiers)} '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.type_name.startswith("object<")
                    and member.initializer is not None
                ):
                    value = self._coerce_typed_object(
                        member.type_name,
                        value,
                        f"{member_noun(member.modifiers)} '{xclass.name}.{member.name}'",
                    )
                if (
                    member.type_name is not None
                    and member.initializer is not None
                    and self._needs_runtime_type_check(member.type_name)
                ):
                    value = self._coerce_runtime_checked_type(
                        member.type_name,
                        value,
                        f"{member_noun(member.modifiers)} '{xclass.name}.{member.name}'",
                    )
                instance.fields[member.name] = value

    def _field_initializer_environment(
        self, xclass: XClass, member: VariableDeclaration
    ) -> Environment:
        field_environment = Environment(xclass.closure)
        field_environment.define("__x_current_class__", xclass)
        if getattr(member, "line", None) is not None:
            self._set_location(member)
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
        if type_name.casefold() == "any":
            return 1
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

    def _number_to_string(self, value: int | float | bool, arguments: list[Any]) -> str:
        """``value.toString()`` or ``value.toString(base)`` with base 2..36."""
        if len(arguments) > 1:
            raise RuntimeErrorX("toString accepts at most one argument")
        if not arguments:
            return self._stringify(value)
        base = arguments[0]
        if isinstance(base, bool) or not isinstance(base, int):
            raise RuntimeErrorX("toString base must be an integer", "TypeException")
        if base < 2 or base > 36:
            raise RuntimeErrorX(
                "toString base must be between 2 and 36", "RangeException"
            )
        if isinstance(value, bool):
            number = int(value)
        elif isinstance(value, float):
            if not value.is_integer():
                raise RuntimeErrorX(
                    "toString with a base requires an integer value", "TypeException"
                )
            number = int(value)
        else:
            number = value
        sign = "-" if number < 0 else ""
        number = abs(number)
        if number == 0:
            return "0"
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        digits: list[str] = []
        while number:
            digits.append(alphabet[number % base])
            number //= base
        return sign + "".join(reversed(digits))

    def _is_truthy(self, value: Any) -> bool:
        if value is UNDEFINED:
            return False
        return bool(value)

    def _stringify(self, value: Any) -> str:
        return self._stringify_within(value, set())

    def _stringify_within(self, value: Any, seen: set[int]) -> str:
        if value is UNDEFINED:
            return "undefined"
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, XCollectionInstance):
            return self._stringify_within(value._data, seen)
        if isinstance(value, (list, set, dict)):
            identity = id(value)
            if identity in seen:
                return "[Circular]"
            seen.add(identity)
            try:
                if isinstance(value, list):
                    return (
                        "["
                        + ", ".join(
                            self._stringify_within(item, seen) for item in value
                        )
                        + "]"
                    )
                if isinstance(value, set):
                    return (
                        "{"
                        + ", ".join(
                            self._stringify_within(item, seen)
                            for item in sorted(self._set_values(value), key=str)
                        )
                        + "}"
                    )
                fields = ", ".join(
                    f"{name}: {self._stringify_within(item, seen)}"
                    for name, item in value.items()
                )
                return "{" + fields + "}"
            finally:
                seen.discard(identity)
        if isinstance(value, XInstance):
            return f"[object {value.xclass.name}]"
        if isinstance(value, XClass):
            return f"[class {value.name}]"
        if isinstance(value, XEnumMember):
            return value.name
        if isinstance(value, XExceptionValue):
            return value.message
        return str(value)