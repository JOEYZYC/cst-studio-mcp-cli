"""Minimal filesystem confinement and project fingerprinting."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cst_rf.errors import CSTRFError, ErrorCode


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class PathPolicy:
    """Allow writes only below one configured root."""

    def __init__(self, work_dir: Path) -> None:
        self.root = work_dir.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_write(self, value: str | Path) -> Path:
        raw = str(value)
        if raw.startswith(("\\\\", "//", "\\?\\", "\\.\\")):
            raise CSTRFError(
                ErrorCode.PATH_OUTSIDE_WORK_DIR,
                f"unsupported path form: {value}",
            )
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        target = candidate.resolve()
        if not target.is_relative_to(self.root):
            raise CSTRFError(
                ErrorCode.PATH_OUTSIDE_WORK_DIR,
                f"path is outside CST_WORK_DIR: {target}",
                details={"path": str(target), "work_dir": str(self.root)},
            )
        return target

    def prepare_output(self, value: str | Path, *, overwrite: bool = False) -> Path:
        target = self.resolve_write(value)
        if target.exists() and not overwrite:
            raise CSTRFError(
                ErrorCode.OVERWRITE_DENIED,
                f"refusing to overwrite: {target}",
                details={"path": str(target)},
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        return target


def resolve_source_project(value: str | Path) -> Path:
    source = Path(value).expanduser().resolve()
    if source.suffix.lower() != ".cst":
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "source project must be a .cst file")
    if not source.is_file():
        raise CSTRFError(
            ErrorCode.PROJECT_NOT_FOUND,
            f"source project does not exist: {source}",
        )
    return source
