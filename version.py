"""Version stamp shown in the app window.

APP_VERSION is bumped by hand (and CHANGELOG.md gets a matching entry). The
build date is read from the program files themselves so it can never go
stale — handy for a non-technical user asking "is this the new one?".
"""
from datetime import datetime
from pathlib import Path
import os

APP_NAME = "Statement Splitter"
APP_VERSION = "1.1"


def resource_base() -> Path:
    """Folder holding bundled files: the .app's Resources, or this folder."""
    rp = os.environ.get("RESOURCEPATH")
    if rp:
        return Path(rp)
    return Path(__file__).resolve().parent


def running_from() -> str:
    return "app" if os.environ.get("RESOURCEPATH") else "source"


def build_date() -> str:
    base = resource_base()
    stamps = []
    for z in base.glob("lib/python*/site-packages.zip"):
        try:
            stamps.append(z.stat().st_mtime)
        except OSError:
            pass
    for py in base.glob("*.py"):
        try:
            stamps.append(py.stat().st_mtime)
        except OSError:
            pass
    if not stamps:
        return ""
    d = datetime.fromtimestamp(max(stamps))
    try:
        return d.strftime("%b %-d, %Y")
    except ValueError:
        return d.strftime("%b %d, %Y")


def version_line() -> str:
    parts = [f"Version {APP_VERSION}"]
    if build_date():
        parts.append(f"built {build_date()}")
    if running_from() == "source":
        parts.append("running from source")
    return "  ·  ".join(parts)
