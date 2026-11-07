"""Choose normal-operation AP settings using greedy search or annealing.

Every installed AP stays ON. Both algorithms use the shared simulator for
coverage, capacity, and energy; annealing also checks the chosen failure policy.
They expect a valid Scenario, as documented in models.py.

Annealing follows Kirkpatrick et al. (1983), doi:10.1126/science.220.4598.671.
Our greedy downgrade rule is a project-specific baseline, not a reproduction
of Chin's activation scheduler. See docs/research.md for the distinction.
"""

from math import exp, isfinite
from random import Random

from .models import (
    AnnealingSettings, Configuration, FailurePolicy, Scenario, SearchResult,
)
from .simulation import evaluate_configuration


def all_high_configuration(scenario: Scenario) -> Configuration:
    """Return a fresh plan using each AP's explicitly named highest setting.

    Args:
        scenario: Valid shelter inputs containing installed APs and their settings.

    Returns:
        A dictionary mapping every installed AP ID to its highest_setting.

    This is a reference and candidate starting point, not a service guarantee.
    The caller must evaluate it. No settings or scenario objects are modified.
    """
    configuration = {}
    for access_point in scenario.access_points:
        configuration[access_point.ap_id] = access_point.highest_setting
    return configuration


def greedy(scenario: Scenario) -> SearchResult:
    """Repeatedly take the largest normal-energy saving that keeps all devices served.

    Args:
        scenario: Valid device demands, AP settings, coverage, and energy interval.

    Returns:
        The locally improved configuration and its normal_only evaluation.
        If the all-high start cannot serve everyone, both result objects are None.

    Each round tries all lower-watt settings on one AP at a time, then keeps the
    valid trial with the largest Wh saving. Sorted AP/setting names break ties.
    steps counts evaluated downgrade trials, including rejected trials; it does
    not count the initial or final verification. This comparison baseline checks
    normal service only. Evaluate failures separately when reporting results.
    """
    current_configuration = all_high_configuration(scenario)
    current_evaluation = evaluate_configuration(
        scenario, current_configuration, failure_policy="normal_only"
    )
    if not current_evaluation.feasible:
        return SearchResult(
            configuration=None,
            evaluation=None,
            steps=0,
            message="The all-high starting plan cannot serve all normal devices. "
                    "Greedy did not find a plan; this does not prove impossibility.",
        )

    access_points_by_id = {}
    for access_point in scenario.access_points:
        access_points_by_id[access_point.ap_id] = access_point
    steps = 0

    # Step 1: Look at every single-AP downgrade from the current configuration.
    while True:
        best_configuration = None
        best_evaluation = current_evaluation

        for ap_id in sorted(current_configuration):
            access_point = access_points_by_id[ap_id]
            current_setting_name = current_configuration[ap_id]
            current_setting = access_point.settings[current_setting_name]

            for setting_name in sorted(access_point.settings):
                candidate_setting = access_point.settings[setting_name]
                if candidate_setting.electrical_watts >= current_setting.electrical_watts:
                    continue

                # Copy the dictionary so a trial cannot change our current plan.
                candidate_configuration = current_configuration.copy()
                candidate_configuration[ap_id] = setting_name
                candidate_evaluation = evaluate_configuration(
                    scenario, candidate_configuration, failure_policy="normal_only"
                )
                steps += 1

                # Step 2: Saving energy is useful only if ALL normal devices fit.
                if not candidate_evaluation.feasible:
                    continue
                if candidate_evaluation.energy_wh < best_evaluation.energy_wh:
                    best_configuration = candidate_configuration
                    best_evaluation = candidate_evaluation

        # No valid cheaper single change remains: this local search is finished.
        if best_configuration is None:
            break
        current_configuration = best_configuration
        current_evaluation = best_evaluation

    final_evaluation = evaluate_configuration(
        scenario, current_configuration, failure_policy="normal_only"
    )
    return SearchResult(
        configuration=current_configuration.copy(),
        evaluation=final_evaluation,
        steps=steps,
        message="Greedy finished with a normal-service plan. "
                "Failure recovery still needs a separate check; optimality is not guaranteed.",
    )


def make_neighbor(
    scenario: Scenario, configuration: Configuration, rng: Random
) -> Configuration:
    """Copy a plan and randomly change exactly one AP to another ON setting.

    Args:
        scenario: Valid installed APs and their available named settings.
        configuration: One valid ON setting per installed AP.
        rng: A caller-owned Random instance, making seeded runs reproducible.

    Returns:
        A new dictionary; the original plan and scenario are preserved.

    Raises:
        ValueError: The configuration is invalid or no AP has alternative settings.

    Only APs with alternatives are eligible. Sorted choices ensure that input
    dictionary/list ordering does not change the meaning of a random seed.
    Both lower and higher settings are possible; no off state is introduced.
    """
    access_points_by_id = {}
    eligible_ap_ids = []
    for access_point in scenario.access_points:
        access_points_by_id[access_point.ap_id] = access_point
        if len(access_point.settings) > 1:
            eligible_ap_ids.append(access_point.ap_id)

    if set(configuration) != set(access_points_by_id):
        raise ValueError("Configuration must contain exactly the installed AP IDs.")
    for ap_id, access_point in access_points_by_id.items():
        setting_name = configuration[ap_id]
        if not isinstance(setting_name, str) or setting_name not in access_point.settings:
            raise ValueError(f"Invalid ON setting for AP {ap_id}: {setting_name!r}")
    if not eligible_ap_ids:
        raise ValueError("No AP has another available ON setting.")

    selected_ap_id = rng.choice(sorted(eligible_ap_ids))
    access_point = access_points_by_id[selected_ap_id]
    alternative_settings = []
    for setting_name in sorted(access_point.settings):
        if setting_name != configuration[selected_ap_id]:
            alternative_settings.append(setting_name)

    neighbor = configuration.copy()
    neighbor[selected_ap_id] = rng.choice(alternative_settings)
    return neighbor


def simulated_annealing(
    scenario: Scenario,
    start: Configuration,
    settings: AnnealingSettings,
    failure_policy: FailurePolicy = "recovery",
) -> SearchResult:
    """Search feasible settings while occasionally accepting higher normal energy.

    Args:
        scenario: Valid shelter inputs shared unchanged throughout the search.
        start: A supplied starting configuration, feasible under failure_policy.
        settings: Temperatures in Wh, cooling rate, proposal budget, and seed.
        failure_policy: normal_only, fixed_settings, or recovery (the default).

    Returns:
        The lowest-normal-Wh feasible plan encountered and its rechecked evaluation.
        An infeasible starting plan returns None for configuration and evaluation.
        steps counts every proposed neighbor, including infeasible/rejected ones.

    Raises:
        ValueError: Search parameters, policy, or configuration format are invalid.

    A hotter search can accept more expensive moves with probability exp(-delta/T).
    Cooling gradually reduces that probability. Current and best remain separate,
    so an accepted worse move cannot overwrite our best answer. This finite local
    search does not guarantee the global optimum. Greedy recovery can also reject
    a plan for which a different recovery method might succeed.
    """
    # Step 1: Reject invalid settings instead of running an unbounded or NaN search.
    numeric_settings = (
        ("initial_temperature_wh", settings.initial_temperature_wh),
        ("minimum_temperature_wh", settings.minimum_temperature_wh),
        ("cooling_rate", settings.cooling_rate),
    )
    for setting_name, value in numeric_settings:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{setting_name} must be a finite number.")
    if not settings.initial_temperature_wh > settings.minimum_temperature_wh > 0:
        raise ValueError("Temperatures must satisfy initial > minimum > 0.")
    if not 0 < settings.cooling_rate < 1:
        raise ValueError("cooling_rate must be between 0 and 1, excluding both ends.")
    # bool inherits from int in Python. Require actual integers so True is not
    # accidentally treated as a one-step budget or a seed value.
    if type(settings.max_steps) is not int or settings.max_steps <= 0:
        raise ValueError("max_steps must be a positive integer.")
    if type(settings.seed) is not int:
        raise ValueError("seed must be an integer.")

    current_evaluation = evaluate_configuration(scenario, start, failure_policy)
    if not current_evaluation.feasible:
        return SearchResult(
            configuration=None,
            evaluation=None,
            steps=0,
            message=f"Starting plan fails the {failure_policy} service policy. "
                    "Provide a feasible start; this result does not prove impossibility.",
        )

    # Step 2: A local generator avoids changing randomness used elsewhere in the app.
    rng = Random(settings.seed)
    current_configuration = start.copy()
    best_configuration = start.copy()
    best_evaluation = current_evaluation
    temperature_wh = settings.initial_temperature_wh
    steps = 0

    has_alternatives = False
    for access_point in scenario.access_points:
        if len(access_point.settings) > 1:
            has_alternatives = True
            break

    # A one-configuration scenario has a valid answer but no neighbors to explore.
    while (
        has_alternatives
        and steps < settings.max_steps
        and temperature_wh > settings.minimum_temperature_wh
    ):
        candidate_configuration = make_neighbor(scenario, current_configuration, rng)
        candidate_evaluation = evaluate_configuration(
            scenario, candidate_configuration, failure_policy
        )

        # Step 3: Service rules are hard constraints, even at high temperature.
        if candidate_evaluation.feasible:
            energy_change_wh = candidate_evaluation.energy_wh - current_evaluation.energy_wh
            accept_candidate = energy_change_wh <= 0
            if energy_change_wh > 0:
                acceptance_probability = exp(-energy_change_wh / temperature_wh)
                accept_candidate = rng.random() < acceptance_probability

            if accept_candidate:
                current_configuration = candidate_configuration.copy()
                current_evaluation = candidate_evaluation
                if current_evaluation.energy_wh < best_evaluation.energy_wh:
                    best_configuration = current_configuration.copy()
                    best_evaluation = current_evaluation

        # Step 4: Every proposal uses the budget and cools the search. Skipping
        # these updates on rejection could cause an endless loop on infeasible moves.
        steps += 1
        temperature_wh *= settings.cooling_rate

    final_evaluation = evaluate_configuration(scenario, best_configuration, failure_policy)
    return SearchResult(
        configuration=best_configuration.copy(),
        evaluation=final_evaluation,
        steps=steps,
        message="Annealing finished with its best encountered feasible plan. "
                "A global optimum is not guaranteed.",
    )
