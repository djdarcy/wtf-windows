# Core Kit

The core kit ships with every wtf-windows installation. These are the primary Windows diagnostic tools.

## Tools

| Tool | Command | Description | Privileges |
|------|---------|-------------|------------|
| [restarted](restarted.md) | `wtf restarted` | Why did my Windows PC restart? | User |
| [locked](locked.md) | `wtf locked` | Why did my Windows PC lock? | Admin |

## Design Principles

Core tools:
- **PS1-primary** -- PowerShell does event collection and system queries; Python wraps, renders, and orchestrates AI
- **Security-first** -- verdicts are ranked by threat level (suspicious events surfaced first)
- **Tiered disclosure** -- Tier 0 (answer), Tier 1 (evidence), Tier 2 (diagnostics) with interactive paging
- **Always useful** -- tools return results even with minimal data sources available

## Always Active

Core tools are loaded regardless of kit selection. They're registered in `kits/core.kit.json` with `"always_active": true`.
