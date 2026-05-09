"""Persistent file logger for diagnostic information.

Writes structured JSON-lines to the app's writable directory so logs
survive app restarts and can be viewed inside the app via the Logs
screen. Each event includes a timestamp, category, and free-form data.
"""

import json
import os
import time
import traceback
from datetime import datetime

try:
    from kivy.logger import Logger as _KivyLogger
    from kivy.utils import platform as _platform
except ImportError:
    _KivyLogger = None
    _platform = "unknown"


def _log_path():
    """Resolve a writable log file path on iOS / desktop."""
    if _platform == "ios":
        # iOS app sandbox - Documents directory is the only writable space
        # exposed to user (and to file viewers if the app enables it later).
        home = os.path.expanduser("~")
        d = os.path.join(home, "Documents")
    else:
        d = os.path.expanduser("~/.electriciansnow")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = "/tmp"
    return os.path.join(d, "diagnostic.log")


LOG_PATH = _log_path()
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB rolling log


def _rotate_if_needed():
    try:
        if os.path.getsize(LOG_PATH) > _MAX_BYTES:
            os.rename(LOG_PATH, LOG_PATH + ".prev")
    except FileNotFoundError:
        pass
    except Exception:
        pass


def log(category, message, **data):
    """Append a structured event to disk and Kivy logger."""
    event = {
        "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
        "category": category,
        "message": message,
    }
    if data:
        # Redact common secrets even if a caller forgets
        safe = {}
        for k, v in data.items():
            if isinstance(v, str) and ("apik_" in v or "Bearer " in v):
                safe[k] = v[:12] + "...REDACTED"
            else:
                safe[k] = v
        event["data"] = safe

    if _KivyLogger:
        try:
            _KivyLogger.info(f"DIAG | {category} | {message} | {event.get('data', '')}")
        except Exception:
            pass

    try:
        _rotate_if_needed()
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass


def log_exception(category, message, exc):
    log(category, message, error=str(exc), trace=traceback.format_exc())


def read_recent(max_lines=200):
    """Return the last N lines of log for in-app display."""
    try:
        with open(LOG_PATH, "r") as f:
            lines = f.readlines()
        return lines[-max_lines:]
    except FileNotFoundError:
        return ["(no log entries yet)\n"]
    except Exception as e:
        return [f"(error reading log: {e})\n"]


def clear():
    try:
        os.remove(LOG_PATH)
    except FileNotFoundError:
        pass
    except Exception:
        pass
