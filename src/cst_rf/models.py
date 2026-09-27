"""Wire-level result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class ResultEnvelope:
    operation: str
    ok: bool = True
    model_type: str = "unknown"
    boundary_type: str = "unknown"
    excitation_type: str = "unknown"
    project_role: str = "unknown"
    project_fingerprint: str | None = None
    cst_version: str = "2026.2"
    solver_state: str = "unknown"
    units: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "ok": self.ok,
            "operation_id": self.operation_id,
            "timestamp_utc": self.timestamp_utc,
            "operation": self.operation,
            "model_type": self.model_type,
            "boundary_type": self.boundary_type,
            "excitation_type": self.excitation_type,
            "project_role": self.project_role,
            "project_fingerprint": self.project_fingerprint,
            "cst_version": self.cst_version,
            "solver_state": self.solver_state,
            "units": self.units,
            "warnings": self.warnings,
            "provenance": self.provenance,
            "artifacts": self.artifacts,
            "data": self.data,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


ENVELOPE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "ok",
        "operation_id",
        "timestamp_utc",
        "operation",
        "model_type",
        "boundary_type",
        "excitation_type",
        "project_role",
        "cst_version",
        "solver_state",
        "units",
        "warnings",
        "provenance",
        "artifacts",
        "data",
    ],
    "properties": {
        "schema_version": {"const": "1.0"},
        "ok": {"type": "boolean"},
        "operation_id": {"type": "string", "minLength": 1},
        "timestamp_utc": {"type": "string", "minLength": 1},
        "operation": {"type": "string", "minLength": 1},
        "model_type": {"type": "string"},
        "boundary_type": {"type": "string"},
        "excitation_type": {"type": "string"},
        "project_role": {"type": "string"},
        "project_fingerprint": {"type": ["string", "null"]},
        "cst_version": {"type": "string"},
        "solver_state": {"type": "string"},
        "units": {"type": "object"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "provenance": {"type": "object"},
        "artifacts": {"type": "array"},
        "data": {"type": "object"},
        "error": {"type": "object"},
    },
    "additionalProperties": False,
}
