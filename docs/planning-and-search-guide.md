# Understanding planning, recovery, and the search graphs

The normal planning page chooses AP settings before any AP fails. A service
requirement is a rule a proposed plan must pass. A setting such as low or high
is the actual operating choice for an AP. These are different things.

## The current two-stage workflow

Normal planning serves every device and compares energy before any AP fails.
Failure & recovery takes the selected normal plan, fails one AP, and compares
how critical devices receive service again. Failure checks happen on that second
tab, without filtering the normal candidates in advance.

| Method | What normal planning does |
| --- | --- |
| All-high reference | Put every AP at its highest setting and check normal service. This reference does not search. |
| Greedy | Try lower-power settings, keeping every device served normally. |
| Simulated annealing | Search for lower normal energy while keeping every device served normally. |

Normal service means each device has one reachable AP with room for its entire
Mbps demand. All three methods now use the same requirement. The old planning
requirement dropdown and policy columns were removed because normal planning
always uses `normal_only` in the app.

## Recovery on the second tab

Select a failed AP and compare unchanged reassignment, greedy recovery, and
recovery annealing. Each method starts independently from the same normal plan.
Devices stay in their original positions. Critical devices are required after
failure, while guests may lose service.

Both recovery methods try unchanged reassignment first. Greedy recovery then
chooses useful setting increases. Recovery annealing, if needed, verifies an
all-high survivor seed and searches for a lower-power complete recovery. Neither
switches off a functioning AP or reduces a survivor below its original normal
operating watts. Recovery start temperature is available under Recovery search
settings on the second tab; changing it does not invalidate normal planning.

The former planning dropdown added hypothetical failure checks before accepting
a normal plan. The agreed app workflow no longer includes that look-ahead step.
Those explicit policies remain in the Python API for separate experiments.

## What AP setting changes tested means

One tested change is one candidate AP setting configuration evaluated by a
search. For example, starting from all high, try AP1 at low and check service
and energy. Testing a setting does not mean applying it to the selected plan.
Rejected candidates still count as work done. This count is neither elapsed
time nor the number of devices reconnected or AP failures simulated.

The x-axis counts those tests. The normal y-axis is energy in Wh over the
scenario interval; the recovery y-axis is surviving AP power in W.

Greedy tests several changes before selecting the best useful one. Its graph
marks saved selections and holds the selected plan constant between them.
The old phrase committed-change checkpoints meant those selected plans.
For Toy shelter, the actual normal greedy history is:

| Changes tested so far | Selected normal plan energy |
| --- | --- |
| 0 | 16 Wh |
| 3 | 12 Wh |
| 5 | 10 Wh |
| 6 | 8 Wh |

This means six changes tested, three changes selected. The replay slider visits
four saved states, including the initial state, so its index is not the same
as the x-axis test count.

Annealing records the current plan after every candidate test. Current plan is
what the search holds at that moment. Best plan found is the lowest cost among
plans that passed the requirement. A rejected change appears as a cross at its
candidate cost. The current plan stays the same when a proposal is rejected.
Initial setup, including a checked recovery seed, uses test count zero.

## Toy results you can explain

At seed 441 and 300 annealing tests, the toy normal plans use 16 Wh all-high,
8 Wh greedy, and 8 Wh annealing. All three checks require normal service only.
After AP1 fails, the all-low normal plan needs recovery: greedy and annealing
both restore the two critical devices at 7 W surviving AP power.

A valid normal plan may still have an unrecoverable failure. The unreachable
critical-device scenario demonstrates this: normal planning succeeds, then the
second tab reports that C1 cannot receive service after AP1 fails.

These examples use invented inputs. Normal energy, recovery watts, and the
number of candidate tests describe different parts of the application.
