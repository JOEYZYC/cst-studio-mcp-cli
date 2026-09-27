import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from cst_rf.config import Settings
from cst_rf.core.jobs import JobStore
from cst_rf.core.session import ManualSession
from cst_rf.errors import CSTRFError, ErrorCode
from cst_rf.service import Service


class RunningSession:
    def __init__(self, project_path: str) -> None:
        self.project_path = project_path

    def inspect_project(self) -> dict[str, object]:
        return {"project_path": self.project_path}

    def solver_status(self) -> dict[str, object]:
        return {"running": True, "state": "running"}


class IdleSession(RunningSession):
    def solver_status(self) -> dict[str, object]:
        return {"running": False, "state": "idle", "run_info": {"state": "ABORTED"}}


class ScriptedSession(RunningSession):
    def __init__(self, statuses: list[dict[str, object]], project_path: str) -> None:
        super().__init__(project_path)
        self.statuses = iter(statuses)

    def solver_status(self) -> dict[str, object]:
        return next(self.statuses)


def test_reconcile_marks_unprovable_solver_jobs_unknown(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = store.create("solver", str(tmp_path / "working.cst"))
    store.update(job["job_id"], state="running")

    reconciled = store.reconcile_stale()

    assert len(reconciled) == 1
    assert reconciled[0]["state"] == "unknown"
    assert store.get(str(job["job_id"]))["state"] == "unknown"


def test_reconcile_does_not_change_completed_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = store.create("solver", str(tmp_path / "working.cst"))
    store.update(job["job_id"], state="completed")

    assert store.reconcile_stale() == []
    assert store.get(str(job["job_id"]))["state"] == "completed"


def test_status_timeout_marks_job_unknown_without_retry(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    service = Service(
        settings, session=cast(ManualSession, RunningSession(str(tmp_path / "working.cst")))
    )
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(
        str(job["job_id"]),
        state="running",
        created_at=(datetime.now(UTC) - timedelta(seconds=30)).isoformat(),
    )

    result = service.call("solve_status", {"job_id": str(job["job_id"]), "timeout_seconds": 1})

    assert result["ok"] is True
    assert result["data"]["timed_out"] is True
    assert service.jobs.get(str(job["job_id"]))["state"] == "unknown"


def test_idle_is_not_proof_of_success(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    service = Service(
        settings, session=cast(ManualSession, IdleSession(str(tmp_path / "working.cst")))
    )
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(job["job_id"], state="running")

    result = service.call("solve_status", {"job_id": str(job["job_id"])})

    assert result["ok"] is True
    assert result["solver_state"] == "unknown"
    assert service.jobs.get(str(job["job_id"]))["state"] == "unknown"
    assert "unverified" in result["warnings"][0]


def test_stopping_job_becomes_stopped_when_idle(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    service = Service(
        settings, session=cast(ManualSession, IdleSession(str(tmp_path / "working.cst")))
    )
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(job["job_id"], state="stopping")

    result = service.call("solve_status", {"job_id": str(job["job_id"])})

    assert result["solver_state"] == "stopped"
    assert service.jobs.get(str(job["job_id"]))["state"] == "stopped"


def test_stop_request_remains_stopping_until_solver_is_idle(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")

    class SwitchingSession(RunningSession):
        running = True

        def solver_status(self) -> dict[str, object]:
            return {
                "running": self.running,
                "state": "running" if self.running else "idle",
                "run_info": {"state": "RUNNING" if self.running else "ABORTED"},
            }

    session = SwitchingSession(str(tmp_path / "working.cst"))
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(job["job_id"], state="stopping")
    active = service.call("solve_status", {"job_id": job["job_id"]})
    assert active["solver_state"] == "stopping"
    assert service.jobs.get(job["job_id"])["state"] == "stopping"
    session.running = False
    stopped = service.call("solve_status", {"job_id": job["job_id"]})
    assert stopped["solver_state"] == "stopped"


def test_stop_request_with_later_success_does_not_count_as_stopped(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    session = ScriptedSession(
        [{"running": False, "state": "idle", "run_info": {"state": "SUCCESS"}}],
        str(tmp_path / "working.cst"),
    )
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(job["job_id"], state="stopping")
    result = service.call("solve_status", {"job_id": job["job_id"]})
    assert result["solver_state"] == "unknown"
    assert any("did not report an aborted final state" in item for item in result["warnings"])


def test_previous_success_does_not_complete_new_job(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    session = ScriptedSession(
        [{"running": False, "state": "idle", "run_info": {"state": "SUCCESS"}}],
        str(tmp_path / "working.cst"),
    )
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(
        job["job_id"],
        state="starting",
        observed_running=False,
        start_result={"baseline_run_info": {"state": "SUCCESS"}},
        created_at=(datetime.now(UTC) - timedelta(seconds=60)).isoformat(),
    )
    result = service.call("solve_status", {"job_id": job["job_id"]})
    assert result["solver_state"] == "unknown"


def test_new_submission_waits_for_solver_to_report_running(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    service = Service(
        settings, session=cast(ManualSession, IdleSession(str(tmp_path / "working.cst")))
    )
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(job["job_id"], state="starting", observed_running=False)

    result = service.call("solve_status", {"job_id": job["job_id"]})

    assert result["solver_state"] == "starting"
    assert service.jobs.get(job["job_id"])["state"] == "starting"


def test_previous_success_remains_unverified_even_when_solver_was_seen(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    session = ScriptedSession(
        [
            {"running": True, "state": "running", "run_info": {"state": "SUCCESS"}},
            {"running": False, "state": "idle", "run_info": {"state": "SUCCESS"}},
        ],
        str(tmp_path / "working.cst"),
    )
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(
        job["job_id"],
        state="running",
        observed_running=False,
        start_result={"baseline_run_info": {"state": "SUCCESS"}},
    )
    service.call("solve_status", {"job_id": job["job_id"]})
    result = service.call("solve_status", {"job_id": job["job_id"]})
    assert result["solver_state"] == "unknown"


def test_observed_run_reports_success_or_failure(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    for outcome, expected in (("SUCCESS", "completed"), ("ERROR", "failed")):
        session = ScriptedSession(
            [
                {"running": True, "state": "running", "run_info": {"state": "RUNNING"}},
                {"running": False, "state": "idle", "run_info": {"state": outcome}},
            ],
            str(tmp_path / "working.cst"),
        )
        service = Service(settings, session=cast(ManualSession, session))
        job = service.jobs.create("solver", str(tmp_path / "working.cst"))
        service.jobs.update(
            job["job_id"],
            state="running",
            observed_running=False,
            start_result={"baseline_run_info": {"state": "SUCCESS"}},
        )
        first = service.call("solve_status", {"job_id": job["job_id"]})
        second = service.call("solve_status", {"job_id": job["job_id"]})
        assert first["solver_state"] == "running"
        assert second["solver_state"] == expected
        assert service.jobs.get(job["job_id"])["state"] == expected


def test_solver_job_cannot_be_attributed_to_another_project(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    service = Service(
        settings, session=cast(ManualSession, IdleSession(str(tmp_path / "other.cst")))
    )
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(job["job_id"], state="running")

    result = service.call("solve_status", {"job_id": job["job_id"]})

    assert result["error"]["code"] == "PROJECT_IDENTITY_MISMATCH"
    assert service.jobs.get(job["job_id"])["state"] == "running"


def test_other_process_cannot_complete_a_running_job_from_old_success(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    session = IdleSession(str(tmp_path / "working.cst"))
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(tmp_path / "working.cst"))
    service.jobs.update(
        job["job_id"],
        state="running",
        owner_pid="-1",
        observed_running=True,
        observed_run_transition=True,
    )

    result = service.call("solve_status", {"job_id": job["job_id"]})

    assert result["solver_state"] == "unknown"
    assert service.jobs.get(job["job_id"])["state"] == "unknown"


def test_ambiguous_stop_error_preserves_unknown_job_without_retry(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    working = settings.work_dir / "operations" / "test" / "project" / "working.cst"
    working.parent.mkdir(parents=True)
    working.write_bytes(b"saved")

    class UnresponsiveSession(RunningSession):
        calls = 0

        def stop_solver(self, *, confirm: bool) -> dict[str, object]:
            assert confirm
            self.calls += 1
            raise TimeoutError("Operation timed out")

    session = UnresponsiveSession(str(working))
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(working))
    service.jobs.update(job["job_id"], state="running")
    result = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})

    assert result["error"]["code"] == "BACKEND_UNAVAILABLE"
    assert service.jobs.get(job["job_id"])["state"] == "unknown"
    assert session.calls == 1


def test_exact_abort_confirmation_is_append_only_audited(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    working = settings.work_dir / "operations" / "test" / "project" / "working.cst"
    working.parent.mkdir(parents=True)
    working.write_bytes(b"saved")

    class ConfirmedStopSession(RunningSession):
        def stop_solver(self, *, confirm: bool) -> dict[str, object]:
            assert confirm
            return {
                "stop_requested": True,
                "handled_popups": [{"title": "CST MICROWAVE STUDIO 2026", "action": "invoke_yes"}],
            }

    service = Service(settings, session=cast(ManualSession, ConfirmedStopSession(str(working))))
    job = service.jobs.create("solver", str(working))
    service.jobs.update(job["job_id"], state="running")
    result = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})
    assert result["ok"] is True
    assert service.jobs.get(job["job_id"])["state"] == "stopping"
    logs = list((settings.work_dir / ".cst-rf" / "audit").glob("*.jsonl"))
    assert any('"event": "popup.handled"' in log.read_text(encoding="utf-8") for log in logs)


def test_abort_confirmation_stays_audited_when_api_times_out(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    working = settings.work_dir / "operations" / "test" / "project" / "working.cst"
    working.parent.mkdir(parents=True)
    working.write_bytes(b"saved")

    class TimedOutSession(RunningSession):
        def stop_solver(self, *, confirm: bool) -> dict[str, object]:
            assert confirm
            raise CSTRFError(
                ErrorCode.BACKEND_UNAVAILABLE,
                "Yes was invoked but CST did not answer",
                details={"handled_popups": [{"action": "invoke_yes"}]},
            )

    service = Service(settings, session=cast(ManualSession, TimedOutSession(str(working))))
    job = service.jobs.create("solver", str(working))
    service.jobs.update(job["job_id"], state="running")
    result = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})
    assert result["error"]["code"] == "BACKEND_UNAVAILABLE"
    assert result["error"]["details"]["handled_popups"] == [{"action": "invoke_yes"}]
    assert service.jobs.get(job["job_id"])["state"] == "unknown"
    logs = list((settings.work_dir / ".cst-rf" / "audit").glob("*.jsonl"))
    assert any('"event": "popup.handled"' in log.read_text(encoding="utf-8") for log in logs)


def test_stop_refuses_solver_startup_before_abort_request(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    working = settings.work_dir / "operations" / "test" / "project" / "working.cst"
    working.parent.mkdir(parents=True)
    working.write_bytes(b"saved")

    class SpySession(RunningSession):
        calls = 0

        def stop_solver(self, *, confirm: bool) -> dict[str, object]:
            self.calls += 1
            return {"stop_requested": True}

    session = SpySession(str(working))
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(working))
    service.jobs.update(job["job_id"], state="running", start_result={"submitted": True})
    result = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})
    assert result["error"]["code"] == "SOLVER_BUSY"
    assert service.jobs.get(job["job_id"])["state"] == "running"
    assert session.calls == 0


def test_stop_refuses_unanswered_mesh_dialog(tmp_path: Path, monkeypatch: object) -> None:
    from cst_rf import service as service_module

    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    working = settings.work_dir / "operations" / "test" / "project" / "working.cst"
    working.parent.mkdir(parents=True)
    working.write_bytes(b"saved")

    class SpySession(RunningSession):
        calls = 0

        def inspect_project(self) -> dict[str, object]:
            return {"project_path": str(working), "pid": 4242}

        def stop_solver(self, *, confirm: bool) -> dict[str, object]:
            self.calls += 1
            return {"stop_requested": True}

    monkeypatch.setattr(  # type: ignore[attr-defined]
        service_module,
        "visible_cst_modals",
        lambda pid, stem: [{"hwnd": 101, "title": "Adaptive Mesh Refinement"}],
    )
    session = SpySession(str(working))
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(working))
    service.jobs.update(
        job["job_id"],
        state="running",
        start_result={"submitted": True},
        created_at=(datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
    )
    result = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})
    assert result["error"]["code"] == "POPUP_REQUIRES_INPUT"
    assert result["error"]["details"]["dialogs"][0]["title"] == "Adaptive Mesh Refinement"
    assert service.jobs.get(job["job_id"])["state"] == "running"
    assert session.calls == 0


def test_stop_waits_for_current_frequency_domain_solver_log(tmp_path: Path) -> None:
    settings = Settings(tmp_path, tmp_path, tmp_path / "work", "manual", False, "full")
    working = settings.work_dir / "operations" / "test" / "project" / "working.cst"
    working.parent.mkdir(parents=True)
    working.write_bytes(b"saved")

    class FdSession(RunningSession):
        calls = 0

        def inspect_project(self) -> dict[str, object]:
            return {"project_path": str(working), "solver_type": "HF Frequency Domain"}

        def stop_solver(self, *, confirm: bool) -> dict[str, object]:
            self.calls += 1
            return {"stop_requested": True, "handled_popups": [{"action": "invoke_yes"}]}

    session = FdSession(str(working))
    service = Service(settings, session=cast(ManualSession, session))
    job = service.jobs.create("solver", str(working))
    service.jobs.update(
        job["job_id"],
        state="running",
        start_result={"submitted": True},
        created_at=(datetime.now(UTC) - timedelta(seconds=15)).isoformat(),
    )
    denied = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})
    assert denied["error"]["code"] == "SOLVER_BUSY"
    assert session.calls == 0

    model_log = working.with_suffix("") / "Result" / "Model.log"
    model_log.parent.mkdir(parents=True)
    model_log.write_text("previous solver", encoding="utf-8")
    old_timestamp = (datetime.now(UTC) - timedelta(seconds=30)).timestamp()
    os.utime(model_log, (old_timestamp, old_timestamp))
    stale = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})
    assert stale["error"]["code"] == "SOLVER_BUSY"
    assert session.calls == 0

    model_log.write_text("solver started", encoding="utf-8")
    accepted = service.call("solve_stop", {"job_id": job["job_id"], "confirm": True})
    assert accepted["ok"] is True
    assert session.calls == 1
