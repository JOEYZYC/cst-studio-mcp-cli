"""Shared application service for CLI and MCP."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any, Literal, cast

from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from cst_rf.config import Settings
from cst_rf.core.audit import AuditLogger
from cst_rf.core.backends import history_vba
from cst_rf.core.backends.results import ResultsBackend
from cst_rf.core.backends.touchstone import render_two_port
from cst_rf.core.help.indexer import HelpIndex
from cst_rf.core.jobs import JobStore
from cst_rf.core.locking import ProjectWriteLock
from cst_rf.core.popups import visible_cst_modals
from cst_rf.core.safety import PathPolicy, sha256_file
from cst_rf.core.scratch import prepare_scratch
from cst_rf.core.session import ManualSession
from cst_rf.core.workflows.antenna import build_patch_recipe, plan_patch
from cst_rf.core.workflows.metasurface import (
    build_finite_array_recipe,
    extract_pcr,
    extract_rta,
    plan_finite_array,
)
from cst_rf.errors import CSTRFError, ErrorCode
from cst_rf.models import ENVELOPE_SCHEMA, ResultEnvelope
from cst_rf.registry import ToolRegistry, ToolSpec

EMPTY_INPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

PREPARE_SCRATCH_INPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["source_project"],
    "properties": {
        "source_project": {"type": "string", "minLength": 1},
        "operation_id": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

LIST_RESULTS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_path"],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "module_type": {"enum": ["3d", "schematic"]},
        "filter_type": {"enum": ["0D/1D", "colormap"]},
    },
    "additionalProperties": False,
}

READ_RESULT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_path", "tree_path"],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "tree_path": {"type": "string", "minLength": 1},
        "run_id": {"type": "integer", "minimum": 0},
        "module_type": {"enum": ["3d", "schematic"]},
    },
    "additionalProperties": False,
}

NO_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

METASURFACE_RTA_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_path", "reflection_paths"],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "reflection_paths": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
        },
        "transmission_paths": {
            "type": "array",
            "items": {"type": "string"},
        },
        "transmission_zero_reason": {"type": "string", "minLength": 1},
        "run_id": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}

EXPORT_CSV_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_path", "tree_path", "artifact_name"],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "tree_path": {"type": "string", "minLength": 1},
        "artifact_name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+\\.csv$"},
        "run_id": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}

EXPORT_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_path", "tree_path", "artifact_name"],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "tree_path": {"type": "string", "minLength": 1},
        "artifact_name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+\\.html$"},
        "run_id": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}

TOUCHSTONE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_path", "channel_paths", "reference_paths", "artifact_name"],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "channel_paths": {
            "type": "object",
            "required": ["S11", "S21", "S12", "S22"],
            "properties": {
                key: {"type": "string", "minLength": 1} for key in ("S11", "S21", "S12", "S22")
            },
            "additionalProperties": False,
        },
        "reference_paths": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {"type": "string", "minLength": 1},
        },
        "artifact_name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+\\.s2p$"},
        "run_id": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}

METASURFACE_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "project_path",
        "reflection_paths",
        "co_polarized_paths",
        "cross_polarized_paths",
        "artifact_name",
    ],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "reflection_paths": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "transmission_paths": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "transmission_zero_reason": {"type": "string", "minLength": 1},
        "co_polarized_paths": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "cross_polarized_paths": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "artifact_name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+\\.html$"},
        "run_id": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}

PATCH_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["frequency_ghz", "epsilon_r", "substrate_height_mm"],
    "properties": {
        "frequency_ghz": {"type": "number", "exclusiveMinimum": 0},
        "epsilon_r": {"type": "number", "exclusiveMinimum": 1},
        "substrate_height_mm": {"type": "number", "exclusiveMinimum": 0},
        "feed_type": {"enum": ["waveguide", "discrete"]},
    },
    "additionalProperties": False,
}

PATCH_CREATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["frequency_ghz", "epsilon_r", "substrate_height_mm", "confirm"],
    "properties": {
        "frequency_ghz": {"type": "number", "exclusiveMinimum": 0},
        "epsilon_r": {"type": "number", "exclusiveMinimum": 1},
        "substrate_height_mm": {"type": "number", "exclusiveMinimum": 0},
        "feed_type": {"enum": ["waveguide", "discrete"]},
        "conductor_thickness_mm": {"type": "number", "exclusiveMinimum": 0},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

FINITE_ARRAY_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["period_mm", "rows", "columns"],
    "properties": {
        "period_mm": {"type": "number", "exclusiveMinimum": 0},
        "rows": {"type": "integer", "minimum": 1},
        "columns": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": False,
}

FINITE_ARRAY_BUILD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["component", "source_shapes", "period_mm", "rows", "columns", "confirm"],
    "properties": {
        "component": {"type": "string", "minLength": 1},
        "source_shapes": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "period_mm": {"type": "number", "exclusiveMinimum": 0},
        "rows": {"type": "integer", "minimum": 1, "maximum": 100},
        "columns": {"type": "integer", "minimum": 1, "maximum": 100},
        "polarization_axis": {"enum": ["x", "y"]},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

SEARCH_HELP_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "additionalProperties": False,
}

LIST_INSTANCES_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

CONNECT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["expected_project_path"],
    "properties": {
        "pid": {"type": "integer", "minimum": 1},
        "expected_project_path": {"type": "string", "minLength": 1},
        "auto_open": {"type": "boolean"},
        "auto_switch": {"type": "boolean"},
    },
    "additionalProperties": False,
}

DISCONNECT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

SET_PARAMETER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "value", "confirm"],
    "properties": {
        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "value": {"type": ["string", "number"]},
        "rebuild": {"type": "boolean"},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

FLOQUET_MODES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["count", "confirm"],
    "properties": {"count": {"type": "integer", "minimum": 1}, "confirm": {"const": True}},
    "additionalProperties": False,
}

INCIDENCE_ANGLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["theta_deg", "phi_deg", "confirm"],
    "properties": {
        "theta_deg": {"type": "number", "minimum": 0, "exclusiveMaximum": 90},
        "phi_deg": {"type": "number", "minimum": 0, "exclusiveMaximum": 360},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

POLARIZATION_BASIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["basis", "confirm"],
    "properties": {
        "basis": {"enum": ["linear", "circular"]},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

HISTORY_PRIMITIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["kind", "name", "component", "material", "confirm"],
    "properties": {
        "kind": {"enum": ["brick", "cylinder"]},
        "name": {"type": "string", "minLength": 1},
        "component": {"type": "string", "minLength": 1},
        "material": {"type": "string", "minLength": 1},
        "axis": {"enum": ["x", "y", "z"]},
        "radius": {"type": ["string", "number"]},
        "x_center": {"type": ["string", "number"]},
        "y_center": {"type": ["string", "number"]},
        "x_min": {"type": ["string", "number"]},
        "x_max": {"type": ["string", "number"]},
        "y_min": {"type": ["string", "number"]},
        "y_max": {"type": ["string", "number"]},
        "z_min": {"type": ["string", "number"]},
        "z_max": {"type": ["string", "number"]},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

HISTORY_FREQUENCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["f_min", "f_max", "confirm"],
    "properties": {
        "f_min": {"type": ["string", "number"]},
        "f_max": {"type": ["string", "number"]},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

HISTORY_BOUNDARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "confirm"],
    "properties": {
        key: {"type": "string", "minLength": 1}
        for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")
    }
    | {"confirm": {"const": True}},
    "additionalProperties": False,
}

HISTORY_MONITOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "monitor_type", "frequency", "confirm"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "monitor_type": {"enum": ["e_field", "h_field", "farfield", "surface_current"]},
        "frequency": {"type": ["string", "number"]},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

HISTORY_MATERIAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "epsilon_r", "confirm"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "epsilon_r": {"type": ["string", "number"]},
        "mu_r": {"type": ["string", "number"]},
        "conductivity": {"type": ["string", "number"]},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

HISTORY_ASSIGN_MATERIAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["component", "name", "material_name", "confirm"],
    "properties": {
        "component": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "material_name": {"type": "string", "minLength": 1},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

HISTORY_BOOLEAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["operation", "component", "target", "tool", "confirm"],
    "properties": {
        "operation": {"enum": ["add", "subtract", "intersect"]},
        "component": {"type": "string", "minLength": 1},
        "target": {"type": "string", "minLength": 1},
        "tool": {"type": "string", "minLength": 1},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

HISTORY_PORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "port_number",
        "port_type",
        "orientation",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "z_min",
        "z_max",
        "confirm",
    ],
    "properties": {
        "port_number": {"type": "integer", "minimum": 1},
        "port_type": {"enum": ["waveguide", "discrete"]},
        "orientation": {"enum": ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"]},
        **{
            key: {"type": ["string", "number"]}
            for key in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
        },
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

SOLVE_CONFIRM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["confirm"],
    "properties": {"confirm": {"const": True}},
    "additionalProperties": False,
}

ABANDON_UNKNOWN_JOB_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "job_id",
        "expected_project_sha256",
        "backup_project_path",
        "expected_backup_sha256",
        "confirm",
    ],
    "properties": {
        "job_id": {"type": "string", "pattern": "^[a-fA-F0-9]{32}$"},
        "expected_project_sha256": {"type": "string", "pattern": "^[a-fA-F0-9]{64}$"},
        "backup_project_path": {"type": "string", "minLength": 1},
        "expected_backup_sha256": {"type": "string", "pattern": "^[a-fA-F0-9]{64}$"},
        "confirm": {"const": True},
    },
    "additionalProperties": False,
}

SOLVE_STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "minLength": 1},
        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
    },
    "additionalProperties": False,
}

SOLVE_STOP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["confirm"],
    "properties": {
        "confirm": {"const": True},
        "job_id": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

POLARIZATION_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["project_path", "co_polarized_paths", "cross_polarized_paths"],
    "properties": {
        "project_path": {"type": "string", "minLength": 1},
        "co_polarized_paths": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "cross_polarized_paths": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
        },
        "run_id": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}


class Service:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        results_backend: ResultsBackend | None = None,
        help_index: HelpIndex | None = None,
        session: ManualSession | None = None,
        reconcile_jobs: bool = False,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.audit = AuditLogger(self.settings.work_dir)
        self.path_policy = PathPolicy(self.settings.work_dir)
        self.results = results_backend or ResultsBackend()
        self.help = help_index or HelpIndex(self.settings.work_dir / ".cst-rf" / "help")
        self.jobs = JobStore(self.settings.work_dir)
        if reconcile_jobs:
            self.jobs.reconcile_stale()
        self.session = session or ManualSession(
            auto_launch=self.settings.auto_launch,
            auto_open_project=self.settings.auto_open_project,
            auto_switch_project=self.settings.auto_switch_project,
            auto_close_project=self.settings.auto_close_project,
            auto_close_environment=self.settings.auto_close_environment,
            auto_handle_popups=self.settings.auto_handle_popups,
            result_dialog_policy=self.settings.result_dialog_policy,
        )
        self._job_locks: dict[str, ProjectWriteLock] = {}
        self.registry = ToolRegistry()
        self.registry.add(
            ToolSpec(
                name="inspect_status",
                description="Report cst-rf configuration and offline CST library availability.",
                risk="read",
                input_schema=EMPTY_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._inspect_status,
            )
        )
        history_records: list[tuple[str, str, dict[str, Any], Any]] = [
            (
                "common_create_primitive",
                "Create one validated brick or cylinder through a fixed History template.",
                HISTORY_PRIMITIVE_SCHEMA,
                self._common_create_primitive,
            ),
            (
                "common_set_frequency_range",
                "Set the solver frequency range through a fixed History template.",
                HISTORY_FREQUENCY_SCHEMA,
                self._common_set_frequency_range,
            ),
            (
                "common_set_boundary",
                "Set all six boundaries through a fixed History template.",
                HISTORY_BOUNDARY_SCHEMA,
                self._common_set_boundary,
            ),
            (
                "common_add_monitor",
                "Add a monitor through a fixed History template.",
                HISTORY_MONITOR_SCHEMA,
                self._common_add_monitor,
            ),
            (
                "common_define_material",
                "Define a material through a fixed History template.",
                HISTORY_MATERIAL_SCHEMA,
                self._common_define_material,
            ),
            (
                "common_assign_material",
                "Assign a material through a fixed History template.",
                HISTORY_ASSIGN_MATERIAL_SCHEMA,
                self._common_assign_material,
            ),
            (
                "common_boolean",
                "Apply a Boolean operation through a fixed History template.",
                HISTORY_BOOLEAN_SCHEMA,
                self._common_boolean,
            ),
            (
                "common_add_port",
                "Add a port through a fixed History template.",
                HISTORY_PORT_SCHEMA,
                self._common_add_port,
            ),
        ]
        for name, description, schema, handler in history_records:
            self.registry.add(
                ToolSpec(
                    name=name,
                    description=description,
                    risk="write",
                    input_schema=schema,
                    output_schema=ENVELOPE_SCHEMA,
                    handler=handler,
                    requires_live_session=True,
                    requires_write_lock=True,
                )
            )
        self.registry.add(
            ToolSpec(
                name="antenna_create_patch",
                description="Create a validated rectangular patch antenna recipe in the attached scratch.",
                risk="write",
                input_schema=PATCH_CREATE_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._antenna_create_patch,
                requires_live_session=True,
                requires_write_lock=True,
            )
        )
        self.registry.add(
            ToolSpec(
                name="metasurface_build_finite_array",
                description="Replicate named unit-cell shapes into a finite open-boundary array.",
                risk="write",
                input_schema=FINITE_ARRAY_BUILD_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._metasurface_build_finite_array,
                requires_live_session=True,
                requires_write_lock=True,
            )
        )
        for name, description, handler in (
            (
                "inspect_project_info",
                "Read attached CST project metadata.",
                self._inspect_project_info,
            ),
            ("inspect_model_tree", "Read the attached CST model tree.", self._inspect_model_tree),
            (
                "inspect_list_parameters",
                "Read attached CST design parameters.",
                self._inspect_list_parameters,
            ),
            (
                "inspect_floquet_info",
                "Read attached Floquet port mode information.",
                self._inspect_floquet_info,
            ),
            (
                "inspect_list_boundaries",
                "Read attached CST boundary settings.",
                self._inspect_list_boundaries,
            ),
        ):
            self.registry.add(
                ToolSpec(
                    name=name,
                    description=description,
                    risk="read",
                    input_schema=NO_INPUT_SCHEMA,
                    output_schema=ENVELOPE_SCHEMA,
                    handler=handler,
                    requires_live_session=True,
                )
            )
        self.registry.add(
            ToolSpec(
                name="inspect_list_instances",
                description="List user-started CST Design Environment PIDs without starting CST.",
                risk="read",
                input_schema=LIST_INSTANCES_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._inspect_list_instances,
            )
        )
        self.registry.add(
            ToolSpec(
                name="inspect_connect",
                description="Attach to one explicit CST PID and verify one expected open project.",
                risk="read",
                input_schema=CONNECT_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._inspect_connect,
                requires_live_session=True,
            )
        )
        self.registry.add(
            ToolSpec(
                name="inspect_disconnect",
                description="Release cst-rf handles without closing CST or its projects.",
                risk="read",
                input_schema=DISCONNECT_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._inspect_disconnect,
            )
        )
        self.registry.add(
            ToolSpec(
                name="inspect_search_help",
                description="Search the local CST Online Help FTS5 index offline.",
                risk="read",
                input_schema=SEARCH_HELP_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._inspect_search_help,
            )
        )
        self.registry.add(
            ToolSpec(
                name="inspect_list_results",
                description="List saved CST result tree paths and run IDs without opening CST.",
                risk="read",
                input_schema=LIST_RESULTS_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._inspect_list_results,
            )
        )
        self.registry.add(
            ToolSpec(
                name="inspect_read_saved_result",
                description="Read one complete saved complex 1D CST result without opening CST.",
                risk="read",
                input_schema=READ_RESULT_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._inspect_read_saved_result,
            )
        )
        self.registry.add(
            ToolSpec(
                name="common_prepare_scratch",
                description="Copy a saved CST project into a new controlled scratch operation.",
                risk="write",
                input_schema=PREPARE_SCRATCH_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._common_prepare_scratch,
            )
        )
        self.registry.add(
            ToolSpec(
                name="metasurface_extract_rta",
                description="Extract R/T/A from explicit saved S-parameter channels.",
                risk="read",
                input_schema=METASURFACE_RTA_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._metasurface_extract_rta,
            )
        )
        self.registry.add(
            ToolSpec(
                name="metasurface_extract_pcr",
                description="Extract PCR and polarization-conversion metrics from explicit saved channels.",
                risk="read",
                input_schema=POLARIZATION_INPUT_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._metasurface_extract_pcr,
            )
        )
        export_records: list[tuple[str, str, dict[str, Any], Any]] = [
            (
                "export_metasurface_report",
                "Export explicit R/T/A and PCR channels to a controlled HTML artifact.",
                METASURFACE_REPORT_SCHEMA,
                self._export_metasurface_report,
            ),
            (
                "export_touchstone",
                "Export saved two-mode S parameters with verified reference impedance.",
                TOUCHSTONE_SCHEMA,
                self._export_touchstone,
            ),
            (
                "export_csv",
                "Export one saved result to a controlled CSV artifact.",
                EXPORT_CSV_SCHEMA,
                self._export_csv,
            ),
            (
                "export_report",
                "Create a minimal controlled HTML report from one saved result.",
                EXPORT_REPORT_SCHEMA,
                self._export_report,
            ),
        ]
        for name, description, schema, handler in export_records:
            self.registry.add(
                ToolSpec(
                    name=name,
                    description=description,
                    risk="export",
                    input_schema=schema,
                    output_schema=ENVELOPE_SCHEMA,
                    handler=handler,
                )
            )
        records: list[tuple[str, str, dict[str, Any], Any, str]] = [
            (
                "common_set_parameter",
                "Set one attached CST parameter.",
                SET_PARAMETER_SCHEMA,
                self._common_set_parameter,
                "write",
            ),
            (
                "common_save_project",
                "Save the confirmed attached scratch, including its results.",
                SOLVE_CONFIRM_SCHEMA,
                self._common_save_project,
                "write",
            ),
            (
                "metasurface_set_floquet_modes",
                "Set considered Floquet modes on Zmax.",
                FLOQUET_MODES_SCHEMA,
                self._metasurface_set_floquet_modes,
                "write",
            ),
            (
                "metasurface_set_incidence_angle",
                "Rebuild and verify periodic theta/phi scan angles on the scratch.",
                INCIDENCE_ANGLE_SCHEMA,
                self._metasurface_set_incidence_angle,
                "write",
            ),
            (
                "metasurface_set_polarization_basis",
                "Switch Zmax Floquet fundamental modes between linear and circular bases.",
                POLARIZATION_BASIS_SCHEMA,
                self._metasurface_set_polarization_basis,
                "write",
            ),
            (
                "solve_start",
                "Start the attached CST solver after explicit confirmation.",
                SOLVE_CONFIRM_SCHEMA,
                self._solve_start,
                "solve",
            ),
            (
                "solve_status",
                "Read attached CST solver status.",
                SOLVE_STATUS_SCHEMA,
                self._solve_status,
                "read",
            ),
            (
                "solve_stop",
                "Request stop of the attached CST solver after confirmation.",
                SOLVE_STOP_SCHEMA,
                self._solve_stop,
                "solve",
            ),
        ]
        for name, description, schema, handler, risk in records:
            self.registry.add(
                ToolSpec(
                    name=name,
                    description=description,
                    risk=cast(Literal["read", "write", "solve", "export"], risk),
                    input_schema=schema,
                    output_schema=ENVELOPE_SCHEMA,
                    handler=handler,
                    requires_live_session=True,
                    requires_write_lock=risk in {"write", "solve"},
                )
            )
        self.registry.add(
            ToolSpec(
                name="solve_abandon_unknown",
                description="Explicitly abandon one unknown solver job after idle CST and backup verification; never mark it successful.",
                risk="write",
                input_schema=ABANDON_UNKNOWN_JOB_SCHEMA,
                output_schema=ENVELOPE_SCHEMA,
                handler=self._solve_abandon_unknown,
                requires_live_session=True,
                requires_write_lock=False,  # custom lock; the unknown-job guard must not block resolution
            )
        )
        plan_records: list[tuple[str, str, dict[str, Any], Any]] = [
            (
                "antenna_plan_patch",
                "Plan a patch antenna without touching CST.",
                PATCH_PLAN_SCHEMA,
                self._antenna_plan_patch,
            ),
            (
                "metasurface_plan_finite_array",
                "Plan a finite array without touching CST.",
                FINITE_ARRAY_PLAN_SCHEMA,
                self._metasurface_plan_finite_array,
            ),
        ]
        for name, description, schema, handler in plan_records:
            self.registry.add(
                ToolSpec(
                    name=name,
                    description=description,
                    risk="read",
                    input_schema=schema,
                    output_schema=ENVELOPE_SCHEMA,
                    handler=handler,
                )
            )

    def call(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        spec = self.registry.get(name)
        if spec is None:
            return self._error(name, ErrorCode.TOOL_NOT_FOUND, f"unknown tool: {name}")
        payload = dict(arguments or {})
        try:
            Draft202012Validator(spec.input_schema).validate(payload)
            if spec.risk != "read":
                self.audit.write("tool.begin", tool=name, arguments=payload)
            transient_lock: ProjectWriteLock | None = None
            if spec.requires_write_lock and name not in {"solve_start", "solve_stop"}:
                project = self.session.inspect_project()
                project_path = project.get("project_path")
                if not project_path:
                    raise CSTRFError(
                        ErrorCode.SESSION_NOT_ATTACHED, "attached project path is unavailable"
                    )
                confined_project = self._controlled_working_project(Path(str(project_path)))
                self._require_no_unresolved_solver_job(confined_project)
                transient_lock = ProjectWriteLock(
                    self.settings.work_dir / ".cst-rf" / "locks", confined_project
                )
                transient_lock.acquire()
            try:
                result = spec.handler(payload)
            finally:
                if transient_lock is not None:
                    transient_lock.release()
            Draft202012Validator(spec.output_schema).validate(result)
            if spec.risk != "read":
                self.audit.write(
                    "tool.end",
                    tool=name,
                    ok=result["ok"],
                    operation_id=result["operation_id"],
                )
            return result
        except ValidationError as exc:
            return self._error(
                name,
                ErrorCode.INVALID_ARGUMENT,
                exc.message,
                details={"path": [str(item) for item in exc.absolute_path]},
            )
        except CSTRFError as exc:
            return self._error(name, exc.code, str(exc), details=exc.details)
        except Exception as exc:  # frontends must receive a stable envelope
            return self._error(name, ErrorCode.INTERNAL_ERROR, str(exc))

    def _inspect_status(self, _: Mapping[str, Any]) -> dict[str, Any]:
        python_package_visible = importlib.util.find_spec("cst") is not None
        settings = self.settings
        return ResultEnvelope(
            operation="inspect_status",
            data={
                "connect_mode": settings.connect_mode,
                "auto_launch": settings.auto_launch,
                "toolset": settings.toolset,
                "allow_high_risk": settings.allow_high_risk,
                "auto_open_project": settings.auto_open_project,
                "auto_switch_project": settings.auto_switch_project,
                "auto_close_project": settings.auto_close_project,
                "auto_close_environment": settings.auto_close_environment,
                "auto_handle_popups": settings.auto_handle_popups,
                "result_dialog_policy": settings.result_dialog_policy,
                "cst_path": str(settings.cst_path),
                "cst_path_exists": settings.cst_path.is_dir(),
                "python_lib_path": str(settings.python_lib_path),
                "python_lib_path_exists": settings.python_lib_path.is_dir(),
                "cst_package_visible": python_package_visible,
                "work_dir": str(settings.work_dir),
                "work_dir_exists": settings.work_dir.is_dir(),
                "registered_tools": [spec.name for spec in self.registry.list()],
            },
        ).to_dict()

    def _common_prepare_scratch(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        operation_id = arguments.get("operation_id")
        scratch = prepare_scratch(
            str(arguments["source_project"]),
            self.settings.work_dir,
            operation_id=str(operation_id) if operation_id is not None else None,
        )
        return ResultEnvelope(
            operation="common_prepare_scratch",
            project_fingerprint=f"sha256:{scratch.source_sha256}",
            data={
                "operation_id": scratch.operation_id,
                "operation_dir": str(scratch.operation_dir),
                "source_project": str(scratch.source_project),
                "source_sha256": scratch.source_sha256,
                "working_project": str(scratch.working_project),
                "requires_user_open": True,
            },
        ).to_dict()

    def _inspect_list_results(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        data = self.results.list_results(
            str(arguments["project_path"]),
            module_type=str(arguments.get("module_type", "3d")),
            filter_type=str(arguments.get("filter_type", "0D/1D")),
        )
        fingerprint = sha256_file(Path(str(arguments["project_path"])))
        return ResultEnvelope(
            operation="inspect_list_results",
            project_fingerprint=f"sha256:{fingerprint}",
            data=data,
        ).to_dict()

    def _inspect_read_saved_result(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        data = self.results.read_1d(
            str(arguments["project_path"]),
            str(arguments["tree_path"]),
            run_id=int(arguments.get("run_id", 0)),
            module_type=str(arguments.get("module_type", "3d")),
        )
        fingerprint = sha256_file(Path(str(arguments["project_path"])))
        return ResultEnvelope(
            operation="inspect_read_saved_result",
            project_fingerprint=f"sha256:{fingerprint}",
            data=data,
        ).to_dict()

    def _inspect_search_help(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        data = {
            "query": str(arguments["query"]),
            "hits": self.help.search(
                str(arguments["query"]),
                limit=int(arguments.get("limit", 8)),
            ),
            "database": str(self.help.database),
        }
        return ResultEnvelope(operation="inspect_search_help", data=data).to_dict()

    def _metasurface_extract_rta(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        project_path = str(arguments["project_path"])
        run_id = int(arguments.get("run_id", 0))

        def read(path: str) -> dict[str, Any]:
            return self.results.read_1d(project_path, path, run_id=run_id)

        reflection = [read(str(path)) for path in arguments["reflection_paths"]]
        transmission = [read(str(path)) for path in arguments.get("transmission_paths", [])]
        data = extract_rta(
            reflection,
            transmission,
            transmission_zero_reason=(
                str(arguments["transmission_zero_reason"])
                if arguments.get("transmission_zero_reason")
                else None
            ),
        )
        fingerprint = sha256_file(Path(project_path))
        return ResultEnvelope(
            operation="metasurface_extract_rta",
            model_type="unknown",
            boundary_type="unknown",
            excitation_type="unknown",
            project_role="saved_result",
            project_fingerprint=f"sha256:{fingerprint}",
            warnings=[
                *data["warnings"],
                "classification requires independent live boundary evidence",
            ],
            provenance={
                "reflection_paths": list(arguments["reflection_paths"]),
                "transmission_paths": list(arguments.get("transmission_paths", [])),
                "run_id": run_id,
            },
            data=data,
        ).to_dict()

    def _metasurface_extract_pcr(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        project_path = str(arguments["project_path"])
        run_id = int(arguments.get("run_id", 0))

        def read(path: str) -> dict[str, Any]:
            return self.results.read_1d(project_path, path, run_id=run_id)

        data = extract_pcr(
            [read(str(path)) for path in arguments["co_polarized_paths"]],
            [read(str(path)) for path in arguments["cross_polarized_paths"]],
        )
        fingerprint = sha256_file(Path(project_path))
        return ResultEnvelope(
            operation="metasurface_extract_pcr",
            model_type="unknown",
            boundary_type="unknown",
            excitation_type="unknown",
            project_role="saved_result",
            project_fingerprint=f"sha256:{fingerprint}",
            warnings=[
                *data["warnings"],
                "classification requires independent live boundary evidence",
            ],
            provenance={
                "co_polarized_paths": list(arguments["co_polarized_paths"]),
                "cross_polarized_paths": list(arguments["cross_polarized_paths"]),
                "run_id": run_id,
            },
            data=data,
        ).to_dict()

    def _artifact_path(self, artifact_name: str, *, project_path: str | Path | None = None) -> Path:
        root = self.settings.work_dir.expanduser().resolve()
        if project_path is not None:
            source = Path(project_path).expanduser().resolve()
            if source.is_relative_to(root / "operations"):
                target = self._operation_artifact_path(source, artifact_name)
                if target.exists():
                    raise CSTRFError(
                        ErrorCode.OVERWRITE_DENIED, f"artifact already exists: {target}"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                return target
        target = (root / "exports" / artifact_name).resolve()
        if not target.is_relative_to(root):
            raise CSTRFError(ErrorCode.PATH_OUTSIDE_WORK_DIR, "artifact is outside CST_WORK_DIR")
        if target.exists():
            raise CSTRFError(ErrorCode.OVERWRITE_DENIED, f"artifact already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _controlled_working_project(self, project_path: str | Path) -> Path:
        path = self.path_policy.resolve_write(project_path)
        operations_root = (self.path_policy.root / "operations").resolve()
        if not path.is_relative_to(operations_root):
            raise CSTRFError(
                ErrorCode.PATH_OUTSIDE_WORK_DIR,
                "write requires a controlled operation working.cst",
            )
        relative = path.relative_to(operations_root)
        if len(relative.parts) != 3 or relative.parts[1:] != ("project", "working.cst"):
            raise CSTRFError(
                ErrorCode.PATH_OUTSIDE_WORK_DIR,
                "write requires a controlled operation working.cst",
            )
        return path

    def _require_no_unresolved_solver_job(self, project_path: Path) -> None:
        expected = str(project_path.resolve()).casefold()
        unresolved = [
            str(job["job_id"])
            for job in self.jobs.list_jobs()
            if job.get("kind") == "solver"
            and job.get("state") in {"queued", "starting", "running", "stopping", "unknown"}
            and job.get("project_path")
            and str(Path(str(job["project_path"])).resolve()).casefold() == expected
        ]
        if unresolved:
            raise CSTRFError(
                ErrorCode.SOLVER_BUSY,
                "unresolved solver jobs block model writes and new solves",
                details={"job_ids": unresolved},
            )

    def _operation_artifact_path(self, project_path: Path, artifact_name: str) -> Path:
        project_path = self._controlled_working_project(project_path)
        operations_root = (self.path_policy.root / "operations").resolve()
        relative = project_path.relative_to(operations_root)
        return self.path_policy.resolve_write(
            operations_root / relative.parts[0] / "artifacts" / artifact_name
        )

    def _export_touchstone(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        project_path = self.path_policy.resolve_write(str(arguments["project_path"]))
        target = self._operation_artifact_path(project_path, str(arguments["artifact_name"]))
        run_id = int(arguments.get("run_id", 0))
        paths = arguments["channel_paths"]
        channels = {
            key: self.results.read_1d(str(project_path), str(paths[key]), run_id=run_id)
            for key in ("S11", "S21", "S12", "S22")
        }
        ref_paths = arguments["reference_paths"]
        references = (
            self.results.read_1d(str(project_path), str(ref_paths[0]), run_id=run_id),
            self.results.read_1d(str(project_path), str(ref_paths[1]), run_id=run_id),
        )
        contents, summary = render_two_port(channels, references)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("x", encoding="ascii", newline="\n") as output:
                output.write(contents)
        except FileExistsError as exc:
            raise CSTRFError(
                ErrorCode.OVERWRITE_DENIED, f"artifact already exists: {target}"
            ) from exc
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return ResultEnvelope(
            operation="export_touchstone",
            model_type="unknown",
            boundary_type="unknown",
            excitation_type="unknown",
            project_role="saved_result",
            project_fingerprint=f"sha256:{sha256_file(project_path)}",
            units={"frequency": "GHz", "reference_impedance": "ohm"},
            provenance={"channel_paths": dict(paths), "reference_paths": list(ref_paths)},
            warnings=[
                "saved S channels alone do not prove model boundaries or excitation; "
                "inspect the live project before classifying this result"
            ],
            artifacts=[
                {"path": str(target), "media_type": "application/x-touchstone", "sha256": digest}
            ],
            data=summary,
        ).to_dict()

    def _export_metasurface_report(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        project_path = self.path_policy.resolve_write(str(arguments["project_path"]))
        target = self._operation_artifact_path(project_path, str(arguments["artifact_name"]))
        run_id = int(arguments.get("run_id", 0))

        def read_paths(field: str) -> list[dict[str, Any]]:
            return [
                self.results.read_1d(str(project_path), str(path), run_id=run_id)
                for path in arguments.get(field, [])
            ]

        reflection = read_paths("reflection_paths")
        transmission = read_paths("transmission_paths")
        co = read_paths("co_polarized_paths")
        cross = read_paths("cross_polarized_paths")
        channels = [*reflection, *transmission, *co, *cross]
        xlabel = str(channels[0].get("xlabel", ""))
        if not xlabel.lower().startswith("frequency / ") or any(
            str(channel.get("xlabel", "")).lower() != xlabel.lower()
            or channel.get("run_id") != run_id
            for channel in channels
        ):
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "result units or run IDs disagree")
        reason = arguments.get("transmission_zero_reason")
        rta = extract_rta(
            reflection,
            transmission,
            transmission_zero_reason=str(reason) if reason else None,
        )
        pcr = extract_pcr(co, cross)
        if rta["frequency"] != pcr["frequency"]:
            raise CSTRFError(ErrorCode.RESULT_NOT_FOUND, "R/T/A and PCR frequency axes disagree")
        valid_pcr = [(value, index) for index, value in enumerate(pcr["pcr"]) if value is not None]
        if not valid_pcr:
            raise CSTRFError(ErrorCode.RESULT_NOT_FOUND, "PCR has no valid samples to report")
        peak = max(valid_pcr)
        columns = (
            "Reflection",
            "Transmission",
            "Absorption (raw)",
            "PCR",
            "Cross-power efficiency",
        )
        rows = "".join(
            "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in values) + "</tr>"
            for values in zip(
                rta["frequency"],
                rta["reflection_power"],
                rta["transmission_power"],
                rta["absorption_raw"],
                pcr["pcr"],
                pcr["conversion_efficiency"],
            )
        )
        source_paths = {
            key: list(arguments.get(key, []))
            for key in (
                "reflection_paths",
                "transmission_paths",
                "co_polarized_paths",
                "cross_polarized_paths",
            )
        }
        contents = (
            "<!doctype html><meta charset='utf-8'><title>CST R/T/A and PCR</title>"
            "<h1>Saved R/T/A and PCR</h1>"
            f"<p>Project SHA-256: {sha256_file(project_path)}; run ID: {run_id}</p>"
            f"<p>Frequency axis: {escape(xlabel)}</p>"
            f"<p>PCR peak: {peak[0]} at {rta['frequency'][peak[1]]} ({escape(xlabel)})</p>"
            f"<p>T=0 justification (if used): {escape(str(reason) if reason else 'none')}</p>"
            "<p>Model and boundary classification require independent live inspection. "
            "Absorption values are not clamped.</p>"
            f"<p>Channels: {escape(json.dumps(source_paths, ensure_ascii=False))}</p>"
            "<table><thead><tr><th>Frequency</th>"
            + "".join(f"<th>{escape(column)}</th>" for column in columns)
            + f"</tr></thead><tbody>{rows}</tbody></table>"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("x", encoding="utf-8") as output:
                output.write(contents)
        except FileExistsError as exc:
            raise CSTRFError(
                ErrorCode.OVERWRITE_DENIED, f"artifact already exists: {target}"
            ) from exc
        return ResultEnvelope(
            operation="export_metasurface_report",
            model_type="unknown",
            boundary_type="unknown",
            excitation_type="unknown",
            project_role="saved_result",
            project_fingerprint=f"sha256:{sha256_file(project_path)}",
            units={"frequency": xlabel.partition("/")[2].strip()},
            warnings=[
                *rta["warnings"],
                *pcr["warnings"],
                "classification requires live boundary evidence",
            ],
            provenance={**source_paths, "transmission_zero_reason": reason},
            artifacts=[
                {
                    "path": str(target),
                    "media_type": "text/html",
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            ],
            data={
                "points": len(rta["frequency"]),
                "run_id": run_id,
                "pcr_max": peak[0],
                "pcr_peak_frequency": rta["frequency"][peak[1]],
            },
        ).to_dict()

    def _export_csv(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        data = self.results.read_1d(
            str(arguments["project_path"]),
            str(arguments["tree_path"]),
            run_id=int(arguments.get("run_id", 0)),
        )
        target = self._artifact_path(
            str(arguments["artifact_name"]), project_path=str(arguments["project_path"])
        )
        try:
            with target.open("x", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["x", "real", "imag", "magnitude", "magnitude_db", "phase_deg"])
                writer.writerows(
                    zip(
                        data["x"],
                        data["real"],
                        data["imag"],
                        data["magnitude"],
                        data["magnitude_db"],
                        data["phase_deg"],
                    )
                )
        except FileExistsError as exc:
            raise CSTRFError(
                ErrorCode.OVERWRITE_DENIED, f"artifact already exists: {target}"
            ) from exc
        return ResultEnvelope(
            operation="export_csv",
            project_role="saved_result",
            artifacts=[{"path": str(target), "media_type": "text/csv"}],
            data={"path": str(target), "points": len(data["x"])},
        ).to_dict()

    def _export_report(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        data = self.results.read_1d(
            str(arguments["project_path"]),
            str(arguments["tree_path"]),
            run_id=int(arguments.get("run_id", 0)),
        )
        target = self._artifact_path(
            str(arguments["artifact_name"]), project_path=str(arguments["project_path"])
        )
        rows = "".join(
            f"<tr><td>{escape(str(x))}</td><td>{escape(str(db))}</td>"
            f"<td>{escape(str(phase))}</td></tr>"
            for x, db, phase in zip(data["x"], data["magnitude_db"], data["phase_deg"])
        )
        html = (
            "<!doctype html><meta charset='utf-8'><title>CST Result</title>"
            f"<h1>{escape(str(data['title']))}</h1>"
            f"<p>Tree: {escape(str(data['tree_path']))}</p>"
            "<table><thead><tr><th>X</th><th>dB</th><th>Phase (deg)</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        try:
            with target.open("x", encoding="utf-8") as output:
                output.write(html)
        except FileExistsError as exc:
            raise CSTRFError(
                ErrorCode.OVERWRITE_DENIED, f"artifact already exists: {target}"
            ) from exc
        return ResultEnvelope(
            operation="export_report",
            project_role="saved_result",
            artifacts=[{"path": str(target), "media_type": "text/html"}],
            data={"path": str(target), "points": len(data["x"])},
        ).to_dict()

    def _antenna_plan_patch(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="antenna_plan_patch",
            data=plan_patch(
                float(arguments["frequency_ghz"]),
                float(arguments["epsilon_r"]),
                float(arguments["substrate_height_mm"]),
                feed_type=str(arguments.get("feed_type", "waveguide")),
            ),
        ).to_dict()

    def _antenna_create_patch(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        recipe = build_patch_recipe(
            float(arguments["frequency_ghz"]),
            float(arguments["epsilon_r"]),
            float(arguments["substrate_height_mm"]),
            feed_type=str(arguments.get("feed_type", "waveguide")),
            conductor_thickness_mm=float(arguments.get("conductor_thickness_mm", 0.035)),
        )
        history_code = str(recipe.pop("history_code"))
        applied = self.session.add_to_history(
            "cst-rf rectangular patch antenna",
            history_code,
            confirm=bool(arguments["confirm"]),
        )
        return ResultEnvelope(
            operation="antenna_create_patch",
            model_type="antenna",
            boundary_type="open",
            excitation_type=str(arguments.get("feed_type", "waveguide")),
            project_role="scratch",
            data={"plan": recipe, "apply": applied},
        ).to_dict()

    def _metasurface_plan_finite_array(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="metasurface_plan_finite_array",
            data=plan_finite_array(
                float(arguments["period_mm"]),
                int(arguments["rows"]),
                int(arguments["columns"]),
            ),
        ).to_dict()

    def _metasurface_build_finite_array(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        recipe = build_finite_array_recipe(
            component=str(arguments["component"]),
            source_shapes=[str(value) for value in arguments["source_shapes"]],
            period_mm=float(arguments["period_mm"]),
            rows=int(arguments["rows"]),
            columns=int(arguments["columns"]),
            polarization_axis=str(arguments.get("polarization_axis", "x")),
        )
        history_code = str(recipe.pop("history_code"))
        applied = self.session.add_to_history(
            "cst-rf finite array",
            history_code,
            confirm=bool(arguments["confirm"]),
        )
        return ResultEnvelope(
            operation="metasurface_build_finite_array",
            model_type="finite_array",
            boundary_type="open",
            excitation_type="plane_wave",
            project_role="scratch",
            data={"plan": recipe, "apply": applied},
        ).to_dict()

    def _common_set_parameter(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="common_set_parameter",
            project_role="scratch",
            data=self.session.set_parameter(
                str(arguments["name"]),
                arguments["value"],
                confirm=bool(arguments["confirm"]),
                rebuild=bool(arguments.get("rebuild", False)),
            ),
        ).to_dict()

    def _common_save_project(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        data = self.session.save_project(confirm=bool(arguments["confirm"]))
        return ResultEnvelope(
            operation="common_save_project",
            project_role="scratch",
            project_fingerprint=f"sha256:{sha256_file(Path(data['project_path']))}",
            data=data,
        ).to_dict()

    def _apply_history(self, operation: str, label: str, code: str) -> dict[str, Any]:
        return ResultEnvelope(
            operation=operation,
            project_role="scratch",
            data=self.session.add_to_history(label, code, confirm=True),
        ).to_dict()

    def _common_create_primitive(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(arguments["kind"])
        common = {
            "name": str(arguments["name"]),
            "component": str(arguments["component"]),
            "material": str(arguments["material"]),
        }
        required: tuple[str, ...]
        if kind == "brick":
            required = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
            if any(key not in arguments for key in required):
                raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "brick requires all six ranges")
            code = history_vba.brick(**common, **{key: arguments[key] for key in required})
        else:
            required = ("axis", "radius", "z_min", "z_max")
            if any(key not in arguments for key in required):
                raise CSTRFError(
                    ErrorCode.INVALID_ARGUMENT, "cylinder requires axis, radius and z ranges"
                )
            code = history_vba.cylinder(
                **common,
                axis=str(arguments["axis"]),
                radius=arguments["radius"],
                z_min=arguments["z_min"],
                z_max=arguments["z_max"],
                x_center=arguments.get("x_center", 0),
                y_center=arguments.get("y_center", 0),
            )
        return self._apply_history("common_create_primitive", f"cst-rf {kind}", code)

    def _common_set_frequency_range(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._apply_history(
            "common_set_frequency_range",
            "cst-rf frequency range",
            history_vba.frequency_range(arguments["f_min"], arguments["f_max"]),
        )

    def _common_set_boundary(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        values = {
            key: str(arguments[key]) for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")
        }
        return self._apply_history(
            "common_set_boundary", "cst-rf boundaries", history_vba.boundary(**values)
        )

    def _common_add_monitor(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._apply_history(
            "common_add_monitor",
            "cst-rf monitor",
            history_vba.monitor(
                name=str(arguments["name"]),
                monitor_type=str(arguments["monitor_type"]),
                frequency=arguments["frequency"],
            ),
        )

    def _common_define_material(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._apply_history(
            "common_define_material",
            "cst-rf material",
            history_vba.material(
                name=str(arguments["name"]),
                epsilon_r=arguments["epsilon_r"],
                mu_r=arguments.get("mu_r", 1.0),
                conductivity=arguments.get("conductivity", 0.0),
            ),
        )

    def _common_assign_material(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._apply_history(
            "common_assign_material",
            "cst-rf assign material",
            history_vba.assign_material(
                component=str(arguments["component"]),
                name=str(arguments["name"]),
                material_name=str(arguments["material_name"]),
            ),
        )

    def _common_boolean(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._apply_history(
            "common_boolean",
            "cst-rf boolean",
            history_vba.boolean(
                operation=str(arguments["operation"]),
                component=str(arguments["component"]),
                target=str(arguments["target"]),
                tool=str(arguments["tool"]),
            ),
        )

    def _common_add_port(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._apply_history(
            "common_add_port",
            "cst-rf port",
            history_vba.port(
                port_number=int(arguments["port_number"]),
                port_type=str(arguments["port_type"]),
                orientation=str(arguments["orientation"]),
                **{
                    key: arguments[key]
                    for key in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
                },
            ),
        )

    def _metasurface_set_floquet_modes(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="metasurface_set_floquet_modes",
            model_type="infinite_unit_cell",
            boundary_type="periodic|unit_cell",
            excitation_type="floquet",
            project_role="scratch",
            data=self.session.set_floquet_modes(
                int(arguments["count"]), confirm=bool(arguments["confirm"])
            ),
        ).to_dict()

    def _metasurface_set_incidence_angle(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="metasurface_set_incidence_angle",
            model_type="infinite_unit_cell",
            boundary_type="periodic|unit_cell",
            excitation_type="floquet",
            project_role="scratch",
            data=self.session.set_incidence_angle(
                float(arguments["theta_deg"]),
                float(arguments["phi_deg"]),
                confirm=bool(arguments["confirm"]),
            ),
        ).to_dict()

    def _metasurface_set_polarization_basis(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="metasurface_set_polarization_basis",
            model_type="infinite_unit_cell",
            boundary_type="periodic|unit_cell",
            excitation_type="floquet",
            project_role="scratch",
            data=self.session.set_floquet_polarization_basis(
                str(arguments["basis"]), confirm=bool(arguments["confirm"])
            ),
        ).to_dict()

    def _solve_start(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        project = self.session.inspect_project()
        project_path = str(project.get("project_path", ""))
        if not project_path:
            raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "attached project path is unavailable")
        confined_project = self._controlled_working_project(Path(project_path))
        self._require_no_unresolved_solver_job(confined_project)
        project_lock = ProjectWriteLock(
            self.settings.work_dir / ".cst-rf" / "locks", confined_project
        )
        project_lock.acquire()
        job = self.jobs.create("solver", project_path)
        self.jobs.update(job["job_id"], state="starting")
        try:
            result = self.session.start_solver(confirm=bool(arguments["confirm"]))
        except Exception as exc:
            if isinstance(exc, CSTRFError) and exc.code in {
                ErrorCode.CONFIRMATION_REQUIRED,
                ErrorCode.SOLVER_BUSY,
                ErrorCode.SESSION_NOT_ATTACHED,
            }:
                project_lock.release()
                self.jobs.update(job["job_id"], state="failed", start_error=str(exc))
            else:
                self._job_locks[str(job["job_id"])] = project_lock
                self.jobs.update(
                    job["job_id"],
                    state="unknown",
                    start_error=str(exc),
                    reconcile_reason="solver submission failed without proof that CST stayed idle",
                )
            raise
        self._job_locks[str(job["job_id"])] = project_lock
        baseline = result.get("baseline_run_info")
        current = result.get("current_run_info")
        self.jobs.update(
            job["job_id"],
            state="running" if result.get("observed_running") else "starting",
            observed_running=bool(result.get("observed_running")),
            observed_run_transition=bool(
                result.get("observed_running")
                and isinstance(current, dict)
                and current != baseline
                and str(current.get("state", "")).upper() != "SUCCESS"
            ),
            start_result=result,
        )
        return ResultEnvelope(
            operation="solve_start",
            project_role="scratch",
            solver_state="running" if result.get("observed_running") else "starting",
            data={"job_id": job["job_id"], **result},
        ).to_dict()

    def _attached_solver_job(self, job_id: str) -> dict[str, object]:
        try:
            job = self.jobs.get(job_id)
        except (FileNotFoundError, ValueError) as exc:
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, f"unknown solver job: {job_id}") from exc
        if job.get("state") in {"queued", "starting", "running", "stopping"} and job.get(
            "owner_pid"
        ) != str(os.getpid()):
            job = self.jobs.update(
                job_id,
                state="unknown",
                reconcile_reason="active solver job belongs to another or an unidentified process",
            )
        attached = self.session.inspect_project().get("project_path")
        expected = job.get("project_path")
        if (
            not attached
            or not expected
            or str(Path(str(attached)).resolve()).casefold()
            != str(Path(str(expected)).resolve()).casefold()
        ):
            raise CSTRFError(
                ErrorCode.PROJECT_IDENTITY_MISMATCH,
                "solver job belongs to a different attached project",
            )
        return job

    def _solve_abandon_unknown(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        project = self.session.inspect_project()
        path = self._controlled_working_project(Path(str(project.get("project_path", ""))))
        opened = [str(item) for item in project.get("open_projects", [])]
        if len(opened) != 1 or str(Path(opened[0]).resolve()).casefold() != str(path).casefold():
            raise CSTRFError(
                ErrorCode.PROJECT_IDENTITY_MISMATCH, "expected one attached scratch only"
            )
        operation_dir = path.parent.parent
        backup = self.path_policy.resolve_write(str(arguments["backup_project_path"]))
        if (
            backup.parent.parent != operation_dir
            or backup.parent.name == "project"
            or backup.name != "working.cst"
            or not backup.is_file()
            or not backup.with_suffix("").is_dir()
        ):
            raise CSTRFError(
                ErrorCode.INVALID_ARGUMENT,
                "backup must be a complete sibling snapshot in this operation",
            )
        expected = str(arguments["expected_project_sha256"]).lower()
        expected_backup = str(arguments["expected_backup_sha256"]).lower()
        lock = ProjectWriteLock(self.settings.work_dir / ".cst-rf" / "locks", path)
        with lock:
            job = self._attached_solver_job(str(arguments["job_id"]))
            if job.get("kind") != "solver" or job.get("state") != "unknown":
                raise CSTRFError(
                    ErrorCode.INVALID_ARGUMENT, "only an unknown solver job can be abandoned"
                )
            current_hash = sha256_file(path)
            backup_hash = sha256_file(backup)
            if current_hash != expected or backup_hash != expected_backup:
                raise CSTRFError(
                    ErrorCode.PROJECT_IDENTITY_MISMATCH, "project or backup SHA-256 changed"
                )
            first = self.session.solver_status()
            second = self.session.solver_status()
            if any(
                bool(status.get("running"))
                or str(status.get("run_info", {}).get("state", "")).upper() == "RUNNING"
                for status in (first, second)
            ):
                raise CSTRFError(ErrorCode.SOLVER_BUSY, "CST solver is not proven idle")
            updated = self.jobs.update(
                str(arguments["job_id"]),
                state="abandoned",
                disposition="user-confirmed abandonment; stop outcome and latest result remain unproven",
                abandoned_project_sha256=current_hash,
                verified_backup_sha256=backup_hash,
                idle_run_info=second.get("run_info"),
            )
            self.audit.write(
                "job.abandoned",
                job_id=arguments["job_id"],
                project_path=path,
                previous_state=job["state"],
                project_sha256=current_hash,
                backup_sha256=backup_hash,
                observed_running=False,
            )
        return ResultEnvelope(
            operation="solve_abandon_unknown",
            project_role="scratch",
            project_fingerprint=f"sha256:{current_hash}",
            solver_state="idle",
            warnings=[
                "job abandoned by explicit confirmation; neither a successful solve nor a successful stop was inferred"
            ],
            provenance={"backup_project_path": str(backup), "backup_sha256": backup_hash},
            data={
                "job_id": updated["job_id"],
                "state": "abandoned",
                "previous_state": job["state"],
                "idle_run_info": second.get("run_info"),
            },
        ).to_dict()

    def _solve_status(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        job_id = arguments.get("job_id")
        job = self._attached_solver_job(str(job_id)) if job_id else None
        status = self.session.solver_status()
        warnings: list[str] = []
        timed_out = False
        if job_id:
            assert job is not None
            if job.get("state") == "unknown":
                warnings.append("persisted job state is unknown; completion is not inferred")
                if not status["running"]:
                    lock = self._job_locks.pop(str(job_id), None)
                    if lock is not None:
                        lock.release()
                status = {**status, "state": "unknown"}
            else:
                timeout_seconds = arguments.get("timeout_seconds")
                if timeout_seconds is not None and job.get("state") in {
                    "queued",
                    "starting",
                    "running",
                    "stopping",
                }:
                    created_at = datetime.fromisoformat(str(job["created_at"]))
                    age = (datetime.now(UTC) - created_at).total_seconds()
                    if age >= float(timeout_seconds) and (
                        bool(status.get("running")) or job.get("state") in {"queued", "starting"}
                    ):
                        timed_out = True
                        warnings.append(
                            "solver status timed out; job is unknown and was not automatically retried or stopped"
                        )
                        self.jobs.update(
                            str(job_id),
                            state="unknown",
                            timeout_seconds=float(timeout_seconds),
                        )
                if timed_out:
                    pass
                elif status["running"]:
                    current = status.get("run_info")
                    start_result = job.get("start_result")
                    baseline = (
                        start_result.get("baseline_run_info")
                        if isinstance(start_result, dict)
                        else None
                    )
                    transitioned = bool(
                        isinstance(current, dict)
                        and current != baseline
                        and str(current.get("state", "")).upper() != "SUCCESS"
                    )
                    self.jobs.update(
                        str(job_id),
                        state="stopping" if job.get("state") == "stopping" else "running",
                        observed_running=True,
                        observed_run_transition=bool(job.get("observed_run_transition"))
                        or transitioned,
                    )
                    if job.get("state") == "stopping":
                        status = {**status, "state": "stopping"}
                else:
                    info = status.get("run_info")
                    run_state = str(info.get("state", "")).upper() if isinstance(info, dict) else ""
                    observed = bool(job.get("observed_running"))
                    age = (
                        datetime.now(UTC) - datetime.fromisoformat(str(job["created_at"]))
                    ).total_seconds()
                    if job.get("state") == "starting" and not observed and age < 30:
                        status = {**status, "state": "starting"}
                    elif job.get("state") == "stopping" and run_state in {
                        "ABORTED",
                        "CANCELLED",
                        "CANCELED",
                        "STOPPED",
                    }:
                        terminal_state = "stopped"
                    elif job.get("state") == "stopping":
                        terminal_state = "unknown"
                        warnings.append(
                            "abort confirmation was requested, but CST did not report an aborted final state"
                        )
                    elif observed and job.get("observed_run_transition") and run_state == "SUCCESS":
                        terminal_state = "completed"
                    elif observed and run_state in {"FAILED", "FAILURE", "ERROR"}:
                        terminal_state = "failed"
                    else:
                        terminal_state = "unknown"
                    if status["state"] != "starting":
                        self.jobs.update(str(job_id), state=terminal_state)
                        if terminal_state == "unknown":
                            warnings.append(
                                "solver is idle, but successful completion is unverified for this job"
                            )
                        lock = self._job_locks.pop(str(job_id), None)
                        if lock is not None:
                            lock.release()
                        status = {**status, "state": terminal_state}
        if timed_out:
            status = {**status, "timed_out": True, "state": "unknown"}
        return ResultEnvelope(
            operation="solve_status",
            project_role="scratch",
            solver_state=str(status.get("state", "unknown")),
            warnings=warnings,
            data=status,
        ).to_dict()

    def _solve_stop(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        job_id = arguments.get("job_id")
        attached = self.session.inspect_project()
        project = attached.get("project_path")
        if not project:
            raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "attached project path is unavailable")
        self._controlled_working_project(Path(str(project)))
        job: dict[str, object] | None = None
        if job_id:
            job = self._attached_solver_job(str(job_id))
            if job.get("start_result"):
                age = (
                    datetime.now(UTC) - datetime.fromisoformat(str(job["created_at"]))
                ).total_seconds()
                if age < 5:
                    raise CSTRFError(
                        ErrorCode.SOLVER_BUSY,
                        "solver startup is not settled; wait at least five seconds and inspect GUI",
                    )
        pid = attached.get("pid")
        if isinstance(pid, int):
            try:
                dialogs = visible_cst_modals(pid, Path(str(project)).stem)
            except Exception as exc:
                raise CSTRFError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"could not inspect CST dialogs before stopping: {exc}",
                ) from exc
            if dialogs:
                raise CSTRFError(
                    ErrorCode.POPUP_REQUIRES_INPUT,
                    "CST is waiting at a modal dialog; no abort request was sent",
                    details={"dialogs": dialogs},
                )
        if (
            job is not None
            and job.get("start_result")
            and attached.get("solver_type") == "HF Frequency Domain"
        ):
            model_log = Path(str(project)).with_suffix("") / "Result" / "Model.log"
            created_at = datetime.fromisoformat(str(job["created_at"])).timestamp()
            if not model_log.is_file() or model_log.stat().st_mtime < created_at:
                raise CSTRFError(
                    ErrorCode.SOLVER_BUSY,
                    "frequency-domain solver has not produced a log for this run; do not abort startup",
                )
        try:
            data = self.session.stop_solver(confirm=bool(arguments["confirm"]))
        except Exception as exc:
            events = exc.details.get("handled_popups") if isinstance(exc, CSTRFError) else None
            if events:
                self.audit.write(
                    "popup.handled"
                    if any(event.get("action") == "invoke_yes" for event in events)
                    else "popup.unhandled",
                    tool="solve_stop",
                    job_id=str(job_id) if job_id else None,
                    events=events,
                )
            if job_id:
                self.jobs.update(
                    str(job_id),
                    state="unknown",
                    stop_error=str(exc),
                    reconcile_reason="stop request outcome could not be verified",
                )
            if isinstance(exc, CSTRFError) and exc.code in {
                ErrorCode.POPUP_REQUIRES_INPUT,
                ErrorCode.BACKEND_UNAVAILABLE,
            }:
                raise
            raise CSTRFError(
                ErrorCode.BACKEND_UNAVAILABLE,
                "stop request outcome is unknown; inspect CST before any deliberate retry",
            ) from exc
        if data.get("handled_popups"):
            self.audit.write(
                "popup.handled",
                tool="solve_stop",
                job_id=str(job_id) if job_id else None,
                events=data["handled_popups"],
            )
        if job_id:
            self.jobs.update(str(job_id), state="stopping")
            data = {"job_id": str(job_id), **data}
        return ResultEnvelope(
            operation="solve_stop",
            project_role="scratch",
            data=data,
        ).to_dict()

    def _inspect_list_instances(self, _: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="inspect_list_instances",
            data={"pids": self.session.list_instances()},
        ).to_dict()

    def _inspect_connect(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        requested_auto = any(bool(arguments.get(key)) for key in ("auto_open", "auto_switch"))
        if requested_auto and not self.settings.allow_high_risk:
            raise CSTRFError(
                ErrorCode.AUTOMATION_NOT_ALLOWED,
                "automatic project actions require CST_ALLOW_HIGH_RISK=true",
            )
        data = self.session.connect(
            int(arguments["pid"]) if arguments.get("pid") is not None else None,
            str(arguments["expected_project_path"]),
            auto_open=arguments.get("auto_open"),
            auto_switch=arguments.get("auto_switch"),
        )
        return ResultEnvelope(
            operation="inspect_connect",
            project_role="scratch",
            data=data,
        ).to_dict()

    def _inspect_disconnect(self, _: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="inspect_disconnect",
            data=self.session.disconnect(),
        ).to_dict()

    def _inspect_project_info(self, _: Mapping[str, Any]) -> dict[str, Any]:
        data = self.session.inspect_project()
        try:
            boundaries = self.session.boundaries()
            floquet = self.session.floquet_info()
            periodic = all(
                boundaries.get(name) in {"unit cell", "periodic"}
                for name in ("Xmin", "Xmax", "Ymin", "Ymax")
            )
            if periodic and floquet.get("IsPortAtZmax"):
                model_type = "infinite_unit_cell"
                boundary_type = "periodic|unit_cell"
                excitation_type = "floquet"
                data["model_classification"] = {
                    "model_type": model_type,
                    "boundary_type": boundary_type,
                    "excitation_type": excitation_type,
                    "boundary": boundaries,
                    "floquet": floquet,
                }
            else:
                model_type = "unknown"
                boundary_type = "unknown"
                excitation_type = "unknown"
        except Exception as exc:
            model_type = "unknown"
            boundary_type = "unknown"
            excitation_type = "unknown"
            data["classification_error"] = str(exc)
        return ResultEnvelope(
            operation="inspect_project_info",
            model_type=model_type,
            boundary_type=boundary_type,
            excitation_type=excitation_type,
            project_role="scratch",
            data=data,
        ).to_dict()

    def _inspect_model_tree(self, _: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="inspect_model_tree",
            project_role="scratch",
            data={"items": self.session.model_tree()},
        ).to_dict()

    def _inspect_list_parameters(self, _: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="inspect_list_parameters",
            project_role="scratch",
            data={"parameters": self.session.parameters()},
        ).to_dict()

    def _inspect_floquet_info(self, _: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="inspect_floquet_info",
            project_role="scratch",
            data=self.session.floquet_info(),
        ).to_dict()

    def _inspect_list_boundaries(self, _: Mapping[str, Any]) -> dict[str, Any]:
        return ResultEnvelope(
            operation="inspect_list_boundaries",
            project_role="scratch",
            data=self.session.boundaries(),
        ).to_dict()

    @staticmethod
    def _error(
        operation: str,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return ResultEnvelope(
            operation=operation,
            ok=False,
            error={
                "code": code.value,
                "message": message,
                "details": details or {},
            },
        ).to_dict()
