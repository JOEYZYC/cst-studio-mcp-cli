"""Fixed, validated CST History VBA snippets.

The public API accepts structured fields only. Callers cannot provide an
arbitrary VBA string; every returned command is assembled by one of the
templates below and is intended to be passed to ``Model3D.add_to_history``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Final

from cst_rf.errors import CSTRFError, ErrorCode

_IDENTIFIER: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EXPRESSION: Final = re.compile(r"^[A-Za-z0-9_ .()+*/-]+$")
_ALLOWED_AXES: Final = {"x", "y", "z"}


def floquet_modes(port: str, count: int) -> str:
    """Configure only the selected Floquet port's considered mode count."""
    if port not in {"Zmin", "Zmax"} or not 1 <= count <= 100:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "unsupported Floquet port or mode count")
    return "\n".join(
        [
            "With FloquetPort",
            f' .Port "{port}"',
            f' .SetNumberOfModesConsidered "{count}"',
            "End With",
        ]
    )


def floquet_polarization_basis(port: str, basis: str) -> str:
    """Toggle the documented fundamental Floquet TE/TM versus RCP/LCP basis."""
    if port not in {"Zmin", "Zmax"} or basis not in {"linear", "circular"}:
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT, "unsupported Floquet port or polarization basis"
        )
    flag = "True" if basis == "circular" else "False"
    return "\n".join(
        [
            "With FloquetPort",
            f' .Port "{port}"',
            f' .SetUseCircularPolarization "{flag}"',
            "End With",
        ]
    )


def parameter_sweep_sequence(
    *, sequence_name: str, parameter_name: str, values: Sequence[float]
) -> str:
    """Define a bounded CST-native sweep sequence; never start the solver here."""
    _name(sequence_name, "sequence_name")
    _name(parameter_name, "parameter_name")
    if not 2 <= len(values) <= 4 or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or abs(value) > 1e6
        for value in values
    ):
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT,
            "sweep needs two to four distinct finite numeric values within +/-1e6",
        )
    formatted = [format(value, ".15g") for value in values]
    if len(set(formatted)) != len(values):
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT, "sweep points collapse to duplicate CST values"
        )
    points = "; ".join(formatted)
    return "\n".join(
        [
            "With ParameterSweep",
            f' .AddSequence "{sequence_name}"',
            f' .AddParameter_ArbitraryPoints "{sequence_name}", "{parameter_name}", "{points}"',
            ' .UseDistributedComputing "False"',
            ' .StartActiveSolver "True"',
            "End With",
        ]
    )


def _name(value: str, field: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, f"{field} must be a simple identifier")
    return value


def _scalar(value: str | float | int, field: str) -> str:
    text = str(value).strip()
    if not text or not _EXPRESSION.fullmatch(text):
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, f"{field} is not a safe CST expression")
    try:
        numeric = float(text)
    except ValueError:
        return text
    if not math.isfinite(numeric):
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, f"{field} must be finite")
    return text


def parameter_expression(value: str | float | int) -> str:
    """Validate a CST parameter expression before handing it to StoreParameter."""
    return _scalar(value, "parameter value")


def _identifier_quoted(value: str, field: str) -> str:
    _name(value, field)
    return f'"{value}"'


def _quoted(value: str, field: str) -> str:
    if not value or '"' in value or "\r" in value or "\n" in value:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, f"{field} contains unsafe quoted text")
    return f'"{value}"'


def brick(
    *,
    name: str,
    component: str,
    material: str,
    x_min: str | float,
    x_max: str | float,
    y_min: str | float,
    y_max: str | float,
    z_min: str | float,
    z_max: str | float,
) -> str:
    return "\n".join(
        [
            "With Brick",
            " .Reset",
            f" .Name ({_identifier_quoted(name, 'name')})",
            f" .Component ({_identifier_quoted(component, 'component')})",
            f" .Material ({_identifier_quoted(material, 'material')})",
            f" .Xrange ({_quoted(_scalar(x_min, 'x_min'), 'x_min')}, {_quoted(_scalar(x_max, 'x_max'), 'x_max')})",
            f" .Yrange ({_quoted(_scalar(y_min, 'y_min'), 'y_min')}, {_quoted(_scalar(y_max, 'y_max'), 'y_max')})",
            f" .Zrange ({_quoted(_scalar(z_min, 'z_min'), 'z_min')}, {_quoted(_scalar(z_max, 'z_max'), 'z_max')})",
            " .Create",
            "End With",
        ]
    )


def cylinder(
    *,
    name: str,
    component: str,
    material: str,
    axis: str,
    radius: str | float,
    z_min: str | float,
    z_max: str | float,
    x_center: str | float = 0,
    y_center: str | float = 0,
) -> str:
    normalized_axis = axis.lower()
    if normalized_axis not in _ALLOWED_AXES:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "axis must be x, y or z")
    return "\n".join(
        [
            "With Cylinder",
            " .Reset",
            f" .Name ({_identifier_quoted(name, 'name')})",
            f" .Component ({_identifier_quoted(component, 'component')})",
            f" .Material ({_identifier_quoted(material, 'material')})",
            f" .Axis ({_identifier_quoted(normalized_axis, 'axis')})",
            f" .OuterRadius ({_quoted(_scalar(radius, 'radius'), 'radius')})",
            f" .Zrange ({_quoted(_scalar(z_min, 'z_min'), 'z_min')}, {_quoted(_scalar(z_max, 'z_max'), 'z_max')})",
            f" .Xcenter ({_quoted(_scalar(x_center, 'x_center'), 'x_center')})",
            f" .Ycenter ({_quoted(_scalar(y_center, 'y_center'), 'y_center')})",
            " .Create",
            "End With",
        ]
    )


def frequency_range(f_min: str | float, f_max: str | float) -> str:
    return "\n".join(
        [
            "With Solver",
            f" .FrequencyRange ({_quoted(_scalar(f_min, 'f_min'), 'f_min')}, {_quoted(_scalar(f_max, 'f_max'), 'f_max')})",
            "End With",
        ]
    )


def boundary(**values: str) -> str:
    allowed = {"xmin", "xmax", "ymin", "ymax", "zmin", "zmax"}
    boundary_values = {"electric", "magnetic", "open", "expanded open", "unit cell", "periodic"}
    if set(values) != allowed:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "all six boundary values are required")
    if any(value not in boundary_values for value in values.values()):
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "unsupported boundary value")
    lines = ["With Boundary", " .Reset"]
    for key in sorted(allowed):
        lines.append(f" .{key.title()} ({_quoted(values[key], key)})")
    lines.extend([" .Create", "End With"])
    return "\n".join(lines)


def monitor(*, name: str, monitor_type: str, frequency: str | float) -> str:
    allowed = {"e_field", "h_field", "farfield", "surface_current"}
    if monitor_type not in allowed:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "unsupported monitor_type")
    return "\n".join(
        [
            "With Monitor",
            " .Reset",
            f" .Name ({_identifier_quoted(name, 'name')})",
            f" .Dimension ({_quoted(monitor_type, 'monitor_type')})",
            f" .Frequency ({_quoted(_scalar(frequency, 'frequency'), 'frequency')})",
            " .Create",
            "End With",
        ]
    )


def material(
    *,
    name: str,
    epsilon_r: str | float,
    mu_r: str | float = 1.0,
    conductivity: str | float = 0.0,
) -> str:
    """Create a simple isotropic material definition."""
    return "\n".join(
        [
            "With Material",
            " .Reset",
            f" .Name ({_identifier_quoted(name, 'name')})",
            f" .Epsilon ({_quoted(_scalar(epsilon_r, 'epsilon_r'), 'epsilon_r')})",
            f" .Mue ({_quoted(_scalar(mu_r, 'mu_r'), 'mu_r')})",
            f" .Kappa ({_quoted(_scalar(conductivity, 'conductivity'), 'conductivity')})",
            " .Create",
            "End With",
        ]
    )


def assign_material(*, component: str, name: str, material_name: str) -> str:
    _name(component, "component")
    _name(name, "name")
    return "\n".join(
        [
            "With Solid",
            f" .Name ({_quoted(f'{component}:{name}', 'solid')})",
            f" .Material ({_identifier_quoted(material_name, 'material_name')})",
            " .Apply",
            "End With",
        ]
    )


def boolean(*, operation: str, component: str, target: str, tool: str) -> str:
    if operation not in {"add", "subtract", "intersect"}:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "operation must be add, subtract or intersect")
    _name(component, "component")
    _name(target, "target")
    _name(tool, "tool")
    method = operation.title()
    return f"Solid.{method} {_quoted(f'{component}:{target}', 'target')}, {_quoted(f'{component}:{tool}', 'tool')}"


def port(
    *,
    port_number: int,
    port_type: str,
    orientation: str,
    x_min: str | float,
    x_max: str | float,
    y_min: str | float,
    y_max: str | float,
    z_min: str | float,
    z_max: str | float,
) -> str:
    if port_number < 1:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "port_number must be positive")
    if port_type not in {"waveguide", "discrete"}:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "port_type must be waveguide or discrete")
    if orientation not in {"xmin", "xmax", "ymin", "ymax", "zmin", "zmax"}:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "unsupported port orientation")
    if port_type == "discrete":
        object_name = "DiscretePort"
    else:
        object_name = "Port"
    return "\n".join(
        [
            f"With {object_name}",
            " .Reset",
            f' .PortNumber ("{port_number}")',
            f" .Orientation ({_identifier_quoted(orientation, 'orientation')})",
            f" .Xrange ({_quoted(_scalar(x_min, 'x_min'), 'x_min')}, {_quoted(_scalar(x_max, 'x_max'), 'x_max')})",
            f" .Yrange ({_quoted(_scalar(y_min, 'y_min'), 'y_max')}, {_quoted(_scalar(y_max, 'y_max'), 'y_max')})",
            f" .Zrange ({_quoted(_scalar(z_min, 'z_min'), 'z_min')}, {_quoted(_scalar(z_max, 'z_max'), 'z_max')})",
            " .Create",
            "End With",
        ]
    )


def translate_copy(
    *, component: str, name: str, x: str | float, y: str | float, z: str | float = 0
) -> str:
    _name(component, "component")
    _name(name, "name")
    return "\n".join(
        [
            "With Transform",
            " .Reset",
            f" .Name ({_quoted(f'{component}:{name}', 'shape')})",
            f" .Vector ({_quoted(_scalar(x, 'x'), 'x')}, {_quoted(_scalar(y, 'y'), 'y')}, {_quoted(_scalar(z, 'z'), 'z')})",
            ' .UsePickedPoints ("False")',
            ' .InvertPickedPoints ("False")',
            ' .MultipleObjects ("True")',
            ' .GroupObjects ("False")',
            ' .Repetitions ("1")',
            ' .Transform ("Shape", "Translate")',
            "End With",
        ]
    )


def plane_wave(*, polarization_axis: str = "x", propagation: str = "-z") -> str:
    if polarization_axis not in {"x", "y"}:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "polarization_axis must be x or y")
    if propagation not in {"+z", "-z"}:
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "propagation must be +z or -z")
    normal_z = 1 if propagation == "+z" else -1
    e_vector = (1, 0, 0) if polarization_axis == "x" else (0, 1, 0)
    return "\n".join(
        [
            "With PlaneWave",
            " .Reset",
            f" .Normal (0, 0, {normal_z})",
            f" .EVector ({e_vector[0]}, {e_vector[1]}, {e_vector[2]})",
            ' .Polarization ("Linear")',
            ' .ReferenceFrequency ("0.0")',
            ' .PhaseDifference ("0.0")',
            " .Store",
            "End With",
        ]
    )
