"""PropertyClaw Commercial -- CAM (Common Area Maintenance) domain module

CAM pool management: create pools, track expenses, allocate to tenants,
run reconciliation, and generate true-up reports.
(3 tables: commercial_cam_pool, commercial_cam_expense, commercial_cam_allocation; 8 actions)
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
    ENTITY_PREFIXES.setdefault("commercial_cam_pool", "CCAM-")
except ImportError:
    pass

SKILL = "propertyclaw-commercial"

VALID_POOL_STATUSES = ("open", "reconciling", "closed")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    t_co = Table("company")
    q_co = Q.from_(t_co).select(t_co.id).where(t_co.id == P())
    if not conn.execute(q_co.get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _validate_pool(conn, pool_id):
    if not pool_id:
        err("--pool-id is required")
    t = Table("commercial_cam_pool")
    q = Q.from_(t).select(t.star).where(t.id == P())
    row = conn.execute(q.get_sql(), (pool_id,)).fetchone()
    if not row:
        err(f"CAM Pool {pool_id} not found")
    return row


def _recalc_pool_actual(conn, pool_id):
    """Recalculate total_actual for a CAM pool from its expenses."""
    row = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) as total FROM commercial_cam_expense WHERE pool_id = ?",
        (pool_id,)).fetchone()
    total = round_currency(to_decimal(str(row["total"])))
    conn.execute(
        "UPDATE commercial_cam_pool SET total_actual = ?, updated_at = datetime('now') WHERE id = ?",
        (str(total), pool_id))
    return total


# ---------------------------------------------------------------------------
# 1. add-cam-pool
# ---------------------------------------------------------------------------
def add_cam_pool(conn, args):
    _validate_company(conn, args.company_id)

    property_name = getattr(args, "property_name", None)
    if not property_name:
        err("--property-name is required")
    pool_year = getattr(args, "pool_year", None)
    if not pool_year:
        err("--pool-year is required")
    total_budget = getattr(args, "total_budget", None)
    if not total_budget:
        err("--total-budget is required")

    budget_dec = round_currency(to_decimal(total_budget))
    if budget_dec <= Decimal("0"):
        err("--total-budget must be greater than zero")

    pool_id = str(uuid.uuid4())
    conn.company_id = args.company_id
    pool_name = get_next_name(conn, "commercial_cam_pool")

    try:
        conn.execute(
            """INSERT INTO commercial_cam_pool
               (id, naming_series, company_id, property_name, pool_year,
                total_budget, total_actual, pool_status, notes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (pool_id, pool_name, args.company_id, property_name, pool_year,
             str(budget_dec), "0", "open", getattr(args, "notes", None)))
    except Exception as e:
        if "UNIQUE" in str(e):
            err(f"CAM pool already exists for {property_name} in {pool_year}")
        raise

    audit(conn, SKILL, "commercial-add-cam-pool", "commercial_cam_pool", pool_id,
          new_values={"naming_series": pool_name, "total_budget": str(budget_dec)})
    conn.commit()
    ok({"pool_id": pool_id, "naming_series": pool_name,
        "total_budget": str(budget_dec), "pool_status": "open"})


# ---------------------------------------------------------------------------
# 2. list-cam-pools
# ---------------------------------------------------------------------------
def list_cam_pools(conn, args):
    if not args.company_id:
        err("--company-id is required")

    params = [args.company_id]
    where = ["company_id = ?"]

    pool_year = getattr(args, "pool_year", None)
    if pool_year:
        where.append("pool_year = ?"); params.append(pool_year)
    pool_status = getattr(args, "pool_status", None)
    if pool_status:
        where.append("pool_status = ?"); params.append(pool_status)
    property_name = getattr(args, "property_name", None)
    if property_name:
        where.append("property_name = ?"); params.append(property_name)

    wc = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM commercial_cam_pool WHERE {wc}", params).fetchone()[0]

    limit = int(args.limit); offset = int(args.offset)
    rows = conn.execute(
        f"""SELECT * FROM commercial_cam_pool
            WHERE {wc} ORDER BY pool_year DESC, created_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall()

    ok({"pools": [row_to_dict(r) for r in rows], "total_count": total,
        "limit": limit, "offset": offset, "has_more": offset + limit < total})


# ---------------------------------------------------------------------------
# 3. get-cam-pool
# ---------------------------------------------------------------------------
def get_cam_pool(conn, args):
    pool = _validate_pool(conn, getattr(args, "pool_id", None))
    data = row_to_dict(pool)

    # Include expenses
    expenses = conn.execute(
        "SELECT * FROM commercial_cam_expense WHERE pool_id = ? ORDER BY expense_date DESC",
        (pool["id"],)).fetchall()
    data["expenses"] = [row_to_dict(e) for e in expenses]
    data["expense_count"] = len(expenses)

    # Include allocations
    allocations = conn.execute(
        """SELECT a.*, l.tenant_name, l.property_name
           FROM commercial_cam_allocation a
           JOIN commercial_nnn_lease l ON a.lease_id = l.id
           WHERE a.pool_id = ?""",
        (pool["id"],)).fetchall()
    data["allocations"] = [row_to_dict(a) for a in allocations]
    data["allocation_count"] = len(allocations)

    ok(data)


# ---------------------------------------------------------------------------
# 4. update-cam-pool
# ---------------------------------------------------------------------------
def update_cam_pool(conn, args):
    pool_id = getattr(args, "pool_id", None)
    _validate_pool(conn, pool_id)

    updates, params, changed = [], [], []

    total_budget = getattr(args, "total_budget", None)
    if total_budget is not None:
        budget_dec = round_currency(to_decimal(total_budget))
        updates.append("total_budget = ?"); params.append(str(budget_dec))
        changed.append("total_budget")

    pool_status = getattr(args, "pool_status", None)
    if pool_status is not None:
        if pool_status not in VALID_POOL_STATUSES:
            err(f"--pool-status must be one of: {', '.join(VALID_POOL_STATUSES)}")
        updates.append("pool_status = ?"); params.append(pool_status)
        changed.append("pool_status")

    notes = getattr(args, "notes", None)
    if notes is not None:
        updates.append("notes = ?"); params.append(notes)
        changed.append("notes")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(pool_id)
    conn.execute(f"UPDATE commercial_cam_pool SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"pool_id": pool_id, "updated_fields": changed})


# ---------------------------------------------------------------------------
# 5. add-cam-expense
# ---------------------------------------------------------------------------
def add_cam_expense(conn, args):
    pool_id = getattr(args, "pool_id", None)
    pool = _validate_pool(conn, pool_id)

    if pool["pool_status"] == "closed":
        err("Cannot add expenses to a closed CAM pool")

    expense_date = getattr(args, "expense_date", None)
    if not expense_date:
        err("--expense-date is required")
    category = getattr(args, "category", None)
    if not category:
        err("--category is required")
    amount = getattr(args, "amount", None)
    if not amount:
        err("--amount is required")

    amount_dec = round_currency(to_decimal(amount))
    if amount_dec <= Decimal("0"):
        err("--amount must be greater than zero")

    expense_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO commercial_cam_expense
           (id, pool_id, expense_date, category, vendor, amount, description, company_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (expense_id, pool_id, expense_date, category,
         getattr(args, "vendor", None), str(amount_dec),
         getattr(args, "description", None), pool["company_id"]))

    # Recalculate pool total
    _recalc_pool_actual(conn, pool_id)

    conn.commit()
    ok({"expense_id": expense_id, "amount": str(amount_dec), "category": category})


# ---------------------------------------------------------------------------
# 6. list-cam-expenses
# ---------------------------------------------------------------------------
def list_cam_expenses(conn, args):
    pool_id = getattr(args, "pool_id", None)
    if not pool_id:
        err("--pool-id is required")
    _validate_pool(conn, pool_id)

    params = [pool_id]
    where = ["pool_id = ?"]

    category = getattr(args, "category", None)
    if category:
        where.append("category = ?"); params.append(category)

    wc = " AND ".join(where)
    rows = conn.execute(
        f"SELECT * FROM commercial_cam_expense WHERE {wc} ORDER BY expense_date DESC",
        params).fetchall()

    total_amount = sum(to_decimal(r["amount"]) for r in rows)
    ok({"expenses": [row_to_dict(r) for r in rows], "count": len(rows),
        "total_amount": str(round_currency(total_amount))})


# ---------------------------------------------------------------------------
# 7. add-cam-allocation
# ---------------------------------------------------------------------------
def add_cam_allocation(conn, args):
    pool_id = getattr(args, "pool_id", None)
    pool = _validate_pool(conn, pool_id)

    lease_id = getattr(args, "lease_id", None)
    if not lease_id:
        err("--lease-id is required")
    t_lease = Table("commercial_nnn_lease")
    q_lease = Q.from_(t_lease).select(t_lease.star).where(t_lease.id == P())
    lease = conn.execute(q_lease.get_sql(), (lease_id,)).fetchone()
    if not lease:
        err(f"NNN Lease {lease_id} not found")

    cam_share_pct = getattr(args, "cam_share_pct", None)
    share_pct = to_decimal(cam_share_pct) if cam_share_pct else to_decimal(lease["cam_share_pct"])

    budget = to_decimal(pool["total_budget"])
    budgeted_amount = round_currency(budget * share_pct / Decimal("100"))

    actual = to_decimal(pool["total_actual"])
    actual_amount = round_currency(actual * share_pct / Decimal("100"))
    variance = round_currency(actual_amount - budgeted_amount)

    alloc_id = str(uuid.uuid4())
    try:
        conn.execute(
            """INSERT INTO commercial_cam_allocation
               (id, pool_id, lease_id, share_pct, budgeted_amount,
                actual_amount, variance, company_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (alloc_id, pool_id, lease_id, str(share_pct), str(budgeted_amount),
             str(actual_amount), str(variance), pool["company_id"]))
    except Exception as e:
        if "UNIQUE" in str(e):
            err(f"Allocation already exists for lease {lease_id} in pool {pool_id}")
        raise

    conn.commit()
    ok({"allocation_id": alloc_id, "share_pct": str(share_pct),
        "budgeted_amount": str(budgeted_amount), "actual_amount": str(actual_amount),
        "variance": str(variance)})


# ---------------------------------------------------------------------------
# 8. list-cam-allocations
# ---------------------------------------------------------------------------
def list_cam_allocations(conn, args):
    pool_id = getattr(args, "pool_id", None)
    if not pool_id:
        err("--pool-id is required")
    _validate_pool(conn, pool_id)

    rows = conn.execute(
        """SELECT a.*, l.tenant_name, l.property_name, l.suite_number
           FROM commercial_cam_allocation a
           JOIN commercial_nnn_lease l ON a.lease_id = l.id
           WHERE a.pool_id = ?
           ORDER BY l.tenant_name""",
        (pool_id,)).fetchall()

    total_share = sum(to_decimal(r["share_pct"]) for r in rows)
    total_budgeted = sum(to_decimal(r["budgeted_amount"]) for r in rows)
    total_actual = sum(to_decimal(r["actual_amount"]) for r in rows)

    ok({
        "allocations": [row_to_dict(r) for r in rows],
        "count": len(rows),
        "total_share_pct": str(round_currency(total_share)),
        "total_budgeted": str(round_currency(total_budgeted)),
        "total_actual": str(round_currency(total_actual)),
    })


# ---------------------------------------------------------------------------
# 9. run-cam-reconciliation
# ---------------------------------------------------------------------------
def run_cam_reconciliation(conn, args):
    pool_id = getattr(args, "pool_id", None)
    pool = _validate_pool(conn, pool_id)

    if pool["pool_status"] == "closed":
        err("Cannot reconcile a closed CAM pool")

    # Recalculate total actual from expenses
    total_actual = _recalc_pool_actual(conn, pool_id)
    budget = to_decimal(pool["total_budget"])

    # Update each allocation with actual amounts
    allocations = conn.execute(
        "SELECT * FROM commercial_cam_allocation WHERE pool_id = ?",
        (pool_id,)).fetchall()

    results = []
    for alloc in allocations:
        share_pct = to_decimal(alloc["share_pct"])
        actual_share = round_currency(total_actual * share_pct / Decimal("100"))
        budgeted_share = round_currency(budget * share_pct / Decimal("100"))
        variance = round_currency(actual_share - budgeted_share)

        conn.execute(
            """UPDATE commercial_cam_allocation
               SET actual_amount = ?, budgeted_amount = ?, variance = ?,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (str(actual_share), str(budgeted_share), str(variance), alloc["id"]))

        results.append({
            "allocation_id": alloc["id"],
            "lease_id": alloc["lease_id"],
            "share_pct": str(share_pct),
            "budgeted_amount": str(budgeted_share),
            "actual_amount": str(actual_share),
            "variance": str(variance),
        })

    # Mark pool as reconciling
    conn.execute(
        "UPDATE commercial_cam_pool SET pool_status = 'reconciling', updated_at = datetime('now') WHERE id = ?",
        (pool_id,))

    reconciliation_date = getattr(args, "reconciliation_date", None) or \
        datetime.now(timezone.utc).strftime("%Y-%m-%d")

    audit(conn, SKILL, "commercial-run-cam-reconciliation", "commercial_cam_pool", pool_id,
          new_values={"reconciliation_date": reconciliation_date, "total_actual": str(total_actual)})
    conn.commit()

    ok({
        "pool_id": pool_id,
        "reconciliation_date": reconciliation_date,
        "total_budget": str(round_currency(budget)),
        "total_actual": str(total_actual),
        "budget_variance": str(round_currency(total_actual - budget)),
        "allocations": results,
        "pool_status": "reconciling",
    })


# ---------------------------------------------------------------------------
# 10. cam-reconciliation-report
# ---------------------------------------------------------------------------
def cam_reconciliation_report(conn, args):
    if not args.company_id:
        err("--company-id is required")

    pool_year = getattr(args, "pool_year", None)
    property_name = getattr(args, "property_name", None)

    params = [args.company_id]
    where = ["p.company_id = ?"]
    if pool_year:
        where.append("p.pool_year = ?"); params.append(pool_year)
    if property_name:
        where.append("p.property_name = ?"); params.append(property_name)

    wc = " AND ".join(where)
    pools = conn.execute(
        f"SELECT * FROM commercial_cam_pool p WHERE {wc} ORDER BY p.pool_year DESC, p.property_name",
        params).fetchall()

    report = []
    for pool in pools:
        allocations = conn.execute(
            """SELECT a.*, l.tenant_name
               FROM commercial_cam_allocation a
               JOIN commercial_nnn_lease l ON a.lease_id = l.id
               WHERE a.pool_id = ?""",
            (pool["id"],)).fetchall()

        pool_data = row_to_dict(pool)
        pool_data["budget_variance"] = str(round_currency(
            to_decimal(pool["total_actual"]) - to_decimal(pool["total_budget"])))
        pool_data["allocations"] = [{
            "tenant_name": a["tenant_name"],
            "share_pct": a["share_pct"],
            "budgeted_amount": a["budgeted_amount"],
            "actual_amount": a["actual_amount"],
            "variance": a["variance"],
        } for a in allocations]
        report.append(pool_data)

    ok({"pools": report, "pool_count": len(report)})


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "commercial-add-cam-pool": add_cam_pool,
    "commercial-list-cam-pools": list_cam_pools,
    "commercial-get-cam-pool": get_cam_pool,
    "commercial-update-cam-pool": update_cam_pool,
    "commercial-add-cam-expense": add_cam_expense,
    "commercial-list-cam-expenses": list_cam_expenses,
    "commercial-add-cam-allocation": add_cam_allocation,
    "commercial-list-cam-allocations": list_cam_allocations,
    "commercial-run-cam-reconciliation": run_cam_reconciliation,
    "commercial-cam-reconciliation-report": cam_reconciliation_report,
}
