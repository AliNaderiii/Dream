"""Structural Python code analysis and AST symbol graph indexer."""

from __future__ import annotations

import ast
import logging
from typing import Any

from dream.refactor.types import CodeSymbol, SymbolType

logger = logging.getLogger(__name__)


class ASTSymbolIndexer:
    """Extracts structural code symbols, definitions, and dependencies from Python AST."""

    def __init__(self) -> None:
        self._symbols_by_name: dict[str, list[CodeSymbol]] = {}
        self._symbols_by_file: dict[str, list[CodeSymbol]] = {}

    def index_source_code(self, file_path: str, source_code: str) -> list[CodeSymbol]:
        """Parse source code with Python AST and index functions, classes, and imports."""
        symbols: list[CodeSymbol] = []
        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError as exc:
            logger.error(f"Syntax error indexing {file_path}: {exc}")
            return symbols

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                sym = self._parse_function_node(node, file_path, SymbolType.FUNCTION)
                symbols.append(sym)
            elif isinstance(node, ast.AsyncFunctionDef):
                sym = self._parse_function_node(node, file_path, SymbolType.ASYNC_FUNCTION)
                symbols.append(sym)
            elif isinstance(node, ast.ClassDef):
                sym = self._parse_class_node(node, file_path)
                symbols.append(sym)
                # Parse methods within class
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_sym = self._parse_function_node(
                            sub,
                            file_path,
                            SymbolType.METHOD,
                            parent_class=node.name,
                        )
                        symbols.append(method_sym)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                import_names = [alias.name for alias in node.names]
                sym = CodeSymbol(
                    name=", ".join(import_names),
                    symbol_type=SymbolType.IMPORT,
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    signature=f"import {', '.join(import_names)}",
                )
                symbols.append(sym)

        # Store in registries
        self._symbols_by_file[file_path] = symbols
        for s in symbols:
            if s.name not in self._symbols_by_name:
                self._symbols_by_name[s.name] = []
            self._symbols_by_name[s.name].append(s)

        return symbols

    def find_symbol(self, symbol_name: str) -> list[CodeSymbol]:
        """Find symbols matching exact name or substring."""
        exact = self._symbols_by_name.get(symbol_name, [])
        if exact:
            return exact

        # Substring search
        matches: list[CodeSymbol] = []
        for name, syms in self._symbols_by_name.items():
            if symbol_name.lower() in name.lower():
                matches.extend(syms)
        return matches

    def get_file_symbols(self, file_path: str) -> list[CodeSymbol]:
        """Retrieve all indexed symbols in a given file."""
        return self._symbols_by_file.get(file_path, [])

    def clear(self) -> None:
        """Reset indexed symbol cache."""
        self._symbols_by_name.clear()
        self._symbols_by_file.clear()

    def _parse_function_node(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        symbol_type: SymbolType,
        parent_class: str | None = None,
    ) -> CodeSymbol:
        """Extract metadata, signature, and docstrings from a function AST node."""
        docstring = ast.get_docstring(node) or ""
        args_list = [a.arg for a in node.args.args]
        sig = f"def {node.name}({', '.join(args_list)})"
        full_name = f"{parent_class}.{node.name}" if parent_class else node.name

        meta: dict[str, Any] = {
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
        }

        return CodeSymbol(
            name=full_name,
            symbol_type=symbol_type,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            docstring=docstring,
            signature=sig,
            metadata=meta,
        )

    def _parse_class_node(self, node: ast.ClassDef, file_path: str) -> CodeSymbol:
        """Extract metadata, bases, and docstrings from a class AST node."""
        docstring = ast.get_docstring(node) or ""
        bases = [self._get_node_name(b) for b in node.bases]
        sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"

        return CodeSymbol(
            name=node.name,
            symbol_type=SymbolType.CLASS,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            docstring=docstring,
            signature=sig,
            dependencies=bases,
        )

    def _get_decorator_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_node_name(node.value)}.{node.attr}"
        return "decorator"

    def _get_node_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_node_name(node.value)}.{node.attr}"
        return "unknown"
