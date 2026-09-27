from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cst_rf.core import session as session_module
from cst_rf.core.popups import KnownAbortConfirmationHandler, visible_cst_modals
from cst_rf.core.session import ManualSession
from cst_rf.errors import CSTRFError, ErrorCode


def test_abort_confirmation_script_requires_exact_text_and_button_set() -> None:
    path = Path(session_module.__file__).with_name("confirm_abort.ps1")
    script = path.read_text(encoding="utf-8")
    assert "Do you really want to abort this calculation?" in script
    assert "Cancel|No|Yes" in script
    assert "IsWindowEnabled($owner)" in script
    assert "InvokePattern" in script


def test_abort_watcher_records_only_verified_yes() -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"handled": True, "action": "invoke_yes", "pid": 4242}),
            "",
        )

    watcher = KnownAbortConfirmationHandler(4242, "working", runner=runner)
    watcher._confirm(2624062)
    assert watcher.events == [{"handled": True, "action": "invoke_yes", "pid": 4242}]
    assert commands[0][-6:] == [
        "-CstPid",
        "4242",
        "-DialogHwnd",
        "2624062",
        "-ProjectStem",
        "working",
    ]


def test_abort_watcher_never_reports_mismatched_dialog_as_handled() -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "Unrecognized CST dialog message")

    watcher = KnownAbortConfirmationHandler(4242, "working", runner=runner)
    watcher._confirm(2624062)
    assert watcher.events[0]["action"] == "unhandled"


def test_confirmed_stop_uses_exact_dialog_watcher(monkeypatch: pytest.MonkeyPatch) -> None:
    class Handler:
        def __init__(self, pid: int, stem: str) -> None:
            assert (pid, stem) == (4242, "working")
            self.events = [{"handled": True, "action": "invoke_yes"}]

        def __enter__(self) -> Handler:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    class Model:
        timeout: int | None = None

        def abort_solver(self, *, timeout: int) -> bool:
            self.timeout = timeout
            return True

    monkeypatch.setattr(session_module, "KnownAbortConfirmationHandler", Handler)
    model = Model()
    session = ManualSession(auto_handle_popups=True)
    session._project = type("Project", (), {"model3d": model})()
    session._project_path = "C:/scratch/working.cst"
    session._pid = 4242
    result = session.stop_solver(confirm=True)
    assert result["stop_requested"] is True
    assert result["handled_popups"] == [{"handled": True, "action": "invoke_yes"}]
    assert model.timeout == 45


def test_unknown_abort_dialog_requires_manual_input(monkeypatch: pytest.MonkeyPatch) -> None:
    class Handler:
        def __init__(self, pid: int, stem: str) -> None:
            self.events = [{"action": "unhandled"}]

        def __enter__(self) -> Handler:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    class Model:
        def abort_solver(self, *, timeout: int) -> bool:
            return True

    monkeypatch.setattr(session_module, "KnownAbortConfirmationHandler", Handler)
    session = ManualSession(auto_handle_popups=True)
    session._project = type("Project", (), {"model3d": Model()})()
    session._project_path = "C:/scratch/working.cst"
    session._pid = 4242
    with pytest.raises(CSTRFError) as caught:
        session.stop_solver(confirm=True)
    assert caught.value.code == ErrorCode.POPUP_REQUIRES_INPUT


def test_yes_invoked_but_api_timed_out_keeps_popup_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = {"handled": True, "action": "invoke_yes"}

    class Handler:
        def __init__(self, pid: int, stem: str) -> None:
            self.events = [event]

        def __enter__(self) -> Handler:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    class Model:
        def abort_solver(self, *, timeout: int) -> bool:
            raise TimeoutError("Operation timed out")

    monkeypatch.setattr(session_module, "KnownAbortConfirmationHandler", Handler)
    session = ManualSession(auto_handle_popups=True)
    session._project = type("Project", (), {"model3d": Model()})()
    session._project_path = "C:/scratch/working.cst"
    session._pid = 4242
    with pytest.raises(CSTRFError) as caught:
        session.stop_solver(confirm=True)
    assert caught.value.code == ErrorCode.BACKEND_UNAVAILABLE
    assert caught.value.details["handled_popups"] == [event]


def test_visible_cst_modals_detects_disabled_owner_without_clicking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from types import SimpleNamespace

    windows = {
        100: (4242, "[60% ] working - CST Studio Suite 2026", 0),
        101: (4242, "Adaptive Mesh Refinement", 100),
        102: (12345, "Other application's dialog", 100),
    }

    def enumerate_windows(callback: object, context: object) -> None:
        for hwnd in windows:
            callback(hwnd, context)  # type: ignore[operator]

    gui = SimpleNamespace(
        EnumWindows=enumerate_windows,
        IsWindowVisible=lambda hwnd: True,
        GetWindowText=lambda hwnd: windows[hwnd][1],
        GetWindow=lambda hwnd, command: windows[hwnd][2],
        IsWindowEnabled=lambda hwnd: hwnd != 100,
    )
    process = SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (0, windows[hwnd][0]))
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(sys.modules, "win32process", process)
    monkeypatch.setitem(sys.modules, "win32con", SimpleNamespace(GW_OWNER=4))
    assert visible_cst_modals(4242, "working") == [
        {"hwnd": 101, "title": "Adaptive Mesh Refinement"}
    ]
