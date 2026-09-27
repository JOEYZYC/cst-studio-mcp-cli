"""Offline antenna planning helpers."""

from __future__ import annotations

import math
from typing import Any

from cst_rf.core.backends import history_vba
from cst_rf.errors import CSTRFError, ErrorCode


def plan_patch(
    frequency_ghz: float,
    epsilon_r: float,
    substrate_height_mm: float,
    *,
    feed_type: str = "waveguide",
) -> dict[str, Any]:
    if frequency_ghz <= 0 or epsilon_r <= 1 or substrate_height_mm <= 0:
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT, "frequency, epsilon_r and height must be positive"
        )
    if feed_type not in {"waveguide", "discrete"}:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "feed_type must be waveguide or discrete")
    c_mm_per_s = 299_792_458_000.0
    frequency_hz = frequency_ghz * 1e9
    width = c_mm_per_s / (2 * frequency_hz) * math.sqrt(2 / (epsilon_r + 1))
    effective_epsilon = (epsilon_r + 1) / 2 + (epsilon_r - 1) / 2 * (
        1 + 12 * substrate_height_mm / width
    ) ** -0.5
    length_extension = (
        0.412
        * substrate_height_mm
        * (
            (effective_epsilon + 0.3)
            * (width / substrate_height_mm + 0.264)
            / ((effective_epsilon - 0.258) * (width / substrate_height_mm + 0.8))
        )
    )
    effective_length = c_mm_per_s / (2 * frequency_hz * math.sqrt(effective_epsilon))
    length = effective_length - 2 * length_extension
    return {
        "feed_type": feed_type,
        "frequency_ghz": frequency_ghz,
        "epsilon_r": epsilon_r,
        "substrate_height_mm": substrate_height_mm,
        "dimensions_mm": {"patch_width": width, "patch_length": length},
        "model_type": "antenna",
        "boundary_type": "open",
        "excitation_type": feed_type,
        "steps": [
            "create substrate",
            "create ground",
            "create patch",
            f"create {feed_type} port",
            "set open boundary",
            "add S11 and farfield monitors",
        ],
    }


def build_patch_recipe(
    frequency_ghz: float,
    epsilon_r: float,
    substrate_height_mm: float,
    *,
    feed_type: str = "waveguide",
    conductor_thickness_mm: float = 0.035,
) -> dict[str, Any]:
    """Build one bounded rectangular-patch History recipe.

    The recipe intentionally uses a single dielectric substrate, PEC ground,
    PEC patch/feed, one port and one far-field monitor. It is a deterministic
    starting geometry, not an impedance-optimized antenna design.
    """
    if conductor_thickness_mm <= 0:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "conductor thickness must be positive")
    plan = plan_patch(
        frequency_ghz,
        epsilon_r,
        substrate_height_mm,
        feed_type=feed_type,
    )
    patch_width = float(plan["dimensions_mm"]["patch_width"])
    patch_length = float(plan["dimensions_mm"]["patch_length"])
    substrate_width = patch_width + 12.0 * substrate_height_mm
    substrate_length = patch_length + 16.0 * substrate_height_mm
    feed_width = max(substrate_height_mm, patch_width / 12.0)
    feed_start = -substrate_length / 2.0
    feed_end = -patch_length / 2.0
    top = substrate_height_mm
    metal_top = top + conductor_thickness_mm
    blocks = [
        history_vba.material(name="PatchSubstrate", epsilon_r=epsilon_r),
        history_vba.brick(
            name="Substrate",
            component="Antenna",
            material="PatchSubstrate",
            x_min=-substrate_width / 2.0,
            x_max=substrate_width / 2.0,
            y_min=-substrate_length / 2.0,
            y_max=substrate_length / 2.0,
            z_min=0,
            z_max=substrate_height_mm,
        ),
        history_vba.brick(
            name="Ground",
            component="Antenna",
            material="PEC",
            x_min=-substrate_width / 2.0,
            x_max=substrate_width / 2.0,
            y_min=-substrate_length / 2.0,
            y_max=substrate_length / 2.0,
            z_min=-conductor_thickness_mm,
            z_max=0,
        ),
        history_vba.brick(
            name="Patch",
            component="Antenna",
            material="PEC",
            x_min=-patch_width / 2.0,
            x_max=patch_width / 2.0,
            y_min=-patch_length / 2.0,
            y_max=patch_length / 2.0,
            z_min=top,
            z_max=metal_top,
        ),
        history_vba.brick(
            name="Feed",
            component="Antenna",
            material="PEC",
            x_min=-feed_width / 2.0,
            x_max=feed_width / 2.0,
            y_min=feed_start,
            y_max=feed_end,
            z_min=top,
            z_max=metal_top,
        ),
        history_vba.boundary(
            xmin="expanded open",
            xmax="expanded open",
            ymin="expanded open",
            ymax="expanded open",
            zmin="expanded open",
            zmax="expanded open",
        ),
        history_vba.frequency_range(0.7 * frequency_ghz, 1.3 * frequency_ghz),
        history_vba.port(
            port_number=1,
            port_type=feed_type,
            orientation="ymin",
            x_min=-feed_width,
            x_max=feed_width,
            y_min=feed_start,
            y_max=feed_start,
            z_min=-conductor_thickness_mm,
            z_max=metal_top + substrate_height_mm,
        ),
        history_vba.monitor(
            name="Farfield_f0",
            monitor_type="farfield",
            frequency=frequency_ghz,
        ),
    ]
    return {
        **plan,
        "dimensions_mm": {
            **plan["dimensions_mm"],
            "substrate_width": substrate_width,
            "substrate_length": substrate_length,
            "feed_width": feed_width,
            "conductor_thickness": conductor_thickness_mm,
        },
        "history_code": "\n\n".join(blocks),
        "validation": {
            "positive_dimensions": True,
            "feed_contacts_patch": feed_end == -patch_length / 2.0,
            "port_on_substrate_edge": True,
        },
    }
