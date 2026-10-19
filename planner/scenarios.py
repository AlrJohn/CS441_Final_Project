"""Scenario loading and input checks belong together here.

Start with data/toy_shelter.json. Keep file reading outside the algorithms so
the same in-memory Scenario works in the interface, experiments, and tests.
The example's coverage sets are declared inputs, not measured radio coverage.
"""

from pathlib import Path

from .models import Scenario


def load_scenario(path: str | Path) -> Scenario:
    """Read a scenario and return the shared data objects.

    Pseudocode:
        Open the JSON file and read its dictionary.
        Build User objects from the user records.
        Build each AP's named PowerSetting objects; convert coverage lists to sets.
        Build AccessPoint objects, then one Scenario.
        Call validate_scenario before returning it.

    Keep useful file/field names in error messages. Use demand_mbps and
    capacity_mbps explicitly; do not accept old generic capacity field names
    silently. models.py defines the one shared demand model.
    """
    raise NotImplementedError("Implement JSON loading after reviewing models.py.")


def validate_scenario(scenario: Scenario) -> None:
    """Return normally for valid input; raise ValueError for invalid input.

    Pseudocode:
        Check unique user IDs and AP IDs, and finite numeric values.
        Require positive demand_mbps and interval_hours, nonnegative capacity_mbps.
        Require positive electrical_watts for every ON setting; no off state.
        Check that every AP has settings and a valid highest_setting.
        Require highest_setting to have maximal electrical draw for that AP.
        Do not assume greater watts automatically means greater capacity/reach.
        Check that coverage sets mention only known user IDs.
        Allow unequal and fractional Mbps demands; never convert them to slots.

    Valid inputs may still describe an impossible service problem. Do not reject
    those as malformed: the service checker and experiments must report them.
    """
    raise NotImplementedError("Implement scenario consistency and unit checks.")
