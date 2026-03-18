# Mode System: Dev/Publish Toggle

The mode system lets tools switch between local development (symlink to your working copy) and distribution (git submodule checkout). This enables the graduation lifecycle where tools start embedded, become standalone, and return as submodules.

## Tool States

Every tool directory exists in one of five states:

| State | Meaning | Toggle? |
|-------|---------|---------|
| **EMBEDDED** | Plain directory, no submodule registered | No -- this is the default for new tools |
| **PUBLISH (submodule)** | Git submodule checkout from remote | Yes -- can switch to DEV |
| **DEV (symlink)** | Symlink/junction to local repo, submodule registered | Yes -- can switch to PUBLISH |
| **LOCAL-ONLY** | Symlink with no submodule registered | No -- register a submodule first |
| **MISSING** | Path doesn't exist | No -- use `--dev` or `--publish` to restore |

Only **PUBLISH** and **DEV** are toggleable. To make an embedded tool toggleable, it must first graduate to a standalone repo and be registered as a submodule.

## Commands

```bash
# Show mode status for all tools
wtf mode status

# Show mode for a specific tool
wtf mode status restarted

# Toggle between dev and publish
wtf mode switch restarted

# Force a specific mode
wtf mode switch restarted --dev --path C:\code\wtf-restarted
wtf mode switch restarted --publish

# Preview without making changes
wtf mode switch restarted --dry-run
```

## Dev/Publish Workflow

### Switching to Dev Mode

When you run `wtf mode switch restarted --dev`:

1. The current submodule directory (`tools/core/restarted/`) is removed
2. A symlink (or junction on Windows without admin) is created pointing to your local repo
3. The dev path is saved to `mode_local.json` for future toggles

After switching, changes to your local repo are immediately reflected when you run `wtf restarted`.

### Switching to Publish Mode

When you run `wtf mode switch restarted --publish`:

1. The symlink is removed
2. `git submodule update --init tools/core/restarted` restores the submodule checkout

### First-Time Publish (Registering a Submodule)

When a tool has never been a submodule before:

```bash
wtf mode switch my-tool --publish --url https://github.com/user/wtf-my-tool.git
```

This runs `git submodule add <url> tools/<namespace>/<name>` and updates `.gitmodules`. After this, the tool can toggle freely between dev and publish modes.

Alternatively, if the manifest has `source.url` or `lifecycle.graduated_to`, the URL is resolved automatically:

```json
{
    "source": {"url": "https://github.com/user/wtf-my-tool.git"},
    "lifecycle": {"graduated_to": "https://github.com/user/wtf-my-tool"}
}
```

## Dev Path Resolution

When switching to dev mode, the system finds your local repo path in this order:

1. **Explicit `--path` flag**: `wtf mode switch restarted --path C:\code\wtf-restarted`
2. **`mode_local.json`**: Previously saved dev paths (auto-saved on first `--path` use)
3. **`.gitmodules` URL**: If the submodule URL is a local filesystem path

If no dev path can be resolved, the command errors with instructions to provide one.

## mode_local.json

This file (at the repo root, git-ignored) stores local development state:

```json
{
    "dev_paths": {
        "core:restarted": "C:\\code\\wtf-restarted"
    },
    "cached_manifests": {
        "core:restarted": {
            "name": "restarted",
            "version": "0.2.3",
            "description": "Why did my Windows PC restart?",
            ...
        }
    }
}
```

**`dev_paths`**: Maps qualified tool names to local filesystem paths. Populated when you use `--path` for the first time. Persists across toggles so you don't need `--path` again.

**`cached_manifests`**: Stores a copy of the `.wtf.json` when switching to publish mode. This is needed because the remote repo may not have a `.wtf.json` file yet (it's a wtf-windows-specific file). Without the cache, the tool would disappear from `wtf list` after switching to a remote that lacks the manifest.

## Windows Symlink Notes

On Windows, `wtf mode switch --dev` tries:
1. **Symbolic link** (`mklink /D`) -- requires Developer Mode or admin privileges
2. **Junction** (`mklink /J`) -- no admin required, works for local paths

Junctions work identically to symlinks for development purposes. The only limitation is that junctions must point to local paths (not network drives).

## Graduation Sequence

The full lifecycle of graduating an embedded tool:

```bash
# 1. Tool starts embedded
wtf new my-tool
# Edit tools/core/my-tool/ until it's mature

# 2. Create a standalone repo
# (Outside wtf-windows: git init, add files, push to GitHub)

# 3. Register as submodule
wtf mode switch my-tool --publish --url https://github.com/user/wtf-my-tool.git

# 4. Now it toggles freely
wtf mode switch my-tool --dev --path C:\code\wtf-my-tool
wtf mode switch my-tool --publish
```
