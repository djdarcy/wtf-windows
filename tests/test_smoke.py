"""Smoke tests for wtf-windows after the T1-M2 dazzlecmd-lib migration.

wtf-windows had ZERO automated tests before v0.1.4-alpha. These were
added alongside the migration that deleted the 619-line forked mode.py
and rewired main() onto dazzlecmd-lib's declarative-config path
(aggregator.json + AggregatorEngine.from_project()).

They are deliberately subprocess-based: they invoke the real CLI via
`python -m wtf_windows` so they exercise the actual entry point,
aggregator.json discovery, engine construction, and meta-command
dispatch end-to-end -- the integration the in-library unit tests can't
cover. Two of these would have caught real bugs found during the
migration:

- `test_version_identifies_as_wtf` guards the cross-aggregator
  impersonation class (v0.7.51 `find_aggregator_root` cwd-first bug,
  where `wtf` run from another aggregator's tree loaded the wrong
  aggregator.json).
- `test_info_does_not_crash` guards the stale `render_info()` 2-arg
  call that crashed `wtf info` (the lib's signature gained `engine`).
"""

import os
import subprocess
import sys


def _run(*args, cwd=None):
    """Invoke `python -m wtf_windows <args>` and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "wtf_windows", *args],
        capture_output=True, text=True, cwd=cwd,
    )


def test_import():
    """Package imports and exposes version metadata."""
    import wtf_windows
    assert hasattr(wtf_windows, "__version__")


def test_aggregator_json_loads():
    """aggregator.json at the repo root parses via the library loader."""
    from dazzlecmd_lib.aggregator_config import (
        find_aggregator_root, load_aggregator_config,
    )
    # Anchor to this package, mirroring how main() does it.
    import wtf_windows
    pkg_dir = os.path.dirname(os.path.abspath(wtf_windows.__file__))
    root = find_aggregator_root(pkg_dir)
    assert root is not None, "aggregator.json not found from package anchor"
    cfg = load_aggregator_config(root)
    assert cfg.name == "wtf-windows"
    assert cfg.command == "wtf"
    assert cfg.tools_dir == "tools"
    # find/git/etc. are NOT reserved here; mode/new/add/enhance/graduate are.
    assert "mode" in cfg.reserved_commands
    assert "new" in cfg.reserved_commands


def test_version_identifies_as_wtf():
    """`wtf --version` identifies as wtf-windows, never as dazzlecmd.

    Regression guard for the v0.7.51 cwd-first find_aggregator_root bug
    where an entry point could load a sibling aggregator's config.
    """
    result = _run("--version")
    assert result.returncode == 0
    assert "wtf-windows" in result.stdout.lower()
    assert "dazzlecmd" not in result.stdout.lower()


def test_list_runs():
    """`wtf list` runs and finds the diagnostic tools."""
    result = _run("list")
    assert result.returncode == 0
    assert "tool(s)" in result.stdout


def test_info_does_not_crash():
    """`wtf info restarted` renders without a traceback.

    Regression guard for the stale `render_info(args, projects)` call
    (the library signature is `render_info(args, projects, engine)`).
    """
    result = _run("info", "restarted")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Traceback" not in result.stderr
    assert "restarted" in result.stdout


def test_mode_status_runs():
    """`wtf mode status` runs via the library's parameterized cmd_status."""
    result = _run("mode", "status")
    assert result.returncode == 0
    assert "tool(s)" in result.stdout


def test_mode_switch_has_force_flag():
    """`wtf mode switch --help` exposes the T1-E `--force` safety flag."""
    result = _run("mode", "switch", "--help")
    assert result.returncode == 0
    assert "--force" in result.stdout
