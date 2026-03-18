"""wtf-locked: Why did my Windows PC lock?

Diagnoses lock causes by analyzing Windows Security log events,
registry settings, and session activity. Identifies who logged in
and from where when a remote session displaced the console.

Architecture (mirrors wtf-restarted):
  PS1 engine (investigate_locks.ps1) does event collection + JSON output
  Python wraps: CLI parsing, Rich rendering, AI orchestration, THAC0 gating
"""

import argparse
import json
import sys

from wtf_windows.lib.ps1.runner import is_admin


def _init_thac0(verbosity, channels=None):
    """Initialize the THAC0 output system with wtf-locked channels."""
    from wtf_windows.lib.log_lib import init_output
    from wtf_windows.lib.log_lib.channels import (
        KNOWN_CHANNELS, CHANNEL_DESCRIPTIONS, OPT_IN_CHANNELS,
    )
    from .channels import (
        CHANNELS as APP_CHANNELS,
        CHANNEL_DESCRIPTIONS as APP_DESCRIPTIONS,
        OPT_IN_CHANNELS as APP_OPT_IN,
    )

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
        strict_channels=True,
    )


def parse_tier_spec(tier_str):
    """Parse --tier flag value into a sorted list of tier numbers."""
    if tier_str.lower() == "all":
        return [0, 1, 2]
    tiers = set()
    for part in tier_str.split(","):
        part = part.strip()
        try:
            t = int(part)
        except ValueError:
            raise ValueError(
                f"invalid tier '{part}': must be 0, 1, 2, or 'all'"
            )
        if t not in (0, 1, 2):
            raise ValueError(
                f"invalid tier {t}: must be 0, 1, or 2"
            )
        tiers.add(t)
    return sorted(tiers)


def build_parser():
    """Build the argument parser for wtf-locked."""
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
        "--json", dest="json_output", action="store_true",
        help="Output raw JSON data",
    )
    parser.add_argument(
        "--tier", "-t", metavar="TIERS",
        help="Which tiers to show: 0, 1, 2, comma-separated, or 'all'",
    )
    parser.add_argument(
        "--no-page", "-np", action="store_true",
        help="Disable interactive paging between tiers",
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
        "--ai", nargs="?", const="claude", default=None, metavar="BACKEND",
        help="Run AI analysis (default backend: claude)",
    )
    parser.add_argument(
        "--ai-only", nargs="?", const="claude", default=None, metavar="BACKEND",
        help="Show only the AI analysis (skip normal output)",
    )
    parser.add_argument(
        "--ai-verbose", action="store_true",
        help="Stream AI output in real-time",
    )
    parser.add_argument(
        "--ai-refresh", action="store_true",
        help="Bypass AI cache and re-run analysis",
    )
    parser.add_argument(
        "--version", action="version",
        version="wtf-locked 0.1.0-alpha",
    )
    return parser


def _hours_explicit(argv):
    """Check if --hours was explicitly passed on the command line."""
    return any(a in ("--hours",) or a.startswith("--hours=") for a in argv)


def main(argv=None):
    """Entry point for wtf locked."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    # Compute verbosity
    args.verbose = args.verbose - args.quiet

    # Initialize THAC0
    _init_thac0(args.verbose, channels=args.show)

    # Parse --tier
    if args.tier is not None:
        try:
            args.tiers = parse_tier_spec(args.tier)
        except ValueError as e:
            parser.error(str(e))
    else:
        args.tiers = None

    # Admin check -- Security log requires elevation
    if sys.platform == "win32" and not is_admin():
        print("Error: wtf-locked requires administrator privileges.", file=sys.stderr)
        print("", file=sys.stderr)
        print("The Security event log requires elevated access.", file=sys.stderr)
        print("Run from an administrator terminal:", file=sys.stderr)
        print("  Right-click terminal -> Run as administrator", file=sys.stderr)
        print("  Then: wtf locked", file=sys.stderr)
        return 1

    # Detect if --hours was explicitly passed (strict time-slice vs lock-anchored)
    hours_explicit = _hours_explicit(argv)

    if args.command == "history":
        return _cmd_history(args, hours_explicit)
    else:
        return _cmd_diagnose(args, hours_explicit)


def _cmd_diagnose(args, hours_explicit=False):
    """Run full lock diagnosis."""
    from .engine.investigator import run_investigation
    from . import render

    # --ai-only implies --ai
    if args.ai_only is not None:
        if not args.ai:
            args.ai = args.ai_only

    # Run investigation (with spinner for interactive terminals)
    interactive = sys.stdout.isatty() and not args.json_output
    if interactive:
        from rich.console import Console
        console = Console(stderr=True)
        with console.status("[bold blue]Reading event logs...[/bold blue]"):
            result = run_investigation(
                hours=args.hours,
                strict_lookback=hours_explicit,
                verbose=args.verbose > 0,
            )
    else:
        result = run_investigation(
            hours=args.hours,
            strict_lookback=hours_explicit,
            verbose=args.verbose > 0,
        )

    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1

    # Build AI fetcher callback (lazy -- called after verdict is visible)
    ai_fetcher = None
    if args.ai:
        ai_fetcher = lambda: _get_ai_sections(args, result)

    # Standard output (unless --ai-only)
    if not args.ai_only:
        if args.json_output:
            ai_result = ai_fetcher() if ai_fetcher else None
            output = result["raw"]
            output["sessions"] = [_session_to_dict(s) for s in result["sessions"]]
            if ai_result:
                output["ai_analysis"] = ai_result
            print(json.dumps(output, indent=2, default=str))
            return 0
        else:
            render.render_diagnosis(
                result,
                verbose=args.verbose,
                tiers=args.tiers,
                no_page=args.no_page,
                interactive=interactive,
                ai_fetcher=ai_fetcher,
            )
            return 0

    # --ai-only mode
    if args.ai_only and ai_fetcher:
        ai_result = ai_fetcher()
        if not ai_result:
            return 1
        if args.json_output:
            output = result["raw"]
            output["ai_analysis"] = ai_result
            print(json.dumps(output, indent=2, default=str))
        elif ai_result.get("success"):
            render.render_ai_analysis(ai_result["sections"])
        else:
            error = ai_result.get("error", "Unknown error")
            print(f"\nAI analysis failed: {error}", file=sys.stderr)

    return 0


def _cmd_history(args, hours_explicit=False):
    """Show lock/unlock timeline."""
    from .engine.investigator import run_investigation
    from . import render

    # Run investigation (with spinner)
    interactive = sys.stdout.isatty() and not args.json_output
    if interactive:
        from rich.console import Console
        console = Console(stderr=True)
        with console.status("[bold blue]Reading event logs...[/bold blue]"):
            result = run_investigation(
                hours=args.hours,
                strict_lookback=hours_explicit,
                verbose=args.verbose > 0,
            )
    else:
        result = run_investigation(
            hours=args.hours,
            strict_lookback=hours_explicit,
            verbose=args.verbose > 0,
        )

    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1

    sessions = result["sessions"]

    if args.json_output:
        output = result["raw"]
        output["sessions"] = [_session_to_dict(s) for s in sessions]
        print(json.dumps(output, indent=2, default=str))
        return 0

    render.render_history(sessions, hours=args.hours)
    return 0


def _get_ai_sections(args, result):
    """Run AI analysis and return the result dict (does not render)."""
    from pathlib import Path
    from wtf_windows.lib.ai.analyzer import analyze, check_available

    backend = args.ai

    if not check_available(backend):
        if backend == "claude":
            print(
                "\nAI analysis unavailable: Claude Code CLI not found.\n"
                "Install from https://claude.ai/claude-code\n"
                "Or use --ai prompt-only to save the prompt for manual use.",
                file=sys.stderr,
            )
        else:
            print(
                f"\nAI analysis unavailable: backend '{backend}' not found.",
                file=sys.stderr,
            )
        if args.ai_only:
            sys.exit(1)
        return None

    # Lock-specific fingerprint for AI cache key
    def _fingerprint(results):
        fp = {}
        lock_events = results.get("lock_events", [])
        fp["lock_count"] = len(lock_events)
        fp["lock_times"] = sorted(e.get("time", "") for e in lock_events)
        fp["audit_enabled"] = results.get("audit_policy_enabled", False)
        login_events = results.get("login_events", [])
        fp["login_count"] = len(login_events)
        fp["login_times"] = sorted(e.get("time", "") for e in login_events)
        return fp

    # Prompt template path
    prompt_dir = Path(__file__).parent / "prompts"
    prompt_path = prompt_dir / "diagnose.md"
    if not prompt_path.exists():
        print("Warning: AI prompt template not found, using raw evidence.",
              file=sys.stderr)
        return None

    cache_dir = Path.home() / ".wtf-locked" / "cache"

    if not args.ai_verbose and not args.json_output:
        if args.ai_refresh:
            print("  Refreshing AI analysis...", file=sys.stderr)
        else:
            print("  Running AI analysis...", file=sys.stderr)

    return analyze(
        results=result["raw"],
        fingerprint_fn=_fingerprint,
        prompt_path=prompt_path,
        cache_dir=cache_dir,
        tool_name="locked",
        backend_name=backend,
        verbose=args.ai_verbose,
        timeout=120,
        refresh=args.ai_refresh,
    )


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


if __name__ == "__main__":
    sys.exit(main())
