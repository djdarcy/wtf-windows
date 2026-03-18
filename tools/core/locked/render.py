"""Rich console rendering for wtf-locked diagnosis results.

Three-tier progressive disclosure (mirroring wtf-restarted):
  Tier 0 (Answer):      Header + lock info + verdict + concurrent login + AI
  Tier 1 (Evidence):    Evidence details + lock/unlock session timeline
  Tier 2 (Diagnostics): Policy settings, audit status, RDP events, power events

Output gating (THAC0 integration):
  Each render section is wrapped in emit() with a channel and level.
  -v/-Q/--show control what content populates sections.
  --tier controls which sections (template) are shown.
  -Q wins over --tier (if a channel is gated by verbosity, it's hidden
  even if the tier is selected).
"""

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from wtf_windows.lib.log_lib import get_output

console = Console()

# Lock verdict -> color and display label (security-first ordering)
VERDICT_STYLES = {
    "REMOTE_TAKEOVER":    ("bold red",    "REMOTE TAKEOVER"),
    "UNAUTHORIZED_LOGIN": ("red",         "UNAUTHORIZED LOGIN"),
    "SOFTWARE_LOCK":      ("yellow",      "SOFTWARE LOCK"),
    "RDP_SELF_RECONNECT": ("cyan",        "RDP SELF-RECONNECT"),
    "SCREENSAVER_LOCK":   ("green",       "SCREENSAVER LOCK"),
    "INACTIVITY_LOCK":    ("green",       "INACTIVITY LOCK"),
    "GROUP_POLICY_LOCK":  ("blue",        "GROUP POLICY LOCK"),
    "SLEEP_RESUME_LOCK":  ("dim",         "SLEEP/RESUME LOCK"),
    "MANUAL_LOCK":        ("dim green",   "MANUAL LOCK (Win+L)"),
    "UNKNOWN_LOCK":       ("white",       "UNKNOWN LOCK"),
}


def _wait_for_keypress(prompt="Press any key for more details..."):
    """Wait for a keypress in interactive mode. Returns the key pressed."""
    console.print(f"\n[dim]{prompt}[/dim]", end="")
    try:
        import msvcrt
        ch = msvcrt.getwch()
        console.print()
        if ch == "\x1b":
            return "q"
        return ch
    except ImportError:
        try:
            line = input()
            if line.strip().lower() == "q":
                return "q"
            return "\n"
        except (EOFError, KeyboardInterrupt):
            return "q"


def _is_interactive():
    """Check if stdout is a TTY (not piped/redirected)."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _has_tier1_content(sessions, data):
    """Check if there is Tier 1 (evidence) content to show."""
    out = get_output()
    if out.is_level_active(0, 'evidence') and sessions:
        for s in sessions:
            if s.evidence:
                return True
    if out.is_level_active(0, 'session') and len(sessions) > 1:
        return True
    return False


def _has_tier2_content(data):
    """Check if there is Tier 2 (diagnostics) content to show."""
    out = get_output()
    if out.is_level_active(0, 'policy'):
        ss = data.get("screensaver_config", {})
        if ss.get("ScreenSaveActive") == "1":
            return True
        if data.get("inactivity_timeout_secs", 0) > 0:
            return True
        if data.get("gpo_inactivity_limit", 0) > 0:
            return True
    if out.is_level_active(0, 'rdp') and data.get("rdp_events"):
        return True
    return False


# ---------------------------------------------------------------------------
# Tier 0: The Answer
# ---------------------------------------------------------------------------

def _render_tier0(sessions, data, ai_fetcher=None):
    """Render Tier 0: header, lock info, verdict, concurrent login, AI.

    Output gating:
      Header:           system/-2 (shown even at -QQ)
      Lock info:        session/-1
      Audit notice:     policy/-1
      Verdict:          verdict/-2
      Concurrent login: login/-1
      Security warning: hint/-2
      AI analysis:      ai/0
    """
    out = get_output()
    audit_enabled = data.get("audit_policy_enabled", False)

    # Header
    out.emit(-2, channel='verdict', render=lambda: (
        console.print(),
        console.print(Panel.fit(
            "[bold]WTF-LOCKED[/bold] -- Last Lock Analysis",
            style="blue",
        )),
    ))

    # Lookback note (when window was auto-extended)
    extended = data.get("lookback_extended", False)
    actual_hours = data.get("lookback_actual_hours")
    requested_hours = data.get("lookback_hours", 720)
    strict = data.get("strict_lookback", False)

    if extended and not strict:
        out.emit(-1, channel='session', render=lambda: (
            console.print(
                f"  [dim]Looked back {actual_hours:.0f}h to cover last lock event "
                f"(default is {requested_hours}h). "
                f"Use --hours {requested_hours} for strict window.[/dim]"
            ),
        ))

    # Lock info table
    if sessions:
        latest = sessions[0]
        out.emit(-1, channel='session', render=lambda:
            _render_lock_info(latest, data))

    # Audit policy notice
    if not audit_enabled:
        source = "Winlogon" if data.get("winlogon_lock_count", 0) > 0 else "none"
        out.emit(-1, channel='policy', render=lambda: (
            console.print(f"  [dim]Using {source} events "
                          f"(enable audit policy for richer data)[/dim]"),
        ))

    # Verdict
    if sessions:
        latest = sessions[0]
        out.emit(-2, channel='verdict', render=lambda: (
            console.print(),
            _render_verdict(latest),
        ))
    else:
        out.emit(-2, channel='verdict', render=lambda: (
            console.print(),
            console.print("  [dim]No lock events found.[/dim]"),
        ))

    # AI analysis (lazy, after verdict is visible)
    if ai_fetcher:
        def _fetch_and_render_ai():
            ai_result = ai_fetcher()
            if ai_result and ai_result.get("success"):
                render_ai_analysis(
                    ai_result["sections"],
                    title="AI Analysis (based on lock evidence)",
                )
            elif ai_result and ai_result.get("error"):
                error = ai_result.get("error", "Unknown error")
                backend = ai_result.get("backend", "")
                if backend == "prompt-only":
                    print(f"\n{error}", file=sys.stderr)
                else:
                    print(f"\nAI analysis failed: {error}", file=sys.stderr)
        out.emit(0, channel='ai', render=_fetch_and_render_ai)


# ---------------------------------------------------------------------------
# Tier 1: Evidence
# ---------------------------------------------------------------------------

def _render_tier1(sessions, data):
    """Render Tier 1: evidence details + session timeline.

    Output gating:
      Evidence:    evidence/0
      Sessions:    session/0
    """
    out = get_output()

    # Evidence for each session
    for i, session in enumerate(sessions[:5]):
        if session.evidence:
            def _render_evidence(s=session, idx=i):
                if idx > 0:
                    console.print()
                console.print(f"  [bold]Lock at {_fmt_time(s.locked_at)}[/bold]"
                              f" -- {s.lock_cause}")
                for ev in s.evidence:
                    console.print(f"    - {ev}")
                if s.concurrent_login:
                    _render_login_detail(s.concurrent_login)
            out.emit(0, channel='evidence', render=_render_evidence)

    # Session timeline (if multiple sessions)
    if len(sessions) > 1:
        out.emit(0, channel='session', render=lambda:
            _render_session_table(sessions))


# ---------------------------------------------------------------------------
# Tier 2: Diagnostics
# ---------------------------------------------------------------------------

def _render_tier2(sessions, data, verbose=0):
    """Render Tier 2: policy settings, audit status, RDP events.

    Output gating:
      Policy settings: policy/0
      RDP events:      rdp/0
      Power events:    session/1 (verbose only)
    """
    out = get_output()

    # Policy settings
    out.emit(0, channel='policy', render=lambda:
        _render_policy_settings(data))

    # Audit policy status
    out.emit(0, channel='policy', render=lambda:
        _render_audit_status(data))

    # RDP events
    rdp_events = data.get("rdp_events", [])
    if rdp_events:
        out.emit(0, channel='rdp', render=lambda:
            _render_rdp_events(rdp_events))

    # Power events (verbose only)
    power_events = data.get("power_events", [])
    if power_events:
        out.emit(1, channel='session', render=lambda:
            _render_power_events(power_events))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_diagnosis(
    result,
    verbose=0,
    tiers=None,
    no_page=False,
    interactive=True,
    ai_fetcher=None,
):
    """Render lock diagnosis with three-tier progressive disclosure.

    Args:
        result: Investigation result dict (with 'sessions', 'raw', 'audit_enabled')
        verbose: Verbosity level
        tiers: Which tiers to show (None = all). List of 0, 1, 2.
        no_page: Disable interactive paging between tiers.
        interactive: Whether stdout is a TTY.
        ai_fetcher: Callable returning AI analysis result dict, or None.
    """
    sessions = result.get("sessions", [])
    data = result.get("raw", {})

    show_tiers = tiers if tiers is not None else [0, 1, 2]

    paging = (
        interactive
        and not no_page
        and len(show_tiers) > 1
    )

    tier_renderers = []

    if 0 in show_tiers:
        tier_renderers.append((
            0,
            lambda: _render_tier0(sessions, data, ai_fetcher=ai_fetcher),
            None,
        ))

    if 1 in show_tiers and sessions and _has_tier1_content(sessions, data):
        tier_renderers.append((
            1,
            lambda: _render_tier1(sessions, data),
            "Press any key for evidence details, q/Esc to quit...",
        ))

    if 2 in show_tiers and _has_tier2_content(data):
        tier_renderers.append((
            2,
            lambda: _render_tier2(sessions, data, verbose=verbose),
            "Press any key for full diagnostics, q/Esc to quit...",
        ))

    for i, (tier_num, render_fn, prompt) in enumerate(tier_renderers):
        if paging and i > 0 and prompt:
            key = _wait_for_keypress(prompt)
            if key.lower() == "q":
                console.print()
                return
        render_fn()

    # AI requested but tier 0 excluded
    if ai_fetcher and 0 not in show_tiers:
        ai_result = ai_fetcher()
        if ai_result and ai_result.get("success"):
            render_ai_analysis(ai_result["sections"])

    console.print()


def render_history(sessions, hours=720):
    """Render lock/unlock history timeline."""
    out = get_output()

    out.emit(-2, channel='history', render=lambda: (
        console.print(),
        console.print(Panel.fit(
            f"[bold]Lock History[/bold] -- Last {hours} hours "
            f"({len(sessions)} event{'s' if len(sessions) != 1 else ''})",
            style="blue",
        )),
    ))

    if not sessions:
        out.emit(-2, channel='history', render=lambda:
            console.print("  [dim]No lock events found.[/dim]"))
        return

    # History table
    def _render_history_table():
        from .engine.verdict import VERDICT_THREAT_LEVEL

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("", width=2)  # threat marker
        table.add_column("Locked At", width=19)
        table.add_column("Duration", width=10)
        table.add_column("Cause", width=22)
        table.add_column("Details")

        for session in sessions:
            threat = VERDICT_THREAT_LEVEL.get(session.lock_cause, 10)
            if threat <= 2:
                marker = "[bold red]!![/bold red]"
            elif threat <= 4:
                marker = "[yellow]![/yellow]"
            else:
                marker = " "

            duration = (f"{session.duration_minutes:.0f}min"
                        if session.duration_minutes else "[dim]ongoing[/dim]")

            color, label = VERDICT_STYLES.get(
                session.lock_cause, ("white", session.lock_cause))

            details = ""
            if session.concurrent_login:
                login = session.concurrent_login
                details = f"{login.domain}\\{login.user}"
                if login.source_ip and login.source_ip != "-":
                    details += f" from {login.source_ip}"

            table.add_row(
                marker,
                _fmt_time(session.locked_at),
                duration,
                f"[{color}]{label}[/{color}]",
                details,
            )

        console.print(table)

    out.emit(-2, channel='history', render=_render_history_table)


def render_ai_analysis(sections, title="AI Analysis"):
    """Render AI analysis sections in a Rich panel."""
    out = get_output()

    def _render():
        lines = []
        for key in ("what_happened", "why", "what_to_do"):
            content = sections.get(key)
            if content:
                label = key.replace("_", " ").title()
                lines.append(f"[bold]{label}:[/bold]")
                lines.append(content)
                lines.append("")

        confidence = sections.get("confidence", "")
        if confidence:
            conf_lower = confidence.lower()
            if "high" in conf_lower:
                style = "green"
            elif "medium" in conf_lower:
                style = "yellow"
            else:
                style = "red"
            lines.append(f"[bold]Confidence:[/bold] [{style}]{confidence}[/{style}]")

        if lines:
            console.print()
            console.print(Panel(
                "\n".join(lines),
                title=title,
                style="cyan",
            ))

    out.emit(0, channel='ai', render=_render)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _render_lock_info(session, data):
    """Render lock information table (Tier 0)."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("label", style="bold", width=18)
    table.add_column("value")

    table.add_row("Locked at:", _fmt_time(session.locked_at))
    if session.unlocked_at:
        table.add_row("Unlocked at:", _fmt_time(session.unlocked_at))
        if session.duration_minutes is not None:
            table.add_row("Duration:", f"{session.duration_minutes:.0f} minutes")
    else:
        table.add_row("Unlocked at:", "[dim]still locked or no unlock event[/dim]")

    source = "Security log" if data.get("security_lock_count", 0) > 0 else "Winlogon events"
    table.add_row("Data source:", source)

    console.print(table)


def _render_verdict(session):
    """Render the verdict panel with threat-level coloring."""
    from .engine.verdict import VERDICT_THREAT_LEVEL

    vtype = session.lock_cause
    color, label = VERDICT_STYLES.get(vtype, ("white", vtype))
    threat = VERDICT_THREAT_LEVEL.get(vtype, 10)

    # Threat indicator
    if threat <= 2:
        threat_text = "[bold red]SUSPICIOUS[/bold red]"
    elif threat <= 4:
        threat_text = "[yellow]NOTABLE[/yellow]"
    else:
        threat_text = "[green]NORMAL[/green]"

    lines = [f"[bold {color}]{label}[/bold {color}]"]
    lines.append(f"Threat: {threat_text}  |  Confidence: {session.confidence}")
    lines.append("")

    # Evidence
    for ev in session.evidence:
        lines.append(f"  - {ev}")

    panel = Panel(
        "\n".join(lines),
        title="Lock Verdict",
        border_style=color,
    )
    console.print(panel)

    # Concurrent login (shown immediately with verdict for suspicious locks)
    if session.concurrent_login:
        _render_login_panel(session.concurrent_login, threat)


def _render_login_panel(login, threat_level):
    """Render concurrent login details as a Rich panel."""
    out = get_output()

    def _render():
        lines = [f"[bold]User:[/bold]    {login.domain}\\{login.user}"]
        lines.append(f"[bold]Type:[/bold]    {login.logon_type_name}")
        if login.source_ip and login.source_ip != "-":
            source = login.source_ip
            if login.source_hostname and login.source_hostname != "-":
                source += f" ({login.source_hostname})"
            lines.append(f"[bold]Source:[/bold]  {source}")
        lines.append(f"[bold]Time:[/bold]    {_fmt_time(login.timestamp)}")

        style = "red" if threat_level <= 2 else "yellow" if threat_level <= 4 else "cyan"
        console.print(Panel(
            "\n".join(lines),
            title="Concurrent Login Detected",
            border_style=style,
        ))

        # Security guidance for suspicious locks
        if threat_level <= 2:
            console.print()
            console.print("[bold red]>> This lock may indicate unauthorized access.[/bold red]")
            console.print("[red]>> Check: Was this login expected? "
                          "Do you recognize the source IP?[/red]")
            console.print("[red]>> If not, investigate immediately "
                          "and consider changing passwords.[/red]")

    out.emit(-1, channel='login', render=_render)


def _render_login_detail(login):
    """Render login details inline (for Tier 1 evidence)."""
    lines = []
    lines.append(f"    Login: {login.domain}\\{login.user} "
                 f"({login.logon_type_name})")
    if login.source_ip and login.source_ip != "-":
        source = login.source_ip
        if login.source_hostname and login.source_hostname != "-":
            source += f" ({login.source_hostname})"
        lines.append(f"    Source: {source}")
    for line in lines:
        console.print(line)


def _render_session_table(sessions):
    """Render a table of all lock sessions."""
    from .engine.verdict import VERDICT_THREAT_LEVEL

    console.print()
    console.print("[bold]All Lock Sessions[/bold]")

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Locked At", width=19)
    table.add_column("Unlocked", width=19)
    table.add_column("Duration", width=10)
    table.add_column("Cause", width=20)

    for session in sessions[:20]:  # Cap at 20
        color, label = VERDICT_STYLES.get(
            session.lock_cause, ("white", session.lock_cause))

        unlock_str = (_fmt_time(session.unlocked_at)
                      if session.unlocked_at else "[dim]--[/dim]")
        duration = (f"{session.duration_minutes:.0f}min"
                    if session.duration_minutes else "[dim]--[/dim]")

        table.add_row(
            _fmt_time(session.locked_at),
            unlock_str,
            duration,
            f"[{color}]{label}[/{color}]",
        )

    console.print(table)
    if len(sessions) > 20:
        console.print(f"  [dim]... and {len(sessions) - 20} more[/dim]")


def _render_policy_settings(data):
    """Render registry/GPO policy settings."""
    console.print()
    console.print("[bold]Lock Policy Settings[/bold]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("setting", style="bold", width=22)
    table.add_column("value")

    ss = data.get("screensaver_config", {})
    ss_active = ss.get("ScreenSaveActive", "0")
    if ss_active == "1":
        timeout = ss.get("ScreenSaveTimeOut") or "not set"
        secure = "yes" if ss.get("ScreenSaverIsSecure") == "1" else "no"
        exe = ss.get("ScreenSaverExe", "")
        table.add_row("Screen saver:", f"Active (timeout: {timeout}s, lock on resume: {secure})")
        if exe:
            table.add_row("", f"[dim]{exe}[/dim]")
    else:
        table.add_row("Screen saver:", "[dim]Inactive[/dim]")

    if data.get("dynamic_lock_enabled"):
        table.add_row("Dynamic Lock:", "Enabled (Bluetooth)")
    else:
        table.add_row("Dynamic Lock:", "[dim]Disabled[/dim]")

    inactivity = data.get("inactivity_timeout_secs", 0)
    if inactivity > 0:
        table.add_row("Inactivity timeout:", f"{inactivity}s ({inactivity // 60} min)")
    else:
        table.add_row("Inactivity timeout:", "[dim]Not set[/dim]")

    gpo = data.get("gpo_inactivity_limit", 0)
    if gpo > 0:
        table.add_row("GPO inactivity:", f"{gpo}s ({gpo // 60} min)")
    else:
        table.add_row("GPO inactivity:", "[dim]Not set[/dim]")

    console.print(table)


def _render_audit_status(data):
    """Render audit policy status."""
    enabled = data.get("audit_policy_enabled", False)
    console.print()
    if enabled:
        console.print("  [green]Audit policy 'Other Logon/Logoff Events': Enabled[/green]")
    else:
        console.print("  [yellow]Audit policy 'Other Logon/Logoff Events': Not enabled[/yellow]")
        console.print('  [dim]Enable: auditpol /set /subcategory:"Other Logon/Logoff Events" /success:enable[/dim]')


def _render_rdp_events(rdp_events):
    """Render RDP session events."""
    console.print()
    console.print("[bold]RDP Session Events[/bold]")

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Time", width=19)
    table.add_column("Event", width=22)
    table.add_column("User")
    table.add_column("Source IP")

    for evt in rdp_events[:20]:
        table.add_row(
            _fmt_time_str(evt.get("time", "")),
            evt.get("event_type", f"ID {evt.get('event_id', '?')}"),
            evt.get("user", ""),
            evt.get("source_ip", ""),
        )

    console.print(table)


def _render_power_events(power_events):
    """Render power/sleep events (verbose only)."""
    console.print()
    console.print("[bold]Power Events[/bold]")

    for evt in power_events[:10]:
        time_str = _fmt_time_str(evt.get("time", ""))
        msg = evt.get("message", "")
        console.print(f"  [{time_str}] {msg}")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _fmt_time(dt):
    """Format a datetime for display."""
    from datetime import datetime
    if not dt or dt == datetime.min:
        return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_time_str(time_str):
    """Format an ISO time string for display."""
    if not time_str:
        return "unknown"
    # Strip timezone and fractional seconds for display
    clean = time_str.split(".")[0].split("+")[0].rstrip("Z")
    return clean.replace("T", " ")
