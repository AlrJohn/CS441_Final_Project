"""Check recovery annealing, traces, comparisons, and new demonstration scenarios."""

from copy import deepcopy
from dataclasses import replace
from itertools import product
from pathlib import Path
from random import Random
import unittest
from unittest.mock import Mock, patch

from planner.experiments import compare_recovery, recovery_summary, results_to_csv, run_comparison
from planner.models import AccessPoint, AnnealingSettings, PowerSetting, RecoveryAnnealingSettings, User
from planner.scenarios import load_scenario
from planner.search import greedy, simulated_annealing_recovery
from planner.simulation import assign_users, calculate_power, recover_service
from test_simulation import make_ap, make_scenario

DATA = Path(__file__).resolve().parents[1] / "data"


class RecoveryTests(unittest.TestCase):
    """Verify the failure-specific search space, service rules, and honest failures."""

    def setUp(self):
        """Use explicit watt-based temperatures and a reproducible seed."""
        self.settings = RecoveryAnnealingSettings(5, 0.01, 0.99, 300, 441)
        self.scenario = load_scenario(DATA / "toy_shelter.json")
        self.plan = greedy(self.scenario).configuration

    def test_toy_recovery_matches_small_exact_reference(self):
        """Enumerate survivor settings and verify this toy seeded run reaches 7 W."""
        critical = {user.user_id for user in self.scenario.users if user.critical}
        feasible_watts = []
        for second, third in product(("low", "high"), repeat=2):
            plan = {"AP1": "low", "AP2": second, "AP3": third}
            if assign_users(self.scenario, plan, critical, "AP1").complete:
                feasible_watts.append(calculate_power(self.scenario, plan, "AP1"))
        result = simulated_annealing_recovery(self.scenario, self.plan, "AP1", self.settings)
        self.assertTrue(result.failure.final.complete)
        self.assertEqual(result.failure.surviving_watts_after, min(feasible_watts))
        self.assertEqual(result.failure.surviving_watts_after, 7)
        self.assertEqual(result.failure.configuration["AP1"], "low")
        self.assertEqual(result.failure.trials, result.steps)

    def test_combination_challenge_restores_service_when_greedy_stalls(self):
        """Both survivor changes together work, despite neither helping alone."""
        scenario = load_scenario(DATA / "recovery_challenge.json")
        plan = greedy(scenario).configuration
        baseline = recover_service(scenario, plan, "F")
        result = simulated_annealing_recovery(scenario, plan, "F", self.settings)
        self.assertFalse(baseline.final.complete)
        self.assertTrue(result.failure.final.complete)
        self.assertEqual(result.failure.changed_ap_ids, ["A", "B"])
        self.assertEqual(result.failure.surviving_watts_after, 4)

    def test_unchanged_reassignment_stops_both_methods_without_changes(self):
        """No recovery search is needed when existing survivors already serve critical devices."""
        result = simulated_annealing_recovery(self.scenario, self.plan, "AP3", self.settings)
        self.assertTrue(result.failure.final.complete)
        self.assertFalse(result.failure.recovery_attempted)
        self.assertEqual(result.steps, 0)
        self.assertEqual(result.failure.configuration, self.plan)

    def test_unreachable_device_is_reported_without_false_success(self):
        """An unserviceable all-high seed returns partial service and an honest message."""
        scenario = load_scenario(DATA / "unreachable_critical.json")
        result = simulated_annealing_recovery(scenario, greedy(scenario).configuration, "AP1", self.settings)
        self.assertFalse(result.failure.final.complete)
        self.assertEqual(result.failure.final.unserved_user_ids, ["C1"])
        self.assertEqual(result.steps, 0)
        self.assertIn("not proof", result.message)

    def test_survivors_never_go_below_original_power(self):
        """A lower-than-original state can be serviceable yet remain outside recovery scope."""
        survivor = AccessPoint("A", 0, 0, "high", {
            "low": PowerSetting(1, 2, {"X"}),
            "medium": PowerSetting(2, 2, set()),
            "high": PowerSetting(3, 2, {"X"}),
        })
        scenario = make_scenario([User("X", 0, 0, True, 1)], [survivor, make_ap("F", 2, {"X"})])
        plan = {"A": "medium", "F": "low"}
        result = simulated_annealing_recovery(scenario, plan, "F", self.settings)
        self.assertEqual(result.failure.configuration["A"], "high")
        for event in result.failure.history:
            self.assertNotEqual(event.configuration["A"], "low")
            self.assertEqual(event.configuration["F"], "low")

    def test_best_recovery_survives_a_worse_accepted_move(self):
        """An accepted uphill current state cannot overwrite the cheaper best recovery."""
        survivor = AccessPoint("A", 0, 0, "high", {
            "low": PowerSetting(1, 2, set()),
            "medium": PowerSetting(2, 2, {"X"}),
            "high": PowerSetting(4, 2, {"X"}),
        })
        scenario = make_scenario([User("X", 0, 0, True, 1)], [survivor, make_ap("F", 2, {"X"})])
        rng = Mock(spec=Random)
        rng.choice.side_effect = ["A", "medium", "A", "high"]
        rng.random.return_value = 0
        with patch("planner.search.Random", return_value=rng):
            result = simulated_annealing_recovery(scenario, {"A": "low", "F": "low"}, "F",
                                                 replace(self.settings, max_steps=2))
        self.assertEqual(result.failure.history[-1].current_value, 4)
        self.assertEqual(result.failure.configuration["A"], "medium")
        self.assertEqual(result.failure.surviving_watts_after, 2)

    def test_seeded_runs_preserve_inputs_and_history_snapshots(self):
        """Equal seeds repeat outcomes; changing an event does not mutate the plan."""
        original = deepcopy(self.scenario)
        plan = self.plan.copy()
        first = simulated_annealing_recovery(self.scenario, self.plan, "AP1", self.settings)
        second = simulated_annealing_recovery(self.scenario, self.plan, "AP1", self.settings)
        self.assertEqual(first, second)
        first.failure.history[-1].configuration["AP2"] = "changed_in_test"
        self.assertNotEqual(first.failure.configuration["AP2"], "changed_in_test")
        self.assertEqual(self.scenario, original)
        self.assertEqual(self.plan, plan)

    def test_invalid_recovery_settings_and_failed_ids_raise(self):
        """Wrong IDs and invalid budgets/temperatures must not silently run."""
        for failed in (None, "missing"):
            with self.assertRaises(ValueError):
                simulated_annealing_recovery(self.scenario, self.plan, failed, self.settings)
        for change in ({"max_steps": 0}, {"initial_temperature_watts": float("nan")}, {"cooling_rate": 1}):
            with self.assertRaises(ValueError):
                simulated_annealing_recovery(self.scenario, self.plan, "AP1", replace(self.settings, **change))

    def test_comparison_keeps_partial_results_and_watt_units(self):
        """A partial low-power outcome must not be presented as a complete recovery."""
        scenario = load_scenario(DATA / "recovery_challenge.json")
        runs = compare_recovery(scenario, greedy(scenario).configuration, "F", self.settings)
        rows = recovery_summary(scenario, "F", runs)
        self.assertEqual([row["complete"] for row in rows], [False, False, True])
        self.assertTrue(all(row["runtime_seconds"] >= 0 for row in rows))
        self.assertNotIn("energy_wh", rows[0])
        text = results_to_csv(rows)
        self.assertIn("critical_served", text)
        self.assertIn("Annealing recovery", text)

    def test_batch_normal_comparison_records_baselines_once(self):
        """Two seeds yield two deterministic baselines plus three policies per seed."""
        settings = [AnnealingSettings(5, .01, .99, 20, seed) for seed in (1, 2)]
        rows = run_comparison(self.scenario, settings)
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(row["method"] == "Greedy" for row in rows), 1)
        self.assertEqual(sum(row["method"] == "All-high reference" for row in rows), 1)
        self.assertIsNone(rows[0]["seed"])


if __name__ == "__main__":
    unittest.main()
