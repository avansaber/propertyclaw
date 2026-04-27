---
name: propertyclaw
version: 1.0.0
description: AI-native property management for US landlords. 102 actions across 8 domains -- properties, units, leases, tenants, maintenance, trust accounting, vacancy/listings, and tenant portal. FCRA-compliant screening, state-specific late fees, 1099 reporting.
author: AvanSaber
homepage: https://github.com/avansaber/propertyclaw
source: https://github.com/avansaber/propertyclaw
tier: 4
category: property-management
requires: [erpclaw]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [propertyclaw, property-management, real-estate, landlord, leasing, tenant, rent, maintenance, work-order, trust-accounting, security-deposit, 1099, fcra, inspection, vacancy, listing, portal, vendor, rubs, utility]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 init_db.py && python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# propertyclaw

Property Manager for PropertyClaw -- AI-native property management on ERPClaw.
Manages properties, units, amenities, tenant applications, FCRA screening, leases, rent collection,
late fees, renewals, maintenance work orders, inspections, vendor management, trust accounting,
security deposits, owner statements, 1099 reporting, vacancy listings, RUBS utility billing,
and tenant self-service portal. All financials post to ERPClaw GL.

### Skill Activation Triggers

Activate when user mentions: property, unit, apartment, tenant, lease, rent, application,
screening, work order, maintenance, inspection, trust account, security deposit, owner statement,
1099, landlord, property management, move-in, move-out, late fee, renewal, listing, vacancy,
vendor, RUBS, utility billing, autopay, amenity.

### Setup
```
python3 {baseDir}/../erpclaw/scripts/db_query.py --action initialize-database
python3 {baseDir}/scripts/db_query.py --action status
```

## Quick Start
```
--action prop-add-property --company-id {id} --name "Elm Street Apts" --address-line1 "100 Elm St" --city "Austin" --state "TX" --zip-code "78701"
--action prop-add-unit --property-id {id} --unit-number "101" --bedrooms 2 --market-rent "1500.00"
--action prop-add-application --company-id {id} --property-id {id} --applicant-name "Jane Doe"
--action prop-add-screening --application-id {id} --screening-type credit --consent-obtained 1
--action prop-approve-application --application-id {id}
--action prop-add-lease --company-id {id} --property-id {id} --unit-id {id} --customer-id {id} --start-date 2026-04-01 --monthly-rent "1500.00"
--action prop-activate-lease --lease-id {id}
```

## All 102 Actions

### Properties & Units (14 actions)
| Action | Description |
|--------|-------------|
| `prop-add-property` | Add rental property |
| `prop-update-property` | Update property details |
| `prop-get-property` | Get property with units |
| `prop-list-properties` | List properties |
| `prop-add-unit` | Add unit to property |
| `prop-update-unit` | Update unit details |
| `prop-get-unit` | Get unit details |
| `prop-list-units` | List units by property |
| `prop-add-amenity` | Add property/unit amenity |
| `prop-list-amenities` | List amenities |
| `prop-delete-amenity` | Delete amenity |
| `prop-add-photo` | Add property/unit photo |
| `prop-list-photos` | List photos |
| `prop-delete-photo` | Delete photo |

### Leases (16 actions)
| Action | Description |
|--------|-------------|
| `prop-add-lease` | Create lease |
| `prop-update-lease` | Update lease |
| `prop-get-lease` | Get lease details |
| `prop-list-leases` | List leases |
| `prop-activate-lease` | Activate lease |
| `prop-terminate-lease` | Terminate lease |
| `prop-add-rent-schedule` | Add rent charge schedule |
| `prop-list-rent-schedules` | List rent schedules |
| `prop-delete-rent-schedule` | Delete rent schedule |
| `prop-generate-charges` | Generate monthly charges |
| `prop-list-charges` | List lease charges |
| `prop-add-late-fee-rule` | Add state-specific late fee rule |
| `prop-list-late-fee-rules` | List late fee rules |
| `prop-apply-late-fees` | Apply late fees |
| `prop-propose-renewal` | Propose lease renewal |
| `prop-accept-renewal` | Accept renewal |

### Tenants & Applications (12 actions)
| Action | Description |
|--------|-------------|
| `prop-add-application` | Create tenant application |
| `prop-update-application` | Update application |
| `prop-get-application` | Get application details |
| `prop-list-applications` | List applications |
| `prop-approve-application` | Approve application |
| `prop-deny-application` | Deny with FCRA notice |
| `prop-add-screening` | Add screening request |
| `prop-get-screening` | Get screening result |
| `prop-list-screenings` | List screenings |
| `prop-add-document` | Add tenant document |
| `prop-list-documents` | List documents |
| `prop-delete-document` | Delete document |

### Maintenance & Inspections (14 actions)
| Action | Description |
|--------|-------------|
| `prop-add-work-order` | Create work order |
| `prop-update-work-order` | Update work order |
| `prop-get-work-order` | Get work order details |
| `prop-list-work-orders` | List work orders |
| `prop-assign-vendor` | Assign vendor to work order |
| `prop-update-vendor-assignment` | Update vendor assignment |
| `prop-complete-work-order` | Complete work order |
| `prop-add-work-order-item` | Add work order line item |
| `prop-list-work-order-items` | List work order items |
| `prop-add-inspection` | Schedule inspection |
| `prop-get-inspection` | Get inspection details |
| `prop-list-inspections` | List inspections |
| `prop-add-inspection-item` | Add inspection checklist item |
| `prop-list-inspection-items` | List inspection items |

### Accounting & Trust (13 actions)
| Action | Description |
|--------|-------------|
| `prop-setup-trust-account` | Set up trust account |
| `prop-get-trust-account` | Get trust account |
| `prop-list-trust-accounts` | List trust accounts |
| `prop-reconcile-trust-account` | Reconcile trust account |
| `prop-add-trust-reconciliation` | Add reconciliation record |
| `prop-list-trust-reconciliations` | List reconciliations |
| `prop-trust-reconciliation-report` | Trust reconciliation report |
| `prop-generate-owner-statement` | Generate owner statement |
| `prop-list-owner-statements` | List owner statements |
| `prop-record-security-deposit` | Record security deposit |
| `prop-return-security-deposit` | Return security deposit |
| `prop-add-deposit-deduction` | Add deposit deduction |
| `prop-list-deposit-deductions` | List deposit deductions |

### Rent & Payments (5 actions)
| Action | Description |
|--------|-------------|
| `prop-process-rent-payment` | Process rent payment |
| `prop-add-payment-method` | Add payment method |
| `prop-list-payment-methods` | List payment methods |
| `prop-enable-autopay` | Enable autopay |
| `prop-disable-autopay` | Disable autopay |

### Vacancy & Listings (10 actions)
| Action | Description |
|--------|-------------|
| `prop-create-listing` | Create vacancy listing |
| `prop-update-listing` | Update listing |
| `prop-list-listings` | List active listings |
| `prop-list-vacancies` | List vacant units |
| `prop-request-vendor-bid` | Request vendor bid |
| `prop-accept-vendor-bid` | Accept vendor bid |
| `prop-list-vendor-bids` | List vendor bids |
| `prop-send-announcement` | Send property announcement |
| `prop-add-announcement` | Create announcement |
| `prop-list-announcements` | List announcements |

### Tenant Portal (8 actions)
| Action | Description |
|--------|-------------|
| `prop-portal-my-lease` | View lease details |
| `prop-portal-my-charges` | View charges |
| `prop-portal-my-payments` | View payment history |
| `prop-portal-my-documents` | View documents |
| `prop-portal-announcements` | View announcements |
| `prop-portal-submit-maintenance-request` | Submit maintenance request |
| `prop-portal-list-maintenance-requests` | List maintenance requests |
| `prop-portal-update-contact-info` | Update contact info |

### Reports (10 actions)
| Action | Description |
|--------|-------------|
| `prop-generate-1099-report` | Generate 1099 for vendors |
| `prop-listing-performance-report` | Listing performance |
| `prop-vendor-performance-report` | Vendor performance |
| `prop-utility-cost-report` | Utility cost report |
| `prop-generate-lease-document` | Generate lease document |
| `prop-list-lease-documents` | List lease documents |
| `prop-generate-payment-receipt` | Generate payment receipt |
| `prop-generate-utility-charges` | Generate utility charges |
| `prop-list-utility-charges` | List utility charges |
| `prop-calculate-rubs` | Calculate RUBS allocations |

## Technical Details (Tier 3)
**Tables (23):** All use `propertyclaw_` prefix. **Script:** `scripts/db_query.py` routes to 8 modules. **Data:** Money=TEXT(Decimal), IDs=TEXT(UUID4). **FCRA:** No raw credit data stored. **Late fees:** State-specific rules.
