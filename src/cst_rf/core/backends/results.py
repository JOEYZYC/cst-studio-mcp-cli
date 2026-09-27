"""Offline saved-result access through the official ``cst.results`` package."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from cst_rf.core.safety import resolve_source_project
from cst_rf.errors import CSTRFError, ErrorCode

ProjectFactory = Callable[..., Any]


def _complex_series(values: Sequence[Any]) -> dict[str, list[float | None]]:
    real: list[float | None] = []
    imag: list[float | None] = []
    magnitude: list[float | None] = []
    magnitude_db: list[float | None] = []
    phase_deg: list[float | None] = []
    for value in values:
        try:
            sample = complex(value)
        except (TypeError, ValueError):
            real.append(None)
            imag.append(None)
            magnitude.append(None)
            magnitude_db.append(None)
            phase_deg.append(None)
            continue
        mag = abs(sample)
        real.append(sample.real if math.isfinite(sample.real) else None)
        imag.append(sample.imag if math.isfinite(sample.imag) else None)
        magnitude.append(mag if math.isfinite(mag) else None)
        magnitude_db.append(20.0 * math.log10(mag) if mag > 0 and math.isfinite(mag) else None)
        phase_deg.append(
            math.degrees(math.atan2(sample.imag, sample.real))
            if math.isfinite(sample.real) and math.isfinite(sample.imag)
            else None
        )
    return {
        "real": real,
        "imag": imag,
        "magnitude": magnitude,
        "magnitude_db": magnitude_db,
        "phase_deg": phase_deg,
    }


def _finite_float(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


class ResultsBackend:
    """Lazy official backend; constructing it never imports or launches CST."""

    def __init__(self, project_factory: ProjectFactory | None = None) -> None:
        self._project_factory = project_factory

    def _factory(self) -> ProjectFactory:
        if self._project_factory is not None:
            return self._project_factory
        try:
            from cst.results import ProjectFile  # type: ignore[import-untyped]
        except Exception as exc:
            raise CSTRFError(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"cst.results is unavailable: {exc}",
            ) from exc
        return ProjectFile  # type: ignore[no-any-return]

    def _open(self, project_path: str | Path) -> tuple[Path, Any]:
        path = resolve_source_project(project_path)
        try:
            project = self._factory()(str(path), allow_interactive=False)
        except Exception as exc:
            raise CSTRFError(
                ErrorCode.RESULT_NOT_FOUND,
                f"could not open saved CST results: {exc}",
                details={"project_path": str(path)},
            ) from exc
        return path, project

    @staticmethod
    def _module(project: Any, module_type: str) -> tuple[Any, str]:
        normalized = module_type.strip().lower()
        if normalized == "3d":
            return project.get_3d(), "3d"
        if normalized == "schematic":
            return project.get_schematic(), "schematic"
        raise CSTRFError(
            ErrorCode.INVALID_ARGUMENT,
            "module_type must be '3d' or 'schematic'",
        )

    def list_results(
        self,
        project_path: str | Path,
        *,
        module_type: str = "3d",
        filter_type: str = "0D/1D",
    ) -> dict[str, Any]:
        path, project = self._open(project_path)
        module, normalized_module = self._module(project, module_type)
        if filter_type not in {"0D/1D", "colormap"}:
            raise CSTRFError(
                ErrorCode.INVALID_ARGUMENT,
                "filter_type must be '0D/1D' or 'colormap'",
            )
        try:
            tree_paths = [str(item) for item in module.get_tree_items(filter=filter_type)]
            items = []
            for tree_path in tree_paths:
                try:
                    run_ids = [int(item) for item in module.get_run_ids(tree_path)]
                except Exception:
                    run_ids = []
                items.append({"tree_path": tree_path, "run_ids": run_ids})
        except Exception as exc:
            raise CSTRFError(
                ErrorCode.RESULT_NOT_FOUND,
                f"could not list saved results: {exc}",
            ) from exc
        return {
            "project_path": str(path),
            "module_type": normalized_module,
            "filter_type": filter_type,
            "count": len(items),
            "items": items,
        }

    def read_1d(
        self,
        project_path: str | Path,
        tree_path: str,
        *,
        run_id: int = 0,
        module_type: str = "3d",
    ) -> dict[str, Any]:
        if not tree_path.strip():
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "tree_path is required")
        path, project = self._open(project_path)
        module, normalized_module = self._module(project, module_type)
        try:
            item = module.get_result_item(tree_path, run_id=run_id, load_impedances=True)
            x_values = [_finite_float(value) for value in item.get_xdata()]
            y_values = list(item.get_ydata())
        except Exception as exc:
            raise CSTRFError(
                ErrorCode.RESULT_NOT_FOUND,
                f"could not read saved result: {exc}",
                details={"tree_path": tree_path, "run_id": run_id},
            ) from exc
        return {
            "project_path": str(path),
            "module_type": normalized_module,
            "tree_path": str(getattr(item, "treepath", tree_path)),
            "run_id": int(getattr(item, "run_id", run_id)),
            "title": str(getattr(item, "title", "")),
            "xlabel": str(getattr(item, "xlabel", "")),
            "ylabel": str(getattr(item, "ylabel", "")),
            "point_count": len(x_values),
            "x": x_values,
            **_complex_series(y_values),
        }
