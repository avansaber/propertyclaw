# PropertyClaw

Property management for [ERPClaw](https://github.com/avansaber/erpclaw). <!-- SYNC:value:group.propertyclaw.module_count -->2<!-- /SYNC --> modules covering residential and commercial real estate. <!-- SYNC:value:group.propertyclaw.total_actions -->133<!-- /SYNC --> actions total with real double-entry GL, trust accounting, and compliance features.

## Modules

### Residential (`propertyclaw`)
Property management for US landlords (20-500 units). <!-- SYNC:value:module.propertyclaw.actions -->103<!-- /SYNC --> actions across 5 domains -- properties, leases, tenants, maintenance, and trust accounting. FCRA-compliant screening, state-specific late fees, and 1099 reporting.

### Commercial (`propertyclaw-commercial`)
Commercial real estate management. NNN (triple-net) leases, CAM reconciliation, and tenant improvements. <!-- SYNC:value:module.propertyclaw-commercial.actions -->30<!-- /SYNC --> actions across 3 domains. Requires the residential core module.

## Installation

Requires [ERPClaw](https://github.com/avansaber/erpclaw) core. Install residential first, then add commercial:

```
install-module propertyclaw
install-module propertyclaw-commercial
```

Or ask naturally:

```
"I manage rental properties"
"Set me up for commercial real estate"
```

## Links

- **Source**: [github.com/avansaber/propertyclaw](https://github.com/avansaber/propertyclaw)
- **ERPClaw Core**: [github.com/avansaber/erpclaw](https://github.com/avansaber/erpclaw)
- **Website**: [erpclaw.ai](https://www.erpclaw.ai)

## License

GNU General Public License v3 -- Copyright (c) 2026 AvanSaber / Nikhil Jathar
