from pathlib import Path

import pytest

from cst_rf.core.backends.results import ResultsBackend
from cst_rf.errors import CSTRFError, ErrorCode


class FakeResultItem:
    treepath = r"1D Results\S-Parameters\S1,1"
    run_id = 7
    title = "S1,1"
    xlabel = "Frequency / GHz"
    ylabel = "S-Parameter"

    @staticmethod
    def get_xdata() -> list[float]:
        return [1.0, 2.0, 3.0]

    @staticmethod
    def get_ydata() -> list[complex]:
        return [1 + 0j, 0.5 + 0.5j, 0j]


class FakeResultModule:
    @staticmethod
    def get_tree_items(*, filter: str) -> list[str]:
        assert filter == "0D/1D"
        return [FakeResultItem.treepath]

    @staticmethod
    def get_run_ids(tree_path: str) -> list[int]:
        assert tree_path == FakeResultItem.treepath
        return [0, 7]

    @staticmethod
    def get_result_item(tree_path: str, *, run_id: int, load_impedances: bool) -> FakeResultItem:
        assert tree_path == FakeResultItem.treepath
        assert run_id == 7
        assert load_impedances is True
        return FakeResultItem()


class FakeProject:
    @staticmethod
    def get_3d() -> FakeResultModule:
        return FakeResultModule()

    @staticmethod
    def get_schematic() -> FakeResultModule:
        return FakeResultModule()


class FakeFactory:
    def __init__(self) -> None:
        self.allow_interactive: bool | None = None

    def __call__(self, path: str, *, allow_interactive: bool) -> FakeProject:
        assert Path(path).is_file()
        self.allow_interactive = allow_interactive
        return FakeProject()


def test_list_results_is_noninteractive(tmp_path: Path) -> None:
    project = tmp_path / "saved.cst"
    project.write_bytes(b"project")
    factory = FakeFactory()
    result = ResultsBackend(factory).list_results(project)
    assert factory.allow_interactive is False
    assert result["count"] == 1
    assert result["items"][0]["run_ids"] == [0, 7]


def test_read_complex_result_preserves_raw_and_derives_values(tmp_path: Path) -> None:
    project = tmp_path / "saved.cst"
    project.write_bytes(b"project")
    result = ResultsBackend(FakeFactory()).read_1d(
        project,
        FakeResultItem.treepath,
        run_id=7,
    )
    assert result["real"] == [1.0, 0.5, 0.0]
    assert result["imag"] == [0.0, 0.5, 0.0]
    assert result["magnitude"][1] == pytest.approx(2**-0.5)
    assert result["magnitude_db"][1] == pytest.approx(-3.01029995664)
    assert result["magnitude_db"][2] is None
    assert result["phase_deg"][1] == pytest.approx(45.0)


def test_invalid_result_filter_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "saved.cst"
    project.write_bytes(b"project")
    with pytest.raises(CSTRFError) as caught:
        ResultsBackend(FakeFactory()).list_results(project, filter_type="all")
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT
