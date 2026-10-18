"""B2: tests for the two tools. No API key or model is needed."""

import pytest

from tools import calculate, lookup


# ------------------------- lookup tests -------------------------

def test_lookup_2025_population():
    result = lookup("Brightwater", "population", 2025)
    assert result["value"] == 44675
    assert result["unit"] == "residents"
    assert "NR-05" in result["source_ids"]


def test_lookup_corrected_area():
    result = lookup("Brightwater", "area", 2025)
    assert result["value"] == 921.4
    assert result["source_ids"] == ["NR-05", "NR-16"]


def test_lookup_misspelled_district():
    result = lookup("Ossbrige", "population", 2025)
    assert "error" in result
    assert result["error"] == "District not found"


def test_lookup_similar_district_names():
    bridge = lookup("Ossbridge", "population", 2025)
    ford = lookup("Ossford", "population", 2025)
    assert bridge["value"] == 52904
    assert ford["value"] == 30982
    assert bridge["source_ids"] == ["NR-01"]
    assert ford["source_ids"] == ["NR-02"]


def test_lookup_archived_year_cannot_replace_current():
    assert "error" in lookup("Tarnvale", "population", 2019)
    result = lookup("Tarnvale", "population", 2025)
    assert result["value"] == 71388
    assert result["source_ids"] == ["NR-03"]


def test_lookup_water_units_are_normalized():
    result = lookup("Lindenmoor", "water_use", 2025)
    assert result["value"] == pytest.approx(2151.4)
    assert result["unit"] == "megalitres"
    assert "NR-08" in result["source_ids"]


def test_lookup_rejects_unsupported_year_or_field():
    assert "error" in lookup("Tarnvale", "area", 2020)
    assert "error" in lookup("Tarnvale", "unknown_field", 2025)


# ----------------------- calculate tests ------------------------

def test_calculate_required_multiplication():
    result = calculate("48317 * 1.0947")
    assert result["value"] == pytest.approx(48317 * 1.0947)


def test_calculate_population_density():
    result = calculate("44675 / 921.4")
    assert result["value"] == pytest.approx(48.48599956587801)


def test_calculate_parentheses_and_subtraction():
    assert calculate("(10 + 5) * 2 - 3")["value"] == 27


def test_calculate_division_by_zero():
    assert calculate("10 / 0")["error"] == "Division by zero"


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo hi')",
    "(1).__class__",
    "9**9**9",
])
def test_calculate_rejects_unsafe_expressions(expression):
    result = calculate(expression)
    assert "error" in result
    assert "value" not in result


def test_calculate_rejects_huge_result():
    result = calculate("1000000000 * 1000000000")
    assert result["error"] == "Result exceeds allowed limits"


def test_calculate_rejects_invalid_input_type():
    assert calculate(None)["error"] == "Invalid arguments"
