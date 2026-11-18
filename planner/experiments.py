"""Time comparable runs and export measured outcomes, independently of Streamlit."""

import csv
from dataclasses import asdict
from io import StringIO
import json
from pathlib import Path
from time import perf_counter

from .models import (
    AnnealingSettings, FailureResult, RecoveryAnnealingSettings,
    RecoverySearchResult, Scenario, SearchResult,
)
from .search import all_high_configuration, greedy, simulated_annealing, simulated_annealing_recovery
from .simulation import assign_users, calculate_power, evaluate_configuration, recover_service


def compare_planning(scenario, settings, failure_policy="normal_only"):
    """Run the reference and both normal planners once; record actual wall time.

    The app uses normal_only for every method, then compares recovery on the
    failure tab. Explicit failure policies remain available for separate Python
    experiments; they apply to annealing and the reference, while greedy remains
    normal-only. A reference with incomplete service is retained.
    """
    runs = []
    start = all_high_configuration(scenario)
    for method in ("All-high reference", "Greedy", "Simulated annealing"):
        started = perf_counter()
        if method == "All-high reference":
            evaluation = evaluate_configuration(scenario, start, failure_policy)
            result = SearchResult(start.copy(), evaluation, 0, "All APs use their highest setting.")
        elif method == "Greedy":
            result = greedy(scenario)
        else:
            result = simulated_annealing(scenario, start, settings, failure_policy)
        runs.append({"method": method, "result": result, "seconds": perf_counter() - started})
    return runs


def compare_recovery(scenario, configuration, failed_ap_id, settings: RecoveryAnnealingSettings):
    """Compare unchanged, greedy, and annealing from the SAME normal configuration.

    No full annealing loop is nested inside normal planning. Each recovery method
    independently sees the same demands, failed AP, and original power settings.
    """
    runs = []
    critical_ids = {user.user_id for user in scenario.users if user.critical}
    for method in ("Unchanged settings", "Greedy recovery", "Annealing recovery"):
        started = perf_counter()
        if method == "Unchanged settings":
            service = assign_users(scenario, configuration, critical_ids, failed_ap_id)
            watts = calculate_power(scenario, configuration, failed_ap_id)
            failure = FailureResult(service, service, configuration.copy(), False, [], watts, watts)
            result = RecoverySearchResult(failure, 0, "Reassignment only; power settings unchanged.")
        elif method == "Greedy recovery":
            failure = recover_service(scenario, configuration, failed_ap_id)
            message = "Greedy restored all critical devices." if failure.final.complete else (
                "Greedy found no complete recovery; a different combination may still work."
            )
            result = RecoverySearchResult(failure, failure.trials, message)
        else:
            result = simulated_annealing_recovery(scenario, configuration, failed_ap_id, settings)
        runs.append({"method": method, "result": result, "seconds": perf_counter() - started})
    return runs


def planning_summary(scenario, runs):
    """Flatten normal results; preserve missing plans rather than inventing zeros."""
    rows = []
    for run in runs:
        result = run["result"]
        evaluation = result.evaluation
        rows.append({
            "method": run["method"],
            "energy_wh": evaluation.energy_wh if evaluation else None,
            "normal_served": len(evaluation.normal.assignments) if evaluation else None,
            "normal_total": len(scenario.users),
            "policy": evaluation.failure_policy if evaluation else None,
            "policy_passed": evaluation.feasible if evaluation else False,
            "trials": result.steps, "runtime_seconds": run["seconds"],
            "configuration": result.configuration, "status": result.message,
        })
    return rows


def recovery_summary(scenario, failed_ap_id, runs):
    """Report recovery watts, complete service, settings, trials, and measured time."""
    rows = []
    critical_total = sum(user.critical for user in scenario.users)
    for run in runs:
        result = run["result"]
        failure = result.failure
        rows.append({
            "method": run["method"], "failed_ap": failed_ap_id,
            "critical_served": len(failure.final.assignments), "critical_total": critical_total,
            "complete": failure.final.complete,
            "surviving_watts": failure.surviving_watts_after,
            "extra_watts": failure.surviving_watts_after - failure.surviving_watts_before,
            "changed_aps": failure.changed_ap_ids, "trials": result.steps,
            "runtime_seconds": run["seconds"], "configuration": failure.configuration,
            "unserved": failure.final.unserved_user_ids, "status": result.message,
        })
    return rows


def results_to_csv(rows: list[dict]) -> str:
    """Serialize rows for download, keeping nested values as readable JSON fields."""
    output = StringIO(newline="")
    if not rows:
        return ""
    fields = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        flat = {}
        for key, value in row.items():
            flat[key] = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
        writer.writerow(flat)
    return output.getvalue()


def run_comparison(scenario: Scenario, settings_by_run: list[AnnealingSettings]) -> list[dict]:
    """Run repeated normal-planning comparisons, then report full recovery checks.

    Reference and greedy run once. Annealing runs under each policy for each
    supplied seed/settings pair. Failure summaries are outside solver timing.
    This is separate from the UI's selected-failure recovery comparison.
    """
    if not settings_by_run:
        return []
    first_runs = compare_planning(scenario, settings_by_run[0], "normal_only")
    records = [(first_runs[0], None), (first_runs[1], None)]
    for index, settings in enumerate(settings_by_run):
        for policy in ("normal_only", "fixed_settings", "recovery"):
            if index == 0 and policy == "normal_only":
                run = first_runs[2]
            else:
                started = perf_counter()
                result = simulated_annealing(scenario, all_high_configuration(scenario), settings, policy)
                run = {"method": "Simulated annealing", "result": result, "seconds": perf_counter() - started}
            records.append((run, settings))
    rows = []
    for run, settings in records:
        row = planning_summary(scenario, [run])[0]
        row.update(scenario_id=scenario.scenario_id, seed=settings.seed if settings else None,
                   settings=asdict(settings) if settings else None)
        plan = run["result"].configuration
        if plan is not None:
            full = evaluate_configuration(scenario, plan, "recovery")
            row["recovery_passed"] = full.feasible
            row["failure_details"] = {
                ap_id: {"complete": failure.final.complete,
                        "critical_served": len(failure.final.assignments),
                        "watts_after": failure.surviving_watts_after,
                        "changed_aps": failure.changed_ap_ids}
                for ap_id, failure in full.failures.items()
            }
        rows.append(row)
    return rows


def save_results(rows: list[dict], path: str | Path) -> None:
    """Save CSV to a new filename; never silently overwrite previous experiment data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as output_file:
        output_file.write(results_to_csv(rows))
