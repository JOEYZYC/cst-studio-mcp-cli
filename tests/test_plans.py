from cst_rf.core.workflows.antenna import build_patch_recipe, plan_patch
from cst_rf.core.workflows.metasurface import build_finite_array_recipe, plan_finite_array


def test_patch_plan_has_physical_labels() -> None:
    result = plan_patch(2.45, 4.3, 1.6)
    assert result["model_type"] == "antenna"
    assert result["boundary_type"] == "open"
    assert result["dimensions_mm"]["patch_width"] > 0


def test_finite_array_plan_is_not_unit_cell() -> None:
    result = plan_finite_array(10.0, 4, 6)
    assert result["model_type"] == "finite_array"
    assert result["boundary_type"] == "open"
    assert result["extent_mm"] == {"x": 60.0, "y": 40.0}


def test_patch_recipe_is_validated_and_contains_fixed_history() -> None:
    result = build_patch_recipe(2.45, 4.3, 1.6)
    assert result["validation"]["feed_contacts_patch"] is True
    assert result["model_type"] == "antenna"
    assert "With Brick" in result["history_code"]
    assert "With Port" in result["history_code"]
    assert "With Monitor" in result["history_code"]


def test_finite_array_recipe_uses_open_boundary_and_plane_wave() -> None:
    result = build_finite_array_recipe(
        component="Cell",
        source_shapes=["Ring", "Substrate"],
        period_mm=10,
        rows=2,
        columns=3,
    )
    assert result["copy_count"] == 10
    assert result["model_type"] == "finite_array"
    assert ' .Transform ("Shape", "Translate")' in result["history_code"]
    assert "With PlaneWave" in result["history_code"]
