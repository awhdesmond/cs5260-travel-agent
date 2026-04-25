import math
import statistics
from datetime import time

EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Return great-circle distance in km between two lat/lng points.
    """
    lat1_r, lng1_r, lat2_r, lng2_r = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def median_latlng(items: list[dict]) -> tuple[float, float] | None:
    """
    Return median lat/lng of items that have coordinates. Returns None if empty.
    """
    lats = [a["lat"] for a in items if a.get("lat") is not None]
    lngs = [a["lng"] for a in items if a.get("lng") is not None]

    if not lats or not lngs:
        return None

    return statistics.median(lats), statistics.median(lngs)


def parse_time(t: str) -> time:
    """
    Split a time string in HH:MM format and return a time object.
    """
    h, m = t.split(":")
    return time(int(h), int(m))


def parse_duration_minutes(dur: str | None) -> int:
    """
    Parse a duration string in HHMM format and return the duration in minutes.
    """
    if not dur:
        return 0
    try:
        total = 0
        d = dur.upper().replace("PT", "")
        if "H" in d:
            h, d = d.split("H", 1)
            total += int(h) * 60
        if "M" in d:
            m = d.replace("M", "")
            total += int(m)
        return total
    except (ValueError, IndexError):
        return 0
