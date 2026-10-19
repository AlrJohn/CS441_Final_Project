"""Shared data containers used by loading, simulation, search, and the interface.

Dataclasses store related values together without custom class machinery.
Treat scenario data as read-only. Search changes copies of Configuration only.
The shared model uses variable device demands and usable AP capacity in Mbps,
electrical draw in watts, and normal-operation energy in Wh. Mbps is megabits
per second, not megabytes per second. These are modeled service budgets, not
measured throughput or an AP's advertised radio signaling rate.

This module imports no other planner module. Input validation belongs in
scenarios.py; assignments, recovery, and energy calculations belong in
simulation.py. Function signatures elsewhere refer to these containers.
"""

from dataclasses import dataclass
from typing import Literal, TypeAlias


Configuration: TypeAlias = dict[str, str]  # Every installed AP -> an ON setting.
Assignment: TypeAlias = dict[str, str]  # user ID -> exactly one serving AP ID
FailurePolicy: TypeAlias = Literal["normal_only", "fixed_settings", "recovery"]


@dataclass
class User:
    """One stationary client device, rather than a person or a whole building.

    Keep the existing User/user_id names consistent throughout the project.
    critical controls failure priority; demand_mbps controls capacity use.
    These are independent: a critical device need not have the largest demand.
    demand_mbps is a positive required rate budget, served wholly by one AP;
    it is not measured traffic. This model uses a single combined traffic budget,
    without separate upload/download constraints or splitting across APs.
    Coordinates are plotting positions in the scenario's common local units.
    """

    user_id: str
    x: float
    y: float
    critical: bool
    demand_mbps: float


@dataclass
class PowerSetting:
    """Inputs describing one available ON setting of one AP.

    electrical_watts is total modeled AP electrical draw, not transmit dBm.
    capacity_mbps is modeled usable aggregate capacity, shared by assigned
    devices: their demand_mbps sum must fit within it. covered_user_ids declares
    reachability, independent of the coordinates. Raising power does not itself
    imply a capacity increase. The scenario author supplies all three inputs.
    """

    electrical_watts: float
    capacity_mbps: float
    covered_user_ids: set[str]


@dataclass
class AccessPoint:
    """One installed AP at a fixed position with named ON settings.

    settings maps names such as low/high to PowerSetting objects. There is no
    off setting. highest_setting names the maximum modeled electrical draw;
    it is explicit rather than inferred from dictionary order or spelling.
    """

    ap_id: str
    x: float
    y: float
    highest_setting: str  # Explicit name, not an assumption about dict order.
    settings: dict[str, PowerSetting]


@dataclass
class Scenario:
    """One shelter's inputs, shared unchanged by every method being compared.

    interval_hours is the NORMAL energy comparison horizon, not an outage time.
    Users and APs have unique IDs within their respective collections. Search
    changes Configuration dictionaries, never these lists or nested settings.
    There is one demand model, fixed to Mbps by the field names; no assignment
    mode or unit switch needs to be selected. All installed APs normally stay on.
    """

    scenario_id: str
    description: str
    interval_hours: float
    users: list[User]
    access_points: list[AccessPoint]


@dataclass
class ServiceResult:
    """Assignments for exactly the devices requested by one service check.

    Each requested device appears either once in assignments or once in
    unserved_user_ids. No unrequested device appears. complete is true exactly
    when unserved_user_ids is empty; an empty requested set is complete.
    Assignment values name functioning reachable APs with enough capacity.
    """

    assignments: Assignment
    unserved_user_ids: list[str]
    complete: bool  # True only when every requested user has an assignment.


@dataclass
class FailureResult:
    """One independently simulated failure, keyed by AP ID in Evaluation.failures.

    unchanged is critical service at the original surviving settings; final is
    critical service after any recovery. configuration is the final copied plan,
    including the failed AP's original entry, which service/power checks ignore.
    recovery_attempted may be true even when no improvement was found.
    changed_ap_ids lists unique surviving APs whose final settings differ from
    the normal plan, rather than counting repeated changes to one AP.
    Both watt values exclude the same failed AP and use the same device demand
    model. They are not outage energy measurements or reconnection times.
    """

    unchanged: ServiceResult
    final: ServiceResult
    configuration: Configuration  # Copy; failed AP's entry is ignored.
    recovery_attempted: bool
    changed_ap_ids: list[str]
    surviving_watts_before: float
    surviving_watts_after: float  # Excludes failed AP; compare with before.


@dataclass
class Evaluation:
    """A normal plan checked under the explicitly recorded failure policy.

    normal requests all devices. normal_only leaves failures as None, and
    feasible means normal.complete. Other policies check every AP separately:
    feasible requires normal.complete and every failure's final.complete.
    fixed_settings never changes settings; recovery permits the agreed increases.
    These flags describe the checker outcome, not a proof of global optimality
    or a guarantee that a heuristic finds every possible recovery.
    """

    energy_wh: float  # Planned energy during normal operation.
    normal: ServiceResult
    failures: dict[str, FailureResult] | None  # None means not checked.
    failure_policy: FailurePolicy
    feasible: bool  # Meets the constraints requested for THIS evaluation.


@dataclass
class AnnealingSettings:
    """Explicit parameters for a reproducible simulated-annealing run.

    Temperatures use the Wh objective's numerical scale. The search validates
    Wh is the modeled energy consumed by the APs during the scenario's interval_hours. (wh = watts * hours). 
    The search uses the Wh objective to compare candidate configurations, and the annealing temperature is expressed in the same units.
    
    initial > minimum > 0, 0 < cooling_rate < 1, and max_steps > 0.
    One step is one proposed neighbor, including a rejected proposal.
    seed is passed to a local random.Random, not the global random generator.
    """

    initial_temperature_wh: float
    minimum_temperature_wh: float
    cooling_rate: float
    max_steps: int
    seed: int


@dataclass
class SearchResult:
    """A best-found plan and its evaluation, or an explained unsuccessful search.

    On success, configuration and evaluation are both present and correspond
    to each other. On failure both are None, with a useful message. steps counts
    examined candidate configurations (neighbor proposals for annealing).
    Missing output means the method did not find a plan, not proven impossibility.
    """

    configuration: Configuration | None
    evaluation: Evaluation | None
    steps: int
    message: str  # Explain a missing plan; do not claim global infeasibility.
