"""
Module loader with namespace-aware import semantics.

Imports produce module namespace objects containing exported declarations
accessible via dot access. Flattened bindings into the importing scope
are retained only when collision-free for backward compatibility; when
flattening would create a different binding for an existing name, a
RuntimeErrorX is raised.
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

"""
Module loader for X language programs.

This module is responsible for loading and resolving module dependencies.
When importing modules, the loader creates module namespace objects
containing exported declarations accessible via dot access. Flattening
of declarations into the importing scope occurs only when necessary for
backward compatibility and only when it does not create collisions between
different bindings; otherwise, a RuntimeErrorX is raised.
"""

"""
Module loader for X language programs.

This module is responsible for loading and resolving module dependencies.
When importing modules, the loader creates module namespace objects
containing exported declarations accessible via dot access. Flattening
of declarations into the importing scope occurs only when necessary for
backward compatibility and only when it does not create collisions between
different bindings; otherwise, a RuntimeErrorX is raised.
"""


"""
Module loader for X language programs.

This module is responsible for loading and resolving module dependencies.
When importing modules, the loader must create module namespace objects
containing the exported declarations of imported modules, accessible via
dot access (e.g., `module.declaration`). Declarations are no longer
arbitrarily flattened into the importing scope; flattening occurs only
when necessary for backward compatibility and never when it would create
a collision between different exported declarations. When a collision
would occur from flattening, an error is raised.
"""


class ModuleLoader:
    STANDARD_LIBRARY_MODULES = {
        "System.concurrent.Async",
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
        self.direct_declarations: dict[Path, list[Any]] = {}
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
                    visible.update(
                        self._combined_names.get(
                            imported_resolved_path,
                            self._names_of(imported_declarations),
                        )
                    )
                    combined_declarations.extend(imported_declarations)
                    if alias is not None:
                        visible.add(alias)
                        combined_declarations.append(
                            ImportNamespaceAlias(exported_names, alias)
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
                        # rest of util's scope.
                        visible.add(import_name)
                        if alias is not None:
                            visible.add(alias)
                        combined_declarations.extend(imported_declarations)
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
                visible.update(
                    self._combined_names.get(
                        imported_resolved_path,
                        self._names_of(imported_declarations),
                    )
                )
                if alias is not None:
                    if import_name in exported_names:
                        self._check_flatten_collision(
                            import_name, imported_resolved_path
                        )
                        self._record_flatten(import_name, imported_resolved_path)
                        visible.add(alias)
                        combined_declarations.extend(imported_declarations)
                        combined_declarations.append(
                            ImportAlias(import_name, alias)
                        )
                    else:
                        visible.add(alias)
                        combined_declarations.extend(imported_declarations)
                        combined_declarations.append(
                            NamespaceDeclaration(
                                alias,
                                self._namespace_members(
                                    imported_resolved_path, exported_names
                                ),
                            )
                        )
                    continue
                for name in exported_names:
                    self._check_flatten_collision(name, imported_resolved_path)
                    self._record_flatten(name, imported_resolved_path)
                combined_declarations.extend(imported_declarations)
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

        combined_declarations.extend(direct_declarations)
        self.loading_files.remove(resolved_path)
        self.loaded_files.add(resolved_path)
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
        self, current: list[Any], part: str, source_module: str
    ) -> NamespaceDeclaration:
        """Find exported namespace *part* among *current* declarations."""
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
        if "export" not in getattr(namespace, "modifiers", set()):
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
        for part in remaining[:-1]:
            current = self._namespace_in_chain(current, part, source_module).declarations
        import_name = remaining[-1]
        member = next(
            (item for item in current if self._declaration_name(item) == import_name),
            None,
        )
        if member is None or "export" not in getattr(member, "modifiers", set()):
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
        if alias is not None:
            visible.add(alias)
        combined_declarations.extend(declarations)
        if len(remaining) > 1:
            # The member lives inside a namespace: bind the ORIGINAL value via
            # ImportAlias. Re-declaring it flat would rebind with a globals
            # closure and break sibling references like `print(obj)`.
            self._append_flat_alias(
                combined_declarations, ".".join(remaining), import_name
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
        for part in remaining[:-1]:
            current = self._namespace_in_chain(current, part, source_module).declarations
        namespace = self._namespace_in_chain(current, remaining[-1], source_module)
        exported_members = [
            (name, member)
            for member in namespace.declarations
            if (name := self._declaration_name(member)) is not None
            and "export" in getattr(member, "modifiers", set())
        ]
        if not exported_members:
            raise RuntimeErrorX(
                f"Namespace '{module_path}' does not export any declarations"
            )
        imported_resolved_path = source_path.resolve()
        self._warn_duplicate_main(
            imported_resolved_path, importer_path, direct_declarations
        )
        # Bind the namespace itself so the flat aliases below resolve through
        # it even when nothing else has imported the module.
        combined_declarations.append(namespace)
        target = remaining[-1]
        for name, _member in exported_members:
            self._check_flatten_collision(name, imported_resolved_path)
            self._record_flatten(name, imported_resolved_path)
            visible.add(name)
            self._append_flat_alias(combined_declarations, f"{target}.{name}", name)
        if alias is not None:
            visible.add(alias)
            combined_declarations.append(
                ImportNamespaceAlias([name for name, _ in exported_members], alias)
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

    def _require_standard_library_feature(self, module_path: str) -> None:
        feature_for_module = {
            "System.concurrent.Async": "async",
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
