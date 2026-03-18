# wtf-windows (`wtf`)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-green.svg)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)

> **Many diagnostics, one command.**

A unified CLI that aggregates Windows diagnostic tools into a single discoverable interface. Instead of remembering which tool answers which question, just use `wtf <tool> [args]`.

Built on the [DazzleCMD](https://github.com/DazzleTools/dazzlecmd) architectural pattern -- manifest-driven discovery, kit system, and a dev/publish mode toggle that lets tools graduate from embedded to standalone repos.

## Why wtf-windows?

Your Windows PC does something unexpected -- it restarts, locks, crashes, or slows down. You want to know *why*. Each "why" needs different event logs, different analysis, and different expertise. But they all share the same diagnostic pipeline: collect events, classify verdicts, render results, optionally ask AI for analysis.

`wtf-windows` provides the shared infrastructure so each diagnostic tool focuses on its specific investigation while inheriting a consistent UX.

## Installation

```bash
pip install wtf-windows
```

Or install from source:

```bash
git clone https://github.com/djdarcy/wtf-windows.git
cd wtf-windows
pip install -e .
```

## Usage

```bash
# List available diagnostic tools
wtf list

# Get detailed info about a tool
wtf info restarted

# Run a diagnostic tool (all arguments pass through)
wtf restarted                     # Why did my PC restart?
wtf restarted --ai                # With AI-enhanced analysis
wtf restarted history             # Restart timeline
wtf restarted --hours 48          # Custom lookback window

# Version info
wtf --version
```

## Included Tools

### Core Kit

| Tool | Command | Description |
|------|---------|-------------|
| [wtf-restarted](https://github.com/djdarcy/wtf-restarted) | `wtf restarted` | Why did my Windows PC restart? Event log analysis, AI diagnosis. |

### Planned

| Tool | Command | Description |
|------|---------|-------------|
| wtf-locked | `wtf locked` | Why did my PC lock? Security log analysis. |
| wtf-crashed | `wtf crashed` | Deep BSOD / bugcheck analysis. |
| wtf-updated | `wtf updated` | Why did Windows Update run? |

## How It Works

1. **Discovery**: On startup, `wtf` scans `tools/<namespace>/<tool>/` for `.wtf.json` manifests
2. **Kit Filtering**: Only tools belonging to active kits are loaded
3. **Parser Assembly**: Each discovered tool gets an argparse subparser
4. **Dispatch**: `wtf <tool> [args]` routes to the tool's entry point with all remaining args passed through

Tools that are standalone packages (like `wtf-restarted`) are invoked via `python -m <module>`, so `wtf restarted --ai` behaves identically to `wtf-restarted --ai`.

## Architecture

```
wtf-windows/
  src/wtf_windows/
    cli.py              # Entry point: wtf <tool> [args]
    loader.py           # .wtf.json manifest discovery, runtime dispatch
    mode.py             # Dev/publish toggle (symlink <-> git submodule)
    importer.py         # Import tools, symlink management
  tools/
    core/
      restarted/        # git submodule -> djdarcy/wtf-restarted
  kits/
    core.kit.json       # Default kit: always active
```

### Tool Manifests

Each tool has a `.wtf.json` manifest declaring its identity, runtime, and diagnostic requirements:

```json
{
    "name": "restarted",
    "version": "0.2.3",
    "description": "Why did my Windows PC restart?",
    "namespace": "core",
    "runtime": {
        "type": "python",
        "pass_through": true,
        "module": "wtf_restarted"
    },
    "diagnostics": {
        "event_logs": ["System"],
        "required_privileges": "user",
        "supports_ai": true,
        "supports_history": true
    }
}
```

### Mode System

Tools can live as git submodules (publish mode) or symlinks to local repos (dev mode):

```bash
wtf mode status                    # Show all tools and their mode
wtf mode switch restarted --dev    # Switch to local dev symlink
wtf mode switch restarted --publish  # Switch back to submodule
```

Dev paths are saved to `mode_local.json` (git-ignored) so you only need `--path` once. See `docs/mode-system.md` for the full five-state model and graduation workflow.

### Graduation Path

Tools follow a natural lifecycle:

1. **Embedded** -- starts as a directory inside `tools/`
2. **Standalone** -- graduates to its own GitHub repo
3. **Submodule** -- returns as a git submodule in `tools/`
4. **Dev mode** -- symlink to local repo for development

This mirrors the [DazzleCMD](https://github.com/DazzleTools/dazzlecmd) pattern and can itself be registered as a DazzleCMD kit.

## Documentation

- [Manifest Reference](docs/manifest-reference.md) -- full `.wtf.json` field documentation
- [Mode System](docs/mode-system.md) -- dev/publish toggle, five states, graduation workflow
- [Writing a Diagnostic Tool](docs/writing-a-diagnostic-tool.md) -- tutorial for creating new tools
- [Contributing](CONTRIBUTING.md) -- development setup and contribution guide
- [Changelog](CHANGELOG.md) -- release history

## Related Projects

- [wtf-restarted](https://github.com/djdarcy/wtf-restarted) -- Why did my Windows PC restart? (standalone)
- [DazzleCMD](https://github.com/DazzleTools/dazzlecmd) -- Unified CLI for the DazzleTools collection (architectural parent)
- [DazzleNodes](https://github.com/djdarcy/DazzleNodes) -- ComfyUI node pack using similar submodule pattern

## License

Copyright (C) 2026 Dustin Darcy

This project is licensed under the GNU Affero General Public License v3.0 -- see the [LICENSE](LICENSE) file for details.
