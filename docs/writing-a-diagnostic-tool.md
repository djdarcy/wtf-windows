# Writing a Diagnostic Tool

This guide walks through creating a new Windows diagnostic tool for wtf-windows, from scaffold to working investigation.

## Step 1: Scaffold

```bash
wtf new locked --description "Why did my Windows PC lock?"
```

This creates:

```
tools/core/locked/
  .wtf.json          # Manifest (you'll edit this)
  locked.py           # Starter script (you'll replace this)
```

For additional scaffolding, use `--simple` (adds TODO.md, NOTES.md) or `--full` (adds ROADMAP.md, tests/, private/claude/).

## Step 2: Edit the Manifest

Open `tools/core/locked/.wtf.json` and fill in the `diagnostics` section:

```json
{
    "name": "locked",
    "version": "0.1.0",
    "description": "Why did my Windows PC lock?",
    "namespace": "core",
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "locked.py"
    },
    "diagnostics": {
        "event_logs": ["Security"],
        "event_ids": [4800, 4801, 4802, 4803],
        "required_privileges": "admin",
        "ps1_scripts": ["ps1/investigate_locks.ps1"],
        "supports_history": true,
        "supports_ai": false
    }
}
```

Key decisions:
- **Which Event Log channels?** Check Windows Event Viewer to find relevant events.
- **Admin required?** Security log needs admin. System log usually doesn't.
- **AI support?** Add later once the basic tool works.

See `docs/manifest-reference.md` for the full field reference.

## Step 3: Write the PowerShell Collector

Create `tools/core/locked/ps1/investigate_locks.ps1`:

```powershell
# investigate_locks.ps1 - Collect lock/unlock events from Security log
param(
    [int]$Hours = 720,
    [switch]$JsonOutput
)

$After = (Get-Date).AddHours(-$Hours)

$Events = @()

# Lock events (4800)
try {
    $LockEvents = Get-WinEvent -FilterHashtable @{
        LogName = 'Security'
        Id = 4800
        StartTime = $After
    } -ErrorAction SilentlyContinue

    foreach ($evt in $LockEvents) {
        $Events += @{
            timestamp = $evt.TimeCreated.ToString("o")
            event_id = $evt.Id
            type = "LOCK"
            message = $evt.Message
        }
    }
} catch { }

# Unlock events (4801)
try {
    $UnlockEvents = Get-WinEvent -FilterHashtable @{
        LogName = 'Security'
        Id = 4801
        StartTime = $After
    } -ErrorAction SilentlyContinue

    foreach ($evt in $UnlockEvents) {
        $Events += @{
            timestamp = $evt.TimeCreated.ToString("o")
            event_id = $evt.Id
            type = "UNLOCK"
            message = $evt.Message
        }
    }
} catch { }

# Output as JSON
$Events | Sort-Object { [datetime]$_.timestamp } | ConvertTo-Json -Depth 3
```

The pattern: query specific Event IDs, build structured objects, output JSON. Python parses this JSON.

## Step 4: Write the Python Entry Point

Replace the starter `locked.py` with your investigation logic:

```python
"""locked - Why did my Windows PC lock?"""

import json
import subprocess
import sys
import os


def run_ps1(script_path, hours=720):
    """Run a PowerShell script and parse JSON output."""
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass",
         "-File", script_path, "-Hours", str(hours), "-JsonOutput"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"PowerShell error: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        return []


def classify_verdict(events):
    """Classify the lock events into a verdict."""
    if not events:
        return "NO_LOCK_EVENTS", "No lock events found in the time window."

    # Find the most recent lock
    locks = [e for e in events if e.get("type") == "LOCK"]
    if not locks:
        return "NO_LOCKS", "Unlock events found but no corresponding locks."

    latest = locks[-1]
    return "LOCK_DETECTED", f"PC was locked at {latest['timestamp']}"


def main(argv=None):
    """Entry point for wtf locked."""
    if argv is None:
        argv = sys.argv[1:]

    # Parse args (simple example -- use argparse for real tools)
    hours = 720
    for i, arg in enumerate(argv):
        if arg == "--hours" and i + 1 < len(argv):
            hours = int(argv[i + 1])

    # Find PS1 script relative to this file
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    ps1_path = os.path.join(tool_dir, "ps1", "investigate_locks.ps1")

    if not os.path.isfile(ps1_path):
        print("Error: PowerShell script not found.", file=sys.stderr)
        return 1

    events = run_ps1(ps1_path, hours)
    verdict, message = classify_verdict(events)

    print(f"Verdict: {verdict}")
    print(f"  {message}")
    print(f"  ({len(events)} events in last {hours} hours)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## Step 5: Test It

```bash
# Via wtf dispatch
wtf locked
wtf locked --hours 24

# Direct execution (for debugging)
python tools/core/locked/locked.py --hours 24
```

## Step 6: Register in a Kit

Your tool should already appear in `wtf list` if it's in `tools/core/`. To explicitly register it in the core kit, add it to `kits/core.kit.json`:

```json
{
    "tools": [
        "core:restarted",
        "core:locked"
    ]
}
```

## What wtf-windows Provides vs What You Own

| Responsibility | wtf-windows provides | Your tool owns |
|---|---|---|
| Discovery | Manifest scanning, `wtf list`, `wtf info` | The `.wtf.json` manifest |
| Dispatch | `wtf <name> [args]` routing | The entry point function and arg parsing |
| Mode toggle | Dev/publish symlink management | Nothing (transparent to the tool) |
| Event log collection | Nothing (yet) | PowerShell scripts for your specific events |
| Verdict classification | Nothing (yet) | Your own verdict logic |
| Output rendering | Nothing (yet) | Your own output formatting |
| AI analysis | Nothing (yet) | Your own AI integration (or wait for shared lib) |

Currently each tool is responsible for its own PowerShell execution, output rendering, and AI integration. As the shared library (`wtf_windows/lib/`) matures, common patterns will be extracted and tools can opt into shared infrastructure.

## Graduation

When your tool matures:

1. Create a standalone GitHub repo
2. Add `pyproject.toml` with entry points (`pip install wtf-locked` gives `wtf-locked` and `wtfl`)
3. Ensure `python -m wtf_locked` works
4. Update `.wtf.json` with `runtime.module`, `source.url`, `lifecycle.graduated_to`
5. Run `wtf mode switch locked --publish --url <github-url>`

See `docs/mode-system.md` for the full graduation sequence.
