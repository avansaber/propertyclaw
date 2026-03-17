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

    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row
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
    t_co = Table("company")
    q_co = Q.from_(t_co).select(t_co.id).where(t_co.id == P())
    if not conn.execute(q_co.get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _validate_lease(conn, lease_id):
    if not lease_id:
        err("--lease-id is required")
    t = Table("commercial_nnn_lease")
    q = Q.from_(t).select(t.star).where(t.id == P())
    row = conn.execute(q.get_sql(), (lease_id,)).fetchone()
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

    sql, _ = insert_row("commercial_nnn_lease", {
        "id": P(), "naming_series": P(), "tenant_name": P(), "property_name": P(),
        "suite_number": P(), "lease_start": P(), "lease_end": P(), "base_rent": P(),
        "cam_share_pct": P(), "insurance_share_pct": P(), "tax_share_pct": P(),
        "escalation_pct": P(), "escalation_frequency": P(), "square_footage": P(),
        "lease_status": P(), "company_id": P(),
    })
    conn.execute(sql, (lease_id, lease_name, args.tenant_name, args.property_name,
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

    updates.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
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
    t_pt = Table("commercial_expense_passthrough")
    q_pt = (Q.from_(t_pt).select(t_pt.star)
            .where(t_pt.lease_id == P())
            .orderby(t_pt.expense_period, order=Order.desc))
    passthroughs = conn.execute(q_pt.get_sql(), (args.lease_id,)).fetchall()
    data["passthroughs"] = [row_to_dict(p) for p in passthroughs]

    ok(data)


# ---------------------------------------------------------------------------
# 4. list-nnn-leases
# ---------------------------------------------------------------------------
def list_nnn_leases(conn, args):
    if not args.company_id:
        err("--company-id is required")

    t = Table("commercial_nnn_lease")
    q_count = Q.from_(t).select(fn.Count("*")).where(t.company_id == P())
    q_rows = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [args.company_id]

    lease_status = getattr(args, "lease_status", None)
    if lease_status:
        q_count = q_count.where(t.lease_status == P())
        q_rows = q_rows.where(t.lease_status == P())
        params.append(lease_status)

    total = conn.execute(q_count.get_sql(), params).fetchone()[0]

    limit = int(args.limit); offset = int(args.offset)
    page_params = list(params) + [limit, offset]
    q_rows = q_rows.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    rows = conn.execute(q_rows.get_sql(), page_params).fetchall()

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
    sql, _ = insert_row("commercial_expense_passthrough", {
        "id": P(), "lease_id": P(), "expense_type": P(), "expense_period": P(),
        "actual_amount": P(), "tenant_share": P(), "estimated_amount": P(),
        "reconciled": P(), "company_id": P(),
    })
    conn.execute(sql, (pt_id, args.lease_id, expense_type, expense_period,
                       actual_amount, tenant_share, estimated_amount, 0, lease["company_id"]))

    conn.commit()
    ok({"passthrough_id": pt_id, "expense_type": expense_type,
        "actual_amount": actual_amount, "tenant_share": tenant_share})


# ---------------------------------------------------------------------------
# 6. list-expense-passthroughs
# ---------------------------------------------------------------------------
def list_expense_passthroughs(conn, args):
    _validate_lease(conn, args.lease_id)

    t = Table("commercial_expense_passthrough")
    q = Q.from_(t).select(t.star).where(t.lease_id == P())
    params = [args.lease_id]
    expense_type = getattr(args, "expense_type", None)
    if expense_type:
        q = q.where(t.expense_type == P())
        params.append(expense_type)

    q = q.orderby(t.expense_period, order=Order.desc)
    rows = conn.execute(q.get_sql(), params).fetchall()

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

    t_pt = Table("commercial_expense_passthrough")
    for etype, pct in [("cam", cam_pct), ("insurance", ins_pct), ("tax", tax_pct)]:
        q_latest = (Q.from_(t_pt).select(t_pt.estimated_amount)
                    .where(t_pt.lease_id == P()).where(t_pt.expense_type == P())
                    .orderby(t_pt.expense_period, order=Order.desc).limit(1))
        latest = conn.execute(q_latest.get_sql(), (args.lease_id, etype)).fetchone()
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

    t_pt = Table("commercial_expense_passthrough")
    for etype, pct, label in [("cam", cam_pct, "CAM Share"),
                                ("insurance", ins_pct, "Insurance Share"),
                                ("tax", tax_pct, "Tax Share")]:
        q_pt = (Q.from_(t_pt).select(t_pt.actual_amount)
                .where(t_pt.lease_id == P()).where(t_pt.expense_type == P())
                .where(t_pt.expense_period == P())
                .orderby(t_pt.created_at, order=Order.desc).limit(1))
        pt = conn.execute(q_pt.get_sql(), (args.lease_id, etype, invoice_period)).fetchone()
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

    from erpclaw_lib.vendor.pypika.terms import LiteralValue

    t = Table("commercial_nnn_lease")
    q_total = Q.from_(t).select(fn.Count("*")).where(t.company_id == P())
    total_leases = conn.execute(q_total.get_sql(), (args.company_id,)).fetchone()[0]

    q_active = Q.from_(t).select(fn.Count("*")).where(t.company_id == P()).where(t.lease_status == "active")
    active = conn.execute(q_active.get_sql(), (args.company_id,)).fetchone()[0]

    q_draft = Q.from_(t).select(fn.Count("*")).where(t.company_id == P()).where(t.lease_status == "draft")
    draft = conn.execute(q_draft.get_sql(), (args.company_id,)).fetchone()[0]

    q_expired = Q.from_(t).select(fn.Count("*")).where(t.company_id == P()).where(t.lease_status == "expired")
    expired = conn.execute(q_expired.get_sql(), (args.company_id,)).fetchone()[0]

    # Total base rent (active leases)
    q_rent = (Q.from_(t)
              .select(LiteralValue('COALESCE(SUM(CAST("base_rent" AS NUMERIC)), 0)').as_("total_rent"))
              .where(t.company_id == P()).where(t.lease_status == "active"))
    rent_row = conn.execute(q_rent.get_sql(), (args.company_id,)).fetchone()
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

    from erpclaw_lib.vendor.pypika.terms import LiteralValue
    t = Table("commercial_nnn_lease")
    q = (Q.from_(t)
         .select(t.id, t.naming_series, t.tenant_name, t.property_name, t.suite_number,
                 t.lease_start, t.lease_end, t.base_rent, t.lease_status)
         .where(t.company_id == P())
         .where(t.lease_status.isin(["active", "draft"]))
         .orderby(t.lease_end))
    rows = conn.execute(q.get_sql(), (args.company_id,)).fetchall()

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
