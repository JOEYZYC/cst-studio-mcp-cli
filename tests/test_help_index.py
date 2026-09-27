from pathlib import Path

from cst_rf.core.help.indexer import HelpIndex


def test_help_index_build_and_search(tmp_path: Path) -> None:
    root = tmp_path / "Online Help"
    root.mkdir()
    (root / "port.html").write_text(
        "<html><head><title>Waveguide Port</title></head>"
        "<body><nav>ignore</nav><p>Configure a waveguide port.</p></body></html>",
        encoding="utf-8",
    )
    index = HelpIndex(tmp_path / "work" / "help")
    built = index.build(root)
    assert built["topics"] == 1
    hits = index.search("waveguide")
    assert hits[0]["title"] == "Waveguide Port"
    assert "waveguide" in hits[0]["snippet"].lower()


def test_help_index_rebuild_is_atomic(tmp_path: Path) -> None:
    root = tmp_path / "Online Help"
    root.mkdir()
    (root / "one.html").write_text("<title>one</title><p>first</p>", encoding="utf-8")
    index = HelpIndex(tmp_path / "help")
    index.build(root)
    (root / "two.html").write_text("<title>two</title><p>second</p>", encoding="utf-8")
    index.build(root)
    assert index.search("second")[0]["title"] == "two"
