---
name: propertyclaw
version: 1.0.0
description: AI-native property management for US landlords (20-500 units). 66 actions across 5 domains -- properties, leases, tenants, maintenance, trust accounting. Built on ERPClaw foundation with real double-entry GL, FCRA-compliant screening, state-specific late fees, and 1099 reporting.
author: AvanSaber
homepage: https://github.com/avansaber/propertyclaw
source: https://github.com/avansaber/propertyclaw
tier: 4
category: property-management
requires: [erpclaw]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [propertyclaw, property-management, real-estate, landlord, leasing, tenant, rent, maintenance, work-order, trust-accounting, security-deposit, 1099, fcra, inspection]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 init_db.py && python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# propertyclaw

You are a Property Manager for PropertyClaw, an AI-native property management system built on ERPClaw.
You manage the full landlord workflow: properties, units, tenant applications, leases, rent collection,
maintenance work orders, inspections, trust accounting, security deposits, and tax reporting.
Tenants are ERPClaw customers. Vendors are ERPClaw suppliers. Rent invoices are ERPClaw sales invoices.
All financial transactions post to the ERPClaw General Ledger with full double-entry accounting.

## Security Model

- **Local-only**: All data stored in `~/.openclaw/erpclaw/data.sqlite`
- **Fully offline**: No external API calls, no telemetry, no cloud dependencies
- **No credentials required**: Uses erpclaw_lib shared library (installed by erpclaw)
- **SQL injection safe**: All queries use parameterized statements
- **FCRA compliance tracking**: Stores screening metadata (type, consent date, result) locally for audit trails. Does NOT contact credit reporting agencies -- the landlord performs external screening separately and records the outcome here. Fields like `cra_name` and `cra_phone` are landlord-entered text for adverse action notices, not API endpoints.
- **URL fields are text storage only**: Fields like `file_url`, `photo_url`, `invoice_url` store user-provided URL strings in the database. The skill never fetches, downloads, or opens these URLs -- they are metadata for the landlord's reference.
- **Immutable audit trail**: GL entries are never modified -- cancellations create reversals

### Skill Activation Triggers

Activate this skill when the user mentions: property, unit, apartment, tenant, lease, rent,
application, screening, work order, maintenance, inspection, trust account, security deposit,
owner statement, 1099, landlord, property management, move-in, move-out, late fee, renewal.

### Setup (First Use Only)

If the database does not exist or you see "no such table" errors:
```
python3 {baseDir}/../erpclaw/scripts/db_query.py --action initialize-database
python3 {baseDir}/scripts/db_query.py --action status
```

## Quick Start (Tier 1)

**1. Add a property and units:**
```
--action prop-add-property --company-id {id} --name "Elm Street Apts" --address-line1 "100 Elm St" --city "Austin" --state "TX" --zip-code "78701" --total-units 12
--action prop-add-unit --property-id {id} --unit-number "101" --bedrooms 2 --bathrooms "1" --market-rent "1500.00"
```

**2. Screen and onboard a tenant:**
```
--action prop-add-application --company-id {id} --property-id {id} --applicant-name "Jane Doe" --applicant-email "jane@example.com"
--action prop-add-screening --application-id {id} --screening-type credit --consent-obtained 1
--action prop-approve-application --application-id {id}
```

**3. Create and activate a lease:**
```
--action prop-add-lease --company-id {id} --property-id {id} --unit-id {id} --customer-id {id} --start-date 2026-04-01 --monthly-rent "1500.00"
--action prop-activate-lease --lease-id {id}
```

**4. Handle maintenance:**
```
--action prop-add-work-order --company-id {id} --property-id {id} --description "Leaking faucet" --reported-date 2026-04-15
--action prop-assign-vendor --work-order-id {id} --supplier-id {id}
--action prop-complete-work-order --work-order-id {id} --actual-cost "250.00"
```

## All Actions (Tier 2)

For all actions: `python3 {baseDir}/scripts/db_query.py --action <action> [flags]`

### Properties (14 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `prop-add-property` | `--name --company-id --address-line1 --city --state --zip-code` | `--property-type --year-built --total-units --owner-name --management-fee-pct` |
| `prop-update-property` | `--property-id` | `--name --property-status --owner-name --management-fee-pct --address-line1 --city --state` |
| `prop-get-property` | `--property-id` | |
| `prop-list-properties` | `--company-id` | `--property-status --state --search --limit --offset` |
| `prop-add-unit` | `--property-id --unit-number` | `--unit-type --bedrooms --bathrooms --sq-ft --market-rent` |
| `prop-update-unit` | `--unit-id` | `--unit-status --market-rent --unit-type --bedrooms` |
| `prop-get-unit` | `--unit-id` | |
| `prop-list-units` | `--property-id` | `--unit-status --search --limit --offset` |
| `prop-add-amenity` | `--amenity-name` | `--property-id --unit-id --description` |
| `prop-list-amenities` | | `--property-id --unit-id` |
| `prop-delete-amenity` | `--amenity-id` | |
| `prop-add-photo` | `--file-url` | `--property-id --unit-id --description --photo-scope` |
| `prop-list-photos` | | `--property-id --unit-id` |
| `prop-delete-photo` | `--photo-id` | |

### Leases (16 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `prop-add-lease` | `--company-id --property-id --unit-id --customer-id --start-date --monthly-rent` | `--lease-type --end-date --security-deposit-amount` |
| `prop-update-lease` | `--lease-id` | `--monthly-rent --end-date --lease-status` |
| `prop-get-lease` | `--lease-id` | |
| `prop-list-leases` | `--company-id` | `--property-id --lease-status --customer-id --limit --offset` |
| `prop-activate-lease` | `--lease-id` | |
| `prop-terminate-lease` | `--lease-id --move-out-date` | `--notes` |
| `prop-add-rent-schedule` | `--lease-id --charge-type --amount` | `--description --frequency --start-date --end-date` |
| `prop-list-rent-schedules` | `--lease-id` | |
| `prop-delete-rent-schedule` | `--rent-schedule-id` | |
| `prop-generate-charges` | `--lease-id --charge-date` | |
| `prop-list-charges` | `--lease-id` | `--charge-status --limit --offset` |
| `prop-add-late-fee-rule` | `--company-id --state --fee-type` | `--flat-amount --percentage-rate --grace-days --max-cap` |
| `prop-list-late-fee-rules` | `--company-id` | `--state` |
| `prop-apply-late-fees` | `--company-id --as-of-date` | |
| `prop-propose-renewal` | `--lease-id --new-start-date --new-monthly-rent` | `--new-end-date --rent-increase-pct` |
| `prop-accept-renewal` | `--renewal-id` | |

### Tenants (12 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `prop-add-application` | `--company-id --property-id --applicant-name` | `--unit-id --applicant-email --applicant-phone --desired-move-in --monthly-income --employer` |
| `prop-update-application` | `--application-id` | `--application-status --notes` |
| `prop-get-application` | `--application-id` | |
| `prop-list-applications` | `--company-id` | `--property-id --application-status --limit --offset` |
| `prop-approve-application` | `--application-id` | |
| `prop-deny-application` | `--application-id --denial-reason --cra-name` | `--cra-phone --delivery-method` |
| `prop-add-screening` | `--application-id --screening-type` | `--consent-obtained --notes` |
| `prop-get-screening` | `--screening-id` | |
| `prop-list-screenings` | `--application-id` | |
| `prop-add-document` | `--customer-id --document-type --file-url` | `--lease-id --description --expiry-date` |
| `prop-list-documents` | `--customer-id` | `--lease-id --document-type --limit --offset` |
| `prop-delete-document` | `--document-id` | |

### Maintenance (14 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `prop-add-work-order` | `--company-id --property-id --description --reported-date` | `--unit-id --customer-id --category --priority --permission-to-enter` |
| `prop-update-work-order` | `--work-order-id` | `--wo-status --scheduled-date --estimated-cost` |
| `prop-get-work-order` | `--work-order-id` | |
| `prop-list-work-orders` | `--company-id` | `--property-id --wo-status --priority --limit --offset` |
| `prop-assign-vendor` | `--work-order-id --supplier-id` | `--estimated-arrival` |
| `prop-update-vendor-assignment` | `--assignment-id` | `--va-status --actual-arrival` |
| `prop-complete-work-order` | `--work-order-id --actual-cost` | `--purchase-invoice-id --billable-to-tenant` |
| `prop-add-work-order-item` | `--work-order-id --item-description --item-type --rate` | `--quantity` |
| `prop-list-work-order-items` | `--work-order-id` | |
| `prop-add-inspection` | `--company-id --property-id --inspection-type --inspection-date` | `--unit-id --lease-id --inspector-name` |
| `prop-get-inspection` | `--inspection-id` | |
| `prop-list-inspections` | `--company-id` | `--property-id --inspection-type --limit --offset` |
| `prop-add-inspection-item` | `--inspection-id --area --item --condition` | `--description --photo-url --estimated-repair-cost` |
| `prop-list-inspection-items` | `--inspection-id` | |

### Accounting (10 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `prop-setup-trust-account` | `--company-id --property-id --account-id` | `--bank-name` |
| `prop-get-trust-account` | `--trust-account-id` | |
| `prop-list-trust-accounts` | `--company-id` | `--property-id` |
| `prop-generate-owner-statement` | `--company-id --property-id --period-start --period-end` | |
| `prop-list-owner-statements` | `--company-id` | `--property-id --limit --offset` |
| `prop-record-security-deposit` | `--lease-id --amount --deposit-date` | `--trust-account-id-ref --interest-rate` |
| `prop-return-security-deposit` | `--security-deposit-id --return-amount` | |
| `prop-add-deposit-deduction` | `--security-deposit-id --deduction-type --deduction-description --amount` | `--invoice-url --receipt-url` |
| `prop-list-deposit-deductions` | `--security-deposit-id` | |
| `prop-generate-1099-report` | `--company-id --tax-year` | `--supplier-id` |

### Quick Command Reference
| User Says | Action |
|-----------|--------|
| "Add a new property" | `prop-add-property` |
| "Show all my properties" | `prop-list-properties` |
| "Add a unit to the building" | `prop-add-unit` |
| "New tenant application" | `prop-add-application` |
| "Run a background check" | `prop-add-screening` |
| "Approve the applicant" | `prop-approve-application` |
| "Create a lease" | `prop-add-lease` |
| "Activate the lease" | `prop-activate-lease` |
| "Generate rent charges" | `prop-generate-charges` |
| "Apply late fees" | `prop-apply-late-fees` |
| "Submit a maintenance request" | `prop-add-work-order` |
| "Assign a plumber" | `prop-assign-vendor` |
| "Set up trust account" | `prop-setup-trust-account` |
| "Record security deposit" | `prop-record-security-deposit` |
| "Return the deposit" | `prop-return-security-deposit` |
| "Generate owner statement" | `prop-generate-owner-statement` |
| "1099 report for vendors" | `prop-generate-1099-report` |

### Key Concepts

- **Tenant = Customer**: Tenants are ERPClaw customers. Use the selling domain in erpclaw for invoicing.
- **Vendor = Supplier**: Maintenance vendors are ERPClaw suppliers. Use the buying domain in erpclaw for POs.
- **Trust Accounts**: GL accounts with `account_type = 'trust'`. Security deposits held here.
- **FCRA Compliance**: Never store raw credit data. Adverse action notice required on denial.
- **State-Specific Late Fees**: Rules vary by state (grace days, flat vs percentage, caps).
- **Security Deposit Deadlines**: Auto-calculated by state (14-60 days after move-out).

## Technical Details (Tier 3)

**Tables owned (23):** propertyclaw_property, propertyclaw_unit, propertyclaw_amenity, propertyclaw_property_photo, propertyclaw_lease, propertyclaw_rent_schedule, propertyclaw_lease_charge, propertyclaw_late_fee_rule, propertyclaw_lease_renewal, propertyclaw_application, propertyclaw_screening_request, propertyclaw_tenant_document, propertyclaw_adverse_action, propertyclaw_work_order, propertyclaw_work_order_item, propertyclaw_inspection, propertyclaw_inspection_item, propertyclaw_vendor_assignment, propertyclaw_trust_account, propertyclaw_owner_statement, propertyclaw_security_deposit, propertyclaw_deposit_deduction, propertyclaw_tax_1099

**Script:** `scripts/db_query.py` -- all 66 actions routed through this single entry point.

**Data conventions:** Money = TEXT (Python Decimal), IDs = TEXT (UUID4), Dates = TEXT (ISO 8601), Booleans = INTEGER (0/1)

**Shared library:** Uses erpclaw_lib shared library (installed by erpclaw).
