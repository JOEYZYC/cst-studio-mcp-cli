from pathlib import Path
from typing import cast

from cst_rf.config import Settings
from cst_rf.core.safety import sha256_file
from cst_rf.core.session import ManualSession
from cst_rf.service import Service


def test_status_is_offline_and_structured(tmp_path: Path) -> None:
    service = Service(
        Settings(
            cst_path=tmp_path / "cst",
            python_lib_path=tmp_path / "libs",
            work_dir=tmp_path / "work",
            connect_mode="manual",
            auto_launch=False,
            toolset="full",
        )
    )
    result = service.call("inspect_status")
    assert result["ok"] is True
    assert result["operation"] == "inspect_status"
    assert result["model_type"] == "unknown"
    assert result["data"]["auto_launch"] is False
    assert set(result["data"]["registered_tools"]) == {
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
        "inspect_connect",
        "inspect_disconnect",
        "inspect_floquet_info",
        "inspect_list_boundaries",
        "inspect_list_instances",
        "inspect_list_parameters",
        "inspect_list_results",
        "inspect_model_tree",
        "inspect_project_info",
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


def test_unknown_tool_has_stable_error(tmp_path: Path) -> None:
    service = Service(
        Settings(
            cst_path=tmp_path,
            python_lib_path=tmp_path,
            work_dir=tmp_path,
            connect_mode="manual",
            auto_launch=False,
            toolset="full",
        )
    )
    result = service.call("missing")
    assert result["ok"] is False
    assert result["error"]["code"] == "TOOL_NOT_FOUND"


def test_prepare_scratch_is_dispatched_and_audited(tmp_path: Path) -> None:
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    work_dir = tmp_path / "work"
    service = Service(
        Settings(
            cst_path=tmp_path,
            python_lib_path=tmp_path,
            work_dir=work_dir,
            connect_mode="manual",
            auto_launch=False,
            toolset="full",
        )
    )

    result = service.call(
        "common_prepare_scratch",
        {"source_project": str(source), "operation_id": "service_001"},
    )

    assert result["ok"] is True
    assert Path(result["data"]["working_project"]).is_file()
    audit_files = list((work_dir / ".cst-rf" / "audit").glob("*.jsonl"))
    assert len(audit_files) == 1
    assert len(audit_files[0].read_text(encoding="utf-8").splitlines()) == 2


class OutsideProjectSession:
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def inspect_project(self) -> dict[str, str]:
        return {"project_path": str(self.project_path)}


def test_write_tools_refuse_attached_source_project_outside_work_dir(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    source = tmp_path / "source.cst"
    source.write_bytes(b"source")
    service = Service(
        Settings(tmp_path, tmp_path, work_dir, "manual", False, "full"),
        session=cast(ManualSession, OutsideProjectSession(source)),
    )

    result = service.call("common_set_parameter", {"name": "FREQ", "value": 5.0, "confirm": True})

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_WORK_DIR"


def test_downloaded_project_inside_work_dir_is_not_a_controlled_scratch(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    downloaded = work_dir / "operations" / "demo" / "downloaded.cst"
    downloaded.parent.mkdir(parents=True)
    downloaded.write_bytes(b"downloaded")
    service = Service(
        Settings(tmp_path, tmp_path, work_dir, "manual", False, "full"),
        session=cast(ManualSession, OutsideProjectSession(downloaded)),
    )

    for tool, arguments in (
        ("common_set_parameter", {"name": "FREQ", "value": 5.0, "confirm": True}),
        ("common_save_project", {"confirm": True}),
        ("metasurface_set_polarization_basis", {"basis": "circular", "confirm": True}),
        ("solve_start", {"confirm": True}),
        ("solve_stop", {"confirm": True}),
    ):
        result = service.call(tool, arguments)
        assert result["error"]["code"] == "PATH_OUTSIDE_WORK_DIR"
    assert service.jobs.list_jobs() == []


def test_incidence_angle_schema_rejects_unconfirmed_or_out_of_range(tmp_path: Path) -> None:
    service = Service(Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full"))
    for payload in (
        {"theta_deg": 5, "phi_deg": 10, "confirm": False},
        {"theta_deg": 90, "phi_deg": 10, "confirm": True},
        {"theta_deg": 5, "phi_deg": 360, "confirm": True},
    ):
        result = service.call("metasurface_set_incidence_angle", payload)
        assert result["error"]["code"] == "INVALID_ARGUMENT"


def test_unknown_solver_job_blocks_writes_and_new_solves(tmp_path: Path) -> None:
    work = tmp_path / "work"
    project = work / "operations" / "cell_001" / "project" / "working.cst"
    project.parent.mkdir(parents=True)
    project.write_bytes(b"saved")
    service = Service(
        Settings(tmp_path, tmp_path, work, "manual", False, "full"),
        session=cast(ManualSession, OutsideProjectSession(project)),
    )
    job = service.jobs.create("solver", str(project))
    service.jobs.update(job["job_id"], state="unknown")

    for tool, args in (
        ("common_set_parameter", {"name": "FREQ", "value": 5, "confirm": True}),
        ("common_save_project", {"confirm": True}),
        ("metasurface_set_polarization_basis", {"basis": "circular", "confirm": True}),
        ("solve_start", {"confirm": True}),
    ):
        result = service.call(tool, args)
        assert result["error"]["code"] == "SOLVER_BUSY"
        assert result["error"]["details"]["job_ids"] == [job["job_id"]]
    assert len(service.jobs.list_jobs()) == 1


def test_confirmed_abandonment_requires_idle_matching_backup_and_keeps_history(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    project = work / "operations" / "cell_001" / "project" / "working.cst"
    backup = work / "operations" / "cell_001" / "postsolve" / "working.cst"
    project.parent.mkdir(parents=True)
    backup.parent.mkdir(parents=True)
    backup.with_suffix("").mkdir()
    project.write_bytes(b"current")
    backup.write_bytes(b"known-good")

    class IdleProjectSession:
        running = False

        def inspect_project(self) -> dict[str, object]:
            return {"project_path": str(project), "open_projects": [str(project)]}

        def solver_status(self) -> dict[str, object]:
            return {
                "running": self.running,
                "state": "running" if self.running else "idle",
                "run_info": {"state": "RUNNING" if self.running else "SUCCESS"},
            }

        def set_parameter(
            self, name: str, value: str | float, *, confirm: bool, rebuild: bool = False
        ) -> dict[str, object]:
            return {"name": name, "value": value, "confirm": confirm, "rebuilt": rebuild}

    session = IdleProjectSession()
    service = Service(
        Settings(tmp_path, tmp_path, work, "manual", False, "full"),
        session=cast(ManualSession, session),
    )
    job = service.jobs.create("solver", str(project))
    service.jobs.update(job["job_id"], state="unknown")
    payload = {
        "job_id": job["job_id"],
        "expected_project_sha256": sha256_file(project),
        "backup_project_path": str(backup),
        "expected_backup_sha256": sha256_file(backup),
        "confirm": True,
    }
    assert (
        service.call("solve_abandon_unknown", {**payload, "confirm": False})["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert (
        service.call("solve_abandon_unknown", {**payload, "expected_project_sha256": "0" * 64})[
            "error"
        ]["code"]
        == "PROJECT_IDENTITY_MISMATCH"
    )
    session.running = True
    assert service.call("solve_abandon_unknown", payload)["error"]["code"] == "SOLVER_BUSY"
    session.running = False

    resolved = service.call("solve_abandon_unknown", payload)

    assert resolved["ok"] is True
    assert resolved["data"]["state"] == "abandoned"
    assert service.jobs.get(job["job_id"])["state"] == "abandoned"
    audit_files = list((work / ".cst-rf" / "audit").glob("*.jsonl"))
    assert any(
        '"event": "job.abandoned"' in path.read_text(encoding="utf-8") for path in audit_files
    )
    assert service.call("common_set_parameter", {"name": "theta", "value": 0, "confirm": True})[
        "ok"
    ]
    assert service.call("solve_abandon_unknown", payload)["error"]["code"] == "INVALID_ARGUMENT"
