"""Read-only R/T/A extraction for an infinite unit-cell result."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

from cst_rf.core.backends import history_vba
from cst_rf.errors import CSTRFError, ErrorCode


def _power(values: Sequence[float | None]) -> list[float | None]:
    return [None if value is None else value * value for value in values]


def _sum_channels(channels: Sequence[Sequence[float | None]], count: int) -> list[float | None]:
    result: list[float | None] = []
    for index in range(count):
        values = [channel[index] for channel in channels]
        if any(value is None for value in values):
            result.append(None)
        else:
            non_null = cast(list[float], values)
            result.append(sum(non_null))
    return result


def _checked_frequency_axis(results: Sequence[Mapping[str, Any]], label: str) -> list[float]:
    frequency = list(results[0].get("x", []))
    if not frequency:
        raise CSTRFError(ErrorCode.RESULT_NOT_FOUND, f"{label} result has no frequency samples")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in frequency
    ) or any(left >= right for left, right in zip(frequency, frequency[1:])):
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "frequency axis must be finite and increasing")
    for result in results:
        if list(result.get("x", [])) != frequency:
            raise CSTRFError(
                ErrorCode.RESULT_NOT_FOUND, "channels do not share the same frequency axis"
            )
        magnitudes = result.get("magnitude", [])
        if len(magnitudes) != len(frequency) or any(
            value is not None
            and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            )
            for value in magnitudes
        ):
            raise CSTRFError(
                ErrorCode.INVALID_ARGUMENT, "channel magnitude is incomplete or invalid"
            )
    for key in ("xlabel", "run_id"):
        present = [result[key] for result in results if key in result]
        if present and (len(present) != len(results) or len(set(present)) != 1):
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, f"channel {key} values disagree")
    return [float(value) for value in frequency]


def extract_rta(
    reflection_results: Sequence[Mapping[str, Any]],
    transmission_results: Sequence[Mapping[str, Any]] = (),
    *,
    transmission_zero_reason: str | None = None,
) -> dict[str, Any]:
    """Combine already-read S-parameter channels using the real frequency axis.

    Each result must contain ``x`` and ``magnitude`` arrays. Transmission is
    intentionally required; this function never silently assumes a PEC backplane.
    """
    if not reflection_results:
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT,
            "reflection_results is required",
        )
    if not transmission_results and not transmission_zero_reason:
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT,
            "transmission_results is required unless transmission_zero_reason explicitly proves T=0",
        )
    if transmission_results and transmission_zero_reason:
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT,
            "provide measured transmission channels or a T=0 backplane reason, not both",
        )
    frequency = _checked_frequency_axis([*reflection_results, *transmission_results], "reflection")

    reflection_power = _sum_channels(
        [_power(result.get("magnitude", [])) for result in reflection_results], len(frequency)
    )
    transmission_power = (
        [0.0] * len(frequency)
        if transmission_zero_reason
        else _sum_channels(
            [_power(result.get("magnitude", [])) for result in transmission_results],
            len(frequency),
        )
    )
    absorption: list[float | None] = []
    warnings: list[str] = (
        ["T=0 is user-asserted; complete backplane requires independent model evidence"]
        if transmission_zero_reason
        else []
    )
    for reflection, transmission in zip(reflection_power, transmission_power):
        if reflection is None or transmission is None:
            absorption.append(None)
            continue
        value = 1.0 - reflection - transmission
        absorption.append(value)
        if not math.isfinite(value) or value < -1e-6 or value > 1.0 + 1e-6:
            warnings.append("R/T/A power balance is outside the numerical tolerance")
    return {
        "frequency": frequency,
        "reflection_power": reflection_power,
        "transmission_power": transmission_power,
        "absorption_raw": absorption,
        "warnings": sorted(set(warnings)),
        "transmission_assumption": transmission_zero_reason,
        "channel_counts": {
            "reflection": len(reflection_results),
            "transmission": len(transmission_results),
        },
    }


def extract_pcr(
    co_polarized_results: Sequence[Mapping[str, Any]],
    cross_polarized_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Calculate polarization-conversion metrics from saved complex channels.

    ``co_polarized_results`` and ``cross_polarized_results`` are normally the
    reflected (or transmitted) Floquet channels in the chosen polarization
    basis.  PCR is defined as cross-polarized power divided by the sum of the
    two supplied polarization powers.  No channel or frequency normalization
    is inferred here.
    """
    if not co_polarized_results or not cross_polarized_results:
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT,
            "both co- and cross-polarized results are required",
        )
    all_results = [*co_polarized_results, *cross_polarized_results]
    frequency = _checked_frequency_axis(all_results, "polarization")
    co_power = _sum_channels(
        [_power(result.get("magnitude", [])) for result in co_polarized_results],
        len(frequency),
    )
    cross_power = _sum_channels(
        [_power(result.get("magnitude", [])) for result in cross_polarized_results],
        len(frequency),
    )
    pcr: list[float | None] = []
    conversion_efficiency: list[float | None] = []
    warnings: list[str] = []
    for co_value, cross_value in zip(co_power, cross_power):
        if co_value is None or cross_value is None:
            pcr.append(None)
            conversion_efficiency.append(None)
            continue
        total = co_value + cross_value
        if total <= 0:
            pcr.append(None)
            conversion_efficiency.append(None)
            warnings.append("polarization power is zero at one or more frequency points")
            continue
        pcr.append(cross_value / total)
        conversion_efficiency.append(cross_value)
    return {
        "frequency": frequency,
        "co_polarized_power": co_power,
        "cross_polarized_power": cross_power,
        "pcr": pcr,
        "conversion_efficiency": conversion_efficiency,
        "warnings": sorted(set(warnings)),
        "channel_counts": {
            "co_polarized": len(co_polarized_results),
            "cross_polarized": len(cross_polarized_results),
        },
    }


def plan_finite_array(period_mm: float, rows: int, columns: int) -> dict[str, Any]:
    if period_mm <= 0 or rows < 1 or columns < 1:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "period and array dimensions must be positive")
    return {
        "model_type": "finite_array",
        "boundary_type": "open",
        "excitation_type": "plane_wave",
        "period_mm": period_mm,
        "rows": rows,
        "columns": columns,
        "extent_mm": {"x": period_mm * columns, "y": period_mm * rows},
        "steps": [
            "copy unit-cell geometry",
            "replicate finite array",
            "set open boundary",
            "add plane-wave excitation",
        ],
    }


def build_finite_array_recipe(
    *,
    component: str,
    source_shapes: Sequence[str],
    period_mm: float,
    rows: int,
    columns: int,
    polarization_axis: str = "x",
) -> dict[str, Any]:
    plan = plan_finite_array(period_mm, rows, columns)
    if not source_shapes:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "source_shapes is required")
    if rows * columns > 100:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "finite-array size is limited to 100 cells")
    blocks: list[str] = []
    for row in range(rows):
        for column in range(columns):
            if row == 0 and column == 0:
                continue
            for shape in source_shapes:
                blocks.append(
                    history_vba.translate_copy(
                        component=component,
                        name=str(shape),
                        x=column * period_mm,
                        y=row * period_mm,
                    )
                )
    blocks.extend(
        [
            history_vba.boundary(
                xmin="expanded open",
                xmax="expanded open",
                ymin="expanded open",
                ymax="expanded open",
                zmin="expanded open",
                zmax="expanded open",
            ),
            history_vba.plane_wave(polarization_axis=polarization_axis),
        ]
    )
    return {
        **plan,
        "component": component,
        "source_shapes": list(source_shapes),
        "polarization_axis": polarization_axis,
        "copy_count": (rows * columns - 1) * len(source_shapes),
        "history_code": "\n\n".join(blocks),
        "validation": {
            "separate_finite_array_model": True,
            "open_boundary": True,
            "plane_wave_excitation": True,
        },
    }
