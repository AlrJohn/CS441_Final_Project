# Research ideas and our implementation

The files contain original project-specific pseudocode, not published source
code. 

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

When writing the report, keep the model limitations explicit: synthetic inputs,
assumed working upstream connection, fixed AP sites, and no packet-level or
interference guarantees. This scaffold supplies no empirical findings.

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
