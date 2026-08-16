#!/usr/bin/env python3
"""PropertyClaw schema extension — adds domain tables to the shared database.

Prerequisite: ERPClaw init_db.py must have run first (creates foundation tables).
Run: python3 init_db.py [db_path]

Tables: 28 domain tables, 68 indexes. (The pre-conversion docstring said "23
domain tables, ~65 indexes, 7 naming series" — stale on all three counts: five
tables were added after it was written, and the naming-series pre-seed was
removed earlier, see the note on `create_propertyclaw_tables`.)
Skills: propertyclaw-properties, propertyclaw-leases, propertyclaw-tenants,
        propertyclaw-maintenance, propertyclaw-accounting

ADR-0034 phase 2 bulk-39. Schema declared as metadata and provisioned through
`erpclaw_lib.seam`, which emits dialect-correct DDL, replacing a hand-written
``CREATE TABLE`` block opened with ``sqlite3.connect`` that could not run on
PostgreSQL at all. Conversion rules are the pilot's (`erpclaw-esign`): seam
vocabulary only, IDs and every amount stay TEXT on every backend (rent, deposits,
late fees and 1099 totals all live here), and ``primary_key=True, nullable=True``
reproduces SQLite's ``id TEXT PRIMARY KEY`` without adding a NOT NULL that never
shipped.

Seven columns across the five most recently added tables shipped
``DEFAULT (datetime('now'))``, which is SQLite's spelling and the single reason
this module could not provision on PostgreSQL even by hand. They are declared
with `seam.now_default()`, which renders ``(datetime('now'))`` on SQLite and
``CURRENT_TIMESTAMP`` on PostgreSQL.

Asymmetries in the shipped DDL are transcribed rather than tidied. The five late
tables are inconsistent with the twenty-three older ones and with each other:
``propertyclaw_payment_method`` carries ``tenant_id`` and ``company_id`` as bare
NOT NULL columns with no foreign key at all, ``propertyclaw_vendor_bid`` names a
``vendor_id`` that points at nothing while its sibling
``propertyclaw_vendor_assignment`` declares ``supplier_id`` REFERENCES
``supplier(id)``, ``propertyclaw_announcement.property_id`` is unconstrained
where every other ``property_id`` in the module is a foreign key, and
``propertyclaw_security_deposit.gl_entry_id`` names a GL row without referencing
it. Their ``status`` columns are also nullable-with-a-default where the older
tables spell the same idea NOT NULL. Each of those is a schema decision to make
or unmake deliberately; a conversion is not the place.

`propertyclaw-commercial` does NOT declare foreign keys into these tables, and so
does not depend on this module's install order. Its thirteen `REFERENCES`
clauses resolve to its own `commercial_*` tables and to foundation's `company`,
nothing else. An earlier draft of this docstring said the opposite; it was
inherited from a dispatch note rather than read off the DDL, and the
`propertyclaw-commercial` conversion checked and corrected it.
"""
import importlib.util
import os
import sys

# Bootstrap the shared lib only when it is not already reachable — an
# unconditional insert at position 0 overrides a caller that deliberately bound a
# different tree (ADR-0034 phase 2 step 2d).
if importlib.util.find_spec("erpclaw_lib") is None:
    sys.path.insert(0, os.path.join(os.path.expanduser(
        os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))

from erpclaw_lib.seam import (  # noqa: E402
    CheckConstraint, Column, ForeignKey, Index, Integer, MetaData, Table, Text,
    UniqueConstraint, now_default, provision, reference_table, text,
)

DEFAULT_DB_PATH = os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "data.sqlite")
DISPLAY_NAME = "PropertyClaw"

# The pre-conversion installer carried this list inline; it is the same list.
REQUIRED_FOUNDATION = [
    "company", "customer", "supplier", "account",
    "sales_invoice", "purchase_invoice", "payment_entry",
    "gl_entry", "naming_series", "recurring_invoice_template",
]

METADATA = MetaData()

# Foundation tables this module points at but does not own. Declared for foreign
# key resolution only and never created here — see `seam.reference_table`.
reference_table("company", METADATA)
reference_table("customer", METADATA)
reference_table("supplier", METADATA)
reference_table("account", METADATA)
reference_table("sales_invoice", METADATA)
reference_table("purchase_invoice", METADATA)
reference_table("payment_entry", METADATA)
reference_table("recurring_invoice_template", METADATA)

# ===========================================================================
# propertyclaw-properties (4 tables)
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. propertyclaw_property — building or land parcel
# ---------------------------------------------------------------------------
PROPERTY = Table(
    "propertyclaw_property", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("name", Text, nullable=False),
    Column("property_type", Text, nullable=False,
           server_default=text("'residential'")),
    Column("address_line1", Text, nullable=False),
    Column("address_line2", Text),
    Column("city", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("zip_code", Text, nullable=False),
    Column("county", Text),
    Column("year_built", Integer),
    Column("total_units", Integer, nullable=False, server_default=text("1")),
    Column("owner_name", Text),
    Column("owner_contact", Text),
    Column("management_fee_pct", Text),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("property_type IN ('residential','commercial','mixed')",
                    name="ck_propertyclaw_property_property_type"),
    CheckConstraint("status IN ('active','inactive','archived')",
                    name="ck_propertyclaw_property_status"),
)

Index("idx_propertyclaw_property_company", PROPERTY.c.company_id)
Index("idx_propertyclaw_property_status", PROPERTY.c.status)
Index("idx_propertyclaw_property_state", PROPERTY.c.state)

# ---------------------------------------------------------------------------
# 2. propertyclaw_unit — individual rentable space within a property
# ---------------------------------------------------------------------------
UNIT = Table(
    "propertyclaw_unit", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT"),
           nullable=False),
    Column("unit_number", Text, nullable=False),
    Column("unit_type", Text, nullable=False, server_default=text("'apartment'")),
    Column("bedrooms", Integer),
    Column("bathrooms", Text),
    Column("sq_ft", Integer),
    Column("floor", Integer),
    Column("market_rent", Text, nullable=False, server_default=text("'0'")),
    Column("status", Text, nullable=False, server_default=text("'available'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "unit_type IN ('apartment','house','condo','townhouse', "
        "'commercial','storage','parking')",
        name="ck_propertyclaw_unit_unit_type"),
    CheckConstraint("status IN ('available','occupied','maintenance','reserved')",
                    name="ck_propertyclaw_unit_status"),
    # Idempotency key: one unit number per property.
    UniqueConstraint("property_id", "unit_number"),
)

Index("idx_propertyclaw_unit_property", UNIT.c.property_id)
Index("idx_propertyclaw_unit_status", UNIT.c.status)

# ---------------------------------------------------------------------------
# 3. propertyclaw_amenity — feature of a property or unit
# ---------------------------------------------------------------------------
AMENITY = Table(
    "propertyclaw_amenity", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT")),
    Column("unit_id", Text,
           ForeignKey("propertyclaw_unit.id", ondelete="RESTRICT")),
    Column("amenity_scope", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("amenity_scope IN ('property','unit')",
                    name="ck_propertyclaw_amenity_amenity_scope"),
)

Index("idx_propertyclaw_amenity_property", AMENITY.c.property_id)
Index("idx_propertyclaw_amenity_unit", AMENITY.c.unit_id)

# ---------------------------------------------------------------------------
# 4. propertyclaw_property_photo
# ---------------------------------------------------------------------------
PROPERTY_PHOTO = Table(
    "propertyclaw_property_photo", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT")),
    Column("unit_id", Text,
           ForeignKey("propertyclaw_unit.id", ondelete="RESTRICT")),
    Column("photo_scope", Text, nullable=False),
    Column("file_url", Text, nullable=False),
    Column("description", Text),
    Column("uploaded_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("photo_scope IN ('property','unit','inspection')",
                    name="ck_propertyclaw_property_photo_photo_scope"),
)

Index("idx_propertyclaw_photo_property", PROPERTY_PHOTO.c.property_id)
Index("idx_propertyclaw_photo_unit", PROPERTY_PHOTO.c.unit_id)


# ===========================================================================
# propertyclaw-leases (5 tables)
# ===========================================================================

# ---------------------------------------------------------------------------
# 5. propertyclaw_lease — lease agreement
# ---------------------------------------------------------------------------
LEASE = Table(
    "propertyclaw_lease", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT"),
           nullable=False),
    Column("unit_id", Text,
           ForeignKey("propertyclaw_unit.id", ondelete="RESTRICT"),
           nullable=False),
    Column("customer_id", Text,
           ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False),
    Column("lease_type", Text, nullable=False, server_default=text("'fixed'")),
    Column("start_date", Text, nullable=False),
    Column("end_date", Text),
    Column("monthly_rent", Text, nullable=False, server_default=text("'0'")),
    Column("security_deposit_amount", Text, nullable=False,
           server_default=text("'0'")),
    Column("deposit_account_id", Text,
           ForeignKey("account.id", ondelete="RESTRICT")),
    Column("move_in_date", Text),
    Column("move_out_date", Text),
    Column("recurring_template_id", Text,
           ForeignKey("recurring_invoice_template.id", ondelete="RESTRICT")),
    Column("primary_contact", Text),
    Column("primary_address", Text),
    Column("name", Text),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("lease_type IN ('fixed','month_to_month')",
                    name="ck_propertyclaw_lease_lease_type"),
    CheckConstraint(
        "status IN ('draft','active','expired','terminated','renewed')",
        name="ck_propertyclaw_lease_status"),
)

Index("idx_propertyclaw_lease_company", LEASE.c.company_id)
Index("idx_propertyclaw_lease_property", LEASE.c.property_id)
Index("idx_propertyclaw_lease_unit", LEASE.c.unit_id)
Index("idx_propertyclaw_lease_customer", LEASE.c.customer_id)
Index("idx_propertyclaw_lease_status", LEASE.c.status)
Index("idx_propertyclaw_lease_dates", LEASE.c.start_date, LEASE.c.end_date)

# ---------------------------------------------------------------------------
# 6. propertyclaw_rent_schedule — recurring charges on a lease
# ---------------------------------------------------------------------------
RENT_SCHEDULE = Table(
    "propertyclaw_rent_schedule", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT"),
           nullable=False),
    Column("charge_type", Text, nullable=False),
    Column("description", Text),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("frequency", Text, nullable=False, server_default=text("'monthly'")),
    Column("start_date", Text, nullable=False),
    Column("end_date", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "charge_type IN ( "
        "'base_rent','pet_rent','parking','storage','utility','other')",
        name="ck_propertyclaw_rent_schedule_charge_type"),
    CheckConstraint("frequency IN ('weekly','biweekly','monthly')",
                    name="ck_propertyclaw_rent_schedule_frequency"),
)

Index("idx_propertyclaw_rent_sched_lease", RENT_SCHEDULE.c.lease_id)

# ---------------------------------------------------------------------------
# 7. propertyclaw_lease_charge — individual charge instance
# ---------------------------------------------------------------------------
LEASE_CHARGE = Table(
    "propertyclaw_lease_charge", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT"),
           nullable=False),
    Column("charge_date", Text, nullable=False),
    Column("charge_type", Text, nullable=False),
    Column("description", Text),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("invoice_id", Text,
           ForeignKey("sales_invoice.id", ondelete="RESTRICT")),
    Column("status", Text, nullable=False, server_default=text("'pending'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("status IN ('pending','invoiced','paid','waived')",
                    name="ck_propertyclaw_lease_charge_status"),
)

Index("idx_propertyclaw_charge_lease", LEASE_CHARGE.c.lease_id)
Index("idx_propertyclaw_charge_date", LEASE_CHARGE.c.charge_date)
Index("idx_propertyclaw_charge_status", LEASE_CHARGE.c.status)

# ---------------------------------------------------------------------------
# 8. propertyclaw_late_fee_rule — state-specific late fee rules
# ---------------------------------------------------------------------------
LATE_FEE_RULE = Table(
    "propertyclaw_late_fee_rule", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("state", Text, nullable=False),
    Column("fee_type", Text, nullable=False),
    Column("flat_amount", Text),
    Column("percentage_rate", Text),
    Column("grace_days", Integer, nullable=False, server_default=text("0")),
    Column("max_cap", Text),
    Column("is_default", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("fee_type IN ('flat','percentage','lower_of','greater_of')",
                    name="ck_propertyclaw_late_fee_rule_fee_type"),
    CheckConstraint("is_default IN (0,1)",
                    name="ck_propertyclaw_late_fee_rule_is_default"),
    # Idempotency key: one rule per company per state.
    UniqueConstraint("company_id", "state"),
)

Index("idx_propertyclaw_late_fee_company", LATE_FEE_RULE.c.company_id)

# ---------------------------------------------------------------------------
# 9. propertyclaw_lease_renewal — lease renewal tracking
# ---------------------------------------------------------------------------
LEASE_RENEWAL = Table(
    "propertyclaw_lease_renewal", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT"),
           nullable=False),
    Column("previous_lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT")),
    Column("new_start_date", Text, nullable=False),
    Column("new_end_date", Text),
    Column("new_monthly_rent", Text, nullable=False, server_default=text("'0'")),
    Column("rent_increase_pct", Text),
    Column("status", Text, nullable=False, server_default=text("'proposed'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("status IN ('proposed','accepted','rejected','expired')",
                    name="ck_propertyclaw_lease_renewal_status"),
)

Index("idx_propertyclaw_renewal_lease", LEASE_RENEWAL.c.lease_id)


# ===========================================================================
# propertyclaw-tenants (4 tables)
# ===========================================================================

# ---------------------------------------------------------------------------
# 10. propertyclaw_application — rental application
# ---------------------------------------------------------------------------
APPLICATION = Table(
    "propertyclaw_application", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT"),
           nullable=False),
    Column("unit_id", Text,
           ForeignKey("propertyclaw_unit.id", ondelete="RESTRICT")),
    Column("applicant_name", Text, nullable=False),
    Column("applicant_email", Text),
    Column("applicant_phone", Text),
    Column("desired_move_in", Text),
    Column("monthly_income", Text),
    Column("employer", Text),
    Column("customer_id", Text,
           ForeignKey("customer.id", ondelete="RESTRICT")),
    Column("denial_reason", Text),
    Column("status", Text, nullable=False, server_default=text("'received'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "status IN ('received','screening','approved','denied','withdrawn')",
        name="ck_propertyclaw_application_status"),
)

Index("idx_propertyclaw_app_company", APPLICATION.c.company_id)
Index("idx_propertyclaw_app_property", APPLICATION.c.property_id)
Index("idx_propertyclaw_app_status", APPLICATION.c.status)

# ---------------------------------------------------------------------------
# 11. propertyclaw_screening_request
#     FCRA compliant — never store raw credit data.
# ---------------------------------------------------------------------------
SCREENING_REQUEST = Table(
    "propertyclaw_screening_request", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("application_id", Text,
           ForeignKey("propertyclaw_application.id", ondelete="RESTRICT"),
           nullable=False),
    Column("screening_type", Text, nullable=False),
    Column("consent_obtained", Integer, nullable=False, server_default=text("0")),
    Column("consent_date", Text),
    Column("request_date", Text),
    Column("result", Text, nullable=False, server_default=text("'pending'")),
    Column("adverse_action_sent", Integer, nullable=False,
           server_default=text("0")),
    Column("adverse_action_date", Text),
    Column("notes", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "screening_type IN ('credit','criminal','eviction','income')",
        name="ck_propertyclaw_screening_request_screening_type"),
    CheckConstraint("consent_obtained IN (0,1)",
                    name="ck_propertyclaw_screening_request_consent_obtained"),
    CheckConstraint("result IN ('pending','pass','fail','review')",
                    name="ck_propertyclaw_screening_request_result"),
    CheckConstraint("adverse_action_sent IN (0,1)",
                    name="ck_propertyclaw_screening_request_adverse_action_sent"),
)

Index("idx_propertyclaw_screen_app", SCREENING_REQUEST.c.application_id)

# ---------------------------------------------------------------------------
# 12. propertyclaw_tenant_document
# ---------------------------------------------------------------------------
TENANT_DOCUMENT = Table(
    "propertyclaw_tenant_document", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("customer_id", Text,
           ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False),
    Column("lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT")),
    Column("document_type", Text, nullable=False),
    Column("file_url", Text, nullable=False),
    Column("description", Text),
    Column("expiry_date", Text),
    Column("uploaded_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "document_type IN ( "
        "'lease','lead_paint_disclosure','move_in_inspection', "
        "'move_out_inspection','application','id_copy', "
        "'insurance','w9','other')",
        name="ck_propertyclaw_tenant_document_document_type"),
)

Index("idx_propertyclaw_doc_customer", TENANT_DOCUMENT.c.customer_id)
Index("idx_propertyclaw_doc_lease", TENANT_DOCUMENT.c.lease_id)

# ---------------------------------------------------------------------------
# 13. propertyclaw_adverse_action — adverse action notice (FCRA)
# ---------------------------------------------------------------------------
ADVERSE_ACTION = Table(
    "propertyclaw_adverse_action", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("application_id", Text,
           ForeignKey("propertyclaw_application.id", ondelete="RESTRICT"),
           nullable=False),
    Column("screening_request_id", Text,
           ForeignKey("propertyclaw_screening_request.id", ondelete="RESTRICT")),
    Column("notice_date", Text, nullable=False),
    Column("cra_name", Text, nullable=False),
    Column("cra_address", Text),
    Column("cra_phone", Text),
    Column("reason", Text, nullable=False),
    Column("delivery_method", Text),
    Column("delivered_date", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("delivery_method IN ('mail','email','hand')",
                    name="ck_propertyclaw_adverse_action_delivery_method"),
)

Index("idx_propertyclaw_adverse_app", ADVERSE_ACTION.c.application_id)


# ===========================================================================
# propertyclaw-maintenance (5 tables)
# ===========================================================================

# ---------------------------------------------------------------------------
# 14. propertyclaw_work_order
# ---------------------------------------------------------------------------
WORK_ORDER = Table(
    "propertyclaw_work_order", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT"),
           nullable=False),
    Column("unit_id", Text,
           ForeignKey("propertyclaw_unit.id", ondelete="RESTRICT")),
    Column("lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT")),
    Column("customer_id", Text,
           ForeignKey("customer.id", ondelete="RESTRICT")),
    Column("category", Text, nullable=False, server_default=text("'general'")),
    Column("priority", Text, nullable=False, server_default=text("'routine'")),
    Column("description", Text, nullable=False),
    Column("reported_date", Text, nullable=False),
    Column("scheduled_date", Text),
    Column("completed_date", Text),
    Column("estimated_cost", Text),
    Column("actual_cost", Text),
    Column("supplier_id", Text,
           ForeignKey("supplier.id", ondelete="RESTRICT")),
    Column("purchase_invoice_id", Text,
           ForeignKey("purchase_invoice.id", ondelete="RESTRICT")),
    Column("billable_to_tenant", Integer, nullable=False,
           server_default=text("0")),
    Column("permission_to_enter", Integer, nullable=False,
           server_default=text("0")),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "category IN ('plumbing','electrical','hvac','appliance', "
        "'structural','general','landscaping','pest','safety')",
        name="ck_propertyclaw_work_order_category"),
    CheckConstraint("priority IN ('emergency','urgent','routine')",
                    name="ck_propertyclaw_work_order_priority"),
    CheckConstraint("billable_to_tenant IN (0,1)",
                    name="ck_propertyclaw_work_order_billable_to_tenant"),
    CheckConstraint("permission_to_enter IN (0,1)",
                    name="ck_propertyclaw_work_order_permission_to_enter"),
    CheckConstraint(
        "status IN ('open','assigned','in_progress','completed','cancelled')",
        name="ck_propertyclaw_work_order_status"),
)

Index("idx_propertyclaw_wo_company", WORK_ORDER.c.company_id)
Index("idx_propertyclaw_wo_property", WORK_ORDER.c.property_id)
Index("idx_propertyclaw_wo_unit", WORK_ORDER.c.unit_id)
Index("idx_propertyclaw_wo_status", WORK_ORDER.c.status)
Index("idx_propertyclaw_wo_priority", WORK_ORDER.c.priority)
Index("idx_propertyclaw_wo_supplier", WORK_ORDER.c.supplier_id)

# ---------------------------------------------------------------------------
# 15. propertyclaw_work_order_item — work order line items
# ---------------------------------------------------------------------------
WORK_ORDER_ITEM = Table(
    "propertyclaw_work_order_item", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("work_order_id", Text,
           ForeignKey("propertyclaw_work_order.id", ondelete="RESTRICT"),
           nullable=False),
    Column("description", Text, nullable=False),
    Column("item_type", Text, nullable=False),
    Column("quantity", Text, nullable=False, server_default=text("'1'")),
    Column("rate", Text, nullable=False, server_default=text("'0'")),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("item_type IN ('labor','material','other')",
                    name="ck_propertyclaw_work_order_item_item_type"),
)

Index("idx_propertyclaw_woi_wo", WORK_ORDER_ITEM.c.work_order_id)

# ---------------------------------------------------------------------------
# 16. propertyclaw_inspection — property/unit inspection
# ---------------------------------------------------------------------------
INSPECTION = Table(
    "propertyclaw_inspection", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT"),
           nullable=False),
    Column("unit_id", Text,
           ForeignKey("propertyclaw_unit.id", ondelete="RESTRICT")),
    Column("lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT")),
    Column("inspection_type", Text, nullable=False),
    Column("inspection_date", Text, nullable=False),
    Column("inspector_name", Text),
    Column("overall_condition", Text),
    Column("notes", Text),
    Column("status", Text, nullable=False, server_default=text("'scheduled'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "inspection_type IN ( "
        "'move_in','move_out','routine','pre_listing')",
        name="ck_propertyclaw_inspection_inspection_type"),
    CheckConstraint(
        "overall_condition IN ('excellent','good','fair','poor')",
        name="ck_propertyclaw_inspection_overall_condition"),
    CheckConstraint("status IN ('scheduled','completed','reviewed')",
                    name="ck_propertyclaw_inspection_status"),
)

Index("idx_propertyclaw_insp_company", INSPECTION.c.company_id)
Index("idx_propertyclaw_insp_property", INSPECTION.c.property_id)
Index("idx_propertyclaw_insp_type", INSPECTION.c.inspection_type)

# ---------------------------------------------------------------------------
# 17. propertyclaw_inspection_item — inspection checklist items
# ---------------------------------------------------------------------------
INSPECTION_ITEM = Table(
    "propertyclaw_inspection_item", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("inspection_id", Text,
           ForeignKey("propertyclaw_inspection.id", ondelete="RESTRICT"),
           nullable=False),
    Column("area", Text, nullable=False),
    Column("item", Text, nullable=False),
    Column("condition", Text, nullable=False),
    Column("description", Text),
    Column("photo_url", Text),
    Column("estimated_repair_cost", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "area IN ( "
        "'kitchen','bathroom','bedroom','living_room', "
        "'dining_room','exterior','garage','other')",
        name="ck_propertyclaw_inspection_item_area"),
    CheckConstraint(
        "item IN ( "
        "'walls','floors','ceiling','windows','doors', "
        "'fixtures','appliances','cabinets','other')",
        name="ck_propertyclaw_inspection_item_item"),
    CheckConstraint(
        "condition IN ('good','fair','poor','damaged','missing')",
        name="ck_propertyclaw_inspection_item_condition"),
)

Index("idx_propertyclaw_inspi_insp", INSPECTION_ITEM.c.inspection_id)

# ---------------------------------------------------------------------------
# 18. propertyclaw_vendor_assignment — vendor assignment to work order
# ---------------------------------------------------------------------------
VENDOR_ASSIGNMENT = Table(
    "propertyclaw_vendor_assignment", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("work_order_id", Text,
           ForeignKey("propertyclaw_work_order.id", ondelete="RESTRICT"),
           nullable=False),
    Column("supplier_id", Text,
           ForeignKey("supplier.id", ondelete="RESTRICT"), nullable=False),
    Column("assigned_date", Text, nullable=False),
    Column("estimated_arrival", Text),
    Column("actual_arrival", Text),
    Column("status", Text, nullable=False, server_default=text("'assigned'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "status IN ('assigned','accepted','declined','en_route','on_site','completed')",
        name="ck_propertyclaw_vendor_assignment_status"),
)

Index("idx_propertyclaw_va_wo", VENDOR_ASSIGNMENT.c.work_order_id)
Index("idx_propertyclaw_va_supplier", VENDOR_ASSIGNMENT.c.supplier_id)


# ===========================================================================
# propertyclaw-accounting (5 tables)
# ===========================================================================

# ---------------------------------------------------------------------------
# 19. propertyclaw_trust_account — property → GL trust account link
# ---------------------------------------------------------------------------
TRUST_ACCOUNT = Table(
    "propertyclaw_trust_account", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT"),
           nullable=False),
    Column("account_id", Text,
           ForeignKey("account.id", ondelete="RESTRICT"), nullable=False),
    Column("bank_name", Text),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("status IN ('active','frozen','closed')",
                    name="ck_propertyclaw_trust_account_status"),
    # Idempotency key: one trust account per company per property.
    UniqueConstraint("company_id", "property_id"),
)

Index("idx_propertyclaw_trust_company", TRUST_ACCOUNT.c.company_id)
Index("idx_propertyclaw_trust_property", TRUST_ACCOUNT.c.property_id)

# ---------------------------------------------------------------------------
# 20. propertyclaw_owner_statement — monthly owner statement
# ---------------------------------------------------------------------------
OWNER_STATEMENT = Table(
    "propertyclaw_owner_statement", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("property_id", Text,
           ForeignKey("propertyclaw_property.id", ondelete="RESTRICT"),
           nullable=False),
    Column("owner_name", Text, nullable=False),
    Column("period_start", Text, nullable=False),
    Column("period_end", Text, nullable=False),
    Column("gross_rent", Text, nullable=False, server_default=text("'0'")),
    Column("other_income", Text, nullable=False, server_default=text("'0'")),
    Column("management_fee", Text, nullable=False, server_default=text("'0'")),
    Column("maintenance_expense", Text, nullable=False,
           server_default=text("'0'")),
    Column("other_expense", Text, nullable=False, server_default=text("'0'")),
    Column("net_distribution", Text, nullable=False, server_default=text("'0'")),
    Column("payment_entry_id", Text,
           ForeignKey("payment_entry.id", ondelete="RESTRICT")),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("status IN ('draft','sent','paid')",
                    name="ck_propertyclaw_owner_statement_status"),
)

Index("idx_propertyclaw_owner_stmt_company", OWNER_STATEMENT.c.company_id)
Index("idx_propertyclaw_owner_stmt_property", OWNER_STATEMENT.c.property_id)
Index("idx_propertyclaw_owner_stmt_period",
      OWNER_STATEMENT.c.period_start, OWNER_STATEMENT.c.period_end)

# ---------------------------------------------------------------------------
# 21. propertyclaw_security_deposit — security deposit tracking
# ---------------------------------------------------------------------------
SECURITY_DEPOSIT = Table(
    "propertyclaw_security_deposit", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("lease_id", Text,
           ForeignKey("propertyclaw_lease.id", ondelete="RESTRICT"),
           nullable=False),
    Column("customer_id", Text,
           ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("deposit_date", Text, nullable=False),
    Column("trust_account_id", Text,
           ForeignKey("propertyclaw_trust_account.id", ondelete="RESTRICT")),
    # Names a GL row without referencing it — transcribed as shipped.
    Column("gl_entry_id", Text),
    Column("interest_rate", Text),
    Column("interest_accrued", Text, nullable=False, server_default=text("'0'")),
    Column("return_deadline", Text),
    Column("return_date", Text),
    Column("return_amount", Text),
    Column("deduction_amount", Text, nullable=False, server_default=text("'0'")),
    Column("status", Text, nullable=False, server_default=text("'held'")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "status IN ('held','partially_returned','returned','forfeited')",
        name="ck_propertyclaw_security_deposit_status"),
)

Index("idx_propertyclaw_deposit_lease", SECURITY_DEPOSIT.c.lease_id)
Index("idx_propertyclaw_deposit_customer", SECURITY_DEPOSIT.c.customer_id)
Index("idx_propertyclaw_deposit_status", SECURITY_DEPOSIT.c.status)

# ---------------------------------------------------------------------------
# 22. propertyclaw_deposit_deduction — deposit deductions
# ---------------------------------------------------------------------------
DEPOSIT_DEDUCTION = Table(
    "propertyclaw_deposit_deduction", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("security_deposit_id", Text,
           ForeignKey("propertyclaw_security_deposit.id", ondelete="RESTRICT"),
           nullable=False),
    Column("deduction_type", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("invoice_url", Text),
    Column("receipt_url", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "deduction_type IN ('damages','unpaid_rent','cleaning','other')",
        name="ck_propertyclaw_deposit_deduction_deduction_type"),
)

Index("idx_propertyclaw_deduction_deposit",
      DEPOSIT_DEDUCTION.c.security_deposit_id)

# ---------------------------------------------------------------------------
# 23. propertyclaw_tax_1099 — 1099 tracking
# ---------------------------------------------------------------------------
TAX_1099 = Table(
    "propertyclaw_tax_1099", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("supplier_id", Text,
           ForeignKey("supplier.id", ondelete="RESTRICT"), nullable=False),
    Column("tax_year", Integer, nullable=False),
    Column("total_payments", Text, nullable=False, server_default=text("'0'")),
    Column("form_type", Text, nullable=False, server_default=text("'1099_nec'")),
    Column("filing_status", Text, nullable=False,
           server_default=text("'pending'")),
    Column("filed_date", Text),
    Column("w9_on_file", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("form_type IN ('1099_nec','1099_misc')",
                    name="ck_propertyclaw_tax_1099_form_type"),
    CheckConstraint("filing_status IN ('pending','filed','corrected')",
                    name="ck_propertyclaw_tax_1099_filing_status"),
    CheckConstraint("w9_on_file IN (0,1)",
                    name="ck_propertyclaw_tax_1099_w9_on_file"),
    # Idempotency key: one form per company/supplier/year/form type.
    UniqueConstraint("company_id", "supplier_id", "tax_year", "form_type"),
)

Index("idx_propertyclaw_1099_company", TAX_1099.c.company_id)
Index("idx_propertyclaw_1099_supplier", TAX_1099.c.supplier_id)
Index("idx_propertyclaw_1099_year", TAX_1099.c.tax_year)


# ===========================================================================
# propertyclaw-rent-payment (1 table)
# ===========================================================================

# ---------------------------------------------------------------------------
# 24. propertyclaw_payment_method — payment method for online rent payments
#     `tenant_id` and `company_id` are bare NOT NULL columns here, with no
#     foreign key — unlike every older table in this module. Transcribed as
#     shipped; see the module docstring.
# ---------------------------------------------------------------------------
PAYMENT_METHOD = Table(
    "propertyclaw_payment_method", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("tenant_id", Text, nullable=False),
    Column("method_type", Text, nullable=False),
    Column("last_four", Text),
    Column("bank_name", Text),
    Column("is_default", Integer, server_default=text("0")),
    Column("autopay_enabled", Integer, server_default=text("0")),
    Column("autopay_day", Integer),
    Column("external_token", Text),
    Column("status", Text, server_default=text("'active'")),
    Column("company_id", Text, nullable=False),
    Column("created_at", Text, server_default=now_default()),
    Column("updated_at", Text, server_default=now_default()),
    CheckConstraint("method_type IN ('ach','credit_card','debit_card')",
                    name="ck_propertyclaw_payment_method_method_type"),
    CheckConstraint("status IN ('active','inactive','expired')",
                    name="ck_propertyclaw_payment_method_status"),
)

Index("idx_propertyclaw_pm_tenant", PAYMENT_METHOD.c.tenant_id)
Index("idx_propertyclaw_pm_company", PAYMENT_METHOD.c.company_id)
Index("idx_propertyclaw_pm_status", PAYMENT_METHOD.c.status)


# ===========================================================================
# propertyclaw-vacancy (1 table)
# ===========================================================================

# ---------------------------------------------------------------------------
# 25. propertyclaw_listing
# ---------------------------------------------------------------------------
LISTING = Table(
    "propertyclaw_listing", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("unit_id", Text,
           ForeignKey("propertyclaw_unit.id", ondelete="RESTRICT"),
           nullable=False),
    Column("listing_title", Text),
    Column("description", Text),
    Column("asking_rent", Text),
    Column("available_date", Text),
    Column("photos", Text),
    Column("amenities", Text),
    Column("syndicated_to", Text),
    Column("listing_url", Text),
    Column("lead_count", Integer, server_default=text("0")),
    Column("status", Text, server_default=text("'active'")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=now_default()),
    Column("updated_at", Text, server_default=now_default()),
    CheckConstraint("status IN ('draft','active','rented','expired')",
                    name="ck_propertyclaw_listing_status"),
)

Index("idx_propertyclaw_listing_unit", LISTING.c.unit_id)
Index("idx_propertyclaw_listing_company", LISTING.c.company_id)
Index("idx_propertyclaw_listing_status", LISTING.c.status)


# ===========================================================================
# propertyclaw-reconciliation (1 table)
# ===========================================================================

# ---------------------------------------------------------------------------
# 26. propertyclaw_trust_reconciliation
# ---------------------------------------------------------------------------
TRUST_RECONCILIATION = Table(
    "propertyclaw_trust_reconciliation", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("trust_account_id", Text,
           ForeignKey("propertyclaw_trust_account.id", ondelete="RESTRICT"),
           nullable=False),
    Column("reconciliation_date", Text, nullable=False),
    Column("bank_balance", Text, nullable=False),
    Column("book_balance", Text, nullable=False),
    Column("difference", Text, server_default=text("'0'")),
    Column("adjustments", Text),
    Column("reconciled_by", Text),
    Column("notes", Text),
    Column("status", Text, server_default=text("'draft'")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=now_default()),
    CheckConstraint("status IN ('draft','reconciled','approved')",
                    name="ck_propertyclaw_trust_reconciliation_status"),
)

Index("idx_propertyclaw_recon_trust", TRUST_RECONCILIATION.c.trust_account_id)
Index("idx_propertyclaw_recon_company", TRUST_RECONCILIATION.c.company_id)
Index("idx_propertyclaw_recon_date",
      TRUST_RECONCILIATION.c.reconciliation_date)


# ===========================================================================
# propertyclaw-announcement (1 table)
# ===========================================================================

# ---------------------------------------------------------------------------
# 27. propertyclaw_announcement
#     `property_id` is unconstrained here where every other `property_id` in
#     the module is a foreign key. Transcribed as shipped.
# ---------------------------------------------------------------------------
ANNOUNCEMENT = Table(
    "propertyclaw_announcement", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("property_id", Text),
    Column("subject", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column("audience", Text, server_default=text("'all'")),
    Column("sent_at", Text),
    Column("sent_by", Text),
    Column("status", Text, server_default=text("'draft'")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=now_default()),
    CheckConstraint("audience IN ('all','tenants','owners','staff')",
                    name="ck_propertyclaw_announcement_audience"),
    CheckConstraint("status IN ('draft','sent','archived')",
                    name="ck_propertyclaw_announcement_status"),
)

Index("idx_propertyclaw_announce_company", ANNOUNCEMENT.c.company_id)
Index("idx_propertyclaw_announce_status", ANNOUNCEMENT.c.status)


# ===========================================================================
# propertyclaw-vendor-bid (1 table)
# ===========================================================================

# ---------------------------------------------------------------------------
# 28. propertyclaw_vendor_bid
#     `vendor_id` points at nothing, where the sibling
#     `propertyclaw_vendor_assignment` declares `supplier_id` REFERENCES
#     `supplier(id)`. Transcribed as shipped.
# ---------------------------------------------------------------------------
VENDOR_BID = Table(
    "propertyclaw_vendor_bid", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("work_order_id", Text,
           ForeignKey("propertyclaw_work_order.id", ondelete="RESTRICT"),
           nullable=False),
    Column("vendor_id", Text, nullable=False),
    Column("bid_amount", Text, nullable=False, server_default=text("'0'")),
    Column("estimated_duration", Text),
    Column("description", Text),
    Column("submitted_date", Text),
    Column("status", Text, server_default=text("'submitted'")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=now_default()),
    CheckConstraint("status IN ('submitted','accepted','rejected','expired')",
                    name="ck_propertyclaw_vendor_bid_status"),
)

Index("idx_propertyclaw_bid_wo", VENDOR_BID.c.work_order_id)
Index("idx_propertyclaw_bid_vendor", VENDOR_BID.c.vendor_id)
Index("idx_propertyclaw_bid_company", VENDOR_BID.c.company_id)
Index("idx_propertyclaw_bid_status", VENDOR_BID.c.status)


def _require_foundation(db_path):
    """The pre-conversion installer's foundation probe, asked through the seam.

    The original read ``sqlite_master`` directly, so the guard that exists to
    produce a friendly error was itself SQLite-only. ``seam.table_exists``
    answers on both backends (ADR-0034 bulk-39). Wording and streams are the
    original's.
    """
    from erpclaw_lib import seam

    missing = [t for t in REQUIRED_FOUNDATION if not seam.table_exists(t, db_path)]
    if missing:
        print(f"ERROR: Foundation tables missing: {', '.join(missing)}")
        print("Run ERPClaw init_db.py and erpclaw first.", file=sys.stderr)
        sys.exit(1)


def create_propertyclaw_tables(db_path):
    """Create PropertyClaw tables and indexes on whichever backend is configured.

    Same contract as before the ADR-0034 conversion: idempotent, and the returned
    counts are what was ACTUALLY created rather than what was declared.

    Naming series: registered on first use, never pre-seeded. get_next_name()
    (erpclaw_lib/naming.py) self-registers a row via INSERT ... ON CONFLICT DO
    UPDATE under the canonical year-scoped prefix f"{base}{year}-" (e.g.
    "PROP-2026-"), which is also its lookup key. The pre-seed removed earlier
    wrote bare prefixes ("PROP") that nothing read — dead rows that only tripped
    INV-10's naming-format check.
    """
    _require_foundation(db_path)
    result = provision(METADATA, db_path)
    return {
        "database": db_path,
        "tables": result["tables"],
        "indexes": result["indexes"],
    }


if __name__ == "__main__":
    # The parent directory is created by the seam, on the path that knows which
    # backend is configured — an os.makedirs here would build a junk directory
    # out of a PostgreSQL URL.
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    result = create_propertyclaw_tables(db_path)
    print(f"{DISPLAY_NAME} schema created in {result['database']}")
    print(f"  Tables: {result['tables']}")
    print(f"  Indexes: {result['indexes']}")
