#!/usr/bin/env python3
"""propertyclaw rent payment domain module.

Online rent payment methods, autopay, and payment processing.
Imported by the unified propertyclaw db_query.py router.
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection, ensure_db_exists, DEFAULT_DB_PATH
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.naming import get_next_name
    from erpclaw_lib.validation import check_input_lengths
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.dependencies import check_required_tables
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row, dynamic_update, now
except ImportError:
    import json as _json
    print(_json.dumps({
        "status": "error",
        "error": "ERPClaw foundation not installed. Install erpclaw first: clawhub install erpclaw",
        "suggestion": "clawhub install erpclaw"
    }))
    sys.exit(1)

REQUIRED_TABLES = ["company", "customer", "propertyclaw_lease",
                   "propertyclaw_lease_charge", "propertyclaw_payment_method"]
SKILL = "prop-propertyclaw-rent-payment"

VALID_METHOD_TYPES = ("ach", "credit_card", "debit_card")
VALID_PM_STATUSES = ("active", "inactive", "expired")


# ---------------------------------------------------------------------------
# prop-add-payment-method
# ---------------------------------------------------------------------------
def add_payment_method(conn, args):
    if not args.customer_id:
        err("--customer-id is required")
    if not args.company_id:
        err("--company-id is required")

    method_type = getattr(args, "method_type", None)
    if not method_type:
        err("--method-type is required")
    if method_type not in VALID_METHOD_TYPES:
        err(f"--method-type must be one of: {', '.join(VALID_METHOD_TYPES)}")

    if not conn.execute(Q.from_(Table("customer")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.customer_id,)).fetchone():
        err(f"Customer {args.customer_id} not found")
    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.company_id,)).fetchone():
        err(f"Company {args.company_id} not found")

    pm_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO propertyclaw_payment_method
           (id, tenant_id, method_type, last_four, bank_name, is_default,
            autopay_enabled, autopay_day, external_token, status, company_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (pm_id, args.customer_id, method_type,
         getattr(args, "last_four", None),
         getattr(args, "bank_name", None),
         0, 0, None,
         getattr(args, "external_token", None),
         "active", args.company_id))

    audit(conn, SKILL, "prop-add-payment-method", "propertyclaw_payment_method", pm_id,
          new_values={"tenant_id": args.customer_id, "method_type": method_type})
    conn.commit()
    ok({"payment_method_id": pm_id, "method_type": method_type, "pm_status": "active"})


# ---------------------------------------------------------------------------
# prop-list-payment-methods
# ---------------------------------------------------------------------------
def list_payment_methods(conn, args):
    params = []
    where = ["1=1"]
    if args.customer_id:
        where.append("pm.tenant_id = ?"); params.append(args.customer_id)
    if args.company_id:
        where.append("pm.company_id = ?"); params.append(args.company_id)

    wc = " AND ".join(where)
    rows = conn.execute(
        f"""SELECT pm.*, c.name as tenant_name
            FROM propertyclaw_payment_method pm
            JOIN customer c ON pm.tenant_id = c.id
            WHERE {wc} ORDER BY pm.is_default DESC, pm.created_at DESC""",
        params).fetchall()

    ok({"payment_methods": [row_to_dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# prop-enable-autopay
# ---------------------------------------------------------------------------
def enable_autopay(conn, args):
    pm_id = getattr(args, "payment_method_id", None)
    if not pm_id:
        err("--payment-method-id is required")

    autopay_day = getattr(args, "autopay_day", None)
    if not autopay_day:
        err("--autopay-day is required (1-28)")
    try:
        day = int(autopay_day)
    except (ValueError, TypeError):
        err("--autopay-day must be an integer (1-28)")
        return  # unreachable but satisfies linter
    if day < 1 or day > 28:
        err("--autopay-day must be between 1 and 28")

    row = conn.execute(
        Q.from_(Table("propertyclaw_payment_method")).select(
            Table("propertyclaw_payment_method").star
        ).where(Field("id") == P()).get_sql(),
        (pm_id,)).fetchone()
    if not row:
        err(f"Payment method {pm_id} not found")
    if row["status"] != "active":
        err(f"Payment method must be active (current: {row['status']})")

    conn.execute(
        """UPDATE propertyclaw_payment_method
           SET autopay_enabled = 1, autopay_day = ?, is_default = 1,
               updated_at = datetime('now')
           WHERE id = ?""",
        (day, pm_id))

    audit(conn, SKILL, "prop-enable-autopay", "propertyclaw_payment_method", pm_id,
          new_values={"autopay_enabled": 1, "autopay_day": day})
    conn.commit()
    ok({"payment_method_id": pm_id, "autopay_enabled": True, "autopay_day": day})


# ---------------------------------------------------------------------------
# prop-disable-autopay
# ---------------------------------------------------------------------------
def disable_autopay(conn, args):
    pm_id = getattr(args, "payment_method_id", None)
    if not pm_id:
        err("--payment-method-id is required")

    row = conn.execute(
        Q.from_(Table("propertyclaw_payment_method")).select(Field("id"), Field("autopay_enabled"))
        .where(Field("id") == P()).get_sql(),
        (pm_id,)).fetchone()
    if not row:
        err(f"Payment method {pm_id} not found")

    conn.execute(
        """UPDATE propertyclaw_payment_method
           SET autopay_enabled = 0, autopay_day = NULL,
               updated_at = datetime('now')
           WHERE id = ?""",
        (pm_id,))

    audit(conn, SKILL, "prop-disable-autopay", "propertyclaw_payment_method", pm_id,
          new_values={"autopay_enabled": 0})
    conn.commit()
    ok({"payment_method_id": pm_id, "autopay_enabled": False})


# ---------------------------------------------------------------------------
# prop-process-rent-payment
# ---------------------------------------------------------------------------
def process_rent_payment(conn, args):
    """Process a rent payment: creates a charge (if needed) and records payment."""
    if not args.lease_id:
        err("--lease-id is required")
    if not args.amount:
        err("--amount is required")

    pm_id = getattr(args, "payment_method_id", None)

    lease = conn.execute(
        Q.from_(Table("propertyclaw_lease")).select(
            Table("propertyclaw_lease").star
        ).where(Field("id") == P()).get_sql(),
        (args.lease_id,)).fetchone()
    if not lease:
        err(f"Lease {args.lease_id} not found")
    if lease["status"] != "active":
        err(f"Lease must be active to process payment (current: {lease['status']})")

    # Validate payment method if provided
    if pm_id:
        pm = conn.execute(
            Q.from_(Table("propertyclaw_payment_method")).select(
                Table("propertyclaw_payment_method").star
            ).where(Field("id") == P()).get_sql(),
            (pm_id,)).fetchone()
        if not pm:
            err(f"Payment method {pm_id} not found")
        if pm["status"] != "active":
            err(f"Payment method must be active (current: {pm['status']})")
        if pm["tenant_id"] != lease["customer_id"]:
            err("Payment method does not belong to the tenant on this lease")

    amount = round_currency(to_decimal(args.amount))
    if amount <= 0:
        err("Amount must be greater than 0")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    charge_date = args.charge_date or today

    # Find pending charges for this lease, pay them off
    pending = conn.execute(
        """SELECT id, amount, status FROM propertyclaw_lease_charge
           WHERE lease_id = ? AND status = 'pending'
           ORDER BY charge_date ASC""",
        (args.lease_id,)).fetchall()

    charges_paid = []
    remaining = amount
    for charge in pending:
        if remaining <= 0:
            break
        charge_amt = to_decimal(charge["amount"])
        if remaining >= charge_amt:
            conn.execute(
                "UPDATE propertyclaw_lease_charge SET status = 'paid' WHERE id = ?",
                (charge["id"],))
            charges_paid.append({"charge_id": charge["id"], "amount": str(charge_amt)})
            remaining -= charge_amt
        # Partial payments: mark as paid if this covers it
        # (simple model: full charge payment only)

    payment_id = str(uuid.uuid4())

    audit(conn, SKILL, "prop-process-rent-payment", "propertyclaw_lease", args.lease_id,
          new_values={"payment_amount": str(amount), "charges_paid": len(charges_paid),
                      "payment_method_id": pm_id})
    conn.commit()
    ok({
        "payment_id": payment_id,
        "lease_id": args.lease_id,
        "amount": str(amount),
        "payment_date": today,
        "payment_method_id": pm_id,
        "charges_paid": charges_paid,
        "charges_paid_count": len(charges_paid),
    })


# ---------------------------------------------------------------------------
# prop-generate-payment-receipt
# ---------------------------------------------------------------------------
def generate_payment_receipt(conn, args):
    """Generate a receipt for a rent payment."""
    if not args.lease_id:
        err("--lease-id is required")
    if not args.amount:
        err("--amount is required")

    lease = conn.execute(
        """SELECT l.*, p.name as property_name, u.unit_number, c.name as tenant_name
           FROM propertyclaw_lease l
           JOIN propertyclaw_property p ON l.property_id = p.id
           JOIN propertyclaw_unit u ON l.unit_id = u.id
           JOIN customer c ON l.customer_id = c.id
           WHERE l.id = ?""",
        (args.lease_id,)).fetchone()
    if not lease:
        err(f"Lease {args.lease_id} not found")

    amount = round_currency(to_decimal(args.amount))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    receipt_number = f"RCPT-{str(uuid.uuid4())[:8].upper()}"

    ok({
        "receipt_number": receipt_number,
        "receipt_date": today,
        "tenant_name": lease["tenant_name"],
        "property_name": lease["property_name"],
        "unit_number": lease["unit_number"],
        "lease_id": args.lease_id,
        "amount": str(amount),
        "payment_method": getattr(args, "payment_method_id", None),
    })


# ---------------------------------------------------------------------------
# Action Router
# ---------------------------------------------------------------------------
ACTIONS = {
    "prop-add-payment-method": add_payment_method,
    "prop-list-payment-methods": list_payment_methods,
    "prop-enable-autopay": enable_autopay,
    "prop-disable-autopay": disable_autopay,
    "prop-process-rent-payment": process_rent_payment,
    "prop-generate-payment-receipt": generate_payment_receipt,
}
