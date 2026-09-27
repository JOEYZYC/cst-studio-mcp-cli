from pathlib import Path

import pytest

from cst_rf.core.safety import PathPolicy, sha256_file
from cst_rf.errors import CSTRFError, ErrorCode


def test_write_path_stays_in_work_dir(tmp_path: Path) -> None:
    policy = PathPolicy(tmp_path / "work")
    assert policy.resolve_write("exports/result.csv").is_relative_to(policy.root)


def test_write_path_escape_is_rejected(tmp_path: Path) -> None:
    policy = PathPolicy(tmp_path / "work")
    with pytest.raises(CSTRFError) as caught:
        policy.resolve_write(tmp_path / "outside.csv")
    assert caught.value.code is ErrorCode.PATH_OUTSIDE_WORK_DIR


def test_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    policy = PathPolicy(tmp_path / "work")
    target = policy.prepare_output("exports/result.csv")
    target.write_text("existing", encoding="utf-8")
    with pytest.raises(CSTRFError) as caught:
        policy.prepare_output(target)
    assert caught.value.code is ErrorCode.OVERWRITE_DENIED


def test_sha256_file(tmp_path: Path) -> None:
    source = tmp_path / "sample.bin"
    source.write_bytes(b"cst-rf")
    assert sha256_file(source) == "325e348be659946382b2f1b0c15420b5188a039195b40f2fe4335426faeff6af"
