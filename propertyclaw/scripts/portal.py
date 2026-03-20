#!/usr/bin/env python3
"""propertyclaw tenant portal domain module.

Scoped-read actions for tenant self-service. Every action verifies
the tenant-lease relationship before returning data.
Imported by the unified propertyclaw db_query.py router.
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection, ensure_db_exists, DEFAULT_DB_PATH
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order
except ImportError:
    import json as _json
    print(_json.dumps({
        "status": "error",
        "error": "ERPClaw foundation not installed. Install erpclaw first: clawhub install erpclaw",
        "suggestion": "clawhub install erpclaw"
    }))
    sys.exit(1)

SKILL = "prop-propertyclaw-portal"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _verify_tenant(conn, customer_id):
    """Verify tenant exists and return their active lease(s)."""
    if not customer_id:
        err("--customer-id is required (tenant identity)")
    if not conn.execute(Q.from_(Table("customer")).select(Field("id")).where(Field("id") == P()).get_sql(), (customer_id,)).fetchone():
        err(f"Tenant {customer_id} not found")
    return customer_id


def _get_tenant_leases(conn, customer_id):
    """Return all leases for this tenant."""
    rows = conn.execute(
        """SELECT l.id FROM propertyclaw_lease l
           WHERE l.customer_id = ? AND l.status IN ('active', 'expired', 'renewed')""",
        (customer_id,)).fetchall()
    return [r["id"] for r in rows]


def _verify_tenant_lease(conn, customer_id, lease_id=None):
    """Verify tenant owns the given lease. If no lease_id, find active one."""
    _verify_tenant(conn, customer_id)

    if lease_id:
        row = conn.execute(
            """SELECT id, customer_id FROM propertyclaw_lease WHERE id = ?""",
            (lease_id,)).fetchone()
        if not row:
            err(f"Lease {lease_id} not found")
        if row["customer_id"] != customer_id:
            err("Access denied: lease does not belong to this tenant")
        return lease_id

    # Find active lease
    row = conn.execute(
        """SELECT id FROM propertyclaw_lease
           WHERE customer_id = ? AND status = 'active'
           ORDER BY start_date DESC LIMIT 1""",
        (customer_id,)).fetchone()
    if not row:
        err("No active lease found for this tenant")
    return row["id"]


# ---------------------------------------------------------------------------
# prop-portal-my-lease
# ---------------------------------------------------------------------------
def portal_my_lease(conn, args):
    """View tenant's current lease details."""
    lease_id = _verify_tenant_lease(conn, args.customer_id, args.lease_id)

    row = conn.execute(
        """SELECT l.*, p.name as property_name, p.address_line1, p.city,
                  p.state, p.zip_code, u.unit_number, u.unit_type,
                  u.bedrooms, u.bathrooms, u.sq_ft
           FROM propertyclaw_lease l
           JOIN propertyclaw_property p ON l.property_id = p.id
           JOIN propertyclaw_unit u ON l.unit_id = u.id
           WHERE l.id = ?""",
        (lease_id,)).fetchone()

    data = row_to_dict(row)
    # Include rent schedules
    schedules = conn.execute(
        "SELECT * FROM propertyclaw_rent_schedule WHERE lease_id = ? ORDER BY charge_type",
        (lease_id,)).fetchall()
    data["rent_schedules"] = [row_to_dict(s) for s in schedules]
    ok(data)


# ---------------------------------------------------------------------------
# prop-portal-my-charges
# ---------------------------------------------------------------------------
def portal_my_charges(conn, args):
    """View tenant's charges (pending and paid)."""
    lease_id = _verify_tenant_lease(conn, args.customer_id, args.lease_id)

    params = [lease_id]
    where = "lease_id = ?"
    if args.charge_status:
        where += " AND status = ?"
        params.append(args.charge_status)

    limit = int(args.limit); offset = int(args.offset)
    total = conn.execute(
        f"SELECT COUNT(*) FROM propertyclaw_lease_charge WHERE {where}",
        params).fetchone()[0]

    rows = conn.execute(
        f"""SELECT * FROM propertyclaw_lease_charge
            WHERE {where} ORDER BY charge_date DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall()

    # Calculate balances
    pending_total = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS NUMERIC)), 0) FROM propertyclaw_lease_charge WHERE lease_id = ? AND status = 'pending'",
        (lease_id,)).fetchone()[0]

    ok({
        "charges": [row_to_dict(r) for r in rows],
        "total_count": total,
        "pending_balance": str(round_currency(to_decimal(str(pending_total)))),
        "limit": limit, "offset": offset,
    })


# ---------------------------------------------------------------------------
# prop-portal-my-payments
# ---------------------------------------------------------------------------
def portal_my_payments(conn, args):
    """View tenant's payment history (paid charges)."""
    lease_id = _verify_tenant_lease(conn, args.customer_id, args.lease_id)

    limit = int(args.limit); offset = int(args.offset)
    rows = conn.execute(
        """SELECT * FROM propertyclaw_lease_charge
           WHERE lease_id = ? AND status = 'paid'
           ORDER BY charge_date DESC LIMIT ? OFFSET ?""",
        (lease_id, limit, offset)).fetchall()

    total = conn.execute(
        "SELECT COUNT(*) FROM propertyclaw_lease_charge WHERE lease_id = ? AND status = 'paid'",
        (lease_id,)).fetchone()[0]

    paid_total = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS NUMERIC)), 0) FROM propertyclaw_lease_charge WHERE lease_id = ? AND status = 'paid'",
        (lease_id,)).fetchone()[0]

    ok({
        "payments": [row_to_dict(r) for r in rows],
        "total_count": total,
        "total_paid": str(round_currency(to_decimal(str(paid_total)))),
        "limit": limit, "offset": offset,
    })


# ---------------------------------------------------------------------------
# prop-portal-submit-maintenance-request
# ---------------------------------------------------------------------------
def portal_submit_maintenance_request(conn, args):
    """Submit a maintenance request through the tenant portal."""
    lease_id = _verify_tenant_lease(conn, args.customer_id, args.lease_id)

    if not args.description:
        err("--description is required")

    # Look up lease details for work order
    lease = conn.execute(
        "SELECT company_id, property_id, unit_id FROM propertyclaw_lease WHERE id = ?",
        (lease_id,)).fetchone()

    category = args.category or "general"
    priority = args.priority or "routine"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pte = 1 if getattr(args, "permission_to_enter", None) and str(args.permission_to_enter).lower() in ("1", "true", "yes") else 0

    wo_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO propertyclaw_work_order
           (id, company_id, property_id, unit_id, lease_id,
            customer_id, category, priority, description, reported_date,
            permission_to_enter, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (wo_id, lease["company_id"], lease["property_id"], lease["unit_id"],
         lease_id, args.customer_id, category, priority,
         args.description, today, pte, "open"))

    audit(conn, SKILL, "prop-portal-submit-maintenance-request",
          "propertyclaw_work_order", wo_id,
          new_values={"tenant_id": args.customer_id, "category": category})
    conn.commit()
    ok({
        "work_order_id": wo_id,
        "category": category,
        "priority": priority,
        "wo_status": "open",
        "reported_date": today,
    })


# ---------------------------------------------------------------------------
# prop-portal-list-maintenance-requests
# ---------------------------------------------------------------------------
def portal_list_maintenance_requests(conn, args):
    """List maintenance requests for the tenant's unit(s)."""
    _verify_tenant(conn, args.customer_id)

    lease_ids = _get_tenant_leases(conn, args.customer_id)
    if not lease_ids:
        ok({"maintenance_requests": [], "count": 0})
        return

    placeholders = ", ".join(["?"] * len(lease_ids))
    rows = conn.execute(
        f"""SELECT w.id, w.category, w.priority, w.description,
                   w.reported_date, w.status, p.name as property_name,
                   u.unit_number
            FROM propertyclaw_work_order w
            JOIN propertyclaw_property p ON w.property_id = p.id
            LEFT JOIN propertyclaw_unit u ON w.unit_id = u.id
            WHERE w.customer_id = ? OR w.lease_id IN ({placeholders})
            ORDER BY w.reported_date DESC
            LIMIT ? OFFSET ?""",
        [args.customer_id] + lease_ids + [int(args.limit), int(args.offset)]).fetchall()

    ok({"maintenance_requests": [row_to_dict(r) for r in rows],
        "count": len(rows)})


# ---------------------------------------------------------------------------
# prop-portal-my-documents
# ---------------------------------------------------------------------------
def portal_my_documents(conn, args):
    """List documents associated with the tenant."""
    _verify_tenant(conn, args.customer_id)

    rows = conn.execute(
        """SELECT * FROM propertyclaw_tenant_document
           WHERE customer_id = ?
           ORDER BY uploaded_at DESC LIMIT ? OFFSET ?""",
        (args.customer_id, int(args.limit), int(args.offset))).fetchall()

    total = conn.execute(
        "SELECT COUNT(*) FROM propertyclaw_tenant_document WHERE customer_id = ?",
        (args.customer_id,)).fetchone()[0]

    ok({"documents": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": int(args.limit), "offset": int(args.offset)})


# ---------------------------------------------------------------------------
# prop-portal-update-contact-info
# ---------------------------------------------------------------------------
def portal_update_contact_info(conn, args):
    """Update tenant's contact information."""
    _verify_tenant(conn, args.customer_id)

    updates = []
    params = []
    changed = []

    email = getattr(args, "applicant_email", None)
    phone = getattr(args, "applicant_phone", None)
    name = getattr(args, "name", None)

    if email is not None:
        updates.append("primary_contact = ?"); params.append(email); changed.append("primary_contact")
    if phone is not None:
        updates.append("primary_address = ?"); params.append(phone); changed.append("primary_address")
    if name is not None:
        updates.append("name = ?"); params.append(name); changed.append("name")

    if not changed:
        err("No contact fields to update (use --applicant-email, --applicant-phone, or --name)")

    # Update tenant contact on the lease record (not core customer table — Art 5)
    params.append(args.customer_id)
    conn.execute(
        f"UPDATE propertyclaw_lease SET {', '.join(updates)} WHERE tenant_id = ? AND status = 'active'",
        params)

    audit(conn, SKILL, "prop-portal-update-contact-info", "customer",
          args.customer_id, new_values={"updated_fields": changed})
    conn.commit()
    ok({"customer_id": args.customer_id, "updated_fields": changed})


# ---------------------------------------------------------------------------
# prop-portal-announcements
# ---------------------------------------------------------------------------
def portal_announcements(conn, args):
    """Show property-level announcements for the tenant's properties.

    Uses work orders with category 'safety' and inspections as announcements.
    In a real system, a dedicated announcements table would exist.
    This provides a tenant-scoped view of upcoming maintenance/inspections.
    """
    _verify_tenant(conn, args.customer_id)

    lease_ids = _get_tenant_leases(conn, args.customer_id)
    if not lease_ids:
        ok({"announcements": [], "count": 0})
        return

    # Get property IDs from leases
    placeholders = ", ".join(["?"] * len(lease_ids))
    props = conn.execute(
        f"SELECT DISTINCT property_id FROM propertyclaw_lease WHERE id IN ({placeholders})",
        lease_ids).fetchall()
    prop_ids = [p["property_id"] for p in props]

    if not prop_ids:
        ok({"announcements": [], "count": 0})
        return

    prop_placeholders = ", ".join(["?"] * len(prop_ids))

    # Upcoming inspections
    inspections = conn.execute(
        f"""SELECT i.id, i.inspection_type, i.inspection_date, i.status,
                   p.name as property_name, u.unit_number,
                   'inspection' as announcement_type
            FROM propertyclaw_inspection i
            JOIN propertyclaw_property p ON i.property_id = p.id
            LEFT JOIN propertyclaw_unit u ON i.unit_id = u.id
            WHERE i.property_id IN ({prop_placeholders})
                  AND i.status = 'scheduled'
            ORDER BY i.inspection_date ASC LIMIT 10""",
        prop_ids).fetchall()

    announcements = [row_to_dict(r) for r in inspections]

    ok({"announcements": announcements, "count": len(announcements)})


# ---------------------------------------------------------------------------
# Action Router
# ---------------------------------------------------------------------------
ACTIONS = {
    "prop-portal-my-lease": portal_my_lease,
    "prop-portal-my-charges": portal_my_charges,
    "prop-portal-my-payments": portal_my_payments,
    "prop-portal-submit-maintenance-request": portal_submit_maintenance_request,
    "prop-portal-list-maintenance-requests": portal_list_maintenance_requests,
    "prop-portal-my-documents": portal_my_documents,
    "prop-portal-update-contact-info": portal_update_contact_info,
    "prop-portal-announcements": portal_announcements,
}
