#!/usr/bin/env python3
"""PropertyClaw schema extension — adds domain tables to the shared database.

Prerequisite: ERPClaw init_db.py must have run first (creates foundation tables).
Run: python3 init_db.py [db_path]

Tables: 23 domain tables, ~65 indexes, 7 naming series
Skills: propertyclaw-properties, propertyclaw-leases, propertyclaw-tenants,
        propertyclaw-maintenance, propertyclaw-accounting
"""
import os
import sqlite3
import sys
import uuid


DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/erpclaw/data.sqlite")
DISPLAY_NAME = "PropertyClaw"


def create_propertyclaw_tables(db_path):
    conn = sqlite3.connect(db_path)
    from erpclaw_lib.db import setup_pragmas
    setup_pragmas(conn)

    # Verify foundation exists
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    required = ["company", "customer", "supplier", "account",
                "sales_invoice", "purchase_invoice", "payment_entry",
                "gl_entry", "naming_series", "recurring_invoice_template"]
    missing = [t for t in required if t not in tables]
    if missing:
        print(f"ERROR: Foundation tables missing: {', '.join(missing)}")
        print("Run ERPClaw init_db.py and erpclaw first.", file=sys.stderr)
        sys.exit(1)

    conn.executescript("""
        -- ==========================================================
        -- PropertyClaw Domain Tables (23 tables)
        -- Convention: propertyclaw_ prefix, TEXT for IDs/money/dates,
        --   INTEGER for booleans with CHECK(x IN (0,1)),
        --   FK with ON DELETE RESTRICT
        -- ==========================================================


        -- ==========================================================
        -- propertyclaw-properties (4 tables)
        -- ==========================================================

        -- Property: building or land parcel
        CREATE TABLE IF NOT EXISTS propertyclaw_property (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            name            TEXT NOT NULL,
            property_type   TEXT NOT NULL DEFAULT 'residential'
                            CHECK(property_type IN ('residential','commercial','mixed')),
            address_line1   TEXT NOT NULL,
            address_line2   TEXT,
            city            TEXT NOT NULL,
            state           TEXT NOT NULL,
            zip_code        TEXT NOT NULL,
            county          TEXT,
            year_built      INTEGER,
            total_units     INTEGER NOT NULL DEFAULT 1,
            owner_name      TEXT,
            owner_contact   TEXT,
            management_fee_pct TEXT,
            status          TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','inactive','archived')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_property_company
            ON propertyclaw_property(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_property_status
            ON propertyclaw_property(status);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_property_state
            ON propertyclaw_property(state);

        -- Unit: individual rentable space within a property
        CREATE TABLE IF NOT EXISTS propertyclaw_unit (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            property_id     TEXT NOT NULL REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            unit_number     TEXT NOT NULL,
            unit_type       TEXT NOT NULL DEFAULT 'apartment'
                            CHECK(unit_type IN ('apartment','house','condo','townhouse',
                                'commercial','storage','parking')),
            bedrooms        INTEGER,
            bathrooms       TEXT,
            sq_ft           INTEGER,
            floor           INTEGER,
            market_rent     TEXT NOT NULL DEFAULT '0',
            status          TEXT NOT NULL DEFAULT 'available'
                            CHECK(status IN ('available','occupied','maintenance','reserved')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(property_id, unit_number)
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_unit_property
            ON propertyclaw_unit(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_unit_status
            ON propertyclaw_unit(status);

        -- Amenity: feature of a property or unit
        CREATE TABLE IF NOT EXISTS propertyclaw_amenity (
            id              TEXT PRIMARY KEY,
            property_id     TEXT REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            unit_id         TEXT REFERENCES propertyclaw_unit(id) ON DELETE RESTRICT,
            amenity_scope   TEXT NOT NULL CHECK(amenity_scope IN ('property','unit')),
            name            TEXT NOT NULL,
            description     TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_amenity_property
            ON propertyclaw_amenity(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_amenity_unit
            ON propertyclaw_amenity(unit_id);

        -- Property photo
        CREATE TABLE IF NOT EXISTS propertyclaw_property_photo (
            id              TEXT PRIMARY KEY,
            property_id     TEXT REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            unit_id         TEXT REFERENCES propertyclaw_unit(id) ON DELETE RESTRICT,
            photo_scope     TEXT NOT NULL CHECK(photo_scope IN ('property','unit','inspection')),
            file_url        TEXT NOT NULL,
            description     TEXT,
            uploaded_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_photo_property
            ON propertyclaw_property_photo(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_photo_unit
            ON propertyclaw_property_photo(unit_id);


        -- ==========================================================
        -- propertyclaw-leases (5 tables)
        -- ==========================================================

        -- Lease agreement
        CREATE TABLE IF NOT EXISTS propertyclaw_lease (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            property_id     TEXT NOT NULL REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            unit_id         TEXT NOT NULL REFERENCES propertyclaw_unit(id) ON DELETE RESTRICT,
            customer_id     TEXT NOT NULL REFERENCES customer(id) ON DELETE RESTRICT,
            lease_type      TEXT NOT NULL DEFAULT 'fixed'
                            CHECK(lease_type IN ('fixed','month_to_month')),
            start_date      TEXT NOT NULL,
            end_date        TEXT,
            monthly_rent    TEXT NOT NULL DEFAULT '0',
            security_deposit_amount TEXT NOT NULL DEFAULT '0',
            deposit_account_id TEXT REFERENCES account(id) ON DELETE RESTRICT,
            move_in_date    TEXT,
            move_out_date   TEXT,
            recurring_template_id TEXT REFERENCES recurring_invoice_template(id) ON DELETE RESTRICT,
            status          TEXT NOT NULL DEFAULT 'draft'
                            CHECK(status IN ('draft','active','expired','terminated','renewed')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_lease_company
            ON propertyclaw_lease(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_lease_property
            ON propertyclaw_lease(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_lease_unit
            ON propertyclaw_lease(unit_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_lease_customer
            ON propertyclaw_lease(customer_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_lease_status
            ON propertyclaw_lease(status);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_lease_dates
            ON propertyclaw_lease(start_date, end_date);

        -- Rent schedule: recurring charges on a lease
        CREATE TABLE IF NOT EXISTS propertyclaw_rent_schedule (
            id              TEXT PRIMARY KEY,
            lease_id        TEXT NOT NULL REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            charge_type     TEXT NOT NULL CHECK(charge_type IN (
                                'base_rent','pet_rent','parking','storage','utility','other')),
            description     TEXT,
            amount          TEXT NOT NULL DEFAULT '0',
            frequency       TEXT NOT NULL DEFAULT 'monthly'
                            CHECK(frequency IN ('weekly','biweekly','monthly')),
            start_date      TEXT NOT NULL,
            end_date        TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_rent_sched_lease
            ON propertyclaw_rent_schedule(lease_id);

        -- Lease charge: individual charge instance
        CREATE TABLE IF NOT EXISTS propertyclaw_lease_charge (
            id              TEXT PRIMARY KEY,
            lease_id        TEXT NOT NULL REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            charge_date     TEXT NOT NULL,
            charge_type     TEXT NOT NULL,
            description     TEXT,
            amount          TEXT NOT NULL DEFAULT '0',
            invoice_id      TEXT REFERENCES sales_invoice(id) ON DELETE RESTRICT,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','invoiced','paid','waived')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_charge_lease
            ON propertyclaw_lease_charge(lease_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_charge_date
            ON propertyclaw_lease_charge(charge_date);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_charge_status
            ON propertyclaw_lease_charge(status);

        -- Late fee rules: state-specific
        CREATE TABLE IF NOT EXISTS propertyclaw_late_fee_rule (
            id              TEXT PRIMARY KEY,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            state           TEXT NOT NULL,
            fee_type        TEXT NOT NULL CHECK(fee_type IN ('flat','percentage','lower_of','greater_of')),
            flat_amount     TEXT,
            percentage_rate TEXT,
            grace_days      INTEGER NOT NULL DEFAULT 0,
            max_cap         TEXT,
            is_default      INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, state)
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_late_fee_company
            ON propertyclaw_late_fee_rule(company_id);

        -- Lease renewal tracking
        CREATE TABLE IF NOT EXISTS propertyclaw_lease_renewal (
            id              TEXT PRIMARY KEY,
            lease_id        TEXT NOT NULL REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            previous_lease_id TEXT REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            new_start_date  TEXT NOT NULL,
            new_end_date    TEXT,
            new_monthly_rent TEXT NOT NULL DEFAULT '0',
            rent_increase_pct TEXT,
            status          TEXT NOT NULL DEFAULT 'proposed'
                            CHECK(status IN ('proposed','accepted','rejected','expired')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_renewal_lease
            ON propertyclaw_lease_renewal(lease_id);


        -- ==========================================================
        -- propertyclaw-tenants (4 tables)
        -- ==========================================================

        -- Rental application
        CREATE TABLE IF NOT EXISTS propertyclaw_application (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            property_id     TEXT NOT NULL REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            unit_id         TEXT REFERENCES propertyclaw_unit(id) ON DELETE RESTRICT,
            applicant_name  TEXT NOT NULL,
            applicant_email TEXT,
            applicant_phone TEXT,
            desired_move_in TEXT,
            monthly_income  TEXT,
            employer        TEXT,
            customer_id     TEXT REFERENCES customer(id) ON DELETE RESTRICT,
            denial_reason   TEXT,
            status          TEXT NOT NULL DEFAULT 'received'
                            CHECK(status IN ('received','screening','approved','denied','withdrawn')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_app_company
            ON propertyclaw_application(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_app_property
            ON propertyclaw_application(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_app_status
            ON propertyclaw_application(status);

        -- Screening request (FCRA compliant — never store raw credit data)
        CREATE TABLE IF NOT EXISTS propertyclaw_screening_request (
            id              TEXT PRIMARY KEY,
            application_id  TEXT NOT NULL REFERENCES propertyclaw_application(id) ON DELETE RESTRICT,
            screening_type  TEXT NOT NULL CHECK(screening_type IN ('credit','criminal','eviction','income')),
            consent_obtained INTEGER NOT NULL DEFAULT 0 CHECK(consent_obtained IN (0,1)),
            consent_date    TEXT,
            request_date    TEXT,
            result          TEXT NOT NULL DEFAULT 'pending'
                            CHECK(result IN ('pending','pass','fail','review')),
            adverse_action_sent INTEGER NOT NULL DEFAULT 0 CHECK(adverse_action_sent IN (0,1)),
            adverse_action_date TEXT,
            notes           TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_screen_app
            ON propertyclaw_screening_request(application_id);

        -- Tenant documents
        CREATE TABLE IF NOT EXISTS propertyclaw_tenant_document (
            id              TEXT PRIMARY KEY,
            customer_id     TEXT NOT NULL REFERENCES customer(id) ON DELETE RESTRICT,
            lease_id        TEXT REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            document_type   TEXT NOT NULL CHECK(document_type IN (
                                'lease','lead_paint_disclosure','move_in_inspection',
                                'move_out_inspection','application','id_copy',
                                'insurance','w9','other')),
            file_url        TEXT NOT NULL,
            description     TEXT,
            expiry_date     TEXT,
            uploaded_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_doc_customer
            ON propertyclaw_tenant_document(customer_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_doc_lease
            ON propertyclaw_tenant_document(lease_id);

        -- Adverse action notice (FCRA)
        CREATE TABLE IF NOT EXISTS propertyclaw_adverse_action (
            id              TEXT PRIMARY KEY,
            application_id  TEXT NOT NULL REFERENCES propertyclaw_application(id) ON DELETE RESTRICT,
            screening_request_id TEXT REFERENCES propertyclaw_screening_request(id) ON DELETE RESTRICT,
            notice_date     TEXT NOT NULL,
            cra_name        TEXT NOT NULL,
            cra_address     TEXT,
            cra_phone       TEXT,
            reason          TEXT NOT NULL,
            delivery_method TEXT CHECK(delivery_method IN ('mail','email','hand')),
            delivered_date  TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_adverse_app
            ON propertyclaw_adverse_action(application_id);


        -- ==========================================================
        -- propertyclaw-maintenance (5 tables)
        -- ==========================================================

        -- Work order
        CREATE TABLE IF NOT EXISTS propertyclaw_work_order (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            property_id     TEXT NOT NULL REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            unit_id         TEXT REFERENCES propertyclaw_unit(id) ON DELETE RESTRICT,
            lease_id        TEXT REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            customer_id     TEXT REFERENCES customer(id) ON DELETE RESTRICT,
            category        TEXT NOT NULL DEFAULT 'general'
                            CHECK(category IN ('plumbing','electrical','hvac','appliance',
                                'structural','general','landscaping','pest','safety')),
            priority        TEXT NOT NULL DEFAULT 'routine'
                            CHECK(priority IN ('emergency','urgent','routine')),
            description     TEXT NOT NULL,
            reported_date   TEXT NOT NULL,
            scheduled_date  TEXT,
            completed_date  TEXT,
            estimated_cost  TEXT,
            actual_cost     TEXT,
            supplier_id     TEXT REFERENCES supplier(id) ON DELETE RESTRICT,
            purchase_invoice_id TEXT REFERENCES purchase_invoice(id) ON DELETE RESTRICT,
            billable_to_tenant INTEGER NOT NULL DEFAULT 0 CHECK(billable_to_tenant IN (0,1)),
            permission_to_enter INTEGER NOT NULL DEFAULT 0 CHECK(permission_to_enter IN (0,1)),
            status          TEXT NOT NULL DEFAULT 'open'
                            CHECK(status IN ('open','assigned','in_progress','completed','cancelled')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_wo_company
            ON propertyclaw_work_order(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_wo_property
            ON propertyclaw_work_order(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_wo_unit
            ON propertyclaw_work_order(unit_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_wo_status
            ON propertyclaw_work_order(status);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_wo_priority
            ON propertyclaw_work_order(priority);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_wo_supplier
            ON propertyclaw_work_order(supplier_id);

        -- Work order line items
        CREATE TABLE IF NOT EXISTS propertyclaw_work_order_item (
            id              TEXT PRIMARY KEY,
            work_order_id   TEXT NOT NULL REFERENCES propertyclaw_work_order(id) ON DELETE RESTRICT,
            description     TEXT NOT NULL,
            item_type       TEXT NOT NULL CHECK(item_type IN ('labor','material','other')),
            quantity        TEXT NOT NULL DEFAULT '1',
            rate            TEXT NOT NULL DEFAULT '0',
            amount          TEXT NOT NULL DEFAULT '0',
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_woi_wo
            ON propertyclaw_work_order_item(work_order_id);

        -- Property/unit inspection
        CREATE TABLE IF NOT EXISTS propertyclaw_inspection (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            property_id     TEXT NOT NULL REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            unit_id         TEXT REFERENCES propertyclaw_unit(id) ON DELETE RESTRICT,
            lease_id        TEXT REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            inspection_type TEXT NOT NULL CHECK(inspection_type IN (
                                'move_in','move_out','routine','pre_listing')),
            inspection_date TEXT NOT NULL,
            inspector_name  TEXT,
            overall_condition TEXT CHECK(overall_condition IN ('excellent','good','fair','poor')),
            notes           TEXT,
            status          TEXT NOT NULL DEFAULT 'scheduled'
                            CHECK(status IN ('scheduled','completed','reviewed')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_insp_company
            ON propertyclaw_inspection(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_insp_property
            ON propertyclaw_inspection(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_insp_type
            ON propertyclaw_inspection(inspection_type);

        -- Inspection checklist items
        CREATE TABLE IF NOT EXISTS propertyclaw_inspection_item (
            id              TEXT PRIMARY KEY,
            inspection_id   TEXT NOT NULL REFERENCES propertyclaw_inspection(id) ON DELETE RESTRICT,
            area            TEXT NOT NULL CHECK(area IN (
                                'kitchen','bathroom','bedroom','living_room',
                                'dining_room','exterior','garage','other')),
            item            TEXT NOT NULL CHECK(item IN (
                                'walls','floors','ceiling','windows','doors',
                                'fixtures','appliances','cabinets','other')),
            condition       TEXT NOT NULL CHECK(condition IN ('good','fair','poor','damaged','missing')),
            description     TEXT,
            photo_url       TEXT,
            estimated_repair_cost TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_inspi_insp
            ON propertyclaw_inspection_item(inspection_id);

        -- Vendor assignment to work order
        CREATE TABLE IF NOT EXISTS propertyclaw_vendor_assignment (
            id              TEXT PRIMARY KEY,
            work_order_id   TEXT NOT NULL REFERENCES propertyclaw_work_order(id) ON DELETE RESTRICT,
            supplier_id     TEXT NOT NULL REFERENCES supplier(id) ON DELETE RESTRICT,
            assigned_date   TEXT NOT NULL,
            estimated_arrival TEXT,
            actual_arrival  TEXT,
            status          TEXT NOT NULL DEFAULT 'assigned'
                            CHECK(status IN ('assigned','accepted','declined','en_route','on_site','completed')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_va_wo
            ON propertyclaw_vendor_assignment(work_order_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_va_supplier
            ON propertyclaw_vendor_assignment(supplier_id);


        -- ==========================================================
        -- propertyclaw-accounting (5 tables)
        -- ==========================================================

        -- Trust account linking (property → GL trust account)
        CREATE TABLE IF NOT EXISTS propertyclaw_trust_account (
            id              TEXT PRIMARY KEY,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            property_id     TEXT NOT NULL REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            account_id      TEXT NOT NULL REFERENCES account(id) ON DELETE RESTRICT,
            bank_name       TEXT,
            status          TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','frozen','closed')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, property_id)
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_trust_company
            ON propertyclaw_trust_account(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_trust_property
            ON propertyclaw_trust_account(property_id);

        -- Monthly owner statement
        CREATE TABLE IF NOT EXISTS propertyclaw_owner_statement (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            property_id     TEXT NOT NULL REFERENCES propertyclaw_property(id) ON DELETE RESTRICT,
            owner_name      TEXT NOT NULL,
            period_start    TEXT NOT NULL,
            period_end      TEXT NOT NULL,
            gross_rent      TEXT NOT NULL DEFAULT '0',
            other_income    TEXT NOT NULL DEFAULT '0',
            management_fee  TEXT NOT NULL DEFAULT '0',
            maintenance_expense TEXT NOT NULL DEFAULT '0',
            other_expense   TEXT NOT NULL DEFAULT '0',
            net_distribution TEXT NOT NULL DEFAULT '0',
            payment_entry_id TEXT REFERENCES payment_entry(id) ON DELETE RESTRICT,
            status          TEXT NOT NULL DEFAULT 'draft'
                            CHECK(status IN ('draft','sent','paid')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_owner_stmt_company
            ON propertyclaw_owner_statement(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_owner_stmt_property
            ON propertyclaw_owner_statement(property_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_owner_stmt_period
            ON propertyclaw_owner_statement(period_start, period_end);

        -- Security deposit tracking
        CREATE TABLE IF NOT EXISTS propertyclaw_security_deposit (
            id              TEXT PRIMARY KEY,
            lease_id        TEXT NOT NULL REFERENCES propertyclaw_lease(id) ON DELETE RESTRICT,
            customer_id     TEXT NOT NULL REFERENCES customer(id) ON DELETE RESTRICT,
            amount          TEXT NOT NULL DEFAULT '0',
            deposit_date    TEXT NOT NULL,
            trust_account_id TEXT REFERENCES propertyclaw_trust_account(id) ON DELETE RESTRICT,
            gl_entry_id     TEXT,
            interest_rate   TEXT,
            interest_accrued TEXT NOT NULL DEFAULT '0',
            return_deadline TEXT,
            return_date     TEXT,
            return_amount   TEXT,
            deduction_amount TEXT NOT NULL DEFAULT '0',
            status          TEXT NOT NULL DEFAULT 'held'
                            CHECK(status IN ('held','partially_returned','returned','forfeited')),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_deposit_lease
            ON propertyclaw_security_deposit(lease_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_deposit_customer
            ON propertyclaw_security_deposit(customer_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_deposit_status
            ON propertyclaw_security_deposit(status);

        -- Deposit deductions
        CREATE TABLE IF NOT EXISTS propertyclaw_deposit_deduction (
            id              TEXT PRIMARY KEY,
            security_deposit_id TEXT NOT NULL REFERENCES propertyclaw_security_deposit(id) ON DELETE RESTRICT,
            deduction_type  TEXT NOT NULL CHECK(deduction_type IN ('damages','unpaid_rent','cleaning','other')),
            description     TEXT NOT NULL,
            amount          TEXT NOT NULL DEFAULT '0',
            invoice_url     TEXT,
            receipt_url     TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_deduction_deposit
            ON propertyclaw_deposit_deduction(security_deposit_id);

        -- 1099 tracking
        CREATE TABLE IF NOT EXISTS propertyclaw_tax_1099 (
            id              TEXT PRIMARY KEY,
            company_id      TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            supplier_id     TEXT NOT NULL REFERENCES supplier(id) ON DELETE RESTRICT,
            tax_year        INTEGER NOT NULL,
            total_payments  TEXT NOT NULL DEFAULT '0',
            form_type       TEXT NOT NULL DEFAULT '1099_nec'
                            CHECK(form_type IN ('1099_nec','1099_misc')),
            filing_status   TEXT NOT NULL DEFAULT 'pending'
                            CHECK(filing_status IN ('pending','filed','corrected')),
            filed_date      TEXT,
            w9_on_file      INTEGER NOT NULL DEFAULT 0 CHECK(w9_on_file IN (0,1)),
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, supplier_id, tax_year, form_type)
        );
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_1099_company
            ON propertyclaw_tax_1099(company_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_1099_supplier
            ON propertyclaw_tax_1099(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_propertyclaw_1099_year
            ON propertyclaw_tax_1099(tax_year);
    """)

    # Insert naming series for each company
    naming_series = [
        ("propertyclaw_property", "PROP"),
        ("propertyclaw_unit", "UNIT"),
        ("propertyclaw_lease", "LEASE"),
        ("propertyclaw_application", "APP"),
        ("propertyclaw_work_order", "WO"),
        ("propertyclaw_inspection", "INSP"),
        ("propertyclaw_owner_statement", "OWN"),
    ]
    companies = conn.execute("SELECT id FROM company").fetchall()
    for company_row in companies:
        company_id = company_row[0]
        for entity_type, prefix in naming_series:
            existing = conn.execute(
                "SELECT 1 FROM naming_series WHERE entity_type = ? AND prefix = ? AND company_id = ?",
                (entity_type, prefix, company_id)
            ).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO naming_series (id, entity_type, prefix, current_value, company_id)
                    VALUES (?, ?, ?, 0, ?)
                """, (str(uuid.uuid4()), entity_type, prefix, company_id))

    conn.commit()
    conn.close()

    # Count tables created
    verify_conn = sqlite3.connect(db_path)
    count = verify_conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'propertyclaw_%'"
    ).fetchone()[0]
    verify_conn.close()

    print(f"{DISPLAY_NAME} schema created: {count} tables in {db_path}", file=sys.stderr)


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    create_propertyclaw_tables(db_path)
