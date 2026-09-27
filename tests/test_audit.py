import json
from pathlib import Path

from cst_rf.core.audit import AuditLogger


def test_audit_appends_and_redacts(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path)
    path = logger.write("write.begin", token="secret", params={"name": "width"})
    logger.write("write.end", ok=True)

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["write.begin", "write.end"]
    assert records[0]["token"] == "<redacted>"
