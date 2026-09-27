import pytest

from cst_rf.core.backends.touchstone import render_two_port
from cst_rf.errors import CSTRFError, ErrorCode


def _channel(real: list[float], imag: list[float]) -> dict[str, object]:
    return {
        "x": [1.0, 2.0],
        "xlabel": "Frequency / THz",
        "ylabel": "S-Parameter",
        "run_id": 1,
        "real": real,
        "imag": imag,
    }


def _reference(value: float) -> dict[str, object]:
    return {
        "x": [1.0, 2.0],
        "xlabel": "Frequency / THz",
        "ylabel": "Impedance / Ohm",
        "run_id": 1,
        "real": [value, value],
        "imag": [0.0, 0.0],
    }


def test_two_port_touchstone_converts_thz_and_preserves_order() -> None:
    text, summary = render_two_port(
        {
            "S11": _channel([0.1, 0.2], [0.01, 0.02]),
            "S21": _channel([0.3, 0.4], [0.03, 0.04]),
            "S12": _channel([0.5, 0.6], [0.05, 0.06]),
            "S22": _channel([0.7, 0.8], [0.07, 0.08]),
        },
        (_reference(376.730313667), _reference(376.730313667)),
    )
    lines = text.splitlines()
    assert lines[2] == "# GHz S RI R 376.730313667"
    assert lines[3].split() == ["1000", "0.1", "0.01", "0.3", "0.03", "0.5", "0.05", "0.7", "0.07"]
    assert summary["points"] == 2
    assert summary["source_frequency_unit"] == "thz"


def test_touchstone_refuses_unequal_reference_impedance() -> None:
    channels = {key: _channel([0.1, 0.2], [0.0, 0.0]) for key in ("S11", "S21", "S12", "S22")}
    with pytest.raises(CSTRFError) as caught:
        render_two_port(channels, (_reference(50.0), _reference(75.0)))
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT


def test_touchstone_accepts_reference_axis_rounding_but_not_different_grid() -> None:
    channels = {key: _channel([0.1, 0.2], [0.0, 0.0]) for key in ("S11", "S21", "S12", "S22")}
    reference = _reference(376.73)
    reference["x"] = [1.0000000000000002, 2.0]
    render_two_port(channels, (reference, _reference(376.73)))
    reference["x"] = [1.0001, 2.0]
    with pytest.raises(CSTRFError, match="axes"):
        render_two_port(channels, (reference, _reference(376.73)))
