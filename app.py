"""Streamlit entry point. Keep algorithms inside planner/, not inside UI callbacks.

Planned interface pseudocode:
    Load a selected scenario using scenarios.load_scenario.
    Let the user choose greedy or annealing and explicit search settings.
    On Run, call the selected search function and keep its result in session_state.
    If no plan was found, show its explanation without drawing a fake result.
    Otherwise, display energy and normal-service status.
    Offer a selector of installed APs, plus normal operation; every AP starts on.
    For a selected failure, call simulation.recover_service on the original plan.
    Display unchanged reassignment first, then final service and changed settings.
    Plot the two results with devices in the same locations; exclude the failed AP.
    Show surviving watts before/after, not invented reconnection times or outage Wh.

For now, main() provides a working landing page only. Wire in the above steps
after the simulation and search functions are implemented and checked.
"""


def main() -> None:
    """Show the starter page; add controls after the core functions are ready."""
    import streamlit as st

    st.set_page_config(page_title="Shelter Wi-Fi Planner", layout="wide")
    st.title("Wi-Fi planning for temporary shelters")
    st.write(
        "Keep every functioning access point on and choose energy-efficient "
        "settings. After one AP fails, try reassignment first, then adjust "
        "surviving AP settings to restore critical-device service."
    )
    st.info("Starter scaffold: the simulation and search still need to be implemented.")
    st.markdown(
        "Start with `planner/models.py` and `planner/scenarios.py`, then implement "
        "the service checker in `planner/simulation.py`. The search pseudocode "
        "is in `planner/search.py`."
    )


if __name__ == "__main__":
    main()
