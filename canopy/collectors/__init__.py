from __future__ import annotations

from dataclasses import dataclass, field


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


@dataclass(frozen=True)
class RawFunctionCC:
    name: str
    complexity: int
    is_method: bool
    classname: str
    lineno: int


@dataclass(frozen=True)
class RawRadonResult:
    path: str
    mi: float
    rank: str
    functions: list[RawFunctionCC] = field(default_factory=list)


@dataclass(frozen=True)
class RawImportEdge:
    source_module: str
    target_module: str


@dataclass(frozen=True)
class RawVultureResult:
    path: str
    lineno: int
    kind: str
    name: str
    confidence: int


@dataclass(frozen=True)
class RawChurnResult:
    path: str
    commit_count: int
