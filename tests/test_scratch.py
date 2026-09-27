from pathlib import Path

import pytest

from cst_rf.core.scratch import prepare_scratch
from cst_rf.errors import CSTRFError, ErrorCode


def test_prepare_scratch_copies_project_and_companion(tmp_path: Path) -> None:
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    companion = tmp_path / "source"
    companion.mkdir()
    (companion / "Model").mkdir()
    (companion / "Model" / "data.bin").write_bytes(b"model")

    scratch = prepare_scratch(source, tmp_path / "work", operation_id="op_001")

    assert scratch.working_project.read_bytes() == b"project"
    assert (scratch.operation_dir / "project" / "working" / "Model" / "data.bin").is_file()
    assert source.read_bytes() == b"project"
    assert (scratch.operation_dir / "source.json").is_file()


def test_prepare_scratch_rejects_locked_source(tmp_path: Path) -> None:
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    companion = tmp_path / "source"
    companion.mkdir()
    (companion / "active.lok").write_text("locked", encoding="utf-8")

    with pytest.raises(CSTRFError) as caught:
        prepare_scratch(source, tmp_path / "work")
    assert caught.value.code is ErrorCode.PROJECT_LOCKED


def test_prepare_scratch_does_not_overwrite_operation(tmp_path: Path) -> None:
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    prepare_scratch(source, tmp_path / "work", operation_id="same")
    with pytest.raises(CSTRFError) as caught:
        prepare_scratch(source, tmp_path / "work", operation_id="same")
    assert caught.value.code is ErrorCode.OVERWRITE_DENIED
