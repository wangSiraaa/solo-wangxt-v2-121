from app.core import evaluate_plan
from app.seed_data import PLANS, TRIALS


def test_volume_to_mass_conversion_and_gap_balance():
    trial = TRIALS[0]
    request = PLANS["OFFLINE-GOOD-01"]
    result = evaluate_plan(trial, request)

    assert result["ok"] is True
    assert result["basis"] == "mass"
    assert result["curve_basis"] == "volume"
    assert abs(result["source_balance"]["total"] - 100.0) < 1.0e-6
    assert abs(result["target_balance"]["total"] - 100.0) < 1.0e-6
    assert result["gaps"]
    assert result["method"]["applicable_scope"]["no_high_temperature_extrapolation"] is True


def test_missing_high_endpoint_rejects_extrapolation():
    trial = TRIALS[1]
    result = evaluate_plan(trial, {
        "basis": "volume",
        "fractions": [{"name": "越界重段", "start": 55.0, "end": 85.0}],
    })

    assert result["ok"] is False
    assert any(i["code"] == "cut_outside_data" for i in result["issues"])
    assert result["valid_interpolation_range"][1] == 78.0


def test_equal_adjacent_cutpoints_and_overlap():
    trial = TRIALS[2]
    result = evaluate_plan(trial, PLANS["OFFLINE-EQUAL-CUT-03"])

    codes = {i["code"] for i in result["issues"]}
    assert "adjacent_cuts_equal" in codes
    assert "cut_overlap" in codes
    zero = next(f for f in result["fractions"] if f["status"] == "zero_width")
    assert zero["target_yield_percent"] == 0.0
    assert result["source_balance"]["total"] == 100.0


def test_decreasing_curve_is_verification_error():
    trial = {
        **TRIALS[0],
        "code": "BAD-DROP",
        "curve_points": [
            {"recovery": 0.0, "temperature_c": None},
            {"recovery": 2.0, "temperature_c": 50.0},
            {"recovery": 10.0, "temperature_c": 45.0},
            {"recovery": 20.0, "temperature_c": 120.0},
        ],
    }
    result = evaluate_plan(trial, {
        "basis": "volume",
        "fractions": [{"name": "x", "start": 2.0, "end": 10.0}],
    })
    assert result["ok"] is False
    assert any(i["code"] == "temperature_decreasing" for i in result["issues"])


def test_mass_and_volume_cannot_share_axis_without_density():
    trial = {**TRIALS[1], "feed_density": None}
    result = evaluate_plan(trial, {
        "basis": "mass",
        "fractions": [{"name": "x", "start": 3.0, "end": 20.0}],
    })
    assert result["ok"] is False
    assert any(i["code"] == "density_conversion_impossible" for i in result["issues"])
