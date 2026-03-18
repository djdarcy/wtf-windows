"""Main CLI entry point for wtf-windows."""

import argparse
import json
import os
import sys

from wtf_windows._version import DISPLAY_VERSION, __version__
from wtf_windows.loader import (
    discover_kits,
    discover_projects,
    get_active_kits,
    resolve_entry_point,
)


# Reserved command names that cannot be used as tool names
RESERVED_COMMANDS = {
    "new", "add", "list", "info", "kit", "search",
    "build", "tree", "version", "enhance", "graduate", "mode",
}


def find_project_root():
    """Find the wtf-windows project root by navigating from __file__.

    Looks for the presence of both tools/ and kits/ directories.
    """
    # Start from the package location and go up
    current = os.path.dirname(os.path.abspath(__file__))

    # In installed mode: __file__ is in site-packages/wtf_windows/
    # In dev mode: __file__ is in src/wtf_windows/
    # Either way, we need to find tools/ and kits/ relative to the repo root
    for _ in range(5):  # Don't go more than 5 levels up
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        if os.path.isdir(os.path.join(current, "tools")) and os.path.isdir(
            os.path.join(current, "kits")
        ):
            return current

    return None


def build_parser(projects):
    """Build argparse parser with dynamic subparsers for discovered tools."""
    # Build categorized epilog for help display
    epilog = _build_categorized_help(projects)

    parser = argparse.ArgumentParser(
        prog="wtf",
        description="wtf-windows - Why is my Windows PC doing that? Many diagnostics, one command.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"wtf-windows {DISPLAY_VERSION} ({__version__})",
    )

    # Suppress default subparser listing -- we show our own categorized version
    subparsers = parser.add_subparsers(dest="command", metavar="<command>",
                                       help=argparse.SUPPRESS)

    # Register meta-commands (hidden from default help, shown in epilog)
    _register_meta_commands(subparsers)

    # Register discovered tool commands
    for project in projects:
        name = project["name"]
        if name in RESERVED_COMMANDS:
            print(
                f"Warning: Tool '{name}' conflicts with reserved command, skipping",
                file=sys.stderr,
            )
            continue

        desc = project.get("description", "")
        sub = subparsers.add_parser(
            name,
            help=desc,
            add_help=False,  # Let the tool handle its own --help
        )
        sub.set_defaults(_project=project)

    return parser


def _build_categorized_help(projects):
    """Build a categorized command listing for the help epilog."""
    # Group tools by namespace
    namespaces = {}
    for project in projects:
        name = project["name"]
        if name in RESERVED_COMMANDS:
            continue
        ns = project.get("namespace", "other")
        namespaces.setdefault(ns, []).append(project)

    lines = []

    # --- Diagnostic tools section ---
    if namespaces:
        lines.append("diagnostic tools:")

        for ns in sorted(namespaces.keys()):
            tools = namespaces[ns]
            if len(namespaces) > 1:
                lines.append(f"  [{ns}]")

            for project in sorted(tools, key=lambda p: p["name"]):
                name = project["name"]
                desc = project.get("description", "")

                # Build capability badges
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

                # Use first sentence only, then truncate if still too long
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

    # --- Management commands section ---
    lines.append("")
    lines.append("management:")
    mgmt_commands = [
        ("list", "List available diagnostic tools"),
        ("info <tool>", "Show detailed info about a tool"),
        ("mode", "Show or toggle dev/publish mode"),
        ("kit", "Manage tool kits"),
    ]
    for cmd, desc in mgmt_commands:
        lines.append(f"  {cmd:<16}  {desc}")

    lines.append("")
    lines.append("development:")
    dev_commands = [
        ("new <name>", "Create a new tool project"),
        ("add", "Import an existing tool/repo"),
    ]
    for cmd, desc in dev_commands:
        lines.append(f"  {cmd:<16}  {desc}")

    # --- Examples section ---
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


def _register_meta_commands(subparsers):
    """Register built-in meta-commands."""
    # wtf list
    list_parser = subparsers.add_parser("list", help="List available tools")
    list_parser.add_argument("--namespace", "-n", help="Filter by namespace")
    list_parser.add_argument("--kit", "-k", help="Filter by kit")
    list_parser.add_argument("--tag", "-t", help="Filter by tag")
    list_parser.add_argument("--platform", "-p", help="Filter by platform")
    list_parser.set_defaults(_meta="list")

    # wtf info <tool>
    info_parser = subparsers.add_parser("info", help="Show detailed info about a tool")
    info_parser.add_argument("tool", help="Tool name to inspect")
    info_parser.set_defaults(_meta="info")

    # wtf kit
    kit_parser = subparsers.add_parser("kit", help="Manage kits")
    kit_sub = kit_parser.add_subparsers(dest="kit_command")
    kit_list = kit_sub.add_parser("list", help="List available kits, or tools in a kit")
    kit_list.add_argument("name", nargs="?", default=None, help="Kit name to show tools for")
    kit_list.set_defaults(_meta="kit_list")
    kit_status = kit_sub.add_parser("status", help="Show active kits")
    kit_status.set_defaults(_meta="kit_status")
    kit_parser.set_defaults(_meta="kit")

    # wtf new <name>
    new_parser = subparsers.add_parser("new", help="Create a new tool project")
    new_parser.add_argument("name", help="Tool name")
    new_parser.add_argument("--namespace", "-n", default="core", help="Namespace (default: core)")
    new_parser.add_argument("--simple", action="store_true", help="Add TODO.md and NOTES.md")
    new_parser.add_argument("--full", action="store_true", help="Add ROADMAP.md, private/claude/, tests/")
    new_parser.add_argument("--description", "-d", default="", help="Tool description")
    new_parser.add_argument("--language", "-l", default="python", help="Primary language (default: python)")
    new_parser.set_defaults(_meta="new")

    # wtf add
    add_parser = subparsers.add_parser("add", help="Import an existing tool/repo")
    add_parser.add_argument("--repo", "-r", required=True,
                            help="Path to source repo (or URL in future)")
    add_parser.add_argument("--namespace", "-n", default="core",
                            help="Namespace (default: core)")
    add_parser.add_argument("--name", help="Override tool name")
    add_parser.add_argument("--link", action="store_true",
                            help="Create symlink to source (editable install)")
    add_parser.add_argument("--kit", "-k", help="Register in this kit")
    add_parser.set_defaults(_meta="add")

    # wtf mode
    mode_parser = subparsers.add_parser("mode", help="Toggle dev/publish mode")
    mode_sub = mode_parser.add_subparsers(dest="mode_command")

    mode_status = mode_sub.add_parser("status", help="Show tool modes")
    mode_status.add_argument("tool", nargs="?", default=None,
                             help="Tool name (optional, show all if omitted)")
    mode_status.add_argument("--kit", "-k", help="Filter by kit")
    mode_status.set_defaults(_meta="mode_status")

    mode_switch = mode_sub.add_parser("switch", help="Toggle dev/publish mode")
    mode_switch.add_argument("tool", help="Tool name to switch")
    mode_switch.add_argument("--path", "-p",
                             help="Path to local source repo (for dev mode)")
    mode_switch.add_argument("--dev", action="store_true",
                             help="Force switch to dev mode")
    mode_switch.add_argument("--publish", action="store_true",
                             help="Force switch to publish mode")
    mode_switch.add_argument("--url", help="Remote URL for submodule "
                             "(reads from manifest if not given)")
    mode_switch.add_argument("--dry-run", action="store_true",
                             help="Show what would happen without doing it")
    mode_switch.set_defaults(_meta="mode_switch")

    mode_parser.set_defaults(_meta="mode")

    # wtf version (alternate to --version)
    version_parser = subparsers.add_parser("version", help="Show version info")
    version_parser.set_defaults(_meta="version")


def dispatch_meta(args, projects, kits, project_root):
    """Handle built-in meta-commands."""
    meta = getattr(args, "_meta", None)

    if meta == "list":
        return _cmd_list(args, projects)
    elif meta == "info":
        return _cmd_info(args, projects)
    elif meta == "kit_list":
        return _cmd_kit_list(args, kits, projects)
    elif meta == "kit_status":
        return _cmd_kit_status(kits)
    elif meta == "kit":
        # bare "wtf kit" with no subcommand
        return _cmd_kit_list(args, kits, projects)
    elif meta == "new":
        return _cmd_new(args, project_root)
    elif meta == "add":
        return _cmd_add(args, project_root)
    elif meta == "mode_status":
        return _cmd_mode_status(args, projects, project_root)
    elif meta == "mode_switch":
        return _cmd_mode_switch(args, projects, project_root)
    elif meta == "mode":
        # bare "wtf mode" with no subcommand -- show status
        return _cmd_mode_status(args, projects, project_root)
    elif meta == "version":
        return _cmd_version()

    return 1


def _cmd_list(args, projects):
    """List available tools."""
    filtered = projects

    if args.namespace:
        filtered = [p for p in filtered if p.get("namespace") == args.namespace]
    if args.platform:
        filtered = [p for p in filtered if p.get("platform", "windows") == args.platform]
    if args.tag:
        filtered = [
            p for p in filtered
            if args.tag in p.get("taxonomy", {}).get("tags", [])
        ]
    if args.kit:
        filtered = [p for p in filtered if p.get("namespace") == args.kit]

    if not filtered:
        print("No tools found.")
        return 0

    # Table output
    name_width = max(len(p["name"]) for p in filtered)
    ns_width = max(len(p.get("namespace", "")) for p in filtered)

    header = f"  {'Name':<{name_width}}  {'Namespace':<{ns_width}}  Description"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for project in filtered:
        name = project["name"]
        ns = project.get("namespace", "")
        desc = project.get("description", "")
        if len(desc) > 60:
            desc = desc[:57] + "..."
        print(f"  {name:<{name_width}}  {ns:<{ns_width}}  {desc}")

    print(f"\n  {len(filtered)} tool(s) found")
    return 0


def _cmd_info(args, projects):
    """Show detailed info about a tool."""
    tool_name = args.tool
    matches = [p for p in projects if p["name"] == tool_name]

    if not matches:
        print(f"Tool '{tool_name}' not found. Use 'wtf list' to see available tools.")
        return 1

    if len(matches) > 1:
        print(f"Multiple tools named '{tool_name}':")
        for p in matches:
            print(f"  {p['namespace']}:{p['name']}")
        print(f"Use 'wtf info namespace:{tool_name}' to be specific.")
        return 1

    project = matches[0]
    print(f"Name:        {project['name']}")
    print(f"Namespace:   {project.get('namespace', 'unknown')}")
    print(f"Version:     {project.get('version', 'unknown')}")
    print(f"Description: {project.get('description', '')}")
    print(f"Platform:    {project.get('platform', 'windows')}")
    print(f"Language:    {project.get('language', 'unknown')}")

    runtime = project.get("runtime", {})
    print(f"Runtime:     {runtime.get('type', 'python')}")
    if runtime.get("script_path"):
        print(f"Script:      {runtime['script_path']}")
    if project.get("pass_through"):
        print(f"Pass-through: yes")

    taxonomy = project.get("taxonomy", {})
    if taxonomy.get("category"):
        print(f"Category:    {taxonomy['category']}")
    if taxonomy.get("tags"):
        print(f"Tags:        {', '.join(taxonomy['tags'])}")

    # Diagnostics section (wtf-windows specific)
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

    # Show link status
    from wtf_windows.importer import is_linked_project, get_link_target
    if is_linked_project(project["_dir"]):
        target = get_link_target(project["_dir"])
        print(f"Linked to:   {target or 'unknown'}")

    return 0


def _cmd_kit_list(args, kits, projects):
    """List available kits, or tools in a specific kit."""
    kit_name = getattr(args, "name", None)

    if not kits:
        print("No kits found.")
        return 0

    if kit_name:
        matching = [k for k in kits if k["name"] == kit_name]
        if not matching:
            print(f"Kit '{kit_name}' not found. Available kits:")
            for k in kits:
                print(f"  {k['name']}")
            return 1

        kit = matching[0]
        active = " (always active)" if kit.get("always_active") else ""
        print(f"Kit: {kit['name']}{active}")
        if kit.get("description"):
            print(f"  {kit['description']}")
        print()

        tool_refs = kit.get("tools", [])
        if not tool_refs:
            print("  No tools in this kit.")
            return 0

        for ref in sorted(tool_refs):
            if ":" in ref:
                ns, name = ref.split(":", 1)
            else:
                ns, name = "", ref

            match = [p for p in projects if p["name"] == name and (not ns or p.get("namespace") == ns)]
            if match:
                p = match[0]
                desc = p.get("description", "")
                if len(desc) > 55:
                    desc = desc[:52] + "..."
                platform = p.get("platform", "")
                print(f"  {name:<16} {platform:<16} {desc}")
            else:
                print(f"  {name:<16} {'':16} (not found)")

        print(f"\n  {len(tool_refs)} tool(s)")
        return 0

    for kit in kits:
        active = " (always active)" if kit.get("always_active") else ""
        tool_count = len(kit.get("tools", []))
        print(f"  {kit['name']:<16} {tool_count} tool(s){active}")
        if kit.get("description"):
            print(f"    {kit['description']}")
    return 0


def _cmd_kit_status(kits):
    """Show active kits summary."""
    active = get_active_kits(kits)
    print(f"Active kits: {len(active)}")
    for kit in active:
        tool_count = len(kit.get("tools", []))
        print(f"  {kit['name']}: {tool_count} tool(s)")
    return 0


def _cmd_version():
    """Show version info (alternate to --version flag)."""
    print(f"wtf-windows {DISPLAY_VERSION} ({__version__})")
    return 0


def _cmd_add(args, project_root):
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
        _register_in_kit(project_root, args.kit, result["namespace"],
                         result["name"])

    return 0


def _register_in_kit(project_root, kit_name, namespace, tool_name):
    """Add a tool reference to a kit's tools array."""
    kits_dir = os.path.join(project_root, "kits")
    kit_file = os.path.join(kits_dir, f"{kit_name}.kit.json")

    if not os.path.isfile(kit_file):
        print(f"  Warning: Kit '{kit_name}' not found at {kit_file}",
              file=sys.stderr)
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


def _cmd_mode_status(args, projects, project_root):
    """Show mode status for tools."""
    from wtf_windows.mode import cmd_status
    tool_filter = getattr(args, "tool", None)
    kit_filter = getattr(args, "kit", None)
    return cmd_status(projects, project_root, tool_filter=tool_filter,
                      kit_filter=kit_filter)


def _cmd_mode_switch(args, projects, project_root):
    """Toggle a tool between dev and publish mode."""
    from wtf_windows.mode import cmd_switch

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
    )


def _cmd_new(args, project_root):
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
        print(f"Error: Project '{namespace}/{name}' already exists at {tool_dir}")
        return 1

    os.makedirs(tool_dir, exist_ok=True)

    # Create .wtf.json manifest
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

    # Create starter script
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
                f.write(f"# Roadmap - {name}\n\n## Planned\n\n## In Progress\n\n## Done\n\n")
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


def dispatch_tool(project, argv):
    """Dispatch to a tool's entry point."""
    runner = resolve_entry_point(project)
    if runner is None:
        print(f"Error: Could not resolve entry point for '{project['name']}'", file=sys.stderr)
        return 1

    try:
        return runner(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error running '{project['name']}': {exc}", file=sys.stderr)
        return 1


def main():
    """Main entry point for wtf-windows CLI."""
    project_root = find_project_root()

    if project_root is None:
        parser = build_parser([])
        if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
            print(f"wtf-windows {DISPLAY_VERSION} ({__version__})")
            return 0
        parser.print_help()
        return 0

    # Discover kits and projects
    kits_dir = os.path.join(project_root, "kits")
    tools_dir = os.path.join(project_root, "tools")

    kits = discover_kits(kits_dir)
    active_kits = get_active_kits(kits)
    projects = discover_projects(tools_dir, active_kits)

    # Build parser with discovered tools
    parser = build_parser(projects)

    # Handle no arguments
    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    # For tool commands, we need to separate wtf args from tool args
    command_name = sys.argv[1]

    # Check if it's a meta-command
    meta_commands = {"list", "info", "kit", "new", "version", "add", "mode"}
    if command_name in meta_commands or command_name.startswith("-"):
        args = parser.parse_args()
        if hasattr(args, "_meta"):
            return dispatch_meta(args, projects, kits, project_root)
        return 0

    # Check if it's a tool command
    tool_matches = [p for p in projects if p["name"] == command_name]
    if tool_matches:
        project = tool_matches[0]
        tool_argv = sys.argv[2:]
        return dispatch_tool(project, tool_argv)

    # Unknown command -- try argparse for error message
    args = parser.parse_args()
    return 0
