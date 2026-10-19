# Checks to implement as you write the code

Algorithms are still stubs. Turn these cases into standard-library `unittest`
tests as you implement them. Check assignments, capacities, copies, and watts,
not just status strings. There is no off state in the current project.

The synthetic toy example uses `demand_mbps` values 3, 2, 1, and 1 for C1, C2,
U1, and U2. Every AP has 5 Mbps modeled usable capacity at either setting.
These are invented values, not measured throughput or application requirements.
AP3 low now reaches guest devices U1/U2 only; this deliberately exercises recovery.

| Normal configuration | Normal service | Critical service after each failure, unchanged | Recovery | Normal Wh, 1 hour |
| --- | --- | --- | --- | --- |
| All low | All 4 served | AP1/AP2 failures each leave one critical device unserved; AP3 failure passes | AP1 failure: raise AP2 to high; AP2 failure: raise AP1 to high; AP3 failure: no change | 8 |
| AP1 high, AP2/AP3 low | All 4 served | AP1 failure fails; AP2/AP3 failures pass | AP1 failure: raise AP2 to high | 10 |
| AP1/AP2 high, AP3 low | All 4 served | All three separate failures pass | No changes needed | 12 |
| All high | All 4 served | All three separate failures pass | No changes needed | 16 |

For all-low with AP1 failed, surviving draw is 5 W before recovery and 7 W after:
AP2 changes from 3 to 5 W; AP3 stays at 2 W. The additional recovery draw is 2 W.
It is not 2 Wh unless an outage duration of 1 hour is explicitly introduced.
The 8 Wh normal value includes AP1; do not compare it directly with surviving
power to infer the cost of recovery. None/off entries must be rejected.

Additional cases:

1. **Reassignment first:** X reaches AP A/B and Y only A; each demands 1 Mbps,
   and each AP has 1 Mbps capacity.
   Find X→B and Y→A without changing settings. First-fit can miss this solution.
2. **Coverage without capacity:** Two 1 Mbps devices reach a 1 Mbps AP;
   only one can be served. More reach alone does not imply enough capacity.
3. **Critical priority:** After a failure, request all critical devices, allowing
   guests to lose service. One device's entire demand must fit on one AP.
4. **Recovery rules:** No failed-AP assignments or setting changes; no AP off
   state, device movement, or changes outside the supplied levels. Preserve input.
5. **Independent failures:** Start each failure from the normal plan, not the
   previous recovery plan. AP1 and AP2 are not removed cumulatively.
6. **No recovery possible:** Remove C1 from every AP2/AP3 coverage set; AP1's
   failure cannot serve C1 even at maximum settings. Return honest partial results.
7. **Greedy limitation:** X/Y each need 1 Mbps. A 1 Mbps AP A reaches X at low
   and X/Y at high;
   AP B reaches nobody at low and X at high. Initially only X is served. Raising
   either AP alone still serves only one; raising both serves X/Y. Positive-gain
   greedy stalls here even though a combination works. Do not claim impossibility.
8. **Annealing bookkeeping:** Worse accepted current must not overwrite best;
   neighbors must not mutate input or offer off. Count/cool on rejected trials.
9. **No alternative levels:** With one setting per AP, return the checked start
   instead of crashing or looping while trying to generate a neighbor.
10. **Honest search failures:** Invalid starts return an explanation, not an
    invented plan or proof that the entire scenario is impossible.

11. **Unsplittable demand:** A 3 Mbps device reaches two 2 Mbps APs. It cannot
    receive service by splitting its demand, despite 4 Mbps combined capacity.
12. **Fractional Mbps:** A 0.1 and a 0.2 Mbps device both fit a 0.3 Mbps AP using
    a small consistent comparison tolerance; do not truncate or round demands.
13. **Criticality is independent:** A 1 Mbps critical device keeps failure priority
    over a 3 Mbps guest. Demand size alone never determines criticality.

Independently enumerate tiny assignment/configuration spaces to validate the
implementation before trusting larger experiments. Type annotations alone do
not reject bad JSON; cover malformed inputs in the scenario-loader tests.
