import pytest

from cst_rf.core.backends import history_vba
from cst_rf.errors import CSTRFError, ErrorCode


def test_brick_template_is_structured_and_quoted() -> None:
    code = history_vba.brick(
        name="Patch",
        component="Antenna",
        material="Copper",
        x_min="-W/2",
        x_max="W/2",
        y_min=-5,
        y_max=5,
        z_min=0,
        z_max="t",
    )
    assert ' .Name ("Patch")' in code
    assert ' .Xrange ("-W/2", "W/2")' in code
    assert "AddToHistory" not in code


def test_templates_reject_raw_vba_like_values() -> None:
    with pytest.raises(CSTRFError) as caught:
        history_vba.brick(
            name='Patch" : KillCST',
            component="Antenna",
            material="Copper",
            x_min=0,
            x_max=1,
            y_min=0,
            y_max=1,
            z_min=0,
            z_max=1,
        )
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT


def test_boundary_requires_all_six_values() -> None:
    with pytest.raises(CSTRFError, match="all six"):
        history_vba.boundary(xmin="unit cell")


def test_material_boolean_and_port_templates_are_fixed() -> None:
    material = history_vba.material(name="FR4", epsilon_r=4.3)
    boolean = history_vba.boolean(
        operation="subtract", component="Antenna", target="Patch", tool="Slot"
    )
    port = history_vba.port(
        port_number=1,
        port_type="waveguide",
        orientation="ymin",
        x_min=-1,
        x_max=1,
        y_min=-2,
        y_max=0,
        z_min=0,
        z_max=1,
    )
    assert '.Name ("FR4")' in material
    assert boolean.startswith("Solid.Subtract")
    assert "With Port" in port


def test_transform_and_plane_wave_follow_documented_objects() -> None:
    transform = history_vba.translate_copy(component="Cell", name="Ring", x=10, y=20)
    excitation = history_vba.plane_wave(polarization_axis="y")
    assert '.Transform ("Shape", "Translate")' in transform
    assert ' .MultipleObjects ("True")' in transform
    assert "With PlaneWave" in excitation
    assert " .EVector (0, 1, 0)" in excitation


def test_bounded_parameter_sweep_sequence_does_not_start_solver() -> None:
    code = history_vba.parameter_sweep_sequence(
        sequence_name="CSTRFScan01", parameter_name="phi", values=[0, 10]
    )
    assert ' .AddSequence "CSTRFScan01"' in code
    assert ' .AddParameter_ArbitraryPoints "CSTRFScan01", "phi", "0; 10"' in code
    assert ' .UseDistributedComputing "False"' in code
    assert ' .StartActiveSolver "True"' in code
    assert " .Start" not in code.splitlines()


@pytest.mark.parametrize(
    ("name", "values"),
    [
        ('phi"\nShell', [0, 10]),
        ("phi", [0]),
        ("phi", [0, 0]),
        ("phi", [0, 1, 2, 3, 4]),
        ("phi", [float("nan"), 10]),
        ("phi", [float("inf"), 10]),
        ("phi", [True, 10]),
        ("phi", [1.0, 1.0 + 1e-15]),
    ],
)
def test_bounded_sweep_rejects_unsafe_or_unbounded_values(name: str, values: list[float]) -> None:
    with pytest.raises(CSTRFError) as caught:
        history_vba.parameter_sweep_sequence(
            sequence_name="CSTRFScan01", parameter_name=name, values=values
        )
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT
