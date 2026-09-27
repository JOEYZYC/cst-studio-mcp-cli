from pathlib import Path

import pytest

from cst_rf.config import Settings


def test_safe_configuration() -> None:
    settings = Settings.from_env(
        {
            "CST_PATH": r"C:\Program Files\CST Studio Suite 2026",
            "CST_WORK_DIR": r"C:\cst-rf-work",
            "CST_CONNECT_MODE": "manual",
            "CST_AUTO_LAUNCH": "0",
        }
    )
    assert settings.connect_mode == "manual"
    assert settings.auto_launch is False
    assert settings.python_lib_path == Path(
        r"C:\Program Files\CST Studio Suite 2026\AMD64\python_cst_libraries"
    )


def test_unconfigured_install_uses_conventional_windows_path_without_connecting() -> None:
    settings = Settings.from_env({})
    assert settings.connect_mode == "manual"
    assert settings.auto_launch is False
    assert settings.allow_high_risk is False
    assert settings.cst_path.name == "CST Studio Suite 2026"


def test_automatic_configuration_requires_high_risk_opt_in() -> None:
    env = {"CST_CONNECT_MODE": "auto", "CST_AUTO_LAUNCH": "1"}
    with pytest.raises(ValueError):
        Settings.from_env(env)


def test_automatic_configuration_is_available_with_high_risk_opt_in() -> None:
    settings = Settings.from_env(
        {
            "CST_CONNECT_MODE": "auto",
            "CST_AUTO_LAUNCH": "1",
            "CST_AUTO_OPEN_PROJECT": "1",
            "CST_AUTO_SWITCH_PROJECT": "1",
            "CST_AUTO_CLOSE_PROJECT": "1",
            "CST_AUTO_CLOSE_ENVIRONMENT": "1",
            "CST_AUTO_HANDLE_POPUPS": "1",
            "CST_ALLOW_HIGH_RISK": "1",
        }
    )
    assert settings.allow_high_risk is True
    assert settings.auto_launch is True
    assert settings.auto_handle_popups is True
    assert settings.result_dialog_policy == "delete_current_keep_cache"
