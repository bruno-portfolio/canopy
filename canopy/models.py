from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Module:
    name: str
    lines: int
    funcs: int
    mi: float
    cc: float
    dead: int = 0
    churn: int = 0
    layer: str = ""
    desc: str = ""


@dataclass(frozen=True)
class Dependency:
    from_module: str
    to_module: str
    weight: float = 1.0


@dataclass(frozen=True)
class Layer:
    name: str
    ring: int
    label: str


@dataclass(frozen=True)
class ProjectData:
    modules: list[Module] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    layers: list[Layer] = field(default_factory=list)
    project_name: str = ""


@dataclass(frozen=True)
class NodePosition:
    name: str
    x: float
    y: float
    radius: float


@dataclass(frozen=True)
class RingPosition:
    layer_name: str
    radius: float
    label: str


@dataclass(frozen=True)
class LayoutResult:
    nodes: list[NodePosition] = field(default_factory=list)
    rings: list[RingPosition] = field(default_factory=list)
