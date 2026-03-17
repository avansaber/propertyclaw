#!/usr/bin/env python3
"""PropertyClaw Commercial Real Estate schema extension.

Creates 8 tables for commercial real estate management:
  - commercial_nnn_lease: Triple-net lease master
  - commercial_nnn_charge: NNN expense passthroughs per lease
  - commercial_cam_pool: Common Area Maintenance pools per property/year
  - commercial_cam_expense: Individual CAM expenses within a pool
  - commercial_cam_allocation: CAM allocations per lease within a pool
  - commercial_ti_allowance: Tenant improvement allowances per lease
  - commercial_ti_draw: TI draws against an allowance

All financial amounts stored as TEXT (Python Decimal).
All IDs stored as TEXT (UUID4).
"""
import os
import sqlite3
import sys

DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/erpclaw/data.sqlite")
DISPLAY_NAME = "PropertyClaw Commercial"
REQUIRED_FOUNDATION = ["company", "naming_series", "audit_log"]


def create_commercial_tables(db_path=None):
    db_path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(db_path)
    from erpclaw_lib.db import setup_pragmas
    setup_pragmas(conn)

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    missing = [t for t in REQUIRED_FOUNDATION if t not in tables]
    if missing:
        print(f"ERROR: Foundation tables missing: {', '.join(missing)}")
        conn.close()
        sys.exit(1)

    tables_created = 0
    indexes_created = 0

    # -----------------------------------------------------------------------
    # 1. commercial_nnn_lease — NNN lease master
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_nnn_lease (
            id                    TEXT PRIMARY KEY,
            naming_series         TEXT,
            company_id            TEXT NOT NULL,
            tenant_name           TEXT NOT NULL,
            property_name         TEXT NOT NULL,
            suite_number          TEXT,
            lease_start           TEXT NOT NULL,
            lease_end             TEXT NOT NULL,
            base_rent             TEXT NOT NULL DEFAULT '0',
            cam_share_pct         TEXT NOT NULL DEFAULT '0',
            insurance_share_pct   TEXT NOT NULL DEFAULT '0',
            tax_share_pct         TEXT NOT NULL DEFAULT '0',
            escalation_pct        TEXT NOT NULL DEFAULT '0',
            escalation_frequency  TEXT DEFAULT 'none',
            square_footage        TEXT DEFAULT '0',
            lease_status          TEXT NOT NULL DEFAULT 'draft'
                CHECK(lease_status IN ('draft', 'active', 'expired', 'terminated')),
            notes                 TEXT,
            created_at            TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at            TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_nnn_lease_company
        ON commercial_nnn_lease(company_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_nnn_lease_status
        ON commercial_nnn_lease(lease_status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_nnn_lease_property
        ON commercial_nnn_lease(property_name)
    """)
    indexes_created += 3

    # -----------------------------------------------------------------------
    # 2. commercial_nnn_charge — NNN expense passthroughs
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_nnn_charge (
            id                TEXT PRIMARY KEY,
            lease_id          TEXT NOT NULL,
            expense_type      TEXT NOT NULL
                CHECK(expense_type IN ('cam', 'insurance', 'property_tax', 'other')),
            expense_period    TEXT NOT NULL,
            actual_amount     TEXT NOT NULL DEFAULT '0',
            estimated_amount  TEXT NOT NULL DEFAULT '0',
            tenant_share      TEXT NOT NULL DEFAULT '0',
            description       TEXT,
            company_id        TEXT NOT NULL,
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lease_id) REFERENCES commercial_nnn_lease(id) ON DELETE RESTRICT,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_nnn_charge_lease
        ON commercial_nnn_charge(lease_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_nnn_charge_period
        ON commercial_nnn_charge(expense_period)
    """)
    indexes_created += 2

    # -----------------------------------------------------------------------
    # 3. commercial_expense_passthrough — NNN expense passthroughs per lease
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_expense_passthrough (
            id                TEXT PRIMARY KEY,
            lease_id          TEXT NOT NULL,
            expense_type      TEXT NOT NULL
                CHECK(expense_type IN ('cam', 'insurance', 'tax', 'utility')),
            expense_period    TEXT NOT NULL,
            actual_amount     TEXT NOT NULL DEFAULT '0',
            estimated_amount  TEXT NOT NULL DEFAULT '0',
            tenant_share      TEXT NOT NULL DEFAULT '0',
            reconciled        INTEGER NOT NULL DEFAULT 0 CHECK(reconciled IN (0, 1)),
            company_id        TEXT NOT NULL,
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lease_id) REFERENCES commercial_nnn_lease(id) ON DELETE RESTRICT,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_expense_passthrough_lease
        ON commercial_expense_passthrough(lease_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_expense_passthrough_period
        ON commercial_expense_passthrough(expense_period)
    """)
    indexes_created += 2

    # -----------------------------------------------------------------------
    # 4. commercial_cam_pool — CAM pools per property/year
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_cam_pool (
            id                TEXT PRIMARY KEY,
            naming_series     TEXT,
            company_id        TEXT NOT NULL,
            property_name     TEXT NOT NULL,
            pool_year         TEXT NOT NULL,
            total_budget      TEXT NOT NULL DEFAULT '0',
            total_actual      TEXT NOT NULL DEFAULT '0',
            pool_status       TEXT NOT NULL DEFAULT 'open'
                CHECK(pool_status IN ('open', 'reconciling', 'closed')),
            notes             TEXT,
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT,
            UNIQUE(company_id, property_name, pool_year)
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_cam_pool_company
        ON commercial_cam_pool(company_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_cam_pool_year
        ON commercial_cam_pool(pool_year)
    """)
    indexes_created += 2

    # -----------------------------------------------------------------------
    # 5. commercial_cam_expense — Individual expenses in a CAM pool
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_cam_expense (
            id              TEXT PRIMARY KEY,
            pool_id         TEXT NOT NULL,
            expense_date    TEXT NOT NULL,
            category        TEXT NOT NULL,
            vendor          TEXT,
            amount          TEXT NOT NULL DEFAULT '0',
            description     TEXT,
            company_id      TEXT NOT NULL,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pool_id) REFERENCES commercial_cam_pool(id) ON DELETE RESTRICT,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_cam_expense_pool
        ON commercial_cam_expense(pool_id)
    """)
    indexes_created += 1

    # -----------------------------------------------------------------------
    # 6. commercial_cam_allocation — CAM share per lease in a pool
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_cam_allocation (
            id               TEXT PRIMARY KEY,
            pool_id          TEXT NOT NULL,
            lease_id         TEXT NOT NULL,
            share_pct        TEXT NOT NULL DEFAULT '0',
            budgeted_amount  TEXT NOT NULL DEFAULT '0',
            actual_amount    TEXT NOT NULL DEFAULT '0',
            variance         TEXT NOT NULL DEFAULT '0',
            company_id       TEXT NOT NULL,
            created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pool_id) REFERENCES commercial_cam_pool(id) ON DELETE RESTRICT,
            FOREIGN KEY (lease_id) REFERENCES commercial_nnn_lease(id) ON DELETE RESTRICT,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT,
            UNIQUE(pool_id, lease_id)
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_cam_allocation_pool
        ON commercial_cam_allocation(pool_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_cam_allocation_lease
        ON commercial_cam_allocation(lease_id)
    """)
    indexes_created += 2

    # -----------------------------------------------------------------------
    # 7. commercial_ti_allowance — Tenant improvement allowances
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_ti_allowance (
            id                TEXT PRIMARY KEY,
            naming_series     TEXT,
            lease_id          TEXT NOT NULL,
            total_allowance   TEXT NOT NULL DEFAULT '0',
            disbursed_amount  TEXT NOT NULL DEFAULT '0',
            remaining_amount  TEXT NOT NULL DEFAULT '0',
            contractor        TEXT,
            scope_of_work     TEXT,
            ti_status         TEXT NOT NULL DEFAULT 'approved'
                CHECK(ti_status IN ('approved', 'in_progress', 'completed', 'cancelled')),
            company_id        TEXT NOT NULL,
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lease_id) REFERENCES commercial_nnn_lease(id) ON DELETE RESTRICT,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_ti_allowance_lease
        ON commercial_ti_allowance(lease_id)
    """)
    indexes_created += 1

    # -----------------------------------------------------------------------
    # 8. commercial_ti_draw — TI draws against an allowance
    # -----------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commercial_ti_draw (
            id                  TEXT PRIMARY KEY,
            allowance_id        TEXT NOT NULL,
            draw_date           TEXT NOT NULL,
            amount              TEXT NOT NULL DEFAULT '0',
            description         TEXT,
            invoice_reference   TEXT,
            draw_status         TEXT NOT NULL DEFAULT 'pending'
                CHECK(draw_status IN ('pending', 'approved', 'paid', 'rejected')),
            company_id          TEXT NOT NULL,
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at          TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (allowance_id) REFERENCES commercial_ti_allowance(id) ON DELETE RESTRICT,
            FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT
        )
    """)
    tables_created += 1

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_commercial_ti_draw_allowance
        ON commercial_ti_draw(allowance_id)
    """)
    indexes_created += 1

    conn.commit()
    conn.close()
    return {"database": db_path, "tables": tables_created, "indexes": indexes_created}


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else None
    result = create_commercial_tables(db)
    print(f"{DISPLAY_NAME} schema created in {result['database']}")
    print(f"  Tables: {result['tables']}")
    print(f"  Indexes: {result['indexes']}")
