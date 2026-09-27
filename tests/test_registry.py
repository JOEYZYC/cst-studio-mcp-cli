from collections.abc import Mapping
from typing import Any

import pytest

from cst_rf.models import ENVELOPE_SCHEMA, ResultEnvelope
from cst_rf.registry import ToolRegistry, ToolSpec


def _handler(_: Mapping[str, Any]) -> dict[str, Any]:
    return ResultEnvelope(operation="example").to_dict()


def _spec() -> ToolSpec:
    return ToolSpec(
        name="inspect_example",
        description="example",
        risk="read",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema=ENVELOPE_SCHEMA,
        handler=_handler,
    )


def test_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.add(_spec())
    with pytest.raises(ValueError, match="duplicate"):
        registry.add(_spec())
