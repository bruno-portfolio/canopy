from __future__ import annotations

import ast
import sys
import warnings
from pathlib import Path

from canopy.collectors import RawImportEdge

_STDLIB_MODULES: frozenset[str] = (
    sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else frozenset()
)


def _discover_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _file_to_module(file: Path, root: Path) -> str:
    relative = file.relative_to(root)
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_import(
    node: ast.Import | ast.ImportFrom,
    package: str,
    pkg_name: str,
) -> list[str]:
    targets: list[str] = []

    if isinstance(node, ast.Import):
        for alias in node.names:
            targets.append(alias.name)
        return targets

    if node.level == 0:
        if node.module:
            targets.append(node.module)
        return targets

    package_parts = package.split(".") if package else []
    base_parts = package_parts[: len(package_parts) - (node.level - 1)]
    base = ".".join(base_parts)

    if node.module:
        target = f"{base}.{node.module}" if base else node.module
        targets.append(target)
    else:
        for alias in node.names:
            target = f"{base}.{alias.name}" if base else alias.name
            targets.append(target)

    return targets


def _extract_imports_from_file(
    file: Path,
    root: Path,
    root_package: str,
) -> list[RawImportEdge]:
    source_module = _file_to_module(file, root)
    full_module = f"{root_package}.{source_module}" if source_module else root_package

    is_init = file.name == "__init__.py"
    if is_init:
        package = full_module
    else:
        parts = full_module.rsplit(".", 1)
        package = parts[0] if len(parts) > 1 else ""

    try:
        source_code = file.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=str(file))
    except (SyntaxError, UnicodeDecodeError) as exc:
        warnings.warn(f"Skipping {file}: {exc}", stacklevel=2)
        return []

    edges: list[RawImportEdge] = []
    seen: set[tuple[str, str]] = set()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue

        targets = _resolve_import(node, package, root_package)

        for target in targets:
            top_level = target.split(".")[0]

            if top_level in _STDLIB_MODULES:
                continue
            if top_level != root_package:
                continue

            if full_module == target:
                continue

            key = (source_module, target)
            if key not in seen:
                seen.add(key)
                edges.append(
                    RawImportEdge(
                        source_module=source_module,
                        target_module=target,
                    )
                )

    return edges


def collect_imports(source_path: str) -> list[RawImportEdge]:
    root = Path(source_path)
    if not root.is_dir():
        return []

    root_package = root.name
    files = _discover_py_files(root)

    all_edges: list[RawImportEdge] = []
    for file in files:
        all_edges.extend(_extract_imports_from_file(file, root, root_package))

    return all_edges
