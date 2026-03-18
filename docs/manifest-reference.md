# .wtf.json Manifest Reference

Every diagnostic tool in wtf-windows has a `.wtf.json` manifest file at its root. This file declares the tool's identity, how to run it, and what Windows resources it needs.

The format extends DazzleCMD's `.dazzlecmd.json` with a `diagnostics` section specific to Windows event log analysis. The full JSON schema is at `config/wtf.schema.json`.

## Quick Start

Minimal manifest for an embedded tool:

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
    }
}
```

## Field Reference

### Identity Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | Yes | string | Tool name, used as CLI command (`wtf <name>`). Lowercase, hyphens/underscores allowed. |
| `version` | Yes | string | Semantic version (e.g., `0.1.0`, `0.2.3-alpha`). |
| `description` | Yes | string | Short description. First sentence appears in `wtf --help`. |
| `namespace` | No | string | Organizational namespace (e.g., `core`, `deep`). Maps to `tools/<namespace>/<name>/` directory. |
| `language` | No | string | Primary language: `python`, `powershell`, `shell`, `batch`. |
| `platform` | No | string | Quick-glance platform: `windows` (default) or `cross-platform`. |
| `platforms` | No | string[] | Specific verified platforms: `["windows"]`, `["windows", "linux"]`. |

### Runtime Fields

The `runtime` object tells the dispatcher how to execute the tool.

| Field | Type | Description |
|-------|------|-------------|
| `runtime.type` | string | **Required.** One of: `python`, `shell`, `script`, `binary`. |
| `runtime.entry_point` | string | Function name to call (default: `main`). For `python` type with direct import. |
| `runtime.script_path` | string | Path to main script, relative to tool dir. Used for direct import or subprocess. |
| `runtime.module` | string | Python module for `-m` invocation. Used when `pass_through` is true and the tool is an installed package. |
| `runtime.pass_through` | boolean | If true, run via subprocess instead of importing. Needed for graduated tools with relative imports. |
| `runtime.shell` | string | Shell interpreter for `shell` type: `bash`, `cmd`, `pwsh`, `powershell`. |

#### Pass-through: Two Locations

`pass_through` can appear in two places:

```json
{"pass_through": true}
```

or:

```json
{"runtime": {"pass_through": true}}
```

Both are checked. The top-level location matches DazzleCMD's convention. The `runtime`-level location is more natural for `.wtf.json` since it's a runtime concern. Use whichever is clearer for your tool -- the loader checks both.

#### Module vs Script Path

For **embedded tools** (source lives inside wtf-windows):
```json
{
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "my_tool.py"
    }
}
```
The loader imports `my_tool` from the tool directory and calls `main(argv)`.

For **graduated tools** (standalone packages installed via pip):
```json
{
    "runtime": {
        "type": "python",
        "pass_through": true,
        "module": "wtf_restarted"
    }
}
```
The loader runs `python -m wtf_restarted` via subprocess. This avoids relative import issues that occur when running a package's `cli.py` directly.

When `module` is specified, it takes precedence over `script_path`.

### Diagnostics Fields

The `diagnostics` section is specific to wtf-windows (not present in DazzleCMD manifests). It declares what Windows resources the tool needs and what capabilities it offers.

| Field | Type | Description |
|-------|------|-------------|
| `diagnostics.event_logs` | string[] | Windows Event Log channels read: `"System"`, `"Security"`, `"Application"`, etc. |
| `diagnostics.event_ids` | integer[] | Specific Event IDs queried (informational, for `wtf info`). |
| `diagnostics.required_privileges` | string | `"user"` (default), `"admin"`, or `"mixed"` (some features need elevation). |
| `diagnostics.audit_policies` | object[] | Audit policies that should be enabled (see below). |
| `diagnostics.ps1_scripts` | string[] | PowerShell data collection scripts, relative to tool dir. |
| `diagnostics.supports_history` | boolean | Whether the tool has a history/timeline subcommand. |
| `diagnostics.supports_ai` | boolean | Whether the tool integrates with the AI analysis pipeline. |

These fields are used by:
- `wtf --help` -- shows `[AI, history, admin]` capability badges
- `wtf info <tool>` -- displays event logs, privileges, capabilities
- Future: privilege checking before dispatch, audit policy guidance

#### Audit Policies

Some tools need specific Windows audit policies enabled to receive events. The `audit_policies` array documents these requirements:

```json
{
    "diagnostics": {
        "audit_policies": [
            {
                "subcategory": "Other Logon/Logoff Events",
                "setting": "success",
                "required": false,
                "guidance": "Enable for lock/unlock tracking: auditpol /set /subcategory:\"Other Logon/Logoff Events\" /success:enable"
            }
        ]
    }
}
```

When `required` is `false`, the tool degrades gracefully without the policy. The `guidance` string is shown to the user if the policy is not detected.

### Classification Fields

| Field | Type | Description |
|-------|------|-------------|
| `taxonomy.category` | string | Primary category (e.g., `windows-diagnostics`). |
| `taxonomy.tags` | string[] | Tags for search and filtering. |

### Lifecycle Fields

| Field | Type | Description |
|-------|------|-------------|
| `lifecycle.stage` | string | One of: `embedded`, `active`, `stable`, `graduated`, `deprecated`. |
| `lifecycle.graduated_to` | string | GitHub repo URL if the tool graduated to standalone. Used by `mode switch --publish` to resolve the submodule URL without needing `--url`. |

### Source Fields

| Field | Type | Description |
|-------|------|-------------|
| `source.url` | string | Remote URL (GitHub, git). Used by `mode switch --publish` for first-time submodule registration. |
| `source.path` | string | Local filesystem path to original source. |

### Dependency Fields

| Field | Type | Description |
|-------|------|-------------|
| `dependencies.python` | string[] | Python package dependencies (e.g., `["rich>=13.0"]`). |
| `dependencies.system` | string[] | System-level dependencies (e.g., `["kd.exe"]`). |

## Complete Examples

### Graduated Tool (wtf-restarted)

```json
{
    "name": "restarted",
    "version": "0.2.3",
    "description": "Why did my Windows PC restart? One command, instant answers.",
    "namespace": "core",
    "language": "python",
    "platform": "windows",
    "platforms": ["windows"],
    "runtime": {
        "type": "python",
        "pass_through": true,
        "module": "wtf_restarted",
        "entry_point": "main",
        "script_path": "wtf_restarted/cli.py"
    },
    "taxonomy": {
        "category": "windows-diagnostics",
        "tags": ["restart", "reboot", "crash", "bsod", "event-log", "shutdown"]
    },
    "diagnostics": {
        "event_logs": ["System"],
        "event_ids": [41, 1074, 6005, 6006, 6008, 6009, 6013, 1001],
        "required_privileges": "user",
        "ps1_scripts": ["wtf_restarted/ps1/investigate.ps1"],
        "supports_history": true,
        "supports_ai": true
    },
    "source": {
        "url": "https://github.com/djdarcy/wtf-restarted.git"
    },
    "lifecycle": {
        "stage": "graduated",
        "graduated_to": "https://github.com/djdarcy/wtf-restarted"
    }
}
```

### Embedded Tool (hypothetical wtf-locked)

```json
{
    "name": "locked",
    "version": "0.1.0",
    "description": "Why did my Windows PC lock?",
    "namespace": "core",
    "language": "python",
    "platform": "windows",
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "locked.py"
    },
    "taxonomy": {
        "category": "windows-diagnostics",
        "tags": ["lock", "security", "session"]
    },
    "diagnostics": {
        "event_logs": ["Security"],
        "event_ids": [4800, 4801, 4802, 4803],
        "required_privileges": "admin",
        "audit_policies": [
            {
                "subcategory": "Other Logon/Logoff Events",
                "setting": "success",
                "required": false,
                "guidance": "auditpol /set /subcategory:\"Other Logon/Logoff Events\" /success:enable"
            }
        ],
        "ps1_scripts": ["ps1/investigate_locks.ps1"],
        "supports_history": true,
        "supports_ai": true
    }
}
```
