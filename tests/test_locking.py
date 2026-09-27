from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cst_rf.core.locking import ProjectWriteLock


def _probe(lock_root: Path, project: Path) -> subprocess.CompletedProcess[str]:
    code = (
        "from pathlib import Path; "
        "from cst_rf.core.locking import ProjectWriteLock; "
        f"lock=ProjectWriteLock(Path({str(lock_root)!r}), Path({str(project)!r})); "
        "lock.acquire(); print('acquired'); lock.release()"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_project_lock_is_cross_process(tmp_path: Path) -> None:
    project = tmp_path / "working.cst"
    project.write_bytes(b"project")
    lock_root = tmp_path / "locks"

    with ProjectWriteLock(lock_root, project):
        blocked = _probe(lock_root, project)
        assert blocked.returncode != 0
        assert "project is locked by another process" in blocked.stderr

    acquired = _probe(lock_root, project)
    assert acquired.returncode == 0
    assert acquired.stdout.strip() == "acquired"
