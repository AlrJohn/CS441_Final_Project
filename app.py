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

For now, main() provides a landing page only. Simulation and configuration search
are implemented; production loading, plotting, and interface integration remain.
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
    st.info(
        "Simulation and configuration search are implemented and tested. "
        "Loading, plotting, and UI integration are still in progress."
    )
    st.markdown(
        "Review the shared contract in `planner/models.py` and the working "
        "simulation and search in `planner/simulation.py` and `planner/search.py`. "
        "Run `python -m unittest discover -s tests -v` for all 48 core tests. "
        "The next milestone is connecting the loader and results to this interface."
    )


if __name__ == "__main__":
    main()
