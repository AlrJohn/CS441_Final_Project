"""Coverage, device assignment, recovery, and energy share one model here.

Every functioning installed AP stays on. Coverage and capacity are separate
setting inputs; higher power does not inherently create more capacity.
Device demand_mbps and AP capacity_mbps use modeled usable Mbps.
No router control or recovery timing.
"""

from .models import (
    Configuration, Evaluation, FailurePolicy, FailureResult, Scenario, ServiceResult,
)


def calculate_power(
    scenario: Scenario,
    configuration: Configuration,
    failed_ap_id: str | None = None,
) -> float:
    """Sum modeled operating watts, excluding an unavailable failed AP.

    Pseudocode:
        For each AP other than failed_ap_id, read its selected ON setting.
        Add electrical_watts and return the sum.

    No off state exists. The failed AP's dictionary entry stays present but is
    ignored. Its actual fault-state draw is not modeled. Never confuse watts
    with transmit dBm, capacity, or energy in Wh.
    """
    raise NotImplementedError("Implement the sum of functioning AP draws.")


def calculate_energy(scenario: Scenario, configuration: Configuration) -> float:
    """Return NORMAL-operation energy in Wh over the common comparison interval.

    Pseudocode:
        Return calculate_power(scenario, configuration) * scenario.interval_hours.

    Report failure-operation watts separately. Do not add them to Wh without
    an agreed outage duration; failure durations/probabilities are outside scope.
    """
    raise NotImplementedError("Implement the watts-times-hours calculation.")


def assign_users(
    scenario: Scenario,
    configuration: Configuration,
    required_user_ids: set[str],
    failed_ap_id: str | None = None,
) -> ServiceResult:
    """Find a maximum-size assignment, with one whole demand served by one AP.

    Pseudocode (a small nested backtracking helper is enough):
        Build reachable choices and capacities from the selected settings.
        Exclude the failed AP. Start with empty current and best assignments.
        At each recursive step, save a COPY of current if it improves best.
        Stop early when all requested users are assigned.
        Return if none remain, or current size + users left cannot beat best.
        Pick the remaining user with fewest currently legal AP choices (MRV).
        For each AP that reaches them and can hold their entire demand:
            Reserve the user's demand_mbps from that AP's capacity_mbps.
            Assign, recurse, then undo the assignment and reservation.
        Also recurse without this user to find the best partial assignment.
        Return best assignments, unserved IDs, and completeness.

    This function NEVER changes settings. Use it for normal service, unchanged
    reassignment, and each proposed recovery configuration. First-fit alone can
    falsely reject feasible service. Start small: backtracking can be expensive.
    Keep a small consistent tolerance for fractional-Mbps capacity comparisons;
    do not round each device's demand to an integer or split it across APs.
    """
    raise NotImplementedError("Implement capacity-aware device assignment.")


def recover_service(
    scenario: Scenario,
    configuration: Configuration,
    failed_ap_id: str,
) -> FailureResult:
    """Try reassignment first, then greedy setting increases on surviving APs.

    Proposed recovery pseudocode:
        Copy the original configuration. Request only the critical users.
        Assign them with the failed AP excluded; save this as unchanged.
        Record the original surviving-AP watts.
        If unchanged is complete, return it with no changes or recovery attempt.
        Otherwise, mark recovery attempted and repeat:
            Try each surviving AP at each available higher-watt setting.
            Reassign ALL critical users from scratch for each copied trial.
            gain = trial served count - current served count.
            cost = trial surviving watts - current surviving watts.
            Among gain > 0 trials, choose largest gain / cost.
            Break ties consistently by AP ID and setting name.
            Keep that trial; stop on complete service or no positive-gain trial.
        Return unchanged, final service, final copied configuration, changed APs,
        and surviving watts before/after. Preserve partial results on a stall.

    Never modify the input, change the failed AP, turn APs off, or move devices.
    Each failure starts independently from the original normal configuration.
    There is no search state beyond the supplied AP settings. Setting increases
    make the loop finite, but greedy can miss combinations needing an initial
    zero-gain change. A stall means this method found no recovery, not a proof
    that recovery is impossible. This procedure minimizes neither changes nor
    watts globally; report actual changes. No reconnection-time guarantee.
    """
    raise NotImplementedError("Implement reassignment and greedy power recovery.")


def evaluate_configuration(
    scenario: Scenario,
    configuration: Configuration,
    failure_policy: FailurePolicy = "recovery",
) -> Evaluation:
    """Check normal service and the selected SINGLE-failure policy.

    Pseudocode:
        Require exactly one valid ON setting per installed AP and a known policy.
        Calculate normal energy and assign ALL users normally.
        For normal_only: failures = None; feasible = normal.complete.
        Otherwise, for EACH installed AP, independently:
            For recovery: call recover_service with the ORIGINAL configuration.
            For fixed_settings: assign critical users without changing settings;
                wrap this in FailureResult with unchanged == final and no changes.
            Store the result under the failed AP ID.
        Feasible means normal complete AND each failure's final service complete.
        Return energy, normal, failures, policy, and feasibility.

    Noncritical users may lose service after failure. A failed AP is unavailable
    in every trial. Fixed settings is only a comparison policy; recovery is the
    selected project behavior. Unchecked failures must not count as passed.
    """
    raise NotImplementedError("Implement normal and independent failure evaluation.")
