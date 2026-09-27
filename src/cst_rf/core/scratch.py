"""Create immutable-source CST scratch operations."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cst_rf.core.safety import PathPolicy, resolve_source_project, sha256_file
from cst_rf.errors import CSTRFError, ErrorCode


@dataclass(frozen=True, slots=True)
class ScratchProject:
    operation_id: str
    operation_dir: Path
    source_project: Path
    source_sha256: str
    working_project: Path


def _lock_files(source: Path) -> list[Path]:
    companion = source.with_suffix("")
    if not companion.is_dir():
        return []
    return sorted(companion.rglob("*.lok"))


def prepare_scratch(
    source_project: str | Path,
    work_dir: Path,
    *,
    operation_id: str | None = None,
) -> ScratchProject:
    source = resolve_source_project(source_project)
    locks = _lock_files(source)
    if locks:
        raise CSTRFError(
            ErrorCode.PROJECT_LOCKED,
            "source project has CST lock files; close it before copying",
            details={"lock_files": [str(path) for path in locks]},
        )

    source_hash = sha256_file(source)
    policy = PathPolicy(work_dir)
    op_id = operation_id or uuid4().hex
    if not op_id.isascii() or not op_id.replace("-", "").replace("_", "").isalnum():
        raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "invalid operation_id")

    operation_dir = policy.resolve_write(Path("operations") / op_id)
    try:
        operation_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise CSTRFError(
            ErrorCode.OVERWRITE_DENIED,
            f"operation already exists: {op_id}",
        ) from exc

    try:
        project_dir = operation_dir / "project"
        project_dir.mkdir()
        working_project = project_dir / "working.cst"
        shutil.copy2(source, working_project)

        companion = source.with_suffix("")
        if companion.is_dir():
            shutil.copytree(companion, project_dir / "working")

        if sha256_file(source) != source_hash:
            raise CSTRFError(
                ErrorCode.PROJECT_LOCKED,
                "source project changed while it was being copied",
            )

        metadata = {
            "operation_id": op_id,
            "source_project": str(source),
            "source_sha256": source_hash,
            "working_project": str(working_project),
        }
        (operation_dir / "source.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return ScratchProject(
            operation_id=op_id,
            operation_dir=operation_dir,
            source_project=source,
            source_sha256=source_hash,
            working_project=working_project,
        )
    except Exception:
        shutil.rmtree(operation_dir, ignore_errors=True)
        raise
