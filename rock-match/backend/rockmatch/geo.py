"""Mars geometry helpers (planetocentric latitude, east longitude in degrees)."""
from __future__ import annotations

import math

MARS_RADIUS_M = 3_389_500.0        # mean radius, for surface distances
MARS_EQ_RADIUS_M = 3_396_190.0     # IAU equatorial radius, used by MER traverse projections


def wrap_lon(lon: float) -> float:
    """Wrap a longitude into [-180, 180)."""
    return (lon + 180.0) % 360.0 - 180.0


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance on Mars in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * MARS_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def fast_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Equirectangular approximation - accurate to <0.1% over a few tens of km."""
    x = math.radians(wrap_lon(lon2 - lon1)) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return MARS_RADIUS_M * math.hypot(x, y)

