"""Command-line frontend."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from cst_rf import __version__
from cst_rf.service import Service


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cst-rf")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    groups = parser.add_subparsers(dest="group", required=True)

    inspect_cmd = groups.add_parser("inspect")
    inspect_actions = inspect_cmd.add_subparsers(dest="action", required=True)
    status = inspect_actions.add_parser("status")
    status.add_argument("--json", action="store_true", dest="as_json")
    instances = inspect_actions.add_parser("list-instances")
    instances.add_argument("--json", action="store_true", dest="as_json")
    connect = inspect_actions.add_parser("connect")
    connect.add_argument("--pid", type=int)
    connect.add_argument("--expected-project-path", required=True)
    connect.add_argument("--auto-open", action="store_true")
    connect.add_argument("--auto-switch", action="store_true")
    connect.add_argument("--json", action="store_true", dest="as_json")
    disconnect = inspect_actions.add_parser("disconnect")
    disconnect.add_argument("--json", action="store_true", dest="as_json")
    for action in (
        "project-info",
        "model-tree",
        "list-parameters",
        "floquet-info",
        "list-boundaries",
    ):
        command = inspect_actions.add_parser(action)
        command.add_argument("--json", action="store_true", dest="as_json")
    list_results = inspect_actions.add_parser("list-results")
    list_results.add_argument("--project-path", required=True)
    list_results.add_argument("--module-type", choices=("3d", "schematic"), default="3d")
    list_results.add_argument("--filter-type", choices=("0D/1D", "colormap"), default="0D/1D")
    list_results.add_argument("--json", action="store_true", dest="as_json")
    read_result = inspect_actions.add_parser("read-saved-result")
    read_result.add_argument("--project-path", required=True)
    read_result.add_argument("--tree-path", required=True)
    read_result.add_argument("--run-id", type=int, default=0)
    read_result.add_argument("--module-type", choices=("3d", "schematic"), default="3d")
    read_result.add_argument("--json", action="store_true", dest="as_json")
    search_help = inspect_actions.add_parser("search-help")
    search_help.add_argument("--query", required=True)
    search_help.add_argument("--limit", type=int, default=8)
    search_help.add_argument("--json", action="store_true", dest="as_json")

    tools_cmd = groups.add_parser("tools")
    tools_actions = tools_cmd.add_subparsers(dest="action", required=True)
    list_cmd = tools_actions.add_parser("list")
    list_cmd.add_argument("--json", action="store_true", dest="as_json")

    common_cmd = groups.add_parser("common")
    common_actions = common_cmd.add_subparsers(dest="action", required=True)
    prepare = common_actions.add_parser("prepare-scratch")
    prepare.add_argument("--source-project", required=True)
    prepare.add_argument("--operation-id")
    prepare.add_argument("--json", action="store_true", dest="as_json")
    parameter = common_actions.add_parser("set-parameter")
    parameter.add_argument("--name", required=True)
    parameter.add_argument("--value", required=True)
    parameter.add_argument("--rebuild", action="store_true")
    parameter.add_argument("--confirm", action="store_true")
    parameter.add_argument("--json", action="store_true", dest="as_json")
    save_project = common_actions.add_parser("save-project")
    save_project.add_argument("--confirm", action="store_true")
    save_project.add_argument("--json", action="store_true", dest="as_json")
    primitive = common_actions.add_parser("create-primitive")
    primitive.add_argument("--kind", choices=("brick", "cylinder"), required=True)
    primitive.add_argument("--name", required=True)
    primitive.add_argument("--component", required=True)
    primitive.add_argument("--material", required=True)
    primitive.add_argument("--axis")
    primitive.add_argument("--radius")
    primitive.add_argument("--x-center", default=0)
    primitive.add_argument("--y-center", default=0)
    for field in ("x-min", "x-max", "y-min", "y-max", "z-min", "z-max"):
        primitive.add_argument(f"--{field}")
    primitive.add_argument("--confirm", action="store_true")
    primitive.add_argument("--json", action="store_true", dest="as_json")
    frequency = common_actions.add_parser("set-frequency-range")
    frequency.add_argument("--f-min", required=True)
    frequency.add_argument("--f-max", required=True)
    frequency.add_argument("--confirm", action="store_true")
    frequency.add_argument("--json", action="store_true", dest="as_json")
    boundary = common_actions.add_parser("set-boundary")
    for field in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"):
        boundary.add_argument(f"--{field}", required=True)
    boundary.add_argument("--confirm", action="store_true")
    boundary.add_argument("--json", action="store_true", dest="as_json")
    monitor = common_actions.add_parser("add-monitor")
    monitor.add_argument("--name", required=True)
    monitor.add_argument("--monitor-type", required=True)
    monitor.add_argument("--frequency", required=True)
    monitor.add_argument("--confirm", action="store_true")
    monitor.add_argument("--json", action="store_true", dest="as_json")

    metasurface_cmd = groups.add_parser("metasurface")
    metasurface_actions = metasurface_cmd.add_subparsers(dest="action", required=True)
    rta = metasurface_actions.add_parser("extract-rta")
    rta.add_argument("--project-path", required=True)
    rta.add_argument("--reflection-path", action="append", required=True)
    rta.add_argument("--transmission-path", action="append", default=[])
    rta.add_argument("--transmission-zero-reason")
    rta.add_argument("--run-id", type=int, default=0)
    rta.add_argument("--json", action="store_true", dest="as_json")
    pcr = metasurface_actions.add_parser("extract-pcr")
    pcr.add_argument("--project-path", required=True)
    pcr.add_argument("--co-polarized-path", action="append", required=True)
    pcr.add_argument("--cross-polarized-path", action="append", required=True)
    pcr.add_argument("--run-id", type=int, default=0)
    pcr.add_argument("--json", action="store_true", dest="as_json")
    incidence = metasurface_actions.add_parser("set-incidence-angle")
    incidence.add_argument("--theta-deg", type=float, required=True)
    incidence.add_argument("--phi-deg", type=float, required=True)
    incidence.add_argument("--confirm", action="store_true")
    incidence.add_argument("--json", action="store_true", dest="as_json")
    polarization = metasurface_actions.add_parser("set-polarization-basis")
    polarization.add_argument("--basis", choices=("linear", "circular"), required=True)
    polarization.add_argument("--confirm", action="store_true")
    polarization.add_argument("--json", action="store_true", dest="as_json")

    export_cmd = groups.add_parser("export")
    export_actions = export_cmd.add_subparsers(dest="action", required=True)
    for action, suffix in (("csv", "csv"), ("report", "html")):
        command = export_actions.add_parser(action)
        command.add_argument("--project-path", required=True)
        command.add_argument("--tree-path", required=True)
        command.add_argument("--artifact-name", required=True)
        command.add_argument("--run-id", type=int, default=0)
        command.add_argument("--json", action="store_true", dest="as_json")
    touchstone = export_actions.add_parser("touchstone")
    touchstone.add_argument("--project-path", required=True)
    for key in ("s11", "s21", "s12", "s22"):
        touchstone.add_argument(f"--{key}", required=True)
    touchstone.add_argument("--reference-path", action="append", required=True)
    touchstone.add_argument("--artifact-name", required=True)
    touchstone.add_argument("--run-id", type=int, default=0)
    touchstone.add_argument("--json", action="store_true", dest="as_json")
    metasurface_report = export_actions.add_parser("metasurface-report")
    metasurface_report.add_argument("--project-path", required=True)
    metasurface_report.add_argument("--reflection-path", action="append", required=True)
    metasurface_report.add_argument("--transmission-path", action="append", default=[])
    metasurface_report.add_argument("--transmission-zero-reason")
    metasurface_report.add_argument("--co-polarized-path", action="append", required=True)
    metasurface_report.add_argument("--cross-polarized-path", action="append", required=True)
    metasurface_report.add_argument("--artifact-name", required=True)
    metasurface_report.add_argument("--run-id", type=int, default=0)
    metasurface_report.add_argument("--json", action="store_true", dest="as_json")

    solve_cmd = groups.add_parser("solve")
    solve_actions = solve_cmd.add_subparsers(dest="action", required=True)
    abandon = solve_actions.add_parser("abandon-unknown")
    abandon.add_argument("--expected-project-path", required=True)
    abandon.add_argument("--pid", type=int)
    abandon.add_argument("--job-id", required=True)
    abandon.add_argument("--expected-project-sha256", required=True)
    abandon.add_argument("--backup-project-path", required=True)
    abandon.add_argument("--expected-backup-sha256", required=True)
    abandon.add_argument("--confirm", action="store_true")
    abandon.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _emit(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, dict) and "ok" in payload:
        print(f"{payload.get('operation')}: {'ok' if payload.get('ok') else 'error'}")
        if payload.get("error"):
            print(payload["error"]["message"])
        return
    print(payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    service = Service()
    if args.group == "inspect" and args.action == "status":
        result = service.call("inspect_status")
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "inspect" and args.action == "list-instances":
        result = service.call("inspect_list_instances")
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "inspect" and args.action == "connect":
        connect_payload: dict[str, Any] = {"expected_project_path": args.expected_project_path}
        if args.pid is not None:
            connect_payload["pid"] = args.pid
        if args.auto_open:
            connect_payload["auto_open"] = True
        if args.auto_switch:
            connect_payload["auto_switch"] = True
        result = service.call(
            "inspect_connect",
            connect_payload,
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "inspect" and args.action == "disconnect":
        result = service.call("inspect_disconnect")
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    live_inspect_tools = {
        "project-info": "inspect_project_info",
        "model-tree": "inspect_model_tree",
        "list-parameters": "inspect_list_parameters",
        "floquet-info": "inspect_floquet_info",
        "list-boundaries": "inspect_list_boundaries",
    }
    if args.group == "inspect" and args.action in live_inspect_tools:
        result = service.call(live_inspect_tools[args.action])
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "inspect" and args.action == "list-results":
        result = service.call(
            "inspect_list_results",
            {
                "project_path": args.project_path,
                "module_type": args.module_type,
                "filter_type": args.filter_type,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "inspect" and args.action == "read-saved-result":
        result = service.call(
            "inspect_read_saved_result",
            {
                "project_path": args.project_path,
                "tree_path": args.tree_path,
                "run_id": args.run_id,
                "module_type": args.module_type,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "inspect" and args.action == "search-help":
        result = service.call(
            "inspect_search_help",
            {"query": args.query, "limit": args.limit},
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "tools" and args.action == "list":
        tools = [
            {
                "name": spec.name,
                "description": spec.description,
                "risk": spec.risk,
                "requires_live_session": spec.requires_live_session,
                "requires_write_lock": spec.requires_write_lock,
            }
            for spec in service.registry.list()
        ]
        _emit({"tools": tools}, as_json=args.as_json)
        return 0
    if args.group == "common" and args.action == "prepare-scratch":
        payload = {"source_project": args.source_project}
        if args.operation_id:
            payload["operation_id"] = args.operation_id
        result = service.call("common_prepare_scratch", payload)
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "common" and args.action == "set-parameter":
        result = service.call(
            "common_set_parameter",
            {
                "name": args.name,
                "value": args.value,
                "rebuild": args.rebuild,
                "confirm": args.confirm,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "common" and args.action == "save-project":
        result = service.call("common_save_project", {"confirm": args.confirm})
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "common" and args.action == "create-primitive":
        payload = {
            key: getattr(args, key)
            for key in (
                "kind",
                "name",
                "component",
                "material",
                "axis",
                "radius",
                "x_center",
                "y_center",
                "x_min",
                "x_max",
                "y_min",
                "y_max",
                "z_min",
                "z_max",
                "confirm",
            )
            if getattr(args, key) is not None
        }
        result = service.call("common_create_primitive", payload)
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "common" and args.action == "set-frequency-range":
        result = service.call(
            "common_set_frequency_range",
            {
                "f_min": args.f_min,
                "f_max": args.f_max,
                "confirm": args.confirm,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "common" and args.action == "set-boundary":
        result = service.call(
            "common_set_boundary",
            {key: getattr(args, key) for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")}
            | {"confirm": args.confirm},
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "common" and args.action == "add-monitor":
        result = service.call(
            "common_add_monitor",
            {
                "name": args.name,
                "monitor_type": args.monitor_type,
                "frequency": args.frequency,
                "confirm": args.confirm,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "metasurface" and args.action == "extract-rta":
        payload = {
            "project_path": args.project_path,
            "reflection_paths": args.reflection_path,
            "transmission_paths": args.transmission_path,
            "run_id": args.run_id,
        }
        if args.transmission_zero_reason is not None:
            payload["transmission_zero_reason"] = args.transmission_zero_reason
        result = service.call(
            "metasurface_extract_rta",
            payload,
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "metasurface" and args.action == "extract-pcr":
        result = service.call(
            "metasurface_extract_pcr",
            {
                "project_path": args.project_path,
                "co_polarized_paths": args.co_polarized_path,
                "cross_polarized_paths": args.cross_polarized_path,
                "run_id": args.run_id,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "metasurface" and args.action == "set-incidence-angle":
        result = service.call(
            "metasurface_set_incidence_angle",
            {
                "theta_deg": args.theta_deg,
                "phi_deg": args.phi_deg,
                "confirm": args.confirm,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "metasurface" and args.action == "set-polarization-basis":
        result = service.call(
            "metasurface_set_polarization_basis",
            {"basis": args.basis, "confirm": args.confirm},
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "export" and args.action in {"csv", "report"}:
        name = "export_csv" if args.action == "csv" else "export_report"
        result = service.call(
            name,
            {
                "project_path": args.project_path,
                "tree_path": args.tree_path,
                "artifact_name": args.artifact_name,
                "run_id": args.run_id,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "export" and args.action == "touchstone":
        result = service.call(
            "export_touchstone",
            {
                "project_path": args.project_path,
                "channel_paths": {
                    "S11": args.s11,
                    "S21": args.s21,
                    "S12": args.s12,
                    "S22": args.s22,
                },
                "reference_paths": args.reference_path,
                "artifact_name": args.artifact_name,
                "run_id": args.run_id,
            },
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "export" and args.action == "metasurface-report":
        payload = {
            "project_path": args.project_path,
            "reflection_paths": args.reflection_path,
            "transmission_paths": args.transmission_path,
            "co_polarized_paths": args.co_polarized_path,
            "cross_polarized_paths": args.cross_polarized_path,
            "artifact_name": args.artifact_name,
            "run_id": args.run_id,
        }
        if args.transmission_zero_reason is not None:
            payload["transmission_zero_reason"] = args.transmission_zero_reason
        result = service.call(
            "export_metasurface_report",
            payload,
        )
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    if args.group == "solve" and args.action == "abandon-unknown":
        if not args.confirm:
            result = service.call(
                "solve_abandon_unknown",
                {
                    "job_id": args.job_id,
                    "expected_project_sha256": args.expected_project_sha256,
                    "backup_project_path": args.backup_project_path,
                    "expected_backup_sha256": args.expected_backup_sha256,
                    "confirm": False,
                },
            )
            _emit(result, as_json=args.as_json)
            return 1
        connection: dict[str, Any] = {"expected_project_path": args.expected_project_path}
        if args.pid is not None:
            connection["pid"] = args.pid
        attached = service.call("inspect_connect", connection)
        if not attached["ok"]:
            _emit(attached, as_json=args.as_json)
            return 1
        try:
            result = service.call(
                "solve_abandon_unknown",
                {
                    "job_id": args.job_id,
                    "expected_project_sha256": args.expected_project_sha256,
                    "backup_project_path": args.backup_project_path,
                    "expected_backup_sha256": args.expected_backup_sha256,
                    "confirm": True,
                },
            )
        finally:
            service.call("inspect_disconnect")
        _emit(result, as_json=args.as_json)
        return 0 if result["ok"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
