# CS441_Final_Project

## Wi-Fi planning for temporary shelters

CS441 group project: keep every functioning installed access point (AP) on,
choose energy-efficient settings, and restore critical-device service after
one AP fails by reassignment first and setting changes only when needed.

This is a **coding scaffold**, not a completed planner. The data containers and
the Streamlit landing page are provided. Algorithm functions contain descriptive
pseudocode and raise `NotImplementedError` until you write them. No results have
been generated.

## Project structure

```text
CS441_Final_Project/
    app.py                    # Streamlit entry point
    requirements.txt          # Interface and plotting dependencies
    planner/
        __init__.py
        models.py             # Shared data structures
        scenarios.py          # Read and validate scenario files
        simulation.py         # Coverage, assignment, failures, and energy
        search.py             # Greedy baseline and simulated annealing
        experiments.py        # Repeated comparisons and CSV output
        visuals.py            # Shelter map and comparison plots
    data/
        toy_shelter.json       # Small, explicitly synthetic example
    docs/
        research.md           # Sources and our proposed adaptations
    tests/
        README.md             # Hand-checkable cases to implement later
    results/
        .gitkeep              # Generated experiment files go here
```

Related functions stay together. We do not need one file per algorithm, user,
access point, or graph. There is no database, separate frontend, or web API.

| File | What you will implement |
| --- | --- |
| `models.py` | Review the common data contract. Add fields only when the model needs them. |
| `scenarios.py` | Convert JSON into those data objects and reject inconsistent inputs. |
| `simulation.py` | Decide who can receive service, check each failure, and calculate energy. |
| `search.py` | Write the greedy method, a neighbor generator, and simulated annealing. |
| `experiments.py` | Compare methods fairly, repeat seeds, and save actual measurements. |
| `visuals.py` | Plot APs, users, assignments, and measured comparisons. |
| `app.py` | Connect the modules to scenario controls and a failure selector. |

## Current scope (updated October 19, 2026)

- AP locations are fixed, and all functioning installed APs stay ON.
- Search changes named operating settings only. No off state or standby backups.
- Every modeled user must receive service normally.
- After **any one AP fails**, first try reassigning critical devices at unchanged
  surviving settings. Devices stay in place; the failed AP remains unavailable.
- If needed, search higher available settings on surviving APs to restore all
  critical service. No new AP is installed or activated after the failure.
- A brief disconnection is acceptable. We test eventual service feasibility,
  not detection, reconnection times, or uninterrupted operation.
- Noncritical users may lose service after a failure if needed for critical users.
- Assume a working upstream connection. This version simulates local service.

This replaces the proposal's earlier unchanged-settings-only restriction.
That old policy remains only as an experimental comparison. All APs being on
does not add a requirement that every AP have a device assigned at every moment.
The input describes installed equipment, not extra candidate APs to deploy.

The application uses search, which satisfies the assignment's AI-method category.
NLP and an HMM are not needed for this proposed project. The final submission
will also need a working application, evaluation, and properly cited research.

## Shared data contract

An AP has named settings, such as `low` and `high`. Each setting supplies a
`capacity_mbps`, an electrical draw in watts, and a list of devices it can reach. A
configuration is a small dictionary:

```python
configuration = {"AP1": "low", "AP2": "high", "AP3": "low"}
# Exactly one ON setting per installed AP. None/off is invalid.
```

`covered_user_ids` is an input to the first scaffold. This avoids quietly choosing
a radio propagation model. Later, you can generate these sets from an agreed
coverage model. Coordinates are for plotting until that rule is chosen.

**The demand model is settled:** each `User` represents one stationary client
device with a positive `demand_mbps`. One AP must reach it and have room for its
entire demand. The sum of assigned demands must fit within that setting's
`capacity_mbps`. Criticality and demand are independent. `User` and `user_id`
remain the code names for consistency, even though we mean devices.

Mbps means megabits per second. We model usable shared capacity, not advertised
radio signaling rates or measured instantaneous traffic. A single combined
traffic budget is used; separate upload/download constraints are outside this
version. There is no unit or assignment-mode switch to configure.

The toy example uses demands of 3, 2, 1, and 1 Mbps, with 5 Mbps capacity per AP.
These are deliberately invented examples, not researched application needs.
Capacity stays constant across low/high in this example; only declared coverage
and electrical draw change. A future scenario may supply other justified values.

The toy values are invented for hand checking, not taken from hardware or a
paper. Real parameter sources, scenario sizes, and annealing settings remain to
be chosen. In particular, electrical watts are different from transmit dBm.
Coverage, capacity, and electrical draw are separate setting inputs. Do not
assume raising transmit power automatically raises capacity. Energy savings
depend on the modeled electrical draws actually differing across settings.

`models.py` is the shared starting contract, not an algorithm file. Its classes
document normal service, before/after recovery results, energy, and search output.
Scenario validation is implemented in `scenarios.py`; dataclass type annotations
do not validate input values at runtime. Algorithms must preserve the documented
result invariants and use copies instead of changing shared inputs.

## Team ownership and handoffs

| Owner | Implementation | Checks and handoff |
| --- | --- | --- |
| Jonathan | `simulation.py`, `search.py`; maintain `models.py` | Assignment/backtracking, energy, independent failures, recovery, greedy, annealing; test tiny cases before handing results to UI/experiments. |
| Teammate 1 | `scenarios.py`, `data/`, `experiments.py` | Loader/validation, documented scenario inputs, repeatable comparisons and CSV; use the exact dataclasses in `models.py`. |
| Teammate 2 | `visuals.py`, `app.py` | Maps and before/after service displays, charts and Streamlit integration; use documented sample result objects while the algorithms are unfinished. |

Each owner tests their own features and records sources for borrowed ideas.
Everyone contributes to interpretation and the final presentation. Keep example
objects clearly labeled; they are not measured experiment results.

Everyone imports from `models.py`; they do not need separate versions of it.
Jonathan reviews proposed changes to field names/types or function signatures
before merging, then updates all callers together. The contract can change if
implementation uncovers a real need, but it is ready for parallel development.
Agree on the schema now; use separate branches and pull requests for feature work.

## Recovery and what we measure

`recover_service()` lives in `simulation.py`, next to the shared assignment
checker. It first tries critical-device reassignment without setting changes.
If needed, the proposed greedy recovery chooses positive service gains per
additional operating watt, using higher settings on surviving APs only.
This is a suggested heuristic, not an exact or complete recovery solver.

Each single failure starts from the original normal plan. Recovery returns
the unchanged and final service results, changed APs, and surviving watts
before/after. Keep the failed AP's dictionary entry but exclude it from service
and surviving-power calculations. Do not mutate the normal configuration.

Optimize normal-operation Wh over a common interval. Report recovery watts and
configuration changes separately; outage duration and failure probability have
not been specified. Do not claim a minimum combined normal-plus-failure energy.

When every maximum setting contains all lower coverage/capacity options,
allowing unrestricted increases can make eventual recovery feasibility depend
on the installed hardware's maximum capability rather than the starting plan.
That is acceptable for this scope: compare normal energy, unchanged service,
and the recovery actions needed. It is not evidence of uninterrupted protection
or a novel resilience constraint. Include cases that still fail at maximum.

## Suggested coding order

1. Review the finalized Mbps fields and result contracts in `models.py` together.
2. Implement `load_scenario()` and `validate_scenario()`.
3. In `simulation.py`, write the energy calculation and user-assignment checker.
   Work through the small cases in `tests/README.md` before adding search.
4. Add unchanged failure checks, then greedy recovery and independent evaluation.
5. Implement `all_high_configuration()` and the greedy setting-reduction baseline.
6. Implement `make_neighbor()`, then `simulated_annealing()`. Start from a checked
   feasible configuration; keep the current plan separate from the best plan.
7. Add repeated experiments and plots, then connect them to Streamlit.

The assignment checker matters: an unlucky first assignment must not make a
serviceable configuration look impossible. The suggested starting checker uses
backtracking, with the most constrained user considered first. It can be slow on
large instances, so validate small cases and measure its cost before scaling up.

## Run the starter page

Use Python 3.11 or newer. From this project folder in PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

These commands do not require activating the environment. The starter page only
explains the project; no search button or fabricated result is wired up. If your
Python launcher does not provide 3.12, use an installed supported Python version.
The core modules use the standard library. After the team's first successful
setup, agree on dependency versions before running the final experiments.

Installation reference: [Streamlit's official instructions](https://docs.streamlit.io/get-started/installation/command-line).

## Research and comparisons

Chin (2011) supplies related energy-aware WLAN work; our all-on downgrade and
recovery rules do not reproduce its activation algorithm. Simulated annealing
follows the general method associated with Kirkpatrick et al. (1983).
See [research notes and APA references](docs/research.md)
for the source-to-code mapping and the proposed difference from prior work.

Compare an all-high reference, normal-service greedy, and annealing using
normal-only, fixed-settings, and recovery policies. The latter is our selected
behavior; fixed-settings is a comparison. Recheck every returned plan under
recovery for reporting, including unchanged service before changes.
Preserve infeasible outcomes and search failures in the results.
A search that finds no plan has not proved that
no plan exists.
