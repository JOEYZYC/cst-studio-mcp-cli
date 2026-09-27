"""MCP stdio frontend."""

from __future__ import annotations

import os
import sys
from io import TextIOWrapper
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

from cst_rf.service import Service

service = Service(reconcile_jobs=True)
mcp = FastMCP("cst-rf", log_level="WARNING", json_response=True)


def inspect_status() -> dict[str, Any]:
    """Report configuration and offline CST library availability without connecting to CST."""
    return service.call("inspect_status")


def inspect_list_instances() -> dict[str, Any]:
    """List user-started CST Design Environment PIDs without starting CST."""
    return service.call("inspect_list_instances")


def inspect_connect(
    expected_project_path: str,
    pid: int | None = None,
    auto_open: bool | None = None,
    auto_switch: bool | None = None,
) -> dict[str, Any]:
    """Attach to CST and optionally open/activate the expected project."""
    arguments: dict[str, Any] = {"expected_project_path": expected_project_path}
    if pid is not None:
        arguments["pid"] = pid
    if auto_open is not None:
        arguments["auto_open"] = auto_open
    if auto_switch is not None:
        arguments["auto_switch"] = auto_switch
    return service.call(
        "inspect_connect",
        arguments,
    )


def inspect_disconnect() -> dict[str, Any]:
    """Release cst-rf handles without closing CST or its projects."""
    return service.call("inspect_disconnect")


def inspect_project_info() -> dict[str, Any]:
    """Read attached CST project metadata."""
    return service.call("inspect_project_info")


def inspect_model_tree() -> dict[str, Any]:
    """Read the attached CST model tree."""
    return service.call("inspect_model_tree")


def inspect_list_parameters() -> dict[str, Any]:
    """Read attached CST design parameters."""
    return service.call("inspect_list_parameters")


def inspect_floquet_info() -> dict[str, Any]:
    """Read attached Floquet port mode information."""
    return service.call("inspect_floquet_info")


def inspect_list_boundaries() -> dict[str, Any]:
    """Read attached CST boundary settings."""
    return service.call("inspect_list_boundaries")


def common_prepare_scratch(source_project: str, operation_id: str | None = None) -> dict[str, Any]:
    """Copy a saved CST project into a new controlled scratch operation."""
    arguments = {"source_project": source_project}
    if operation_id is not None:
        arguments["operation_id"] = operation_id
    return service.call("common_prepare_scratch", arguments)


def common_create_primitive(
    kind: str,
    name: str,
    component: str,
    material: str,
    confirm: bool = False,
    axis: str | None = None,
    radius: str | float | None = None,
    x_center: str | float = 0,
    y_center: str | float = 0,
    x_min: str | float | None = None,
    x_max: str | float | None = None,
    y_min: str | float | None = None,
    y_max: str | float | None = None,
    z_min: str | float | None = None,
    z_max: str | float | None = None,
) -> dict[str, Any]:
    """Create a brick or cylinder through a fixed History template."""
    arguments: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "component": component,
        "material": material,
        "confirm": confirm,
    }
    for key, value in {
        "axis": axis,
        "radius": radius,
        "x_center": x_center,
        "y_center": y_center,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "z_min": z_min,
        "z_max": z_max,
    }.items():
        if value is not None:
            arguments[key] = value
    return service.call("common_create_primitive", arguments)


def common_set_frequency_range(
    f_min: str | float, f_max: str | float, confirm: bool = False
) -> dict[str, Any]:
    """Set the frequency range through a fixed History template."""
    return service.call(
        "common_set_frequency_range", {"f_min": f_min, "f_max": f_max, "confirm": confirm}
    )


def common_set_boundary(
    xmin: str, xmax: str, ymin: str, ymax: str, zmin: str, zmax: str, confirm: bool = False
) -> dict[str, Any]:
    """Set all six boundaries through a fixed History template."""
    return service.call(
        "common_set_boundary",
        {
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "zmin": zmin,
            "zmax": zmax,
            "confirm": confirm,
        },
    )


def common_add_monitor(
    name: str, monitor_type: str, frequency: str | float, confirm: bool = False
) -> dict[str, Any]:
    """Add a monitor through a fixed History template."""
    return service.call(
        "common_add_monitor",
        {
            "name": name,
            "monitor_type": monitor_type,
            "frequency": frequency,
            "confirm": confirm,
        },
    )


def common_define_material(
    name: str,
    epsilon_r: str | float,
    mu_r: str | float = 1.0,
    conductivity: str | float = 0.0,
    confirm: bool = False,
) -> dict[str, Any]:
    """Define a material through a fixed History template."""
    return service.call(
        "common_define_material",
        {
            "name": name,
            "epsilon_r": epsilon_r,
            "mu_r": mu_r,
            "conductivity": conductivity,
            "confirm": confirm,
        },
    )


def common_assign_material(
    component: str, name: str, material_name: str, confirm: bool = False
) -> dict[str, Any]:
    """Assign a material through a fixed History template."""
    return service.call(
        "common_assign_material",
        {
            "component": component,
            "name": name,
            "material_name": material_name,
            "confirm": confirm,
        },
    )


def common_boolean(
    operation: str, component: str, target: str, tool: str, confirm: bool = False
) -> dict[str, Any]:
    """Apply a Boolean operation through a fixed History template."""
    return service.call(
        "common_boolean",
        {
            "operation": operation,
            "component": component,
            "target": target,
            "tool": tool,
            "confirm": confirm,
        },
    )


def common_add_port(
    port_number: int,
    port_type: str,
    orientation: str,
    x_min: str | float,
    x_max: str | float,
    y_min: str | float,
    y_max: str | float,
    z_min: str | float,
    z_max: str | float,
    confirm: bool = False,
) -> dict[str, Any]:
    """Add a port through a fixed History template."""
    return service.call(
        "common_add_port",
        {
            "port_number": port_number,
            "port_type": port_type,
            "orientation": orientation,
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "z_min": z_min,
            "z_max": z_max,
            "confirm": confirm,
        },
    )


def inspect_list_results(
    project_path: str,
    module_type: str = "3d",
    filter_type: str = "0D/1D",
) -> dict[str, Any]:
    """List saved CST result tree paths and run IDs without opening CST."""
    return service.call(
        "inspect_list_results",
        {
            "project_path": project_path,
            "module_type": module_type,
            "filter_type": filter_type,
        },
    )


def inspect_read_saved_result(
    project_path: str,
    tree_path: str,
    run_id: int = 0,
    module_type: str = "3d",
) -> dict[str, Any]:
    """Read one complete saved complex 1D CST result without opening CST."""
    return service.call(
        "inspect_read_saved_result",
        {
            "project_path": project_path,
            "tree_path": tree_path,
            "run_id": run_id,
            "module_type": module_type,
        },
    )


def inspect_search_help(query: str, limit: int = 8) -> dict[str, Any]:
    """Search the local CST Online Help FTS5 index offline."""
    return service.call("inspect_search_help", {"query": query, "limit": limit})


def metasurface_extract_rta(
    project_path: str,
    reflection_paths: list[str],
    transmission_paths: list[str] | None = None,
    transmission_zero_reason: str | None = None,
    run_id: int = 0,
) -> dict[str, Any]:
    """Extract R/T/A from explicit saved S-parameter channels."""
    payload: dict[str, Any] = {
        "project_path": project_path,
        "reflection_paths": reflection_paths,
        "transmission_paths": transmission_paths or [],
        "run_id": run_id,
    }
    if transmission_zero_reason is not None:
        payload["transmission_zero_reason"] = transmission_zero_reason
    return service.call("metasurface_extract_rta", payload)


def metasurface_extract_pcr(
    project_path: str,
    co_polarized_paths: list[str],
    cross_polarized_paths: list[str],
    run_id: int = 0,
) -> dict[str, Any]:
    """Extract PCR from explicit co- and cross-polarized saved channels."""
    return service.call(
        "metasurface_extract_pcr",
        {
            "project_path": project_path,
            "co_polarized_paths": co_polarized_paths,
            "cross_polarized_paths": cross_polarized_paths,
            "run_id": run_id,
        },
    )


def common_set_parameter(
    name: str, value: str | float, confirm: bool = False, rebuild: bool = False
) -> dict[str, Any]:
    """Set an attached parameter; optionally rebuild and verify its readback."""
    return service.call(
        "common_set_parameter",
        {"name": name, "value": value, "confirm": confirm, "rebuild": rebuild},
    )


def common_save_project(confirm: bool = False) -> dict[str, Any]:
    """Save the attached controlled scratch, including results, after confirmation."""
    return service.call("common_save_project", {"confirm": confirm})


def metasurface_set_floquet_modes(count: int, confirm: bool = False) -> dict[str, Any]:
    """Set considered Floquet modes on Zmax after explicit confirmation."""
    return service.call("metasurface_set_floquet_modes", {"count": count, "confirm": confirm})


def metasurface_set_incidence_angle(
    theta_deg: float, phi_deg: float, confirm: bool = False
) -> dict[str, Any]:
    """Rebuild and verify periodic Floquet scan angles after confirmation."""
    return service.call(
        "metasurface_set_incidence_angle",
        {"theta_deg": theta_deg, "phi_deg": phi_deg, "confirm": confirm},
    )


def metasurface_set_polarization_basis(basis: str, confirm: bool = False) -> dict[str, Any]:
    """Toggle and read back linear/circular Floquet modes on a periodic scratch."""
    return service.call("metasurface_set_polarization_basis", {"basis": basis, "confirm": confirm})


def solve_start(confirm: bool = False) -> dict[str, Any]:
    """Start the attached CST solver after explicit confirmation."""
    return service.call("solve_start", {"confirm": confirm})


def solve_status(job_id: str | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
    """Read attached CST solver status."""
    arguments: dict[str, Any] = {}
    if job_id is not None:
        arguments["job_id"] = job_id
    if timeout_seconds is not None:
        arguments["timeout_seconds"] = timeout_seconds
    return service.call("solve_status", arguments)


def solve_stop(confirm: bool = False, job_id: str | None = None) -> dict[str, Any]:
    """Request solver stop after explicit confirmation."""
    arguments: dict[str, Any] = {"confirm": confirm}
    if job_id is not None:
        arguments["job_id"] = job_id
    return service.call("solve_stop", arguments)


def solve_abandon_unknown(
    job_id: str,
    expected_project_sha256: str,
    backup_project_path: str,
    expected_backup_sha256: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Explicitly abandon an unknown job after checking CST is idle and a full backup exists."""
    return service.call(
        "solve_abandon_unknown",
        {
            "job_id": job_id,
            "expected_project_sha256": expected_project_sha256,
            "backup_project_path": backup_project_path,
            "expected_backup_sha256": expected_backup_sha256,
            "confirm": confirm,
        },
    )


def export_csv(
    project_path: str, tree_path: str, artifact_name: str, run_id: int = 0
) -> dict[str, Any]:
    """Export one saved result to a controlled CSV artifact."""
    return service.call(
        "export_csv",
        {
            "project_path": project_path,
            "tree_path": tree_path,
            "artifact_name": artifact_name,
            "run_id": run_id,
        },
    )


def export_report(
    project_path: str, tree_path: str, artifact_name: str, run_id: int = 0
) -> dict[str, Any]:
    """Create a minimal controlled HTML report from one saved result."""
    return service.call(
        "export_report",
        {
            "project_path": project_path,
            "tree_path": tree_path,
            "artifact_name": artifact_name,
            "run_id": run_id,
        },
    )


def export_touchstone(
    project_path: str,
    channel_paths: dict[str, str],
    reference_paths: list[str],
    artifact_name: str,
    run_id: int = 0,
) -> dict[str, Any]:
    """Export explicit saved two-mode S channels to Touchstone s2p."""
    return service.call(
        "export_touchstone",
        {
            "project_path": project_path,
            "channel_paths": channel_paths,
            "reference_paths": reference_paths,
            "artifact_name": artifact_name,
            "run_id": run_id,
        },
    )


def export_metasurface_report(
    project_path: str,
    reflection_paths: list[str],
    co_polarized_paths: list[str],
    cross_polarized_paths: list[str],
    artifact_name: str,
    transmission_paths: list[str] | None = None,
    transmission_zero_reason: str | None = None,
    run_id: int = 0,
) -> dict[str, Any]:
    """Export saved R/T/A and PCR to one controlled HTML report."""
    payload: dict[str, Any] = {
        "project_path": project_path,
        "reflection_paths": reflection_paths,
        "co_polarized_paths": co_polarized_paths,
        "cross_polarized_paths": cross_polarized_paths,
        "artifact_name": artifact_name,
        "transmission_paths": transmission_paths or [],
        "run_id": run_id,
    }
    if transmission_zero_reason is not None:
        payload["transmission_zero_reason"] = transmission_zero_reason
    return service.call("export_metasurface_report", payload)


def antenna_plan_patch(
    frequency_ghz: float,
    epsilon_r: float,
    substrate_height_mm: float,
    feed_type: str = "waveguide",
) -> dict[str, Any]:
    """Plan a patch antenna without touching CST."""
    return service.call(
        "antenna_plan_patch",
        {
            "frequency_ghz": frequency_ghz,
            "epsilon_r": epsilon_r,
            "substrate_height_mm": substrate_height_mm,
            "feed_type": feed_type,
        },
    )


def antenna_create_patch(
    frequency_ghz: float,
    epsilon_r: float,
    substrate_height_mm: float,
    feed_type: str = "waveguide",
    conductor_thickness_mm: float = 0.035,
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a validated rectangular patch recipe in the attached scratch."""
    return service.call(
        "antenna_create_patch",
        {
            "frequency_ghz": frequency_ghz,
            "epsilon_r": epsilon_r,
            "substrate_height_mm": substrate_height_mm,
            "feed_type": feed_type,
            "conductor_thickness_mm": conductor_thickness_mm,
            "confirm": confirm,
        },
    )


def metasurface_plan_finite_array(period_mm: float, rows: int, columns: int) -> dict[str, Any]:
    """Plan a finite array without touching CST."""
    return service.call(
        "metasurface_plan_finite_array",
        {
            "period_mm": period_mm,
            "rows": rows,
            "columns": columns,
        },
    )


def metasurface_build_finite_array(
    component: str,
    source_shapes: list[str],
    period_mm: float,
    rows: int,
    columns: int,
    polarization_axis: str = "x",
    confirm: bool = False,
) -> dict[str, Any]:
    """Build a finite open-boundary array from named unit-cell shapes."""
    return service.call(
        "metasurface_build_finite_array",
        {
            "component": component,
            "source_shapes": source_shapes,
            "period_mm": period_mm,
            "rows": rows,
            "columns": columns,
            "polarization_axis": polarization_axis,
            "confirm": confirm,
        },
    )


mcp.add_tool(
    inspect_list_instances,
    name="inspect_list_instances",
    description="List user-started CST Design Environment PIDs without starting CST.",
    structured_output=True,
)
mcp.add_tool(
    inspect_connect,
    name="inspect_connect",
    description="Attach to one explicit CST PID and verify one expected open project.",
    structured_output=True,
)
mcp.add_tool(
    inspect_disconnect,
    name="inspect_disconnect",
    description="Release cst-rf handles without closing CST or its projects.",
    structured_output=True,
)
mcp.add_tool(
    inspect_project_info,
    name="inspect_project_info",
    description="Read attached CST project metadata.",
    structured_output=True,
)
mcp.add_tool(
    inspect_model_tree,
    name="inspect_model_tree",
    description="Read the attached CST model tree.",
    structured_output=True,
)
mcp.add_tool(
    inspect_list_parameters,
    name="inspect_list_parameters",
    description="Read attached CST design parameters.",
    structured_output=True,
)
mcp.add_tool(
    inspect_floquet_info,
    name="inspect_floquet_info",
    description="Read attached Floquet port mode information.",
    structured_output=True,
)
mcp.add_tool(
    inspect_list_boundaries,
    name="inspect_list_boundaries",
    description="Read attached CST boundary settings.",
    structured_output=True,
)
mcp.add_tool(
    common_prepare_scratch,
    name="common_prepare_scratch",
    description="Copy a saved CST project into a new controlled scratch operation.",
    structured_output=True,
)
mcp.add_tool(
    inspect_list_results,
    name="inspect_list_results",
    description="List saved CST result tree paths and run IDs without opening CST.",
    structured_output=True,
)
mcp.add_tool(
    inspect_read_saved_result,
    name="inspect_read_saved_result",
    description="Read one complete saved complex 1D CST result without opening CST.",
    structured_output=True,
)
mcp.add_tool(
    inspect_search_help,
    name="inspect_search_help",
    description="Search the local CST Online Help FTS5 index offline.",
    structured_output=True,
)
mcp.add_tool(
    inspect_status,
    name="inspect_status",
    description="Report cst-rf configuration and offline CST library availability.",
    structured_output=True,
)
mcp.add_tool(
    metasurface_extract_rta,
    name="metasurface_extract_rta",
    description="Extract R/T/A from explicit saved S-parameter channels.",
    structured_output=True,
)
mcp.add_tool(
    metasurface_extract_pcr,
    name="metasurface_extract_pcr",
    description="Extract PCR from explicit co- and cross-polarized saved channels.",
    structured_output=True,
)
for function, name, description in (
    (
        common_create_primitive,
        "common_create_primitive",
        "Create a primitive through a fixed History template.",
    ),
    (
        common_set_frequency_range,
        "common_set_frequency_range",
        "Set frequency range through a fixed History template.",
    ),
    (
        common_set_boundary,
        "common_set_boundary",
        "Set boundaries through a fixed History template.",
    ),
    (common_add_monitor, "common_add_monitor", "Add a monitor through a fixed History template."),
    (
        common_define_material,
        "common_define_material",
        "Define a material through a fixed History template.",
    ),
    (
        common_assign_material,
        "common_assign_material",
        "Assign a material through a fixed History template.",
    ),
    (
        common_boolean,
        "common_boolean",
        "Apply a Boolean operation through a fixed History template.",
    ),
    (common_add_port, "common_add_port", "Add a port through a fixed History template."),
    (
        common_set_parameter,
        "common_set_parameter",
        "Set one attached CST parameter after explicit confirmation.",
    ),
    (
        common_save_project,
        "common_save_project",
        "Save the confirmed attached controlled scratch with results.",
    ),
    (
        metasurface_set_floquet_modes,
        "metasurface_set_floquet_modes",
        "Set considered Floquet modes on Zmax after explicit confirmation.",
    ),
    (
        metasurface_set_incidence_angle,
        "metasurface_set_incidence_angle",
        "Rebuild and verify periodic theta/phi scan angles after confirmation.",
    ),
    (
        metasurface_set_polarization_basis,
        "metasurface_set_polarization_basis",
        "Toggle and read back linear/circular Zmax Floquet modes after confirmation.",
    ),
    (solve_start, "solve_start", "Start the attached CST solver after explicit confirmation."),
    (solve_status, "solve_status", "Read attached CST solver status."),
    (solve_stop, "solve_stop", "Request solver stop after explicit confirmation."),
    (
        solve_abandon_unknown,
        "solve_abandon_unknown",
        "Explicitly abandon an unknown job only after live idle and backup verification.",
    ),
    (export_csv, "export_csv", "Export one saved result to a controlled CSV artifact."),
    (
        export_touchstone,
        "export_touchstone",
        "Export two saved S modes to a verified Touchstone artifact.",
    ),
    (
        export_metasurface_report,
        "export_metasurface_report",
        "Export explicit R/T/A and PCR results to a controlled HTML artifact.",
    ),
    (
        export_report,
        "export_report",
        "Create a minimal controlled HTML report from one saved result.",
    ),
    (antenna_plan_patch, "antenna_plan_patch", "Plan a patch antenna without touching CST."),
    (
        antenna_create_patch,
        "antenna_create_patch",
        "Create a validated rectangular patch recipe in the attached scratch.",
    ),
    (
        metasurface_plan_finite_array,
        "metasurface_plan_finite_array",
        "Plan a finite array without touching CST.",
    ),
    (
        metasurface_build_finite_array,
        "metasurface_build_finite_array",
        "Build a finite open-boundary array from named unit-cell shapes.",
    ),
):
    mcp.add_tool(function, name=name, description=description, structured_output=True)


async def _run_stdio() -> None:
    """Reserve the original stdout for JSON-RPC and redirect all other writes."""
    protocol_fd = os.dup(sys.stdout.fileno())
    protocol_binary = os.fdopen(protocol_fd, "wb", closefd=True)
    protocol_text = TextIOWrapper(protocol_binary, encoding="utf-8", write_through=True)

    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr

    if os.environ.get("CST_RF_TEST_STDOUT_CONTAMINATION") == "1":
        print("python stdout contamination probe")
        os.write(1, b"native stdout contamination probe\n")

    protocol_stdout = anyio.wrap_file(protocol_text)
    try:
        async with stdio_server(stdout=protocol_stdout) as (read_stream, write_stream):
            await mcp._mcp_server.run(  # noqa: SLF001 - pinned SDK, custom safe stdio
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),  # noqa: SLF001
            )
    finally:
        await protocol_stdout.aclose()


def main() -> None:
    anyio.run(_run_stdio)


if __name__ == "__main__":
    main()
