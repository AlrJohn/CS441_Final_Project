"""Calculate service, energy, and recovery for one shelter configuration.

Every functioning installed AP stays on. Devices stay at their original
positions, and coverage comes from each setting's covered_user_ids. Device
demands and usable AP capacities are in Mbps; electrical draw is in watts.

These functions expect a valid Scenario, as described in models.py. Full JSON
and scenario validation belongs in scenarios.py. Here we check configurations,
requested device IDs, and failed AP IDs so mistakes do not silently pass.
"""

from .models import (
    Configuration, Evaluation, FailurePolicy, FailureResult, Scenario, ServiceResult,
)


# A tiny allowance handles values such as 0.1 + 0.2, which floating-point
# arithmetic may store slightly above 0.3. It is not extra usable bandwidth.
CAPACITY_TOLERANCE_MBPS = 1e-9


def _validate_configuration(
    scenario: Scenario,
    configuration: Configuration,
    failed_ap_id: str | None = None,
) -> None:
    """Check that every installed AP has exactly one valid ON setting.

    Args:
        scenario: The shelter's already-validated input objects.
        configuration: AP IDs mapped to named operating settings.
        failed_ap_id: An installed AP to exclude, or None for no failure.

    Raises:
        ValueError: An AP is missing/extra, a setting is invalid, or the failed
            AP is unknown. The leading underscore marks a module helper.
    """
    installed_ap_ids = set()
    for access_point in scenario.access_points:
        installed_ap_ids.add(access_point.ap_id)

    # Even a failed AP keeps its original dictionary entry. Failure is a
    # separate input, rather than a setting called off or a missing entry.
    if set(configuration) != installed_ap_ids:
        raise ValueError("Configuration must contain exactly the installed AP IDs.")

    for access_point in scenario.access_points:
        setting_name = configuration[access_point.ap_id]
        if not isinstance(setting_name, str) or setting_name not in access_point.settings:
            raise ValueError(f"Invalid ON setting for AP {access_point.ap_id}: {setting_name!r}")

    if failed_ap_id is not None and failed_ap_id not in installed_ap_ids:
        raise ValueError(f"Unknown failed AP: {failed_ap_id}")


def calculate_power(
    scenario: Scenario,
    configuration: Configuration,
    failed_ap_id: str | None = None,
) -> float:
    """Return the total modeled electrical draw of functioning APs, in watts.

    Args:
        scenario: Valid shelter inputs containing each setting's electrical draw.
        configuration: One ON setting per installed AP.
        failed_ap_id: Optional AP to leave out of the operating-power total.

    Returns:
        Sum of electrical_watts, excluding the failed AP when one is supplied.

    The failed AP's actual fault-state draw is outside our model. This value
    is neither transmit power in dBm nor an amount of energy in Wh.
    """
    _validate_configuration(scenario, configuration, failed_ap_id)
    total_watts = 0.0

    for access_point in scenario.access_points:
        if access_point.ap_id == failed_ap_id:
            continue

        setting_name = configuration[access_point.ap_id]
        selected_setting = access_point.settings[setting_name]
        total_watts += selected_setting.electrical_watts

    return total_watts


def calculate_energy(scenario: Scenario, configuration: Configuration) -> float:
    """Return normal-operation energy in Wh: total watts multiplied by hours.

    Args:
        scenario: Valid inputs, including the common comparison interval_hours.
        configuration: One ON setting per installed AP during normal operation.

    Returns:
        Modeled normal energy over the scenario's interval, in watt-hours.

    Outage durations are unspecified. Recovery operating watts are reported
    separately rather than added to this normal-energy value.
    """
    total_watts = calculate_power(scenario, configuration)
    energy_wh = total_watts * scenario.interval_hours
    return energy_wh


def assign_users(
    scenario: Scenario,
    configuration: Configuration,
    required_user_ids: set[str],
    failed_ap_id: str | None = None,
) -> ServiceResult:
    """Use backtracking with MRV to serve the largest possible requested group.

    Args:
        scenario: Valid device demands, AP capacities, and declared coverage.
        configuration: Fixed settings for this check; never changed here.
        required_user_ids: Exactly the devices this call must try to serve.
        failed_ap_id: Optional AP that cannot receive any device assignments.

    Returns:
        A maximum-count assignment, unserved IDs, and a completeness flag.
        Each device's whole demand must fit on one functioning reachable AP.

    MRV means Minimum Remaining Values: consider the device with the fewest
    currently legal APs first. Backtracking tries alternatives and undoes each
    trial. A skip branch also finds the best partial result when full service
    is impossible. Ties use sorted IDs so repeated calls are reproducible.
    This small-instance exact checker can take exponential time on large inputs.
    """
    _validate_configuration(scenario, configuration, failed_ap_id)

    users_by_id = {}
    for user in scenario.users:
        users_by_id[user.user_id] = user

    # Set difference leaves only requested IDs absent from the scenario.
    unknown_user_ids = required_user_ids - set(users_by_id)
    if unknown_user_ids:
        raise ValueError(f"Unknown requested device IDs: {sorted(unknown_user_ids)}")

    # Step 1: Build each device's reachable choices and the available capacities.
    # These are local dictionaries, so reserving capacity cannot alter Scenario.
    requested_user_ids = sorted(required_user_ids)
    reachable_aps = {}
    remaining_capacity = {}
    for user_id in requested_user_ids:
        reachable_aps[user_id] = []

    for access_point in scenario.access_points:
        if access_point.ap_id == failed_ap_id:
            continue

        setting_name = configuration[access_point.ap_id]
        selected_setting = access_point.settings[setting_name]
        remaining_capacity[access_point.ap_id] = selected_setting.capacity_mbps

        for user_id in requested_user_ids:
            if user_id in selected_setting.covered_user_ids:
                reachable_aps[user_id].append(access_point.ap_id)

    for user_id in requested_user_ids:
        reachable_aps[user_id].sort()

    current_assignments = {}
    best_assignments = {}

    def backtrack(users_left: list[str]) -> None:
        """Explore assignments, keeping the best copy and restoring each trial.

        users_left contains only devices not yet considered on this branch.
        nonlocal lets this nested helper replace the enclosing best dictionary.
        Current assignments and remaining capacities are shared local search
        state; each recursive trial must undo its changes before returning.
        """
        nonlocal best_assignments

        if len(current_assignments) > len(best_assignments):
            best_assignments = current_assignments.copy()

        # Base case: no assignment can improve on serving every requested device.
        if len(best_assignments) == len(requested_user_ids):
            return

        # Prune a branch if even serving everyone left cannot improve the best.
        possible_count = len(current_assignments) + len(users_left)
        if possible_count <= len(best_assignments):
            return

        # Step 2: Recompute legal choices because earlier assignments use capacity.
        selected_user_id = None
        selected_choices = []
        for user_id in users_left:
            demand_mbps = users_by_id[user_id].demand_mbps
            legal_choices = []
            for ap_id in reachable_aps[user_id]:
                if demand_mbps <= remaining_capacity[ap_id] + CAPACITY_TOLERANCE_MBPS:
                    legal_choices.append(ap_id)

            if selected_user_id is None or len(legal_choices) < len(selected_choices):
                selected_user_id = user_id
                selected_choices = legal_choices

        # users_left is empty only when the count bound above already returned.
        next_users = users_left.copy()
        next_users.remove(selected_user_id)
        demand_mbps = users_by_id[selected_user_id].demand_mbps

        # Step 3: Assign, recurse, then undo. Restore the saved capacity exactly
        # instead of repeatedly adding floats, which could accumulate rounding.
        for ap_id in selected_choices:
            previous_capacity = remaining_capacity[ap_id]
            remaining_capacity[ap_id] = previous_capacity - demand_mbps
            current_assignments[selected_user_id] = ap_id

            backtrack(next_users)

            del current_assignments[selected_user_id]
            remaining_capacity[ap_id] = previous_capacity

            if len(best_assignments) == len(requested_user_ids):
                return

        # Step 4: Leaving this device unserved can allow MORE other devices to fit.
        # Without this branch, one large demand could hide a better partial result.
        backtrack(next_users)

    backtrack(requested_user_ids)

    unserved_user_ids = []
    for user_id in requested_user_ids:
        if user_id not in best_assignments:
            unserved_user_ids.append(user_id)

    return ServiceResult(
        assignments=best_assignments,
        unserved_user_ids=unserved_user_ids,
        complete=len(unserved_user_ids) == 0,
    )


def recover_service(
    scenario: Scenario,
    configuration: Configuration,
    failed_ap_id: str,
) -> FailureResult:
    """Try unchanged reassignment, then greedy increases to surviving settings.

    Args:
        scenario: Valid shelter inputs; only critical devices require service here.
        configuration: Original normal plan, copied rather than modified.
        failed_ap_id: Installed AP that remains unavailable throughout recovery.

    Returns:
        Before/after critical service, the final copied plan, changed AP IDs,
        and surviving operating watts before/after.

    Each greedy step chooses the most additional critical devices served per
    extra watt. Sorted AP/setting names break equal-score ties. Only strictly
    higher-watt supplied settings are tried, so recovery cannot cycle forever.
    The heuristic can miss combinations requiring an initial zero-gain change;
    an incomplete result is not proof that recovery is impossible.
    """
    _validate_configuration(scenario, configuration, failed_ap_id)
    if failed_ap_id is None:
        raise ValueError("Recovery requires the ID of an installed failed AP.")

    critical_user_ids = set()
    access_points_by_id = {}
    for user in scenario.users:
        if user.critical:
            critical_user_ids.add(user.user_id)
    for access_point in scenario.access_points:
        access_points_by_id[access_point.ap_id] = access_point

    # Step 1: Reconnect at unchanged settings before spending additional power.
    recovered_configuration = configuration.copy()
    unchanged_service = assign_users(
        scenario, configuration, critical_user_ids, failed_ap_id
    )
    current_service = unchanged_service
    watts_before = calculate_power(scenario, configuration, failed_ap_id)
    current_watts = watts_before
    recovery_attempted = not unchanged_service.complete

    # Step 2: Test one surviving AP setting change at a time.
    while not current_service.complete:
        best_score = 0.0
        best_configuration = None
        best_service = None
        best_watts = current_watts

        for ap_id in sorted(recovered_configuration):
            if ap_id == failed_ap_id:
                continue

            access_point = access_points_by_id[ap_id]
            current_setting_name = recovered_configuration[ap_id]
            current_setting = access_point.settings[current_setting_name]

            for setting_name in sorted(access_point.settings):
                trial_setting = access_point.settings[setting_name]
                if trial_setting.electrical_watts <= current_setting.electrical_watts:
                    continue

                trial_configuration = recovered_configuration.copy()
                trial_configuration[ap_id] = setting_name
                trial_service = assign_users(
                    scenario, trial_configuration, critical_user_ids, failed_ap_id
                )

                additional_served = (
                    len(trial_service.assignments) - len(current_service.assignments)
                )
                if additional_served <= 0:
                    continue

                additional_watts = (
                    trial_setting.electrical_watts - current_setting.electrical_watts
                )
                score = additional_served / additional_watts

                # Use >, not >=: sorted iteration keeps the first equal-score
                # candidate, making tie-breaking consistent across runs.
                if score > best_score:
                    best_score = score
                    best_configuration = trial_configuration
                    best_service = trial_service
                    best_watts = calculate_power(
                        scenario, trial_configuration, failed_ap_id
                    )

        # No single positive-gain change was found. Preserve partial service
        # instead of inventing a successful result or claiming impossibility.
        if best_configuration is None:
            break

        recovered_configuration = best_configuration
        current_service = best_service
        current_watts = best_watts

    changed_ap_ids = []
    for ap_id in sorted(configuration):
        if ap_id != failed_ap_id and recovered_configuration[ap_id] != configuration[ap_id]:
            changed_ap_ids.append(ap_id)

    return FailureResult(
        unchanged=unchanged_service,
        final=current_service,
        configuration=recovered_configuration,
        recovery_attempted=recovery_attempted,
        changed_ap_ids=changed_ap_ids,
        surviving_watts_before=watts_before,
        surviving_watts_after=current_watts,
    )


def evaluate_configuration(
    scenario: Scenario,
    configuration: Configuration,
    failure_policy: FailurePolicy = "recovery",
) -> Evaluation:
    """Check normal service and each independent failure under one policy.

    Args:
        scenario: Valid shelter inputs, shared unchanged across checks.
        configuration: Original normal-operation settings for every installed AP.
        failure_policy: normal_only, fixed_settings, or recovery (the app's goal).

    Returns:
        Normal Wh and service, optional per-AP failure results, and feasibility.
        Every device is required normally; only critical devices are required
        after failure. Each failure starts from the original normal plan.

    Raises:
        ValueError: The policy or configuration is invalid.
    """
    if failure_policy not in ("normal_only", "fixed_settings", "recovery"):
        raise ValueError(f"Unknown failure policy: {failure_policy}")
    _validate_configuration(scenario, configuration)

    all_user_ids = set()
    critical_user_ids = set()
    for user in scenario.users:
        all_user_ids.add(user.user_id)
        if user.critical:
            critical_user_ids.add(user.user_id)

    energy_wh = calculate_energy(scenario, configuration)
    normal_service = assign_users(scenario, configuration, all_user_ids)

    if failure_policy == "normal_only":
        return Evaluation(
            energy_wh=energy_wh,
            normal=normal_service,
            failures=None,
            failure_policy=failure_policy,
            feasible=normal_service.complete,
        )

    failures = {}
    feasible = normal_service.complete
    for failed_ap_id in sorted(configuration):
        if failure_policy == "recovery":
            failure_result = recover_service(scenario, configuration, failed_ap_id)
        else:
            # This comparison policy tries reassignment but never changes power.
            service = assign_users(
                scenario, configuration, critical_user_ids, failed_ap_id
            )
            surviving_watts = calculate_power(scenario, configuration, failed_ap_id)
            failure_result = FailureResult(
                unchanged=service,
                final=service,
                configuration=configuration.copy(),
                recovery_attempted=False,
                changed_ap_ids=[],
                surviving_watts_before=surviving_watts,
                surviving_watts_after=surviving_watts,
            )

        failures[failed_ap_id] = failure_result
        if not failure_result.final.complete:
            feasible = False

    return Evaluation(
        energy_wh=energy_wh,
        normal=normal_service,
        failures=failures,
        failure_policy=failure_policy,
        feasible=feasible,
    )
