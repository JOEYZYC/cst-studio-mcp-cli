"""Small persistent job state store for solver operations."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4


class JobStore:
    def __init__(self, work_dir: Path) -> None:
        self.root = work_dir.expanduser().resolve() / ".cst-rf" / "jobs"

    def create(self, kind: str, project_path: str) -> dict[str, str]:
        job_id = uuid4().hex
        payload = {
            "job_id": job_id,
            "kind": kind,
            "project_path": project_path,
            "owner_pid": str(os.getpid()),
            "state": "queued",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(job_id).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    def update(self, job_id: str, **fields: object) -> dict[str, object]:
        path = self._path(job_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(fields)
        payload["updated_at"] = datetime.now(UTC).isoformat()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return cast(dict[str, object], payload)

    def get(self, job_id: str) -> dict[str, object]:
        path = self._path(job_id)
        if not path.is_file():
            raise FileNotFoundError(f"job not found: {job_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"invalid job payload: {job_id}")
        return cast(dict[str, object], payload)

    def list_jobs(self) -> list[dict[str, object]]:
        if not self.root.is_dir():
            return []
        jobs: list[dict[str, object]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                jobs.append(cast(dict[str, object], payload))
        return jobs

    def reconcile_stale(self) -> list[dict[str, object]]:
        """Mark jobs from an earlier process as unknown.

        A new MCP process cannot prove that a persisted solver is still the
        same CST operation.  Unknown is deliberately conservative and never
        means completed.
        """
        reconciled: list[dict[str, object]] = []
        for payload in self.list_jobs():
            if payload.get("state") in {"queued", "starting", "running", "stopping"}:
                reconciled.append(
                    self.update(
                        str(payload["job_id"]),
                        state="unknown",
                        reconcile_reason="job observed by a new process; solver state could not be proven",
                    )
                )
        return reconciled

    def _path(self, job_id: str) -> Path:
        if not job_id.isascii() or not job_id.isalnum():
            raise ValueError("invalid job id")
        return self.root / f"{job_id}.json"
