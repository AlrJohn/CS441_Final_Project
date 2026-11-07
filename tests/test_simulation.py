"""Check the simulation independently of the unfinished loader and interface.

Run from the repository root with:
    python -m unittest discover -s tests -v

All fixtures are synthetic. The small JSON reader below is test setup only;
production JSON loading and scenario validation still belong to scenarios.py.
"""

from copy import deepcopy
from itertools import product
import json
from pathlib import Path
from random import Random
import unittest

from planner.models import AccessPoint, PowerSetting, Scenario, User
from planner.simulation import (
    assign_users, calculate_energy, calculate_power, evaluate_configuration,
    recover_service,
)


def make_scenario(users: list[User], access_points: list[AccessPoint]) -> Scenario:
    """Build a one-hour synthetic fixture from explicitly supplied model objects."""
    return Scenario(
        scenario_id="test_scenario",
        description="Invented inputs for a small correctness check.",
        interval_hours=1.0,
        users=users,
        access_points=access_points,
    )


def make_ap(ap_id: str, capacity_mbps: float, covered_ids: set[str]) -> AccessPoint:
    """Build a fixed-position AP with one ON setting for assignment tests."""
    return AccessPoint(
        ap_id=ap_id,
        x=0.0,
        y=0.0,
        highest_setting="low",
        settings={"low": PowerSetting(3.0, capacity_mbps, covered_ids)},
    )


def load_toy_fixture() -> Scenario:
    """Construct test objects from the shared toy JSON without using the loader stub."""
    scenario_path = Path(__file__).resolve().parents[1] / "data" / "toy_shelter.json"
    with scenario_path.open(encoding="utf-8") as scenario_file:
        scenario_data = json.load(scenario_file)

    users = []
    for user_data in scenario_data["users"]:
        # ** passes the JSON dictionary's fields as named constructor arguments.
        users.append(User(**user_data))

    access_points = []
    for ap_data in scenario_data["access_points"]:
        settings = {}
        for setting_name, setting_data in ap_data["settings"].items():
            settings[setting_name] = PowerSetting(
                electrical_watts=setting_data["electrical_watts"],
                capacity_mbps=setting_data["capacity_mbps"],
                covered_user_ids=set(setting_data["covered_user_ids"]),
            )
        access_points.append(AccessPoint(
            ap_id=ap_data["ap_id"],
            x=ap_data["x"],
            y=ap_data["y"],
            highest_setting=ap_data["highest_setting"],
            settings=settings,
        ))

    return Scenario(
        scenario_id=scenario_data["scenario_id"],
        description=scenario_data["description"],
        interval_hours=scenario_data["interval_hours"],
        users=users,
        access_points=access_points,
    )


def exhaustive_served_count(
    scenario: Scenario, configuration: dict[str, str], failed_ap_id: str | None,
) -> int:
    """Enumerate every tiny assignment as an independent backtracking test oracle.

    Each device chooses one surviving AP or None (unserved). This deliberately
    uses enumeration rather than MRV/recursion, so it checks the result through
    a different approach. Never use it for production-sized scenarios.
    """
    available_settings = {}
    for access_point in scenario.access_points:
        if access_point.ap_id != failed_ap_id:
            setting_name = configuration[access_point.ap_id]
            available_settings[access_point.ap_id] = access_point.settings[setting_name]

    choices = [None] + sorted(available_settings)
    best_count = 0
    for assignments in product(choices, repeat=len(scenario.users)):
        loads = dict.fromkeys(available_settings, 0.0)
        valid = True
        served_count = 0

        for user, ap_id in zip(scenario.users, assignments):
            if ap_id is None:
                continue
            setting = available_settings[ap_id]
            if user.user_id not in setting.covered_user_ids:
                valid = False
                break
            loads[ap_id] += user.demand_mbps
            if loads[ap_id] > setting.capacity_mbps:
                valid = False
                break
            served_count += 1

        if valid and served_count > best_count:
            best_count = served_count

    return best_count


class SimulationTests(unittest.TestCase):
    """Test assignments, energy, and recovery through their public functions."""

    def setUp(self):
        """Give every test fresh inputs so changes cannot leak between tests."""
        self.scenario = load_toy_fixture()
        self.configuration = {"AP1": "low", "AP2": "low", "AP3": "low"}

    def test_power_and_energy_use_correct_units(self):
        """The all-low plan uses 8 W, or 20 Wh over a 2.5-hour interval."""
        self.scenario.interval_hours = 2.5
        self.assertEqual(calculate_power(self.scenario, self.configuration), 8.0)
        self.assertEqual(calculate_energy(self.scenario, self.configuration), 20.0)
        self.assertEqual(calculate_power(self.scenario, self.configuration, "AP1"), 5.0)

    def test_configuration_errors_are_reported(self):
        """Reject missing/extra APs, off entries, and unavailable setting names."""
        invalid_configurations = [
            {"AP1": "low", "AP2": "low"},
            {**self.configuration, "AP4": "low"},
            {**self.configuration, "AP1": None},
            {**self.configuration, "AP1": "off"},
            {**self.configuration, "AP1": "missing_setting"},
        ]
        for configuration in invalid_configurations:
            with self.subTest(configuration=configuration):
                with self.assertRaises(ValueError):
                    calculate_power(self.scenario, configuration)

    def test_unknown_ids_are_reported(self):
        """A typo must not become a silently ignored AP or device."""
        with self.assertRaises(ValueError):
            calculate_power(self.scenario, self.configuration, "AP_missing")
        with self.assertRaises(ValueError):
            assign_users(self.scenario, self.configuration, {"missing_device"})
        with self.assertRaises(ValueError):
            recover_service(self.scenario, self.configuration, None)

    def test_all_low_serves_every_device_normally(self):
        """The toy normal configuration can fit all 7 Mbps across its APs."""
        result = assign_users(self.scenario, self.configuration, {"C1", "C2", "U1", "U2"})
        self.assertTrue(result.complete)
        self.assertEqual(len(result.assignments), 4)
        self.assertEqual(result.unserved_user_ids, [])

    def test_backtracking_reverses_an_unlucky_first_choice(self):
        """Equal MRV counts can still require undoing X->A and trying X->B."""
        users = [User(name, 0, 0, True, 1) for name in ("X", "Y", "Z")]
        access_points = [
            make_ap("A", 1, {"X", "Y", "Z"}),
            make_ap("B", 1, {"X"}),
            make_ap("C", 1, {"Y", "Z"}),
        ]
        scenario = make_scenario(users, access_points)
        result = assign_users(scenario, {"A": "low", "B": "low", "C": "low"}, {"X", "Y", "Z"})
        self.assertTrue(result.complete)
        self.assertEqual(result.assignments["X"], "B")
        self.assertEqual({result.assignments["Y"], result.assignments["Z"]}, {"A", "C"})

    def test_partial_assignment_can_skip_a_large_demand(self):
        """Skipping A's 3 Mbps serves two smaller devices instead of just one."""
        users = [User("A", 0, 0, True, 3), User("B", 0, 0, True, 1), User("C", 0, 0, True, 1)]
        scenario = make_scenario(users, [make_ap("AP", 3, {"A", "B", "C"})])
        result = assign_users(scenario, {"AP": "low"}, {"A", "B", "C"})
        self.assertFalse(result.complete)
        self.assertEqual(set(result.assignments), {"B", "C"})
        self.assertEqual(result.unserved_user_ids, ["A"])

    def test_coverage_alone_is_not_enough(self):
        """Two covered 1 Mbps devices cannot both fit a 1 Mbps AP."""
        users = [User("X", 0, 0, True, 1), User("Y", 0, 0, True, 1)]
        scenario = make_scenario(users, [make_ap("AP", 1, {"X", "Y"})])
        result = assign_users(scenario, {"AP": "low"}, {"X", "Y"})
        self.assertFalse(result.complete)
        self.assertEqual(len(result.assignments), 1)

    def test_one_device_cannot_split_demand(self):
        """Two 2 Mbps APs cannot combine their capacity for one 3 Mbps device."""
        scenario = make_scenario(
            [User("X", 0, 0, True, 3)],
            [make_ap("A", 2, {"X"}), make_ap("B", 2, {"X"})],
        )
        result = assign_users(scenario, {"A": "low", "B": "low"}, {"X"})
        self.assertEqual(result.assignments, {})
        self.assertEqual(result.unserved_user_ids, ["X"])

    def test_fractional_demands_fit_without_rounding(self):
        """Floating-point representation must not reject 0.1 + 0.2 in 0.3 Mbps."""
        users = [User("X", 0, 0, True, 0.1), User("Y", 0, 0, True, 0.2)]
        scenario = make_scenario(users, [make_ap("AP", 0.3, {"X", "Y"})])
        result = assign_users(scenario, {"AP": "low"}, {"X", "Y"})
        self.assertTrue(result.complete)

    def test_empty_request_is_complete(self):
        """No requested devices needs no assignment, even with an AP failed."""
        result = assign_users(self.scenario, self.configuration, set(), "AP1")
        self.assertTrue(result.complete)
        self.assertEqual(result.assignments, {})

    def test_assignment_order_is_reproducible(self):
        """Input list order must not change equal-choice assignment results."""
        required = {"C1", "C2", "U1", "U2"}
        first = assign_users(self.scenario, self.configuration, required)
        self.scenario.users.reverse()
        self.scenario.access_points.reverse()
        second = assign_users(self.scenario, self.configuration, required)
        self.assertEqual(first, second)

    def test_normal_only_leaves_failure_results_unchecked(self):
        """Normal feasibility must not imply that failure protection was checked."""
        result = evaluate_configuration(self.scenario, self.configuration, "normal_only")
        self.assertTrue(result.feasible)
        self.assertIsNone(result.failures)
        self.assertEqual(result.energy_wh, 8.0)

    def test_fixed_settings_reports_unserved_critical_devices(self):
        """The all-low plan needs changes after AP1/AP2, but not AP3, fails."""
        result = evaluate_configuration(self.scenario, self.configuration, "fixed_settings")
        self.assertFalse(result.feasible)
        self.assertEqual(result.failures["AP1"].final.unserved_user_ids, ["C1"])
        self.assertEqual(result.failures["AP2"].final.unserved_user_ids, ["C2"])
        self.assertTrue(result.failures["AP3"].final.complete)
        for failure in result.failures.values():
            self.assertFalse(failure.recovery_attempted)
            self.assertEqual(failure.configuration, self.configuration)

    def test_recovery_chooses_service_gain_per_extra_watt(self):
        """AP2 high restores C1 for 2 extra W; AP3 high would cost 4 extra W."""
        result = recover_service(self.scenario, self.configuration, "AP1")
        self.assertFalse(result.unchanged.complete)
        self.assertTrue(result.final.complete)
        self.assertTrue(result.recovery_attempted)
        self.assertEqual(result.changed_ap_ids, ["AP2"])
        self.assertEqual(result.configuration, {"AP1": "low", "AP2": "high", "AP3": "low"})
        self.assertEqual(result.surviving_watts_before, 5.0)
        self.assertEqual(result.surviving_watts_after, 7.0)
        self.assertEqual(set(result.final.assignments), {"C1", "C2"})
        self.assertNotIn("AP1", result.final.assignments.values())

    def test_reassignment_can_succeed_without_power_changes(self):
        """When AP3 fails, both critical devices already have surviving service."""
        result = recover_service(self.scenario, self.configuration, "AP3")
        self.assertTrue(result.unchanged.complete)
        self.assertFalse(result.recovery_attempted)
        self.assertEqual(result.changed_ap_ids, [])
        self.assertEqual(result.surviving_watts_before, result.surviving_watts_after)

    def test_failures_are_independent_and_inputs_are_preserved(self):
        """AP2's failure must not inherit the changed settings from AP1's failure."""
        original_scenario = deepcopy(self.scenario)
        original_configuration = self.configuration.copy()
        result = evaluate_configuration(self.scenario, self.configuration)
        self.assertTrue(result.feasible)
        self.assertEqual(result.failures["AP1"].changed_ap_ids, ["AP2"])
        self.assertEqual(result.failures["AP2"].changed_ap_ids, ["AP1"])
        self.assertEqual(result.failures["AP2"].configuration["AP2"], "low")
        self.assertEqual(self.configuration, original_configuration)
        self.assertEqual(self.scenario, original_scenario)
        self.assertIsNot(result.failures["AP1"].configuration, self.configuration)
        self.assertIsNot(result.failures["AP1"].configuration, result.failures["AP2"].configuration)

    def test_all_high_needs_no_recovery_changes(self):
        """The reference's unchanged critical service passes each separate failure."""
        configuration = {"AP1": "high", "AP2": "high", "AP3": "high"}
        result = evaluate_configuration(self.scenario, configuration)
        self.assertTrue(result.feasible)
        self.assertEqual(result.energy_wh, 16.0)
        for failure in result.failures.values():
            self.assertTrue(failure.unchanged.complete)
            self.assertEqual(failure.changed_ap_ids, [])

    def test_recovery_cannot_create_missing_coverage(self):
        """If C1 reaches only failed AP1 at every level, report incomplete service."""
        for access_point in self.scenario.access_points:
            if access_point.ap_id != "AP1":
                for setting in access_point.settings.values():
                    setting.covered_user_ids.discard("C1")
        result = recover_service(self.scenario, self.configuration, "AP1")
        self.assertFalse(result.final.complete)
        self.assertEqual(result.final.unserved_user_ids, ["C1"])
        self.assertTrue(result.recovery_attempted)
        self.assertEqual(result.changed_ap_ids, [])

    def test_higher_power_does_not_override_capacity(self):
        """Increasing coverage does not let a 2 Mbps AP serve C1's 3 Mbps."""
        for access_point in self.scenario.access_points:
            if access_point.ap_id != "AP1":
                for setting in access_point.settings.values():
                    setting.capacity_mbps = 2
        result = recover_service(self.scenario, self.configuration, "AP1")
        self.assertFalse(result.final.complete)
        self.assertIn("C1", result.final.unserved_user_ids)

    def test_recovery_counts_unique_changed_aps(self):
        """Two increases on one AP should produce one changed AP ID, not two."""
        users = [User("X", 0, 0, True, 1), User("Y", 0, 0, True, 1)]
        survivor = AccessPoint("A", 0, 0, "high", {
            "low": PowerSetting(1, 2, set()),
            "medium": PowerSetting(2, 2, {"X"}),
            "high": PowerSetting(5, 2, {"X", "Y"}),
        })
        scenario = make_scenario(users, [survivor, make_ap("F", 2, {"X", "Y"})])
        result = recover_service(scenario, {"A": "low", "F": "low"}, "F")
        self.assertTrue(result.final.complete)
        self.assertEqual(result.changed_ap_ids, ["A"])
        self.assertEqual(result.configuration["A"], "high")
        self.assertEqual(result.surviving_watts_before, 1)
        self.assertEqual(result.surviving_watts_after, 5)

    def test_equal_recovery_scores_use_sorted_ap_ids(self):
        """Equivalent recovery choices should pick A even if B is listed first."""
        access_points = []
        for ap_id in ("B", "A"):
            access_points.append(AccessPoint(ap_id, 0, 0, "high", {
                "low": PowerSetting(1, 1, set()),
                "high": PowerSetting(2, 1, {"X"}),
            }))
        access_points.append(make_ap("F", 1, {"X"}))
        scenario = make_scenario([User("X", 0, 0, True, 1)], access_points)
        result = recover_service(scenario, {"A": "low", "B": "low", "F": "low"}, "F")
        self.assertEqual(result.changed_ap_ids, ["A"])

    def test_greedy_stall_does_not_prove_recovery_impossible(self):
        """Document a feasible two-change recovery that positive-gain greedy misses."""
        users = [User("X", 0, 0, True, 1), User("Y", 0, 0, True, 1)]
        access_points = [
            AccessPoint("A", 0, 0, "high", {
                "low": PowerSetting(1, 1, {"X"}),
                "high": PowerSetting(2, 1, {"X", "Y"}),
            }),
            AccessPoint("B", 0, 0, "high", {
                "low": PowerSetting(1, 1, set()),
                "high": PowerSetting(2, 1, {"X"}),
            }),
            make_ap("F", 1, {"Y"}),
        ]
        scenario = make_scenario(users, access_points)
        configuration = {"A": "low", "B": "low", "F": "low"}
        result = recover_service(scenario, configuration, "F")
        self.assertFalse(result.final.complete)
        # Neither increase helps alone, but both together allow Y->A and X->B.
        combined = {"A": "high", "B": "high", "F": "low"}
        self.assertTrue(assign_users(scenario, combined, {"X", "Y"}, "F").complete)

    def test_normal_service_still_requires_noncritical_devices(self):
        """Passing critical failure checks cannot excuse a disconnected normal guest."""
        for access_point in self.scenario.access_points:
            for setting in access_point.settings.values():
                setting.covered_user_ids.discard("U1")
        result = evaluate_configuration(self.scenario, self.configuration)
        self.assertFalse(result.normal.complete)
        self.assertFalse(result.feasible)
        self.assertTrue(all(failure.final.complete for failure in result.failures.values()))

    def test_no_critical_devices_requires_no_recovery_changes(self):
        """Empty critical sets pass failure checks but normal devices still matter."""
        for user in self.scenario.users:
            user.critical = False
        result = evaluate_configuration(self.scenario, self.configuration)
        self.assertTrue(result.feasible)
        for failure in result.failures.values():
            self.assertTrue(failure.final.complete)
            self.assertEqual(failure.final.assignments, {})
            self.assertFalse(failure.recovery_attempted)

    def test_no_aps_cannot_serve_a_normal_device(self):
        """An empty failure dictionary must not make an unserved plan feasible."""
        scenario = make_scenario([User("X", 0, 0, True, 1)], [])
        result = evaluate_configuration(scenario, {})
        self.assertFalse(result.feasible)
        self.assertEqual(result.failures, {})

    def test_invalid_policy_is_reported(self):
        """A misspelled policy must not silently select another behavior."""
        with self.assertRaises(ValueError):
            evaluate_configuration(self.scenario, self.configuration, "unknown")

    def test_small_random_cases_match_exhaustive_assignments(self):
        """Compare maximum served counts against enumeration on 40 seeded cases."""
        random_generator = Random(441)
        for case_number in range(40):
            users = []
            for number in range(4):
                users.append(User(f"U{number}", 0, 0, True, random_generator.randint(1, 3)))

            access_points = []
            for ap_id in ("A", "B", "C"):
                covered_ids = set()
                for user in users:
                    if random_generator.random() < 0.65:
                        covered_ids.add(user.user_id)
                access_points.append(make_ap(ap_id, random_generator.randint(0, 4), covered_ids))

            scenario = make_scenario(users, access_points)
            original_scenario = deepcopy(scenario)
            configuration = {"A": "low", "B": "low", "C": "low"}
            failed_ap_id = "A" if case_number % 2 == 0 else None
            requested_ids = {user.user_id for user in users}
            result = assign_users(scenario, configuration, requested_ids, failed_ap_id)

            with self.subTest(case=case_number):
                self.assertEqual(
                    len(result.assignments),
                    exhaustive_served_count(scenario, configuration, failed_ap_id),
                )
                self.assertEqual(set(result.assignments) | set(result.unserved_user_ids), requested_ids)
                self.assertTrue(set(result.assignments).isdisjoint(result.unserved_user_ids))
                self.assertEqual(result.complete, len(result.assignments) == len(users))
                # Check the returned assignment itself, not only its size.
                for access_point in access_points:
                    load_mbps = 0
                    for user in users:
                        if result.assignments.get(user.user_id) == access_point.ap_id:
                            self.assertNotEqual(access_point.ap_id, failed_ap_id)
                            self.assertIn(user.user_id, access_point.settings["low"].covered_user_ids)
                            load_mbps += user.demand_mbps
                    self.assertLessEqual(load_mbps, access_point.settings["low"].capacity_mbps)
                self.assertEqual(scenario, original_scenario)


if __name__ == "__main__":
    unittest.main()
