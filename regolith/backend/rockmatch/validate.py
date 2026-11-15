"""Hold-out tests of Regolith's matching and predictions, run by build_dataset.py and shown in the app.

Every number here is measured on NASA/CSA data the method was not allowed to see:
- re-measurement test: a known rock is "measured again" with its own instrument error bars - is it found?
- nearest-other test: with a rock removed, is the closest remaining rock the same deposit type?
- new-stop test: hide a measurement and everything within 50 m of it (the whole rover stop), then predict its
  deposit type from the measurements around it.
"""
from __future__ import annotations

import math
import random

from .chemistry import TRACES, classify
from .geo import fast_distance_m
from .match import Matcher
from .predict import MIN_NEAR, NEAR_M, class_odds, near_weight

HOLD_M = 50.0          # a rover stop: repeat measurements of one target sit within this distance
SAMPLE = 400
SEED = 20261114


def remeasure(rock: dict, rng: random.Random) -> dict:
    """The rock's chemistry plus Gaussian noise of its own 1-sigma error bars (same as the app's Simulate)."""
    out = {}
    for el, v in rock["chemistry"].items():
        err = (rock.get("errors") or {}).get(el) or max(0.03 * v, 10 if el in TRACES else 0.02)
        out[el] = max(0.0, v + rng.gauss(0, 1) * err)
    return out


def matching_tests(rocks: list[dict]) -> dict:
    rng = random.Random(SEED)
    matcher = Matcher(rocks)
    sample = rng.sample(rocks, min(SAMPLE, len(rocks)))
    top1 = top5 = same_class = stable = loo = 0
    for r in sample:
        noisy = remeasure(r, rng)
        hits = matcher.search(noisy, top_k=5)
        ids = [h["rock"]["id"] for h in hits]
        top1 += bool(ids) and ids[0] == r["id"]
        top5 += r["id"] in ids
        same_class += bool(hits) and hits[0]["rock"]["deposit"] == r["deposit"]
        stable += classify(noisy, r.get("sample_type"))[0] == r["deposit"]
        other = matcher.search(r["chemistry"], top_k=1, exclude={r["id"]})
        loo += bool(other) and other[0]["rock"]["deposit"] == r["deposit"]
    n = len(sample)
    pct = lambda k: round(100 * k / n, 1)  # noqa: E731
    return {"n": n, "seed": SEED,
            "remeasure_top1_pct": pct(top1), "remeasure_top5_pct": pct(top5), "remeasure_same_type_pct": pct(same_class),
            "classification_stable_pct": pct(stable), "nearest_other_same_type_pct": pct(loo)}


def nearby_test(rocks: list[dict]) -> dict:
    n = len(rocks)
    prior: dict[str, float] = {}
    for r in rocks:
        prior[r["deposit"]] = prior.get(r["deposit"], 0.0) + 1 / n
    common = max(prior, key=prior.get)
    by_rover: dict[str, list[int]] = {}
    for i, r in enumerate(rocks):
        by_rover.setdefault(r["rover"], []).append(i)
    nb: list[list[tuple[float, int]]] = [[] for _ in rocks]
    for idx in by_rover.values():
        for a, i in enumerate(idx):
            ri = rocks[i]
            for j in idx[a + 1:]:
                rj = rocks[j]
                if abs(ri["lat"] - rj["lat"]) > 0.02:          # 0.02 deg of latitude is about 1.2 km
                    continue
                d = fast_distance_m(ri["lat"], ri["lon"], rj["lat"], rj["lon"])
                if d <= NEAR_M:
                    nb[i].append((d, j))
                    nb[j].append((d, i))
    cases = top1 = top3 = base = 0
    ll = ll_prior = 0.0
    bins = [[0.0, 0.10, 0.0, 0, 0], [0.10, 0.30, 0.0, 0, 0], [0.30, 0.60, 0.0, 0, 0], [0.60, 1.01, 0.0, 0, 0]]
    for i, r in enumerate(rocks):
        w: dict[str, float] = {}
        m = 0
        for d, j in nb[i]:
            if d <= HOLD_M:
                continue
            c = rocks[j]["deposit"]
            w[c] = w.get(c, 0.0) + near_weight(d)
            m += 1
        if m < MIN_NEAR:
            continue
        p = class_odds(w, prior)
        rank = sorted(p, key=lambda c: -p[c])
        true = r["deposit"]
        cases += 1
        top1 += rank[0] == true
        top3 += true in rank[:3]
        base += true == common
        ll += -math.log(max(p.get(true, 0.0), 1e-9))
        ll_prior += -math.log(prior[true])
        for c, v in p.items():
            for b in bins:
                if b[0] <= v < b[1]:
                    b[2] += v
                    b[3] += 1
                    b[4] += c == true
                    break
    pct = lambda k: round(100 * k / cases, 1)  # noqa: E731
    return {"n": cases, "hold_m": HOLD_M, "top1_pct": pct(top1), "top3_pct": pct(top3),
            "baseline_pct": pct(base), "baseline_class": common,
            "log_loss": round(ll / cases, 3), "log_loss_prior_only": round(ll_prior / cases, 3),
            "calibration": [{"range_pct": [round(b[0] * 100), min(100, round(b[1] * 100))], "predicted_pct": round(100 * b[2] / b[3], 1),
                             "observed_pct": round(100 * b[4] / b[3], 1), "n": b[3]} for b in bins if b[3]]}


def run(rocks: list[dict]) -> dict:
    return {"matching": matching_tests(rocks), "nearby": nearby_test(rocks)}
