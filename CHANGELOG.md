# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.5-alpha] - 2026-05-26

Phase 3.5 T1-M2: adopt dazzlecmd-lib's declarative-config path and retire wtf's forked mode logic. Where 0.1.4-alpha moved engine construction onto `dazzlecmd-lib`, this commit completes the migration -- wtf no longer carries any forked library code, and its identity/layout/policy are declared in `aggregator.json` instead of hardcoded constructor kwargs.

### Added

- `aggregator.json` at the repo root. Declares wtf's identity (`name: "wtf-windows"`, `command: "wtf"`), layout (`tools_dir: "tools"`, `kits_dir: "kits"`, `manifest_name: ".wtf.json"`), meta-command policy (`enabled_meta_commands: [list, info, kit, version]`; `extra_reserved_commands: [mode, new, add, enhance, graduate]`), schema (`remote_url_paths: [source.url]` -- matches wtf's actual tool manifests, which use `source.url` + `lifecycle.graduated_to`), and discovery patterns. Read by `AggregatorEngine.from_project()`.
- `--force` flag on `wtf mode switch` -- bypasses the new dirty-tree safety gate (DATA LOSS escape hatch). wtf inherits the T1-E safety primitive from `dazzlecmd-lib` v0.6.13: `wtf mode switch` now refuses to destroy a tool directory with uncommitted changes unless `--force` is passed. wtf previously had NO dirty-tree protection.
- `tests/test_smoke.py` -- wtf's first automated tests (7 subprocess smoke tests). wtf had zero test coverage before this. Guards: version identifies as wtf-windows (not the impersonation bug), list/info/mode-status run, aggregator.json loads, `mode switch --help` exposes `--force`. Two of these would have caught bugs found during this migration.

### Changed

- **`src/wtf_windows/cli.py:main()` rewritten** onto `find_aggregator_root() + AggregatorEngine.from_project()`. The hardcoded `AggregatorEngine(name=..., command=..., tools_dir=..., ...)` constructor kwargs are gone -- those values live in `aggregator.json`. The imperative customizations stay in code (they ARE code): the domain-enriched `_wtf_list_handler` / `_wtf_info_handler` overrides, the `mode`/`new`/`add` meta-command registrations, and the categorized help epilog. `find_aggregator_root()` is anchored to the package's own `__file__` location (NOT cwd) so `wtf` always resolves to the wtf-windows project regardless of the directory it's invoked from.
- The mode handlers (`_mode_status_handler`, `_mode_switch_handler`) now import from `dazzlecmd_lib.mode` and thread `tools_dir=engine.tools_dir`, `command=engine.command` (and `force` / `schema=None` for switch).
- `pyproject.toml` -- `dazzlecmd-lib` dependency bumped from `>=0.1.0` to `>=0.6.13,<1.0` (the parameterized `mode` module + `from_project()` + `find_aggregator_root()` land in 0.6.13).

### Fixed

- `wtf info <tool>` crashed with `TypeError: render_info() missing 1 required positional argument: 'engine'`. `_wtf_info_handler` delegated to `dazzlecmd_lib.default_meta_commands.render_info(args, projects)` with a stale 2-arg signature; the library's signature gained `engine`. Pre-existing bug (undetected because wtf had no tests), surfaced and fixed during T1-M2 end-to-end verification. Now passes `engine`.

### Removed

- **`src/wtf_windows/mode.py` deleted** (619 LOC). wtf's forked copy of the mode subsystem -- a pre-parameterization snapshot of dazzlecmd's mode logic that hardcoded `"tools/"` and `"wtf"`. All of it now lives in `dazzlecmd_lib.mode` (parameterized in lib v0.6.10-0.6.12), consumed via the thin handlers in `cli.py`. The library version is a strict superset (adds the dirty-tree safety gate + schema decoupling wtf's fork lacked).
- `_find_wtf_project_root()` helper removed -- replaced by `dazzlecmd_lib.aggregator_config.find_aggregator_root()`.

## [0.1.4-alpha] - 2026-04-18

### Added

- **Adopted `dazzlecmd-lib` as the engine.** wtf-windows is the first
  third-party production adopter of the `dazzlecmd-lib` library
  (alongside dazzlecmd itself, which dogfoods it). The library powers
  kit discovery, tool registration, FQCN resolution, runtime dispatch,
  config management, and user-override integration. Adopting the
  library removes ~400 LOC of duplicated engine code from wtf-windows
  and ensures bug fixes and feature improvements land in wtf
  automatically with each `dazzlecmd-lib` upgrade.
- `pyproject.toml` declares `dazzlecmd-lib>=0.1.0` as a runtime
  dependency.

### Changed

- **`src/wtf_windows/cli.py` rewritten** around `AggregatorEngine` +
  `MetaCommandRegistry`. The CLI shape is unchanged from the user's
  perspective:
  - Tools still dispatch via `wtf <tool>` (e.g. `wtf locked`,
    `wtf restarted history`)
  - `wtf list` still shows domain-enriched output with
    `[AI, history, admin]` diagnostic badges (implemented as a registry
    handler override)
  - `wtf info <tool>` still appends wtf-specific diagnostics (event
    logs, privileges, AI / history support, link status)
  - `wtf kit list`, `wtf kit status`, `wtf version` use the library
    defaults
  - `wtf mode status` / `wtf mode switch` registered as wtf-specific
    meta-commands via `engine.meta_registry.register(...)`
  - `wtf new <name>` / `wtf add` registered the same way
  - Categorized help epilog (diagnostic tools / management /
    development / examples sections) preserved via
    `engine.epilog_builder`

  Internally, the meta-command registry flow replaces the previous
  hand-written parser / dispatch code.

### Removed

- **`src/wtf_windows/loader.py`** (392 LOC). Replaced by
  `dazzlecmd_lib.loader` (discovery) and `dazzlecmd_lib.registry`
  (runtime dispatch). All kit / project discovery and Python / shell /
  script / binary / node / docker runner factories now come from the
  library.
- `_cmd_list`, `_cmd_kit_list`, `_cmd_kit_status`, `_cmd_version`
  handlers: inherited from `dazzlecmd_lib.default_meta_commands`;
  domain-specific overrides (list, info) remain in `cli.py`.

### Fixed

- wtf's mode-cache fallback still works during discovery. wtf's
  `cli.py` now explicitly hooks `wtf_windows.mode.get_cached_manifest`
  into the library's `set_manifest_cache_fn(fn)` hook at `main()`
  startup.
- Python package-mode tool dispatch (tools with `__init__.py` +
  relative imports, e.g. `locked`, `restarted`) works via the library's
  fixed `make_python_runner` -- places parent of tool_dir on sys.path
  and imports as `<package_name>.<script_stem>`. (Library fix ships in
  `dazzlecmd-lib` v0.7.24; wtf depends on it.)

### Notes

- This is an internal-architecture change. The user-facing CLI is
  identical to v0.1.3-alpha. No documented command changes; no
  migration needed.
- wtf-windows remains dispatchable as an embedded kit inside dazzlecmd
  via the `projects/wtf/` submodule. The 3-tier nesting case
  (`dz wtf:core:locked`) still works; validated end-to-end by the
  tester-agent sweep accompanying dazzlecmd v0.7.24.
- Future work: replace the temporary `_override_tools_dir` /
  `_override_manifest` fields in dazzlecmd's `kits/wtf.kit.json` with
  direct declarations in wtf's own `kits/core.kit.json` (tracked in
  dazzlecmd repo).

## [0.1.3-alpha] - 2026-04-02

### Added
- git-repokit-common subtree at `scripts/` with shared tooling:
  gh_issue_full.py, sync-versions.py, git hooks, session tools
- `[tool.repokit-common]` config in pyproject.toml for version management
- Git hooks: pre-commit (version sync, private file protection),
  post-commit (hash refresh), pre-push (syntax check, tests)
- sync-versions.py: `tag-format` config option -- projects can choose
  `"human"` (v0.1.3-alpha) or `"pep440"` (v0.1.3a1, default). Fixes
  --check false positives and CHANGELOG link corruption for pre-release
  projects using human-readable git tags.

### Fixed
- pre-push hook: package detection missed src/ layout projects; syntax
  check failed on empty globs; test runner blocked push when no tests
  existed yet

### Changed
- `__version__` now includes git metadata (branch, build, date, hash)
  via sync-versions.py, auto-updated by pre-commit hook

## [0.1.2-alpha] - 2026-04-02

### Added
- Kit manifest self-describing fields: `tools_dir` and `manifest` in
  `kits/core.kit.json` for DazzleCMD kit-as-repo discovery
- DazzleCMD Integration section in CLAUDE.md with migration context

### Fixed
- `importer.py`: replaced `cmd.exe /c mklink` with PowerShell
  `New-Item -ItemType Junction` -- cmd.exe fails silently from bash/WSL

### Changed
- Updated restarted submodule: `.wtf.json` now committed in wtf-restarted
  repo (was untracked, blocking kit discovery)

### Cross-references
- DazzleTools/dazzlecmd#7, #13
- Design: `2026-04-02__19-54-21__dev-workflow_dazzlecmd-integration-gaps-and-design-problems.md`

## [0.1.1-alpha] - 2026-03-19

### Added
- **wtf-locked**: first embedded diagnostic tool
  - Diagnoses lock causes: RDP takeover, unauthorized login, screensaver,
    inactivity, GPO, sleep/wake, manual lock
  - Security-first verdict ranking (suspicious events surfaced first)
  - Concurrent login detection: who logged in, from where, what IP
  - Winlogon type 4 (REMOTE_DISCONNECT) as lock-equivalent event --
    works without audit policy enabled
  - Three-tier Rich output with panels, tables, and color-coded verdicts
  - THAC0 channel-gated rendering with render=lambda: closures
  - Lock-anchored lookback (auto-extends to find most recent lock)
  - --tier, --no-page, --ai, --ai-only, --ai-verbose, --ai-refresh flags
  - Rich spinner during PS1 execution
  - AI prompt template with security-focused analysis
  - Event deduplication for Winlogon subscriber notifications
- Shared library (`src/wtf_windows/lib/`):
  - THAC0 libs (log_lib, core_lib, help_lib) -- 13 files, temporary
    residents pending DazzleLib extraction
  - ps1/runner.py: generalized PowerShell runner with caller-supplied ps1_dir
  - ai/analyzer.py: generalized AI pipeline with caller-supplied fingerprint_fn,
    prompt_path, cache_dir, tool_name
  - ai/backends/: claude, codex, prompt-only (claude uses stdin for prompts
    >8KB to avoid Windows command-line length limit)
- Tool documentation: docs/tools/core/ with overview docs for restarted
  and locked; tool-local docs at tools/core/locked/docs/event-reference.md

### Fixed
- **RDP lock misclassification**: locks caused by RDP session reconnects
  (same user from another machine) were reported as UNKNOWN_LOCK instead
  of RDP_SELF_RECONNECT when Security audit was enabled. Root cause:
  Security 4800 events lack Winlogon's lock_type metadata; fix enriches
  Security events from Winlogon and adds TerminalServices-based fallback
  classification (Rule 8) that detects RDP console displacement directly
- Tier 1 now shows "RDP Session Flow" with surrounding TerminalServices
  events for RDP-related verdicts, so users can see the full
  disconnect/reconnect sequence
- Claude CLI backend: prompts >8KB piped via stdin (-p "-") to avoid
  WinError 206 on Windows
- Winlogon event deduplication: multiple subscribers per lock no longer
  produce duplicate lock sessions

### Changed
- loader.py: embedded tools with __init__.py run as packages via subprocess
  with PYTHONPATH (supports relative imports)
- loader.py: pass_through checked in both top-level and runtime dict

## [0.1.0-alpha] - 2026-03-17

### Added
- Initial project scaffold based on [DazzleCMD](https://github.com/DazzleTools/dazzlecmd) architectural pattern
- Dispatch infrastructure: `wtf <tool> [args]` routes to diagnostic tools
- Manifest-driven discovery via `.wtf.json` files with `diagnostics` extension
- Kit system with `core.kit.json` (always active)
- Dev/publish mode toggle (`wtf mode switch`) for symlink <-> submodule
- Tool import (`wtf add --repo <path> --link`)
- Tool scaffolding (`wtf new <name>`)
- `wtf-restarted` integrated as first git submodule (`tools/core/restarted/`)
- Pass-through dispatch: `wtf restarted` invokes `python -m wtf_restarted`
- Help output with diagnostic tool section, capability badges `[AI, history]`, management/development sections, and examples
- `wtf list`, `wtf info`, `wtf kit`, `wtf mode status` meta-commands
- README, CLAUDE.md, CONTRIBUTING.md

### Architecture
- Cloned from DazzleCMD with adaptations:
  - `projects/` renamed to `tools/` (domain-specific)
  - `.dazzlecmd.json` renamed to `.wtf.json`
  - Manifest extended with `diagnostics` section (event_logs, required_privileges, audit_policies, supports_ai, supports_history)
  - `pass_through` supported in both top-level and `runtime` dict
  - Module invocation (`python -m`) for graduated packages
  - Default platform: `windows` (not `cross-platform`)

### Cross-references
- GitHub: djdarcy/wtf-restarted#27, DazzleTools/dazzlecmd#13
- Design: `2026-03-16__16-24-35__dev-workflow_wtf-windows-umbrella-architecture.md`

[Unreleased]: https://github.com/djdarcy/wtf-windows/compare/v0.1.5-alpha...HEAD
[0.1.3-alpha]: https://github.com/djdarcy/wtf-windows/compare/v0.1.2-alpha...v0.1.3-alpha
[0.1.2-alpha]: https://github.com/djdarcy/wtf-windows/compare/v0.1.1-alpha...v0.1.2-alpha
[0.1.1-alpha]: https://github.com/djdarcy/wtf-windows/compare/v0.1.0-alpha...v0.1.1-alpha
[0.1.0-alpha]: https://github.com/djdarcy/wtf-windows/releases/tag/v0.1.0-alpha
