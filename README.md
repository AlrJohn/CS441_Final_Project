# CS441 Final Project

## Wi-Fi planning for temporary shelters

Keep every functioning installed access point (AP) on, choose energy-efficient
normal settings, and restore critical-device service after one AP fails.
This is a small Python simulation using search, not a controller for real Wi-Fi
equipment. Built-in inputs are explicitly synthetic.

**Current milestone — November 16, 2026:** normal planning, greedy and simulated
annealing recovery, JSON loading/validation, comparisons, plots, and the Streamlit
workflow are connected. No core module remains a pseudocode stub. The next stage
is broader evaluation and refinement, not adding HMM/RL features.

See [the session report](docs/session-report-2026-11-16.md) for implementation
details, checked outcomes, limitations, and next steps.

## Run the application

Use Python 3.11 or newer; this milestone was tested on **Python 3.12.14**. From
the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If `.venv` already exists, skip the first command. No activation is required.
Open the local URL printed by Streamlit, usually
[http://localhost:8501](http://localhost:8501). Direct UI/plot dependencies are
pinned in `requirements.txt`; algorithms use the standard library.

1. Choose a scenario or upload matching JSON. **Inputs & model** shows demands,
   settings, declared coverage, and assumptions.
2. Under **Normal planning**, run all-high, greedy, and simulated annealing.
   Select a normal plan to inspect its assignments/settings.
3. Under **Failure & recovery**, select one failed AP and run the comparison.
   Unchanged reassignment, greedy recovery, and annealing recovery all receive
   the same original normal plan.
4. Inspect an outcome's service, assignment map, and settings. Expand search
   steps to see current/best costs, accepted/rejected proposals, and replay
   recorded states. Download comparisons or traces as CSV.

Search runs on button clicks. Changed inputs mark results stale or clear them.
Replay shows recorded states after decisions, not packet traffic or reconnection
timing. Greedy records committed changes; annealing records every proposal.

## Current model and scope

- AP locations are fixed. Every functioning installed AP stays ON, including
  APs that happen to have no device assigned. No standby/off state is allowed.
- Every stationary device must be served normally. Each has positive
  `demand_mbps`, an independent critical flag, and one AP assignment. Its demand
  cannot be split across APs.
- Each named AP setting supplies electrical watts, usable `capacity_mbps`, and
  `covered_user_ids`. Assigned demand must fit within capacity.
- After one AP fails, try critical-device reassignment at unchanged surviving
  settings first. Devices do not physically move.
- If needed, search surviving settings at or above each AP's original electrical
  draw. Annealing may lower settings from its high recovery seed, but never below
  the original watts. The failed AP stays unavailable and unchanged.
- Guests may lose service after failure. Each failed AP is tested independently
  from the original normal configuration.
- A brief interruption is acceptable. Detection/reconnection timing, interference,
  packet behavior, and upstream capacity are outside this model. Assume upstream works.

Coordinates are for plotting, not radio propagation. Coverage, capacity, and
electrical draw are separate inputs; watts do not automatically increase capacity
or calculate a coverage radius. Mbps models usable shared capacity, not measured
traffic or advertised radio rates. Electrical W is different from transmit dBm.

This replaces the early unchanged-settings-only restriction, which remains a
comparison policy. HMM, Markov, Monte Carlo, and RL ideas remain draft only.

## Algorithms and fair comparisons

`assign_users()` uses small-instance backtracking with Minimum Remaining Values
(MRV), handles coverage/capacity, and returns a maximum-count partial assignment
when complete service is impossible. This exact checker can become expensive.
The UI limits inputs to 8 APs/16 devices, a guardrail rather than a speed guarantee.

Normal planning minimizes **Wh over the scenario's interval**:

- All-high supplies a checked reference and candidate start.
- Greedy takes the largest single-AP energy reduction preserving every normal
  device. It is a `normal_only` baseline.
- Annealing changes one AP at a time, sometimes accepts higher-energy feasible
  plans, and keeps its best separately. It supports `normal_only`, `fixed_settings`,
  and `recovery`; the checked policy appears beside each result.

Choose **Normal service only** for an energy comparison under equal requirements.
Stronger-policy runs impose extra checks; energy differences do not automatically
show that one algorithm is better.

Recovery compares **surviving operating W**, with no assumed outage duration:

- Unchanged: reassignment only.
- Greedy: increases settings by positive critical-device gain per added watt,
  stopping when complete or when no improving single change remains.
- Annealing: tries unchanged reassignment, verifies an all-high survivor seed,
  then searches complete recovery configurations for fewer watts.

Normal annealing's `recovery` screen still uses **greedy recovery**. Recovery
annealing runs separately on the selected final normal plan, not inside another
annealing loop. A plan rejected by the greedy screen could be recoverable by
another method. The UI states this distinction.

Neither heuristic guarantees a global optimum. A failed all-high seed is not
proof of impossibility for arbitrary non-nested settings. Incomplete low-watt
recovery is not a better solution: partial bars and unserved devices are labeled.

## Examples and checked outcomes

All values are synthetic correctness examples, not hardware measurements.
Default UI annealing uses seed 441, 300 proposals, starting temperature 5,
minimum 0.01, cooling 0.99 (Wh normally, W for recovery).

| Input | Checked behavior |
| --- | --- |
| `toy_shelter.json` | 3 APs/4 devices. Greedy normal plan uses 8 Wh over 1 hour versus 16 Wh all-high. After AP1 fails, greedy and annealing restore 2/2 critical devices at 7 W. |
| `larger_shelter.json` | 5 APs/10 devices for broader assignment and failure exploration. |
| `recovery_challenge.json` | All-low normal plan, F failed: unchanged/greedy serve 1/2 critical devices at 2 W; annealing returns 2/2 at 4 W. Two changes are needed together. The all-high recovery seed already serves both. |
| `unreachable_critical.json` | AP1 failure leaves C1 unreachable. Both methods retain an incomplete outcome. |

These demonstrate behavior, not general annealing superiority. Tests also
compare normal annealing with exhaustive enumeration on the eight-configuration
toy fixture; that proves a minimum for that fixture only.

## Project structure and ownership

```text
CS441_Final_Project/
    app.py                    # Streamlit controls and workflow
    requirements.txt          # Tested direct dependencies
    .streamlit/config.toml    # Theme; no secrets
    planner/
        models.py             # Shared inputs, results, search events
        scenarios.py          # JSON loading and validation
        simulation.py         # Assignments, W/Wh, failures, greedy recovery
        search.py             # Normal searches and recovery annealing
        experiments.py        # Comparisons, repeated normal runs, CSV
        visuals.py            # Assignment maps, traces, comparison plots
    data/                     # Four synthetic JSON examples
    docs/                     # Research, milestone reports, discussion draft
    tests/                    # Core, loader, comparison, UI checks
    results/                  # Ignored generated experiment files
```

Related functions stay together; no database, separate frontend, or API is needed.
Existing dataclass constructors remain compatible through optional trace fields.

| Owner | Remaining focus |
| --- | --- |
| Jonathan | Explain/review assignment and search algorithms, objectives, and limits; maintain the shared models and review algorithm changes. |
| Teammate 1 | Expand documented scenarios, justify parameter sources, and run repeated comparisons across seeds and AP failures. |
| Teammate 2 | Refine maps, replay, UI wording, and presentation visuals; test the workflow with teammates' scenarios. |

The loader, comparisons, plots, and UI now have implementations to build on.
Coordinate branches/reviews and shared model changes. Everyone contributes
interpretation and the final presentation.

## Tests and remaining evaluation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**71 tests pass:** 27 simulation, 21 normal-search, 10 recovery/comparison,
7 loader, and 6 Streamlit interaction tests. UI tests skip without Streamlit;
core tests use the standard library. See [test notes](tests/README.md).

`compare_planning()` and `compare_recovery()` produce real comparisons and CSV.
`run_comparison()` repeats normal annealing across supplied seeds/policies and
reports greedy recovery outside solver timing. It does not yet batch recovery
annealing across every seed and failed AP.

Next: agree on varied scenarios; compare both recovery methods over every single
AP failure and repeated seeds; document runtime/quality tradeoffs; check scaling;
and prepare the final report/presentation. A full research evaluation is not done.

## Research credit and milestones

The simulation milestone was October 27 and normal configuration search was
November 6. The earlier [discussion draft](docs/discussion-update-2026-11-06.md)
records that stage; [the November 16 report](docs/session-report-2026-11-16.md)
records this update.

Chin (2011) provides related energy-aware WLAN scheduling; our all-on downgrade
and recovery heuristics do not reproduce its activation algorithm. Annealing
uses Kirkpatrick et al. (1983). [Research notes](docs/research.md) contain the
source-to-code mapping, related capacity/association work, and APA references.
No published implementation was copied. Explain the project-specific adaptation
without claiming first-ever novelty in fault-tolerant networking.
