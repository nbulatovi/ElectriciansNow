"""iOS Core Location bridge with robust polling and a state machine.

The previous version had an 8s timeout that started before the user could
react to the permission dialog. This version:
- Checks authorizationStatus before doing anything.
- Bumps the wait to 30s with status callbacks every step.
- Polls manager.location through the wait so we catch the first fix
  whenever it lands (permission dialog can take any amount of user time).
- Has an explicit denied/restricted/timeout state.

Reverse geocoding uses Nominatim (free).

Note: Apple's CLLocationManager normally delivers updates via a delegate.
Without a delegate, manager.location can be populated as a side effect of
startUpdatingLocation if the run loop is serviced. Kivy services its loop
on the main thread; this function runs on a worker thread and polls,
which is enough for the simple "give me the current location" use case.
"""

import platform
import time

from app_logger import log, log_exception

IS_IOS = platform.system() == "Darwin"

_OBJC_OK = False
CLLocationManager = None
autoclass = None

if IS_IOS:
    try:
        from pyobjus import autoclass as _autoclass
        autoclass = _autoclass
        CLLocationManager = autoclass('CLLocationManager')
        _OBJC_OK = True
        log("location", "pyobjus core loaded")
    except Exception as e:
        log_exception("location", "pyobjus unavailable", e)


# Apple authorization status values
NOT_DETERMINED = 0
RESTRICTED = 1
DENIED = 2
AUTHORIZED_ALWAYS = 3
AUTHORIZED_WHEN_IN_USE = 4


def authorization_status():
    if not _OBJC_OK:
        return None
    try:
        return CLLocationManager.authorizationStatus()
    except Exception as e:
        log_exception("location", "authorizationStatus raised", e)
        return None


def get_current_address(status_cb=None, timeout=30):
    """Resolve the user's current address.

    status_cb(state, ms_elapsed, **extra): called as the state machine
    advances. States: waiting_permission, locating, geocoding, done,
    denied, restricted, timeout, unsupported, error.

    Returns the human-readable address string on success, None otherwise.
    """
    started = time.time()

    def _emit(state, **extra):
        ms = int((time.time() - started) * 1000)
        log("location", f"state={state}", ms=ms, **extra)
        if status_cb:
            try:
                status_cb(state, ms, **extra)
            except Exception:
                pass

    if not _OBJC_OK:
        _emit("unsupported")
        return None

    auth = authorization_status()
    log("location", "initial auth", value=auth)
    if auth in (DENIED, RESTRICTED):
        _emit("denied" if auth == DENIED else "restricted")
        return None

    try:
        manager = CLLocationManager.alloc().init()
        manager.desiredAccuracy = 100  # ~100m, plenty for geocoding
    except Exception as e:
        log_exception("location", "manager init failed", e)
        _emit("error", reason="manager_init")
        return None

    try:
        manager.requestWhenInUseAuthorization()
    except Exception as e:
        log_exception("location", "requestAuth failed", e)

    _emit("waiting_permission")

    # Phase 1: wait for permission. Tight loop so the moment user grants,
    # we move on without burning the entire 30s budget.
    perm_deadline = started + timeout
    auth = authorization_status()
    while auth not in (AUTHORIZED_ALWAYS, AUTHORIZED_WHEN_IN_USE) and time.time() < perm_deadline:
        if auth in (DENIED, RESTRICTED):
            _emit("denied" if auth == DENIED else "restricted")
            return None
        time.sleep(0.4)
        auth = authorization_status()

    if auth not in (AUTHORIZED_ALWAYS, AUTHORIZED_WHEN_IN_USE):
        _emit("timeout", phase="permission")
        return None

    _emit("locating")

    # Phase 2: start updating + wait for a fix.
    try:
        manager.startUpdatingLocation()
    except Exception as e:
        log_exception("location", "startUpdating failed", e)
        _emit("error", reason="startUpdating")
        return None

    coords = None
    deadline = time.time() + 20  # 20s after permission for first fix
    while time.time() < deadline:
        time.sleep(0.4)
        try:
            loc = manager.location
            if loc:
                lat = loc.coordinate.latitude
                lng = loc.coordinate.longitude
                # Some implementations return (0,0) until first real fix
                if lat or lng:
                    coords = (lat, lng)
                    break
        except Exception as e:
            log_exception("location", "polling raised", e)

    try:
        manager.stopUpdatingLocation()
    except Exception:
        pass

    if not coords:
        _emit("timeout", phase="locate")
        return None

    _emit("geocoding", lat=coords[0], lng=coords[1])
    addr = _reverse_geocode(*coords)
    if addr:
        _emit("done", lat=coords[0], lng=coords[1], address=addr)
    else:
        _emit("error", reason="geocode_failed")
    return addr


def _reverse_geocode(lat, lng):
    try:
        import requests
    except Exception:
        return None
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "addressdetails": 1},
            headers={"User-Agent": "ElectriciansNow/1.0"},
            timeout=10,
        )
        log("location", "reverse geocode", status=r.status_code)
        if r.status_code != 200:
            return None
        data = r.json()
        a = data.get("address", {}) or {}
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
        return data.get("display_name") or None
    except Exception as e:
        log_exception("location", "reverse geocode raised", e)
        return None
