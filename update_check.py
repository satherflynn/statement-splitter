"""
Ask GitHub whether a newer release exists.

Runs on a background thread when the app opens. Any problem (offline, GitHub
down, rate-limited, odd JSON) is swallowed — the app must never nag or fail
because of an update check. Returns (version_string, download_page_url) when
a newer release is out, else None.
"""
from __future__ import annotations

import json
import re
import urllib.request

from version import APP_VERSION

REPO = "satherflynn/statement-splitter"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
TIMEOUT_SECONDS = 4


def _as_tuple(version: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Non-numeric bits are ignored."""
    nums = re.findall(r"\d+", version)
    return tuple(int(n) for n in nums) or (0,)


def newer_release() -> tuple[str, str] | None:
    try:
        req = urllib.request.Request(
            API_URL,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"StatementSplitter/{APP_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name") or "")
        page = str(data.get("html_url") or RELEASES_URL)
        if tag and _as_tuple(tag) > _as_tuple(APP_VERSION):
            return tag.lstrip("vV"), page
    except Exception:
        pass
    return None
