#!/usr/bin/env python3
"""PropertyClaw Commercial Real Estate schema extension.

Creates 7 tables for commercial real estate management:
  - commercial_nnn_lease: Triple-net lease master
  - commercial_expense_passthrough: NNN expense passthroughs per lease
  - commercial_cam_pool: Common Area Maintenance pools per property/year
  - commercial_cam_expense: Individual CAM expenses within a pool
  - commercial_cam_allocation: CAM allocations per lease within a pool
  - commercial_ti_allowance: Tenant improvement allowances per lease
  - commercial_ti_draw: TI draws against an allowance

(The pre-conversion docstring said "8 tables" and listed `commercial_nnn_charge`,
which migration 001 dropped on 2026-06-01, while omitting
`commercial_expense_passthrough`, which the installer has always created. Both
were stale; the installer creates 7 tables and 12 indexes.)

All financial amounts stored as TEXT (Python Decimal).
All IDs stored as TEXT (UUID4).

ADR-0034 phase 2 bulk-39. The schema is declared as metadata and provisioned
through `erpclaw_lib.seam`, which emits dialect-correct DDL, replacing a
hand-written ``CREATE TABLE`` block opened with ``sqlite3.connect`` that could
not run on PostgreSQL at all. Seam vocabulary only; IDs and every amount stay
TEXT on every backend (base rent, CAM shares, TI allowances and draws all live
here), and ``primary_key=True, nullable=True`` reproduces SQLite's
``id TEXT PRIMARY KEY`` without adding a NOT NULL that never shipped.

The two table-level ``UNIQUE`` clauses — one CAM pool per company/property/year,
one CAM allocation per pool/lease — are idempotency keys: losing either would let
a re-run double-book a pool or an allocation. They are declared as
`UniqueConstraint` and left unnamed, as shipped.

Foreign keys point only at this module's own `commercial_*` tables and at
foundation's `company`. Despite the shared `propertyclaw` prefix in the repo,
nothing here references a `propertyclaw_*` table, so this module has no
install-order dependency on `propertyclaw` on PostgreSQL. (The converted
`propertyclaw` installer's docstring states the opposite; that claim is wrong and
is left for its owner to correct.)
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
    UniqueConstraint, provision, reference_table, text,
)

DEFAULT_DB_PATH = os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "data.sqlite")
DISPLAY_NAME = "PropertyClaw Commercial"
REQUIRED_FOUNDATION = ["company", "naming_series", "audit_log"]

METADATA = MetaData()

# Foundation table this module points at but does not own. Declared for foreign
# key resolution only and never created here — see `seam.reference_table`.
reference_table("company", METADATA)


# ---------------------------------------------------------------------------
# 1. commercial_nnn_lease — NNN lease master
# ---------------------------------------------------------------------------
NNN_LEASE = Table(
    "commercial_nnn_lease", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("tenant_name", Text, nullable=False),
    Column("property_name", Text, nullable=False),
    Column("suite_number", Text),
    Column("lease_start", Text, nullable=False),
    Column("lease_end", Text, nullable=False),
    Column("base_rent", Text, nullable=False, server_default=text("'0'")),
    Column("cam_share_pct", Text, nullable=False, server_default=text("'0'")),
    Column("insurance_share_pct", Text, nullable=False,
           server_default=text("'0'")),
    Column("tax_share_pct", Text, nullable=False, server_default=text("'0'")),
    Column("escalation_pct", Text, nullable=False, server_default=text("'0'")),
    Column("escalation_frequency", Text, server_default=text("'none'")),
    Column("square_footage", Text, server_default=text("'0'")),
    Column("lease_status", Text, nullable=False, server_default=text("'draft'")),
    Column("notes", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "lease_status IN ('draft', 'active', 'expired', 'terminated')",
        name="ck_commercial_nnn_lease_lease_status"),
)

Index("idx_commercial_nnn_lease_company", NNN_LEASE.c.company_id)
Index("idx_commercial_nnn_lease_status", NNN_LEASE.c.lease_status)
Index("idx_commercial_nnn_lease_property", NNN_LEASE.c.property_name)

# ---------------------------------------------------------------------------
# commercial_nnn_charge removed 2026-06-01 (audit P2): dead scaffolding (zero
# code/doc references); commercial_nnn_lease kept. Dropped from existing DBs by
# this module's migration 001.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 2. commercial_expense_passthrough — NNN expense passthroughs per lease
# ---------------------------------------------------------------------------
EXPENSE_PASSTHROUGH = Table(
    "commercial_expense_passthrough", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("lease_id", Text,
           ForeignKey("commercial_nnn_lease.id", ondelete="RESTRICT"),
           nullable=False),
    Column("expense_type", Text, nullable=False),
    Column("expense_period", Text, nullable=False),
    Column("actual_amount", Text, nullable=False, server_default=text("'0'")),
    Column("estimated_amount", Text, nullable=False, server_default=text("'0'")),
    Column("tenant_share", Text, nullable=False, server_default=text("'0'")),
    # A 0/1 flag, not an amount — Integer as shipped.
    Column("reconciled", Integer, nullable=False, server_default=text("0")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "expense_type IN ('cam', 'insurance', 'tax', 'utility')",
        name="ck_commercial_expense_passthrough_expense_type"),
    CheckConstraint("reconciled IN (0, 1)",
                    name="ck_commercial_expense_passthrough_reconciled"),
)

Index("idx_commercial_expense_passthrough_lease",
      EXPENSE_PASSTHROUGH.c.lease_id)
Index("idx_commercial_expense_passthrough_period",
      EXPENSE_PASSTHROUGH.c.expense_period)

# ---------------------------------------------------------------------------
# 3. commercial_cam_pool — CAM pools per property/year
# ---------------------------------------------------------------------------
CAM_POOL = Table(
    "commercial_cam_pool", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("property_name", Text, nullable=False),
    Column("pool_year", Text, nullable=False),
    Column("total_budget", Text, nullable=False, server_default=text("'0'")),
    Column("total_actual", Text, nullable=False, server_default=text("'0'")),
    Column("pool_status", Text, nullable=False, server_default=text("'open'")),
    Column("notes", Text),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("pool_status IN ('open', 'reconciling', 'closed')",
                    name="ck_commercial_cam_pool_pool_status"),
    # One pool per company, property and year. Unnamed, as shipped: SQLite backs
    # it with an implicit `sqlite_autoindex` the parity oracle filters out, so it
    # is carried here by transcription rather than by the index diff.
    UniqueConstraint("company_id", "property_name", "pool_year"),
)

Index("idx_commercial_cam_pool_company", CAM_POOL.c.company_id)
Index("idx_commercial_cam_pool_year", CAM_POOL.c.pool_year)

# ---------------------------------------------------------------------------
# 4. commercial_cam_expense — Individual expenses in a CAM pool
# ---------------------------------------------------------------------------
CAM_EXPENSE = Table(
    "commercial_cam_expense", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("pool_id", Text,
           ForeignKey("commercial_cam_pool.id", ondelete="RESTRICT"),
           nullable=False),
    Column("expense_date", Text, nullable=False),
    Column("category", Text, nullable=False),
    Column("vendor", Text),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("description", Text),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    # No `updated_at` here, unlike its siblings. Transcribed, not tidied.
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
)

Index("idx_commercial_cam_expense_pool", CAM_EXPENSE.c.pool_id)

# ---------------------------------------------------------------------------
# 5. commercial_cam_allocation — CAM share per lease in a pool
# ---------------------------------------------------------------------------
CAM_ALLOCATION = Table(
    "commercial_cam_allocation", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("pool_id", Text,
           ForeignKey("commercial_cam_pool.id", ondelete="RESTRICT"),
           nullable=False),
    Column("lease_id", Text,
           ForeignKey("commercial_nnn_lease.id", ondelete="RESTRICT"),
           nullable=False),
    Column("share_pct", Text, nullable=False, server_default=text("'0'")),
    Column("budgeted_amount", Text, nullable=False, server_default=text("'0'")),
    Column("actual_amount", Text, nullable=False, server_default=text("'0'")),
    Column("variance", Text, nullable=False, server_default=text("'0'")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    # One allocation per lease within a pool. Unnamed, as shipped.
    UniqueConstraint("pool_id", "lease_id"),
)

Index("idx_commercial_cam_allocation_pool", CAM_ALLOCATION.c.pool_id)
Index("idx_commercial_cam_allocation_lease", CAM_ALLOCATION.c.lease_id)

# ---------------------------------------------------------------------------
# 6. commercial_ti_allowance — Tenant improvement allowances
# ---------------------------------------------------------------------------
TI_ALLOWANCE = Table(
    "commercial_ti_allowance", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("lease_id", Text,
           ForeignKey("commercial_nnn_lease.id", ondelete="RESTRICT"),
           nullable=False),
    Column("total_allowance", Text, nullable=False, server_default=text("'0'")),
    Column("disbursed_amount", Text, nullable=False, server_default=text("'0'")),
    Column("remaining_amount", Text, nullable=False, server_default=text("'0'")),
    Column("contractor", Text),
    Column("scope_of_work", Text),
    Column("ti_status", Text, nullable=False, server_default=text("'approved'")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "ti_status IN ('approved', 'in_progress', 'completed', 'cancelled')",
        name="ck_commercial_ti_allowance_ti_status"),
)

Index("idx_commercial_ti_allowance_lease", TI_ALLOWANCE.c.lease_id)

# ---------------------------------------------------------------------------
# 7. commercial_ti_draw — TI draws against an allowance
# ---------------------------------------------------------------------------
TI_DRAW = Table(
    "commercial_ti_draw", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("allowance_id", Text,
           ForeignKey("commercial_ti_allowance.id", ondelete="RESTRICT"),
           nullable=False),
    Column("draw_date", Text, nullable=False),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("description", Text),
    Column("invoice_reference", Text),
    Column("draw_status", Text, nullable=False,
           server_default=text("'pending'")),
    Column("company_id", Text,
           ForeignKey("company.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "draw_status IN ('pending', 'approved', 'paid', 'rejected')",
        name="ck_commercial_ti_draw_draw_status"),
)

Index("idx_commercial_ti_draw_allowance", TI_DRAW.c.allowance_id)


def _require_foundation(db_path):
    """The pre-conversion installer's foundation probe, asked through the seam.

    The original read ``sqlite_master`` directly, so the guard that exists to
    produce a friendly error was itself SQLite-only. ``seam.table_exists``
    answers on both backends (ADR-0034 bulk-39). Wording and stream are the
    original's.
    """
    from erpclaw_lib import seam

    missing = [t for t in REQUIRED_FOUNDATION if not seam.table_exists(t, db_path)]
    if missing:
        print(f"ERROR: Foundation tables missing: {', '.join(missing)}")
        sys.exit(1)


def create_commercial_tables(db_path=None):
    """Create the commercial tables and indexes on whichever backend is configured.

    Same contract as before the ADR-0034 conversion: idempotent, and the returned
    counts are what was ACTUALLY created rather than what was declared.
    """
    db_path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)
    _require_foundation(db_path)
    result = provision(METADATA, db_path)
    return {
        "database": db_path,
        "tables": result["tables"],
        "indexes": result["indexes"],
    }


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else None
    result = create_commercial_tables(db)
    print(f"{DISPLAY_NAME} schema created in {result['database']}")
    print(f"  Tables: {result['tables']}")
    print(f"  Indexes: {result['indexes']}")
