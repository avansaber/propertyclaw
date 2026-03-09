"""PropertyClaw Commercial — NNN Leases domain module

Actions for triple-net lease management (2 tables, 10 actions).
Imported by db_query.py (unified router).
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit

    # Register naming prefixes
    ENTITY_PREFIXES.setdefault("commercial_nnn_lease", "CNNN-")
except ImportError:
    pass

SKILL = "propertyclaw-commercial"

VALID_ESCALATION_FREQ = ("annual", "biannual", "none")
VALID_LEASE_STATUSES = ("draft", "active", "expired", "terminated")
VALID_EXPENSE_TYPES = ("cam", "insurance", "tax", "utility")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute("SELECT id FROM company WHERE id = ?", (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _validate_lease(conn, lease_id):
    if not lease_id:
        err("--lease-id is required")
    row = conn.execute("SELECT * FROM commercial_nnn_lease WHERE id = ?", (lease_id,)).fetchone()
    if not row:
        err(f"NNN Lease {lease_id} not found")
    return row


# ---------------------------------------------------------------------------
# 1. add-nnn-lease
# ---------------------------------------------------------------------------
def add_nnn_lease(conn, args):
    _validate_company(conn, args.company_id)
    if not args.tenant_name:
        err("--tenant-name is required")
    if not args.property_name:
        err("--property-name is required")
    if not args.lease_start:
        err("--lease-start is required")
    if not args.lease_end:
        err("--lease-end is required")
    if not args.base_rent:
        err("--base-rent is required")

    esc_freq = getattr(args, "escalation_frequency", None) or "none"
    if esc_freq not in VALID_ESCALATION_FREQ:
        err(f"--escalation-frequency must be one of: {', '.join(VALID_ESCALATION_FREQ)}")

    base_rent = str(round_currency(to_decimal(args.base_rent)))
    cam_pct = str(round_currency(to_decimal(getattr(args, "cam_share_pct", None) or "0")))
    ins_pct = str(round_currency(to_decimal(getattr(args, "insurance_share_pct", None) or "0")))
    tax_pct = str(round_currency(to_decimal(getattr(args, "tax_share_pct", None) or "0")))
    esc_pct = str(round_currency(to_decimal(getattr(args, "escalation_pct", None) or "0")))
    sq_ft = getattr(args, "square_footage", None)

    lease_id = str(uuid.uuid4())
    conn.company_id = args.company_id
    lease_name = get_next_name(conn, "commercial_nnn_lease")

    conn.execute(
        """INSERT INTO commercial_nnn_lease
           (id, naming_series, tenant_name, property_name, suite_number,
            lease_start, lease_end, base_rent, cam_share_pct, insurance_share_pct,
            tax_share_pct, escalation_pct, escalation_frequency, square_footage,
            lease_status, company_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (lease_id, lease_name, args.tenant_name, args.property_name,
         getattr(args, "suite_number", None),
         args.lease_start, args.lease_end, base_rent, cam_pct, ins_pct,
         tax_pct, esc_pct, esc_freq, sq_ft,
         "draft", args.company_id))

    audit(conn, SKILL, "commercial-add-nnn-lease", "commercial_nnn_lease", lease_id,
          new_values={"tenant": args.tenant_name, "naming_series": lease_name})
    conn.commit()
    ok({"lease_id": lease_id, "naming_series": lease_name, "lease_status": "draft"})


# ---------------------------------------------------------------------------
# 2. update-nnn-lease
# ---------------------------------------------------------------------------
def update_nnn_lease(conn, args):
    _validate_lease(conn, args.lease_id)

    updates, params, changed = [], [], []

    if args.tenant_name is not None:
        updates.append("tenant_name = ?"); params.append(args.tenant_name); changed.append("tenant_name")
    if args.property_name is not None:
        updates.append("property_name = ?"); params.append(args.property_name); changed.append("property_name")
    suite = getattr(args, "suite_number", None)
    if suite is not None:
        updates.append("suite_number = ?"); params.append(suite); changed.append("suite_number")
    if args.lease_start is not None:
        updates.append("lease_start = ?"); params.append(args.lease_start); changed.append("lease_start")
    if args.lease_end is not None:
        updates.append("lease_end = ?"); params.append(args.lease_end); changed.append("lease_end")
    if args.base_rent is not None:
        updates.append("base_rent = ?")
        params.append(str(round_currency(to_decimal(args.base_rent))))
        changed.append("base_rent")
    cam_pct = getattr(args, "cam_share_pct", None)
    if cam_pct is not None:
        updates.append("cam_share_pct = ?")
        params.append(str(round_currency(to_decimal(cam_pct))))
        changed.append("cam_share_pct")
    ins_pct = getattr(args, "insurance_share_pct", None)
    if ins_pct is not None:
        updates.append("insurance_share_pct = ?")
        params.append(str(round_currency(to_decimal(ins_pct))))
        changed.append("insurance_share_pct")
    tax_pct = getattr(args, "tax_share_pct", None)
    if tax_pct is not None:
        updates.append("tax_share_pct = ?")
        params.append(str(round_currency(to_decimal(tax_pct))))
        changed.append("tax_share_pct")
    esc_pct = getattr(args, "escalation_pct", None)
    if esc_pct is not None:
        updates.append("escalation_pct = ?")
        params.append(str(round_currency(to_decimal(esc_pct))))
        changed.append("escalation_pct")
    esc_freq = getattr(args, "escalation_frequency", None)
    if esc_freq is not None:
        if esc_freq not in VALID_ESCALATION_FREQ:
            err(f"--escalation-frequency must be one of: {', '.join(VALID_ESCALATION_FREQ)}")
        updates.append("escalation_frequency = ?"); params.append(esc_freq); changed.append("escalation_frequency")
    sq_ft = getattr(args, "square_footage", None)
    if sq_ft is not None:
        updates.append("square_footage = ?"); params.append(sq_ft); changed.append("square_footage")
    lease_status = getattr(args, "lease_status", None)
    if lease_status is not None:
        if lease_status not in VALID_LEASE_STATUSES:
            err(f"--lease-status must be one of: {', '.join(VALID_LEASE_STATUSES)}")
        updates.append("lease_status = ?"); params.append(lease_status); changed.append("lease_status")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(args.lease_id)
    conn.execute(f"UPDATE commercial_nnn_lease SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"lease_id": args.lease_id, "updated_fields": changed})


# ---------------------------------------------------------------------------
# 3. get-nnn-lease
# ---------------------------------------------------------------------------
def get_nnn_lease(conn, args):
    row = _validate_lease(conn, args.lease_id)
    data = row_to_dict(row)

    # Include passthroughs
    passthroughs = conn.execute(
        "SELECT * FROM commercial_expense_passthrough WHERE lease_id = ? ORDER BY expense_period DESC",
        (args.lease_id,)).fetchall()
    data["passthroughs"] = [row_to_dict(p) for p in passthroughs]

    ok(data)


# ---------------------------------------------------------------------------
# 4. list-nnn-leases
# ---------------------------------------------------------------------------
def list_nnn_leases(conn, args):
    if not args.company_id:
        err("--company-id is required")

    params = [args.company_id]
    where = ["company_id = ?"]

    lease_status = getattr(args, "lease_status", None)
    if lease_status:
        where.append("lease_status = ?"); params.append(lease_status)

    wc = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM commercial_nnn_lease WHERE {wc}", params).fetchone()[0]

    limit = int(args.limit); offset = int(args.offset)
    rows = conn.execute(
        f"""SELECT * FROM commercial_nnn_lease
            WHERE {wc} ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall()

    ok({"leases": [row_to_dict(r) for r in rows], "total_count": total,
        "limit": limit, "offset": offset, "has_more": offset + limit < total})


# ---------------------------------------------------------------------------
# 5. add-expense-passthrough
# ---------------------------------------------------------------------------
def add_expense_passthrough(conn, args):
    lease = _validate_lease(conn, args.lease_id)
    expense_type = getattr(args, "expense_type", None)
    if not expense_type:
        err("--expense-type is required")
    if expense_type not in VALID_EXPENSE_TYPES:
        err(f"--expense-type must be one of: {', '.join(VALID_EXPENSE_TYPES)}")
    expense_period = getattr(args, "expense_period", None)
    if not expense_period:
        err("--expense-period is required")

    actual_amount = str(round_currency(to_decimal(getattr(args, "actual_amount", None) or "0")))
    estimated_amount = str(round_currency(to_decimal(getattr(args, "estimated_amount", None) or "0")))

    # Calculate tenant share based on the lease's share percentage for this type
    pct_map = {"cam": "cam_share_pct", "insurance": "insurance_share_pct",
               "tax": "tax_share_pct", "utility": "cam_share_pct"}
    share_pct = to_decimal(lease[pct_map[expense_type]])
    actual_dec = to_decimal(actual_amount)
    tenant_share = str(round_currency(actual_dec * share_pct / Decimal("100")))

    pt_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO commercial_expense_passthrough
           (id, lease_id, expense_type, expense_period, actual_amount,
            tenant_share, estimated_amount, reconciled, company_id)
           VALUES (?,?,?,?,?,?,?,0,?)""",
        (pt_id, args.lease_id, expense_type, expense_period,
         actual_amount, tenant_share, estimated_amount, lease["company_id"]))

    conn.commit()
    ok({"passthrough_id": pt_id, "expense_type": expense_type,
        "actual_amount": actual_amount, "tenant_share": tenant_share})


# ---------------------------------------------------------------------------
# 6. list-expense-passthroughs
# ---------------------------------------------------------------------------
def list_expense_passthroughs(conn, args):
    _validate_lease(conn, args.lease_id)

    params = [args.lease_id]
    where = ["lease_id = ?"]
    expense_type = getattr(args, "expense_type", None)
    if expense_type:
        where.append("expense_type = ?"); params.append(expense_type)

    wc = " AND ".join(where)
    rows = conn.execute(
        f"SELECT * FROM commercial_expense_passthrough WHERE {wc} ORDER BY expense_period DESC",
        params).fetchall()

    ok({"passthroughs": [row_to_dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# 7. calculate-monthly-charges
# ---------------------------------------------------------------------------
def calculate_monthly_charges(conn, args):
    lease = _validate_lease(conn, args.lease_id)

    base_rent = to_decimal(lease["base_rent"])
    cam_pct = to_decimal(lease["cam_share_pct"])
    ins_pct = to_decimal(lease["insurance_share_pct"])
    tax_pct = to_decimal(lease["tax_share_pct"])

    # Fetch latest passthroughs by type to get estimated monthly
    charges = {"base_rent": str(round_currency(base_rent))}
    total = base_rent

    for etype, pct in [("cam", cam_pct), ("insurance", ins_pct), ("tax", tax_pct)]:
        latest = conn.execute(
            """SELECT estimated_amount FROM commercial_expense_passthrough
               WHERE lease_id = ? AND expense_type = ?
               ORDER BY expense_period DESC LIMIT 1""",
            (args.lease_id, etype)).fetchone()
        if latest:
            est = to_decimal(latest["estimated_amount"])
            share = round_currency(est * pct / Decimal("100"))
        else:
            share = Decimal("0")
        charges[f"{etype}_share"] = str(share)
        total += share

    charges["total_monthly"] = str(round_currency(total))
    ok(charges)


# ---------------------------------------------------------------------------
# 8. generate-nnn-invoice (descriptive, does not create actual invoice)
# ---------------------------------------------------------------------------
def generate_nnn_invoice(conn, args):
    lease = _validate_lease(conn, args.lease_id)
    invoice_period = getattr(args, "invoice_period", None)
    if not invoice_period:
        err("--invoice-period is required")

    base_rent = to_decimal(lease["base_rent"])
    cam_pct = to_decimal(lease["cam_share_pct"])
    ins_pct = to_decimal(lease["insurance_share_pct"])
    tax_pct = to_decimal(lease["tax_share_pct"])

    line_items = [{"description": "Base Rent", "amount": str(round_currency(base_rent))}]
    total = base_rent

    for etype, pct, label in [("cam", cam_pct, "CAM Share"),
                                ("insurance", ins_pct, "Insurance Share"),
                                ("tax", tax_pct, "Tax Share")]:
        pt = conn.execute(
            """SELECT actual_amount FROM commercial_expense_passthrough
               WHERE lease_id = ? AND expense_type = ? AND expense_period = ?
               ORDER BY created_at DESC LIMIT 1""",
            (args.lease_id, etype, invoice_period)).fetchone()
        if pt:
            actual = to_decimal(pt["actual_amount"])
            share = round_currency(actual * pct / Decimal("100"))
        else:
            share = Decimal("0")
        line_items.append({"description": label, "amount": str(share)})
        total += share

    ok({
        "lease_id": args.lease_id,
        "tenant_name": lease["tenant_name"],
        "invoice_period": invoice_period,
        "line_items": line_items,
        "total_amount": str(round_currency(total)),
    })


# ---------------------------------------------------------------------------
# 9. nnn-lease-summary
# ---------------------------------------------------------------------------
def nnn_lease_summary(conn, args):
    if not args.company_id:
        err("--company-id is required")

    total_leases = conn.execute(
        "SELECT COUNT(*) FROM commercial_nnn_lease WHERE company_id = ?",
        (args.company_id,)).fetchone()[0]
    active = conn.execute(
        "SELECT COUNT(*) FROM commercial_nnn_lease WHERE company_id = ? AND lease_status = 'active'",
        (args.company_id,)).fetchone()[0]
    draft = conn.execute(
        "SELECT COUNT(*) FROM commercial_nnn_lease WHERE company_id = ? AND lease_status = 'draft'",
        (args.company_id,)).fetchone()[0]
    expired = conn.execute(
        "SELECT COUNT(*) FROM commercial_nnn_lease WHERE company_id = ? AND lease_status = 'expired'",
        (args.company_id,)).fetchone()[0]

    # Total base rent (active leases)
    rent_row = conn.execute(
        """SELECT COALESCE(SUM(CAST(base_rent AS REAL)), 0) as total_rent
           FROM commercial_nnn_lease
           WHERE company_id = ? AND lease_status = 'active'""",
        (args.company_id,)).fetchone()
    total_base_rent = str(round_currency(to_decimal(str(rent_row["total_rent"]))))

    ok({
        "total_leases": total_leases,
        "active": active,
        "draft": draft,
        "expired": expired,
        "total_active_base_rent": total_base_rent,
    })


# ---------------------------------------------------------------------------
# 10. lease-expiry-schedule
# ---------------------------------------------------------------------------
def lease_expiry_schedule(conn, args):
    if not args.company_id:
        err("--company-id is required")

    rows = conn.execute(
        """SELECT id, naming_series, tenant_name, property_name, suite_number,
                  lease_start, lease_end, base_rent, lease_status
           FROM commercial_nnn_lease
           WHERE company_id = ? AND lease_status IN ('active', 'draft')
           ORDER BY lease_end ASC""",
        (args.company_id,)).fetchall()

    ok({"leases": [row_to_dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "commercial-add-nnn-lease": add_nnn_lease,
    "commercial-update-nnn-lease": update_nnn_lease,
    "commercial-get-nnn-lease": get_nnn_lease,
    "commercial-list-nnn-leases": list_nnn_leases,
    "commercial-add-expense-passthrough": add_expense_passthrough,
    "commercial-list-expense-passthroughs": list_expense_passthroughs,
    "commercial-calculate-monthly-charges": calculate_monthly_charges,
    "commercial-generate-nnn-invoice": generate_nnn_invoice,
    "commercial-nnn-lease-summary": nnn_lease_summary,
    "commercial-lease-expiry-schedule": lease_expiry_schedule,
}
