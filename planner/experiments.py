"""Run fair comparisons and save actual measurements, separate from the UI.

Keep one result row per scenario/method/run, including unsuccessful runs.
Suggested columns: scenario_id, method, seed, search settings, solver_seconds,
steps, configuration, energy_wh, normal_served, normal_total, critical_total,
worst_critical_before, worst_critical_after, recovery_feasible, fixed_feasible,
max_recovery_extra_watts, max_changed_aps, failure_details, and status.
"""

from pathlib import Path

from .models import AnnealingSettings, Scenario
from .search import all_high_configuration, greedy, simulated_annealing
from .simulation import evaluate_configuration


def run_comparison(
    scenario: Scenario, settings_by_run: list[AnnealingSettings]
) -> list[dict]:
    """Compare all-high, greedy, and annealing under explicit service policies.

    Pseudocode:
        Build and check the all-high reference. Record it even if it fails.
        Run normal-service greedy once; measure solver time with perf_counter.
        For each settings/seed pair, run annealing using normal_only, fixed_settings,
        and recovery policies. The fixed policy is a comparison, not our app's goal.
            Use the same start and search settings. Check start for each policy.
        After timing each solver, re-evaluate its returned plan under recovery.
        Record normal service, unchanged and recovered critical counts per failure,
        changed AP IDs, and surviving watts before/after for each failure.
        Derive fixed feasibility from unchanged service plus normal completeness.
        Report worst-case counts, maximum additional surviving watts, and maximum
        changed APs. Those maxima can come from DIFFERENT failures: keep details.
        Record failed searches as failed rows, with metrics missing rather than zero.
        Return rows; compute repeated-run summaries from successful runs and report
        how many runs failed as well. Keep measurements separate from solver time.

    If there are no critical users, report count 0 and mark a fraction N/A. If
    there are no APs, still enforce normal service; an empty failure list
    cannot excuse unserved normal users. Do not invent a plan for a failed run.
    """
    raise NotImplementedError("Implement controlled repeated comparisons.")


def save_results(rows: list[dict], path: str | Path) -> None:
    """Save one CSV with Python's csv module.

    Pseudocode:
        Use consistent column names and create the output parent folder if needed.
        Serialize configuration, search settings, and failure details as JSON strings.
        Write the header and every row, including statuses for unsuccessful runs.
        Keep missing metrics blank. Use a new filename for a new experiment.
    """
    raise NotImplementedError("Implement CSV output without overwriting prior runs.")
