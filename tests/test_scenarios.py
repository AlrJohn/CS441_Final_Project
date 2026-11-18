"""Validate file/schema boundaries before invalid inputs reach expensive searches."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from planner.scenarios import load_scenario, scenario_from_dict, validate_scenario

DATA = Path(__file__).resolve().parents[1] / "data"


class ScenarioTests(unittest.TestCase):
    """Exercise real bundled JSON and representative user-upload mistakes."""

    def setUp(self):
        """Load fresh raw data to alter one field in each invalid-input case."""
        self.data = json.loads((DATA / "toy_shelter.json").read_text(encoding="utf-8"))

    def test_every_bundled_example_loads(self):
        """All synthetic examples, including infeasible recovery, are valid input."""
        for path in DATA.glob("*.json"):
            with self.subTest(path=path.name):
                scenario = load_scenario(path)
                validate_scenario(scenario)
                self.assertIsInstance(scenario.access_points[0].settings["low"].covered_user_ids, set)

    def test_unknown_and_legacy_fields_are_rejected(self):
        """Generic capacity fields must not be guessed or silently converted."""
        self.data["users"][0]["demand_units"] = self.data["users"][0].pop("demand_mbps")
        with self.assertRaisesRegex(ValueError, "missing fields"):
            scenario_from_dict(self.data)

    def test_duplicate_ids_are_rejected(self):
        """Duplicate device/AP IDs would overwrite lookup entries and must fail early."""
        duplicate_user = deepcopy(self.data)
        duplicate_user["users"].append(deepcopy(duplicate_user["users"][0]))
        duplicate_ap = deepcopy(self.data)
        duplicate_ap["access_points"].append(deepcopy(duplicate_ap["access_points"][0]))
        for data in (duplicate_user, duplicate_ap):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                scenario_from_dict(data)

    def test_invalid_numeric_inputs_are_rejected(self):
        """Reject zero/negative demand, booleans, and nonfinite capacities."""
        for demand in (0, -1, True, float("nan"), float("inf")):
            data = deepcopy(self.data)
            data["users"][0]["demand_mbps"] = demand
            with self.assertRaises(ValueError):
                scenario_from_dict(data)
        self.data["access_points"][0]["settings"]["low"]["capacity_mbps"] = -1
        with self.assertRaises(ValueError):
            scenario_from_dict(self.data)

    def test_coverage_must_reference_known_devices(self):
        """A misspelled coverage ID cannot silently create a disconnected device."""
        self.data["access_points"][0]["settings"]["low"]["covered_user_ids"].append("typo")
        with self.assertRaisesRegex(ValueError, "unknown device"):
            scenario_from_dict(self.data)

    def test_highest_setting_and_critical_type_are_checked(self):
        """Maximum draw is explicit, and critical must be a JSON boolean."""
        incorrect = deepcopy(self.data)
        incorrect["access_points"][0]["highest_setting"] = "low"
        with self.assertRaises(ValueError):
            scenario_from_dict(incorrect)
        self.data["users"][0]["critical"] = "true"
        with self.assertRaises(ValueError):
            scenario_from_dict(self.data)

    def test_fractional_mbps_and_zero_capacity_are_allowed(self):
        """Valid numeric inputs can describe an infeasible service problem."""
        self.data["users"][0]["demand_mbps"] = 0.5
        self.data["access_points"][0]["settings"]["low"]["capacity_mbps"] = 0
        scenario = scenario_from_dict(self.data)
        self.assertEqual(scenario.users[0].demand_mbps, 0.5)


if __name__ == "__main__":
    unittest.main()
