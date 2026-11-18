"""Streamlit workflow: load a shelter, plan normal settings, then compare recovery.

Algorithms stay inside planner/. Session state retains measured results across
widget reruns; changing inputs never silently relabels stale results as new ones.
Run from the repository root: .venv/Scripts/python.exe -m streamlit run app.py
"""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from planner.experiments import (
    compare_planning, compare_recovery, planning_summary, recovery_summary, results_to_csv,
)
from planner.models import AnnealingSettings, RecoveryAnnealingSettings
from planner.scenarios import load_scenario, scenario_from_dict
from planner.search import all_high_configuration
from planner.simulation import assign_users


ROOT = Path(__file__).resolve().parent
EXAMPLES = {
    "Toy shelter": "toy_shelter.json",
    "Larger shelter": "larger_shelter.json",
    "Recovery combination challenge": "recovery_challenge.json",
    "Unreachable critical device": "unreachable_critical.json",
}


def _settings_table(scenario, configuration, service, failed_ap_id=None):
    """Show selected settings and actual assigned demand for each functioning AP."""
    rows = []
    users = {user.user_id: user for user in scenario.users}
    for ap in scenario.access_points:
        devices = []
        load = 0.0
        for user_id, ap_id in service.assignments.items():
            if ap_id == ap.ap_id:
                devices.append(user_id)
                load += users[user_id].demand_mbps
        selected = ap.settings[configuration[ap.ap_id]]
        failed = ap.ap_id == failed_ap_id
        rows.append({"AP": ap.ap_id, "Setting": "Failed" if failed else configuration[ap.ap_id],
                     "Operating W": None if failed else selected.electrical_watts,
                     "Assigned Mbps": load, "Capacity Mbps": None if failed else selected.capacity_mbps,
                     "Devices": ", ".join(sorted(devices))})
    return rows


def _show_trace(st, scenario, history, unit, key, failed_ap_id=None,
                selected_changes_only=False, total_trials=None):
    """Display the measured trajectory, replay current states, and export full events."""
    from planner.visuals import plot_layout, plot_trace

    if not history:
        st.info("The all-high reference uses maximum settings without searching for alternatives.")
        return
    st.pyplot(plot_trace(history, unit, selected_changes_only, total_trials))
    index = len(history) - 1
    if len(history) > 1:
        index = st.slider("Replay step", 0, len(history) - 1, index, key=f"{key}_frame")
    event = history[index]
    required_ids = set()
    for user in scenario.users:
        if failed_ap_id is None or user.critical:
            required_ids.add(user.user_id)
    service = assign_users(scenario, event.configuration, required_ids, failed_ap_id)
    cost_label = "Normal energy" if unit == "Wh" else "Surviving AP power"
    st.caption(f"Setting changes tested: {event.step}. {cost_label}: {event.current_value:g} {unit}.")
    st.pyplot(plot_layout(scenario, event.configuration, service, failed_ap_id))
    events = []
    for item in history:
        events.append({
            "Changes tested": item.step,
            f"Current plan ({unit})": item.current_value,
            f"Best plan ({unit})": item.best_value,
            f"Tested change ({unit})": item.candidate_value,
            "Change accepted": item.accepted,
            "Tested change meets requirement": item.feasible,
            "Tested change: devices served": f"{item.served_count}/{item.required_count}",
            "Current AP settings": json.dumps(item.configuration, sort_keys=True),
            "Temperature": item.temperature,
        })
    st.dataframe(events, hide_index=True)
    st.download_button("Download search trace", results_to_csv([asdict(item) for item in history]),
                       file_name=f"{key}_trace.csv", mime="text/csv", key=f"{key}_download")


def _show_inputs(st, scenario, raw_json):
    """Explain the simulation inputs and expose them without promising real RF behavior."""
    st.subheader("Scenario inputs")
    st.write(scenario.description)
    st.dataframe([{"Device": user.user_id, "Critical": user.critical,
                   "Demand Mbps": user.demand_mbps, "x": user.x, "y": user.y}
                  for user in scenario.users], hide_index=True)
    setting_rows = []
    for ap in scenario.access_points:
        for name, setting in ap.settings.items():
            setting_rows.append({"AP": ap.ap_id, "Setting": name,
                                 "Electrical W": setting.electrical_watts,
                                 "Capacity Mbps": setting.capacity_mbps,
                                 "Reachable devices": ", ".join(sorted(setting.covered_user_ids))})
    st.dataframe(setting_rows, hide_index=True)
    st.info("All built-in values are synthetic. Lines show assignments; positions do not calculate radio coverage. "
            "Every functioning AP stays on. Power, capacity, and declared reach are separate inputs.")
    st.write("Normal service requires every device. After one failure, all critical devices are required; "
             "guests may lose service. Recovery timing, interference, and upstream capacity are outside this model.")
    st.download_button("Download scenario JSON", raw_json, file_name=f"{scenario.scenario_id}.json", mime="application/json")


def main() -> None:
    """Render controls and the complete planning/failure workflow from real results."""
    import streamlit as st
    from planner.visuals import plot_comparison, plot_layout

    st.set_page_config(page_title="Shelter Wi-Fi Planner", page_icon="📡", layout="wide")
    st.caption("CS441 · AI group project")
    st.title("Wi-Fi planning & recovery")
    st.write("Compare AP power settings, simulate one failure, and see how critical devices reconnect.")

    with st.sidebar:
        st.header("Run controls")
        selected_example = st.selectbox("Shelter scenario", list(EXAMPLES) + ["Upload JSON"])
        uploaded = st.file_uploader("Scenario JSON", type=["json"]) if selected_example == "Upload JSON" else None
        seed = st.number_input("Random seed", min_value=0, max_value=999999, value=441, step=1)
        proposals = st.slider(
            "Annealing change limit", 50, 1500, 300, step=50,
            help="Maximum AP setting changes to test in each annealing run. The search may stop earlier as it cools.",
        )
        with st.expander("Annealing parameters"):
            normal_temperature = st.number_input("Normal start temperature (Wh)", min_value=0.02, value=5.0)
            minimum = st.number_input("Minimum temperature", min_value=0.0001, value=0.01, format="%.4f")
            cooling = st.number_input("Cooling rate", min_value=0.5, max_value=0.9999, value=0.99, format="%.4f")

    try:
        if selected_example == "Upload JSON":
            if uploaded is None:
                st.info("Upload a scenario JSON, or choose one of the built-in examples.")
                return
            raw_json = uploaded.getvalue().decode("utf-8-sig")
            scenario = scenario_from_dict(json.loads(raw_json))
        else:
            path = ROOT / "data" / EXAMPLES[selected_example]
            raw_json = path.read_text(encoding="utf-8-sig")
            scenario = load_scenario(path)
        # The exact assignment checker is intended for small interactive cases.
        if len(scenario.access_points) > 8 or len(scenario.users) > 16:
            raise ValueError("Interactive examples support up to 8 APs and 16 devices; the exact checker can become expensive.")
        if normal_temperature <= minimum:
            raise ValueError("Normal starting temperature must be greater than the minimum.")
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        st.error(f"Cannot run these inputs: {error}")
        return

    scenario_key = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    if st.session_state.get("scenario_key") != scenario_key:
        st.session_state["scenario_key"] = scenario_key
        st.session_state.pop("planning", None)
        st.session_state.pop("recovery", None)
    settings = AnnealingSettings(normal_temperature, minimum, cooling, proposals, seed)
    planning_key = (scenario_key, tuple(asdict(settings).values()))

    columns = st.columns(3)
    columns[0].metric("Installed APs · all on", len(scenario.access_points))
    columns[1].metric("Critical devices", sum(user.critical for user in scenario.users))
    columns[2].metric("Total demand (Mbps)", f"{sum(user.demand_mbps for user in scenario.users):g}")
    normal_tab, failure_tab, inputs_tab = st.tabs(["1 · Normal planning", "2 · Failure & recovery", "3 · Inputs & model"])

    with normal_tab:
        st.subheader("Choose an energy-efficient normal plan")
        if st.button("Run planning comparison", type="primary", key="run_planning"):
            with st.spinner("Comparing reference, greedy, and annealing plans…"):
                # Every normal planner checks the same rule: serve all devices.
                # Failures and recovery are evaluated later on the second tab.
                runs = compare_planning(scenario, settings, failure_policy="normal_only")
            st.session_state["planning"] = {"key": planning_key, "runs": runs}
            st.session_state.pop("recovery", None)
            st.session_state.pop("selected_normal", None)

        planning = st.session_state.get("planning")
        stale = planning is not None and planning["key"] != planning_key
        if stale:
            st.warning("Planning controls changed. Run the comparison again to update these results.")
        if planning is None:
            reference = all_high_configuration(scenario)
            service = assign_users(scenario, reference, {user.user_id for user in scenario.users})
            st.pyplot(plot_layout(scenario, reference, service))
            st.caption("Preview: all-high settings. Stars = critical devices; circles = guests; squares = APs. Green = served, red = unserved.")
            st.info("Run the planning comparison, then open Failure & recovery to test a selected AP.")
        else:
            runs = planning["runs"]
            rows = planning_summary(scenario, runs)
            st.pyplot(plot_comparison(rows))
            display_rows = []
            for row in rows:
                display_rows.append({"Method": row["method"], "Normal Wh": row["energy_wh"],
                                     "Served": f"{row['normal_served']}/{row['normal_total']}" if row["normal_served"] is not None else "No plan",
                                     "Changes tested": row["trials"], "Runtime ms": round(row["runtime_seconds"] * 1000, 2)})
            st.dataframe(display_rows, hide_index=True)
            valid_runs = {}
            for run in runs:
                if run["result"].configuration is not None and run["result"].evaluation.normal.complete:
                    valid_runs[run["method"]] = run
            if not valid_runs:
                st.error("No normal plan serves every device. Review the scenario's reach and capacity.")
            else:
                names = list(valid_runs)
                selected_method = st.selectbox("Plan to inspect", names, index=names.index("Greedy") if "Greedy" in names else 0,
                                               key="selected_plan")
                selected = valid_runs[selected_method]["result"]
                st.session_state["selected_normal"] = {"scenario": scenario_key, "method": selected_method,
                                                       "result": selected, "planning_key": planning["key"]}
                st.pyplot(plot_layout(scenario, selected.configuration, selected.evaluation.normal))
                st.dataframe(_settings_table(scenario, selected.configuration, selected.evaluation.normal), hide_index=True)
                with st.expander("Inspect normal search steps"):
                    _show_trace(st, scenario, selected.history, "Wh", f"normal_{selected_method}",
                                selected_changes_only=selected_method == "Greedy", total_trials=selected.steps)
            st.download_button("Download planning comparison", results_to_csv(rows),
                               file_name="planning_comparison.csv", mime="text/csv")

    with failure_tab:
        st.subheader("Simulate one AP failure")
        selected_normal = st.session_state.get("selected_normal")
        if planning is None or stale or selected_normal is None or selected_normal["scenario"] != scenario_key:
            st.info("Run a current planning comparison and select a normal plan first.")
        elif not scenario.access_points:
            st.info("This scenario has no AP to fail.")
        else:
            normal_plan = selected_normal["result"].configuration
            st.write(f"Normal plan: **{selected_normal['method']}**")
            ap_ids = sorted(normal_plan)
            default_ap = ap_ids.index("F") if "F" in ap_ids else 0
            failed_ap = st.selectbox("Failed AP", ap_ids, index=default_ap, key="failed_ap")
            with st.expander("Recovery search settings"):
                recovery_temperature = st.number_input("Recovery start temperature (W)", min_value=0.02, value=5.0)
            recovery_settings = RecoveryAnnealingSettings(recovery_temperature, minimum, cooling, proposals, seed)
            recovery_controls_valid = recovery_temperature > minimum
            if not recovery_controls_valid:
                st.error("Recovery starting temperature must be greater than the minimum temperature.")
            recovery_key = (planning_key, selected_normal["method"], failed_ap, tuple(asdict(recovery_settings).values()))
            if st.button("Compare recovery methods", type="primary", key="run_recovery", disabled=not recovery_controls_valid):
                with st.spinner("Trying reassignment, greedy recovery, and annealing recovery…"):
                    recovery_runs = compare_recovery(scenario, normal_plan, failed_ap, recovery_settings)
                st.session_state["recovery"] = {"key": recovery_key, "runs": recovery_runs}
            recovery = st.session_state.get("recovery")
            if recovery is None or recovery["key"] != recovery_key:
                st.info("Compare recovery to see the unchanged state and both recovery outcomes for this AP.")
            else:
                recovery_runs = recovery["runs"]
                rows = recovery_summary(scenario, failed_ap, recovery_runs)
                st.pyplot(plot_comparison(rows))
                st.dataframe([{"Method": row["method"],
                               "Critical served": f"{row['critical_served']}/{row['critical_total']}",
                               "Complete": row["complete"], "Surviving W": row["surviving_watts"],
                               "Extra W": row["extra_watts"], "Changed APs": ", ".join(row["changed_aps"]) or "None",
                               "Changes tested": row["trials"], "Runtime ms": round(row["runtime_seconds"] * 1000, 2)}
                              for row in rows], hide_index=True)
                method_names = [run["method"] for run in recovery_runs]
                detail_method = st.radio("Inspect recovery method", method_names, index=2, horizontal=True, key="recovery_detail")
                detail = recovery_runs[method_names.index(detail_method)]["result"]
                failure = detail.failure
                if failure.final.complete:
                    st.success("All critical devices are serviceable in this outcome.")
                else:
                    st.warning("Critical devices still unserved: " + ", ".join(failure.final.unserved_user_ids))
                st.pyplot(plot_layout(scenario, failure.configuration, failure.final, failed_ap))
                st.dataframe(_settings_table(scenario, failure.configuration, failure.final, failed_ap), hide_index=True)
                with st.expander("Inspect recovery search steps"):
                    _show_trace(st, scenario, failure.history, "W", f"recovery_{detail_method}", failed_ap,
                                selected_changes_only=detail_method == "Greedy recovery", total_trials=detail.steps)
                export_rows = []
                for row in rows:
                    export_rows.append({**row, "scenario_id": scenario.scenario_id,
                                        "normal_plan": normal_plan, "annealing_settings": asdict(recovery_settings)})
                st.download_button("Download recovery comparison", results_to_csv(export_rows),
                                   file_name=f"recovery_{failed_ap}.csv", mime="text/csv")

    with inputs_tab:
        _show_inputs(st, scenario, raw_json)


if __name__ == "__main__":
    main()
