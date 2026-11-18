"""Exercise real Streamlit widgets, stale-state handling, and recovery outcomes."""

from pathlib import Path
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

APP = Path(__file__).resolve().parents[1] / "app.py"


def widget_by_label(widgets, label):
    """Find a UI control by its displayed label rather than its changing position."""
    for widget in widgets:
        if widget.label == label:
            return widget
    raise AssertionError(f"Widget not found: {label}")


@unittest.skipIf(AppTest is None, "Install requirements.txt to run Streamlit UI tests.")
class AppTests(unittest.TestCase):
    """Run UI flows with the actual simulator and algorithms, without fake results."""

    def setUp(self):
        """Create a fresh app session for each test."""
        self.app = AppTest.from_file(str(APP), default_timeout=60).run()

    def test_initial_page_previews_inputs_without_running_search(self):
        """A new session is readable and waits for an explicit planning run."""
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.app.tabs), 3)
        self.assertEqual(self.app.button(key="run_planning").label, "Run planning comparison")
        self.assertTrue(any("Run the planning comparison" in item.value for item in self.app.info))

    def test_planning_and_toy_recovery_work_end_to_end(self):
        """Real controls select the greedy plan and compare recovery after AP1 fails."""
        self.app.button(key="run_planning").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.selectbox(key="selected_plan").value, "Greedy")
        self.app.button(key="run_recovery").click().run()
        self.assertEqual(len(self.app.exception), 0)
        outcomes = self.app.session_state["recovery"]["runs"]
        self.assertFalse(outcomes[0]["result"].failure.final.complete)
        self.assertTrue(outcomes[1]["result"].failure.final.complete)
        self.assertTrue(outcomes[2]["result"].failure.final.complete)

    def test_combination_challenge_shows_different_recovery_outcomes(self):
        """Greedy's limitation and annealing's successful combination remain visible."""
        widget_by_label(self.app.selectbox, "Shelter scenario").select("Recovery combination challenge").run()
        self.app.button(key="run_planning").click().run()
        self.assertEqual(self.app.selectbox(key="failed_ap").value, "F")
        self.app.button(key="run_recovery").click().run()
        self.assertEqual(len(self.app.exception), 0)
        outcomes = self.app.session_state["recovery"]["runs"]
        self.assertFalse(outcomes[1]["result"].failure.final.complete)
        self.assertTrue(outcomes[2]["result"].failure.final.complete)
        self.app.radio(key="recovery_detail").set_value("Greedy recovery").run()
        self.assertTrue(any("Critical devices still unserved" in item.value for item in self.app.warning))

    def test_infeasible_recovery_is_shown_honestly(self):
        """The UI must retain failed outcomes rather than fabricate a complete plan."""
        widget_by_label(self.app.selectbox, "Shelter scenario").select("Unreachable critical device").run()
        self.app.button(key="run_planning").click().run()
        self.app.button(key="run_recovery").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertTrue(any("Critical devices still unserved: C1" in item.value for item in self.app.warning))

    def test_changed_controls_mark_old_planning_results_stale(self):
        """New settings cannot silently relabel existing results as a fresh run."""
        self.app.button(key="run_planning").click().run()
        widget_by_label(self.app.number_input, "Random seed").set_value(442).run()
        self.assertTrue(any("Planning controls changed" in item.value for item in self.app.warning))
        self.assertFalse(any(item.key == "run_recovery" for item in self.app.button))

    def test_normal_planning_does_not_screen_future_failures(self):
        """A valid normal plan survives planning even if a later failure is unrecoverable."""
        widget_by_label(self.app.selectbox, "Shelter scenario").select("Unreachable critical device").run()
        self.app.button(key="run_planning").click().run()
        self.assertEqual(len(self.app.exception), 0)
        runs = self.app.session_state["planning"]["runs"]
        self.assertEqual(len(runs), 3)
        for run in runs:
            result = run["result"]
            self.assertIsNotNone(result.configuration)
            self.assertTrue(result.evaluation.normal.complete)
            self.assertEqual(result.evaluation.failure_policy, "normal_only")
            self.assertIsNone(result.evaluation.failures)
        self.assertFalse(any(item.label == "Annealing service requirement" for item in self.app.selectbox))
        self.assertNotIn("Check performed", self.app.dataframe[0].value.columns)
        self.app.button(key="run_recovery").click().run()
        for run in self.app.session_state["recovery"]["runs"]:
            self.assertFalse(run["result"].failure.final.complete)

    def test_recovery_temperature_does_not_invalidate_normal_planning(self):
        """Recovery controls affect the failure stage without rerunning normal planning."""
        self.app.button(key="run_planning").click().run()
        original_key = self.app.session_state["planning"]["key"]
        original_plan = self.app.session_state["selected_normal"]["result"].configuration.copy()
        widget_by_label(self.app.number_input, "Recovery start temperature (W)").set_value(7.0).run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state["planning"]["key"], original_key)
        self.assertEqual(self.app.session_state["selected_normal"]["result"].configuration, original_plan)
        self.assertFalse(self.app.button(key="run_recovery").disabled)
        self.app.button(key="run_recovery").click().run()
        self.assertTrue(self.app.session_state["recovery"]["runs"][2]["result"].failure.final.complete)

    def test_scenario_switch_clears_previous_results(self):
        """Changing the input scenario cannot reuse a previous shelter's assignments."""
        self.app.button(key="run_planning").click().run()
        widget_by_label(self.app.selectbox, "Shelter scenario").select("Larger shelter").run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertTrue(any("Run the planning comparison" in item.value for item in self.app.info))


if __name__ == "__main__":
    unittest.main()
