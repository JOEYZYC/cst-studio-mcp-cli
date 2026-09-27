from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_initialize_list_and_call(tmp_path: Path) -> None:
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    env = dict(os.environ)
    env.update(
        {
            "CST_CONNECT_MODE": "manual",
            "CST_AUTO_LAUNCH": "0",
            "CST_WORK_DIR": str(tmp_path / "work"),
            "CST_RF_TEST_STDOUT_CONTAMINATION": "1",
        }
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cst_rf.frontends.mcp_server"],
        env=env,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.name == "cst-rf"
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "common_prepare_scratch",
                "common_add_monitor",
                "common_add_port",
                "common_assign_material",
                "common_boolean",
                "common_create_primitive",
                "common_define_material",
                "common_set_boundary",
                "common_set_frequency_range",
                "common_set_parameter",
                "common_save_project",
                "antenna_plan_patch",
                "antenna_create_patch",
                "antenna_plan_patch",
                "export_csv",
                "export_report",
                "export_touchstone",
                "export_metasurface_report",
                "inspect_list_instances",
                "inspect_connect",
                "inspect_disconnect",
                "inspect_project_info",
                "inspect_model_tree",
                "inspect_list_parameters",
                "inspect_floquet_info",
                "inspect_list_boundaries",
                "inspect_list_results",
                "inspect_read_saved_result",
                "inspect_search_help",
                "inspect_status",
                "metasurface_extract_rta",
                "metasurface_extract_pcr",
                "metasurface_plan_finite_array",
                "metasurface_build_finite_array",
                "metasurface_set_floquet_modes",
                "metasurface_set_incidence_angle",
                "metasurface_set_polarization_basis",
                "metasurface_plan_finite_array",
                "solve_start",
                "solve_status",
                "solve_stop",
                "solve_abandon_unknown",
            }
            result = await session.call_tool("inspect_status", {})
            assert result.isError is False
            assert result.structuredContent is not None
            assert result.structuredContent["ok"] is True
            assert result.structuredContent["operation"] == "inspect_status"

            scratch = await session.call_tool(
                "common_prepare_scratch",
                {"source_project": str(source), "operation_id": "mcp_001"},
            )
            assert scratch.isError is False
            assert scratch.structuredContent is not None
            assert scratch.structuredContent["ok"] is True
            assert Path(scratch.structuredContent["data"]["working_project"]).is_file()
