# CS441_Final_Project

## Wi-Fi planning for temporary shelters

CS441 group project: keep every functioning installed access point (AP) on,
choose energy-efficient settings, and restore critical-device service after
one AP fails by reassignment first and setting changes only when needed.

This project is **under development**. The shared models and simulation layer
are implemented, including device assignment and greedy failure recovery.
The all-high reference, greedy baseline, and simulated annealing are implemented.
The production scenario loader, experiment runner, and plotting functions still
contain pseudocode and raise `NotImplementedError`. Streamlit
currently shows a landing page only. Synthetic correctness tests are available;
no full search experiments or measured network results have been generated.

## Working milestone: configuration search (November 6, 2026)

`planner/search.py` now chooses normal AP settings automatically:

- `all_high_configuration()` builds the reference and candidate starting plan.
- `greedy()` repeatedly chooses the largest single-AP energy reduction that
  preserves ALL normal-device service. Failure checks are separate for this baseline.
- `make_neighbor()` changes one AP to another available ON setting, preserving
  the original configuration. Both higher and lower moves are possible.
- `simulated_annealing()` searches under normal-only, fixed-settings, or recovery
  constraints. It uses a local random seed, records its best plan separately from
  its current plan, and counts/cools after rejected proposals too.

Run all 48 simulation/search tests from the repository root:

```powershell
python -m unittest discover -s tests -v
```

The 21 new search tests cover seeded reproducibility, infeasible starts, valid
neighbors, service constraints, uphill acceptance, preservation of the best plan,
and stopping after rejected moves. The existing 27 simulation tests still pass.
No third-party dependencies are needed to run this suite.

The following are observed SYNTHETIC toy results, not hardware measurements or
general performance claims. Annealing used seed 441, initial temperature 5 Wh,
minimum 0.01 Wh, cooling rate 0.99, and a 500-proposal budget. All APs stay on.

| Method/policy | Normal energy over 1 hour | Interpretation |
| --- | --- | --- |
| All-high reference | 16 Wh | All critical devices survive each failure at unchanged settings. |
| Greedy normal baseline | 8 Wh | All devices served normally; separate checks pass with recovery, fail with fixed settings. |
| Annealing, normal only | 8 Wh | Normal service checked during search. |
| Annealing, fixed settings | 12 Wh | Each failure passes without changing surviving settings. |
| Annealing, recovery | 8 Wh | Each failure passes after any needed greedy recovery. |

For this eight-configuration fixture, the seeded annealing results match an
enumerated minimum under each policy. This does not establish global optimality
on other inputs or show an advantage over greedy; both reach 8 Wh here.

The next milestone is connecting the loader and search results to the interface,
then comparing larger varied scenarios through `experiments.py`. Those modules
remain available for the other team members. HMMs and other temporal extensions
remain draft ideas outside the active implementation; see `docs/research.md`.

The discussion-post draft for this milestone is in
[`docs/discussion-update-2026-11-06.md`](docs/discussion-update-2026-11-06.md).

## Previous milestone: simulation (October 27, 2026)

`planner/simulation.py` now provides:

- `calculate_power()` and `calculate_energy()`: functioning-AP watts and normal Wh.
- `assign_users()`: backtracking with Minimum Remaining Values (MRV), coverage,
  unsplittable Mbps demands, capacity limits, and maximum-count partial service.
- `recover_service()`: unchanged reassignment first, then greedy setting increases
  scored by additional critical devices served per additional watt.
- `evaluate_configuration()`: normal-only, fixed-settings, or recovery checks,
  with every AP failure evaluated independently from the original configuration.

The simulation assumes a valid `Scenario`. It checks configuration keys/settings
and requested/failed IDs itself; complete scenario/JSON validation remains the
loader owner's task. Results use the existing `models.py` contract unchanged.

Run the correctness checks from the repository root with any supported Python:

```powershell
python -m unittest discover -s tests -v
```

These tests use only the standard library; Streamlit and Matplotlib are not
required. The test fixture reader constructs model objects from the toy JSON
without depending on the production loader stub. It is not a second app loader.

There are 27 tests, including 40 tiny seeded cases checked against exhaustive
assignment enumeration. The toy all-low plan serves all four devices normally
using 8 W (8 Wh over its one-hour interval). After AP1 fails, raising AP2 to high
restores both critical devices; surviving draw goes from 5 to 7 W. After AP3
fails, unchanged reassignment already serves both critical devices.

Backtracking is intended for small cases and may become expensive as inputs
grow. Greedy recovery is not complete: it can miss a valid combination when
neither setting increase improves service alone. A regression test documents
this limitation. Recovery failure is a method outcome, not proof of impossibility.

The search functions described in the November 6 milestone now use this
simulation to evaluate each candidate configuration.

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
        test_simulation.py    # Standard-library simulation correctness checks
        test_search.py        # Search feasibility, randomness, and stopping checks
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
Scenario validation belongs in the unfinished `scenarios.py`; dataclass type annotations
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

`recover_service()` is implemented in `simulation.py`, next to the shared assignment
checker. It first tries critical-device reassignment without setting changes.
If needed, greedy recovery chooses positive service gains per
additional operating watt, using higher settings on surviving APs only.
This is a heuristic, not an exact or complete recovery solver.

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
