# Session report — November 16, 2026

## Milestone completed

Add simulated annealing as a separate failure-recovery method, compare it with
greedy from the same original plan, and connect the complete planning/failure
workflow to Streamlit. HMM, Markov, Monte Carlo, and RL ideas remain deferred.

## What changed

| Area | Implemented behavior |
| --- | --- |
| `planner/search.py` | Recovery annealing; unchanged reassignment first, checked high-power survivor seed, feasible one-AP proposals, probabilistic acceptance, best/current separation, repeatable seed, proposal/temperature history. Normal search also records history. |
| `planner/simulation.py` | Greedy recovery now records committed configurations and trial counts without changing the existing service rules. |
| `planner/models.py` | Shared `SearchStep`, recovery annealing controls, and `RecoverySearchResult`; optional trace/trial fields preserve existing constructors. Recovery temperatures are W, normal temperatures remain Wh. |
| `planner/scenarios.py` | Real JSON loading and validation, shared by files and uploads: fields, IDs, numbers, demands, capacities, settings, and coverage references. |
| `planner/experiments.py` | Timed normal/recovery comparisons, honest summaries, repeated normal-policy/seed runs, and CSV serialization/saving. |
| `planner/visuals.py` | Assignment maps, failed AP/critical/guest markers, objective traces, and comparison charts with incomplete recovery labeled. |
| `app.py` | Scenario/seed/search controls; normal plan selection; failed AP selection; recovery comparison; method inspection; AP loads/settings; replay and downloads; input/model explanation. |
| Examples | Larger shelter, a coordinated-change challenge, and an unreachable critical-device case, alongside the existing toy shelter. |
| Setup/docs | Tested direct dependencies pinned, Streamlit theme, revised README/test/research notes, and this report. |

Functions have explanatory docstrings, and the search loops explain copying,
feasibility checks, acceptance, temperature updates, and stopping. Algorithm code
stays in the planner modules rather than being hidden inside UI callbacks.

## How recovery works now

1. Start from a chosen normal configuration, remove one AP from service, and
   attempt reassignment of every critical device at unchanged survivor settings.
2. If complete, both recovery methods finish without unnecessary setting changes.
3. Otherwise greedy tries increases with a positive critical-service gain per
   added watt. It may stall when several changes are useful only together.
4. Recovery annealing checks an all-high survivor seed. If complete, search its
   feasible neighborhood for fewer surviving operating watts. A proposal changes
   one AP, and accepted higher-cost moves may help exploration. Keep the cheapest
   complete encountered plan separately from the current state.
5. Recheck the returned plan and report required service, surviving W, added W,
   changed APs, evaluated proposals, and elapsed solver time.

All functioning APs stay on; no AP is installed or awakened. The failed AP never
serves devices and its saved setting is unchanged. Recovery may reduce settings
from its high seed but never below each survivor's original normal watts.
Stationary devices reconnect through assignment changes; they do not move.

Normal energy remains Wh over the input interval. Recovery uses operating W,
because no outage duration has been agreed. Guests are not required after failure.

## What the user can inspect

The three tabs are Normal planning, Failure & recovery, and Inputs & model.
Normal results compare all-high, greedy, and annealing; a selected plan feeds
the failure tab. Every recovery method starts independently from that exact plan.
Changing inputs clears or marks old results rather than silently reusing them.

Maps show actual assignment lines and settings, a failed AP marker, critical
stars, and guest circles. Gray guests after failure are outside the critical-only
check; red required devices are unserved. No radio coverage circles are invented.

Recorded search histories show current cost, best feasible cost, candidate cost,
acceptance, feasibility, counts served/required, configuration, and temperature.
Replay displays the current configuration after each recorded decision, with a
fresh assignment check. Greedy histories contain committed changes; annealing
histories contain every proposal. Setup events use trial zero, including the
checked all-high recovery seed. Solver trial totals exclude setup/final checks.
This is replay after a run, not a live packet or outage-duration animation.

Comparisons, event tables, and scenario inputs can be downloaded. Recovery CSV
also records the original normal plan, scenario ID, and annealing controls.

## Evidence from this session

**71 automated tests passed** using the repository virtual environment on
Python 3.12.14: 27 simulation, 21 normal search, 10 recovery/comparison,
7 loader, and 6 real Streamlit widget tests. Test expectations include exhaustive
tiny-case checks, seeded reproducibility, failed outcomes, best/current separation,
unchanged/failed AP invariants, power bounds, and stale-result handling.

| Synthetic case | Checked result |
| --- | --- |
| Toy, greedy normal plan | 8 Wh over 1 hour versus 16 Wh all-high. |
| Toy, AP1 failed | Unchanged service is incomplete; both recovery methods restore 2/2 critical devices at 7 W surviving draw. |
| Combination challenge, F failed | Unchanged/greedy retain 1/2 critical devices at 2 W. Annealing returns A/B high, 2/2 critical devices at 4 W. |
| Unreachable critical device, AP1 failed | Neither method restores C1; the outcome is retained and shown as incomplete. |

Default demonstration controls: seed 441, 300 proposals, start temperature 5,
minimum 0.01, cooling 0.99. Temperature units follow each objective.

Live Playwright browser checks verified the normal-to-failure flow, greedy versus
annealing outcome selection, recovery CSV contents, replay from the initial
state to the final recorded state, valid JSON uploads, helpful rejection of
missing fields, and readable plots/maps. Matplotlib labels were enlarged and
aligned inward after visual inspection. A follow-up screenshot exposed collisions
in the larger shelter: map labels now use two lines and measured collision-aware
placement, with thin leader lines and unchanged scenario coordinates. All four
built-in normal maps rendered without overlapping label boxes; larger normal
and failure maps were checked in Streamlit, and all six UI tests passed again.
Browser evidence is saved in this chat's
workspace `outputs/`, not mixed into the project source tree.

The combination example's high recovery seed already serves both devices. It
demonstrates a useful recovery approach beyond positive-gain greedy, not proof
that stochastic search was needed to discover that particular combination or
that annealing always beats greedy.

## Limits that still matter

- Normal annealing uses the fast **greedy recovery checker** for the `recovery`
  constraint. Recovery annealing is compared separately on final plans. No
  annealing loop is nested inside another. Greedy screening can reject a plan
  recoverable by the separate method; the interface and research notes say so.
- Normal greedy enforces normal service only. Select the normal-only policy for
  a matched energy comparison; distinguish stronger-policy runs explicitly.
- Recovery annealing needs a complete high seed and only accepts complete
  candidates. A failed seed is not a proof of impossibility with arbitrary
  non-nested input settings, and feasible-only moves may not connect every plan.
- Greedy is incomplete, and finite annealing does not guarantee the optimum.
  An incomplete low-watt result cannot be ranked as a better complete recovery.
- Exact assignment can become expensive. The interactive limit of 8 APs and
  16 devices is a guardrail, not a guaranteed runtime bound.
- Built-in values are synthetic. Coverage sets are declared inputs; coordinates
  do not derive coverage. Capacity, electrical W, and coverage are independent.
  No real network, interference, reconnection-time, or hardware claim is made.
- `run_comparison()` currently batches normal policies/seeds with greedy recovery
  reports. Repeated recovery-annealing evaluation across all AP failures is not
  yet a batch feature. The UI compares either method for any selected single AP.
- Direct dependencies are pinned; this is not a full transitive lockfile.

## Run it and continue

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

For the clearest demonstration, choose Recovery combination challenge, run
planning, keep Greedy as the inspected normal plan, open Failure & recovery,
leave F selected, and compare. Then inspect both recovery methods and replay
the annealing history. Toy shelter shows a case where the methods agree;
Unreachable critical device shows that recovery is not always possible.

Next work, in order:

1. Team review of the app and algorithm explanations; agree on scenario inputs
   and parameter sources before treating results as research findings.
2. Add a small repeatable batch for both recovery methods over every single AP
   failure and multiple seeds, preserving incomplete runs and original plans.
3. Report complete critical service first, then W, additional W, changed APs,
   runtime, and variation across seeds. Separately compare normal energy under
   matched requirements. Include cases that favor neither method and that fail.
4. Measure assignment/search costs before increasing scenario size; improve
   pruning or limit input sizes if needed.
5. Prepare final plots, limitations, source credit, and the December 8 presentation.

Work remains local and uncommitted; no commit, push, or deployment was performed.
