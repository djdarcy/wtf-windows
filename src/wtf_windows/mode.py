"""Dev/publish mode toggle for wtf-windows tools.

Switches tools between dev mode (symlinks to local repos) and
publish mode (git submodules). Follows the DazzleCMD pattern,
adapted for wtf-windows's tools-based architecture.
"""

import configparser
import json
import os
import subprocess
import sys

from wtf_windows.importer import (
    create_link,
    get_link_target,
    is_linked_project,
    remove_link,
)


# Tool states
STATE_SYMLINK = "symlink"        # Dev mode -- symlink/junction to local repo
STATE_SUBMODULE = "submodule"    # Publish mode -- git submodule checkout
STATE_EMBEDDED = "embedded"      # Plain directory, no submodule registered
STATE_MISSING = "missing"        # Path doesn't exist
STATE_LOCAL_ONLY = "local-only"  # Symlink with no submodule registered


def parse_gitmodules(project_root):
    """Parse .gitmodules to discover submodule mappings.

    Returns dict mapping submodule path (e.g. "tools/core/restarted")
    to {"url": ..., "name": ..., "namespace": ..., "tool_name": ...}.
    """
    gitmodules_path = os.path.join(project_root, ".gitmodules")
    if not os.path.isfile(gitmodules_path):
        return {}

    config = configparser.ConfigParser()
    config.read(gitmodules_path)

    mappings = {}
    for section in config.sections():
        if not section.startswith('submodule "'):
            continue

        path = config[section].get("path", "")
        url = config[section].get("url", "")

        if not path.startswith("tools/"):
            continue

        # Parse tools/<namespace>/<tool_name>
        parts = path.split("/")
        if len(parts) != 3:
            continue

        namespace = parts[1]
        tool_name = parts[2]

        mappings[path] = {
            "url": url,
            "path": path,
            "namespace": namespace,
            "tool_name": tool_name,
        }

    return mappings


def _load_full_config(project_root):
    """Load full mode_local.json contents."""
    config_path = os.path.join(project_root, "mode_local.json")
    if not os.path.isfile(config_path):
        return {"dev_paths": {}, "cached_manifests": {}}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("dev_paths", {})
        data.setdefault("cached_manifests", {})
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: Could not load mode_local.json: {exc}",
              file=sys.stderr)
        return {"dev_paths": {}, "cached_manifests": {}}


def _save_full_config(project_root, data):
    """Save full mode_local.json contents."""
    config_path = os.path.join(project_root, "mode_local.json")
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
    except OSError as exc:
        print(f"Warning: Could not save mode_local.json: {exc}",
              file=sys.stderr)


def load_local_config(project_root):
    """Load dev path mappings from mode_local.json."""
    return _load_full_config(project_root).get("dev_paths", {})


def save_local_config(project_root, dev_paths):
    """Save dev path mappings to mode_local.json."""
    data = _load_full_config(project_root)
    data["dev_paths"] = dev_paths
    _save_full_config(project_root, data)


def cache_manifest(project_root, qualified_name, manifest):
    """Cache a tool's manifest for when the remote version lacks one."""
    data = _load_full_config(project_root)
    clean = {k: v for k, v in manifest.items() if not k.startswith("_")}
    data["cached_manifests"][qualified_name] = clean
    _save_full_config(project_root, data)


def get_cached_manifest(project_root, qualified_name):
    """Retrieve a cached manifest for a tool."""
    data = _load_full_config(project_root)
    return data.get("cached_manifests", {}).get(qualified_name)


def detect_tool_state(tool_dir, gitmodules):
    """Detect the current mode of a tool."""
    rel_key = _tool_dir_to_submodule_path(tool_dir)
    has_submodule = rel_key in gitmodules if rel_key else False

    if not os.path.exists(tool_dir):
        return STATE_MISSING

    if is_linked_project(tool_dir):
        if has_submodule:
            return STATE_SYMLINK
        else:
            return STATE_LOCAL_ONLY

    if os.path.isdir(tool_dir):
        if has_submodule:
            return STATE_SUBMODULE
        else:
            return STATE_EMBEDDED

    return STATE_MISSING


def _tool_dir_to_submodule_path(tool_dir):
    """Convert absolute tool_dir to relative submodule path.

    Example: C:/code/wtf-windows/tools/core/restarted
          -> tools/core/restarted
    """
    norm = tool_dir.replace("\\", "/")
    idx = norm.find("tools/")
    if idx < 0:
        return None
    return norm[idx:]


def resolve_dev_path(qualified_name, project_root, explicit_path=None):
    """Resolve the local dev path for a tool."""
    if explicit_path:
        path = os.path.abspath(explicit_path)
        if os.path.isdir(path):
            return path
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return None

    local_config = load_local_config(project_root)
    if qualified_name in local_config:
        path = local_config[qualified_name]
        if os.path.isdir(path):
            return path
        print(f"Warning: Configured dev path does not exist: {path}",
              file=sys.stderr)

    gitmodules = parse_gitmodules(project_root)
    for info in gitmodules.values():
        qn = f"{info['namespace']}:{info['tool_name']}"
        if qn == qualified_name:
            url = info["url"]
            if _is_local_path(url):
                local = _normalize_local_path(url)
                if os.path.isdir(local):
                    return local

    return None


def _is_local_path(url):
    """Check if a URL is actually a local filesystem path."""
    if url.startswith(("http://", "https://", "git@", "ssh://")):
        return False
    return True


def _normalize_local_path(path_str):
    """Normalize a path from .gitmodules to a local filesystem path."""
    if sys.platform == "win32" and len(path_str) >= 3:
        if path_str[0] == "/" and path_str[2] == "/":
            drive = path_str[1].upper()
            return drive + ":" + path_str[2:].replace("/", "\\")
    return os.path.abspath(path_str)


# ============================================================================
# Status Command
# ============================================================================

STATE_LABELS = {
    STATE_SYMLINK: "DEV (symlink)",
    STATE_SUBMODULE: "PUBLISH (submodule)",
    STATE_EMBEDDED: "EMBEDDED",
    STATE_MISSING: "MISSING",
    STATE_LOCAL_ONLY: "LOCAL-ONLY (symlink, no submodule)",
}


def cmd_status(projects, project_root, tool_filter=None, kit_filter=None):
    """Show mode status for tools."""
    gitmodules = parse_gitmodules(project_root)

    all_projects = list(projects)
    known_names = {p["name"] for p in all_projects}
    data = _load_full_config(project_root)
    cached = data.get("cached_manifests", {})

    tools_dir = os.path.join(project_root, "tools")
    if os.path.isdir(tools_dir):
        for ns in sorted(os.listdir(tools_dir)):
            ns_dir = os.path.join(tools_dir, ns)
            if not os.path.isdir(ns_dir) or ns.startswith("."):
                continue
            for name in sorted(os.listdir(ns_dir)):
                if name in known_names or name.startswith("."):
                    continue
                tool_dir = os.path.join(ns_dir, name)
                if not os.path.isdir(tool_dir):
                    continue
                qualified = f"{ns}:{name}"
                if qualified in cached:
                    entry = dict(cached[qualified])
                else:
                    entry = {"name": name, "description": "(no manifest)"}
                entry["_dir"] = tool_dir
                entry["namespace"] = ns
                entry.setdefault("name", name)
                all_projects.append(entry)
                known_names.add(name)

    filtered = all_projects
    if tool_filter:
        filtered = [p for p in filtered if p["name"] == tool_filter]
        if not filtered:
            print(f"Tool '{tool_filter}' not found. Use 'wtf list' to see "
                  "available tools.")
            return 1
    if kit_filter:
        filtered = [p for p in filtered if p.get("namespace") == kit_filter]

    if not filtered:
        print("No tools found.")
        return 0

    name_width = max(len(p["name"]) for p in filtered)
    ns_width = max(len(p.get("namespace", "")) for p in filtered)

    print()
    header = (f"  {'Name':<{name_width}}  {'Namespace':<{ns_width}}  "
              f"{'Mode':<30}  Details")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for project in filtered:
        tool_dir = project["_dir"]
        state = detect_tool_state(tool_dir, gitmodules)
        label = STATE_LABELS.get(state, state)

        name = project["name"]
        ns = project.get("namespace", "")

        details = ""
        if state == STATE_SYMLINK or state == STATE_LOCAL_ONLY:
            target = get_link_target(tool_dir)
            if target:
                details = f"-> {target}"
        elif state == STATE_SUBMODULE:
            rel_key = _tool_dir_to_submodule_path(tool_dir)
            if rel_key and rel_key in gitmodules:
                details = gitmodules[rel_key]["url"]

        print(f"  {name:<{name_width}}  {ns:<{ns_width}}  "
              f"{label:<30}  {details}")

    print(f"\n  {len(filtered)} tool(s)")
    return 0


# ============================================================================
# Switch Command
# ============================================================================

def cmd_switch(tool_name, projects, project_root, dev_path=None,
               force_mode=None, dry_run=False, url=None):
    """Toggle a tool between dev and publish mode."""
    matches = [p for p in projects if p["name"] == tool_name]
    if matches:
        project = matches[0]
    else:
        project = _find_undiscovered_tool(tool_name, project_root)
        if project is None:
            print(f"Error: Tool '{tool_name}' not found. Use 'wtf list' "
                  "to see available tools.", file=sys.stderr)
            return 1

    tool_dir = project["_dir"]
    namespace = project.get("namespace", "")
    qualified = f"{namespace}:{tool_name}"

    gitmodules = parse_gitmodules(project_root)
    state = detect_tool_state(tool_dir, gitmodules)

    if dry_run:
        print("[DRY-RUN] No changes will be made\n")

    if force_mode:
        target = force_mode
    else:
        target = _determine_target(state)

    if target is None:
        _print_no_toggle(tool_name, state)
        return 1

    print(f"Tool:    {qualified}")
    print(f"Current: {STATE_LABELS.get(state, state)}")
    print(f"Target:  {'DEV (symlink)' if target == 'dev' else 'PUBLISH (submodule)'}")
    print()

    if target == "dev":
        return _switch_to_dev(project, project_root, gitmodules, dev_path,
                              dry_run)
    else:
        return _switch_to_publish(project, project_root, gitmodules,
                                  dry_run, url=url)


def _find_undiscovered_tool(tool_name, project_root):
    """Find a tool by scanning tools/ directories even without a manifest."""
    tools_dir = os.path.join(project_root, "tools")
    if not os.path.isdir(tools_dir):
        return None

    for namespace in os.listdir(tools_dir):
        ns_dir = os.path.join(tools_dir, namespace)
        if not os.path.isdir(ns_dir) or namespace.startswith("."):
            continue
        tool_dir = os.path.join(ns_dir, tool_name)
        if os.path.exists(tool_dir) or is_linked_project(tool_dir):
            qualified = f"{namespace}:{tool_name}"
            cached = get_cached_manifest(project_root, qualified)
            if cached:
                cached["_dir"] = tool_dir
                cached["namespace"] = namespace
                return cached
            return {
                "name": tool_name,
                "namespace": namespace,
                "_dir": tool_dir,
            }

    data = _load_full_config(project_root)
    for qn, manifest in data.get("cached_manifests", {}).items():
        if ":" in qn:
            ns, name = qn.split(":", 1)
        else:
            ns, name = "", qn
        if name == tool_name:
            tool_dir = os.path.join(tools_dir, ns, name)
            manifest["_dir"] = tool_dir
            manifest["namespace"] = ns
            return manifest

    return None


def _determine_target(state):
    """Given current state, determine which mode to switch to."""
    if state == STATE_SYMLINK:
        return "publish"
    elif state == STATE_SUBMODULE:
        return "dev"
    elif state == STATE_MISSING:
        return None
    elif state == STATE_EMBEDDED:
        return None
    elif state == STATE_LOCAL_ONLY:
        return None
    return None


def _print_no_toggle(tool_name, state):
    """Print a helpful message when toggle is not possible."""
    if state == STATE_EMBEDDED:
        print(f"Error: '{tool_name}' is embedded (no submodule registered).",
              file=sys.stderr)
        print("  This tool lives directly in the repo -- no mode toggle "
              "available.", file=sys.stderr)
    elif state == STATE_LOCAL_ONLY:
        print(f"Error: '{tool_name}' is a local-only symlink (no submodule "
              "registered).", file=sys.stderr)
        print("  To enable mode switching, register a submodule first:",
              file=sys.stderr)
        print(f"    git submodule add <url> tools/<ns>/{tool_name}",
              file=sys.stderr)
    elif state == STATE_MISSING:
        print(f"Error: '{tool_name}' is missing from disk.",
              file=sys.stderr)
        print("  Use --dev or --publish to specify which mode to restore.",
              file=sys.stderr)
    else:
        print(f"Error: Cannot toggle '{tool_name}' (state: {state}).",
              file=sys.stderr)


def _switch_to_dev(project, project_root, gitmodules, explicit_path,
                   dry_run):
    """Switch a tool from publish mode (submodule) to dev mode (symlink)."""
    tool_dir = project["_dir"]
    tool_name = project["name"]
    namespace = project.get("namespace", "")
    qualified = f"{namespace}:{tool_name}"
    state = detect_tool_state(tool_dir, gitmodules)

    if state == STATE_SYMLINK or state == STATE_LOCAL_ONLY:
        print("Already in dev mode (symlink).")
        target = get_link_target(tool_dir)
        if target:
            print(f"  -> {target}")
        return 0

    dev_path = resolve_dev_path(qualified, project_root, explicit_path)
    if dev_path is None:
        print(f"Error: Cannot determine dev path for '{tool_name}'.",
              file=sys.stderr)
        print("  Specify with: wtf mode switch <tool> --path /local/repo",
              file=sys.stderr)
        print("  Or add to mode_local.json:", file=sys.stderr)
        print(f'    {{"dev_paths": {{"{qualified}": "/path/to/repo"}}}}',
              file=sys.stderr)
        return 1

    if dry_run:
        if os.path.exists(tool_dir):
            print(f"  Would remove: {tool_dir}")
        print(f"  Would create symlink: {tool_dir} -> {dev_path}")
        print(f"  Would save dev path to mode_local.json: "
              f"{qualified} -> {dev_path}")
        return 0

    if os.path.exists(tool_dir):
        if is_linked_project(tool_dir):
            remove_link(tool_dir)
        else:
            import shutil
            try:
                shutil.rmtree(tool_dir)
            except OSError as exc:
                print(f"Error: Could not remove {tool_dir}: {exc}",
                      file=sys.stderr)
                return 1

    link_mode = create_link(dev_path, tool_dir)
    if link_mode is None:
        print(f"Error: Could not create link to {dev_path}",
              file=sys.stderr)
        return 1

    _remember_dev_path(qualified, dev_path, project_root)

    print(f"Switched to DEV mode ({link_mode})")
    print(f"  {tool_dir} -> {dev_path}")
    return 0


def _switch_to_publish(project, project_root, gitmodules, dry_run,
                       url=None):
    """Switch a tool from dev mode (symlink) to publish mode (submodule)."""
    tool_dir = project["_dir"]
    tool_name = project["name"]
    namespace = project.get("namespace", "")

    state = detect_tool_state(tool_dir, gitmodules)
    if state == STATE_SUBMODULE:
        print("Already in publish mode (submodule).")
        return 0

    rel_key = _tool_dir_to_submodule_path(tool_dir)
    if not rel_key:
        rel_key = f"tools/{namespace}/{tool_name}"

    has_submodule = rel_key in gitmodules

    qualified = f"{namespace}:{tool_name}"
    if project.get("name"):
        cache_manifest(project_root, qualified, project)

    if not has_submodule:
        remote_url = _resolve_remote_url(project, url)
        if not remote_url:
            print(f"Error: No remote URL known for '{tool_name}'.",
                  file=sys.stderr)
            print("  Provide one with: wtf mode switch <tool> "
                  "--publish --url <url>", file=sys.stderr)
            return 1

        if dry_run:
            if is_linked_project(tool_dir):
                print(f"  Would remove symlink: {tool_dir}")
            print(f"  Would run: git submodule add {remote_url} "
                  f"{rel_key}")
            print("  Note: .gitmodules will be updated (uncommitted)")
            return 0

        if is_linked_project(tool_dir):
            if not remove_link(tool_dir):
                print(f"Error: Could not remove symlink at {tool_dir}",
                      file=sys.stderr)
                return 1
        elif os.path.isdir(tool_dir):
            import shutil
            try:
                shutil.rmtree(tool_dir)
            except OSError as exc:
                print(f"Error: Could not remove {tool_dir}: {exc}",
                      file=sys.stderr)
                return 1

        try:
            result = subprocess.run(
                ["git", "-C", project_root, "submodule", "add",
                 remote_url, rel_key],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                print(f"Error: git submodule add failed: "
                      f"{result.stderr.strip()}", file=sys.stderr)
                return 1
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Error: git submodule add failed: {exc}",
                  file=sys.stderr)
            return 1

        print("Switched to REMOTE mode (submodule - first time)")
        print(f"  {remote_url}")
        print("  Note: .gitmodules updated (uncommitted)")
        return 0

    # Existing submodule -- just restore it
    submodule_path = rel_key

    if dry_run:
        if is_linked_project(tool_dir):
            print(f"  Would remove symlink: {tool_dir}")
        print(f"  Would run: git submodule update --init {submodule_path}")
        return 0

    if is_linked_project(tool_dir):
        if not remove_link(tool_dir):
            print(f"Error: Could not remove symlink at {tool_dir}",
                  file=sys.stderr)
            return 1

    try:
        result = subprocess.run(
            ["git", "-C", project_root, "submodule", "update", "--init",
             submodule_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"Error: git submodule update failed: "
                  f"{result.stderr.strip()}", file=sys.stderr)
            return 1
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Error: git submodule update failed: {exc}",
              file=sys.stderr)
        return 1

    print("Switched to REMOTE mode (submodule)")
    print(f"  {gitmodules[rel_key]['url']}")
    return 0


def _resolve_remote_url(project, explicit_url=None):
    """Resolve remote URL for a tool."""
    if explicit_url:
        return explicit_url

    source = project.get("source", {})
    if source.get("url"):
        return source["url"]

    lifecycle = project.get("lifecycle", {})
    if lifecycle.get("graduated_to"):
        return lifecycle["graduated_to"]

    return None


def _remember_dev_path(qualified_name, dev_path, project_root):
    """Save a dev path to mode_local.json for future toggles."""
    local_config = load_local_config(project_root)
    local_config[qualified_name] = dev_path
    save_local_config(project_root, local_config)
