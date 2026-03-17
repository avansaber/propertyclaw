"""PropertyClaw Commercial — Reports domain module

Reporting and analytics actions for commercial real estate (6 actions + status).
Imported by db_query.py (unified router).
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row
except ImportError:
    pass

SKILL = "propertyclaw-commercial"


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    t_co = Table("company")
    q_co = Q.from_(t_co).select(t_co.id).where(t_co.id == P())
    if not conn.execute(q_co.get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")


# ---------------------------------------------------------------------------
# 1. noi-report (Net Operating Income)
# ---------------------------------------------------------------------------
def noi_report(conn, args):
    _validate_company(conn, args.company_id)
    property_name = getattr(args, "property_name", None)

    from erpclaw_lib.vendor.pypika.terms import LiteralValue

    # Active leases for company
    t_l = Table("commercial_nnn_lease")
    q_leases = (Q.from_(t_l).select(t_l.star)
                .where(t_l.company_id == P()).where(t_l.lease_status == P()))
    params = [args.company_id, "active"]
    if property_name:
        q_leases = q_leases.where(t_l.property_name == P())
        params.append(property_name)
    leases = conn.execute(q_leases.get_sql(), params).fetchall()

    total_income = Decimal("0")
    for lease in leases:
        total_income += to_decimal(lease["base_rent"])

    # Total CAM expenses for open/reconciling pools
    t_e = Table("commercial_cam_expense")
    t_p = Table("commercial_cam_pool")
    q_exp = (Q.from_(t_e)
             .join(t_p).on(t_e.pool_id == t_p.id)
             .select(LiteralValue('COALESCE(SUM(CAST("commercial_cam_expense"."amount" AS NUMERIC)), 0)').as_("total_expenses"))
             .where(t_p.company_id == P())
             .where(t_p.pool_status.isin(["open", "reconciling"])))
    exp_params = [args.company_id]
    if property_name:
        q_exp = q_exp.where(t_p.property_name == P())
        exp_params.append(property_name)
    expenses_row = conn.execute(q_exp.get_sql(), exp_params).fetchone()
    total_expenses = to_decimal(str(expenses_row["total_expenses"]))

    noi = round_currency(total_income - total_expenses)

    ok({
        "property_name": property_name or "All Properties",
        "total_rental_income": str(round_currency(total_income)),
        "total_operating_expenses": str(round_currency(total_expenses)),
        "net_operating_income": str(noi),
        "lease_count": len(leases),
    })


# ---------------------------------------------------------------------------
# 2. cap-rate-analysis
# ---------------------------------------------------------------------------
def cap_rate_analysis(conn, args):
    _validate_company(conn, args.company_id)
    property_value = getattr(args, "property_value", None)
    if not property_value:
        err("--property-value is required")

    pv = to_decimal(property_value)
    if pv <= Decimal("0"):
        err("--property-value must be greater than zero")

    property_name = getattr(args, "property_name", None)

    from erpclaw_lib.vendor.pypika.terms import LiteralValue

    # Calculate annual NOI
    t_l = Table("commercial_nnn_lease")
    q_leases = (Q.from_(t_l).select(t_l.base_rent)
                .where(t_l.company_id == P()).where(t_l.lease_status == P()))
    params = [args.company_id, "active"]
    if property_name:
        q_leases = q_leases.where(t_l.property_name == P())
        params.append(property_name)
    leases = conn.execute(q_leases.get_sql(), params).fetchall()
    annual_income = sum(to_decimal(l["base_rent"]) for l in leases) * Decimal("12")

    # Annual expenses
    t_e = Table("commercial_cam_expense")
    t_p = Table("commercial_cam_pool")
    q_exp = (Q.from_(t_e)
             .join(t_p).on(t_e.pool_id == t_p.id)
             .select(LiteralValue('COALESCE(SUM(CAST("commercial_cam_expense"."amount" AS NUMERIC)), 0)').as_("total_expenses"))
             .where(t_p.company_id == P()))
    exp_params = [args.company_id]
    if property_name:
        q_exp = q_exp.where(t_p.property_name == P())
        exp_params.append(property_name)
    expenses_row = conn.execute(q_exp.get_sql(), exp_params).fetchone()
    annual_expenses = to_decimal(str(expenses_row["total_expenses"]))

    annual_noi = round_currency(annual_income - annual_expenses)
    cap_rate = round_currency(annual_noi / pv * Decimal("100")) if pv > Decimal("0") else Decimal("0")

    ok({
        "property_name": property_name or "All Properties",
        "annual_rental_income": str(round_currency(annual_income)),
        "annual_operating_expenses": str(round_currency(annual_expenses)),
        "annual_noi": str(annual_noi),
        "property_value": str(round_currency(pv)),
        "cap_rate_pct": str(cap_rate),
    })


# ---------------------------------------------------------------------------
# 3. occupancy-trend
# ---------------------------------------------------------------------------
def occupancy_trend(conn, args):
    _validate_company(conn, args.company_id)

    t = Table("commercial_nnn_lease")

    q_total = Q.from_(t).select(fn.Count("*")).where(t.company_id == P())
    total = conn.execute(q_total.get_sql(), (args.company_id,)).fetchone()[0]

    q_active = Q.from_(t).select(fn.Count("*")).where(t.company_id == P()).where(t.lease_status == "active")
    active = conn.execute(q_active.get_sql(), (args.company_id,)).fetchone()[0]

    q_draft = Q.from_(t).select(fn.Count("*")).where(t.company_id == P()).where(t.lease_status == "draft")
    draft = conn.execute(q_draft.get_sql(), (args.company_id,)).fetchone()[0]

    q_expired = Q.from_(t).select(fn.Count("*")).where(t.company_id == P()).where(t.lease_status == "expired")
    expired = conn.execute(q_expired.get_sql(), (args.company_id,)).fetchone()[0]

    q_term = Q.from_(t).select(fn.Count("*")).where(t.company_id == P()).where(t.lease_status == "terminated")
    terminated = conn.execute(q_term.get_sql(), (args.company_id,)).fetchone()[0]

    occupancy_rate = str(round_currency(
        Decimal(str(active)) / Decimal(str(total)) * Decimal("100")
    )) if total > 0 else "0.00"

    ok({
        "total_leases": total,
        "active": active,
        "draft": draft,
        "expired": expired,
        "terminated": terminated,
        "occupancy_rate_pct": occupancy_rate,
    })


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "commercial-noi-report": noi_report,
    "commercial-cap-rate-analysis": cap_rate_analysis,
    "commercial-occupancy-trend": occupancy_trend,
}
