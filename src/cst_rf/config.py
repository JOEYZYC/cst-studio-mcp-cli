"""Environment-backed runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated process configuration without side effects."""

    cst_path: Path
    python_lib_path: Path
    work_dir: Path
    connect_mode: str
    auto_launch: bool
    toolset: str
    allow_high_risk: bool = False
    auto_open_project: bool = False
    auto_switch_project: bool = False
    auto_close_project: bool = False
    auto_close_environment: bool = False
    auto_handle_popups: bool = False
    result_dialog_policy: str = "delete_current_keep_cache"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        cst_path = (
            Path(env.get("CST_PATH", r"C:\Program Files\CST Studio Suite 2026"))
            .expanduser()
            .resolve()
        )
        python_lib = (
            Path(
                env.get(
                    "CST_PYTHON_LIB",
                    str(cst_path / "AMD64" / "python_cst_libraries"),
                )
            )
            .expanduser()
            .resolve()
        )
        work_dir = (
            Path(
                env.get(
                    "CST_WORK_DIR",
                    str(Path.cwd() / ".cst-work"),
                )
            )
            .expanduser()
            .resolve()
        )
        connect_mode = env.get("CST_CONNECT_MODE", "manual").strip().lower()
        if connect_mode not in {"manual", "auto"}:
            raise ValueError("CST_CONNECT_MODE must be 'manual' or 'auto'")
        auto_launch = _env_bool(env.get("CST_AUTO_LAUNCH"), default=False)
        toolset = env.get("CST_TOOLSET", "full").strip().lower() or "full"
        allow_high_risk = _env_bool(env.get("CST_ALLOW_HIGH_RISK"), default=False)
        auto_open_project = _env_bool(env.get("CST_AUTO_OPEN_PROJECT"), default=False)
        auto_switch_project = _env_bool(env.get("CST_AUTO_SWITCH_PROJECT"), default=False)
        auto_close_project = _env_bool(env.get("CST_AUTO_CLOSE_PROJECT"), default=False)
        auto_close_environment = _env_bool(env.get("CST_AUTO_CLOSE_ENVIRONMENT"), default=False)
        auto_handle_popups = _env_bool(env.get("CST_AUTO_HANDLE_POPUPS"), default=False)
        result_dialog_policy = (
            env.get("CST_RESULT_DIALOG_POLICY", "delete_current_keep_cache").strip().lower()
        )
        if result_dialog_policy not in {"delete_current_keep_cache", "cancel"}:
            raise ValueError("unsupported CST_RESULT_DIALOG_POLICY")
        automation_requested = (
            any(
                (
                    auto_launch,
                    auto_open_project,
                    auto_switch_project,
                    auto_close_project,
                    auto_close_environment,
                    auto_handle_popups,
                )
            )
            or connect_mode == "auto"
        )
        if automation_requested and not allow_high_risk:
            raise ValueError("CST_ALLOW_HIGH_RISK must be true for automatic CST actions")
        return cls(
            cst_path=cst_path,
            python_lib_path=python_lib,
            work_dir=work_dir,
            connect_mode=connect_mode,
            auto_launch=auto_launch,
            toolset=toolset,
            allow_high_risk=allow_high_risk,
            auto_open_project=auto_open_project,
            auto_switch_project=auto_switch_project,
            auto_close_project=auto_close_project,
            auto_close_environment=auto_close_environment,
            auto_handle_popups=auto_handle_popups,
            result_dialog_policy=result_dialog_policy,
        )
