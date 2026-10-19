"""Plotting only. Read the model's results; do not decide service in a chart.

Use Matplotlib when implementing these functions and return Figure objects.
Streamlit can display them; experiments can save the same figures to files.
"""

from typing import TYPE_CHECKING

from .models import Configuration, Scenario, ServiceResult

if TYPE_CHECKING:
    from matplotlib.figure import Figure


def plot_layout(
    scenario: Scenario,
    configuration: Configuration,
    service: ServiceResult,
    failed_ap_id: str | None = None,
) -> "Figure":
    """Show a normal or failed configuration with its actual assignment result.

    Pseudocode:
        Plot users and fixed AP positions with equal x/y scale.
        Distinguish critical users by a star and failed APs by a cross and label.
        All functioning APs are on; label their selected settings.
        Draw user-to-AP lines from service.assignments only.
        Mark unserved users clearly and add a concise legend.
        Return the figure. Draw coverage circles only after a radius model is agreed.

    Geometry alone does not establish coverage when inputs are reachability sets.
    For a recovery comparison, call this twice: once with the normal settings and
    FailureResult.unchanged, then with its configuration and final service. Keep
    device positions fixed in both panels and list changed APs alongside them.
    """
    raise NotImplementedError("Implement the scenario and failure visualization.")


def plot_comparison(rows: list[dict]) -> "Figure":
    """Plot measured energy/service results without disguising failed runs.

    Pseudocode:
        Group comparable rows by method within the same scenario.
        Plot measured energy in Wh and show run-to-run variation for annealing.
        Identify which configurations pass the full service policy.
        Plot before/after critical service and recovery extra watts separately.
        Show failed-run counts separately; never plot missing metrics as zero.
        Return a labeled figure. Do not mix different scenarios into one mean.
    """
    raise NotImplementedError("Implement plots after there are real experiment rows.")
