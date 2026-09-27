from pathlib import Path
from typing import Any

from cst_rf.config import Settings
from cst_rf.core.backends.results import ResultsBackend
from cst_rf.service import Service


class Item:
    title = "S11"
    treepath = "S11"
    run_id = 1
    xlabel = "GHz"
    ylabel = "S"

    def get_xdata(self) -> list[float]:
        return [1.0, 2.0]

    def get_ydata(self) -> list[complex]:
        return [0.5 + 0j, 0.25 + 0.25j]


class Module:
    def get_result_item(self, path: str, *, run_id: int, load_impedances: bool) -> Item:
        return Item()


class Project:
    def get_3d(self) -> Module:
        return Module()


def factory(path: str, *, allow_interactive: bool) -> Project:
    return Project()


def test_export_csv_and_report(tmp_path: Path) -> None:
    project = tmp_path / "saved.cst"
    project.write_bytes(b"saved")
    service = Service(
        Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full"),
        results_backend=ResultsBackend(factory),
    )
    csv_result = service.call(
        "export_csv",
        {
            "project_path": str(project),
            "tree_path": "S11",
            "artifact_name": "s11.csv",
        },
    )
    report_result = service.call(
        "export_report",
        {
            "project_path": str(project),
            "tree_path": "S11",
            "artifact_name": "s11.html",
        },
    )
    assert csv_result["ok"] is True
    assert report_result["ok"] is True
    assert (tmp_path / "work" / "exports" / "s11.csv").is_file()
    assert (tmp_path / "work" / "exports" / "s11.html").is_file()


def test_saved_scratch_csv_and_html_stay_in_operation_artifacts(tmp_path: Path) -> None:
    work = tmp_path / "work"
    project = work / "operations" / "cell_001" / "project" / "working.cst"
    project.parent.mkdir(parents=True)
    project.write_bytes(b"saved")
    service = Service(
        Settings(tmp_path, tmp_path, work, "manual", False, "full"),
        results_backend=ResultsBackend(factory),
    )
    for tool, extension in (("export_csv", "csv"), ("export_report", "html")):
        payload = {
            "project_path": str(project),
            "tree_path": "S11",
            "artifact_name": f"result.{extension}",
            "run_id": 1,
        }
        result = service.call(tool, payload)
        assert result["ok"] is True
        assert (work / "operations" / "cell_001" / "artifacts" / f"result.{extension}").is_file()
        assert service.call(tool, payload)["error"]["code"] == "OVERWRITE_DENIED"
    assert not (work / "exports").exists()


class TwoPortResults(ResultsBackend):
    def read_1d(
        self,
        project_path: str | Path,
        tree_path: str,
        *,
        run_id: int = 0,
        module_type: str = "3d",
    ) -> dict[str, Any]:
        reference = tree_path.startswith("ZRef")
        return {
            "x": [1.0, 2.0],
            "xlabel": "Frequency / THz",
            "ylabel": "Impedance / Ohm" if reference else "S Parameter",
            "run_id": run_id,
            "real": [376.73, 376.73] if reference else [0.1, 0.2],
            "imag": [0.0, 0.0],
            "magnitude": [376.73, 376.73] if reference else [0.1, 0.2],
        }


def test_touchstone_export_is_confined_and_does_not_infer_model_type(tmp_path: Path) -> None:
    work = tmp_path / "work"
    project = work / "operations" / "cell_001" / "project" / "working.cst"
    project.parent.mkdir(parents=True)
    project.write_bytes(b"saved")
    service = Service(
        Settings(tmp_path, tmp_path, work, "manual", False, "full"),
        results_backend=TwoPortResults(),
    )
    payload = {
        "project_path": str(project),
        "channel_paths": {name: name for name in ("S11", "S21", "S12", "S22")},
        "reference_paths": ["ZRef(1)", "ZRef(2)"],
        "artifact_name": "modes.s2p",
        "run_id": 1,
    }
    result = service.call("export_touchstone", payload)
    artifact = work / "operations" / "cell_001" / "artifacts" / "modes.s2p"
    assert result["ok"] is True
    assert (result["model_type"], result["boundary_type"], result["excitation_type"]) == (
        "unknown",
        "unknown",
        "unknown",
    )
    assert result["warnings"]
    assert artifact.read_text(encoding="ascii").splitlines()[2] == "# GHz S RI R 376.73"
    assert service.call("export_touchstone", payload)["error"]["code"] == "OVERWRITE_DENIED"

    external = tmp_path / "outside.cst"
    external.write_bytes(b"saved")
    assert (
        service.call("export_touchstone", {**payload, "project_path": str(external)})["error"][
            "code"
        ]
        == "PATH_OUTSIDE_WORK_DIR"
    )


def test_metasurface_report_preserves_raw_absorption_and_escapes_evidence(tmp_path: Path) -> None:
    work = tmp_path / "work"
    project = work / "operations" / "cell_001" / "project" / "working.cst"
    project.parent.mkdir(parents=True)
    project.write_bytes(b"saved")
    service = Service(
        Settings(tmp_path, tmp_path, work, "manual", False, "full"),
        results_backend=TwoPortResults(),
    )
    payload = {
        "project_path": str(project),
        "reflection_paths": ["S11", "S21"],
        "co_polarized_paths": ["S11"],
        "cross_polarized_paths": ["S21"],
        "transmission_zero_reason": "complete PEC backplane <script>alert(1)</script>",
        "artifact_name": "rta-pcr.html",
        "run_id": 1,
    }
    result = service.call("export_metasurface_report", payload)
    assert result["ok"] is True
    assert result["model_type"] == "unknown"
    assert result["data"]["pcr_max"] == 0.5
    artifact = work / "operations" / "cell_001" / "artifacts" / "rta-pcr.html"
    html = artifact.read_text(encoding="utf-8")
    assert "0.98" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert service.call("export_metasurface_report", payload)["error"]["code"] == "OVERWRITE_DENIED"

    invalid = service.call(
        "export_metasurface_report",
        {**payload, "transmission_paths": ["S12"], "artifact_name": "invalid.html"},
    )
    assert invalid["error"]["code"] == "INVALID_ARGUMENT"
    assert not (artifact.parent / "invalid.html").exists()


def test_saved_metasurface_channels_do_not_prove_periodic_model(tmp_path: Path) -> None:
    project = tmp_path / "unclassified.cst"
    project.write_bytes(b"saved")
    service = Service(
        Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full"),
        results_backend=TwoPortResults(),
    )
    for tool, channels in (
        (
            "metasurface_extract_rta",
            {"reflection_paths": ["S11"], "transmission_paths": ["S21"]},
        ),
        (
            "metasurface_extract_pcr",
            {"co_polarized_paths": ["S11"], "cross_polarized_paths": ["S21"]},
        ),
    ):
        result = service.call(tool, {"project_path": str(project), "run_id": 1, **channels})
        assert result["ok"] is True
        assert (result["model_type"], result["boundary_type"], result["excitation_type"]) == (
            "unknown",
            "unknown",
            "unknown",
        )
        assert "classification requires independent live boundary evidence" in result["warnings"]
        assert result["provenance"]["run_id"] == 1
