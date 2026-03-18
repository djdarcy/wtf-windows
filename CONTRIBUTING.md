# Contributing to wtf-windows

Thank you for considering contributing to wtf-windows!

## Code of Conduct

Please note that this project is released with a Contributor Code of Conduct.
By participating in this project you agree to abide by its terms.

## Development Setup

### Prerequisites

- **Windows 10 or 11** -- diagnostic tools read Windows Event Logs
- **PowerShell 5.1+** (built into Windows 10/11)
- **Python 3.10+**
- **Git**

### Clone and Install

```bash
git clone https://github.com/djdarcy/wtf-windows.git
cd wtf-windows
git submodule update --init --recursive
python -m venv .venv
.venv\Scripts\activate     # Windows cmd
# or: source .venv/Scripts/activate   # Git Bash / WSL
pip install -e ".[dev]"
```

The submodule init pulls `wtf-restarted` into `tools/core/restarted/`.

### Verify Installation

```bash
wtf --version              # Should show PREALPHA 0.1.0-alpha
wtf list                   # Should show 'restarted' in core tools
wtf restarted --version    # Should dispatch to wtf-restarted
```

## Project Structure

```
wtf-windows/
  src/wtf_windows/           # Dispatch infrastructure (DazzleCMD pattern)
    cli.py                   # Entry point, argparse, meta-commands
    loader.py                # .wtf.json manifest discovery, runtime dispatch
    mode.py                  # Dev/publish toggle (symlink <-> submodule)
    importer.py              # Import tools, symlink management
    templates/               # Scaffolding for `wtf new`
  tools/                     # Diagnostic tool modules
    core/
      restarted/             # git submodule -> djdarcy/wtf-restarted
  kits/
    core.kit.json            # Default kit definition
  config/
    wtf.schema.json          # JSON schema for .wtf.json manifests
  tests/
  scripts/
```

### How It Works

1. `cli.py` parses the command and identifies whether it's a meta-command (`list`, `info`, `mode`) or a tool name
2. `loader.py` scans `tools/<namespace>/<tool>/` for `.wtf.json` manifests
3. For tool commands, `loader.py` resolves the runtime and dispatches:
   - `pass_through: true` tools run via `python -m <module>` (graduated tools like wtf-restarted)
   - Embedded tools import the entry point directly
4. `mode.py` handles dev/publish toggling (symlink <-> git submodule)

## Adding a New Diagnostic Tool

### Embedded Tool (starts inside wtf-windows)

```bash
wtf new my-tool --description "What is my PC doing?"
```

This creates `tools/core/my-tool/` with a `.wtf.json` manifest and starter script. Edit the manifest to declare your event log sources, privilege requirements, and capabilities.

### Importing an Existing Tool

```bash
wtf add --repo /path/to/my-tool --link --kit core
```

This creates a symlink from `tools/core/my-tool/` to your local repo. The source directory must contain a `.wtf.json` manifest file -- create one manually or scaffold with `wtf new` first.

### Tool Manifest (.wtf.json)

Every tool needs a `.wtf.json` manifest. Key fields:

```json
{
    "name": "my-tool",
    "version": "0.1.0",
    "description": "What is my PC doing?",
    "namespace": "core",
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "my_tool.py"
    },
    "diagnostics": {
        "event_logs": ["System", "Security"],
        "required_privileges": "admin",
        "supports_history": true,
        "supports_ai": false
    }
}
```

The `diagnostics` section is wtf-windows-specific (not in DazzleCMD):
- `event_logs`: Which Windows Event Log channels the tool reads
- `required_privileges`: "user" or "admin"
- `supports_history`: Whether the tool has a history/timeline subcommand
- `supports_ai`: Whether the tool integrates with the AI analysis pipeline

### Graduation Path

Tools naturally evolve:

1. **Embedded** -- directory in `tools/`, quick iteration
2. **Standalone** -- own GitHub repo, own tests and releases
3. **Submodule** -- returns to wtf-windows as a git submodule
4. **Dev mode** -- symlink for local development (`wtf mode switch <tool> --dev`)

## Running Tests

```bash
pytest                     # Run all tests
pytest -v                  # Verbose output
pytest --cov=wtf_windows   # With coverage
```

## Versioning

Version info lives in `src/wtf_windows/_version.py`. Don't edit `__version__` directly -- it's updated by git hooks. To bump: edit `MAJOR`, `MINOR`, `PATCH`, and `PHASE`.

## How Can I Contribute?

### Reporting Bugs

- Use [GitHub Issues](https://github.com/djdarcy/wtf-windows/issues)
- Include `wtf --version` output
- Include your Windows version (`winver`)

### Suggesting New Diagnostic Tools

- Open an issue describing the Windows mystery you want to solve
- Include which Event Log channels and Event IDs would be relevant
- Check the [Notes & Quick Ideas](https://github.com/djdarcy/wtf-windows/issues/2) issue for existing brainstorming

### Pull Requests

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Run `pytest` and confirm tests pass
5. Submit a pull request

Keep PRs focused -- one tool or feature per PR.

## Related Projects

- [wtf-restarted](https://github.com/djdarcy/wtf-restarted) -- First graduated diagnostic tool
- [DazzleCMD](https://github.com/DazzleTools/dazzlecmd) -- Architectural parent (unified CLI pattern)
