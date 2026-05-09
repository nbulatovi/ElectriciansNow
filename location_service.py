"""iOS Core Location bridge + free reverse geocoding via Nominatim.

Pyobjus drives CLLocationManager. We poll for `manager.location` after
calling start, since attaching a delegate from Python is fragile. The
returned coordinate is reverse-geocoded with OpenStreetMap's free
Nominatim endpoint to produce a human-readable address.
"""

import platform
import time

from app_logger import log, log_exception

IS_IOS = platform.system() == "Darwin"

if IS_IOS:
    try:
        from pyobjus import autoclass
        CLLocationManager = autoclass('CLLocationManager')
        OBJC_AVAILABLE = True
    except Exception as e:
        OBJC_AVAILABLE = False
        log_exception("location", "pyobjus unavailable", e)
else:
    OBJC_AVAILABLE = False


def _ios_get_coords(timeout_seconds=8):
    """Returns (lat, lng) or None. Requests permission on first call."""
    if not OBJC_AVAILABLE:
        return None
    try:
        m = CLLocationManager.alloc().init()
        m.requestWhenInUseAuthorization()
        m.startUpdatingLocation()
        log("location", "started CLLocationManager")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(0.4)
            loc = m.location
            if loc:
                lat = loc.coordinate.latitude
                lng = loc.coordinate.longitude
                m.stopUpdatingLocation()
                log("location", "got coords", lat=lat, lng=lng)
                return (lat, lng)
        m.stopUpdatingLocation()
        log("location", "timeout waiting for coords")
        return None
    except Exception as e:
        log_exception("location", "iOS coord fetch failed", e)
        return None


def _reverse_geocode(lat, lng):
    """Use Nominatim (free, no key) to get a readable address."""
    import requests
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        r = requests.get(url, params={
            "lat": lat, "lon": lng, "format": "json", "addressdetails": 1,
        }, headers={"User-Agent": "ElectriciansNow/1.0"}, timeout=10)
        log("location", "reverse geocode response", status=r.status_code)
        if r.status_code == 200:
            data = r.json()
            # Build a clean street + city + state line
            a = data.get("address", {})
            parts = []
            num = a.get("house_number")
            road = a.get("road")
            if num and road:
                parts.append(f"{num} {road}")
            elif road:
                parts.append(road)
            city = a.get("city") or a.get("town") or a.get("village") or a.get("hamlet")
            if city:
                parts.append(city)
            state = a.get("state")
            if state:
                parts.append(state)
            zipcode = a.get("postcode")
            if zipcode:
                parts.append(zipcode)
            if parts:
                return ", ".join(parts)
            return data.get("display_name", "")
    except Exception as e:
        log_exception("location", "reverse geocode failed", e)
    return None


def get_current_address():
    """Returns a string address for the user's current location, or None."""
    coords = _ios_get_coords() if IS_IOS else None
    if not coords:
        return None
    return _reverse_geocode(*coords)
