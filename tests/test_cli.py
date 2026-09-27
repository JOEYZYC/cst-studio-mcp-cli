import json

import pytest

from cst_rf.frontends.cli import _parser, main


def test_cli_status_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", "status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["operation"] == "inspect_status"


def test_cli_parameter_rebuild_is_opt_in_and_confirmation_gated() -> None:
    args = _parser().parse_args(
        ["common", "set-parameter", "--name", "theta", "--value", "1", "--rebuild", "--confirm"]
    )
    assert (args.name, args.value, args.rebuild, args.confirm) == ("theta", "1", True, True)
    defaults = _parser().parse_args(["common", "set-parameter", "--name", "theta", "--value", "1"])
    assert defaults.rebuild is False
    assert defaults.confirm is False


def test_cli_save_project_requires_confirmation_flag() -> None:
    assert _parser().parse_args(["common", "save-project"]).confirm is False
    assert _parser().parse_args(["common", "save-project", "--confirm"]).confirm is True


def test_cli_incidence_angle_requires_explicit_confirmation() -> None:
    args = _parser().parse_args(
        [
            "metasurface",
            "set-incidence-angle",
            "--theta-deg",
            "5",
            "--phi-deg",
            "10",
            "--confirm",
            "--json",
        ]
    )
    assert (args.theta_deg, args.phi_deg, args.confirm) == (5.0, 10.0, True)


def test_cli_floquet_polarization_basis_requires_confirmation() -> None:
    args = _parser().parse_args(
        ["metasurface", "set-polarization-basis", "--basis", "circular", "--confirm"]
    )
    assert (args.basis, args.confirm) == ("circular", True)


def test_cli_abandon_unknown_requires_confirm_and_fingerprints() -> None:
    args = _parser().parse_args(
        [
            "solve",
            "abandon-unknown",
            "--expected-project-path",
            "working.cst",
            "--job-id",
            "a" * 32,
            "--expected-project-sha256",
            "b" * 64,
            "--backup-project-path",
            "backup.cst",
            "--expected-backup-sha256",
            "c" * 64,
        ]
    )
    assert args.confirm is False
    assert (args.job_id, args.expected_project_sha256, args.expected_backup_sha256) == (
        "a" * 32,
        "b" * 64,
        "c" * 64,
    )


def test_cli_lists_registry(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["tools", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {tool["name"] for tool in payload["tools"]} == {
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
