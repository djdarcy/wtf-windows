# CLAUDE.md

## Project Overview

**wtf-windows** -- "Why is my Windows PC doing that?" Many diagnostics, one command.

A unified Windows diagnostic CLI built on the DazzleCMD architectural pattern. Aggregates diagnostic tools (`wtf-restarted`, `wtf-locked`, etc.) into a single dispatch interface with manifest-driven discovery, kit system, and dev/publish mode toggle.

- **Language**: Python 3.10+
- **License**: AGPL-3.0-or-later
- **PyPI**: `pip install wtf-windows` (planned)
- **Entry points**: `wtf`, `wtf-windows`
- **Architectural parent**: [DazzleCMD](https://github.com/DazzleTools/dazzlecmd)

## Common Commands

```bash
# Install in editable mode
pip install -e .

# Run the tool
wtf list                   # List available tools
wtf restarted --ai         # Dispatch to wtf-restarted
wtf info restarted         # Show tool metadata
wtf mode status            # Show dev/publish state

# Run tests
python -m pytest
```

## Architecture

```
wtf-windows/
  src/wtf_windows/
    cli.py              # Argument parsing, meta-commands, tool dispatch
    loader.py           # .wtf.json manifest discovery, runtime resolution
    mode.py             # Dev/publish toggle (symlink <-> git submodule)
    importer.py         # Import tools from local repos, symlink management
    _version.py         # Version constants
    templates/          # Scaffolding templates for `wtf new`
  tools/                # Investigation modules (like DazzleCMD's projects/)
    core/
      restarted/        # git submodule -> djdarcy/wtf-restarted
        .wtf.json       # Manifest with pass-through dispatch
  kits/
    core.kit.json       # Default kit: always active
```

### Key Design Patterns

- **DazzleCMD clone**: Same manifest/dispatch/kit/mode pattern, adapted for Windows diagnostics
- **Pass-through dispatch**: `wtf restarted` invokes `python -m wtf_restarted` with all args forwarded
- **Manifest-driven**: `.wtf.json` extends `.dazzlecmd.json` with a `diagnostics` section (event_logs, required_privileges, audit_policies)
- **Mode toggle**: `wtf mode switch` toggles dev (symlink) / publish (submodule) per tool
- **Graduation path**: Tools start embedded, graduate to standalone repos, return as submodules

### Differences from DazzleCMD

- `projects/` renamed to `tools/` (domain-specific naming)
- `.dazzlecmd.json` renamed to `.wtf.json`
- Default platform is `windows` (not `cross-platform`)
- Manifest has `diagnostics` section for event logs, privileges, audit policies
- `wtf info` shows diagnostics metadata (event logs, privileges, AI support)
- Default namespace for `wtf new` is `core` (not `dazzletools`)
- `pass_through` can be specified in `runtime` dict (not just top-level)

## GitHub Issues

- **#1**: Roadmap (evergreen)
- **#2**: Notes & Quick Ideas (evergreen)
- **#3**: EPIC: Architecture and DazzleCMD-pattern implementation

## Cross-References

- [wtf-restarted](https://github.com/djdarcy/wtf-restarted) -- First graduated tool (submodule)
- [DazzleCMD](https://github.com/DazzleTools/dazzlecmd) -- Architectural parent
- DazzleCMD #13 -- Recursive kit PoC (this project tests it)
- wtf-restarted #27 -- Umbrella plan from wtf-restarted's perspective

## Versioning

- **Scheme**: `MAJOR.MINOR.PATCH` with optional PHASE (PEP 440)
- **Current**: 0.1.0-alpha (PREALPHA)
- **Source of truth**: `_version.py` constants
