"""Address autocomplete via Photon (free OSM-based, no API key).

Photon docs: https://photon.komoot.io/

Per Komoot's stated rate limit, we cap requests at ~1 per second per
client. Results are biased toward the US continental centroid; tweak
the bias for other markets later.
"""

import time
from threading import Lock

from app_logger import log, log_exception

PHOTON_URL = "https://photon.komoot.io/api/"
US_CENTER = (39.5, -98.35)

_last_request = 0.0
_request_lock = Lock()


def _rate_limit_wait(min_interval=1.0):
    global _last_request
    with _request_lock:
        delta = time.time() - _last_request
        if delta < min_interval:
            time.sleep(min_interval - delta)
        _last_request = time.time()


def _format_feature(f):
    p = f.get("properties", {}) or {}
    parts = []
    num = p.get("housenumber")
    name = p.get("name")
    street = p.get("street")
    if num and street:
        parts.append(f"{num} {street}")
    elif street:
        parts.append(street)
    elif name:
        parts.append(name)
    city = p.get("city") or p.get("town") or p.get("village") or p.get("hamlet")
    if city:
        parts.append(city)
    state = p.get("state")
    if state:
        parts.append(state)
    postcode = p.get("postcode")
    if postcode:
        parts.append(postcode)
    label = ", ".join(parts) if parts else (p.get("country") or "")

    coords = (f.get("geometry") or {}).get("coordinates", [None, None])
    lng, lat = coords[0], coords[1]
    return {"label": label, "lat": lat, "lng": lng, "raw": p}


def suggest(query, limit=5):
    """Return up to `limit` address suggestions for the user's typed query.

    Returns [] on empty query, network error, or non-200 response.
    """
    if not query or len(query.strip()) < 3:
        return []

    try:
        import requests
    except Exception as e:
        log_exception("autocomplete", "requests not available", e)
        return []

    _rate_limit_wait()
    log("autocomplete", "photon query", q=query, limit=limit)

    try:
        r = requests.get(PHOTON_URL, params={
            "q": query,
            "limit": limit,
            "lang": "en",
            "lat": US_CENTER[0],
            "lon": US_CENTER[1],
            "location_bias_scale": 0.3,
        }, timeout=6)
    except Exception as e:
        log_exception("autocomplete", "request raised", e)
        return []

    if r.status_code != 200:
        log("autocomplete", "non-200", status=r.status_code, body=r.text[:300])
        return []

    try:
        data = r.json()
    except Exception as e:
        log_exception("autocomplete", "json decode", e)
        return []

    features = data.get("features") or []
    results = [_format_feature(f) for f in features]
    results = [r for r in results if r["label"]]
    log("autocomplete", "results", count=len(results),
        first=results[0]["label"] if results else None)
    return results
