"""Lock investigation orchestrator.

Calls investigate_locks.ps1 via the shared PowerShell runner,
then builds LockSession objects with verdicts.

Lock-anchored lookback (parallel to wtf-restarted's boot-anchored lookback):
  Default: auto-extends past the --hours window to cover the most recent lock
  Explicit --hours: strict time-slice (user asked for exactly this window)
"""

from pathlib import Path

from wtf_windows.lib.ps1.runner import run_ps1
from .verdict import build_sessions

# PS1 scripts are in this tool's ps1/ directory
_PS1_DIR = Path(__file__).parent.parent / "ps1"


def run_investigation(hours=720, strict_lookback=False, verbose=False):
    """Run the lock investigation.

    Args:
        hours: How far back to look in the event log (default: 30 days)
        strict_lookback: If True, use exact time window (user passed --hours).
            If False, auto-extend to cover the most recent lock event.
        verbose: Print debug info

    Returns:
        dict with:
            raw: Full data dict from PowerShell
            sessions: List of LockSession objects
            audit_enabled: Whether the audit policy is active
            error: Error string or None
    """
    params = {"Hours": hours}
    if strict_lookback:
        params["StrictLookback"] = True

    data = run_ps1(
        "investigate_locks.ps1",
        _PS1_DIR,
        timeout=60,
        verbose=verbose,
        **params,
    )

    if "error" in data:
        return {
            "raw": data,
            "sessions": [],
            "audit_enabled": False,
            "error": data["error"],
        }

    audit_enabled = data.get("audit_policy_enabled", False)

    # Coerce event fields to lists -- PowerShell's ConvertTo-Json
    # unwraps single-element arrays into scalars (a dict instead of
    # a list of one dict). This is a known serialization quirk.
    for key in ("lock_events", "unlock_events", "screensaver_events",
                "login_events", "rdp_events", "power_events"):
        val = data.get(key, [])
        if isinstance(val, dict):
            data[key] = [val]
        elif not isinstance(val, list):
            data[key] = []

    lock_events = data.get("lock_events", [])
    unlock_events = data.get("unlock_events", [])

    sessions = []
    if lock_events:
        sessions = build_sessions(lock_events, unlock_events, data)

    return {
        "raw": data,
        "sessions": sessions,
        "audit_enabled": audit_enabled,
        "error": None,
    }
