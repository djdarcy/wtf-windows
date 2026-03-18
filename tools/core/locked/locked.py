"""wtf-locked: Why did my Windows PC lock?

Diagnoses lock causes by analyzing Windows Security log events,
registry settings, and session activity. Identifies who logged in
and from where when a remote session displaced the console.
"""

import argparse
import sys
from datetime import datetime

from wtf_windows.lib.ps1.runner import is_admin


def _init_thac0(verbosity, channels=None):
    """Initialize the THAC0 output system with wtf-locked channels.

    Args:
        verbosity: Computed verbosity level (verbose - quiet).
        channels: List of --show channel specs (e.g., ['session:2', 'trace:1']).
    """
    from wtf_windows.lib.log_lib import init_output
    from wtf_windows.lib.log_lib.channels import KNOWN_CHANNELS, CHANNEL_DESCRIPTIONS, OPT_IN_CHANNELS
    from .channels import (
        CHANNELS as APP_CHANNELS,
        CHANNEL_DESCRIPTIONS as APP_DESCRIPTIONS,
        OPT_IN_CHANNELS as APP_OPT_IN,
    )

    # Merge app channels into the library's known set
    KNOWN_CHANNELS.clear()
    KNOWN_CHANNELS.update(APP_CHANNELS)
    CHANNEL_DESCRIPTIONS.clear()
    CHANNEL_DESCRIPTIONS.update(APP_DESCRIPTIONS)
    OPT_IN_CHANNELS.clear()
    OPT_IN_CHANNELS.update(APP_OPT_IN)

    init_output(
        verbosity=verbosity,
        channels=channels,
        known_channels=APP_CHANNELS,
    )


def main(argv=None):
    """Entry point for wtf locked."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="wtf-locked",
        description=(
            "Why did my Windows PC lock? Analyzes Security log events, "
            "registry settings, and session activity to determine lock causes."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["diagnose", "history"],
        default="diagnose",
        help="Command to run (default: diagnose)",
    )
    parser.add_argument(
        "--hours", type=int, default=720, metavar="N",
        help="Hours to look back in event log (default: 720 = 30 days)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON data",
    )
    parser.add_argument(
        "--verbose", "-v", action="count", default=0,
        help="Increase verbosity (-v, -vv)",
    )
    parser.add_argument(
        "--quiet", "-Q", action="count", default=0,
        help="Decrease verbosity (-Q, -QQ)",
    )
    parser.add_argument(
        "--show", action="append", default=[], metavar="CHANNEL:LEVEL",
        help="Set per-channel verbosity (repeatable)",
    )
    parser.add_argument(
        "--version", action="version",
        version="wtf-locked 0.1.0-alpha",
    )

    args = parser.parse_args(argv)
    args.verbose = args.verbose - args.quiet

    # Initialize THAC0 output system
    _init_thac0(args.verbose, channels=args.show)

    # Admin check -- Security log requires elevation
    if sys.platform == "win32" and not is_admin():
        from wtf_windows.lib.log_lib import get_output
        out = get_output()
        out.emit(-2, "wtf-locked requires administrator privileges.", channel="error")
        out.emit(-2, "", channel="error")
        out.emit(-2, "The Security event log (where lock/unlock events live) requires", channel="error")
        out.emit(-2, "elevated access. Please run from an administrator terminal:", channel="error")
        out.emit(-2, "", channel="error")
        out.emit(-2, "  Right-click terminal -> Run as administrator", channel="error")
        out.emit(-2, "  Then: wtf locked", channel="error")
        return 1

    if args.command == "history":
        return _cmd_history(args)
    else:
        return _cmd_diagnose(args)


def _cmd_diagnose(args):
    """Diagnose the most recent lock event."""
    from wtf_windows.lib.log_lib import get_output
    from .engine.investigator import run_investigation

    out = get_output()

    result = run_investigation(hours=args.hours, verbose=args.verbose > 0)

    if args.json:
        import json
        output = result["raw"]
        output["sessions"] = [_session_to_dict(s) for s in result["sessions"]]
        print(json.dumps(output, indent=2, default=str))
        return 0

    if result.get("error"):
        out.emit(-2, f"Error: {result['error']}", channel="error")
        return 1

    sessions = result["sessions"]

    # Note audit policy status (but don't stop -- Winlogon events are always available)
    if not result["audit_enabled"]:
        _show_audit_notice(out, has_events=len(sessions) > 0)

    if not sessions:
        out.emit(-2, f"No lock events found in the last {args.hours} hours.", channel="verdict")
        _show_policy_summary(result["raw"], out)
        return 0

    # Show the most recent lock
    latest = sessions[0]
    _render_verdict(latest, out)

    # Show count of other locks
    if len(sessions) > 1:
        out.emit(0, f"\n  ({len(sessions) - 1} other lock event(s) in the last {args.hours} hours"
                 " -- use 'wtf locked history' to see all)", channel="hint")

    return 0


def _cmd_history(args):
    """Show lock/unlock timeline."""
    from wtf_windows.lib.log_lib import get_output
    from .engine.investigator import run_investigation

    out = get_output()

    result = run_investigation(hours=args.hours, verbose=args.verbose > 0)

    if args.json:
        import json
        output = result["raw"]
        output["sessions"] = [_session_to_dict(s) for s in result["sessions"]]
        print(json.dumps(output, indent=2, default=str))
        return 0

    if result.get("error"):
        out.emit(-2, f"Error: {result['error']}", channel="error")
        return 1

    sessions = result["sessions"]

    if not result["audit_enabled"]:
        _show_audit_notice(out, has_events=len(sessions) > 0)

    if not sessions:
        out.emit(-2, f"No lock events found in the last {args.hours} hours.", channel="history")
        _show_policy_summary(result["raw"], out)
        return 0

    out.emit(-2, f"\n  Lock History -- Last {args.hours} hours ({len(sessions)} events)", channel="history")
    out.emit(-2, "  " + "-" * 70, channel="history")

    for session in sessions:
        _render_history_row(session, out, args.verbose)

    return 0


def _render_verdict(session, out):
    """Render a lock verdict to the console via THAC0 channels."""
    from .engine.verdict import VERDICT_THREAT_LEVEL

    threat = VERDICT_THREAT_LEVEL.get(session.lock_cause, 10)

    # Severity indicator
    if threat <= 2:
        severity = "[!!]"
        label = "SUSPICIOUS"
    elif threat <= 4:
        severity = "[!]"
        label = "NOTABLE"
    else:
        severity = "[.]"
        label = "NORMAL"

    out.emit(-2, f"\n  {severity} {session.lock_cause}  ({label}, confidence: {session.confidence})",
             channel="verdict")
    out.emit(-2, f"  Locked at: {_fmt_time(session.locked_at)}", channel="session")

    if session.unlocked_at:
        out.emit(-2, f"  Unlocked:  {_fmt_time(session.unlocked_at)}"
                 f"  (duration: {session.duration_minutes:.0f} min)", channel="session")
    else:
        out.emit(-2, "  Unlocked:  (still locked or no unlock event)", channel="session")

    # Evidence
    if session.evidence:
        out.emit(0, "", channel="evidence")
        for line in session.evidence:
            out.emit(0, f"    - {line}", channel="evidence")

    # Concurrent login details (the key "who did this?" info)
    login = session.concurrent_login
    if login:
        out.emit(-1, "", channel="login")
        out.emit(-1, "  Concurrent login detected:", channel="login")
        out.emit(-1, f"    User:    {login.domain}\\{login.user}", channel="login")
        out.emit(-1, f"    Type:    {login.logon_type_name}", channel="login")
        if login.source_ip and login.source_ip != "-":
            source_line = f"    Source:  {login.source_ip}"
            if login.source_hostname and login.source_hostname != "-":
                source_line += f" ({login.source_hostname})"
            out.emit(-1, source_line, channel="login")
        out.emit(-1, f"    Time:    {_fmt_time(login.timestamp)}", channel="login")

    # Guidance for suspicious locks
    if threat <= 2:
        out.emit(-2, "", channel="hint")
        out.emit(-2, "  >> This lock may indicate unauthorized access.", channel="hint")
        out.emit(-2, "  >> Check: Was this login expected? Do you recognize the source IP?", channel="hint")
        out.emit(-2, "  >> If not, investigate immediately and consider changing passwords.", channel="hint")


def _render_history_row(session, out, verbose=0):
    """Render one row in the history timeline."""
    from .engine.verdict import VERDICT_THREAT_LEVEL

    threat = VERDICT_THREAT_LEVEL.get(session.lock_cause, 10)
    if threat <= 2:
        marker = "!!"
    elif threat <= 4:
        marker = "! "
    else:
        marker = "  "

    duration_str = f"{session.duration_minutes:.0f}min" if session.duration_minutes else "ongoing"

    line = (f"  {marker} {_fmt_time(session.locked_at)}  "
            f"{session.lock_cause:<22}  {duration_str:<10}")

    # Add concurrent login info if present
    if session.concurrent_login:
        login = session.concurrent_login
        source = login.source_ip or ""
        line += f"  {login.domain}\\{login.user}"
        if source and source != "-":
            line += f" from {source}"

    out.emit(-2, line, channel="history")

    # Show evidence in verbose mode
    if verbose > 0 and session.evidence:
        for ev in session.evidence:
            out.emit(1, f"       {ev}", channel="evidence")


def _show_audit_notice(out, has_events=False):
    """Show a note about audit policy status (but don't stop processing).

    The tool always continues -- Winlogon events are available without
    the audit policy. This notice just informs the user that richer
    data is available if they enable it.
    """
    out.emit(0, "", channel="policy")
    if has_events:
        out.emit(0, "  Note: Using Winlogon events (audit policy not enabled).", channel="policy")
        out.emit(0, "  Enable audit policy for richer data (user SID, session ID):", channel="hint")
    else:
        out.emit(-2, "  Note: Audit policy 'Other Logon/Logoff Events' is not enabled.", channel="policy")
        out.emit(-2, "  Enable for detailed lock/unlock tracking:", channel="hint")
    out.emit(0, '    auditpol /set /subcategory:"Other Logon/Logoff Events" /success:enable', channel="hint")
    out.emit(0, "", channel="policy")


def _show_policy_summary(data, out):
    """Show registry/GPO settings as context when no lock events are found."""
    out.emit(0, "", channel="policy")
    out.emit(0, "  Lock-related settings:", channel="policy")

    ss = data.get("screensaver_config", {})
    ss_active = ss.get("ScreenSaveActive", "0")
    if ss_active == "1":
        timeout = ss.get("ScreenSaveTimeOut") or "not set"
        secure = "yes" if ss.get("ScreenSaverIsSecure") == "1" else "no"
        out.emit(0, f"    Screen saver:       Active (timeout: {timeout}s, lock on resume: {secure})",
                 channel="policy")
    else:
        out.emit(0, "    Screen saver:       Inactive", channel="policy")

    if data.get("dynamic_lock_enabled"):
        out.emit(0, "    Dynamic Lock:       Enabled (Bluetooth)", channel="policy")

    inactivity = data.get("inactivity_timeout_secs", 0)
    if inactivity > 0:
        out.emit(0, f"    Inactivity timeout: {inactivity}s ({inactivity // 60} min)", channel="policy")
    else:
        out.emit(0, "    Inactivity timeout: Not set", channel="policy")

    gpo = data.get("gpo_inactivity_limit", 0)
    if gpo > 0:
        out.emit(0, f"    GPO inactivity:     {gpo}s ({gpo // 60} min)", channel="policy")
    else:
        out.emit(0, "    GPO inactivity:     Not set", channel="policy")


def _session_to_dict(session):
    """Convert a LockSession to a JSON-serializable dict."""
    d = {
        "locked_at": str(session.locked_at),
        "unlocked_at": str(session.unlocked_at) if session.unlocked_at else None,
        "duration_minutes": session.duration_minutes,
        "lock_cause": session.lock_cause,
        "confidence": session.confidence,
        "evidence": session.evidence,
    }
    if session.concurrent_login:
        login = session.concurrent_login
        d["concurrent_login"] = {
            "user": login.user,
            "domain": login.domain,
            "source_ip": login.source_ip,
            "source_hostname": login.source_hostname,
            "logon_type": login.logon_type,
            "logon_type_name": login.logon_type_name,
            "timestamp": str(login.timestamp),
        }
    return d


def _fmt_time(dt):
    """Format a datetime for display."""
    if not dt or dt == datetime.min:
        return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    sys.exit(main())
