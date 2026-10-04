# How the layout algorithm works

The engine groups stations into chains between terminals, junctions and
interchanges. It simplifies and smooths each geographic chain, then searches
for a rotation and vertical stretch that favor compass directions. A PCA
candidate aligns the primary line with the vertical axis.

The default layout starts with a skeleton containing only key stations.
Each skeleton chain receives a short octilinear route. Simulated annealing
moves keys, chains and branches, balancing crossings, line turns, zigzags,
short straight runs and geographic direction. Seeded restarts alternate
skeleton and geographic starts.

Through stations are placed at equal arc-length intervals on the skeleton
routes. Local refinement reroutes incident edges and moves stations to repair
spacing, clearance, ports and circular neighbor order, then reduce zigzags.
The optimizer retains states by hard violation count, crossings, zigzags and
weighted energy, in that order. Annealing acceptance uses weighted energy.

Finally, the engine packs components, orders bundled lines, places labels and
exports the layout with metrics and a violation report. All seven hard
constraints are checked on the final graph. The search is heuristic; a result
is feasible only when that report contains zero hard violations.

See [CONSTRAINTS.md](CONSTRAINTS.md) for exact formulas and
[default.yaml](schematic_map/config/default.yaml) for parameters. Set
`init.mode: geo` to use the flat geographic initialization.
