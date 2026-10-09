"""X language interpreter: cohesive builtin-family mixins split from the core Interpreter."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ._common import *  # noqa: F401,F403
from ._common import MAX_STRING_LENGTH, ComparatorItem, _is_class_method, _ARRAY_METHODS, _STRING_METHODS


#: Declared origin of the top-level ``delete(...)`` builtin.  ``delete`` is the
#: unqualified spelling of ``Object.delete(...)`` in the ``Object`` namespace —
#: the same arrangement ``print`` has with the console builtins — so the
#: qualified name below is the single Python-side statement of where the
#: builtin comes from: it is used for the ``BuiltinFunction`` label, the
#: object-namespace entry, editor hover text and the README.
DELETE_BUILTIN_NAME = "Object.delete"


class NativeBuiltins:
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
        object_namespace.define(
            "delete", BuiltinFunction(DELETE_BUILTIN_NAME, self._delete_indirect)
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

    # ------------------------------------------------------------------
    # delete(target) — remove an object key, an array element, or a field
    # ------------------------------------------------------------------

    def _delete_indirect(self, arguments: list[Any]) -> Any:
        """Called only when ``delete`` is not written as ``delete(target)``.

        ``delete`` has to see the *key expression* (``delete(user.name)`` or
        ``delete(values[0])``) so it can remove the entry itself; evaluating
        the argument first would read the value and lose the container.  The
        interpreter therefore routes ``delete(...)``/``Object.delete(...)``
        through :meth:`_delete_builtin_call` before arguments are evaluated,
        which leaves this implementation for round-uses such as
        ``let f = Object.delete;``.
        """
        raise RuntimeErrorX(
            f"{DELETE_BUILTIN_NAME} must be called as delete(target) or "
            "Object.delete(target), for example delete(user.name) or "
            "delete(values[0])",
            "IllegalArgumentException",
        )

    def _delete_builtin_call(
        self, argument_nodes: list[Any], environment: Environment
    ) -> bool:
        """Evaluate ``delete(target)``; returns ``true`` when it removed it.

        Delete is strict, exactly like reading: a key, index or field that is
        not there raises the same error its read would raise, so deleting
        twice (``delete(o.p); delete(o.p);``) is reported instead of silently
        doing nothing.
        """
        if len(argument_nodes) != 1:
            raise RuntimeErrorX(
                f"delete expects exactly one argument, got {len(argument_nodes)}",
                "IllegalArgumentException",
            )
        target = argument_nodes[0]
        if isinstance(target, Member):
            container = self._evaluate(target.object, environment)
            self._set_location(target)
            return self._delete_member(container, target.name, environment)
        if isinstance(target, Index):
            container = self._evaluate(target.object, environment)
            key = self._evaluate(target.index, environment)
            self._set_location(target)
            return self._delete_index(container, key)
        self._set_location(target)
        raise RuntimeErrorX(
            "delete expects an object key or array index, for example "
            "delete(user.name) or delete(values[0])",
            "IllegalArgumentException",
        )

    def _resolve_delete_callee(
        self, callee: Any, environment: Environment
    ) -> BuiltinFunction | None:
        """Return the ``delete`` builtin when *callee* is a delete call.

        The identity check keeps a user-defined ``delete`` function (or an
        unrelated ``something.delete(...)`` method) working exactly as written:
        only calls that resolve to the builtin declared as
        ``DELETE_BUILTIN_NAME`` take the special path.
        """
        if isinstance(callee, Identifier) and callee.name == "delete":
            try:
                value = environment.get("delete")
            except RuntimeErrorX:
                return None
            if isinstance(value, BuiltinFunction) and value.name == DELETE_BUILTIN_NAME:
                return value
            return None
        if (
            isinstance(callee, Member)
            and callee.name == "delete"
            and isinstance(callee.object, Identifier)
            and callee.object.name == "Object"
        ):
            try:
                object_namespace = environment.get("Object")
            except RuntimeErrorX:
                return None
            if not isinstance(object_namespace, Environment):
                return None
            value = object_namespace.values.get("delete")
            if isinstance(value, BuiltinFunction) and value.name == DELETE_BUILTIN_NAME:
                return value
        return None

    def _delete_member(
        self, container: Any, name: str, environment: Environment
    ) -> bool:
        """Remove ``name`` from an object, instance, or namespace."""
        if isinstance(container, dict):
            if name not in container:
                raise RuntimeErrorX(
                    f"Cannot delete key {name}: object has no such key",
                    "IndexOutOfBoundsException",
                )
            declared = container[name]
            if isinstance(declared, BuiltinFunction):
                raise RuntimeErrorX(
                    f"Cannot delete '{name}': builtins are declared in the "
                    "standard library and cannot be removed",
                    "TypeException",
                )
            del container[name]
            return True
        if isinstance(container, Environment):
            raise RuntimeErrorX(
                f"Cannot delete '{name}' from a namespace: imports declare "
                "their own members",
                "TypeException",
            )
        if isinstance(container, XInstance):
            return self._delete_instance_member(container, name, environment)
        if isinstance(container, XClass):
            raise RuntimeErrorX(
                f"Cannot delete '{name}' from class '{container.name}': "
                "class members are shared by every instance",
                "TypeException",
            )
        if isinstance(container, str):
            raise RuntimeErrorX(
                f"Cannot delete property '{name}' from a string: "
                "strings are immutable",
                "TypeException",
            )
        raise RuntimeErrorX(
            f"Cannot delete property '{name}': "
            f"{self._builtin_type_of([container])} values do not support "
            "property deletion",
            "TypeException",
        )

    def _delete_instance_member(
        self, instance: XInstance, name: str, environment: Environment
    ) -> bool:
        """Remove one field from a class instance (visibility rules apply)."""
        if name in instance.fields:
            field_definition = self._find_field_owner(instance.xclass, name)
            if field_definition is not None:
                field_owner, field_declaration = field_definition
                if not self._can_access_member(
                    field_declaration.modifiers,
                    field_owner,
                    self._access_context(environment),
                ):
                    raise RuntimeErrorX(
                        f"Cannot access {member_noun(field_declaration.modifiers)} "
                        f"'{instance.xclass.name}.{name}'"
                    )
            del instance.fields[name]
            return True
        if instance.xclass.find_methods(name):
            raise RuntimeErrorX(
                f"Cannot delete method '{instance.xclass.name}.{name}': "
                "methods are declared on the class",
                "TypeException",
            )
        if self._find_field_owner(instance.xclass, name, is_static=True) is not None:
            raise RuntimeErrorX(
                f"Cannot delete static field '{instance.xclass.name}.{name}': "
                "static fields are shared by every instance",
                "TypeException",
            )
        raise RuntimeErrorX(
            f"'{instance.xclass.name}' has no member '{name}'"
        )

    def _delete_index(self, container: Any, key: Any) -> bool:
        """Remove one array element (the array shrinks) or one object key."""
        if isinstance(container, list):
            if isinstance(key, bool) or not isinstance(key, int):
                raise RuntimeErrorX(
                    f"Cannot delete index {self._stringify(key)}: "
                    "index must be an integer",
                    "IndexOutOfBoundsException",
                )
            if not (-len(container) <= key < len(container)):
                raise RuntimeErrorX(
                    f"Cannot delete index {key}: out of range for array "
                    f"of length {len(container)}",
                    "IndexOutOfBoundsException",
                )
            container.pop(key)
            return True
        if isinstance(container, dict):
            if isinstance(key, bool) or not isinstance(key, (int, str)):
                raise RuntimeErrorX(
                    f"Cannot delete key {self._stringify(key)}: "
                    "object keys must be strings",
                    "IndexOutOfBoundsException",
                )
            if key not in container:
                raise RuntimeErrorX(
                    f"Cannot delete key {self._stringify(key)}: "
                    "object has no such key",
                    "IndexOutOfBoundsException",
                )
            declared = container[key]
            if isinstance(declared, BuiltinFunction):
                raise RuntimeErrorX(
                    f"Cannot delete '{self._stringify(key)}': builtins are "
                    "declared in the standard library and cannot be removed",
                    "TypeException",
                )
            del container[key]
            return True
        if isinstance(container, str):
            raise RuntimeErrorX(
                f"Cannot delete index {self._stringify(key)}: "
                "strings are immutable",
                "TypeException",
            )
        if isinstance(container, tuple):
            raise RuntimeErrorX(
                f"Cannot delete index {self._stringify(key)}: "
                "tuples do not support index deletion",
                "TypeException",
            )
        if isinstance(container, XInstance):
            raise RuntimeErrorX(
                f"Cannot delete index {self._stringify(key)}: "
                f"class '{container.xclass.name}' members are named, "
                "not indexed",
                "TypeException",
            )
        raise RuntimeErrorX(
            f"Cannot delete index {self._stringify(key)}: "
            f"{self._builtin_type_of([container])} values do not support "
            "index deletion",
            "TypeException",
        )

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

    def _console_members(self) -> dict[str, BuiltinFunction]:
        return {
            "print": BuiltinFunction("Console.print", lambda args: self._builtin_print(args)),
            "input": BuiltinFunction("Console.input", lambda args: self._builtin_input(args)),
        }

    def _exception_namespace(self, name: str) -> dict[str, Any]:
        """Member table for *name* in the ``System.Throwable...`` tree.

        Branches nest (``Exception`` holds ``IOException``, which holds
        ``HttpException``); leaves are the same builtin constructors the
        globals expose, so ``System.Throwable.Exception.IOException.
        HttpException("boom")`` builds the value ``throw`` needs.
        """
        members: dict[str, Any] = {}
        for child in exception_children(name):
            if exception_children(child):
                members[child] = self._exception_namespace(child)
            else:
                value = self.globals.values.get(child)
                if value is not None:
                    members[child] = value
        return members

    def _json_members(self) -> dict[str, BuiltinFunction]:
        """Member table for ``System.utils.JSON``.

        Declares ``toJSON`` as the builtin ``System.utils.JSON.toJSON`` —
        a ``JSON.stringify`` equivalent for X values.
        """
        return {
            "toJSON": BuiltinFunction("JSON.toJSON", self._json_to_string),
        }

    def _json_to_string(self, arguments: list[Any]) -> str:
        """Builtin ``System.utils.JSON.toJSON(value, indent?) -> string``."""
        if len(arguments) not in (1, 2):
            raise RuntimeErrorX(
                "toJSON(value, indent?) expects a value and an optional indent"
            )
        space = arguments[1] if len(arguments) == 2 else None
        return jsonify.stringify(arguments[0], space)

    def _http_fetch(self, arguments: list[Any]) -> Any:
        if len(arguments) not in (1, 2):
            raise RuntimeErrorX(
                "fetch(url, options) expects a url and an optional options object",
                "HttpException",
            )
        options = arguments[1] if len(arguments) == 2 else None
        # Validate synchronously so mistakes surface at the call site with a
        # source location, even before the coroutine is awaited.
        normalize_fetch_call(arguments[0], options)
        return FetchCall(lambda: self._http_fetch_async(arguments[0], options))

    async def _http_fetch_async(self, url: str, options: Any) -> Any:
        return await asyncio.to_thread(perform_fetch, url, options)

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
            )

    def _filesystem_is_file(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("isFile", arguments)
        try:
            return path.is_file()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot check whether '{path}' is a file: {error}",
                "FileSystemException",
            )

    def _filesystem_is_directory(self, arguments: list[Any]) -> bool:
        path = self._filesystem_path("isDirectory", arguments)
        try:
            return path.is_dir()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot check whether '{path}' is a directory: {error}",
                "FileSystemException",
            )

    def _filesystem_read_text(self, arguments: list[Any]) -> str:
        path = self._filesystem_path("readText", arguments)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(
                f"Cannot read text file '{path}': {error}",
                "FileSystemException",
            )

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
            )
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
            )
        return None

    def _filesystem_create_directory(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("createDirectory", arguments)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot create directory '{path}': {error}",
                "FileSystemException",
            )
        return None

    def _filesystem_list_directory(self, arguments: list[Any]) -> list[str]:
        path = self._filesystem_path("listDirectory", arguments)
        try:
            return sorted(entry.name for entry in path.iterdir())
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot list directory '{path}': {error}",
                "FileSystemException",
            )

    def _filesystem_delete_file(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("deleteFile", arguments)
        try:
            path.unlink()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot delete file '{path}': {error}",
                "FileSystemException",
            )
        return None

    def _filesystem_delete_directory(self, arguments: list[Any]) -> None:
        path = self._filesystem_path("deleteDirectory", arguments)
        try:
            path.rmdir()
        except OSError as error:
            raise RuntimeErrorX(
                f"Cannot delete directory '{path}'; it must be empty: {error}",
                "FileSystemException",
            )
        return None


