"""Shared helper functions for PropertyClaw Commercial unit tests.

Provides:
  - DB bootstrap via init_schema.init_db() + propertyclaw init_db + commercial init_db
  - call_action() / ns() / is_error() / is_ok()
  - Seed functions for company, naming series
  - load_db_query() for explicit module loading
"""
import argparse
import importlib.util
import io
import json
import os
import sqlite3
import sys
import uuid
from decimal import Decimal
from unittest.mock import patch

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(TESTS_DIR)   # scripts/
ROOT_DIR = os.path.dirname(MODULE_DIR)    # propertyclaw-commercial/
PARENT_DIR = os.path.dirname(ROOT_DIR)    # src/propertyclaw/
SRC_DIR = os.path.dirname(PARENT_DIR)     # src/
SETUP_DIR = os.path.join(SRC_DIR, "erpclaw", "scripts", "erpclaw-setup")
INIT_SCHEMA_PATH = os.path.join(SETUP_DIR, "init_schema.py")
PROPERTYCLAW_INIT_DB = os.path.join(PARENT_DIR, "propertyclaw", "init_db.py")
COMMERCIAL_INIT_DB = os.path.join(ROOT_DIR, "init_db.py")

# Make erpclaw_lib importable
ERPCLAW_LIB = os.path.expanduser("~/.openclaw/erpclaw/lib")
if ERPCLAW_LIB not in sys.path:
    sys.path.insert(0, ERPCLAW_LIB)

from erpclaw_lib.db import setup_pragmas


def load_db_query():
    """Load commercial db_query.py explicitly to avoid sys.path collisions."""
    db_query_path = os.path.join(MODULE_DIR, "db_query.py")
    spec = importlib.util.spec_from_file_location("db_query_commercial", db_query_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────────────────

def init_all_tables(db_path: str):
    """Create foundation tables + propertyclaw core tables + commercial tables."""
    # 1. Foundation
    spec = importlib.util.spec_from_file_location("init_schema", INIT_SCHEMA_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init_db(db_path)

    # 2. PropertyClaw core tables (leases, units, etc. — FK targets for commercial)
    spec2 = importlib.util.spec_from_file_location("pc_init_db", PROPERTYCLAW_INIT_DB)
    mod2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(mod2)
    mod2.create_propertyclaw_tables(db_path)

    # 3. Commercial tables
    spec3 = importlib.util.spec_from_file_location("comm_init_db", COMMERCIAL_INIT_DB)
    mod3 = importlib.util.module_from_spec(spec3)
    spec3.loader.exec_module(mod3)
    mod3.create_commercial_tables(db_path)


class _ConnWrapper:
    """Wraps sqlite3.Connection to support conn.company_id attribute."""
    def __init__(self, real_conn):
        self._conn = real_conn
        self.company_id = None

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._conn.executemany(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self._conn.executescript(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, val):
        self._conn.row_factory = val


class _DecimalSum:
    """Custom SQLite aggregate: SUM using Python Decimal for precision."""
    def __init__(self):
        self.total = Decimal("0")
    def step(self, value):
        if value is not None:
            self.total += Decimal(str(value))
    def finalize(self):
        return str(self.total)


def get_conn(db_path: str):
    """Return a wrapped sqlite3.Connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    setup_pragmas(conn)
    conn.create_aggregate("decimal_sum", 1, _DecimalSum)
    return _ConnWrapper(conn)


# ──────────────────────────────────────────────────────────────────────────────
# Action invocation helpers
# ──────────────────────────────────────────────────────────────────────────────

def call_action(fn, conn, args) -> dict:
    """Invoke a domain function, capture stdout JSON, return parsed dict."""
    buf = io.StringIO()

    def _fake_exit(code=0):
        raise SystemExit(code)

    try:
        with patch("sys.stdout", buf), patch("sys.exit", side_effect=_fake_exit):
            fn(conn, args)
    except SystemExit:
        pass

    output = buf.getvalue().strip()
    if not output:
        return {"status": "error", "message": "no output captured"}
    return json.loads(output)


def ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace from keyword args (mimics CLI flags)."""
    defaults = {
        "limit": 50, "offset": 0, "search": None,
        "company_id": None, "lease_id": None,
        "name": None, "description": None, "notes": None,
        # NNN Leases
        "tenant_name": None, "property_name": None, "suite_number": None,
        "lease_start": None, "lease_end": None, "base_rent": None,
        "cam_share_pct": None, "insurance_share_pct": None, "tax_share_pct": None,
        "escalation_pct": None, "escalation_frequency": None,
        "square_footage": None, "lease_status": None,
        # Expense Passthrough
        "expense_type": None, "expense_period": None,
        "actual_amount": None, "estimated_amount": None,
        # Invoice
        "invoice_period": None,
        # CAM
        "pool_id": None, "pool_year": None, "total_budget": None,
        "pool_status": None, "expense_date": None, "category": None,
        "vendor": None, "amount": None, "reconciliation_date": None,
        # TI
        "allowance_id": None, "total_allowance": None, "contractor": None,
        "scope_of_work": None, "ti_status": None,
        "draw_date": None, "draw_status": None, "invoice_reference": None,
        # Reports
        "property_value": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def is_error(result: dict) -> bool:
    return result.get("status") == "error"


def is_ok(result: dict) -> bool:
    return result.get("status") == "ok"


# ──────────────────────────────────────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


# ──────────────────────────────────────────────────────────────────────────────
# Seed helpers
# ──────────────────────────────────────────────────────────────────────────────

def seed_company(conn, name="Test Co", abbr="TC", country="United States") -> str:
    cid = _uuid()
    conn.execute(
        """INSERT INTO company (id, name, abbr, default_currency, country,
           fiscal_year_start_month)
           VALUES (?, ?, ?, 'USD', ?, 1)""",
        (cid, f"{name} {cid[:6]}", f"{abbr}{cid[:4]}", country)
    )
    conn.commit()
    return cid


def seed_naming_series(conn, company_id: str):
    """Seed naming series for commercial entity types."""
    series = [
        ("commercial_nnn_lease", "CNNN-", 0),
        ("commercial_cam_pool", "CCAM-", 0),
        ("commercial_ti_allowance", "CTI-", 0),
        ("propertyclaw_property", "PROP-", 0),
        ("propertyclaw_unit", "UNIT-", 0),
        ("propertyclaw_lease", "LEASE-", 0),
    ]
    for entity_type, prefix, current in series:
        conn.execute(
            """INSERT OR IGNORE INTO naming_series
               (id, entity_type, prefix, current_value, company_id)
               VALUES (?, ?, ?, ?, ?)""",
            (_uuid(), entity_type, prefix, current, company_id)
        )
    conn.commit()


def seed_fiscal_year(conn, company_id: str,
                     start="2026-01-01", end="2026-12-31") -> str:
    fid = _uuid()
    conn.execute(
        """INSERT INTO fiscal_year (id, name, start_date, end_date, company_id)
           VALUES (?, ?, ?, ?, ?)""",
        (fid, f"FY-{fid[:6]}", start, end, company_id)
    )
    conn.commit()
    return fid


def build_env(conn) -> dict:
    """Create a full commercial test environment."""
    cid = seed_company(conn)
    seed_naming_series(conn, cid)
    seed_fiscal_year(conn, cid)
    return {"company_id": cid}
