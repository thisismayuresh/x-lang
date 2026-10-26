"""
Module loader with namespace-aware import semantics.

Imports produce module namespace objects containing exported declarations
accessible via dot access. The loader resolves every file the program needs
transitively (dependencies first) and records two runtime views on the
`Program`:

- `modules` — each file's own top-level declarations, in completion order,
  which the interpreter runs in one top-level `Environment` per file.
- `import_bindings` — what each file's import statements bind (`name`,
  `dict`, `namespace`, or `builtin`), applied to that file's environment,
  before its own declarations are hoisted.

The flat `declarations` list (all files' declarations in one list, imports
spliced in place) is still built and remains what the type checker, the
TypeScript codegen, and the REPL consume; `module_visibility` and
`name_provenance` carry the per-file visibility the checker enforces. Since
bindings no longer land in one shared global scope, re-importing a module
re-binds it instead of raising a collision, and type aliases are never
runtime-bound (they have no runtime value).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import XConfig
from .ast_nodes import (
    Call,
    ClassDeclaration,
    EnumDeclaration,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    ImportAlias,
    ImportBinding,
    ImportDeclaration,
    ImportNamespaceAlias,
    NamespaceDeclaration,
    Program,
    TypeDeclaration,
    VariableDeclaration,
)
from .diagnostics import SourceWarning as ModuleWarning
from .lexer import Lexer
from .parser import Parser
from .runtime import RuntimeErrorX, qualified_exception_paths

class ModuleLoader:
    STANDARD_LIBRARY_MODULES = {
        "System.concurrent.Async",
        "System.concurrent.Lock",
        "System.concurrent.Thread",
        "System.io.FileSystem",
        "System.io.Console",
        "System.io.Network",
        "System.io.Network.http",
        "System.io.Network.http.fetch",
        "System.process",
        "System.process.Environment",
        "System.process.exit",
        "System.utils.Collections",
        "System.utils.Collections.HashMap",
        "System.utils.Collections.LinkedList",
        "System.utils.Collections.List",
        "System.utils.Collections.Stack",
        "System.utils.Collections.Queue",
        "System.utils.Collections.PriorityQueue",
        "System.utils.Collections.Trie",
        "System.utils.Collections.Set",
        "System.utils.Math",
        "System.utils.JSON",
        "System.utils.JSON.toJSON",
        "System.utils.JSON.parse",
        # Every System.Throwable... path mirrors the builtin exception
        # hierarchy: Throwable, Exception, IOException, HttpException, ...
        # The set is generated so it can never drift from the hierarchy.
    } | set(qualified_exception_paths())

    def __init__(
        self,
        project_root: Path,
        config: XConfig | None = None,
        recover_errors: bool = False,
        source_overrides: dict[Path, str] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.config = config or XConfig()
        self.recover_errors = recover_errors
        self.loaded_files: set[Path] = set()
        self.loading_files: set[Path] = set()
        # Files in completion order: every module's imports finish before the
        # module itself, so the entry file is always last.  ``load_program``
        # turns this into ``Program.modules`` / ``Program.import_bindings``.
        self.load_order: list[Path] = []
        self.direct_declarations: dict[Path, list[Any]] = {}
        # What each file's imports bind, recorded while it loads; consumed
        # by the interpreter to scope imports per module instead of hoisting
        # them into one shared global scope.
        self.file_import_bindings: dict[Path, list[ImportBinding]] = {}
        # Per file: modules whose declarations were extended flat into this
        # file's combined list (the narrow branches bind only a member but
        # still flatten the source).  `_combined_origin` walks this chain so
        # a transitive importer's binding points at the module that really
        # declares the name.
        self.flat_parents: dict[Path, list[Path]] = {}
        self.sources: dict[Path, str] = {}
        self.warnings: list[ModuleWarning] = []
        self.errors: list[BaseException] = []
        # In-memory sources keyed by resolved path.  The language server uses
        # this to type-check an unsaved editor buffer together with its real
        # on-disk imports; the CLI leaves it empty and reads everything from
        # disk.  An overridden path is treated as existing even before the
        # file check below, so a brand-new buffer can be checked.
        self.source_overrides: dict[Path, str] = (
            {path.resolve(): text for path, text in source_overrides.items()}
            if source_overrides
            else {}
        )
        self._flattened_bindings: dict[str, Path] = {}  # name -> source module path
        self._emitted_declarations: set[int] = set()
        self._emitted_namespaces: set[tuple[str, str]] = set()
        # Import scoping for the type checker.  ``_module_visibility`` maps a
        # source file (as the parser spells it) to every bare name that file
        # may reference: its own top-level declarations plus exactly what its
        # imports bind.  ``_name_provenance`` maps a name to the dotted import
        # path of the project module declaring it, so the checker can reject
        # sibling leaks and suggest the right ``import`` line.  ``_combined_
        # names`` remembers each loaded module's flattened declaration names
        # for importers that load it a second time (``_load_file`` returns
        # ``[]`` for files already loaded).
        self._module_visibility: dict[str, frozenset[str]] = {}
        self._name_provenance: dict[str, str] = {}
        self._combined_names: dict[Path, set[str]] = {}

    def load_program(self, entry_file: Path) -> Program:
        declarations = self._load_file(entry_file)
        unique_declarations: list[Any] = []
        for declaration in declarations:
            identity = id(declaration)
            if identity in self._emitted_declarations:
                continue
            self._emitted_declarations.add(identity)
            unique_declarations.append(declaration)
        return Program(
            unique_declarations,
            # Completion order — dependencies before importers, entry last —
            # so the interpreter can run each module's file in turn.
            modules={
                str(path): list(self.direct_declarations[path])
                for path in self.load_order
            },
            import_bindings={
                str(path): list(self.file_import_bindings.get(path, ()))
                for path in self.load_order
            },
            module_visibility=dict(self._module_visibility),
            name_provenance=dict(self._name_provenance),
        )

    def _load_file(self, source_path: Path) -> list[Any]:
        resolved_path = source_path.resolve()
        if resolved_path in self.loading_files:
            raise RuntimeErrorX(f"Circular module import detected at '{source_path}'")
        if resolved_path in self.loaded_files:
            return []
        overridden = self.source_overrides.get(resolved_path)
        if overridden is None and not resolved_path.is_file():
            raise RuntimeErrorX(f"Imported source file '{source_path}' does not exist")

        try:
            source = (
                overridden
                if overridden is not None
                else resolved_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(f"Cannot read source file '{source_path}': {error}") from error

        self.sources[resolved_path] = source
        try:
            lexer = Lexer(
                source,
                str(resolved_path),
                recover_errors=self.recover_errors,
            )
            tokens = lexer.tokenize()
            self.errors.extend(lexer.errors)
            parser = Parser(
                tokens,
                self.config.features,
                str(resolved_path),
                recover_errors=self.recover_errors,
            )
            program = parser.parse()
            self.errors.extend(parser.errors)
        except RecursionError:
            raise RuntimeErrorX(
                f"Maximum recursion depth exceeded while parsing "
                f"'{source_path}'; the file nests too deeply"
            ) from None
        direct_declarations = [
            declaration
            for declaration in program.declarations
            if declaration is not None
            and (
                not isinstance(declaration, ImportDeclaration)
                # `import B.greet("Maya")` imports *and* calls, so it stays in
                # the file's own declarations to run after its imports bind.
                or declaration.statement is not None
            )
        ]
        self.direct_declarations[resolved_path] = direct_declarations
        self._warn_about_bare_main_reference(
            direct_declarations, str(resolved_path)
        )
        module_spelling = str(resolved_path)
        visible: set[str] = set()
        for declaration in direct_declarations:
            name = self._declaration_name(declaration)
            if name is None:
                continue
            visible.add(name)
            # value = declaring file, so the checker can suggest the right
            # importer-relative `import ...` line.
            self._name_provenance.setdefault(name, module_spelling)
        self.loading_files.add(resolved_path)

        combined_declarations: list[Any] = []
        # Every import below records what it binds into this file, next to
        # the flat declarations it appends to `combined_declarations`.
        bindings: list[ImportBinding] = []
        for declaration in program.declarations:
            if not isinstance(declaration, ImportDeclaration):
                continue
            for module_path, alias in declaration.targets:
                self._warn_default_reimport(module_path, declaration, str(resolved_path))
                if declaration.wildcard:
                    imported_path = self._path_for_module(
                        module_path, resolved_path
                    )
                    # `import util.MyNamespace.*`: wildcard over a namespace
                    # chain, not a file path. Guarded to user modules so
                    # `System.*` stdlib file paths keep their resolution.
                    if (
                        not imported_path.is_file()
                        and module_path not in self.STANDARD_LIBRARY_MODULES
                        and not module_path.startswith("System.")
                        and self._import_namespace_wildcard(
                            module_path,
                            resolved_path,
                            direct_declarations,
                            alias,
                            visible,
                            combined_declarations,
                            bindings,
                        )
                    ):
                        continue
                    imported_declarations = self._load_file(imported_path)
                    imported_resolved_path = imported_path.resolve()
                    exported_names = self._exported_names(imported_resolved_path)
                    if not exported_names:
                        raise RuntimeErrorX(
                            f"Module '{module_path}' does not export any declarations"
                        )
                    self._warn_duplicate_main(
                        imported_resolved_path,
                        resolved_path,
                        direct_declarations,
                    )
                    combined_names = self._combined_names.get(
                        imported_resolved_path,
                        self._names_of(imported_declarations),
                    )
                    visible.update(combined_names)
                    for name in combined_names:
                        origin = self._combined_origin(
                            imported_resolved_path, name
                        )
                        if origin is None:
                            continue  # type alias: no runtime value
                        bindings.append(
                            ImportBinding(
                                local=name,
                                kind="name",
                                source=origin[0],
                                source_name=origin[1],
                            )
                        )
                    combined_declarations.extend(imported_declarations)
                    self.flat_parents.setdefault(resolved_path, []).append(
                        imported_resolved_path
                    )
                    if alias is not None:
                        visible.add(alias)
                        combined_declarations.append(
                            ImportNamespaceAlias(exported_names, alias)
                        )
                        bindings.append(
                            ImportBinding(
                                local=alias,
                                kind="dict",
                                source=str(imported_resolved_path),
                                members=tuple(
                                    (name, name)
                                    for name in exported_names
                                    if not isinstance(
                                        self._declaration_at(
                                            imported_resolved_path, name
                                        ),
                                        TypeDeclaration,
                                    )
                                ),
                            )
                        )
                    continue

                module_parts = module_path.split(".")
                if len(module_parts) > 1:
                    source_module = ".".join(module_parts[:-1])
                    source_path = self._path_for_module(
                        source_module, resolved_path
                    )
                    if source_path.is_file():
                        imported_declarations = self._load_file(source_path)
                        imported_resolved_path = source_path.resolve()
                        import_name = module_parts[-1]
                        if not self._is_exported(
                            imported_resolved_path, import_name
                        ):
                            raise RuntimeErrorX(
                                f"'{import_name}' is not exported by module "
                                f"'{source_module}'"
                            )
                        self._warn_duplicate_main(
                            imported_resolved_path,
                            resolved_path,
                            direct_declarations,
                        )
                        self._check_flatten_collision(
                            import_name, imported_resolved_path
                        )
                        self._record_flatten(import_name, imported_resolved_path)
                        # Member imports bind only the named declaration:
                        # `import util.Gender` lets you say `Gender`, not the
                        # rest of util's scope.  A type alias member
                        # (`import util.Info`) stays type-only: it has no
                        # runtime value to bind.
                        visible.add(import_name)
                        if not isinstance(
                            self._declaration_at(imported_resolved_path, import_name),
                            TypeDeclaration,
                        ):
                            bindings.append(
                                ImportBinding(
                                    local=import_name,
                                    kind="name",
                                    source=str(imported_resolved_path),
                                    source_name=import_name,
                                )
                            )
                        if alias is not None:
                            visible.add(alias)
                            if not isinstance(
                                self._declaration_at(
                                    imported_resolved_path, import_name
                                ),
                                TypeDeclaration,
                            ):
                                bindings.append(
                                    ImportBinding(
                                        local=alias,
                                        kind="name",
                                        source=str(imported_resolved_path),
                                        source_name=import_name,
                                    )
                                )
                        combined_declarations.extend(imported_declarations)
                        self.flat_parents.setdefault(resolved_path, []).append(
                            imported_resolved_path
                        )
                        if alias is not None:
                            combined_declarations.append(
                                ImportAlias(import_name, alias)
                            )
                        continue

                # `import util.MyNamespace.fun`: a namespace chain inside the
                # shortest existing prefix module file, not a plain file path
                # (`util/MyNamespace/fun.x`). Guarded to user modules so
                # `System.*` stdlib file paths keep their resolution.
                if (
                    module_path not in self.STANDARD_LIBRARY_MODULES
                    and not module_path.startswith("System.")
                    and self._import_namespace_path(
                        module_path,
                        resolved_path,
                        direct_declarations,
                        alias,
                        visible,
                        combined_declarations,
                        bindings,
                    )
                ):
                    continue

                if module_path in self.STANDARD_LIBRARY_MODULES:
                    self._require_standard_library_feature(module_path)
                    import_name = module_path.split(".")[-1]
                    visible.add(alias or import_name)
                    combined_declarations.append(
                        ImportAlias(module_path, alias or import_name)
                    )
                    bindings.append(
                        ImportBinding(
                            local=alias or import_name,
                            kind="builtin",
                            source=module_path,
                        )
                    )
                    continue
                imported_path = self._path_for_module(module_path, resolved_path)
                imported_declarations = self._load_file(imported_path)
                imported_resolved_path = imported_path.resolve()
                self._warn_duplicate_main(
                    imported_resolved_path,
                    resolved_path,
                    direct_declarations,
                )
                import_name = module_path.split(".")[-1]
                exported_names = self._exported_names(imported_resolved_path)
                combined_names = self._combined_names.get(
                    imported_resolved_path,
                    self._names_of(imported_declarations),
                )
                visible.update(combined_names)
                for name in combined_names:
                    origin = self._combined_origin(imported_resolved_path, name)
                    if origin is None:
                        continue  # type alias: no runtime value
                    bindings.append(
                        ImportBinding(
                            local=name,
                            kind="name",
                            source=origin[0],
                            source_name=origin[1],
                        )
                    )
                combined_declarations.extend(imported_declarations)
                self.flat_parents.setdefault(resolved_path, []).append(
                    imported_resolved_path
                )
                if alias is not None:
                    if import_name in exported_names:
                        self._check_flatten_collision(
                            import_name, imported_resolved_path
                        )
                        self._record_flatten(import_name, imported_resolved_path)
                        visible.add(alias)
                        combined_declarations.append(
                            ImportAlias(import_name, alias)
                        )
                        if not isinstance(
                            self._declaration_at(
                                imported_resolved_path, import_name
                            ),
                            TypeDeclaration,
                        ):
                            bindings.append(
                                ImportBinding(
                                    local=alias,
                                    kind="name",
                                    source=str(imported_resolved_path),
                                    source_name=import_name,
                                )
                            )
                    else:
                        visible.add(alias)
                        combined_declarations.append(
                            NamespaceDeclaration(
                                alias,
                                self._namespace_members(
                                    imported_resolved_path, exported_names
                                ),
                            )
                        )
                        bindings.append(
                            ImportBinding(
                                local=alias,
                                kind="namespace",
                                source=str(imported_resolved_path),
                                members=self._value_members(
                                    imported_resolved_path, exported_names
                                ),
                            )
                        )
                    continue
                for name in exported_names:
                    self._check_flatten_collision(name, imported_resolved_path)
                    self._record_flatten(name, imported_resolved_path)
                if exported_names and not self._declares(
                    imported_resolved_path, import_name
                ):
                    self._emit_namespace(
                        combined_declarations,
                        import_name,
                        imported_resolved_path,
                        exported_names,
                    )
                    visible.add(import_name)
                    bindings.append(
                        ImportBinding(
                            local=import_name,
                            kind="namespace",
                            source=str(imported_resolved_path),
                            members=self._value_members(
                                imported_resolved_path, exported_names
                            ),
                        )
                    )

        combined_declarations.extend(direct_declarations)
        self.loading_files.remove(resolved_path)
        self.loaded_files.add(resolved_path)
        self.load_order.append(resolved_path)
        self.file_import_bindings[resolved_path] = bindings
        self._module_visibility[str(resolved_path)] = frozenset(visible)
        self._combined_names[resolved_path] = self._names_of(
            combined_declarations
        )
        return combined_declarations

    def _emit_namespace(
        self,
        combined: list[Any],
        namespace_name: str,
        source_module: Path,
        exported_names: list[str],
    ) -> None:
        key = (namespace_name, str(source_module.resolve()))
        if key in self._emitted_namespaces:
            return
        self._emitted_namespaces.add(key)
        combined.append(
            NamespaceDeclaration(
                namespace_name,
                self._namespace_members(source_module, exported_names),
            )
        )

    def _namespace_prefix_file(
        self, module_path: str, importer_path: Path
    ) -> tuple[Path | None, list[str]]:
        """Shortest existing prefix module file for a dotted import.

        Returns ``(source_path, remaining_parts)`` where ``remaining_parts``
        are the dots still to resolve inside that file, or ``(None, [])``
        when no prefix file exists.
        """
        parts = module_path.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            candidate = self._path_for_module(".".join(parts[:cut]), importer_path)
            if candidate.is_file():
                return candidate, parts[cut:]
        return None, []

    def _append_flat_alias(
        self, combined_declarations: list[Any], source: str, name: str
    ) -> None:
        """Bind ``name`` from the dotted ``source`` unless already flat-bound.

        Equivalent ``ImportAlias`` nodes from repeated imports of the same
        member would emit duplicate ``const`` bindings in TypeScript
        codegen, so a second binding of the same name is skipped.
        """
        for item in combined_declarations:
            if isinstance(item, ImportAlias) and item.alias_name == name:
                return
        combined_declarations.append(ImportAlias(source, name))

    def _namespace_in_chain(
        self,
        current: list[Any],
        part: str,
        source_module: str,
        require_export: bool = True,
    ) -> NamespaceDeclaration:
        """Find namespace *part* among *current* declarations.

        Only the module-level hop requires the ``export`` modifier: an
        exported namespace publishes everything inside it (nested
        namespaces included), like a class publishes its methods.
        """
        namespace = next(
            (
                item
                for item in current
                if isinstance(item, NamespaceDeclaration) and item.name == part
            ),
            None,
        )
        if namespace is None:
            raise RuntimeErrorX(
                f"'{part}' does not name a namespace in module '{source_module}'"
            )
        if require_export and "export" not in getattr(namespace, "modifiers", set()):
            raise RuntimeErrorX(
                f"'{part}' is not exported by module '{source_module}'"
            )
        return namespace

    def _import_namespace_path(
        self,
        module_path: str,
        importer_path: Path,
        direct_declarations: list[Any],
        alias: str | None,
        visible: set[str],
        combined_declarations: list[Any],
        bindings: list[ImportBinding],
    ) -> bool:
        """Bind `import util.MyNamespace.fun`: a namespace chain inside the
        shortest existing prefix module file.

        Returns False when no prefix file exists (the caller falls back to
        plain file-path imports). Raises RuntimeErrorX when a file was found
        but the namespace chain or the member is missing or not exported.
        """
        parts = module_path.split(".")
        source_path, remaining = self._namespace_prefix_file(
            module_path, importer_path
        )
        if source_path is None or not remaining:
            return False
        source_module = ".".join(parts[: len(parts) - len(remaining)])
        declarations = self._load_file(source_path)
        # `_load_file` returns [] for already-loaded files; the declarations
        # themselves live in the persistent cache (same as `_is_exported`).
        current = self.direct_declarations.get(source_path.resolve(), declarations)
        for index, part in enumerate(remaining[:-1]):
            current = self._namespace_in_chain(
                current, part, source_module, require_export=index == 0
            ).declarations
        import_name = remaining[-1]
        member = next(
            (item for item in current if self._declaration_name(item) == import_name),
            None,
        )
        if len(remaining) > 1:
            # Inside an exported namespace every member is reachable — the
            # namespace boundary is the export boundary (like a class and
            # its methods).
            if member is None:
                raise RuntimeErrorX(
                    f"'{import_name}' is not a member of namespace "
                    f"'{'.'.join(parts[: len(parts) - 1])}'"
                )
        elif member is None or "export" not in getattr(member, "modifiers", set()):
            # A top-level file member keeps the file's export rules.
            raise RuntimeErrorX(
                f"'{import_name}' is not exported by module '{source_module}'"
            )
        imported_resolved_path = source_path.resolve()
        self._warn_duplicate_main(
            imported_resolved_path, importer_path, direct_declarations
        )
        self._check_flatten_collision(import_name, imported_resolved_path)
        self._record_flatten(import_name, imported_resolved_path)
        visible.add(import_name)
        # The dotted path inside the prefix file (`MyNamespace.fun`): the
        # runtime binding walks it from that module's own environment.  A
        # type-alias member has no runtime value, so it stays type-only.
        is_value = not isinstance(member, TypeDeclaration)
        source_name = ".".join(remaining)
        if is_value:
            bindings.append(
                ImportBinding(
                    local=import_name,
                    kind="name",
                    source=str(imported_resolved_path),
                    source_name=source_name,
                )
            )
        if alias is not None:
            visible.add(alias)
            if is_value:
                bindings.append(
                    ImportBinding(
                        local=alias,
                        kind="name",
                        source=str(imported_resolved_path),
                        source_name=source_name,
                    )
                )
        combined_declarations.extend(declarations)
        self.flat_parents.setdefault(importer_path.resolve(), []).append(
            imported_resolved_path
        )
        if len(remaining) > 1:
            # The member lives inside a namespace: bind the ORIGINAL value via
            # ImportAlias. Re-declaring it flat would rebind with a globals
            # closure and break sibling references like `print(obj)`.
            self._append_flat_alias(
                combined_declarations, source_name, import_name
            )
        if alias is not None:
            combined_declarations.append(ImportAlias(import_name, alias))
        return True

    def _import_namespace_wildcard(
        self,
        module_path: str,
        importer_path: Path,
        direct_declarations: list[Any],
        alias: str | None,
        visible: set[str],
        combined_declarations: list[Any],
        bindings: list[ImportBinding],
    ) -> bool:
        """Bind `import util.MyNamespace.*`: every exported member of the
        namespace chain inside the shortest existing prefix module file.

        Returns False when no prefix file exists (the caller falls back to
        plain file-path wildcard imports).
        """
        parts = module_path.split(".")
        source_path, remaining = self._namespace_prefix_file(
            module_path, importer_path
        )
        if source_path is None or not remaining:
            return False
        source_module = ".".join(parts[: len(parts) - len(remaining)])
        declarations = self._load_file(source_path)
        current = self.direct_declarations.get(source_path.resolve(), declarations)
        for index, part in enumerate(remaining[:-1]):
            current = self._namespace_in_chain(
                current, part, source_module, require_export=index == 0
            ).declarations
        namespace = self._namespace_in_chain(
            current,
            remaining[-1],
            source_module,
            require_export=len(remaining) == 1,
        )
        members = [
            (name, member)
            for member in namespace.declarations
            if (name := self._declaration_name(member)) is not None
        ]
        if not members:
            raise RuntimeErrorX(
                f"Namespace '{module_path}' declares no members"
            )
        imported_resolved_path = source_path.resolve()
        self._warn_duplicate_main(
            imported_resolved_path, importer_path, direct_declarations
        )
        # Bind the namespace itself so the flat aliases below resolve through
        # it even when nothing else has imported the module.
        combined_declarations.append(namespace)
        source_name = ".".join(remaining)
        # The namespace enters this file's flattened scope through the append
        # above, so record it too: a transitive importer of this file may
        # reference it, and its binding must walk the chain in the prefix
        # file's own module scope.
        bindings.append(
            ImportBinding(
                local=namespace.name,
                kind="name",
                source=str(imported_resolved_path),
                source_name=source_name,
            )
        )
        for name, member in members:
            self._check_flatten_collision(name, imported_resolved_path)
            self._record_flatten(name, imported_resolved_path)
            visible.add(name)
            # The flat alias stays rooted at the namespace name appended
            # above (top-level in the flat scope); the ImportBinding walks
            # the full chain in the prefix module's own scope instead.
            # Type-alias members have no runtime value to bind.
            self._append_flat_alias(
                combined_declarations,
                f"{remaining[-1]}.{name}",
                name,
            )
            if not isinstance(member, TypeDeclaration):
                bindings.append(
                    ImportBinding(
                        local=name,
                        kind="name",
                        source=str(imported_resolved_path),
                        source_name=f"{source_name}.{name}",
                    )
                )
        if alias is not None:
            visible.add(alias)
            combined_declarations.append(
                ImportNamespaceAlias([name for name, _ in members], alias)
            )
            bindings.append(
                ImportBinding(
                    local=alias,
                    kind="dict",
                    source=str(imported_resolved_path),
                    members=tuple(
                        (name, f"{source_name}.{name}")
                        for name, member in members
                        if not isinstance(member, TypeDeclaration)
                    ),
                )
            )
        return True

    def _namespace_members(
        self, source_module: Path, exported_names: list[str]
    ) -> list[Any]:
        declarations = self.direct_declarations.get(source_module, [])
        return [
            declaration
            for name in exported_names
            for declaration in declarations
            if self._declaration_name(declaration) == name
        ]

    def _declares(self, source_module: Path, name: str) -> bool:
        return any(
            self._declaration_name(declaration) == name
            for declaration in self.direct_declarations.get(source_module, [])
        )

    def _value_members(
        self, source_module: Path, names: list[str]
    ) -> tuple[tuple[str, str], ...]:
        """``(local, dotted)`` pairs for names that are runtime values.

        Type aliases are type-checker-only — a namespace object built from
        these names must skip them, exactly like the flat
        ``_define_namespace`` pass does.
        """
        return tuple(
            (name, name)
            for name in names
            if not isinstance(
                self._declaration_at(source_module, name), TypeDeclaration
            )
        )

    def _declaration_at(self, source_module: Path, name: str) -> Any | None:
        """Top-level declaration named ``name`` in ``source_module``."""
        for declaration in self.direct_declarations.get(source_module, []):
            if self._declaration_name(declaration) == name:
                return declaration
        return None

    def _combined_origin(
        self, source_module: Path, name: str
    ) -> tuple[str, str] | None:
        """Where ``name`` in ``source_module``'s flattened scope comes from.

        Returns ``(module path, dotted name)`` so an importer's binding can
        walk the declaring module's own environment instead of the (possibly
        narrower) intermediate scope.  Follows this file's recorded bindings
        and its flat-flattened parents transitively; falls back to resolving
        the name directly in ``source_module``.  Returns ``None`` when the
        name is a type alias — those exist only for the type checker and
        never materialise as a runtime value.
        """
        declaration = self._declaration_at(source_module, name)
        if declaration is not None:
            if isinstance(declaration, TypeDeclaration):
                return None
            return str(source_module), name
        for binding in self.file_import_bindings.get(source_module, ()):
            if binding.local != name:
                continue
            if binding.kind == "name":
                return binding.source, binding.source_name
            # dict/namespace/builtin bindings are installed under this
            # file's own scope, so the name resolves there.
            return str(source_module), name
        for parent in self.flat_parents.get(source_module, ()):
            if name in self._combined_names.get(parent, ()):
                # The parent's chain has the definitive answer — a real
                # origin, or None when it is a type alias.
                return self._combined_origin(parent, name)
        return str(source_module), name

    def _require_standard_library_feature(self, module_path: str) -> None:
        feature_for_module = {
            "System.concurrent.Async": "async",
            "System.concurrent.Lock": "threads",
            "System.concurrent.Thread": "threads",
            "System.io.FileSystem": "filesystem",
        }
        if module_path == "System.utils.Collections" or module_path.startswith(
            "System.utils.Collections."
        ):
            feature_name = "collections"
        elif module_path == "System.utils.Math":
            feature_name = "math_library"
        elif module_path == "System.io.Console":
            feature_name = "command_input"
        elif module_path == "System.io.Network" or module_path.startswith(
            "System.io.Network."
        ):
            feature_name = "network"
        elif module_path == "System.Throwable" or module_path.startswith(
            "System.Throwable."
        ):
            feature_name = "exceptions"
        else:
            feature_name = feature_for_module.get(module_path)
        if feature_name is not None and not self.config.enabled(feature_name):
            raise RuntimeErrorX(
                f"Cannot import '{module_path}': feature '{feature_name}' is disabled"
            )

    def _path_for_module(self, module_path: str, importer_path: Path) -> Path:
        path_parts = module_path.split(".")
        relative_path = importer_path.parent.joinpath(*path_parts).with_suffix(".x")
        if relative_path.is_file():
            return relative_path
        return self.project_root.joinpath(*path_parts).with_suffix(".x")

    def _exported_names(self, module_path: Path) -> list[str]:
        return [
            name
            for declaration in self.direct_declarations.get(module_path, [])
            if "export" in getattr(declaration, "modifiers", set())
            and (name := self._declaration_name(declaration)) is not None
        ]

    def _warn_default_reimport(
        self, module_path: str, declaration: Any, source_name: str
    ) -> None:
        """Warn when a module is imported explicitly AND has been added to
        ``[imports].default`` so the import is repeated."""
        if module_path not in getattr(self.config, "default_imports", []):
            return
        self.warnings.append(
            ModuleWarning(
                f"'{module_path}' is declared as a default import in x.toml "
                f"([imports].default); importing it again is redundant",
                source_name,
                getattr(declaration, "line", None),
                getattr(declaration, "column", None),
            )
        )

    def _warn_duplicate_main(
        self,
        imported_resolved_path: Path,
        importer_path: Path,
        importer_declarations: list[Any],
    ) -> None:
        if not self._has_top_level_call(
            self.direct_declarations[imported_resolved_path], "main"
        ):
            return
        for call_site in self._top_level_calls(importer_declarations, "main"):
            self.warnings.append(
                ModuleWarning(
                    "The imported module already calls main() during "
                    "import. This call runs it again; remove this call "
                    "to avoid duplicate execution.",
                    str(importer_path),
                    getattr(call_site, "line", None),
                    getattr(call_site, "column", None),
                )
            )

    def _is_exported(self, module_path: Path, name: str) -> bool:
        declarations = self.direct_declarations.get(module_path, [])
        for declaration in declarations:
            if self._declaration_name(declaration) != name:
                continue
            if "export" in getattr(declaration, "modifiers", set()):
                return True
        return False

    def _has_top_level_call(
        self, declarations: list[Any], function_name: str
    ) -> bool:
        return bool(self._top_level_calls(declarations, function_name))

    def _top_level_calls(
        self, declarations: list[Any], function_name: str
    ) -> list[ExpressionStatement]:
        call_statements: list[ExpressionStatement] = []
        for declaration in declarations:
            if not isinstance(declaration, ExpressionStatement):
                continue
            expression = declaration.expression
            if not isinstance(expression, Call):
                continue
            if (
                isinstance(expression.callee, Identifier)
                and expression.callee.name == function_name
            ):
                call_statements.append(declaration)
        return call_statements

    def _warn_about_bare_main_reference(
        self, declarations: list[Any], source_name: str
    ) -> None:
        for declaration in declarations:
            if not isinstance(declaration, ExpressionStatement):
                continue
            if not isinstance(declaration.expression, Identifier):
                continue
            if declaration.expression.name != "main":
                continue
            self.warnings.append(
                ModuleWarning(
                    "This references main without calling it. Since '//' starts "
                    "a line comment, write 'main()' to invoke it or '// main()' "
                    "to comment out the call.",
                    source_name,
                    getattr(declaration, "line", None),
                    getattr(declaration, "column", None),
                )
            )

    def _declaration_name(self, declaration: Any) -> str | None:
        if isinstance(
            declaration,
            (
                ClassDeclaration,
                EnumDeclaration,
                FunctionDeclaration,
                NamespaceDeclaration,
                TypeDeclaration,
                VariableDeclaration,
            ),
        ):
            return declaration.name
        return None

    def _names_of(self, declarations: list[Any]) -> set[str]:
        names: set[str] = set()
        for declaration in declarations:
            name = self._declaration_name(declaration)
            if name is not None:
                names.add(name)
        return names

    def _module_name_from_path(self, module_path: Path) -> str:
        resolved = module_path.resolve()
        try:
            relative = resolved.relative_to(self.project_root)
        except ValueError:
            # Outside the project root (e.g. an absolute import in a temp
            # dir): fall back to the file name itself.
            relative = resolved
        return relative.with_suffix("").name

    def _check_flatten_collision(self, name: str, source_module: Path) -> None:
        if name in self._flattened_bindings:
            existing_source = self._flattened_bindings[name]
            if existing_source != source_module.resolve():
                existing_name = self._module_name_from_path(existing_source)
                new_name = self._module_name_from_path(source_module)
                raise RuntimeErrorX(
                    f"'{name}' is already declared (from module "
                    f"'{existing_name}' and now from module '{new_name}')"
                )

    def _record_flatten(self, name: str, source_module: Path) -> None:
        source_resolved = source_module.resolve()
        if name not in self._flattened_bindings:
            self._flattened_bindings[name] = source_resolved
        elif self._flattened_bindings[name] != source_resolved:
            self._check_flatten_collision(name, source_module)
