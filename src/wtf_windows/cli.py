"""Main CLI entry point for wtf-windows.

Built on top of ``dazzlecmd-lib``'s ``AggregatorEngine``. wtf-windows is
the second production adopter of the library; dazzlecmd itself is the
first (and dogfoods the library via its own cli.py).

Library defaults (``list``, ``info``, ``kit``, ``version``) are
registered automatically. wtf overrides ``list`` and ``info`` to add
domain-specific rendering (diagnostic badges, event-log fields), drops
``tree`` and ``setup`` (not in wtf's vocabulary), and registers its own
``mode``, ``new``, and ``add`` meta-commands.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from wtf_windows._version import DISPLAY_VERSION, __version__
from dazzlecmd_lib import AggregatorEngine
from dazzlecmd_lib import default_meta_commands as _dmc
from dazzlecmd_lib.loader import set_manifest_cache_fn


# ---------------------------------------------------------------------------
# Domain-enriched handlers: list + info with diagnostic badges
# ---------------------------------------------------------------------------


def _wtf_list_handler(args, engine, projects, kits, project_root):
    """List available diagnostic tools with capability badges.

    Renders the stock table plus `[AI, history, admin]` badges derived
    from each project's ``diagnostics`` manifest block — information the
    library-default renderer doesn't know about.
    """
    filtered = list(projects)
    if args.namespace:
        filtered = [p for p in filtered if p.get("namespace") == args.namespace]
    if args.platform:
        filtered = [
            p for p in filtered
            if p.get("platform", "windows") == args.platform
        ]
    if args.tag:
        filtered = [
            p for p in filtered
            if args.tag in p.get("taxonomy", {}).get("tags", [])
        ]
    if args.kit:
        filtered = [
            p for p in filtered
            if p.get("_kit_import_name") == args.kit
            or p.get("namespace") == args.kit
        ]

    if not filtered:
        print("No tools found.")
        return 0

    name_width = max(len(p["name"]) for p in filtered)
    ns_width = max(len(p.get("namespace", "")) for p in filtered)

    header = f"  {'Name':<{name_width}}  {'Namespace':<{ns_width}}  Description"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for project in filtered:
        name = project["name"]
        ns = project.get("namespace", "")
        desc = project.get("description", "")

        diag = project.get("diagnostics", {})
        badges = []
        if diag.get("supports_ai"):
            badges.append("AI")
        if diag.get("supports_history"):
            badges.append("history")
        if diag.get("required_privileges") == "admin":
            badges.append("admin")
        badge_str = f"  [{', '.join(badges)}]" if badges else ""

        # Single-sentence description for the table
        if ". " in desc:
            desc = desc[:desc.index(". ") + 1]
        elif "? " in desc:
            desc = desc[:desc.index("? ") + 1]
        max_desc = 52
        if len(desc) > max_desc:
            desc = desc[:max_desc - 3] + "..."

        print(f"  {name:<{name_width}}  {ns:<{ns_width}}  {desc}{badge_str}")

    print(f"\n  {len(filtered)} tool(s) found")
    return 0


def _wtf_info_handler(args, engine, projects, kits, project_root):
    """Show info on a tool including wtf-specific diagnostics fields."""
    # Start with the library's stock renderer
    result = _dmc.render_info(args, projects, engine)
    if result != 0:
        return result

    # Append wtf-specific diagnostics block
    tool_name = args.tool
    if ":" in tool_name:
        matches = [p for p in projects if p.get("_fqcn") == tool_name]
    else:
        matches = [p for p in projects if p["name"] == tool_name]
    if not matches:
        return 0

    project = matches[0]
    diag = project.get("diagnostics", {})
    if diag:
        if diag.get("event_logs"):
            print(f"Event logs:  {', '.join(diag['event_logs'])}")
        if diag.get("required_privileges"):
            print(f"Privileges:  {diag['required_privileges']}")
        if diag.get("supports_ai"):
            print(f"AI support:  yes")
        if diag.get("supports_history"):
            print(f"History:     yes")

    # Link status (wtf's importer module)
    try:
        from wtf_windows.importer import is_linked_project, get_link_target
        if is_linked_project(project["_dir"]):
            target = get_link_target(project["_dir"])
            print(f"Linked to:   {target or 'unknown'}")
    except ImportError:
        pass
    return 0


# ---------------------------------------------------------------------------
# wtf-specific meta-commands: mode, new, add
# ---------------------------------------------------------------------------


def _mode_parser_factory(subparsers):
    """Register `wtf mode` with status/switch subcommands."""
    mode_parser = subparsers.add_parser(
        "mode", help="Show or toggle dev/publish mode"
    )
    mode_sub = mode_parser.add_subparsers(dest="mode_command")

    mode_status = mode_sub.add_parser("status", help="Show tool modes")
    mode_status.add_argument(
        "tool", nargs="?", default=None,
        help="Tool name (optional, show all if omitted)",
    )
    mode_status.add_argument("--kit", "-k", help="Filter by kit")
    mode_status.set_defaults(_meta="mode_status")

    mode_switch = mode_sub.add_parser("switch", help="Toggle dev/publish mode")
    mode_switch.add_argument("tool", help="Tool name to switch")
    mode_switch.add_argument(
        "--path", "-p",
        help="Path to local source repo (for dev mode)",
    )
    mode_switch.add_argument(
        "--dev", action="store_true",
        help="Force switch to dev mode",
    )
    mode_switch.add_argument(
        "--publish", action="store_true",
        help="Force switch to publish mode",
    )
    mode_switch.add_argument(
        "--url",
        help="Remote URL for submodule (reads from manifest if not given)",
    )
    mode_switch.add_argument(
        "--force", action="store_true",
        help="Bypass the dirty-tree safety check (DATA LOSS: any "
             "uncommitted work in the tool directory is destroyed).",
    )
    mode_switch.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without doing it",
    )
    mode_switch.set_defaults(_meta="mode_switch")

    # Bare `wtf mode` → status
    mode_parser.set_defaults(_meta="mode_status")


def _mode_status_handler(args, engine, projects, kits, project_root):
    from dazzlecmd_lib.mode import cmd_status
    tool_filter = getattr(args, "tool", None)
    kit_filter = getattr(args, "kit", None)
    return cmd_status(
        projects, project_root,
        tool_filter=tool_filter, kit_filter=kit_filter,
        tools_dir=engine.tools_dir, command=engine.command,
    )


def _mode_switch_handler(args, engine, projects, kits, project_root):
    from dazzlecmd_lib.mode import cmd_switch
    force_mode = None
    if getattr(args, "dev", False):
        force_mode = "dev"
    elif getattr(args, "publish", False):
        force_mode = "publish"
    return cmd_switch(
        tool_name=args.tool,
        projects=projects,
        project_root=project_root,
        dev_path=getattr(args, "path", None),
        force_mode=force_mode,
        dry_run=getattr(args, "dry_run", False),
        url=getattr(args, "url", None),
        force=getattr(args, "force", False),
        tools_dir=engine.tools_dir, command=engine.command, schema=None,
    )


def _new_parser_factory(subparsers):
    p = subparsers.add_parser("new", help="Create a new tool project")
    p.add_argument("name", help="Tool name")
    p.add_argument(
        "--namespace", "-n", default="core",
        help="Namespace (default: core)",
    )
    p.add_argument(
        "--simple", action="store_true",
        help="Add TODO.md and NOTES.md",
    )
    p.add_argument(
        "--full", action="store_true",
        help="Add ROADMAP.md, private/claude/, tests/",
    )
    p.add_argument(
        "--description", "-d", default="",
        help="Tool description",
    )
    p.add_argument(
        "--language", "-l", default="python",
        help="Primary language (default: python)",
    )
    p.set_defaults(_meta="new")


def _new_handler(args, engine, projects, kits, project_root):
    """Create a new tool project with progressive scaffolding."""
    name = args.name
    namespace = args.namespace
    description = args.description or f"A new wtf-windows diagnostic tool: {name}"
    language = args.language

    tools_dir = os.path.join(project_root, "tools", namespace)
    tool_dir = os.path.join(tools_dir, name)

    if os.path.exists(tool_dir):
        if args.simple or args.full:
            return _layer_extras(tool_dir, name, args)
        print(
            f"Error: Project '{namespace}/{name}' already exists at {tool_dir}",
            file=sys.stderr,
        )
        return 1

    os.makedirs(tool_dir, exist_ok=True)

    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": description,
        "namespace": namespace,
        "language": language,
        "platform": "windows",
        "runtime": {
            "type": "python",
            "entry_point": "main",
            "script_path": f"{name.replace('-', '_')}.py",
        },
        "pass_through": False,
        "taxonomy": {
            "category": "windows-diagnostics",
            "tags": [],
        },
        "diagnostics": {
            "event_logs": [],
            "required_privileges": "user",
            "supports_history": False,
            "supports_ai": False,
        },
    }

    manifest_path = os.path.join(tool_dir, ".wtf.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        f.write("\n")

    script_name = f"{name.replace('-', '_')}.py"
    script_path = os.path.join(tool_dir, script_name)

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    tmpl_path = os.path.join(template_dir, "python_tool.py.tmpl")
    if os.path.isfile(tmpl_path):
        with open(tmpl_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("{name}", name)
        content = content.replace("{description}", description)
    else:
        content = _default_python_template(name, description)

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Created project: {namespace}/{name}")
    print(f"  {tool_dir}/")
    print(f"  - .wtf.json")
    print(f"  - {script_name}")

    if args.simple or args.full:
        _layer_extras(tool_dir, name, args)

    return 0


def _layer_extras(tool_dir, name, args):
    """Add extra files to an existing project."""
    added = []
    if args.simple or args.full:
        for filename in ["TODO.md", "NOTES.md"]:
            filepath = os.path.join(tool_dir, filename)
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# {filename.replace('.md', '')} - {name}\n\n")
                added.append(filename)
    if args.full:
        roadmap = os.path.join(tool_dir, "ROADMAP.md")
        if not os.path.exists(roadmap):
            with open(roadmap, "w", encoding="utf-8") as f:
                f.write(
                    f"# Roadmap - {name}\n\n## Planned\n\n"
                    f"## In Progress\n\n## Done\n\n"
                )
            added.append("ROADMAP.md")
        for subdir in ["private/claude", "tests"]:
            dirpath = os.path.join(tool_dir, subdir)
            if not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
                added.append(f"{subdir}/")
    if added:
        print(f"  Added: {', '.join(added)}")
    return 0


def _default_python_template(name, description):
    """Fallback Python tool template when template file is not found."""
    return f'''"""
{name} - {description}
"""

import sys


def main(argv=None):
    """Entry point for {name}."""
    if argv is None:
        argv = sys.argv[1:]

    print(f"{name}: not yet implemented")
    print(f"Arguments: {{argv}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _add_parser_factory(subparsers):
    p = subparsers.add_parser("add", help="Import an existing tool/repo")
    p.add_argument(
        "--repo", "-r", required=True,
        help="Path to source repo (or URL in future)",
    )
    p.add_argument(
        "--namespace", "-n", default="core",
        help="Namespace (default: core)",
    )
    p.add_argument("--name", help="Override tool name")
    p.add_argument(
        "--link", action="store_true",
        help="Create symlink to source (editable install)",
    )
    p.add_argument("--kit", "-k", help="Register in this kit")
    p.set_defaults(_meta="add")


def _add_handler(args, engine, projects, kits, project_root):
    """Import an existing repo as a wtf-windows tool."""
    from wtf_windows.importer import add_from_local

    repo_path = args.repo
    namespace = args.namespace
    tools_dir = os.path.join(project_root, "tools")

    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    if not os.path.isdir(repo_path):
        print(f"Error: '{repo_path}' is not a directory", file=sys.stderr)
        return 1

    link_mode = "link" if args.link else "copy"
    result = add_from_local(
        source_path=repo_path,
        tools_dir=tools_dir,
        namespace=namespace,
        link_mode=link_mode,
        tool_name=args.name,
    )
    if result is None:
        return 1

    mode_desc = "Linked" if result["link_mode"] in ("symlink", "junction") else "Copied"
    print(f"{mode_desc}: {result['namespace']}:{result['name']}")
    if result["link_mode"] in ("symlink", "junction"):
        print(f"  {result['link_mode']} -> {result['source_path']}")
    print(f"  Run: wtf {result['name']} --help")

    if args.kit:
        _register_in_kit(project_root, args.kit, result["namespace"], result["name"])
    return 0


def _register_in_kit(project_root, kit_name, namespace, tool_name):
    """Add a tool reference to a kit's tools array."""
    kits_dir = os.path.join(project_root, "kits")
    kit_file = os.path.join(kits_dir, f"{kit_name}.kit.json")
    if not os.path.isfile(kit_file):
        print(f"  Warning: Kit '{kit_name}' not found at {kit_file}", file=sys.stderr)
        return
    try:
        with open(kit_file, "r", encoding="utf-8") as f:
            kit = json.load(f)
        qualified = f"{namespace}:{tool_name}"
        if qualified not in kit.get("tools", []):
            kit.setdefault("tools", []).append(qualified)
            with open(kit_file, "w", encoding="utf-8") as f:
                json.dump(kit, f, indent=4)
                f.write("\n")
            print(f"  Registered in kit: {kit_name}")
        else:
            print(f"  Already in kit: {kit_name}")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Warning: Could not update kit: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Categorized help epilog (diagnostic-tool badges + management/dev sections)
# ---------------------------------------------------------------------------


_RESERVED_COMMANDS = {
    "new", "add", "list", "info", "kit", "search",
    "build", "tree", "version", "enhance", "graduate", "mode",
}


def _build_categorized_help(projects):
    """Build a categorized command listing for the help epilog."""
    namespaces = {}
    for project in projects:
        name = project["name"]
        if name in _RESERVED_COMMANDS:
            continue
        ns = project.get("namespace", "other")
        namespaces.setdefault(ns, []).append(project)

    lines = []
    if namespaces:
        lines.append("diagnostic tools:")
        for ns in sorted(namespaces.keys()):
            tools = namespaces[ns]
            if len(namespaces) > 1:
                lines.append(f"  [{ns}]")
            for project in sorted(tools, key=lambda p: p["name"]):
                name = project["name"]
                desc = project.get("description", "")
                diag = project.get("diagnostics", {})
                badges = []
                if diag.get("supports_ai"):
                    badges.append("AI")
                if diag.get("supports_history"):
                    badges.append("history")
                privs = diag.get("required_privileges", "")
                if privs == "admin":
                    badges.append("admin")
                badge_str = f"  [{', '.join(badges)}]" if badges else ""
                if ". " in desc:
                    desc = desc[:desc.index(". ") + 1]
                elif "? " in desc:
                    desc = desc[:desc.index("? ") + 1]
                max_desc = 52
                if len(desc) > max_desc:
                    desc = desc[:max_desc - 3] + "..."
                lines.append(f"  {name:<16}  {desc}{badge_str}")
    else:
        lines.append("diagnostic tools:")
        lines.append("  (none installed -- use 'wtf add' to import a tool)")

    lines.append("")
    lines.append("management:")
    for cmd, desc in [
        ("list", "List available diagnostic tools"),
        ("info <tool>", "Show detailed info about a tool"),
        ("mode", "Show or toggle dev/publish mode"),
        ("kit", "Manage tool kits"),
    ]:
        lines.append(f"  {cmd:<16}  {desc}")

    lines.append("")
    lines.append("development:")
    for cmd, desc in [
        ("new <name>", "Create a new tool project"),
        ("add", "Import an existing tool/repo"),
    ]:
        lines.append(f"  {cmd:<16}  {desc}")

    lines.append("")
    lines.append("examples:")
    lines.append("  wtf restarted              Why did my PC restart?")
    lines.append("  wtf restarted --ai         With AI-enhanced analysis")
    lines.append("  wtf restarted history      Restart timeline")
    lines.append("  wtf list                   Show all available tools")
    lines.append("  wtf info restarted         Detailed tool info")

    lines.append("")
    lines.append("Run 'wtf <tool> --help' for tool-specific options.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main():
    """Main entry point for wtf-windows CLI.

    As of v0.1.4-alpha (Phase 3.5 T1-M2), wtf-windows consumes
    dazzlecmd-lib's declarative-config path: identity, layout, and
    meta-command policy live in ``aggregator.json`` and are read via
    ``AggregatorEngine.from_project()``. The imperative customizations
    below (domain-enriched list/info handlers, the mode/new/add
    meta-commands, the categorized help epilog) stay in code because
    they ARE code -- handler functions can't be expressed in JSON.
    ``aggregator.json``'s ``enabled_meta_commands`` already excludes
    ``tree``/``setup``, so the old post-construction unregister calls
    are gone; mode forks were retired in favor of ``dazzlecmd_lib.mode``.
    """
    from dazzlecmd_lib.aggregator_config import find_aggregator_root
    from dazzlecmd_lib.mode import get_cached_manifest

    # Hook wtf's cached-manifest fallback into the library's loader so that
    # mode-switched tools (manifest absent from disk, cached in mode state)
    # are still discovered.
    set_manifest_cache_fn(get_cached_manifest)

    # Anchor discovery to THIS package's location, not cwd. Anchoring to
    # cwd would make `wtf` impersonate whatever aggregator the user is
    # standing in (e.g., running `wtf` from inside the dazzlecmd tree).
    # The entry point's identity is fixed by which package it is.
    project_root = find_aggregator_root(os.path.dirname(os.path.abspath(__file__)))
    if project_root is None:
        print(
            "Error: could not find aggregator.json. The wtf-windows package "
            "must be installed alongside its project tree.",
            file=sys.stderr,
        )
        return 1

    engine = AggregatorEngine.from_project(
        project_root,
        version_info=(DISPLAY_VERSION, __version__),
        is_root=True,
    )

    # Override library defaults for domain-enriched output
    engine.meta_registry.override("list", handler=_wtf_list_handler)
    engine.meta_registry.override("info", handler=_wtf_info_handler)

    # Register wtf-specific meta-commands
    engine.meta_registry.register(
        "mode", _mode_parser_factory,
        # Root meta handler: bare `wtf mode` → mode_status.
        # Subcommands (`wtf mode status`, `wtf mode switch`) set _meta
        # directly via their parser factories, routed via registry dispatch.
        _mode_status_handler,
    )
    # Register sub-meta handlers for mode's subcommands
    engine.meta_registry.register(
        "mode_status", lambda subs: None, _mode_status_handler,
    )
    engine.meta_registry.register(
        "mode_switch", lambda subs: None, _mode_switch_handler,
    )

    engine.meta_registry.register("new", _new_parser_factory, _new_handler)
    engine.meta_registry.register("add", _add_parser_factory, _add_handler)

    # Custom categorized help epilog
    engine.epilog_builder = _build_categorized_help

    return engine.run()


if __name__ == "__main__":
    sys.exit(main())
