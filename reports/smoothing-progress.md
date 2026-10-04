| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 35 | 69 → 69 |
| jre | 11 → 11 | 28 → 28 | 1421 → 1421 | 1770 → 1770 |
| jrw | 4 → 4 | 8 → 8 | 978 → 978 | 1209 → 1209 |

## B — linear costs and longer segments

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 36 | 69 → 51 |
| jre | 11 → 78 | 28 → 211 | 1421 → 1228 | 1770 → 1835 |
| jrw | 4 → 24 | 8 → 74 | 978 → 835 | 1209 → 1229 |

## C — smoothed references and key-only geography

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 35 | 69 → 44 |
| jre | 11 → 82 | 28 → 244 | 1421 → 1222 | 1770 → 1920 |
| jrw | 4 → 18 | 8 → 62 | 978 → 745 | 1209 → 1082 |

## D — key-node skeleton and corridor routing

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 1 | 69 → 7 |
| jre | 11 → 20 | 28 → 52 | 1421 → 65 | 1770 → 258 |
| jrw | 4 → 3 | 8 → 16 | 978 → 33 | 1209 → 122 |

## E — primary alignment, rotation moves and geographic/skeleton restarts

The same bounded smoke budgets were retained. One restart in this comparison
exercises the skeleton start; the separate longer run uses two restarts to
exercise both starting layouts. Refinement now targets hard failures first,
then residual zigzags, with configurable star-order and step-scale proposals.

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 2 | 69 → 13 |
| jre | 11 → 21 | 28 → 93 | 1421 → 77 | 1770 → 267 |
| jrw | 4 → 7 | 8 → 14 | 978 → 34 | 1209 → 123 |

## F — final line and geography diagnostics

Geometry is unchanged from E. Metrics were recomputed from saved routes and
the original graph; PNGs were copied unchanged. Baseline diagnostics were
backfilled using the same metric definitions. JSON and provenance are stored
under `output/comparisons/F/`.

| Fixture | Turns before → after | Mean run before → after | Axis error ° before → after | Spearman x before → after | Spearman y before → after |
|---|---:|---:|---:|---:|---:|
| jre | 1861 → 623 | 1.614 → 13.859 | 18.492 → 1.418 | 0.984 → 0.923 | 0.865 → 0.877 |
| jre_shinkansen | 69 → 15 | 2.320 → 10.462 | 36.527 → 2.758 | 0.952 → 0.998 | 0.991 → 1.000 |
| jrw | 1233 → 303 | 1.649 → 17.747 | 74.822 → 35.962 | 0.876 → 0.860 | 0.407 → 0.437 |
