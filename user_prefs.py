"""Persistent user preferences (address, phone) stored in app sandbox."""

import json
import os

try:
    from kivy.utils import platform as _platform
except ImportError:
    _platform = "unknown"


def _path():
    if _platform == "ios":
        d = os.path.join(os.path.expanduser("~"), "Documents")
    else:
        d = os.path.expanduser("~/.electriciansnow")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = "/tmp"
    return os.path.join(d, "user_prefs.json")


def load():
    try:
        with open(_path(), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    except Exception:
        return {}


def save(prefs):
    try:
        with open(_path(), "w") as f:
            json.dump(prefs, f)
    except Exception:
        pass


def update(**kwargs):
    """Merge keys into existing prefs."""
    prefs = load()
    prefs.update({k: v for k, v in kwargs.items() if v is not None})
    save(prefs)
    return prefs
