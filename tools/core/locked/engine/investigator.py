"""Lock investigation orchestrator.

Calls investigate_locks.ps1 via the shared PowerShell runner,
then builds LockSession objects with verdicts.
"""

from pathlib import Path

from wtf_windows.lib.ps1.runner import run_ps1
from .verdict import build_sessions

# PS1 scripts are in this tool's ps1/ directory
_PS1_DIR = Path(__file__).parent.parent / "ps1"


def run_investigation(hours=720, verbose=False):
    """Run the lock investigation.

    Args:
        hours: How far back to look in the event log (default: 30 days)
        verbose: Print debug info

    Returns:
        dict with:
            raw: Full data dict from PowerShell
            sessions: List of LockSession objects
            audit_enabled: Whether the audit policy is active
    """
    data = run_ps1(
        "investigate_locks.ps1",
        _PS1_DIR,
        timeout=60,
        verbose=verbose,
        Hours=hours,
    )

    if "error" in data:
        return {
            "raw": data,
            "sessions": [],
            "audit_enabled": False,
            "error": data["error"],
        }

    audit_enabled = data.get("audit_policy_enabled", False)

    # Build lock sessions from events
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
