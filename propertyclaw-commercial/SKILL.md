---
name: propertyclaw-commercial
version: 1.0.0
description: "Commercial real estate management: NNN leases, CAM reconciliation, tenant improvements"
author: AvanSaber / Nikhil Jathar
homepage: https://www.propertyclaw.ai
source: https://github.com/avansaber/propertyclaw-commercial
tier: 2
category: commercial
requires: [erpclaw-setup]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [commercial, nnn, triple-net, cam, tenant-improvement, lease, real-estate]
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
scripts:
  - scripts/db_query.py
actions:
  - add-nnn-lease
  - update-nnn-lease
  - get-nnn-lease
  - list-nnn-leases
  - add-expense-passthrough
  - list-expense-passthroughs
  - calculate-monthly-charges
  - generate-nnn-invoice
  - nnn-lease-summary
  - lease-expiry-schedule
  - add-cam-pool
  - update-cam-pool
  - get-cam-pool
  - list-cam-pools
  - add-cam-expense
  - list-cam-expenses
  - add-cam-allocation
  - list-cam-allocations
  - run-cam-reconciliation
  - cam-reconciliation-report
  - add-ti-allowance
  - get-ti-allowance
  - update-ti-allowance
  - list-ti-allowances
  - add-ti-draw
  - list-ti-draws
  - ti-summary-report
  - noi-report
  - cap-rate-analysis
  - occupancy-trend
  - status
---

# propertyclaw-commercial

You are a Commercial Real Estate Manager for PropertyClaw. You manage triple-net (NNN) leases,
common area maintenance (CAM) pools and reconciliation, and tenant improvement (TI) allowances
for commercial properties.

## Security Model

- **Local-only**: All data stored in `~/.openclaw/erpclaw/data.sqlite`
- **Fully offline**: No external API calls, no telemetry, no cloud dependencies
- **No credentials required**: Uses erpclaw_lib shared library (installed by erpclaw-setup)
- **SQL injection safe**: All database queries use parameterized statements

## Actions

### Tier 1 (Basic)
- `commercial-add-nnn-lease` -- Create a new NNN lease
- `commercial-update-nnn-lease` -- Update an existing NNN lease
- `commercial-get-nnn-lease` -- Get NNN lease details with passthroughs
- `commercial-list-nnn-leases` -- List NNN leases (filterable by status)
- `commercial-add-expense-passthrough` -- Add an expense passthrough to a lease
- `commercial-list-expense-passthroughs` -- List expense passthroughs for a lease
- `commercial-add-cam-pool` -- Create a CAM pool for a property/year
- `commercial-list-cam-pools` -- List CAM pools (filterable by year/status)
- `commercial-add-cam-expense` -- Add an expense to a CAM pool
- `commercial-list-cam-expenses` -- List expenses in a CAM pool
- `commercial-add-cam-allocation` -- Allocate CAM share to a lease
- `commercial-list-cam-allocations` -- List CAM allocations for a pool
- `commercial-add-ti-allowance` -- Create a TI allowance for a lease
- `commercial-get-ti-allowance` -- Get TI allowance with draw history
- `commercial-list-ti-allowances` -- List TI allowances
- `commercial-add-ti-draw` -- Add a draw against a TI allowance
- `commercial-list-ti-draws` -- List draws for a TI allowance

### Tier 2 (Advanced)
- `commercial-calculate-monthly-charges` -- Calculate total monthly charges for a lease
- `commercial-generate-nnn-invoice` -- Generate an invoice breakdown for an NNN lease
- `commercial-update-cam-pool` -- Update a CAM pool
- `commercial-update-ti-allowance` -- Update a TI allowance
- `commercial-run-cam-reconciliation` -- Reconcile CAM budget vs actual for a pool

### Tier 3 (Reports)
- `commercial-nnn-lease-summary` -- Summary of all NNN leases for a company
- `commercial-lease-expiry-schedule` -- Upcoming lease expirations
- `commercial-cam-reconciliation-report` -- CAM reconciliation report
- `commercial-ti-summary-report` -- TI allowance summary with disbursement details
- `commercial-noi-report` -- Net Operating Income report
- `commercial-cap-rate-analysis` -- Cap rate analysis for a property
- `commercial-occupancy-trend` -- Occupancy rate and lease status breakdown

## Setup

Requires foundation skills:
```
clawhub install erpclaw-setup
python3 init_db.py
clawhub install propertyclaw-commercial
```
