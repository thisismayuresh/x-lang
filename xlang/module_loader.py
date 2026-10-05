from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import XConfig
from .ast_nodes import (
    ClassDeclaration,
    EnumDeclaration,
    FunctionDeclaration,
    ImportAlias,
    ImportDeclaration,
    Program,
    TypeDeclaration,
    VariableDeclaration,
)
from .lexer import Lexer
from .parser import Parser
from .runtime import RuntimeErrorX


class ModuleLoader:
    STANDARD_LIBRARY_MODULES = {
        "System.concurrent.Async",
        "System.concurrent.Thread",
        "System.io.FileSystem",
        "System.Environment",
    }

    def __init__(self, project_root: Path, config: XConfig | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config = config or XConfig()
        self.loaded_files: set[Path] = set()
        self.loading_files: set[Path] = set()
        self.direct_declarations: dict[Path, list[Any]] = {}
        self.sources: dict[Path, str] = {}

    def load_program(self, entry_file: Path) -> Program:
        declarations = self._load_file(entry_file)
        return Program(declarations)

    def _load_file(self, source_path: Path) -> list[Any]:
        resolved_path = source_path.resolve()
        if resolved_path in self.loading_files:
            raise RuntimeErrorX(f"Circular module import detected at '{source_path}'")
        if resolved_path in self.loaded_files:
            return []
        if not resolved_path.is_file():
            raise RuntimeErrorX(f"Imported source file '{source_path}' does not exist")

        try:
            source = resolved_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeErrorX(f"Cannot read source file '{source_path}': {error}") from error

        self.sources[resolved_path] = source
        lexer = Lexer(source, str(resolved_path))
        tokens = lexer.tokenize()
        parser = Parser(tokens, self.config.features, str(resolved_path))
        program = parser.parse()
        direct_declarations = [
            declaration
            for declaration in program.declarations
            if not isinstance(declaration, ImportDeclaration) and declaration is not None
        ]
        self.direct_declarations[resolved_path] = direct_declarations
        self.loading_files.add(resolved_path)

        combined_declarations: list[Any] = []
        for declaration in program.declarations:
            if not isinstance(declaration, ImportDeclaration):
                continue
            for module_path, alias in declaration.targets:
                if module_path in self.STANDARD_LIBRARY_MODULES:
                    self._require_standard_library_feature(module_path)
                    import_name = module_path.split(".")[-1]
                    combined_declarations.append(
                        ImportAlias(module_path, alias or import_name)
                    )
                    continue
                imported_path = self._path_for_module(module_path, resolved_path)
                imported_declarations = self._load_file(imported_path)
                import_name = module_path.split(".")[-1]
                if not self._is_exported(imported_path.resolve(), import_name):
                    raise RuntimeErrorX(
                        f"'{import_name}' is not exported by module '{module_path}'"
                    )
                combined_declarations.extend(imported_declarations)
                if alias is not None:
                    combined_declarations.append(ImportAlias(import_name, alias))

        combined_declarations.extend(direct_declarations)
        self.loading_files.remove(resolved_path)
        self.loaded_files.add(resolved_path)
        return combined_declarations

    def _require_standard_library_feature(self, module_path: str) -> None:
        feature_for_module = {
            "System.concurrent.Async": "async",
            "System.concurrent.Thread": "threads",
            "System.io.FileSystem": "filesystem",
        }
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

    def _is_exported(self, module_path: Path, name: str) -> bool:
        declarations = self.direct_declarations.get(module_path, [])
        for declaration in declarations:
            if self._declaration_name(declaration) != name:
                continue
            if "export" in getattr(declaration, "modifiers", set()):
                return True
        return False

    def _declaration_name(self, declaration: Any) -> str | None:
        if isinstance(
            declaration,
            (
                ClassDeclaration,
                EnumDeclaration,
                FunctionDeclaration,
                TypeDeclaration,
                VariableDeclaration,
            ),
        ):
            return declaration.name
        return None
