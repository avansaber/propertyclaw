"""Shared helper functions for PropertyClaw core unit tests.

Provides:
  - DB bootstrap via init_schema.init_db() + propertyclaw init_db
  - call_action() / ns() / is_error() / is_ok()
  - Seed functions for company, accounts, customers, naming series
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
ROOT_DIR = os.path.dirname(MODULE_DIR)    # propertyclaw/
PARENT_DIR = os.path.dirname(ROOT_DIR)    # source/propertyclaw/
SRC_DIR = os.path.dirname(PARENT_DIR)     # source/
SETUP_DIR = os.path.join(SRC_DIR, "erpclaw", "scripts", "erpclaw-setup")
INIT_SCHEMA_PATH = os.path.join(SETUP_DIR, "init_schema.py")
PROPERTYCLAW_INIT_DB = os.path.join(ROOT_DIR, "init_db.py")

# Make erpclaw_lib importable
ERPCLAW_LIB = os.path.expanduser("~/.openclaw/erpclaw/lib")
if ERPCLAW_LIB not in sys.path:
    sys.path.insert(0, ERPCLAW_LIB)

from erpclaw_lib.db import setup_pragmas


def load_db_query():
    """Load propertyclaw db_query.py explicitly to avoid sys.path collisions."""
    db_query_path = os.path.join(MODULE_DIR, "db_query.py")
    spec = importlib.util.spec_from_file_location("db_query_propertyclaw", db_query_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────────────────

def init_all_tables(db_path: str):
    """Create foundation tables + propertyclaw domain tables."""
    # 1. Foundation
    spec = importlib.util.spec_from_file_location("init_schema", INIT_SCHEMA_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init_db(db_path)

    # 2. PropertyClaw tables (requires a company to exist for naming series)
    spec2 = importlib.util.spec_from_file_location("pc_init_db", PROPERTYCLAW_INIT_DB)
    mod2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(mod2)
    mod2.create_propertyclaw_tables(db_path)


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
        "company_id": None, "property_id": None, "unit_id": None,
        "lease_id": None, "customer_id": None, "supplier_id": None,
        "name": None, "property_type": None, "address_line1": None,
        "address_line2": None, "city": None, "state": None,
        "zip_code": None, "county": None, "year_built": None,
        "total_units": None, "owner_name": None, "owner_contact": None,
        "management_fee_pct": None, "property_status": None,
        "unit_status": None, "unit_number": None, "unit_type": None,
        "bedrooms": None, "bathrooms": None, "sq_ft": None,
        "area": None, "floor": None, "market_rent": None,
        "amenity_id": None, "amenity_name": None, "category": None,
        "description": None, "photo_id": None, "file_url": None,
        "photo_scope": None, "lease_status": None, "lease_type": None,
        "start_date": None, "end_date": None, "monthly_rent": None,
        "security_deposit_amount": None, "deposit_account_id": None,
        "move_in_date": None, "move_out_date": None,
        "charge_status": None, "charge_type": None, "charge_date": None,
        "rent_schedule_id": None, "scheduled_date": None,
        "fee_type": None, "flat_amount": None, "percentage_rate": None,
        "grace_days": None, "max_cap": None, "frequency": None,
        "as_of_date": None, "new_end_date": None, "new_start_date": None,
        "new_monthly_rent": None, "rent_increase_pct": None,
        "renewal_id": None, "application_status": None,
        "application_id": None, "applicant_name": None,
        "applicant_phone": None, "applicant_email": None,
        "monthly_income": None, "desired_move_in": None,
        "employer": None, "screening_id": None,
        "screening_request_id": None, "screening_type": None,
        "consent_obtained": None, "consent_date": None,
        "cra_name": None, "cra_phone": None, "cra_address": None,
        "denial_reason": None, "delivery_method": None,
        "document_id": None, "document_type": None, "expiry_date": None,
        "wo_status": None, "va_status": None, "work_order_id": None,
        "priority": None, "reported_date": None,
        "estimated_cost": None, "actual_cost": None,
        "purchase_invoice_id": None, "permission_to_enter": None,
        "assignment_id": None, "estimated_arrival": None,
        "actual_arrival": None, "item_type": None,
        "item_description": None, "quantity": None, "rate": None,
        "billable_to_tenant": None, "inspection_id": None,
        "inspection_type": None, "inspection_date": None,
        "inspector_name": None, "item": None, "condition": None,
        "overall_condition": None, "photo_url": None,
        "estimated_repair_cost": None,
        "account_id": None, "trust_account_id": None,
        "bank_name": None, "period_start": None, "period_end": None,
        "security_deposit_id": None, "amount": None,
        "deposit_date": None, "trust_account_id_for_deposit": None,
        "return_amount": None, "deduction_type": None,
        "deduction_description": None, "invoice_url": None,
        "receipt_url": None, "tax_year": None,
        "interest_rate": None, "notes": None,
        # -- Rent Payment --
        "method_type": None, "last_four": None, "external_token": None,
        "payment_method_id": None, "autopay_day": None,
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
    """Seed naming series for PropertyClaw entity types."""
    series = [
        ("propertyclaw_property", "PROP-", 0),
        ("propertyclaw_unit", "UNIT-", 0),
        ("propertyclaw_lease", "LEASE-", 0),
        ("propertyclaw_application", "APP-", 0),
        ("propertyclaw_work_order", "WO-", 0),
        ("propertyclaw_inspection", "INSP-", 0),
        ("propertyclaw_owner_statement", "OWN-", 0),
        ("sales_invoice", "SI-", 0),
        ("purchase_invoice", "PI-", 0),
    ]
    for entity_type, prefix, current in series:
        conn.execute(
            """INSERT OR IGNORE INTO naming_series
               (id, entity_type, prefix, current_value, company_id)
               VALUES (?, ?, ?, ?, ?)""",
            (_uuid(), entity_type, prefix, current, company_id)
        )
    conn.commit()


def seed_account(conn, company_id: str, name="Test Account",
                 root_type="asset", account_type=None,
                 account_number=None) -> str:
    aid = _uuid()
    direction = "debit_normal" if root_type in ("asset", "expense") else "credit_normal"
    conn.execute(
        """INSERT INTO account (id, name, account_number, root_type, account_type,
           balance_direction, company_id, depth)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
        (aid, name, account_number or f"ACC-{aid[:6]}", root_type,
         account_type, direction, company_id)
    )
    conn.commit()
    return aid


def seed_customer(conn, company_id: str, name="Test Customer") -> str:
    cid = _uuid()
    conn.execute(
        """INSERT INTO customer (id, name, company_id, customer_type, status, credit_limit)
           VALUES (?, ?, ?, 'company', 'active', '0')""",
        (cid, name, company_id)
    )
    conn.commit()
    return cid


def seed_supplier(conn, company_id: str, name="Test Supplier") -> str:
    sid = _uuid()
    conn.execute(
        """INSERT INTO supplier (id, name, company_id)
           VALUES (?, ?, ?)""",
        (sid, name, company_id)
    )
    conn.commit()
    return sid


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


def seed_trust_account_raw(conn, company_id: str, name="Trust Account") -> str:
    """Insert a trust-type account by bypassing CHECK constraint.
    The schema doesn't have 'trust' as a valid account_type, so we
    temporarily disable FK/CHECK and insert directly.
    """
    aid = _uuid()
    # We need to insert a bank-type account and then update it to 'trust'
    # via direct SQL ignoring the CHECK.  Alternatively, just use bank.
    # The propertyclaw setup_trust_account action checks account_type == 'trust'.
    # We'll insert directly into propertyclaw_trust_account to bypass.
    conn.execute(
        """INSERT INTO account (id, name, account_number, root_type, account_type,
           balance_direction, company_id, depth)
           VALUES (?, ?, ?, 'asset', 'bank', 'debit_normal', ?, 0)""",
        (aid, name, f"TRUST-{aid[:6]}", company_id)
    )
    conn.commit()
    return aid


def build_env(conn) -> dict:
    """Create a full PropertyClaw test environment."""
    cid = seed_company(conn)
    seed_naming_series(conn, cid)
    seed_fiscal_year(conn, cid)
    trust_acct = seed_account(conn, cid, "Trust Account", "asset", "bank", "1300")
    ar_acct = seed_account(conn, cid, "Accounts Receivable", "asset", "receivable", "1100")
    cust = seed_customer(conn, cid)
    supplier = seed_supplier(conn, cid)

    return {
        "company_id": cid,
        "trust_account": trust_acct,
        "ar_account": ar_acct,
        "customer": cust,
        "supplier": supplier,
    }
