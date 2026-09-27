from pathlib import Path

import pytest

from cst_rf.core.backends.history_vba import floquet_modes, floquet_polarization_basis
from cst_rf.core.session import ManualSession
from cst_rf.errors import CSTRFError, ErrorCode


class FakeProject:
    def __init__(self, path: str) -> None:
        self.path = path
        self.model3d = FakeModel()


class FakeFloquet:
    def Port(self, port: str) -> None:
        assert port == "Zmax"

    def GetNumberOfModes(self, timeout: int = 0) -> int:
        return 2

    def GetNumberOfModesConsidered(self, timeout: int = 0) -> int:
        return 18

    def IsPortAtZmin(self, timeout: int = 0) -> bool:
        return False

    def IsPortAtZmax(self, timeout: int = 0) -> bool:
        return True

    def GetModeNameByNumber(self, number: int, timeout: int = 0) -> tuple[bool, str]:
        return True, ("TE(0,0)", "TM(0,0)")[number - 1]


class FakeModel:
    FloquetPort = FakeFloquet()

    def allow_history_commands(self) -> None:
        pass


class FakeEnvironment:
    def __init__(self, paths: list[str]) -> None:
        self.paths = paths

    def list_open_projects(self) -> list[str]:
        return self.paths

    def get_open_project(self, path: str) -> FakeProject:
        return FakeProject(path)


class FakeDesignEnvironment:
    def __init__(self) -> None:
        self.environment = FakeEnvironment([r"G:\work\working.cst"])

    def connect(self, pid: int) -> FakeEnvironment:
        assert pid == 1234
        return self.environment

    def running_design_environments(self) -> list[int]:
        return [1234]


class FakeInterface:
    DesignEnvironment = FakeDesignEnvironment()

    @staticmethod
    def running_design_environments() -> list[int]:
        return [1234]


def test_list_instances_does_not_start_environment() -> None:
    session = ManualSession(FakeInterface)
    assert session.list_instances() == [1234]


def test_explicit_connect_verifies_expected_path() -> None:
    session = ManualSession(FakeInterface)
    result = session.connect(1234, Path(r"G:\work\working.cst"))
    assert result["pid"] == 1234
    assert result["project_handle"] is True
    assert result["open_projects"] == [r"G:\work\working.cst"]
    assert session.disconnect()["closed_cst"] is False


def test_floquet_info_uses_explicit_history_capability() -> None:
    session = ManualSession(FakeInterface)
    session.connect(1234, Path(r"G:\work\working.cst"))
    assert session.floquet_info() == {
        "port": "Zmax",
        "GetNumberOfModes": 2,
        "GetNumberOfModesConsidered": 18,
        "IsPortAtZmin": False,
        "IsPortAtZmax": True,
        "mode_names": [
            {"number": 1, "name": "TE(0,0)"},
            {"number": 2, "name": "TM(0,0)"},
        ],
        "polarization_basis": "linear",
    }


def test_floquet_modes_template_rejects_unsafe_inputs() -> None:
    assert '.Port "Zmax"' in floquet_modes("Zmax", 3)
    assert '.SetNumberOfModesConsidered "3"' in floquet_modes("Zmax", 3)
    with pytest.raises(CSTRFError, match="Floquet"):
        floquet_modes("Zmax\n.Reset", 3)
    assert '.SetUseCircularPolarization "True"' in floquet_polarization_basis("Zmax", "circular")
    with pytest.raises(CSTRFError, match="Floquet"):
        floquet_polarization_basis("Zmax", "circular\nShell")


def test_floquet_mode_write_requires_readback() -> None:
    class Floquet:
        count = 2

        def Port(self, port: str) -> None:
            assert port == "Zmax"

        def GetNumberOfModesConsidered(self, timeout: int = 0) -> int:
            return self.count

    class Model:
        FloquetPort = Floquet()
        history_calls: list[tuple[str, str]] = []

        def is_solver_running(self, timeout: int = 0) -> bool:
            return False

        def allow_history_commands(self) -> None:
            pass

        def add_to_history(self, label: str, code: str) -> None:
            self.history_calls.append((label, code))
            self.FloquetPort.count = 3

    session = ManualSession()
    session._project = type("Project", (), {"model3d": Model()})()
    assert session.set_floquet_modes(3, confirm=True)["modes_considered"] == 3
    assert session.set_floquet_modes(3, confirm=True)["changed"] is False
    assert len(session._project.model3d.history_calls) == 1
    session._project.model3d.FloquetPort.count = 2
    session._project.model3d.add_to_history = lambda _label, _code: None
    with pytest.raises(CSTRFError) as caught:
        session.set_floquet_modes(3, confirm=True)
    assert caught.value.code == ErrorCode.BACKEND_UNAVAILABLE


def test_confirmed_parameter_rebuild_validates_and_reads_back() -> None:
    class Model:
        expression = "0"
        rebuild_count = 0

        def is_solver_running(self, timeout: int = 0) -> bool:
            return False

        def allow_history_commands(self) -> None:
            pass

        def StoreParameter(self, name: str, value: str) -> None:
            assert name == "theta"
            self.expression = value

        def full_history_rebuild(self) -> None:
            self.rebuild_count += 1

        def GetNumberOfParameters(self) -> int:
            return 1

        def GetParameterName(self, index: int) -> str:
            assert index == 0
            return "theta"

        def GetParameterSValue(self, index: int) -> str:
            assert index == 0
            return self.expression

    model = Model()
    session = ManualSession()
    session._project = type("Project", (), {"model3d": model})()
    result = session.set_parameter("theta", "1", confirm=True, rebuild=True)
    assert result["rebuilt"] is True
    assert result["readback"] == "1"
    assert result["saved"] is False
    assert model.rebuild_count == 1
    with pytest.raises(CSTRFError) as caught:
        session.set_parameter("theta", '1"\nShell', confirm=True, rebuild=True)
    assert caught.value.code == ErrorCode.INVALID_ARGUMENT
    assert model.rebuild_count == 1


def test_project_save_is_confirmed_and_checks_attached_identity(tmp_path: Path) -> None:
    working = tmp_path / "working.cst"
    working.write_bytes(b"before")

    class Model:
        def is_solver_running(self, timeout: int = 0) -> bool:
            return False

    class Project:
        def __init__(self) -> None:
            self.model3d = Model()
            self.path = working
            self.save_calls: list[tuple[bool, bool]] = []

        def filename(self) -> str:
            return str(self.path)

        def save(self, *, include_results: bool, allow_overwrite: bool) -> None:
            self.save_calls.append((include_results, allow_overwrite))
            working.write_bytes(b"after")

    session = ManualSession()
    session._project = Project()
    session._project_path = str(working)
    with pytest.raises(CSTRFError) as denied:
        session.save_project(confirm=False)
    assert denied.value.code == ErrorCode.CONFIRMATION_REQUIRED
    assert session.save_project(confirm=True)["saved"] is True
    assert working.read_bytes() == b"after"
    assert session._project.save_calls == [(True, True)]
    session._project.path = tmp_path / "different.cst"
    with pytest.raises(CSTRFError) as mismatch:
        session.save_project(confirm=True)
    assert mismatch.value.code == ErrorCode.PROJECT_IDENTITY_MISMATCH


def test_periodic_boundary_scan_angles_are_read_live() -> None:
    class Boundary:
        def __getattr__(self, name: str) -> object:
            if name.startswith("Get"):
                return lambda timeout=0: "unit cell"
            raise AttributeError(name)

        def GetUnitCellScanAngle(self, timeout: int = 0) -> tuple[bool, float, float, int]:
            return True, 12.0, 34.0, -1

    class Model:
        def __init__(self) -> None:
            self.Boundary = Boundary()

        def allow_history_commands(self) -> None:
            pass

    session = ManualSession()
    session._project = type("Project", (), {"model3d": Model()})()
    assert session.boundaries()["scan_angle"] == {
        "active": True,
        "theta_deg": 12.0,
        "phi_deg": 34.0,
        "direction": -1,
    }


def test_incidence_angle_write_verifies_scan_and_rolls_back_on_mismatch() -> None:
    class Boundary:
        def __init__(self, model: object) -> None:
            self.model = model

        def __getattr__(self, name: str) -> object:
            if name in {"GetXmin", "GetXmax", "GetYmin", "GetYmax"}:
                return lambda timeout=0: "unit cell"
            raise AttributeError(name)

        def GetUnitCellScanAngle(self, timeout: int = 0) -> tuple[bool, float, float, int]:
            model = self.model
            return (
                True,
                float(model.parameters["theta"]),  # type: ignore[attr-defined]
                float(model.parameters["phi"]) + (1 if model.bad_readback else 0),  # type: ignore[attr-defined]
                -1,
            )

    class Port:
        def Port(self, name: str) -> None:
            assert name == "Zmax"

        def IsPortAtZmax(self, timeout: int = 0) -> bool:
            return True

    class Model:
        def __init__(self) -> None:
            self.parameters = {"theta": "0", "phi": "0"}
            self.Boundary = Boundary(self)
            self.FloquetPort = Port()
            self.rebuild_count = 0
            self.bad_readback = False

        def is_solver_running(self, timeout: int = 0) -> bool:
            return False

        def allow_history_commands(self) -> None:
            pass

        def GetNumberOfParameters(self) -> int:
            return 2

        def GetParameterName(self, index: int) -> str:
            return ("theta", "phi")[index]

        def GetParameterSValue(self, index: int) -> str:
            return self.parameters[self.GetParameterName(index)]

        def StoreParameter(self, name: str, value: str) -> None:
            self.parameters[name] = value

        def full_history_rebuild(self) -> None:
            self.rebuild_count += 1

    model = Model()
    session = ManualSession()
    session._project = type("Project", (), {"model3d": model})()
    result = session.set_incidence_angle(5.0, 10.0, confirm=True)
    assert (result["theta_deg"], result["phi_deg"], result["direction"]) == (5.0, 10.0, -1)
    assert result["saved"] is False
    session.set_incidence_angle(0.0, 0.0, confirm=True)
    assert model.parameters == {"theta": "0", "phi": "0"}
    assert model.rebuild_count == 2

    model.bad_readback = True
    with pytest.raises(CSTRFError) as caught:
        session.set_incidence_angle(5.0, 10.0, confirm=True)
    assert caught.value.code == ErrorCode.BACKEND_UNAVAILABLE
    assert model.parameters == {"theta": "0", "phi": "0"}
    assert model.rebuild_count == 4
    with pytest.raises(CSTRFError) as invalid:
        session.set_incidence_angle(90.0, 0.0, confirm=True)
    assert invalid.value.code == ErrorCode.INVALID_ARGUMENT


def test_floquet_polarization_basis_requires_mode_name_readback() -> None:
    class Boundary:
        def __getattr__(self, name: str) -> object:
            if name in {"GetXmin", "GetXmax", "GetYmin", "GetYmax"}:
                return lambda timeout=0: "unit cell"
            raise AttributeError(name)

    class Port:
        basis = "linear"

        def Port(self, name: str) -> None:
            assert name == "Zmax"

        def IsPortAtZmax(self, timeout: int = 0) -> bool:
            return True

        def GetNumberOfModesConsidered(self, timeout: int = 0) -> int:
            return 2

        def GetModeNameByNumber(self, number: int, timeout: int = 0) -> tuple[bool, str]:
            names = ("TE(0,0)", "TM(0,0)") if self.basis == "linear" else ("RCP(0,0)", "LCP(0,0)")
            return True, names[number - 1]

    class Model:
        def __init__(self) -> None:
            self.Boundary = Boundary()
            self.FloquetPort = Port()
            self.apply_enabled = True
            self.rebuild_count = 0

        def is_solver_running(self, timeout: int = 0) -> bool:
            return False

        def allow_history_commands(self) -> None:
            pass

        def add_to_history(self, label: str, code: str) -> None:
            if self.apply_enabled:
                self.FloquetPort.basis = "circular" if '"True"' in code else "linear"

        def full_history_rebuild(self) -> None:
            self.rebuild_count += 1

    model = Model()
    session = ManualSession()
    session._project = type("Project", (), {"model3d": model})()
    changed = session.set_floquet_polarization_basis("circular", confirm=True)
    assert changed["basis"] == "circular"
    assert changed["rebuilt"] is True
    assert changed["mode_names"] == ["RCP(0,0)", "LCP(0,0)"]
    assert session.set_floquet_polarization_basis("linear", confirm=True)["basis"] == "linear"
    model.apply_enabled = False
    with pytest.raises(CSTRFError) as mismatch:
        session.set_floquet_polarization_basis("circular", confirm=True)
    assert mismatch.value.code == ErrorCode.BACKEND_UNAVAILABLE
    assert model.FloquetPort.basis == "linear"
    assert model.rebuild_count == 4
    with pytest.raises(CSTRFError) as denied:
        session.set_floquet_polarization_basis("circular", confirm=False)
    assert denied.value.code == ErrorCode.CONFIRMATION_REQUIRED


class AutoProject(FakeProject):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.activated = False
        self.closed = False

    def activate(self) -> None:
        self.activated = True

    def close(self) -> None:
        self.closed = True


class AutoEnvironment:
    def __init__(self) -> None:
        self.paths: list[str] = []
        self.project: AutoProject | None = None
        self.quiet_values: list[bool] = []
        self.closed = False

    def list_open_projects(self) -> list[str]:
        return self.paths

    def open_project(self, path: str) -> AutoProject:
        self.paths.append(path)
        self.project = AutoProject(path)
        return self.project

    def get_open_project(self, path: str) -> AutoProject:
        return self.project or AutoProject(path)

    def pid(self) -> int:
        return 5678

    def set_quiet_mode(self, enabled: bool) -> None:
        self.quiet_values.append(enabled)

    def close(self) -> None:
        self.closed = True


class AutoDesignEnvironment:
    environment = AutoEnvironment()

    @classmethod
    def new(cls) -> AutoEnvironment:
        return cls.environment


class AutoInterface:
    DesignEnvironment = AutoDesignEnvironment

    @staticmethod
    def running_design_environments() -> list[int]:
        return []


def test_automatic_session_opens_handles_and_closes_project() -> None:
    environment = AutoDesignEnvironment.environment
    session = ManualSession(
        AutoInterface,
        auto_launch=True,
        auto_open_project=True,
        auto_close_project=True,
        auto_close_environment=True,
        auto_handle_popups=True,
    )
    path = Path(r"G:\work\automatic.cst")

    connected = session.connect(None, path)
    disconnected = session.disconnect()

    assert connected["pid"] == 5678
    assert connected["opened_project"] is True
    assert connected["created_environment"] is True
    assert disconnected["closed_project"] is True
    assert disconnected["closed_environment"] is True
    assert environment.quiet_values == [True, False, True, False, True, False]


def test_automatic_disconnect_preserves_user_owned_handles() -> None:
    path = Path(r"G:\work\user-opened.cst")
    environment = AutoEnvironment()
    environment.paths = [str(path)]
    environment.project = AutoProject(str(path))

    class ExistingDesignEnvironment:
        @staticmethod
        def connect(pid: int) -> AutoEnvironment:
            assert pid == 5678
            return environment

    class ExistingInterface:
        DesignEnvironment = ExistingDesignEnvironment

    session = ManualSession(
        ExistingInterface,
        auto_close_project=True,
        auto_close_environment=True,
    )
    connected = session.connect(5678, path)
    disconnected = session.disconnect()

    assert connected["opened_project"] is False
    assert connected["created_environment"] is False
    assert disconnected["closed_project"] is False
    assert disconnected["closed_environment"] is False
    assert environment.project.closed is False
    assert environment.closed is False
