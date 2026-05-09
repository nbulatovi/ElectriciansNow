"""NASA-style continuous telemetry.

Every meaningful action calls track(event, **data). Events queue in
memory; a daemon thread flushes to a Cloudflare Worker every 30 seconds
or on critical events. Failed flushes persist to disk for next launch.

Configuration is baked at build time via secrets_baked.py:
- TELEMETRY_URL: the CF worker URL (POST /ingest)
- TELEMETRY_HMAC_KEY: shared HMAC secret

If neither is set, telemetry no-ops gracefully (local logging still works).
"""

import hashlib
import hmac
import json
import os
import platform
import threading
import time
import uuid
from queue import Queue, Empty

# --- Secrets ---------------------------------------------------------------
try:
    import secrets_baked as _baked
except ImportError:
    _baked = None

def _secret(name, default=''):
    if _baked is not None and getattr(_baked, name, None):
        return getattr(_baked, name)
    return os.environ.get(name, default)

TELEMETRY_URL = _secret('TELEMETRY_URL')
TELEMETRY_HMAC_KEY = _secret('TELEMETRY_HMAC_KEY')

# --- Storage paths ---------------------------------------------------------
try:
    from kivy.utils import platform as _kvplatform
except ImportError:
    _kvplatform = "unknown"

if _kvplatform == "ios":
    _DIR = os.path.join(os.path.expanduser("~"), "Documents")
else:
    _DIR = os.path.expanduser("~/.electriciansnow")
try:
    os.makedirs(_DIR, exist_ok=True)
except Exception:
    _DIR = "/tmp"

PENDING_PATH = os.path.join(_DIR, "telemetry_pending.jsonl")

APP_VERSION = "248"  # bumped manually when shipping a new build

SESSION_ID = uuid.uuid4().hex[:16]

# --- Critical event prefixes flushed immediately ---------------------------
_CRITICAL_PREFIXES = ("payment_", "error_", "crash_", "estimate_returned",
                      "location_result", "app_started")

# --- Internals --------------------------------------------------------------
_queue: "Queue" = Queue(maxsize=2000)
_flush_lock = threading.Lock()
_started = False


def _device_info():
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python": platform.python_version(),
        "kivy_platform": _kvplatform,
    }


def _sign(body_bytes):
    if not TELEMETRY_HMAC_KEY:
        return ""
    return hmac.new(TELEMETRY_HMAC_KEY.encode(), body_bytes, hashlib.sha256).hexdigest()


def _post(events):
    """Synchronously POST a batch. Returns True on success."""
    if not TELEMETRY_URL or not events:
        return False
    try:
        import requests  # imported lazily to avoid startup penalty
    except Exception:
        return False
    payload = {
        "events": events,
        "session_id": SESSION_ID,
        "app_version": APP_VERSION,
        "device": _device_info(),
    }
    body = json.dumps(payload, default=str).encode()
    try:
        r = requests.post(
            TELEMETRY_URL.rstrip('/') + "/ingest",
            data=body,
            headers={"Content-Type": "application/json", "X-Sig": _sign(body)},
            timeout=8,
        )
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def _persist_pending(events):
    try:
        with open(PENDING_PATH, "a") as f:
            for ev in events:
                f.write(json.dumps(ev, default=str) + "\n")
    except Exception:
        pass


def _drain_pending():
    """Send up to 500 previously-failed events from disk."""
    try:
        with open(PENDING_PATH, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return
    except Exception:
        return
    if not lines:
        return
    batch, rest = lines[:500], lines[500:]
    events = []
    for line in batch:
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    if _post(events):
        try:
            with open(PENDING_PATH, "w") as f:
                f.writelines(rest)
        except Exception:
            pass


def _flush_loop():
    """Daemon: drain queue every 30s, also send pending from disk."""
    while True:
        time.sleep(30)
        try:
            with _flush_lock:
                events = []
                while True:
                    try:
                        events.append(_queue.get_nowait())
                    except Empty:
                        break
                if events:
                    if not _post(events):
                        _persist_pending(events)
                _drain_pending()
        except Exception:
            pass


def _drain_immediate():
    """Flush queue immediately (called for critical events)."""
    with _flush_lock:
        events = []
        while True:
            try:
                events.append(_queue.get_nowait())
            except Empty:
                break
        if events and not _post(events):
            _persist_pending(events)


def start():
    """Start the background flusher. Idempotent."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_flush_loop, daemon=True, name="telemetry-flush")
    t.start()
    track("telemetry_started", url_configured=bool(TELEMETRY_URL))


def track(event, **data):
    """Append an event. Critical events trigger an immediate flush."""
    ev = {
        "ts": time.time(),
        "event": event,
        **data,
    }
    try:
        _queue.put_nowait(ev)
    except Exception:
        pass

    if any(event.startswith(p) for p in _CRITICAL_PREFIXES):
        try:
            threading.Thread(target=_drain_immediate, daemon=True).start()
        except Exception:
            pass


def install_excepthook():
    """Capture uncaught exceptions as crash_unhandled events."""
    import sys, traceback
    prev = sys.excepthook
    def hook(exctype, value, tb):
        try:
            track("crash_unhandled",
                  type=exctype.__name__ if exctype else "?",
                  message=str(value),
                  trace="".join(traceback.format_exception(exctype, value, tb))[:4000])
            _drain_immediate()
        except Exception:
            pass
        if prev:
            prev(exctype, value, tb)
    sys.excepthook = hook
