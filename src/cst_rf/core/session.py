"""Serialized CST session backend with optional high-risk automation."""

from __future__ import annotations

import importlib
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from cst_rf.core.backends import history_vba
from cst_rf.core.popups import KnownAbortConfirmationHandler, KnownPopupHandler
from cst_rf.errors import CSTRFError, ErrorCode


def _canonical(value: str | Path) -> str:
    return str(Path(value).expanduser().resolve()).casefold()


class ManualSession:
    def __init__(
        self,
        interface_module: Any | None = None,
        *,
        auto_launch: bool = False,
        auto_open_project: bool = False,
        auto_switch_project: bool = False,
        auto_close_project: bool = False,
        auto_close_environment: bool = False,
        auto_handle_popups: bool = False,
        result_dialog_policy: str = "delete_current_keep_cache",
    ) -> None:
        self._interface = interface_module
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cst-rf")
        self._design_environment: Any | None = None
        self._pid: int | None = None
        self._project_path: str | None = None
        self._project: Any | None = None
        self._auto_launch = auto_launch
        self._auto_open_project = auto_open_project
        self._auto_switch_project = auto_switch_project
        self._auto_close_project = auto_close_project
        self._auto_close_environment = auto_close_environment
        self._auto_handle_popups = auto_handle_popups
        self._result_dialog_policy = result_dialog_policy
        self._opened_project_by_agent = False
        self._created_environment_by_agent = False

    def _interface_module(self) -> Any:
        if self._interface is None:
            try:
                self._interface = importlib.import_module("cst.interface")
            except Exception as exc:
                raise CSTRFError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"cst.interface is unavailable: {exc}",
                ) from exc
        return self._interface

    def list_instances(self) -> list[int]:
        def operation() -> list[int]:
            interface = self._interface_module()
            try:
                return [int(pid) for pid in interface.running_design_environments()]
            except Exception as exc:
                raise CSTRFError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"could not list CST Design Environments: {exc}",
                ) from exc

        return self._executor.submit(operation).result()

    def _quiet_mode(self, environment: Any, enabled: bool) -> None:
        if not self._auto_handle_popups:
            return
        setter = getattr(environment, "set_quiet_mode", None)
        if callable(setter):
            setter(enabled)

    def _popup_handler(self) -> KnownPopupHandler | None:
        if not self._auto_handle_popups or self._pid is None:
            return None
        return KnownPopupHandler(self._pid, result_policy=self._result_dialog_policy)

    def connect(
        self,
        pid: int | None,
        expected_project_path: str | Path,
        *,
        auto_open: bool | None = None,
        auto_switch: bool | None = None,
    ) -> dict[str, Any]:
        expected = _canonical(expected_project_path)
        auto_open_enabled = self._auto_open_project if auto_open is None else auto_open
        auto_switch_enabled = self._auto_switch_project if auto_switch is None else auto_switch

        def operation() -> dict[str, Any]:
            interface = self._interface_module()
            environment = None
            created_environment = False
            try:
                if pid is not None:
                    environment = interface.DesignEnvironment.connect(int(pid))
                else:
                    running = [int(item) for item in interface.running_design_environments()]
                    if running:
                        for candidate_pid in running:
                            candidate = interface.DesignEnvironment.connect(candidate_pid)
                            candidate_projects = [
                                str(item) for item in candidate.list_open_projects()
                            ]
                            if any(_canonical(path) == expected for path in candidate_projects):
                                environment = candidate
                                break
                        if environment is None:
                            environment = interface.DesignEnvironment.connect(running[0])
                    elif self._auto_launch:
                        environment = interface.DesignEnvironment.new()
                        created_environment = True
                    else:
                        raise CSTRFError(
                            ErrorCode.CST_NOT_RUNNING,
                            "no CST Design Environment is running",
                        )
                open_projects = [str(item) for item in environment.list_open_projects()]
            except Exception as exc:
                if isinstance(exc, CSTRFError):
                    raise
                raise CSTRFError(
                    ErrorCode.CST_NOT_RUNNING,
                    f"could not attach to CST: {exc}",
                ) from exc
            matches = [path for path in open_projects if _canonical(path) == expected]
            opened_project = False
            try:
                self._quiet_mode(environment, True)
                if len(matches) == 1:
                    project_path = matches[0]
                    project = environment.get_open_project(project_path)
                    if auto_switch_enabled:
                        activate = getattr(project, "activate", None)
                        if callable(activate):
                            activate()
                elif auto_open_enabled:
                    project = environment.open_project(str(Path(expected_project_path).resolve()))
                    project_path = str(Path(expected_project_path).resolve())
                    opened_project = True
                    open_projects.append(project_path)
                else:
                    raise CSTRFError(
                        ErrorCode.PROJECT_IDENTITY_MISMATCH,
                        "expected project is not uniquely open in the requested CST instance",
                        details={"pid": pid, "expected": expected, "open_projects": open_projects},
                    )
            except CSTRFError:
                raise
            except Exception as exc:
                message = str(exc)
                if self._auto_handle_popups and any(
                    token in message.lower() for token in ("dialog", "message box", "input")
                ):
                    raise CSTRFError(
                        ErrorCode.POPUP_REQUIRES_INPUT,
                        f"CST automation reached a dialog requiring user input: {message}",
                    ) from exc
                raise CSTRFError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"could not open or activate CST project: {message}",
                ) from exc
            finally:
                self._quiet_mode(environment, False)
            self._design_environment = environment
            self._pid = int(environment.pid()) if pid is None else int(pid)
            self._project_path = project_path
            self._project = project
            self._opened_project_by_agent = opened_project
            self._created_environment_by_agent = created_environment
            return {
                "pid": self._pid,
                "project_path": project_path,
                "open_projects": open_projects,
                "project_handle": project is not None,
                "opened_project": opened_project,
                "created_environment": created_environment,
            }

        return self._executor.submit(operation).result()

    def disconnect(
        self,
        *,
        close_project: bool | None = None,
        close_environment: bool | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            pid = self._pid
            project_path = self._project_path
            project_closed = False
            environment_closed = False
            should_close_project = (
                self._auto_close_project and self._opened_project_by_agent
                if close_project is None
                else close_project
            )
            should_close_environment = (
                self._auto_close_environment and self._created_environment_by_agent
                if close_environment is None
                else close_environment
            )
            if self._project is not None and should_close_project:
                self._quiet_mode(self._design_environment, True)
                try:
                    self._project.close()
                    project_closed = True
                finally:
                    self._quiet_mode(self._design_environment, False)
            if self._design_environment is not None and should_close_environment:
                self._quiet_mode(self._design_environment, True)
                try:
                    self._design_environment.close()
                    environment_closed = True
                finally:
                    self._quiet_mode(self._design_environment, False)
            self._design_environment = None
            self._pid = None
            self._project_path = None
            self._project = None
            self._opened_project_by_agent = False
            self._created_environment_by_agent = False
            return {
                "pid": pid,
                "project_path": project_path,
                "closed_project": project_closed,
                "closed_environment": environment_closed,
                "closed_cst": environment_closed,
            }

        return self._executor.submit(operation).result()

    def inspect_project(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if self._project is None or self._design_environment is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            project = self._project
            model = project.model3d
            result: dict[str, Any] = {
                "pid": self._pid,
                "project_path": self._project_path,
            }
            try:
                project_type = project.project_type()
                result["project_type"] = getattr(project_type, "name", str(project_type))
            except Exception:
                result["project_type"] = "unknown"
            try:
                result["solver_type"] = str(model.get_active_solver_name())
            except Exception:
                result["solver_type"] = "unknown"
            try:
                result["solver_running"] = bool(model.is_solver_running())
            except Exception:
                result["solver_running"] = None
            try:
                result["open_projects"] = [
                    str(item) for item in self._design_environment.list_open_projects()
                ]
            except Exception:
                result["open_projects"] = []
            return result

        return self._executor.submit(operation).result()

    def model_tree(self) -> list[str]:
        def operation() -> list[str]:
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            return [str(item) for item in self._project.model3d.get_tree_items()]

        return self._executor.submit(operation).result()

    def parameters(self) -> list[dict[str, Any]]:
        def operation() -> list[dict[str, Any]]:
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            count = int(model.GetNumberOfParameters())
            values: list[dict[str, Any]] = []
            for index in range(count):
                name = str(model.GetParameterName(index))
                item: dict[str, Any] = {"name": name}
                try:
                    item["expression"] = str(model.GetParameterSValue(index))
                except Exception:
                    item["expression"] = None
                try:
                    item["value"] = float(model.GetParameterNValue(index))
                except Exception:
                    item["value"] = None
                values.append(item)
            return values

        return self._executor.submit(operation).result()

    def floquet_info(self, port: str = "Zmax") -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            allow_history = getattr(model, "allow_history_commands", None)
            if not callable(allow_history):
                raise CSTRFError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    "CST binding requires allow_history_commands() for Floquet inspection",
                )
            allow_history()
            floquet = model.FloquetPort
            floquet.Port(port)
            values: dict[str, Any] = {"port": port}
            for name in ("GetNumberOfModes", "GetNumberOfModesConsidered"):
                try:
                    values[name] = int(getattr(floquet, name)(timeout=5))
                except Exception as exc:
                    values[name] = None
                    values[f"{name}_error"] = str(exc)
            for name in ("IsPortAtZmin", "IsPortAtZmax"):
                try:
                    values[name] = bool(getattr(floquet, name)(timeout=5))
                except Exception as exc:
                    values[name] = None
                    values[f"{name}_error"] = str(exc)
            modes: list[dict[str, Any]] = []
            try:
                count = min(
                    int(values["GetNumberOfModes"]), int(values["GetNumberOfModesConsidered"]), 4
                )
                for number in range(1, count + 1):
                    found, mode_name = floquet.GetModeNameByNumber(number, timeout=5)
                    if not found:
                        break
                    modes.append({"number": number, "name": str(mode_name)})
            except Exception as exc:
                values["mode_names_error"] = str(exc)
            values["mode_names"] = modes
            fundamental = [item["name"] for item in modes[:2]]
            values["polarization_basis"] = (
                "linear"
                if fundamental == ["TE(0,0)", "TM(0,0)"]
                else "circular"
                if set(fundamental) == {"RCP(0,0)", "LCP(0,0)"}
                else "unknown"
            )
            return values

        return self._executor.submit(operation).result()

    def boundaries(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            model.allow_history_commands()
            boundary = model.Boundary
            values: dict[str, Any] = {}
            for name in ("Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"):
                try:
                    values[name] = str(getattr(boundary, f"Get{name}")(timeout=5))
                except Exception as exc:
                    values[name] = None
                    values[f"{name}_error"] = str(exc)
            for name in ("GetUnitCellDs1", "GetUnitCellDs2", "GetUnitCellAngle"):
                try:
                    values[name] = str(getattr(boundary, name)(timeout=5))
                except Exception:
                    values[name] = None
            try:
                active, theta, phi, direction = boundary.GetUnitCellScanAngle(timeout=5)
                values["scan_angle"] = {
                    "active": bool(active),
                    "theta_deg": float(theta),
                    "phi_deg": float(phi),
                    "direction": int(direction),
                }
            except Exception as exc:
                values["scan_angle"] = None
                values["scan_angle_error"] = str(exc)
            return values

        return self._executor.submit(operation).result()

    def set_parameter(
        self, name: str, value: str | float, *, confirm: bool, rebuild: bool = False
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if not confirm:
                raise CSTRFError(
                    ErrorCode.CONFIRMATION_REQUIRED, "parameter change requires confirm=true"
                )
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            if bool(model.is_solver_running(timeout=5)):
                raise CSTRFError(ErrorCode.SOLVER_BUSY, "cannot change parameters while solving")
            expression = history_vba.parameter_expression(value)
            model.allow_history_commands()
            popup_handler = self._popup_handler()
            if popup_handler is None:
                model.StoreParameter(name, expression)
                if rebuild:
                    model.full_history_rebuild()
                popup_events: list[dict[str, Any]] = []
            else:
                with popup_handler:
                    model.StoreParameter(name, expression)
                    if rebuild:
                        model.full_history_rebuild()
                popup_events = popup_handler.events
            readback: str | None = None
            if rebuild:
                for index in range(int(model.GetNumberOfParameters())):
                    if str(model.GetParameterName(index)) == name:
                        readback = str(model.GetParameterSValue(index))
                        break
                if readback != expression:
                    raise CSTRFError(
                        ErrorCode.BACKEND_UNAVAILABLE,
                        f"parameter readback disagrees after rebuild: {name}",
                    )
            return {
                "name": name,
                "value": expression,
                "rebuilt": rebuild,
                "readback": readback,
                "saved": False,
                "handled_popups": popup_events,
            }

        return self._executor.submit(operation).result()

    def save_project(self, *, confirm: bool) -> dict[str, Any]:
        """Save only the already attached scratch project, including its results."""
        if not confirm:
            raise CSTRFError(ErrorCode.CONFIRMATION_REQUIRED, "project save requires confirm=true")

        def operation() -> dict[str, Any]:
            if self._project is None or self._project_path is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            path = Path(self._project_path).resolve()
            if _canonical(self._project.filename()) != _canonical(path):
                raise CSTRFError(
                    ErrorCode.PROJECT_IDENTITY_MISMATCH, "attached project filename changed"
                )
            if bool(self._project.model3d.is_solver_running(timeout=5)):
                raise CSTRFError(ErrorCode.SOLVER_BUSY, "cannot save while solving")
            self._project.save(include_results=True, allow_overwrite=True)
            return {"project_path": str(path), "saved": True, "include_results": True}

        return self._executor.submit(operation).result()

    def set_floquet_modes(self, count: int, *, confirm: bool) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if not confirm:
                raise CSTRFError(
                    ErrorCode.CONFIRMATION_REQUIRED, "Floquet change requires confirm=true"
                )
            if count < 1:
                raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "Floquet mode count must be positive")
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            if bool(model.is_solver_running(timeout=5)):
                raise CSTRFError(ErrorCode.SOLVER_BUSY, "cannot change Floquet modes while solving")
            model.allow_history_commands()
            port = model.FloquetPort
            port.Port("Zmax")
            previous = int(port.GetNumberOfModesConsidered(timeout=5))
            if previous == count:
                return {"port": "Zmax", "modes_considered": count, "changed": False}
            code = history_vba.floquet_modes("Zmax", count)
            popup_handler = self._popup_handler()
            if popup_handler is None:
                model.add_to_history("Set Zmax Floquet considered modes", code)
                popup_events: list[dict[str, Any]] = []
            else:
                with popup_handler:
                    model.add_to_history("Set Zmax Floquet considered modes", code)
                popup_events = popup_handler.events
            model.allow_history_commands()
            port.Port("Zmax")
            actual = int(port.GetNumberOfModesConsidered(timeout=5))
            if actual != count:
                raise CSTRFError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"Floquet mode write did not persist: requested {count}, read {actual}",
                )
            return {
                "port": "Zmax",
                "modes_considered": actual,
                "changed": True,
                "handled_popups": popup_events,
            }

        return self._executor.submit(operation).result()

    def set_incidence_angle(
        self, theta_deg: float, phi_deg: float, *, confirm: bool
    ) -> dict[str, Any]:
        """Rebuild and verify the two periodic scan parameters as one locked operation."""
        if not confirm:
            raise CSTRFError(
                ErrorCode.CONFIRMATION_REQUIRED, "scan-angle change requires confirm=true"
            )
        if (
            not math.isfinite(theta_deg)
            or not math.isfinite(phi_deg)
            or not 0 <= theta_deg < 90
            or not 0 <= phi_deg < 360
        ):
            raise CSTRFError(
                ErrorCode.INVALID_ARGUMENT, "scan angles must satisfy 0<=theta<90 and 0<=phi<360"
            )
        theta = format(theta_deg, ".12g")
        phi = format(phi_deg, ".12g")

        def operation() -> dict[str, Any]:
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            if bool(model.is_solver_running(timeout=5)):
                raise CSTRFError(ErrorCode.SOLVER_BUSY, "cannot change scan angles while solving")
            model.allow_history_commands()
            boundary = model.Boundary
            if not all(
                str(getattr(boundary, f"Get{name}")(timeout=5)) in {"unit cell", "periodic"}
                for name in ("Xmin", "Xmax", "Ymin", "Ymax")
            ):
                raise CSTRFError(
                    ErrorCode.INVALID_ARGUMENT, "scan angles require periodic x/y boundaries"
                )
            port = model.FloquetPort
            port.Port("Zmax")
            if not bool(port.IsPortAtZmax(timeout=5)):
                raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "Zmax Floquet port is required")
            originals: dict[str, str] = {}
            for index in range(int(model.GetNumberOfParameters())):
                name = str(model.GetParameterName(index))
                if name in {"theta", "phi"}:
                    originals[name] = str(model.GetParameterSValue(index))
            if set(originals) != {"theta", "phi"}:
                raise CSTRFError(
                    ErrorCode.INVALID_ARGUMENT, "theta and phi parameters must already exist"
                )
            popup_handler = self._popup_handler()

            def apply(expressions: dict[str, str]) -> None:
                model.StoreParameter("theta", expressions["theta"])
                model.StoreParameter("phi", expressions["phi"])
                model.full_history_rebuild()

            try:
                if popup_handler is None:
                    apply({"theta": theta, "phi": phi})
                else:
                    with popup_handler:
                        apply({"theta": theta, "phi": phi})
                active, observed_theta, observed_phi, direction = boundary.GetUnitCellScanAngle(
                    timeout=5
                )
                if (
                    not active
                    or not math.isclose(float(observed_theta), theta_deg, abs_tol=1e-8)
                    or not math.isclose(float(observed_phi), phi_deg, abs_tol=1e-8)
                ):
                    raise CSTRFError(
                        ErrorCode.BACKEND_UNAVAILABLE, "CST scan-angle readback disagrees"
                    )
            except Exception:
                try:
                    rollback_handler = self._popup_handler()
                    if rollback_handler is None:
                        apply(originals)
                    else:
                        with rollback_handler:
                            apply(originals)
                except Exception as rollback_exc:
                    raise CSTRFError(
                        ErrorCode.BACKEND_UNAVAILABLE,
                        f"scan-angle write and rollback were not proven: {rollback_exc}",
                    ) from rollback_exc
                raise
            return {
                "theta_deg": float(observed_theta),
                "phi_deg": float(observed_phi),
                "direction": int(direction),
                "rebuilt": True,
                "saved": False,
                "handled_popups": popup_handler.events if popup_handler is not None else [],
            }

        return self._executor.submit(operation).result()

    def set_floquet_polarization_basis(self, basis: str, *, confirm: bool) -> dict[str, Any]:
        """Write a fixed Floquet basis template and verify mode names on Zmax."""
        if not confirm:
            raise CSTRFError(
                ErrorCode.CONFIRMATION_REQUIRED, "polarization change requires confirm=true"
            )
        if basis not in {"linear", "circular"}:
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "basis must be linear or circular")

        def operation() -> dict[str, Any]:
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            if bool(model.is_solver_running(timeout=5)):
                raise CSTRFError(ErrorCode.SOLVER_BUSY, "cannot change polarization while solving")
            model.allow_history_commands()
            boundary = model.Boundary
            if not all(
                str(getattr(boundary, f"Get{name}")(timeout=5)) in {"unit cell", "periodic"}
                for name in ("Xmin", "Xmax", "Ymin", "Ymax")
            ):
                raise CSTRFError(
                    ErrorCode.INVALID_ARGUMENT,
                    "polarization change requires periodic x/y boundaries",
                )
            port = model.FloquetPort
            port.Port("Zmax")
            if (
                not bool(port.IsPortAtZmax(timeout=5))
                or int(port.GetNumberOfModesConsidered(timeout=5)) < 2
            ):
                raise CSTRFError(
                    ErrorCode.INVALID_ARGUMENT, "two considered Zmax Floquet modes are required"
                )

            def read_basis() -> tuple[str, list[str]]:
                names = []
                for number in (1, 2):
                    found, name = port.GetModeNameByNumber(number, timeout=5)
                    if not found:
                        raise CSTRFError(
                            ErrorCode.BACKEND_UNAVAILABLE, "Floquet mode readback is missing"
                        )
                    names.append(str(name))
                if names == ["TE(0,0)", "TM(0,0)"]:
                    return "linear", names
                if set(names) == {"RCP(0,0)", "LCP(0,0)"}:
                    return "circular", names
                return "unknown", names

            original, before = read_basis()
            if original == "unknown":
                raise CSTRFError(
                    ErrorCode.BACKEND_UNAVAILABLE, "unknown initial Floquet basis; no safe rollback"
                )
            if original == basis:
                return {"basis": basis, "mode_names": before, "changed": False}

            def apply(value: str) -> list[dict[str, Any]]:
                handler = self._popup_handler()
                code = history_vba.floquet_polarization_basis("Zmax", value)
                if handler is None:
                    model.add_to_history("Set Zmax Floquet polarization basis", code)
                    model.full_history_rebuild()
                    return []
                with handler:
                    model.add_to_history("Set Zmax Floquet polarization basis", code)
                    model.full_history_rebuild()
                return handler.events

            try:
                popup_events = apply(basis)
                port.Port("Zmax")
                actual, names = read_basis()
                if actual != basis:
                    raise CSTRFError(
                        ErrorCode.BACKEND_UNAVAILABLE, "Floquet basis write did not persist"
                    )
            except Exception:
                try:
                    apply(original)
                    port.Port("Zmax")
                    reverted, _ = read_basis()
                    if reverted != original:
                        raise CSTRFError(
                            ErrorCode.BACKEND_UNAVAILABLE, "Floquet rollback readback disagrees"
                        )
                except Exception as rollback_exc:
                    raise CSTRFError(
                        ErrorCode.BACKEND_UNAVAILABLE,
                        f"polarization write and rollback were not proven: {rollback_exc}",
                    ) from rollback_exc
                raise
            return {
                "basis": actual,
                "mode_names": names,
                "changed": True,
                "rebuilt": True,
                "saved": False,
                "handled_popups": popup_events,
            }

        return self._executor.submit(operation).result()

    def start_solver(self, *, confirm: bool) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if not confirm:
                raise CSTRFError(
                    ErrorCode.CONFIRMATION_REQUIRED, "solver start requires confirm=true"
                )
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            if bool(model.is_solver_running(timeout=5)):
                raise CSTRFError(ErrorCode.SOLVER_BUSY, "solver is already running")
            baseline_run = model.get_solver_run_info(timeout=5)
            result = model.start_solver(timeout=10)
            running = bool(model.is_solver_running(timeout=5))
            current_run = model.get_solver_run_info(timeout=5) if running else None
            return {
                "submitted": True,
                "result": str(result) if result else "ok",
                "baseline_run_info": baseline_run,
                "observed_running": running,
                "current_run_info": current_run,
            }

        return self._executor.submit(operation).result()

    def solver_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            running = model.is_solver_running(timeout=5)
            run_info = model.get_solver_run_info(timeout=5)
            return {
                "running": bool(running),
                "state": "running" if running else "idle",
                "run_info": run_info,
            }

        return self._executor.submit(operation).result()

    def stop_solver(self, *, confirm: bool) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if not confirm:
                raise CSTRFError(
                    ErrorCode.CONFIRMATION_REQUIRED, "solver stop requires confirm=true"
                )
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            if self._auto_handle_popups and self._pid is not None and self._project_path:
                with KnownAbortConfirmationHandler(
                    self._pid, Path(self._project_path).stem
                ) as handler:
                    try:
                        result = self._project.model3d.abort_solver(timeout=45)
                    except Exception as exc:
                        if any(event.get("action") == "unhandled" for event in handler.events):
                            raise CSTRFError(
                                ErrorCode.POPUP_REQUIRES_INPUT,
                                "CST displayed an abort dialog that failed exact verification",
                                details={"handled_popups": handler.events},
                            ) from exc
                        if handler.events:
                            raise CSTRFError(
                                ErrorCode.BACKEND_UNAVAILABLE,
                                "CST abort Yes was invoked, but the API outcome is unverified",
                                details={"handled_popups": handler.events},
                            ) from exc
                        raise
                events = handler.events
                if any(event.get("action") == "unhandled" for event in events):
                    raise CSTRFError(
                        ErrorCode.POPUP_REQUIRES_INPUT,
                        "CST displayed an abort dialog that failed exact verification",
                        details={"handled_popups": events},
                    )
            else:
                result = self._project.model3d.abort_solver(timeout=30)
                events = []
            return {
                "stop_requested": True,
                "result": str(result) if result else "ok",
                "handled_popups": events,
            }

        return self._executor.submit(operation).result()

    def add_to_history(self, label: str, code: str, *, confirm: bool) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if not confirm:
                raise CSTRFError(
                    ErrorCode.CONFIRMATION_REQUIRED,
                    "History model changes require confirm=true",
                )
            if self._project is None:
                raise CSTRFError(ErrorCode.SESSION_NOT_ATTACHED, "no CST project is attached")
            model = self._project.model3d
            if bool(model.is_solver_running(timeout=5)):
                raise CSTRFError(
                    ErrorCode.SOLVER_BUSY, "cannot change the model while solver is running"
                )
            popup_handler = self._popup_handler()
            if popup_handler is None:
                model.add_to_history(label, code)
                popup_events: list[dict[str, Any]] = []
            else:
                with popup_handler:
                    model.add_to_history(label, code)
                popup_events = popup_handler.events
            return {"label": label, "applied": True, "handled_popups": popup_events}

        return self._executor.submit(operation).result()
