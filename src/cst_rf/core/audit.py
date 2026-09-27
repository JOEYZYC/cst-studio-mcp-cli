"""Append-only JSONL audit events."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET_KEYS = {"authorization", "cookie", "password", "secret", "token"}


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 512 else value[:512] + "…"
    if isinstance(value, dict):
        return {
            str(key): "<redacted>"
            if str(key).lower() in _SECRET_KEYS
            else _safe_value(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, Path):
        return str(value)
    return repr(value)[:512]


class AuditLogger:
    def __init__(self, work_dir: Path) -> None:
        self.log_dir = work_dir.expanduser().resolve() / ".cst-rf" / "audit"
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        target = self.log_dir / f"audit-{now:%Y-%m-%d}.jsonl"
        record = {
            "timestamp_utc": now.isoformat(),
            "event": event,
            **{
                key: "<redacted>" if key.lower() in _SECRET_KEYS else _safe_value(value)
                for key, value in fields.items()
            },
        }
        with self._lock, target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return target
