"""Single tool catalog consumed by both frontends."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

ToolHandler = Callable[[Mapping[str, Any]], dict[str, Any]]
Risk = Literal["read", "write", "solve", "export"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    risk: Risk
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: ToolHandler
    requires_live_session: bool = False
    requires_write_lock: bool = False

    def validate(self) -> None:
        if not self.name or " " in self.name:
            raise ValueError(f"invalid tool name: {self.name!r}")
        Draft202012Validator.check_schema(self.input_schema)
        Draft202012Validator.check_schema(self.output_schema)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def add(self, spec: ToolSpec) -> None:
        spec.validate()
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool name: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))
