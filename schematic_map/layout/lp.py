"""Constraint-graph layout solved as one LP, ported from TRA_Visualization's schematic_layout.py.

Only relative relations are used, never geographic distances:
1. Key nodes (degree != 2) split the graph into chains of through stations.
2. Port assignment: each key node gives its chains distinct octilinear directions that keep
   their geographic circular order, choosing the cheapest of all order-preserving assignments.
3. A chain's shape follows from its two ports: straight, L-shaped, or a three-piece U.
4. Shape constraints (horizontal/vertical/diagonal pieces, chain length >= station count) and
   left/right/above/below constraints between geographically near key nodes form an LP that
   minimizes total length.
5. Crossing or too-close pieces get separation constraints from their geographic sides; re-solve.
Stations are then spaced evenly along each chain's polyline.
"""
import math
from collections import defaultdict
from itertools import combinations
import numpy as np

DV = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def seg_dist(p1, p2, q1, q2):
    """Shortest distance between two segments (0 when they cross)."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def pt_seg(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)

    d1, d2 = cross(q1, q2, p1), cross(q1, q2, p2)
    d3, d4 = cross(p1, p2, q1), cross(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0
    return min(pt_seg(p1, q1, q2), pt_seg(p2, q1, q2), pt_seg(q1, p1, p2), pt_seg(q2, p1, p2))


def overlap_len(p, q, a, b):
    """Overlap length of two collinear segments (0 when not collinear)."""
    ux, uy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(ux, uy)
    if L < 1e-9:
        return 0.0
    ux, uy = ux / L, uy / L
    off = lambda r: (r[0] - p[0]) * uy - (r[1] - p[1]) * ux
    if abs(off(a)) > 1e-6 or abs(off(b)) > 1e-6:
        return 0.0
    proj = lambda r: (r[0] - p[0]) * ux + (r[1] - p[1]) * uy
    lo, hi = sorted((proj(a), proj(b)))
    return max(0.0, min(L, hi) - max(0.0, lo))


def extract_chains(n, adjacency):
    """Key nodes (terminals/junctions) and the chains of node indices between them."""
    nbrs = [sorted({v for v, _ in adjacency[u] if v != u}) for u in range(n)]
    key = {u for u in range(n) if nbrs[u] and len(nbrs[u]) != 2}
    seen = set()
    for u in range(n):  # a pure loop without any key node: pick its lowest index
        if u in seen or not nbrs[u]:
            continue
        comp, stack = [], [u]
        seen.add(u)
        while stack:
            x = stack.pop(); comp.append(x)
            for y in nbrs[x]:
                if y not in seen:
                    seen.add(y); stack.append(y)
        if not key & set(comp):
            key.add(min(comp))
    chains, used = [], set()
    for k in sorted(key):
        for m in nbrs[k]:
            if (k, m) in used:
                continue
            chain = [k, m]
            used.update({(k, m), (m, k)})
            while chain[-1] not in key:
                cur, prev = chain[-1], chain[-2]
                nxt = next(x for x in nbrs[cur] if x != prev)
                used.update({(cur, nxt), (nxt, cur)})
                chain.append(nxt)
            chains.append(chain)
    return key, chains


def place_along(stations, pts):
    """Evenly space stations along a polyline; return positions and the bends between stations."""
    clean = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, clean[-1]) > 1e-9:
            clean.append(p)
    pts = [clean[0]]  # keep only real corners
    for k in range(1, len(clean) - 1):
        a, b, c = pts[-1], clean[k], clean[k + 1]
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-9:
            pts.append(b)
    if len(clean) > 1:
        pts.append(clean[-1])
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))

    def at(d):
        for k in range(len(pts) - 1):
            if d <= cum[k + 1] + 1e-9 or k == len(pts) - 2:
                t = 0 if cum[k + 1] == cum[k] else (d - cum[k]) / (cum[k + 1] - cum[k])
                (x1, y1), (x2, y2) = pts[k], pts[k + 1]
                return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
        return pts[0]

    n = len(stations) - 1
    arcs = [cum[-1] * i / n for i in range(n + 1)]
    coords = [at(d) for d in arcs]
    bends = [[pts[k] for k in range(1, len(pts) - 1) if da + 1e-9 < cum[k] < db - 1e-9]
             for da, db in zip(arcs, arcs[1:])]
    return coords, bends


def lp_layout(graph, config, log=None):
    """Return (positions (n, 2), routes per edge) for one connected graph, y up, unit = station spacing."""
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix, vstack

    cfg = config['lp']
    log = log or (lambda *a: None)
    pos = graph.geo
    n = len(graph.nodes)
    key, chains = extract_chains(n, graph.adjacency)
    split = []
    for ch in chains:  # a chain that closes on itself is cut in the middle
        if ch[0] == ch[-1] and len(ch) > 3:
            mid = len(ch) // 2
            key.add(ch[mid]); split += [ch[:mid + 1], ch[mid:]]
        else:
            split.append(ch)
    C = [{'st': ch, 'u': ch[0], 'v': ch[-1], 'L': len(ch) - 1} for ch in split]
    positions = np.zeros((n, 2))
    routes = [None] * len(graph.edges)
    if not C:
        return positions, routes
    log(f'LP layout: {n} stations, {len(key)} key nodes, {len(C)} chains')

    def geo_dir(node, ci):
        """Geographic direction of a chain leaving node, aimed ~1/3 (at most 4 stations) in."""
        st = C[ci]['st'] if C[ci]['u'] == node else C[ci]['st'][::-1]
        far = st[max(1, min(4, len(st) // 3))]
        return math.atan2(pos[far][1] - pos[node][1], pos[far][0] - pos[node][0])

    # 1. Port assignment: 0 = east, counterclockwise in 45 degree steps.
    incident = defaultdict(list)
    for ci, c in enumerate(C):
        incident[c['u']].append(ci)
        incident[c['v']].append(ci)
    port = {}

    def dev(angle, p):
        return abs((angle - p * math.pi / 4 + math.pi) % (2 * math.pi) - math.pi)

    for node, cis in incident.items():
        ends = sorted(cis, key=lambda ci: geo_dir(node, ci) % (2 * math.pi))
        angs = [geo_dir(node, ci) for ci in ends]
        k = len(ends)
        if k > 8:
            raise ValueError(f'{graph.nodes[node]["id"]} has {k} chains, more than 8 octilinear ports')
        best, best_cost = None, math.inf
        for subset in combinations(range(8), k):
            for r in range(k):  # rotate the mapping: keeps circular order
                assign = [subset[(i + r) % k] for i in range(k)]
                cost = sum(dev(a, p) ** 2 + (cfg['port_diagonal_cost'] if p % 2 else 0) for a, p in zip(angs, assign))
                if cost < best_cost:
                    best, best_cost = assign, cost
        for ci, p in zip(ends, best):
            port[(node, ci)] = p

    # 2. Direction sequence of each chain.
    shape = {}
    for ci, c in enumerate(C):
        d0 = port[(c['u'], ci)]
        d1 = (port[(c['v'], ci)] + 4) % 8  # travel direction on arrival at v
        turn = (d1 - d0) % 8
        if turn == 0:
            dirs = [d0]
        elif turn in (1, 2, 6, 7):
            dirs = [d0, d1]
        elif turn in (3, 5):
            # 135 degrees: a 90 degree piece then 45 degrees, rotating the short way. Going the
            # long way round (225 degrees) makes the third piece cross the first.
            dirs = [d0, (d0 + (2 if turn == 3 else -2)) % 8, d1]
        else:
            # 180 degrees: a U, bending toward the chain's geography.
            mid = c['st'][len(c['st']) // 2]
            gx, gy = pos[mid][0] - pos[c['u']][0], pos[mid][1] - pos[c['u']][1]
            left = (math.cos(d0 * math.pi / 4) * gy - math.sin(d0 * math.pi / 4) * gx) > 0
            dirs = [d0, (d0 + (2 if left else -2)) % 8, d1]
        shape[ci] = dirs

    # 3. Variables: key nodes plus each chain's corners.
    vid = {}

    def var_of(k):
        if k not in vid:
            vid[k] = len(vid)
        return vid[k]
    chain_verts = {}
    for ci, c in enumerate(C):
        chain_verts[ci] = ([var_of(('n', c['u']))] + [var_of(('c', ci, j)) for j in range(len(shape[ci]) - 1)]
                           + [var_of(('n', c['v']))])
    nv = len(vid)
    X = lambda v: v
    Y = lambda v: nv + v
    rows, lo, hi, cost, slack_cost = [], [], [], [0.0] * (2 * nv), []

    def add(coefs, l=-math.inf, h=math.inf):
        rows.append(coefs); lo.append(l); hi.append(h)

    def soft(coefs, l, weight):
        """coefs . z >= l, violable through a slack costing weight per unit."""
        s = 2 * nv + len(slack_cost)
        slack_cost.append(weight)
        add({**coefs, s: 1}, l)

    min_piece, w_shape = cfg['min_piece'], cfg['w_shape']
    for ci, c in enumerate(C):
        vs, dirs = chain_verts[ci], shape[ci]
        length_terms = defaultdict(float)
        for (a, b), d in zip(zip(vs, vs[1:]), dirs):
            dx, dy = DV[d]
            if dx == 0:
                add({X(b): 1, X(a): -1}, 0, 0)
                soft({Y(b): dy, Y(a): -dy}, min_piece, w_shape)
                length_terms[Y(b)] += dy; length_terms[Y(a)] -= dy
            elif dy == 0:
                add({Y(b): 1, Y(a): -1}, 0, 0)
                soft({X(b): dx, X(a): -dx}, min_piece, w_shape)
                length_terms[X(b)] += dx; length_terms[X(a)] -= dx
            else:
                add({X(b): dy, X(a): -dy, Y(b): -dx, Y(a): dx}, 0, 0)
                soft({X(b): dx, X(a): -dx}, min_piece / math.sqrt(2), w_shape)
                length_terms[X(b)] += dx * math.sqrt(2); length_terms[X(a)] -= dx * math.sqrt(2)
        add(dict(length_terms), c['L'])  # total length >= station count: spacing at least 1
        for j, w in length_terms.items():
            cost[j] += w

    # 4. Relative position of geographically near key nodes.
    knodes = sorted(key)

    def rel_constraint(a_var, b_var, ga, gb, weight):
        gx, gy = gb[0] - ga[0], gb[1] - ga[1]
        g = math.hypot(gx, gy)
        if g < 1e-9:
            return
        if abs(gx) >= cfg['rel_ratio'] * g:
            sx = 1 if gx > 0 else -1
            soft({X(b_var): sx, X(a_var): -sx}, cfg['node_sep'], weight)
        if abs(gy) >= cfg['rel_ratio'] * g:
            sy = 1 if gy > 0 else -1
            soft({Y(b_var): sy, Y(a_var): -sy}, cfg['node_sep'], weight)

    linked = {frozenset((c['u'], c['v'])) for c in C}
    pairs = set()
    for a in knodes:
        near = sorted((b for b in knodes if b != a), key=lambda b: (math.dist(pos[a], pos[b]), b))[:cfg['rel_neighbors']]
        pairs.update(frozenset((a, b)) for b in near)
    for pr in sorted(tuple(sorted(p)) for p in pairs - linked):  # linked pairs already follow their ports
        a, b = pr
        rel_constraint(var_of(('n', a)), var_of(('n', b)), pos[a], pos[b], cfg['w_rel'])

    def solve():
        nvar = 2 * nv + len(slack_cost)
        r, cidx, val = [], [], []
        for i, coefs in enumerate(rows):
            for j, a in coefs.items():
                r.append(i); cidx.append(j); val.append(a)
        A = coo_matrix((val, (r, cidx)), shape=(len(rows), nvar)).tocsr()
        lo_a, hi_a = np.array(lo), np.array(hi)
        eq = lo_a == hi_a
        A_ub = vstack([A[~eq & np.isfinite(hi_a)], -A[~eq & np.isfinite(lo_a)]])
        b_ub = np.concatenate([hi_a[~eq & np.isfinite(hi_a)], -lo_a[~eq & np.isfinite(lo_a)]])
        bounds = [(None, None)] * (2 * nv) + [(0, None)] * len(slack_cost)
        bounds[X(0)] = (0, 0); bounds[Y(0)] = (0, 0)
        return linprog(cost + slack_cost, A_ub=A_ub, b_ub=b_ub, A_eq=A[eq], b_eq=lo_a[eq], bounds=bounds, method='highs')

    def seg_geo(ci, j):
        """Rough geographic location of a piece: the stations at the matching chain fraction."""
        st = C[ci]['st']; m = len(shape[ci])
        a = st[int(len(st) * j / m)]; b = st[min(len(st) - 1, int(len(st) * (j + 1) / m))]
        return ((pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2)

    seg_index = {(ci, j): (chain_verts[ci][j], chain_verts[ci][j + 1]) for ci in range(len(C)) for j in range(len(shape[ci]))}

    # 5. Separate crossing, overlapping or too-close pieces and re-solve.
    seg_sep, added = cfg['seg_sep'], set()
    for rnd in range(cfg['rounds']):
        res = solve()
        if res.status != 0:
            raise RuntimeError(f'Constraint-graph LP has no solution: {res.message}')
        P = [(res.x[X(v)], res.x[Y(v)]) for v in range(nv)]
        segs = [(k, P[a], P[b]) for k, (a, b) in seg_index.items()]
        bad = []
        for i in range(len(segs)):
            k1, p1, q1 = segs[i]
            for j in range(i + 1, len(segs)):
                k2, p2, q2 = segs[j]
                if k1[0] == k2[0]:
                    continue
                if set(seg_index[k1]) & set(seg_index[k2]):
                    if overlap_len(p1, q1, p2, q2) < 1e-6:  # sharing a key node conflicts only when stacked
                        continue
                elif seg_dist(p1, q1, p2, q2) >= seg_sep * 0.99:
                    continue
                pair = (min(k1, k2), max(k1, k2))
                if pair not in added:
                    bad.append(pair)
        log(f'LP solve {rnd + 1}: {len(bad)} crossing or close piece pairs')
        if not bad:
            break
        for k1, k2 in bad:
            added.add((k1, k2))
            g1, g2 = seg_geo(*k1), seg_geo(*k2)
            gx, gy = g2[0] - g1[0], g2[1] - g1[1]
            (a1, b1), (a2, b2) = seg_index[k1], seg_index[k2]
            shared = {a1, b1} & {a2, b2}
            # Put the whole second piece on its geographic side of the first.
            axis = 0 if abs(gx) >= abs(gy) else 1
            sgn = 1 if (gx if axis == 0 else gy) > 0 else -1
            V = X if axis == 0 else Y
            for v1 in (a1, b1):
                for v2 in (a2, b2):
                    if v1 in shared or v2 in shared:
                        continue
                    soft({V(v2): sgn, V(v1): -sgn}, seg_sep, cfg['w_sep'])

    viol = [w for v, w in zip(res.x[2 * nv:], slack_cost) if v > 1e-6]
    n_shape = sum(1 for w in viol if w == w_shape)
    if viol:
        log(f'LP: {len(viol) - n_shape} relative/separation constraints and {n_shape} piece directions unsatisfied')

    edge_of = {frozenset(map(int, e)): i for i, e in enumerate(graph.endpoints)}
    placed = set()
    for ci, c in enumerate(C):
        coords, bends = place_along(c['st'], [P[v] for v in chain_verts[ci]])
        for sid, p in zip(c['st'], coords):
            if sid not in placed:
                positions[sid] = p; placed.add(sid)
        for a, b, inner in zip(c['st'], c['st'][1:], bends):
            edge = edge_of[frozenset((a, b))]
            path = [positions[a], *inner, positions[b]]
            if graph.endpoints[edge][0] != a:
                path = path[::-1]
            routes[edge] = np.array(path, dtype=float)
    # Key nodes are placed by their first chain; re-anchor every route on final station positions.
    for edge, (u, v) in enumerate(graph.endpoints):
        routes[edge][0], routes[edge][-1] = positions[u], positions[v]
    return positions, routes
