# Research ideas and our implementation

The files contain original project-specific implementations, not copied
published source code. Simulation, normal configuration search, recovery
annealing, JSON loading/validation, comparisons, plots, and the Streamlit
workflow are implemented as of November 16, 2026. The examples are synthetic;
they establish correctness cases, not measured networking performance.

| Source | Where it helps | What we are doing differently |
| --- | --- | --- |
| Chin (2011) | Related energy-aware WLAN scheduling and coverage/cost reasoning | Keep all installed APs on; our normal greedy downgrades and failure-recovery heuristic are not its activation algorithm. |
| Kirkpatrick et al. (1983) | `search.py`: annealing's temperature and probabilistic acceptance | Search all-on power settings and check normal service plus the selected failure/recovery policy. |
| Guo and Huang (2009) | `simulation.py`: coverage and capacity both constrain association | Keep AP sites fixed. The initial checker uses small-instance backtracking rather than reproducing the relay-placement/matching implementation. |
| Garroppo et al. (2021) | Shared activation, power, energy, and user-association model | Build a simpler simulation and heuristic search, not their exact optimization method. |

Chin's scheduler selects reachable-user sets using a coverage/cost ratio and a
group restriction on AP settings. Its AP activation behavior differs from our
current scope. Our normal baseline starts all-high and greedily lowers settings
while preserving normal service. Our separate recovery heuristic first tries
unchanged reassignment, then selects higher surviving settings by critical-user
gain per additional watt. These project-specific heuristics need evaluation;
do not label them reproductions of Chin's Algorithm 1.

The proposed project extension is an explicit check that **every critical user
can receive service after each individual AP fails**, first with reassociation
and then, if needed, higher settings on surviving APs. Every functioning AP stays
on; no standby activation is included. Compare fixed-settings and recovery
policies for normal energy, critical service, recovery watts, and changed APs.
Recovery delays are outside scope; do not claim uninterrupted service.
Describe this as our extension of the
selected baseline, not as proof of first-ever novelty in fault-tolerant networking.

If settings have nested coverage and nondecreasing capacity, unconstrained
eventual recovery can depend only on maximum installed capability. Explain this
when interpreting results: a lower normal-energy plan may simply need more
post-failure setting changes. The greedy recovery method can also miss feasible
combinations; distinguish a heuristic failure from proven impossibility.

## Recovery comparison implemented November 16, 2026

`simulated_annealing_recovery()` tries unchanged reassignment first. If that
fails, it checks a seed with every surviving AP at its highest setting, then
searches for a lower-watt complete recovery. Each proposal changes one surviving
AP; it can step down from the high seed but cannot go below that AP's original
normal operating watts. Feasibility is a hard constraint. Temperature controls
acceptance of extra watts, and current and best configurations remain separate.
There is no standby activation, failed-AP repair, or device movement.

The unchanged, greedy, and annealing recovery methods receive the same original
normal configuration and failed AP. Report complete critical service before
comparing surviving watts, additional watts, changed APs, trials, and runtime.
Normal planning minimizes Wh over the input interval. Recovery minimizes W;
an outage duration has not been introduced. Greedy may stop at its first complete
recovery; annealing may spend more trials looking for a cheaper complete plan.
Neither is guaranteed to find an optimal result.

The combination challenge demonstrates a limitation of positive-gain greedy:
two setting changes together restore service although neither helps alone.
Annealing's checked all-high seed already restores service in this example;
the result demonstrates the complete recovery workflow, not that stochastic
search was needed to discover this particular combination. A failed all-high
seed is also not a proof of impossibility for arbitrary non-nested settings.

As of November 18, the app separates normal planning from failure recovery.
Every normal method checks only normal service. The second tab fails a selected
AP and compares unchanged reassignment, greedy recovery, and annealing recovery.
The app does not screen normal candidates against hypothetical future failures.

The Python API retains explicit `fixed_settings` and `recovery` policies for
separate experiments. The latter uses greedy recovery screening, so those
experimental policies should be described separately from the app workflow.
Repeated-seed and varied-scenario evaluation is still needed.

When writing the report, keep the model limitations explicit: synthetic inputs,
assumed working upstream connection, fixed AP sites, and no packet-level or
interference guarantees. The toy correctness results are synthetic, not measured
network findings or a general comparison of algorithm performance.

## Deferred ideas (draft only, November 6, 2026)

Possible later extensions are AP-health estimation with an HMM, Markov demand
forecasting, Monte Carlo stress evaluation, and an MDP/reward-based controller.
They remain exploratory notes from the November 1 discussion and are outside
the active scope. No associated model fields, dependencies, or algorithms have
been added. Finish and evaluate the existing all-on search/recovery application
before considering any of these extensions.

## APA references and primary links

Chin, K.-W. (2011). A green scheduler for enterprise WLANs. In *2011 Australasian
Telecommunication Networks and Applications Conference (ATNAC)* (pp. 1–3).
IEEE. https://doi.org/10.1109/ATNAC.2011.6096630

[Author-hosted paper](https://documents.uow.edu.au/~kwanwu/greenAP-atnac2011.pdf),
particularly Section IV and Algorithm 1.

Garroppo, R. G., Nencioni, G., Tavanti, L., Gendron, B., & Scutellà, M. G.
(2021). Optimal access point power management for green IEEE 802.11 networks.
*Sensors, 21*(6), Article 2076. https://doi.org/10.3390/s21062076

[Publisher article](https://www.mdpi.com/1424-8220/21/6/2076).

Guo, W., & Huang, X. (2009). On coverage and capacity for disaster area wireless
networks using mobile relays. *EURASIP Journal on Wireless Communications and
Networking, 2009*, Article 251314. https://doi.org/10.1155/2009/251314

[Primary full text](https://link.springer.com/article/10.1155/2009/251314),
especially Sections 4 and 5.1 for per-user association and capacity limits.

Kirkpatrick, S., Gelatt, C. D., Jr., & Vecchi, M. P. (1983). Optimization by
simulated annealing. *Science, 220*(4598), 671–680.
https://doi.org/10.1126/science.220.4598.671

[IBM publication record](https://research.ibm.com/publications/optimization-by-simulated-annealing).
