"""Narrow, auditable handling for known CST modal dialogs."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any


class KnownPopupHandler:
    """Handle only explicitly known CST dialogs owned by one process."""

    RESULT_DIALOG_TITLE = "Results May Get Incompatible With Model"

    def __init__(
        self,
        pid: int,
        *,
        result_policy: str = "delete_current_keep_cache",
        poll_seconds: float = 0.1,
    ) -> None:
        if result_policy not in {"delete_current_keep_cache", "cancel"}:
            raise ValueError(f"unsupported CST result dialog policy: {result_policy}")
        self.pid = pid
        self.result_policy = result_policy
        self.poll_seconds = poll_seconds
        self.events: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._handled_windows: set[int] = set()

    def _run(self) -> None:
        try:
            import win32con  # type: ignore[import-untyped]
            import win32gui  # type: ignore[import-untyped]
            import win32process  # type: ignore[import-untyped]
        except ImportError:
            return

        while not self._stop.wait(self.poll_seconds):
            windows: list[tuple[int, str]] = []

            def collect(hwnd: int, _: object) -> None:
                if hwnd in self._handled_windows or not win32gui.IsWindowVisible(hwnd):
                    return
                _, owner_pid = win32process.GetWindowThreadProcessId(hwnd)
                if owner_pid == self.pid:
                    windows.append((hwnd, win32gui.GetWindowText(hwnd)))

            win32gui.EnumWindows(collect, None)
            for hwnd, title in windows:
                if title != self.RESULT_DIALOG_TITLE:
                    continue
                key = (
                    win32con.VK_RETURN
                    if self.result_policy == "delete_current_keep_cache"
                    else win32con.VK_ESCAPE
                )
                win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, key, 0)
                win32gui.PostMessage(hwnd, win32con.WM_KEYUP, key, 0)
                self._handled_windows.add(hwnd)
                self.events.append(
                    {
                        "title": title,
                        "policy": self.result_policy,
                        "action": "accept_default" if key == win32con.VK_RETURN else "cancel",
                    }
                )

    def __enter__(self) -> KnownPopupHandler:
        self._thread = threading.Thread(target=self._run, name="cst-rf-popup", daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        time.sleep(self.poll_seconds)
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


class KnownAbortConfirmationHandler:
    """Invoke Yes only after CST PID, owner, exact message and buttons match."""

    TITLE = "CST MICROWAVE STUDIO 2026"

    def __init__(
        self,
        pid: int,
        project_stem: str,
        *,
        poll_seconds: float = 0.1,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.pid = pid
        self.project_stem = project_stem
        self.poll_seconds = poll_seconds
        self.events: list[dict[str, Any]] = []
        self._runner = runner
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: set[int] = set()

    def _confirm(self, hwnd: int) -> None:
        command = [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(Path(__file__).with_name("confirm_abort.ps1")),
            "-CstPid",
            str(self.pid),
            "-DialogHwnd",
            str(hwnd),
            "-ProjectStem",
            self.project_stem,
        ]
        try:
            completed = self._runner(
                command, capture_output=True, text=True, timeout=12, check=False
            )
            if completed.returncode:
                self.events.append(
                    {"title": self.TITLE, "action": "unhandled", "error": completed.stderr[:512]}
                )
                return
            event = json.loads(completed.stdout)
            if event.get("handled") is not True or event.get("action") != "invoke_yes":
                raise ValueError("abort confirmation script did not verify Yes")
            self.events.append(event)
        except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError) as exc:
            self.events.append(
                {"title": self.TITLE, "action": "unhandled", "error": str(exc)[:512]}
            )

    def _run(self) -> None:
        try:
            import win32gui
            import win32process
        except ImportError as exc:
            self.events.append({"action": "unhandled", "error": str(exc)})
            return

        while not self._stop.wait(self.poll_seconds):
            matches: list[int] = []

            def collect(hwnd: int, _: object) -> None:
                if hwnd in self._seen or not win32gui.IsWindowVisible(hwnd):
                    return
                _, owner_pid = win32process.GetWindowThreadProcessId(hwnd)
                if owner_pid == self.pid and win32gui.GetWindowText(hwnd) == self.TITLE:
                    matches.append(hwnd)

            win32gui.EnumWindows(collect, None)
            for hwnd in matches:
                self._seen.add(hwnd)
                self._confirm(hwnd)

    def __enter__(self) -> KnownAbortConfirmationHandler:
        self._thread = threading.Thread(target=self._run, name="cst-rf-abort-confirm", daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=15.0)
            if self._thread.is_alive():
                raise RuntimeError("CST abort confirmation watcher did not stop")


def visible_cst_modals(pid: int, project_stem: str) -> list[dict[str, str | int]]:
    """Read titles of visible CST-owned dialogs; never interact with them."""
    try:
        import win32con
        import win32gui
        import win32process
    except ImportError as exc:
        raise RuntimeError("Win32 dialog inspection is unavailable") from exc

    candidates: list[tuple[int, str, int]] = []

    def collect(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
        if window_pid == pid:
            candidates.append(
                (
                    hwnd,
                    str(win32gui.GetWindowText(hwnd)),
                    win32gui.GetWindow(hwnd, win32con.GW_OWNER),
                )
            )

    win32gui.EnumWindows(collect, None)
    main_suffix = f"{project_stem} - CST Studio Suite 2026"
    main_handles = {
        hwnd for hwnd, title, owner in candidates if owner == 0 and title.endswith(main_suffix)
    }
    return [
        {"hwnd": hwnd, "title": title}
        for hwnd, title, owner in candidates
        if title and owner in main_handles and not win32gui.IsWindowEnabled(owner)
    ]
