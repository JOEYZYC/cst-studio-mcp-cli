from collections.abc import Callable
from typing import Any

import pytest

from cst_rf.core.workflows.metasurface import extract_pcr, extract_rta
from cst_rf.errors import CSTRFError, ErrorCode


def _result(values: list[float]) -> dict[str, object]:
    return {"x": [1.0, 2.0], "magnitude": values}


def test_extract_rta_uses_explicit_channels() -> None:
    result = extract_rta(
        [_result([0.5, 0.25])],
        [_result([0.25, 0.25])],
    )
    assert result["reflection_power"] == [0.25, 0.0625]
    assert result["transmission_power"] == [0.0625, 0.0625]
    assert result["absorption_raw"] == pytest.approx([0.6875, 0.875])


def test_extract_rta_refuses_implicit_zero_transmission() -> None:
    with pytest.raises(CSTRFError) as caught:
        extract_rta([_result([0.5, 0.5])], [])
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT


def test_extract_rta_allows_explicit_full_backplane_assumption() -> None:
    result = extract_rta(
        [_result([0.5, 0.25])],
        transmission_zero_reason="complete PEC backplane; T is physically zero",
    )
    assert result["transmission_power"] == [0.0, 0.0]
    assert result["transmission_assumption"].startswith("complete PEC")
    assert any("user-asserted" in warning for warning in result["warnings"])


def test_extract_rta_rejects_measured_transmission_with_zero_assumption() -> None:
    with pytest.raises(CSTRFError) as caught:
        extract_rta(
            [_result([0.5, 0.25])],
            [_result([0.25, 0.25])],
            transmission_zero_reason="complete backplane",
        )
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT


def test_extract_pcr_uses_cross_power_over_total_polarized_power() -> None:
    result = extract_pcr(
        [_result([0.8, 0.4])],
        [_result([0.6, 0.2])],
    )
    assert result["co_polarized_power"] == pytest.approx([0.64, 0.16])
    assert result["cross_polarized_power"] == pytest.approx([0.36, 0.04])
    assert result["pcr"] == pytest.approx([0.36, 0.2])
    assert result["conversion_efficiency"] == pytest.approx([0.36, 0.04])


@pytest.mark.parametrize("extractor", [extract_rta, extract_pcr])
@pytest.mark.parametrize(
    "altered",
    [
        {"magnitude": [0.5]},
        {"magnitude": [0.5, float("inf")]},
        {"x": [1.0, 1.0]},
        {"x": [1.0, float("nan")]},
    ],
)
def test_metasurface_rejects_incomplete_or_invalid_channels(
    extractor: Callable[..., dict[str, Any]], altered: dict[str, list[float]]
) -> None:
    first = _result([0.5, 0.5])
    first.update(altered)
    with pytest.raises(CSTRFError):
        extractor([first], [_result([0.25, 0.25])])


@pytest.mark.parametrize("extractor", [extract_rta, extract_pcr])
def test_metasurface_rejects_mixed_run_or_units(
    extractor: Callable[..., dict[str, Any]],
) -> None:
    first = {**_result([0.5, 0.5]), "xlabel": "Frequency / THz", "run_id": 1}
    second = {**_result([0.25, 0.25]), "xlabel": "Frequency / GHz", "run_id": 1}
    with pytest.raises(CSTRFError, match="xlabel"):
        extractor([first], [second])
    second["xlabel"] = first["xlabel"]
    second["run_id"] = 0
    with pytest.raises(CSTRFError, match="run_id"):
        extractor([first], [second])
