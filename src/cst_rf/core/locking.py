"""Windows cross-process write lock for one CST project."""

from __future__ import annotations

import hashlib
import msvcrt
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

from cst_rf.errors import CSTRFError, ErrorCode


class ProjectWriteLock:
    def __init__(self, lock_root: Path, project_path: Path) -> None:
        identity = str(project_path.expanduser().resolve()).casefold().encode("utf-8")
        key = hashlib.sha256(identity).hexdigest()
        self.path = lock_root.expanduser().resolve() / f"{key}.lock"
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            handle.close()
            raise CSTRFError(
                ErrorCode.LOCK_CONFLICT,
                f"project is locked by another process: {self.path}",
            ) from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        self._handle.seek(0)
        msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        self._handle.close()
        self._handle = None

    def __enter__(self) -> ProjectWriteLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
