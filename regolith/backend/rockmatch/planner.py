"""EVA traverse planner: a walking route over real terrain that visits the most valuable deposit sites and
returns to the start within the time budget.

Terrain: NASA Mars Trek "MRO HiRISE, Gale Crater DEM" (Gale_DEM_SMG_1m), read at ~10 m per pixel. Its 8-bit
grey levels are converted to metres with a scale fitted to the elevations of all 1,768 Curiosity waypoints
(residual about 6 m, the size of one grey step), then averaged into 80 m cells and smoothed so the 18.6 m grey
steps do not show up as fake cliffs.

Walking: speed falls with slope following the shape of Tobler's hiking function (an Earth rule), scaled to the
chosen flat-ground speed; cells steeper than the slope limit are not entered.

Route: an orienteering heuristic (greedy insertion by value per extra minute, then 2-opt), with the whole EVA -
walking, sampling stops and the walk back - kept inside the budget minus a reserve.
"""
from __future__ import annotations

import heapq
import math
from functools import lru_cache
from pathlib import Path

from .geo import MARS_RADIUS_M
from .terrain import read_png_grey

GALE_Z = 12
GALE_BBOX = (137.1224711, -4.9254743, 137.7298129, -4.2489631)     # lon W, lat S, lon E, lat N
CELL_M = 80.0
RESERVE = 0.10                                                     # share of the EVA kept back for safety
M_PER_DEG = MARS_RADIUS_M * math.pi / 180


class Terrain:
    """Calibrated Gale DEM, read lazily tile by tile."""

    def __init__(self, folder: Path, scale: float, offset: float):
        self.folder, self.scale, self.offset = folder, scale, offset
        self.span = 180 / 2 ** GALE_Z

    def covers(self, lat: float, lon: float, margin_deg: float = 0.0) -> bool:
        w, s, e, n = GALE_BBOX
        return w + margin_deg <= lon <= e - margin_deg and s + margin_deg <= lat <= n - margin_deg

    @lru_cache(maxsize=512)
    def _tile(self, ty: int, tx: int):
        f = self.folder / f"{ty}_{tx}.png"
        return read_png_grey(f, keep_alpha=True) if f.exists() else None

    def grey(self, lat: float, lon: float):
        x, y = (lon + 180) / self.span, (90 - lat) / self.span
        tx, ty = int(x), int(y)
        t = self._tile(ty, tx)
        if t is None:
            return None
        g, a = t[min(255, int((y - ty) * 256))][min(255, int((x - tx) * 256))]
        return g if a else None

    def elev(self, lat: float, lon: float):
        g = self.grey(lat, lon)
        return None if g is None else self.scale * g + self.offset


def tobler(slope: float) -> float:
    """Relative walking speed for a gradient (rise/run), 1.0 on flat ground (Tobler's hiking function shape)."""
    return math.exp(-3.5 * (abs(slope + 0.05) - 0.05))


def class_values(class_counts: dict[str, int], typical: set[str]) -> dict[str, float]:
    """Scientific value of a deposit type: rarer types are worth more (information, -log frequency)."""
    total = sum(class_counts.values()) or 1
    return {c: (0.0 if c in typical else max(0.5, -math.log(n / total))) for c, n in class_counts.items()}


def plan(terrain: Terrain, start: tuple[float, float], hours: float, max_slope_deg: float, stop_min: float,
         speed_kmh: float, sites: list[dict], values: dict[str, float], labels: dict[str, str]) -> dict:
    lat0, lon0 = start
    if not terrain.covers(lat0, lon0):
        raise ValueError("The planner needs high-resolution terrain: it covers the MRO HiRISE Gale Crater DEM "
                         f"({GALE_BBOX[1]:.2f} to {GALE_BBOX[3]:.2f} N, {GALE_BBOX[0]:.2f} to {GALE_BBOX[2]:.2f} E), "
                         "Curiosity's area. Pick a start point there.")
    budget_h = hours * (1 - RESERVE)
    reach_m = min(budget_h * speed_kmh * 1000 / 2, 7000) + 400
    coslat = math.cos(math.radians(lat0))
    dlat, dlon = CELL_M / M_PER_DEG, CELL_M / (M_PER_DEG * coslat)
    n = int(2 * reach_m / CELL_M) + 1
    half = n // 2
    lat_of = lambda r: lat0 + (half - r) * dlat          # noqa: E731  row 0 = north
    lon_of = lambda c: lon0 + (c - half) * dlon          # noqa: E731

    # --- elevation grid: average of a 3x3 sample inside each cell, then a 3x3 smoothing pass (twice)
    raw = [[None] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            vals = []
            for fr in (-0.33, 0, 0.33):
                for fc in (-0.33, 0, 0.33):
                    e = terrain.elev(lat_of(r + fr), lon_of(c + fc))
                    if e is not None:
                        vals.append(e)
            raw[r][c] = sum(vals) / len(vals) if vals else None

    def smooth(g):
        out = [[None] * n for _ in range(n)]
        for r in range(n):
            for c in range(n):
                if g[r][c] is None:
                    continue
                vs = [g[rr][cc] for rr in range(max(0, r - 1), min(n, r + 2)) for cc in range(max(0, c - 1), min(n, c + 2))
                      if g[rr][cc] is not None]
                out[r][c] = sum(vs) / len(vs)
        return out
    elev = smooth(smooth(raw))

    # --- slope of each cell (degrees) from central differences
    slope = [[None] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            if elev[r][c] is None:
                continue
            def e(rr, cc):
                if 0 <= rr < n and 0 <= cc < n and elev[rr][cc] is not None:
                    return elev[rr][cc]
                return elev[r][c]
            gx = (e(r, c + 1) - e(r, c - 1)) / (2 * CELL_M)
            gy = (e(r - 1, c) - e(r + 1, c)) / (2 * CELL_M)
            slope[r][c] = math.degrees(math.atan(math.hypot(gx, gy)))
    ok = [[slope[r][c] is not None and slope[r][c] <= max_slope_deg for c in range(n)] for r in range(n)]
    ok[half][half] = elev[half][half] is not None

    v0 = speed_kmh * 1000 / 3600                          # m/s on flat ground
    nbrs = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]

    def dijkstra(src, targets):
        """Walking time (s) from src to every cell, stopping once all targets are settled."""
        dist = {src: 0.0}
        prev = {}
        left = set(targets)
        pq = [(0.0, src)]
        while pq and left:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, math.inf):
                continue
            left.discard(u)
            r, c = u
            for dr, dc, k in nbrs:
                rr, cc = r + dr, c + dc
                if not (0 <= rr < n and 0 <= cc < n) or not ok[rr][cc]:
                    continue
                run = k * CELL_M
                t = run / (v0 * tobler((elev[rr][cc] - elev[r][c]) / run))
                nd = d + t
                if nd < dist.get((rr, cc), math.inf):
                    dist[(rr, cc)] = nd
                    prev[(rr, cc)] = u
                    heapq.heappush(pq, (nd, (rr, cc)))
        return dist, prev

    # --- candidate deposit sites inside the box, on passable ground (snapped to the nearest passable cell)
    def cell_of(lat, lon):
        return half - round((lat - lat0) / dlat), half + round((lon - lon0) / dlon)

    def snap(rc):
        r, c = rc
        for rad in range(0, 3):
            best = None
            for rr in range(r - rad, r + rad + 1):
                for cc in range(c - rad, c + rad + 1):
                    if 0 <= rr < n and 0 <= cc < n and ok[rr][cc]:
                        dd = (rr - r) ** 2 + (cc - c) ** 2
                        if best is None or dd < best[0]:
                            best = (dd, (rr, cc))
            if best:
                return best[1]
        return None

    cands = []
    for s in sites:
        v = values.get(s["class"], 0.0)
        if v <= 0:
            continue
        rc = cell_of(s["lat"], s["lon"])
        if not (0 <= rc[0] < n and 0 <= rc[1] < n):
            continue
        cell = snap(rc)
        if cell is None:
            continue
        cands.append({**s, "value": v, "cell": cell})
    start_cell = (half, half)
    d0, p0 = dijkstra(start_cell, [c["cell"] for c in cands])
    cands = [c for c in cands if c["cell"] in d0 and 2 * d0[c["cell"]] / 3600 + stop_min / 60 <= budget_h]
    cands.sort(key=lambda c: -c["value"] / (1 + d0[c["cell"]] / 3600))
    cands = cands[:14]

    nodes = [start_cell] + [c["cell"] for c in cands]
    trees = [(d0, p0)] + [dijkstra(cell, nodes) for cell in nodes[1:]]
    T = [[trees[i][0].get(nodes[j], math.inf) / 3600 for j in range(len(nodes))] for i in range(len(nodes))]

    # --- orienteering: greedy insertion by marginal value per extra hour, diversity-aware, then 2-opt
    def route_time(rt):
        seq = [0] + rt + [0]
        return sum(T[a][b] for a, b in zip(seq, seq[1:])) + len(rt) * stop_min / 60

    def route_value(rt):
        seen, total = {}, 0.0
        for i in rt:
            cl = cands[i - 1]["class"]
            total += cands[i - 1]["value"] * (1.0 if cl not in seen else 0.3)   # a second site of a type adds less
            seen[cl] = True
        return total

    def two_opt(rt):
        improved = True
        while improved:
            improved = False
            for a in range(len(rt) - 1):
                for b in range(a + 1, len(rt)):
                    alt = rt[:a] + rt[a:b + 1][::-1] + rt[b + 1:]
                    if route_time(alt) + 1e-9 < route_time(rt):
                        rt, improved = alt, True
        return rt

    route: list[int] = []
    while True:
        best = None
        base_t, base_v = route_time(route), route_value(route)
        for i in range(1, len(nodes)):
            if i in route:
                continue
            for pos in range(len(route) + 1):
                alt = route[:pos] + [i] + route[pos:]
                t = route_time(alt)
                if t > budget_h or math.isinf(t):
                    continue
                gain = (route_value(alt) - base_v) / max(t - base_t, 1e-3)
                if best is None or gain > best[0]:
                    best = (gain, alt)
        if best is None:
            break
        route = two_opt(best[1])

    # --- reconstruct the walked path, with elevation, distance, gain and steepest slope
    def path(i, j):
        prev = trees[i][1]
        cur, out = nodes[j], []
        while cur != nodes[i]:
            out.append(cur)
            cur = prev[cur]
        out.append(nodes[i])
        return out[::-1]

    seq = [0] + route + [0]
    cells, stops, t_acc = [], [], 0.0
    for k, (a, b) in enumerate(zip(seq, seq[1:])):
        seg = path(a, b)
        cells.extend(seg if not cells else seg[1:])
        t_acc += T[a][b]
        if b != 0:
            c = cands[b - 1]
            stops.append({"n": k + 1, "id": c["id"], "class": c["class"], "label": labels.get(c["class"], c["class"]),
                          "names": c.get("names", [])[:3], "members": c.get("members", [])[:20], "count": c.get("count"),
                          "lat": c["lat"], "lon": c["lon"], "value": round(c["value"], 2),
                          "arrive_min": round(t_acc * 60), "leave_min": round(t_acc * 60 + stop_min)})
            t_acc += stop_min / 60
    pts, dist_m, gain_m, loss_m, steep = [], 0.0, 0.0, 0.0, 0.0
    for idx, (r, c) in enumerate(cells):
        e = elev[r][c]
        if idx:
            pr, pc = cells[idx - 1]
            run = CELL_M * math.hypot(r - pr, c - pc)
            rise = e - elev[pr][pc]
            dist_m += run
            gain_m += max(0.0, rise)
            loss_m += max(0.0, -rise)
            steep = max(steep, slope[r][c])
        pts.append([round(lat_of(r), 6), round(lon_of(c), 6), round(e, 1), round(dist_m)])
    # display line: Chaikin corner-cutting (twice) so the 80 m grid steps do not show as zig-zags
    line = [(p[0], p[1]) for p in pts]
    for _ in range(2):
        if len(line) < 3:
            break
        sm = [line[0]]
        for (a1, b1), (a2, b2) in zip(line, line[1:]):
            sm += [(0.75 * a1 + 0.25 * a2, 0.75 * b1 + 0.25 * b2), (0.25 * a1 + 0.75 * a2, 0.25 * b1 + 0.75 * b2)]
        line = sm + [line[-1]]
    walk_h = route_time(route) - len(route) * stop_min / 60
    total_h = route_time(route)
    types = sorted({s["class"] for s in stops})
    missed = [{"id": c["id"], "label": labels.get(c["class"], c["class"]), "class": c["class"], "lat": c["lat"], "lon": c["lon"],
               "one_way_min": round(d0[c["cell"]] / 60)} for i, c in enumerate(cands, 1) if i not in route][:5]
    return {
        "start": {"lat": lat0, "lon": lon0, "elev_m": round(elev[half][half], 1) if elev[half][half] is not None else None},
        "stops": stops, "path": pts, "line": [[round(a, 6), round(b, 6)] for a, b in line], "missed": missed,
        "summary": {"stops": len(stops), "new_types": len(types), "types": [labels.get(t, t) for t in types],
                    "distance_km": round(dist_m / 1000, 2), "gain_m": round(gain_m), "loss_m": round(loss_m),
                    "steepest_deg": round(steep, 1), "walk_h": round(walk_h, 2), "stops_h": round(len(stops) * stop_min / 60, 2),
                    "total_h": round(total_h, 2), "budget_h": hours, "reserve_h": round(hours - total_h, 2)},
        "settings": {"hours": hours, "max_slope_deg": max_slope_deg, "stop_min": stop_min, "speed_kmh": speed_kmh,
                     "cell_m": CELL_M, "reserve_pct": round(RESERVE * 100)},
    }
