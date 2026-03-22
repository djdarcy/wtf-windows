# wtf locked

Why did my Windows PC lock? Diagnoses lock causes, identifies who logged in, and flags suspicious session takeovers.

**Status:** Embedded (lives in wtf-windows, will graduate to standalone)
**Requires:** Administrator privileges (Security event log access)

## Quick Start

```bash
# Basic diagnosis -- what caused the last lock?
wtf locked

# Lock/unlock history timeline
wtf locked history

# With AI-enhanced analysis
wtf locked --ai

# Last 24 hours only
wtf locked --hours 24

# Just the verdict (no evidence/diagnostics)
wtf locked --tier 0
```

## Usage

```
wtf locked [command] [options]
```

### Commands

| Command | Description |
|---------|-------------|
| `diagnose` | Analyze last lock event (default) |
| `history` | Show lock/unlock timeline with verdicts |

### Key Flags

| Flag | Description |
|------|-------------|
| `--hours N` | Lookback window in hours (default: 720 = 30 days, auto-extends to cover last lock) |
| `--ai [BACKEND]` | Run AI analysis (backends: claude, codex, prompt-only) |
| `--ai-only [BACKEND]` | Show only the AI analysis |
| `--tier TIERS` | Which tiers to show: 0, 1, 2, or all |
| `--no-page` | Disable interactive paging between tiers |
| `-v` / `-Q` | Increase / decrease verbosity |
| `--show CHANNEL:LEVEL` | Per-channel verbosity override |
| `--json` | Output raw JSON |

### Tiered Disclosure

| Tier | Content |
|------|---------|
| 0 (Answer) | Header, lock info, verdict panel with threat level, concurrent login details, AI analysis |
| 1 (Evidence) | Evidence per session, all lock sessions table |
| 2 (Diagnostics) | Policy settings (screensaver, GPO, inactivity timeout), audit status, RDP events, power events |

## Verdicts

Ordered by threat level (most suspicious first):

| Verdict | Threat | Color | Meaning |
|---------|--------|-------|---------|
| REMOTE_TAKEOVER | High | Red | Unknown user/IP connected via RDP, displacing console session |
| UNAUTHORIZED_LOGIN | High | Red | Different user account logged in |
| SOFTWARE_LOCK | Medium | Yellow | A process called LockWorkStation() |
| RDP_SELF_RECONNECT | Notable | Cyan | Own account reconnected from another machine via RDP |
| SCREENSAVER_LOCK | Normal | Green | Screen saver triggered with lock-on-resume enabled |
| INACTIVITY_LOCK | Normal | Green | Machine inactivity timeout elapsed |
| GROUP_POLICY_LOCK | Normal | Blue | GPO-enforced machine lock |
| SLEEP_RESUME_LOCK | Normal | Dim | Machine slept, login required on wake |
| MANUAL_LOCK | Normal | Dim green | User pressed Win+L (intentional) |
| UNKNOWN_LOCK | Unknown | White | No automated trigger detected |

### Security Warnings

For high-threat verdicts (REMOTE_TAKEOVER, UNAUTHORIZED_LOGIN), the tool displays:
- The concurrent login details (user, domain, source IP, hostname, authentication type)
- A security warning with recommended actions (investigate, check the source IP, change passwords)

## Event Sources

The tool queries multiple event logs, prioritizing always-available sources:

| Source | Log | Events | Requires Audit? |
|--------|-----|--------|-----------------|
| Winlogon lock/unlock | `Microsoft-Windows-Winlogon/Operational` | Type 7 (lock), 8 (unlock), 4 (RDP disconnect) | No |
| Security lock/unlock | `Security` | 4800, 4801 | Yes |
| Screen saver | `Security` | 4802, 4803 | Yes |
| Logon events | `Security` | 4624 (logon type 2/10/11) | No |
| RDP sessions | `TerminalServices-LocalSessionManager/Operational` | 21, 23, 24, 25 | No |
| Power events | `System` (Kernel-Power) | 42, 107, 507 | No |
| Registry | Screen saver, inactivity timeout, GPO, Dynamic Lock | -- | No |

### Audit Policy

For the richest data (user SID, session ID per lock event), enable the Security log audit policy:

```
auditpol /set /subcategory:"Other Logon/Logoff Events" /success:enable
```

The tool works without this policy -- it falls back to Winlogon events and RDP session data -- but the Security log provides more detail per event.

## Lock-Anchored Lookback

By default, `wtf locked` auto-extends the lookback window to cover the most recent lock event, even if it's older than the default 720 hours. This ensures you always get a verdict.

Explicit `--hours` gives a strict time-slice:

```bash
# Only show locks from the last 24 hours
wtf locked --hours 24

# Default: auto-extend to find the most recent lock
wtf locked
```

## Concurrent Login Detection

When a lock event is detected, the tool searches for login events (Security 4624) within 60 seconds of the lock. If found, it reports:

- **Who:** User account and domain
- **From where:** Source IP address and hostname
- **How:** Authentication type (Interactive, RDP, Cached)
- **When:** Timestamp of the login

This is the key feature for answering "someone just took over my session -- who?"

## Output Channels

THAC0 channels for per-section verbosity control:

| Channel | Content |
|---------|---------|
| `verdict` | Lock verdict and threat assessment |
| `evidence` | Evidence supporting the verdict |
| `session` | Lock/unlock session details and durations |
| `login` | Concurrent login details |
| `rdp` | RDP session events |
| `policy` | Registry, GPO, screen saver settings |
| `history` | Lock/unlock timeline |
| `hint` | Security guidance and tips |

Example:
```bash
# Show only verdict and login channels
wtf locked --show verdict:-2 --show login:-2 -QQ

# Enable RDP events at verbose level
wtf locked --show rdp:1
```

## JSON Output

```bash
# Full investigation data as JSON
wtf locked --json

# JSON with AI analysis included
wtf locked --json --ai
```

The JSON output includes the raw PowerShell investigation data, serialized lock sessions with verdicts, and optionally the AI analysis result.

## AI Analysis

```bash
# Claude Code CLI (default)
wtf locked --ai

# Stream AI output in real-time
wtf locked --ai --ai-verbose

# Force re-analysis (bypass 24h cache)
wtf locked --ai --ai-refresh

# Save prompt for manual AI use
wtf locked --ai prompt-only
```

The AI prompt includes all investigation evidence and specifically asks: "Is this lock suspicious? Could it indicate unauthorized access? What should the user check?"

## Examples

```bash
# Quick answer: what caused the last lock?
wtf locked --tier 0

# Full detail with all tiers
wtf locked --tier all

# Lock timeline for the last week
wtf locked history --hours 168

# JSON export for scripting
wtf locked --json | python -m json.tool

# Investigate a specific time window
wtf locked --hours 2

# AI analysis of lock patterns
wtf locked --ai --tier 0
```

## In-Depth Documentation

For detailed technical reference, see the tool-local docs:

- [Event Reference](../../../tools/core/locked/docs/event-reference.md) -- every Windows event queried, with IDs, fields, and PowerShell examples
