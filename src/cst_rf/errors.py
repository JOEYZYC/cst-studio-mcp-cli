"""Stable errors shared by CLI and MCP frontends."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    PATH_OUTSIDE_WORK_DIR = "PATH_OUTSIDE_WORK_DIR"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PROJECT_LOCKED = "PROJECT_LOCKED"
    OVERWRITE_DENIED = "OVERWRITE_DENIED"
    LOCK_CONFLICT = "LOCK_CONFLICT"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    CST_NOT_RUNNING = "CST_NOT_RUNNING"
    PROJECT_IDENTITY_MISMATCH = "PROJECT_IDENTITY_MISMATCH"
    SESSION_NOT_ATTACHED = "SESSION_NOT_ATTACHED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    SOLVER_BUSY = "SOLVER_BUSY"
    RESULT_NOT_FOUND = "RESULT_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    AUTOMATION_NOT_ALLOWED = "AUTOMATION_NOT_ALLOWED"
    POPUP_REQUIRES_INPUT = "POPUP_REQUIRES_INPUT"


class CSTRFError(RuntimeError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}
