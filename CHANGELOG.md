# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/djdarcy/wtf-windows/compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/djdarcy/wtf-windows/releases/tag/v0.1.0-alpha
