"""Strict two-port Touchstone 1.0 export from saved complex CST results."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from cst_rf.errors import CSTRFError, ErrorCode

_GHZ_FACTOR = {"hz": 1e-9, "khz": 1e-6, "mhz": 1e-3, "ghz": 1.0, "thz": 1e3}


def render_two_port(
    channels: Mapping[str, Mapping[str, Any]],
    references: tuple[Mapping[str, Any], Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Return standard S11/S21/S12/S22 RI data, never guessing normalization."""
    if set(channels) != {"S11", "S21", "S12", "S22"}:
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT, "four explicit two-mode S channels are required"
        )
    first = channels["S11"]
    axis = list(first.get("x", []))
    xlabel = str(first.get("xlabel", ""))
    pieces = xlabel.lower().split("/")
    if len(pieces) != 2 or pieces[0].strip() != "frequency":
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "S result must declare a frequency axis")
    unit = pieces[1].strip()
    if unit not in _GHZ_FACTOR or not axis:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "unsupported or empty frequency axis")
    data = [*channels.values(), *references]
    run_id = first.get("run_id")
    for result in data:
        result_axis = list(result.get("x", []))
        if (
            len(result_axis) != len(axis)
            or str(result.get("xlabel", "")).strip().lower() != xlabel.strip().lower()
            or any(
                x is None
                or y is None
                or not math.isfinite(x)
                or not math.isfinite(y)
                or not math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-12)
                for x, y in zip(axis, result_axis)
            )
            or result.get("run_id") != run_id
            or len(result.get("real", [])) != len(axis)
            or len(result.get("imag", [])) != len(axis)
        ):
            raise CSTRFError(
                ErrorCode.RESULT_NOT_FOUND, "channel axes, run IDs or sample counts disagree"
            )
    z_values: list[float] = []
    for result in references:
        if "ohm" not in str(result.get("ylabel", "")).lower():
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "reference impedance must be in ohms")
        for real, imag in zip(result["real"], result["imag"]):
            if real is None or imag is None or not math.isfinite(real) or not math.isfinite(imag):
                raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "invalid reference impedance")
            if abs(imag) > 1e-6 or real <= 0:
                raise CSTRFError(
                    ErrorCode.INVALID_ARGUMENT, "complex or nonpositive reference impedance"
                )
            z_values.append(real)
    z_ref = z_values[0]
    if any(abs(value - z_ref) > max(1e-6, z_ref * 1e-9) for value in z_values):
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT, "frequency-dependent or unequal reference impedances"
        )
    lines = [
        "! cst-rf saved complex S parameters; no renormalization performed",
        "! Port 1/2 follow the explicitly supplied Sij channels; source run = " + str(run_id),
        f"# GHz S RI R {z_ref:.12g}",
    ]
    previous = -math.inf
    for index, value in enumerate(axis):
        if value is None or not math.isfinite(value) or value <= previous or value < 0:
            raise CSTRFError(
                ErrorCode.INVALID_ARGUMENT, "frequency axis must be finite and increasing"
            )
        previous = value
        fields = [f"{value * _GHZ_FACTOR[unit]:.12g}"]
        for key in ("S11", "S21", "S12", "S22"):
            real = channels[key]["real"][index]
            imag = channels[key]["imag"][index]
            if real is None or imag is None or not math.isfinite(real) or not math.isfinite(imag):
                raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "non-finite complex S sample")
            fields.extend((f"{real:.12g}", f"{imag:.12g}"))
        lines.append(" ".join(fields))
    return "\n".join(lines) + "\n", {
        "points": len(axis),
        "run_id": run_id,
        "reference_impedance_ohm": z_ref,
        "frequency_unit": "GHz",
        "source_frequency_unit": unit,
    }
