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
    FailureResult, RecoveryAnnealingSettings, RecoverySearchResult, SearchStep,
)
from .simulation import assign_users, calculate_power, evaluate_configuration


def _validate_annealing_parameters(initial, minimum, cooling_rate, max_steps, seed):
    """Check shared annealing controls while keeping W/Wh in their own models."""
    for name, value in (("initial temperature", initial), ("minimum temperature", minimum),
                        ("cooling rate", cooling_rate)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{name} must be a finite number.")
    if not initial > minimum > 0:
        raise ValueError("Temperatures must satisfy initial > minimum > 0.")
    if not 0 < cooling_rate < 1:
        raise ValueError("cooling_rate must be between 0 and 1, excluding both ends.")
    # bool inherits from int; True must not accidentally become a one-step budget.
    if type(max_steps) is not int or max_steps <= 0:
        raise ValueError("max_steps must be a positive integer.")
    if type(seed) is not int:
        raise ValueError("seed must be an integer.")


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
    history = [SearchStep(
        0, current_evaluation.energy_wh, current_evaluation.energy_wh,
        current_evaluation.energy_wh, True, True,
        len(current_evaluation.normal.assignments), len(scenario.users),
        current_configuration.copy(),
    )]

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
        history.append(SearchStep(
            steps, current_evaluation.energy_wh, current_evaluation.energy_wh,
            current_evaluation.energy_wh, True, True,
            len(current_evaluation.normal.assignments), len(scenario.users),
            current_configuration.copy(),
        ))

    final_evaluation = evaluate_configuration(
        scenario, current_configuration, failure_policy="normal_only"
    )
    return SearchResult(
        configuration=current_configuration.copy(),
        evaluation=final_evaluation,
        steps=steps,
        message="Greedy finished with a normal-service plan. "
                "Failure recovery still needs a separate check; optimality is not guaranteed.",
        history=history,
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
    _validate_annealing_parameters(
        settings.initial_temperature_wh, settings.minimum_temperature_wh,
        settings.cooling_rate, settings.max_steps, settings.seed,
    )

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

    history = [SearchStep(
        0, current_evaluation.energy_wh, best_evaluation.energy_wh,
        current_evaluation.energy_wh, True, True,
        len(current_evaluation.normal.assignments), len(scenario.users),
        current_configuration.copy(), temperature_wh,
    )]

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

        accept_candidate = False
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
        history.append(SearchStep(
            steps, current_evaluation.energy_wh, best_evaluation.energy_wh,
            candidate_evaluation.energy_wh, accept_candidate, candidate_evaluation.feasible,
            len(candidate_evaluation.normal.assignments), len(scenario.users),
            current_configuration.copy(), temperature_wh,
        ))
        temperature_wh *= settings.cooling_rate

    final_evaluation = evaluate_configuration(scenario, best_configuration, failure_policy)
    return SearchResult(
        configuration=best_configuration.copy(),
        evaluation=final_evaluation,
        steps=steps,
        message="Annealing finished with its best encountered feasible plan. "
                "A global optimum is not guaranteed.",
        history=history,
    )


def simulated_annealing_recovery(
    scenario: Scenario,
    configuration: Configuration,
    failed_ap_id: str,
    settings: RecoveryAnnealingSettings,
) -> RecoverySearchResult:
    """Restore critical service, then minimize surviving operating watts.

    First try unchanged reassignment, just like greedy recovery. If needed, seed
    annealing with all surviving APs at their highest settings. Only complete
    critical-service candidates are accepted. Neighbors may increase or decrease
    from the seed, but never below an AP's original operating watts. The failed
    AP remains unavailable and keeps its original entry; no AP is switched off.

    Temperatures and the objective are W, not Wh. Returned history records setup
    and every proposal. A failed all-high seed is reported honestly; with arbitrary
    non-nested input settings it does not prove that no other recovery exists.
    Greedy recovery is not used inside this search, keeping the methods separate.
    """
    _validate_annealing_parameters(
        settings.initial_temperature_watts, settings.minimum_temperature_watts,
        settings.cooling_rate, settings.max_steps, settings.seed,
    )
    # assign_users checks the configuration and failed ID. None is not a failure.
    if failed_ap_id is None:
        raise ValueError("Recovery requires an installed failed AP ID.")
    critical_ids = set()
    for user in scenario.users:
        if user.critical:
            critical_ids.add(user.user_id)
    unchanged = assign_users(scenario, configuration, critical_ids, failed_ap_id)
    watts_before = calculate_power(scenario, configuration, failed_ap_id)
    history = [SearchStep(
        0, watts_before, watts_before if unchanged.complete else None, watts_before,
        True, unchanged.complete, len(unchanged.assignments), len(critical_ids),
        configuration.copy(),
    )]
    if unchanged.complete:
        failure = FailureResult(
            unchanged, unchanged, configuration.copy(), False, [],
            watts_before, watts_before, history,
        )
        return RecoverySearchResult(failure, 0, "Unchanged reassignment already serves every critical device.")

    # Build the recovery search space once. Named settings are inputs; their
    # electrical draw determines the lower bound, not the spelling of the name.
    allowed_settings = {}
    current_configuration = configuration.copy()
    for access_point in scenario.access_points:
        ap_id = access_point.ap_id
        if ap_id == failed_ap_id:
            continue
        baseline = access_point.settings[configuration[ap_id]].electrical_watts
        allowed_settings[ap_id] = []
        for name in sorted(access_point.settings):
            if access_point.settings[name].electrical_watts >= baseline:
                allowed_settings[ap_id].append(name)
        current_configuration[ap_id] = access_point.highest_setting

    current_service = assign_users(scenario, current_configuration, critical_ids, failed_ap_id)
    current_watts = calculate_power(scenario, current_configuration, failed_ap_id)
    if not current_service.complete:
        # Keep the better partial assignment for inspection, without claiming a
        # complete recovery or treating a failed seed as proof of impossibility.
        if len(current_service.assignments) <= len(unchanged.assignments):
            current_configuration = configuration.copy()
            current_service = unchanged
            current_watts = watts_before
        changed = []
        for ap_id in sorted(configuration):
            if current_configuration[ap_id] != configuration[ap_id]:
                changed.append(ap_id)
        history.append(SearchStep(
            0, current_watts, None, current_watts, False, False,
            len(current_service.assignments), len(critical_ids), current_configuration.copy(),
        ))
        failure = FailureResult(
            unchanged, current_service, current_configuration.copy(), True, changed,
            watts_before, current_watts, history,
        )
        return RecoverySearchResult(
            failure, 0, "No feasible all-high recovery seed was found. This is not proof of impossibility."
        )

    best_configuration = current_configuration.copy()
    best_service = current_service
    best_watts = current_watts
    temperature = settings.initial_temperature_watts
    rng = Random(settings.seed)
    steps = 0
    eligible_ids = []
    for ap_id in sorted(allowed_settings):
        if len(allowed_settings[ap_id]) > 1:
            eligible_ids.append(ap_id)
    history.append(SearchStep(
        0, current_watts, best_watts, current_watts, True, True,
        len(current_service.assignments), len(critical_ids), current_configuration.copy(), temperature,
    ))

    while eligible_ids and steps < settings.max_steps and temperature > settings.minimum_temperature_watts:
        ap_id = rng.choice(eligible_ids)
        alternatives = []
        for name in allowed_settings[ap_id]:
            if name != current_configuration[ap_id]:
                alternatives.append(name)
        candidate = current_configuration.copy()
        candidate[ap_id] = rng.choice(alternatives)
        service = assign_users(scenario, candidate, critical_ids, failed_ap_id)
        watts = calculate_power(scenario, candidate, failed_ap_id)
        accepted = False
        if service.complete:
            delta = watts - current_watts
            accepted = delta <= 0
            if delta > 0:
                accepted = rng.random() < exp(-delta / temperature)
            if accepted:
                current_configuration = candidate.copy()
                current_service = service
                current_watts = watts
                if current_watts < best_watts:
                    best_configuration = current_configuration.copy()
                    best_service = current_service
                    best_watts = current_watts
        steps += 1
        history.append(SearchStep(
            steps, current_watts, best_watts, watts, accepted, service.complete,
            len(service.assignments), len(critical_ids), current_configuration.copy(), temperature,
        ))
        temperature *= settings.cooling_rate

    changed = []
    for ap_id in sorted(configuration):
        if ap_id != failed_ap_id and best_configuration[ap_id] != configuration[ap_id]:
            changed.append(ap_id)
    # Recheck the returned best, which may differ from the last accepted current.
    best_service = assign_users(scenario, best_configuration, critical_ids, failed_ap_id)
    failure = FailureResult(
        unchanged, best_service, best_configuration.copy(), True, changed,
        watts_before, best_watts, history, steps,
    )
    return RecoverySearchResult(
        failure, steps, "Recovery annealing returned its best complete plan; global optimality is not guaranteed."
    )
