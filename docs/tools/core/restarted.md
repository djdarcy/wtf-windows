# wtf restarted

Why did my Windows PC restart? Analyzes event logs, crash dumps, and system state to tell you what happened.

**Standalone repo:** [github.com/djdarcy/wtf-restarted](https://github.com/djdarcy/wtf-restarted)
**PyPI:** `pip install wtf-restarted`
**Status:** Graduated (standalone package, integrated as submodule)

## Quick Start

```bash
# Basic diagnosis -- what caused the last restart?
wtf restarted

# With AI-enhanced analysis
wtf restarted --ai

# Restart history timeline
wtf restarted history

# Custom lookback window
wtf restarted --hours 48
```

## Usage

```
wtf restarted [command] [options]
```

### Commands

| Command | Description |
|---------|-------------|
| `diagnose` | Analyze last restart (default) |
| `history` | Show restart timeline |

### Key Flags

| Flag | Description |
|------|-------------|
| `--hours N` | Lookback window in hours (default: auto-extends to cover last restart) |
| `--ai [BACKEND]` | Run AI analysis (backends: claude, codex, prompt-only) |
| `--ai-only [BACKEND]` | Show only the AI analysis |
| `--tier TIERS` | Which tiers to show: 0, 1, 2, or all |
| `--no-page` | Disable interactive paging between tiers |
| `-v` / `-Q` | Increase / decrease verbosity |
| `--show CHANNEL:LEVEL` | Per-channel verbosity override |
| `--json` | Output raw JSON |
| `--skip-dump` | Skip crash dump analysis |

### Tiered Disclosure

| Tier | Content |
|------|---------|
| 0 (Answer) | Header, system info, verdict, AI analysis |
| 1 (Evidence) | Evidence table, key events (Kernel-Power 41, Event 6008, shutdown initiator) |
| 2 (Diagnostics) | BugCheck, GPU, Windows Update, WHEA, crash dumps, context window |

## Verdicts

| Verdict | Color | Meaning |
|---------|-------|---------|
| BSOD | Red | Blue Screen of Death (bugcheck detected) |
| UNEXPECTED_SHUTDOWN | Yellow | Dirty shutdown without clean stop |
| INITIATED_RESTART | Cyan | Normal restart initiated by user/system/update |
| MIXED_SIGNALS | Magenta | Conflicting evidence from multiple sources |
| CLEAN_RESTART | Green | Normal clean shutdown and restart |

## Event Sources

- **System log**: Kernel-Power 41, Event 6008, shutdown initiator 1074/1076, boot sequence 6005/6006/6009
- **Application log**: BugCheck/BlueScreen entries from Windows Error Reporting
- **Crash dumps**: `C:\Windows\MEMORY.DMP`, `C:\Windows\Minidump\*.dmp` (via kd.exe if available)

## Boot-Anchored Lookback

By default, `wtf restarted` auto-extends the lookback window past `--hours` to cover the most recent restart. This ensures you always get a verdict even if uptime exceeds the default window.

Explicit `--hours` gives a strict time-slice (no auto-extension).

## AI Analysis

```bash
# Claude Code CLI (default)
wtf restarted --ai

# OpenAI Codex
wtf restarted --ai codex

# Save prompt to file for manual use
wtf restarted --ai prompt-only

# Force re-analysis (bypass 24h cache)
wtf restarted --ai --ai-refresh
```

## Standalone Usage

`wtf-restarted` also works independently without wtf-windows:

```bash
pip install wtf-restarted
wtf-restarted --ai
wtfr history
```

## More Information

See the [wtf-restarted README](https://github.com/djdarcy/wtf-restarted) for full documentation including PowerShell engine details, event reference, and platform support.
