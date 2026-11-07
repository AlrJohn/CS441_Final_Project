"""Check normal-setting search using real simulation results and controlled moves.

Run from the repository root: python -m unittest discover -s tests -v
The shared fixture helpers come from test_simulation.py, so no production loader
or external package is needed. Fixtures and measured outcomes here are synthetic.
"""

from copy import deepcopy
from dataclasses import replace
from itertools import product
import random
from random import Random
import unittest
from unittest.mock import Mock, patch

from planner.models import AccessPoint, AnnealingSettings, PowerSetting, User
from planner.search import all_high_configuration, greedy, make_neighbor, simulated_annealing
from planner.simulation import evaluate_configuration
from test_simulation import load_toy_fixture, make_ap, make_scenario


def minimum_toy_energy(scenario, failure_policy):
    """Enumerate tiny AP configurations to check a toy search result's energy.

    This is an exact reference for this small fixture only, not an additional
    production solver or proof that finite annealing always finds an optimum.
    """
    ap_ids = []
    setting_choices = []
    for access_point in scenario.access_points:
        ap_ids.append(access_point.ap_id)
        setting_choices.append(sorted(access_point.settings))

    minimum_energy_wh = None
    # product tries every combination of ON settings, not device assignments.
    for setting_names in product(*setting_choices):
        configuration = dict(zip(ap_ids, setting_names))
        evaluation = evaluate_configuration(scenario, configuration, failure_policy)
        if evaluation.feasible:
            if minimum_energy_wh is None or evaluation.energy_wh < minimum_energy_wh:
                minimum_energy_wh = evaluation.energy_wh
    return minimum_energy_wh


class SearchTests(unittest.TestCase):
    """Test feasibility, reproducibility, stopping rules, and best-plan bookkeeping."""

    def setUp(self):
        """Create fresh toy inputs and explicitly recorded annealing parameters."""
        self.scenario = load_toy_fixture()
        self.start = {"AP1": "high", "AP2": "high", "AP3": "high"}
        self.low = {"AP1": "low", "AP2": "low", "AP3": "low"}
        self.settings = AnnealingSettings(
            initial_temperature_wh=5.0,
            minimum_temperature_wh=0.01,
            cooling_rate=0.99,
            max_steps=500,
            seed=441,
        )

    def test_reference_uses_explicit_highest_names(self):
        """Highest settings need not be named high or appear last in a dictionary."""
        access_point = AccessPoint("A", 0, 0, "full", {
            "full": PowerSetting(5, 1, {"X"}),
            "reduced": PowerSetting(2, 1, {"X"}),
        })
        scenario = make_scenario([User("X", 0, 0, True, 1)], [access_point])
        first = all_high_configuration(scenario)
        first["A"] = "reduced"
        self.assertEqual(all_high_configuration(scenario), {"A": "full"})
        self.assertEqual(access_point.highest_setting, "full")

    def test_greedy_reduces_toy_energy_and_keeps_all_devices(self):
        """The normal baseline reduces the toy reference from 16 Wh to 8 Wh."""
        original = deepcopy(self.scenario)
        result = greedy(self.scenario)
        self.assertEqual(result.configuration, self.low)
        self.assertEqual(result.evaluation.energy_wh, 8.0)
        self.assertTrue(result.evaluation.normal.complete)
        self.assertEqual(result.evaluation.failure_policy, "normal_only")
        self.assertIsNone(result.evaluation.failures)
        self.assertGreater(result.steps, 0)
        self.assertEqual(self.scenario, original)

    def test_greedy_does_not_claim_fixed_failure_protection(self):
        """A valid normal baseline can still need power changes after failure."""
        result = greedy(self.scenario)
        fixed = evaluate_configuration(self.scenario, result.configuration, "fixed_settings")
        recovered = evaluate_configuration(self.scenario, result.configuration, "recovery")
        self.assertFalse(fixed.feasible)
        self.assertTrue(recovered.feasible)

    def test_greedy_rejects_a_downgrade_that_loses_service(self):
        """A cheaper setting is not acceptable if a normal device becomes unreachable."""
        access_point = AccessPoint("A", 0, 0, "high", {
            "low": PowerSetting(1, 1, set()),
            "high": PowerSetting(3, 1, {"X"}),
        })
        scenario = make_scenario([User("X", 0, 0, True, 1)], [access_point])
        result = greedy(scenario)
        self.assertEqual(result.configuration, {"A": "high"})
        self.assertTrue(result.evaluation.feasible)
        self.assertEqual(result.steps, 1)

    def test_greedy_reports_an_infeasible_start_honestly(self):
        """An unserviceable all-high start returns missing output, not a fake plan."""
        for access_point in self.scenario.access_points:
            for setting in access_point.settings.values():
                setting.covered_user_ids.discard("C1")
        result = greedy(self.scenario)
        self.assertIsNone(result.configuration)
        self.assertIsNone(result.evaluation)
        self.assertEqual(result.steps, 0)
        self.assertIn("does not prove", result.message)

    def test_greedy_breaks_equal_savings_ties_by_ap_id(self):
        """Either AP can lower alone; sorted ties choose A even when B is listed first."""
        access_points = []
        for ap_id in ("B", "A"):
            access_points.append(AccessPoint(ap_id, 0, 0, "high", {
                "high": PowerSetting(2, 1, {"X"}),
                "low": PowerSetting(1, 1, set()),
            }))
        scenario = make_scenario([User("X", 0, 0, True, 1)], access_points)
        result = greedy(scenario)
        self.assertEqual(result.configuration, {"A": "low", "B": "high"})

    def test_neighbors_change_exactly_one_on_setting(self):
        """Repeated neighbors preserve input and never add an off state."""
        original = deepcopy(self.scenario)
        rng = Random(441)
        for _ in range(20):
            neighbor = make_neighbor(self.scenario, self.start, rng)
            changed_ids = []
            for ap_id in self.start:
                if neighbor[ap_id] != self.start[ap_id]:
                    changed_ids.append(ap_id)
                self.assertIn(neighbor[ap_id], ("low", "high"))
            self.assertEqual(len(changed_ids), 1)
            self.assertIsNot(neighbor, self.start)
        self.assertEqual(self.start, {"AP1": "high", "AP2": "high", "AP3": "high"})
        self.assertEqual(self.scenario, original)

    def test_neighbors_ignore_aps_without_alternative_levels(self):
        """A fixed-level AP remains unchanged when another AP has alternatives."""
        self.scenario.access_points[0].settings.pop("low")
        rng = Random(7)
        for _ in range(10):
            neighbor = make_neighbor(self.scenario, self.start, rng)
            self.assertEqual(neighbor["AP1"], "high")

    def test_neighbor_seed_is_independent_of_input_order(self):
        """Identical seeds produce identical choices even if AP/setting order changes."""
        reordered = deepcopy(self.scenario)
        reordered.access_points.reverse()
        for access_point in reordered.access_points:
            access_point.settings = dict(reversed(list(access_point.settings.items())))
        first_rng = Random(42)
        second_rng = Random(42)
        for _ in range(10):
            self.assertEqual(
                make_neighbor(self.scenario, self.start, first_rng),
                make_neighbor(reordered, self.start, second_rng),
            )

    def test_neighbor_rejects_malformed_configuration(self):
        """Missing/extra APs and off/unknown settings must not enter the search space."""
        invalid_plans = [
            {"AP1": "high"},
            {**self.start, "AP4": "high"},
            {**self.start, "AP1": None},
            {**self.start, "AP1": "off"},
        ]
        for plan in invalid_plans:
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    make_neighbor(self.scenario, plan, Random(441))

    def test_one_configuration_needs_no_annealing_moves(self):
        """No alternative settings returns the feasible start with zero proposals."""
        scenario = make_scenario([User("X", 0, 0, False, 1)], [make_ap("A", 1, {"X"})])
        start = {"A": "low"}
        with self.assertRaises(ValueError):
            make_neighbor(scenario, start, Random(441))
        result = simulated_annealing(scenario, start, self.settings, "normal_only")
        self.assertEqual(result.configuration, start)
        self.assertIsNot(result.configuration, start)
        self.assertEqual(result.steps, 0)
        self.assertTrue(result.evaluation.feasible)

    def test_annealing_rejects_invalid_parameters(self):
        """Reject NaN/infinite values, invalid temperatures, and invalid budgets/seeds."""
        changes = [
            {"initial_temperature_wh": float("nan")},
            {"initial_temperature_wh": float("inf")},
            {"initial_temperature_wh": 0.01},
            {"minimum_temperature_wh": 0},
            {"minimum_temperature_wh": -1},
            {"minimum_temperature_wh": float("inf")},
            {"cooling_rate": 0},
            {"cooling_rate": 1},
            {"cooling_rate": float("nan")},
            {"cooling_rate": "slow"},
            {"max_steps": 0},
            {"max_steps": 2.5},
            {"max_steps": True},
            {"seed": 2.5},
        ]
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    simulated_annealing(self.scenario, self.start, replace(self.settings, **change))

    def test_annealing_reports_infeasible_start_without_a_plan(self):
        """All-low is unsuitable as a fixed-settings-protected starting plan."""
        result = simulated_annealing(self.scenario, self.low, self.settings, "fixed_settings")
        self.assertIsNone(result.configuration)
        self.assertIsNone(result.evaluation)
        self.assertEqual(result.steps, 0)
        self.assertIn("does not prove", result.message)

    def test_annealing_rejects_unknown_policy(self):
        """A misspelled policy must not silently enable a weaker service rule."""
        with self.assertRaises(ValueError):
            simulated_annealing(self.scenario, self.start, self.settings, "unknown")

    def test_annealing_is_reproducible_and_preserves_inputs(self):
        """Equal seeds repeat results without mutating scenario, start, or global RNG."""
        original_scenario = deepcopy(self.scenario)
        original_start = self.start.copy()
        original_random_state = random.getstate()
        first = simulated_annealing(self.scenario, self.start, self.settings)
        second = simulated_annealing(self.scenario, self.start, self.settings)
        self.assertEqual(first, second)
        self.assertEqual(self.scenario, original_scenario)
        self.assertEqual(self.start, original_start)
        self.assertEqual(random.getstate(), original_random_state)
        self.assertIsNot(first.configuration, self.start)

    def test_best_plan_survives_an_accepted_worse_move(self):
        """Annealing may move uphill, but must return the earlier cheaper best."""
        settings = replace(self.settings, max_steps=3)
        controlled_rng = Mock(spec=Random)
        controlled_rng.random.return_value = 0.0  # Always accept a finite uphill chance.
        with patch("planner.search.Random", return_value=controlled_rng):
            with patch("planner.search.make_neighbor", side_effect=[self.low, self.start, self.low]) as moves:
                result = simulated_annealing(self.scenario, self.start, settings)
        # The third proposal receives the higher-energy current plan, confirming
        # that the uphill move happened rather than merely being rejected.
        self.assertEqual(moves.call_args_list[2].args[1], self.start)
        self.assertEqual(result.configuration, self.low)
        self.assertEqual(result.evaluation.energy_wh, 8.0)
        self.assertEqual(result.steps, 3)

    def test_rejected_uphill_move_keeps_current_plan(self):
        """A failed acceptance draw leaves the current configuration at the cheaper plan."""
        controlled_rng = Mock(spec=Random)
        controlled_rng.random.return_value = 0.999
        settings = replace(self.settings, max_steps=3)
        with patch("planner.search.Random", return_value=controlled_rng):
            with patch("planner.search.make_neighbor", side_effect=[self.low, self.start, self.low]) as moves:
                result = simulated_annealing(self.scenario, self.start, settings)
        self.assertEqual(moves.call_args_list[2].args[1], self.low)
        self.assertEqual(result.configuration, self.low)

    def test_high_temperature_never_overrides_service_constraints(self):
        """An all-low fixed-policy failure stays rejected even with very high T."""
        settings = replace(self.settings, initial_temperature_wh=1000, max_steps=1)
        with patch("planner.search.make_neighbor", return_value=self.low):
            result = simulated_annealing(self.scenario, self.start, settings, "fixed_settings")
        self.assertEqual(result.configuration, self.start)
        self.assertTrue(result.evaluation.feasible)
        self.assertEqual(result.steps, 1)

    def test_rejected_moves_use_the_proposal_budget(self):
        """Repeated infeasible proposals still stop at max_steps."""
        settings = replace(self.settings, max_steps=4)
        with patch("planner.search.make_neighbor", return_value=self.low) as moves:
            result = simulated_annealing(self.scenario, self.start, settings, "fixed_settings")
        self.assertEqual(result.steps, 4)
        self.assertEqual(moves.call_count, 4)

    def test_rejected_moves_still_cool_the_search(self):
        """Temperatures 8, 4, 2 produce three trials; reaching 1 stops the loop."""
        settings = replace(
            self.settings, initial_temperature_wh=8, minimum_temperature_wh=1,
            cooling_rate=0.5, max_steps=100,
        )
        with patch("planner.search.make_neighbor", return_value=self.low) as moves:
            result = simulated_annealing(self.scenario, self.start, settings, "fixed_settings")
        self.assertEqual(result.steps, 3)
        self.assertEqual(moves.call_count, 3)

    def test_toy_seeded_results_match_enumerated_minima(self):
        """This seeded toy run reaches the minimum for all three evaluation policies."""
        expected_energy = {"normal_only": 8.0, "fixed_settings": 12.0, "recovery": 8.0}
        for policy, expected in expected_energy.items():
            with self.subTest(policy=policy):
                result = simulated_annealing(self.scenario, self.start, self.settings, policy)
                self.assertTrue(result.evaluation.feasible)
                self.assertEqual(result.evaluation.failure_policy, policy)
                self.assertEqual(result.evaluation.energy_wh, expected)
                self.assertEqual(result.evaluation.energy_wh, minimum_toy_energy(self.scenario, policy))
                self.assertEqual(
                    result.evaluation,
                    evaluate_configuration(self.scenario, result.configuration, policy),
                )


if __name__ == "__main__":
    unittest.main()
