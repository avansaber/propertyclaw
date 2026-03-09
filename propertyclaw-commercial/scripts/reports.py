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
except ImportError:
    pass

SKILL = "propertyclaw-commercial"


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute("SELECT id FROM company WHERE id = ?", (company_id,)).fetchone():
        err(f"Company {company_id} not found")


# ---------------------------------------------------------------------------
# 1. noi-report (Net Operating Income)
# ---------------------------------------------------------------------------
def noi_report(conn, args):
    _validate_company(conn, args.company_id)
    property_name = getattr(args, "property_name", None)

    # Active leases for company
    params = [args.company_id, "active"]
    where = "company_id = ? AND lease_status = ?"
    if property_name:
        where += " AND property_name = ?"
        params.append(property_name)

    leases = conn.execute(
        f"SELECT * FROM commercial_nnn_lease WHERE {where}", params).fetchall()

    total_income = Decimal("0")
    for lease in leases:
        total_income += to_decimal(lease["base_rent"])

    # Total CAM expenses for open/reconciling pools
    exp_params = [args.company_id]
    exp_where = "p.company_id = ? AND p.pool_status IN ('open', 'reconciling')"
    if property_name:
        exp_where += " AND p.property_name = ?"
        exp_params.append(property_name)

    expenses_row = conn.execute(
        f"""SELECT COALESCE(SUM(CAST(e.amount AS REAL)), 0) as total_expenses
            FROM commercial_cam_expense e
            JOIN commercial_cam_pool p ON e.pool_id = p.id
            WHERE {exp_where}""",
        exp_params).fetchone()
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

    # Calculate annual NOI
    params = [args.company_id, "active"]
    where = "company_id = ? AND lease_status = ?"
    if property_name:
        where += " AND property_name = ?"
        params.append(property_name)

    leases = conn.execute(
        f"SELECT base_rent FROM commercial_nnn_lease WHERE {where}", params).fetchall()
    annual_income = sum(to_decimal(l["base_rent"]) for l in leases) * Decimal("12")

    # Annual expenses
    exp_params = [args.company_id]
    exp_where = "p.company_id = ?"
    if property_name:
        exp_where += " AND p.property_name = ?"
        exp_params.append(property_name)

    expenses_row = conn.execute(
        f"""SELECT COALESCE(SUM(CAST(e.amount AS REAL)), 0) as total_expenses
            FROM commercial_cam_expense e
            JOIN commercial_cam_pool p ON e.pool_id = p.id
            WHERE {exp_where}""",
        exp_params).fetchone()
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

    total = conn.execute(
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
    terminated = conn.execute(
        "SELECT COUNT(*) FROM commercial_nnn_lease WHERE company_id = ? AND lease_status = 'terminated'",
        (args.company_id,)).fetchone()[0]

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
