"""PropertyClaw Commercial — TI (Tenant Improvement) domain module

Actions for tenant improvement allowance tracking and draws (2 tables, 6 actions).
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
    ENTITY_PREFIXES.setdefault("commercial_ti_allowance", "CTI-")
except ImportError:
    pass

SKILL = "propertyclaw-commercial"

VALID_TI_STATUSES = ("approved", "in_progress", "completed", "cancelled")
VALID_DRAW_STATUSES = ("pending", "approved", "paid")


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


def _validate_allowance(conn, allowance_id):
    if not allowance_id:
        err("--allowance-id is required")
    t = Table("commercial_ti_allowance")
    q = Q.from_(t).select(t.star).where(t.id == P())
    row = conn.execute(q.get_sql(), (allowance_id,)).fetchone()
    if not row:
        err(f"TI Allowance {allowance_id} not found")
    return row


def _recalc_allowance(conn, allowance_id):
    """Recalculate disbursed and remaining amounts for a TI allowance."""
    from erpclaw_lib.vendor.pypika.terms import LiteralValue

    t_allow = Table("commercial_ti_allowance")
    q_allow = Q.from_(t_allow).select(t_allow.total_allowance).where(t_allow.id == P())
    allowance = conn.execute(q_allow.get_sql(), (allowance_id,)).fetchone()
    total = to_decimal(allowance["total_allowance"])

    # Sum approved or paid draws only
    t_draw = Table("commercial_ti_draw")
    q_drawn = (Q.from_(t_draw)
               .select(LiteralValue('COALESCE(SUM(CAST("amount" AS REAL)), 0)').as_("total_drawn"))
               .where(t_draw.allowance_id == P())
               .where(t_draw.draw_status.isin(["approved", "paid"])))
    row = conn.execute(q_drawn.get_sql(), (allowance_id,)).fetchone()
    disbursed = round_currency(to_decimal(str(row["total_drawn"])))
    remaining = round_currency(total - disbursed)

    sql = update_row("commercial_ti_allowance",
                     data={"disbursed_amount": P(), "remaining_amount": P(),
                           "updated_at": LiteralValue("datetime('now')")},
                     where={"id": P()})
    conn.execute(sql, (str(disbursed), str(remaining), allowance_id))

    return disbursed, remaining


# ---------------------------------------------------------------------------
# 1. add-ti-allowance
# ---------------------------------------------------------------------------
def add_ti_allowance(conn, args):
    lease = _validate_lease(conn, args.lease_id)

    total_allowance = getattr(args, "total_allowance", None)
    if not total_allowance:
        err("--total-allowance is required")

    total_dec = round_currency(to_decimal(total_allowance))
    if total_dec <= Decimal("0"):
        err("--total-allowance must be greater than zero")

    allowance_id = str(uuid.uuid4())
    conn.company_id = lease["company_id"]
    ti_name = get_next_name(conn, "commercial_ti_allowance")

    sql, _ = insert_row("commercial_ti_allowance", {
        "id": P(), "naming_series": P(), "lease_id": P(), "total_allowance": P(),
        "disbursed_amount": P(), "remaining_amount": P(), "contractor": P(),
        "scope_of_work": P(), "ti_status": P(), "company_id": P(),
    })
    conn.execute(sql, (allowance_id, ti_name, args.lease_id, str(total_dec), "0",
                       str(total_dec), getattr(args, "contractor", None),
                       getattr(args, "scope_of_work", None), "approved", lease["company_id"]))

    audit(conn, SKILL, "commercial-add-ti-allowance", "commercial_ti_allowance", allowance_id,
          new_values={"naming_series": ti_name, "total_allowance": str(total_dec)})
    conn.commit()
    ok({"allowance_id": allowance_id, "naming_series": ti_name,
        "total_allowance": str(total_dec), "ti_status": "approved"})


# ---------------------------------------------------------------------------
# 2. get-ti-allowance
# ---------------------------------------------------------------------------
def get_ti_allowance(conn, args):
    allowance_id = getattr(args, "allowance_id", None)
    allowance = _validate_allowance(conn, allowance_id)
    data = row_to_dict(allowance)

    # Include lease info
    t_l = Table("commercial_nnn_lease")
    q_lease = (Q.from_(t_l)
               .select(t_l.tenant_name, t_l.property_name, t_l.suite_number)
               .where(t_l.id == P()))
    lease = conn.execute(q_lease.get_sql(), (allowance["lease_id"],)).fetchone()
    if lease:
        data["tenant_name"] = lease["tenant_name"]
        data["property_name"] = lease["property_name"]
        data["suite_number"] = lease["suite_number"]

    # Include draws
    t_d = Table("commercial_ti_draw")
    q_draws = (Q.from_(t_d).select(t_d.star)
               .where(t_d.allowance_id == P())
               .orderby(t_d.draw_date, order=Order.desc))
    draws = conn.execute(q_draws.get_sql(), (allowance_id,)).fetchall()
    data["draws"] = [row_to_dict(d) for d in draws]
    data["draw_count"] = len(draws)

    ok(data)


# ---------------------------------------------------------------------------
# 3. update-ti-allowance
# ---------------------------------------------------------------------------
def update_ti_allowance(conn, args):
    allowance_id = getattr(args, "allowance_id", None)
    allowance = _validate_allowance(conn, allowance_id)

    updates, params, changed = [], [], []

    ta = getattr(args, "total_allowance", None)
    if ta is not None:
        new_total = round_currency(to_decimal(ta))
        updates.append("total_allowance = ?"); params.append(str(new_total)); changed.append("total_allowance")
        # Recalc remaining
        disbursed = to_decimal(allowance["disbursed_amount"])
        updates.append("remaining_amount = ?"); params.append(str(round_currency(new_total - disbursed)))
    contractor = getattr(args, "contractor", None)
    if contractor is not None:
        updates.append("contractor = ?"); params.append(contractor); changed.append("contractor")
    scope = getattr(args, "scope_of_work", None)
    if scope is not None:
        updates.append("scope_of_work = ?"); params.append(scope); changed.append("scope_of_work")
    ti_status = getattr(args, "ti_status", None)
    if ti_status is not None:
        if ti_status not in VALID_TI_STATUSES:
            err(f"--ti-status must be one of: {', '.join(VALID_TI_STATUSES)}")
        updates.append("ti_status = ?"); params.append(ti_status); changed.append("ti_status")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(allowance_id)
    conn.execute(f"UPDATE commercial_ti_allowance SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"allowance_id": allowance_id, "updated_fields": changed})


# ---------------------------------------------------------------------------
# 4. list-ti-allowances
# ---------------------------------------------------------------------------
def list_ti_allowances(conn, args):
    if not args.company_id:
        err("--company-id is required")

    t_a = Table("commercial_ti_allowance")
    t_l = Table("commercial_nnn_lease")

    q_count = Q.from_(t_a).select(fn.Count("*")).where(t_a.company_id == P())
    q_rows = (Q.from_(t_a)
              .join(t_l).on(t_a.lease_id == t_l.id)
              .select(t_a.star, t_l.tenant_name, t_l.property_name)
              .where(t_a.company_id == P()))
    params = [args.company_id]

    if args.lease_id:
        q_count = q_count.where(t_a.lease_id == P())
        q_rows = q_rows.where(t_a.lease_id == P())
        params.append(args.lease_id)
    ti_status = getattr(args, "ti_status", None)
    if ti_status:
        q_count = q_count.where(t_a.ti_status == P())
        q_rows = q_rows.where(t_a.ti_status == P())
        params.append(ti_status)

    total = conn.execute(q_count.get_sql(), params).fetchone()[0]

    limit = int(args.limit); offset = int(args.offset)
    page_params = list(params) + [limit, offset]
    q_rows = q_rows.orderby(t_a.created_at, order=Order.desc).limit(P()).offset(P())
    rows = conn.execute(q_rows.get_sql(), page_params).fetchall()

    ok({"allowances": [row_to_dict(r) for r in rows], "total_count": total,
        "limit": limit, "offset": offset, "has_more": offset + limit < total})


# ---------------------------------------------------------------------------
# 5. add-ti-draw
# ---------------------------------------------------------------------------
def add_ti_draw(conn, args):
    allowance_id = getattr(args, "allowance_id", None)
    allowance = _validate_allowance(conn, allowance_id)

    if allowance["ti_status"] in ("completed", "cancelled"):
        err(f"Cannot add draws to a TI allowance with status '{allowance['ti_status']}'")

    draw_date = getattr(args, "draw_date", None)
    if not draw_date:
        err("--draw-date is required")
    amount = getattr(args, "amount", None)
    if not amount:
        err("--amount is required")

    amount_dec = round_currency(to_decimal(amount))
    if amount_dec <= Decimal("0"):
        err("--amount must be greater than zero")

    remaining = to_decimal(allowance["remaining_amount"])
    if amount_dec > remaining:
        err(f"Draw amount ({amount_dec}) exceeds remaining allowance ({remaining})")

    draw_id = str(uuid.uuid4())
    sql, _ = insert_row("commercial_ti_draw", {
        "id": P(), "allowance_id": P(), "draw_date": P(), "amount": P(),
        "description": P(), "invoice_reference": P(), "draw_status": P(),
        "company_id": P(),
    })
    conn.execute(sql, (draw_id, allowance_id, draw_date, str(amount_dec),
                       getattr(args, "description", None),
                       getattr(args, "invoice_reference", None),
                       "pending", allowance["company_id"]))

    conn.commit()
    ok({"draw_id": draw_id, "amount": str(amount_dec), "draw_status": "pending"})


# ---------------------------------------------------------------------------
# 6. list-ti-draws
# ---------------------------------------------------------------------------
def list_ti_draws(conn, args):
    allowance_id = getattr(args, "allowance_id", None)
    _validate_allowance(conn, allowance_id)

    t = Table("commercial_ti_draw")
    q = Q.from_(t).select(t.star).where(t.allowance_id == P())
    params = [allowance_id]
    draw_status = getattr(args, "draw_status", None)
    if draw_status:
        q = q.where(t.draw_status == P())
        params.append(draw_status)

    q = q.orderby(t.draw_date, order=Order.desc)
    rows = conn.execute(q.get_sql(), params).fetchall()

    total_drawn = sum(to_decimal(r["amount"]) for r in rows)
    ok({"draws": [row_to_dict(r) for r in rows], "count": len(rows),
        "total_drawn": str(round_currency(total_drawn))})


# ---------------------------------------------------------------------------
# 7. ti-summary-report
# ---------------------------------------------------------------------------
def ti_summary_report(conn, args):
    if not args.company_id:
        err("--company-id is required")

    t_a = Table("commercial_ti_allowance")
    t_l = Table("commercial_nnn_lease")
    q = (Q.from_(t_a)
         .join(t_l).on(t_a.lease_id == t_l.id)
         .select(t_a.star, t_l.tenant_name, t_l.property_name)
         .where(t_a.company_id == P())
         .orderby(t_a.created_at, order=Order.desc))
    rows = conn.execute(q.get_sql(), (args.company_id,)).fetchall()

    total_allowance = Decimal("0")
    total_disbursed = Decimal("0")
    total_remaining = Decimal("0")
    summaries = []
    for r in rows:
        ta = to_decimal(r["total_allowance"])
        da = to_decimal(r["disbursed_amount"])
        ra = to_decimal(r["remaining_amount"])
        total_allowance += ta
        total_disbursed += da
        total_remaining += ra
        summaries.append({
            "allowance_id": r["id"],
            "naming_series": r["naming_series"],
            "tenant_name": r["tenant_name"],
            "property_name": r["property_name"],
            "total_allowance": str(ta),
            "disbursed_amount": str(da),
            "remaining_amount": str(ra),
            "ti_status": r["ti_status"],
        })

    ok({
        "allowances": summaries,
        "count": len(summaries),
        "grand_total_allowance": str(round_currency(total_allowance)),
        "grand_total_disbursed": str(round_currency(total_disbursed)),
        "grand_total_remaining": str(round_currency(total_remaining)),
    })


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "commercial-add-ti-allowance": add_ti_allowance,
    "commercial-get-ti-allowance": get_ti_allowance,
    "commercial-update-ti-allowance": update_ti_allowance,
    "commercial-list-ti-allowances": list_ti_allowances,
    "commercial-add-ti-draw": add_ti_draw,
    "commercial-list-ti-draws": list_ti_draws,
    "commercial-ti-summary-report": ti_summary_report,
}
