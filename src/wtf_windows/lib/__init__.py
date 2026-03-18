"""
Shared infrastructure library for wtf-windows diagnostic tools.

Provides THAC0 output management, PowerShell runner, and AI analysis
pipeline. Tools import from sub-packages:

    from wtf_windows.lib.log_lib import init_output, get_output
    from wtf_windows.lib.ps1.runner import run_ps1, is_admin
    from wtf_windows.lib.ai.analyzer import analyze

IMPORTANT -- TEMPORARY RESIDENCE NOTICE:
    log_lib, core_lib, and help_lib are intended to become independent
    DazzleLib packages. They are guests in wtf_windows, not owned by it.
    They must not import from wtf_windows or any wtf_windows subpackage.

    When extracted, only import paths change. No logic changes are needed.

    Extraction checklist:
      1. Create standalone package (e.g., pip install dazzle-log-lib)
      2. Change "from wtf_windows.lib.log_lib" -> "from dazzle_log_lib"
         in all consuming code
      3. Add dazzle-log-lib to pyproject.toml dependencies
      4. Remove the local copy from src/wtf_windows/lib/
      5. Done.

    Invariant: grep -r "from wtf_windows" src/wtf_windows/lib/ returns nothing.
"""
