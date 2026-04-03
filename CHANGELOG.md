# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/djdarcy/wtf-windows/compare/v0.1.3-alpha...HEAD
[0.1.3-alpha]: https://github.com/djdarcy/wtf-windows/compare/v0.1.2-alpha...v0.1.3-alpha
[0.1.2-alpha]: https://github.com/djdarcy/wtf-windows/compare/v0.1.1-alpha...v0.1.2-alpha
[0.1.1-alpha]: https://github.com/djdarcy/wtf-windows/compare/v0.1.0-alpha...v0.1.1-alpha
[0.1.0-alpha]: https://github.com/djdarcy/wtf-windows/releases/tag/v0.1.0-alpha
