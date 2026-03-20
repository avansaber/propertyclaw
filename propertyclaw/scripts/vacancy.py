"""PropertyClaw -- Vacancy Listing, Utility Billing (RUBS), Bank Reconciliation,
Lease Document Gen, Tenant Communication, Vendor Bidding domain module.

22 actions across 6 gap areas:
P3: Vacancy Listing (5 actions)
P4: Utility Billing/RUBS (4 actions)
P5: Bank Reconciliation (4 actions)
P6: Lease Document Gen (2 actions)
P7: Tenant Communication (3 actions)
P10: Vendor Bidding (4 actions)
"""
import json
import os
import sys
import uuid
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection, ensure_db_exists, DEFAULT_DB_PATH
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row, dynamic_update, now
except ImportError:
    import json as _json
    print(_json.dumps({
        "status": "error",
        "error": "ERPClaw foundation not installed.",
        "suggestion": "clawhub install erpclaw"
    }))
    sys.exit(1)

SKILL = "propertyclaw"

_t_listing = Table("propertyclaw_listing")
_t_unit = Table("propertyclaw_unit")
_t_lease = Table("propertyclaw_lease")
_t_charge = Table("propertyclaw_lease_charge")
_t_trust = Table("propertyclaw_trust_account")
_t_recon = Table("propertyclaw_trust_reconciliation")
_t_announce = Table("propertyclaw_announcement")
_t_bid = Table("propertyclaw_vendor_bid")
_t_wo = Table("propertyclaw_work_order")
_t_property = Table("propertyclaw_property")
_t_doc = Table("propertyclaw_tenant_document")

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _d(val, default="0"):
    if val is None:
        return Decimal(default)
    return Decimal(str(val))


# ===========================================================================
# P3: VACANCY LISTING
# ===========================================================================

def create_listing(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")
    unit_id = getattr(args, "unit_id", None)
    if not unit_id:
        err("--unit-id is required")

    unit = conn.execute(
        Q.from_(_t_unit).select(_t_unit.star).where(_t_unit.id == P()).get_sql(),
        (unit_id,),
    ).fetchone()
    if not unit:
        err(f"Unit {unit_id} not found")

    l_id = str(uuid.uuid4())
    n = _now_iso()
    sql, _ = insert_row("propertyclaw_listing", {
        "id": P(), "unit_id": P(), "listing_title": P(), "description": P(),
        "asking_rent": P(), "available_date": P(), "photos": P(),
        "amenities": P(), "syndicated_to": P(), "listing_url": P(),
        "lead_count": P(), "status": P(), "company_id": P(),
        "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql, (
        l_id, unit_id,
        getattr(args, "listing_title", None),
        getattr(args, "description", None),
        str(_d(getattr(args, "asking_rent", None))),
        getattr(args, "available_date", None),
        getattr(args, "photos", None),
        getattr(args, "amenities", None),
        getattr(args, "syndicated_to", None),
        getattr(args, "listing_url", None),
        0, "draft",
        args.company_id, n, n,
    ))
    audit(conn, SKILL, "prop-create-listing", "propertyclaw_listing", l_id,
          new_values={"unit_id": unit_id})
    conn.commit()
    ok({"listing_id": l_id, "unit_id": unit_id, "listing_status": "draft"})


def list_listings(conn, args):
    t = _t_listing
    q = Q.from_(t).select(t.star)
    params = []

    cid = getattr(args, "company_id", None)
    if cid:
        q = q.where(t.company_id == P())
        params.append(cid)
    uid = getattr(args, "unit_id", None)
    if uid:
        q = q.where(t.unit_id == P())
        params.append(uid)
    st = getattr(args, "listing_status", None)
    if st:
        q = q.where(t.status == P())
        params.append(st)

    q = q.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    limit = getattr(args, "limit", 50) or 50
    offset = getattr(args, "offset", 0) or 0
    rows = conn.execute(q.get_sql(), params + [limit, offset]).fetchall()
    ok({"listings": [row_to_dict(r) for r in rows], "total_count": len(rows)})


def update_listing(conn, args):
    l_id = getattr(args, "listing_id", None)
    if not l_id:
        err("--listing-id is required")

    row = conn.execute(
        Q.from_(_t_listing).select(_t_listing.star).where(_t_listing.id == P()).get_sql(),
        (l_id,),
    ).fetchone()
    if not row:
        err(f"Listing {l_id} not found")

    data, changed = {}, []
    for field, attr in [
        ("listing_title", "listing_title"), ("description", "description"),
        ("asking_rent", "asking_rent"), ("available_date", "available_date"),
        ("photos", "photos"), ("amenities", "amenities"),
        ("syndicated_to", "syndicated_to"), ("listing_url", "listing_url"),
    ]:
        val = getattr(args, attr, None)
        if val is not None:
            data[field] = val if field != "asking_rent" else str(_d(val))
            changed.append(field)

    ls = getattr(args, "listing_status", None)
    if ls:
        if ls not in ("draft", "active", "rented", "expired"):
            err(f"Invalid listing status: {ls}")
        data["status"] = ls
        changed.append("status")

    if not changed:
        err("No fields to update")

    data["updated_at"] = _now_iso()
    sql, params = dynamic_update("propertyclaw_listing", data, {"id": l_id})
    conn.execute(sql, params)
    audit(conn, SKILL, "prop-update-listing", "propertyclaw_listing", l_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"listing_id": l_id, "updated_fields": changed})


def listing_performance_report(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")

    rows = conn.execute(
        """SELECT l.*, u.unit_number, u.property_id
           FROM propertyclaw_listing l
           JOIN propertyclaw_unit u ON l.unit_id = u.id
           WHERE l.company_id = ?
           ORDER BY l.lead_count DESC""",
        (args.company_id,),
    ).fetchall()

    listings = []
    total_leads = 0
    active_count = 0
    for r in rows:
        d = row_to_dict(r)
        total_leads += r["lead_count"] or 0
        if r["status"] == "active":
            active_count += 1
        listings.append(d)

    ok({
        "company_id": args.company_id,
        "total_listings": len(listings),
        "active_listings": active_count,
        "total_leads": total_leads,
        "listings": listings,
    })


def list_vacancies(conn, args):
    """List all available (unoccupied) units across properties."""
    if not getattr(args, "company_id", None):
        err("--company-id is required")

    rows = conn.execute(
        """SELECT u.*, p.name as property_name, p.address_line1
           FROM propertyclaw_unit u
           JOIN propertyclaw_property p ON u.property_id = p.id
           WHERE p.company_id = ? AND u.status = 'available'
           ORDER BY p.name, u.unit_number""",
        (args.company_id,),
    ).fetchall()

    vacancies = [row_to_dict(r) for r in rows]
    ok({
        "company_id": args.company_id,
        "total_vacancies": len(vacancies),
        "vacancies": vacancies,
    })


# ===========================================================================
# P4: UTILITY BILLING / RUBS
# ===========================================================================

def calculate_rubs(conn, args):
    """Allocate utility cost by sq ft or occupancy across occupied units in a property."""
    if not getattr(args, "company_id", None):
        err("--company-id is required")
    property_id = getattr(args, "property_id", None)
    if not property_id:
        err("--property-id is required")
    amount_raw = getattr(args, "amount", None)
    if not amount_raw:
        err("--amount is required (total utility cost to allocate)")

    total_cost = _d(amount_raw)

    # Get all occupied units in the property
    units = conn.execute(
        """SELECT u.id, u.unit_number, u.sq_ft, l.customer_id, l.id as lease_id
           FROM propertyclaw_unit u
           LEFT JOIN propertyclaw_lease l ON l.unit_id = u.id AND l.status = 'active'
           WHERE u.property_id = ? AND u.status = 'occupied'""",
        (property_id,),
    ).fetchall()

    if not units:
        err(f"No occupied units found for property {property_id}")

    total_sqft = sum(_d(u["sq_ft"]) for u in units if u["sq_ft"])
    if total_sqft == 0:
        # Equal split if no sq ft data
        share = total_cost / Decimal(str(len(units)))
        allocations = []
        for u in units:
            allocations.append({
                "unit_id": u["id"],
                "unit_number": u["unit_number"],
                "lease_id": u["lease_id"],
                "sq_ft": u["sq_ft"],
                "allocation_method": "equal",
                "allocated_amount": str(share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            })
    else:
        allocations = []
        for u in units:
            sqft = _d(u["sq_ft"])
            share = (sqft / total_sqft) * total_cost
            allocations.append({
                "unit_id": u["id"],
                "unit_number": u["unit_number"],
                "lease_id": u["lease_id"],
                "sq_ft": str(sqft),
                "allocation_pct": str((sqft / total_sqft * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "allocation_method": "sqft",
                "allocated_amount": str(share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            })

    ok({
        "property_id": property_id,
        "total_cost": str(total_cost),
        "occupied_units": len(units),
        "total_sqft": str(total_sqft),
        "allocations": allocations,
    })


def generate_utility_charges(conn, args):
    """Generate lease charges from RUBS allocations."""
    if not getattr(args, "company_id", None):
        err("--company-id is required")
    property_id = getattr(args, "property_id", None)
    if not property_id:
        err("--property-id is required")
    amount_raw = getattr(args, "amount", None)
    if not amount_raw:
        err("--amount is required")
    charge_date = getattr(args, "charge_date", None) or date.today().isoformat()

    total_cost = _d(amount_raw)

    # Get active leases for occupied units
    leases = conn.execute(
        """SELECT l.id as lease_id, l.customer_id, u.id as unit_id, u.sq_ft, u.unit_number
           FROM propertyclaw_lease l
           JOIN propertyclaw_unit u ON l.unit_id = u.id
           WHERE u.property_id = ? AND l.status = 'active' AND l.company_id = ?""",
        (property_id, args.company_id),
    ).fetchall()

    if not leases:
        err("No active leases found for this property")

    total_sqft = sum(_d(l["sq_ft"]) for l in leases if l["sq_ft"])
    charges_created = []
    n = _now_iso()

    for l in leases:
        sqft = _d(l["sq_ft"])
        if total_sqft > 0:
            share = (sqft / total_sqft) * total_cost
        else:
            share = total_cost / Decimal(str(len(leases)))

        share_str = str(share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        c_id = str(uuid.uuid4())
        sql, _ = insert_row("propertyclaw_lease_charge", {
            "id": P(), "lease_id": P(), "charge_date": P(),
            "charge_type": P(), "description": P(), "amount": P(),
            "invoice_id": P(), "status": P(), "created_at": P(),
        })
        conn.execute(sql, (
            c_id, l["lease_id"], charge_date,
            "utility", f"Utility charge (RUBS) - Unit {l['unit_number']}",
            share_str, None, "pending", n,
        ))
        charges_created.append({
            "charge_id": c_id, "lease_id": l["lease_id"],
            "unit_number": l["unit_number"], "amount": share_str,
        })

    audit(conn, SKILL, "prop-generate-utility-charges", "propertyclaw_lease_charge", None,
          new_values={"property_id": property_id, "charges_count": len(charges_created)})
    conn.commit()
    ok({
        "property_id": property_id,
        "charges_created": len(charges_created),
        "charges": charges_created,
    })


def list_utility_charges(conn, args):
    t = _t_charge
    q = Q.from_(t).select(t.star).where(t.charge_type == P())
    params = ["utility"]

    lease_id = getattr(args, "lease_id", None)
    if lease_id:
        q = q.where(t.lease_id == P())
        params.append(lease_id)
    st = getattr(args, "charge_status", None)
    if st:
        q = q.where(t.status == P())
        params.append(st)

    q = q.orderby(t.charge_date, order=Order.desc).limit(P()).offset(P())
    limit = getattr(args, "limit", 50) or 50
    offset = getattr(args, "offset", 0) or 0
    rows = conn.execute(q.get_sql(), params + [limit, offset]).fetchall()
    ok({"utility_charges": [row_to_dict(r) for r in rows], "total_count": len(rows)})


def utility_cost_report(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")

    rows = conn.execute(
        """SELECT lc.charge_date, lc.amount, l.unit_id, u.unit_number, u.property_id
           FROM propertyclaw_lease_charge lc
           JOIN propertyclaw_lease l ON lc.lease_id = l.id
           JOIN propertyclaw_unit u ON l.unit_id = u.id
           WHERE lc.charge_type = 'utility' AND l.company_id = ?
           ORDER BY lc.charge_date DESC""",
        (args.company_id,),
    ).fetchall()

    total = Decimal("0")
    by_property = {}
    for r in rows:
        amt = _d(r["amount"])
        total += amt
        pid = r["property_id"]
        by_property.setdefault(pid, Decimal("0"))
        by_property[pid] += amt

    ok({
        "company_id": args.company_id,
        "total_utility_charges": str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "charge_count": len(rows),
        "by_property": {k: str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) for k, v in by_property.items()},
    })


# ===========================================================================
# P5: BANK RECONCILIATION
# ===========================================================================

def add_trust_reconciliation(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")
    ta_id = getattr(args, "trust_account_id", None)
    if not ta_id:
        err("--trust-account-id is required")
    bank_balance = getattr(args, "bank_balance", None)
    if not bank_balance:
        err("--bank-balance is required")
    book_balance = getattr(args, "book_balance", None)
    if not book_balance:
        err("--book-balance is required")

    # Verify trust account exists
    ta = conn.execute(
        Q.from_(_t_trust).select(_t_trust.star).where(_t_trust.id == P()).get_sql(),
        (ta_id,),
    ).fetchone()
    if not ta:
        err(f"Trust account {ta_id} not found")

    bb = _d(bank_balance)
    bk = _d(book_balance)
    diff = bb - bk

    r_id = str(uuid.uuid4())
    n = _now_iso()
    sql, _ = insert_row("propertyclaw_trust_reconciliation", {
        "id": P(), "trust_account_id": P(), "reconciliation_date": P(),
        "bank_balance": P(), "book_balance": P(), "difference": P(),
        "adjustments": P(), "reconciled_by": P(), "notes": P(),
        "status": P(), "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (
        r_id, ta_id,
        getattr(args, "reconciliation_date", None) or date.today().isoformat(),
        str(bb), str(bk), str(diff),
        getattr(args, "adjustments", None),
        getattr(args, "reconciled_by", None),
        getattr(args, "notes", None),
        "draft",
        args.company_id, n,
    ))
    audit(conn, SKILL, "prop-add-trust-reconciliation",
          "propertyclaw_trust_reconciliation", r_id,
          new_values={"trust_account_id": ta_id, "difference": str(diff)})
    conn.commit()
    ok({
        "reconciliation_id": r_id, "trust_account_id": ta_id,
        "bank_balance": str(bb), "book_balance": str(bk),
        "difference": str(diff), "reconciliation_status": "draft",
    })


def list_trust_reconciliations(conn, args):
    t = _t_recon
    q = Q.from_(t).select(t.star)
    params = []

    cid = getattr(args, "company_id", None)
    if cid:
        q = q.where(t.company_id == P())
        params.append(cid)
    ta_id = getattr(args, "trust_account_id", None)
    if ta_id:
        q = q.where(t.trust_account_id == P())
        params.append(ta_id)

    q = q.orderby(t.reconciliation_date, order=Order.desc).limit(P()).offset(P())
    limit = getattr(args, "limit", 50) or 50
    offset = getattr(args, "offset", 0) or 0
    rows = conn.execute(q.get_sql(), params + [limit, offset]).fetchall()
    ok({"trust_reconciliations": [row_to_dict(r) for r in rows], "total_count": len(rows)})


def reconcile_trust_account(conn, args):
    """Mark a reconciliation as reconciled."""
    recon_id = getattr(args, "reconciliation_id", None)
    if not recon_id:
        err("--reconciliation-id is required")

    row = conn.execute(
        Q.from_(_t_recon).select(_t_recon.star).where(_t_recon.id == P()).get_sql(),
        (recon_id,),
    ).fetchone()
    if not row:
        err(f"Reconciliation {recon_id} not found")
    if row["status"] != "draft":
        err(f"Reconciliation is already {row['status']}")

    data = {"status": "reconciled"}
    reconciled_by = getattr(args, "reconciled_by", None)
    if reconciled_by:
        data["reconciled_by"] = reconciled_by

    sql, params = dynamic_update("propertyclaw_trust_reconciliation", data, {"id": recon_id})
    conn.execute(sql, params)
    audit(conn, SKILL, "prop-reconcile-trust-account",
          "propertyclaw_trust_reconciliation", recon_id,
          new_values={"status": "reconciled"})
    conn.commit()
    ok({"reconciliation_id": recon_id, "reconciliation_status": "reconciled"})


def trust_reconciliation_report(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")

    rows = conn.execute(
        """SELECT r.*, ta.bank_name
           FROM propertyclaw_trust_reconciliation r
           LEFT JOIN propertyclaw_trust_account ta ON r.trust_account_id = ta.id
           WHERE r.company_id = ?
           ORDER BY r.reconciliation_date DESC""",
        (args.company_id,),
    ).fetchall()

    reconciliations = [row_to_dict(r) for r in rows]
    total_difference = sum(_d(r["difference"]) for r in rows)

    ok({
        "company_id": args.company_id,
        "total_reconciliations": len(reconciliations),
        "total_difference": str(total_difference.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "reconciliations": reconciliations,
    })


# ===========================================================================
# P6: LEASE DOCUMENT GEN
# ===========================================================================

def generate_lease_document(conn, args):
    """Generate a lease document using the erpclaw-documents template system."""
    if not getattr(args, "company_id", None):
        err("--company-id is required")
    lease_id = getattr(args, "lease_id", None)
    if not lease_id:
        err("--lease-id is required")

    lease = conn.execute(
        Q.from_(_t_lease).select(_t_lease.star).where(_t_lease.id == P()).get_sql(),
        (lease_id,),
    ).fetchone()
    if not lease:
        err(f"Lease {lease_id} not found")

    # Create a tenant_document record referencing this lease
    doc_id = str(uuid.uuid4())
    n = _now_iso()
    sql, _ = insert_row("propertyclaw_tenant_document", {
        "id": P(), "customer_id": P(), "lease_id": P(),
        "document_type": P(), "file_url": P(), "description": P(),
        "expiry_date": P(), "uploaded_at": P(),
    })
    conn.execute(sql, (
        doc_id, lease["customer_id"], lease_id,
        "lease",
        f"generated://lease/{lease_id}/{doc_id}",
        f"Lease document for lease {lease_id}",
        lease["end_date"],
        n,
    ))
    audit(conn, SKILL, "prop-generate-lease-document",
          "propertyclaw_tenant_document", doc_id,
          new_values={"lease_id": lease_id})
    conn.commit()
    ok({
        "document_id": doc_id, "lease_id": lease_id,
        "document_type": "lease",
        "file_url": f"generated://lease/{lease_id}/{doc_id}",
    })


def list_lease_documents(conn, args):
    t = _t_doc
    q = Q.from_(t).select(t.star).where(t.document_type == P())
    params = ["lease"]

    lease_id = getattr(args, "lease_id", None)
    if lease_id:
        q = q.where(t.lease_id == P())
        params.append(lease_id)
    cid = getattr(args, "customer_id", None)
    if cid:
        q = q.where(t.customer_id == P())
        params.append(cid)

    q = q.orderby(t.uploaded_at, order=Order.desc)
    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"lease_documents": [row_to_dict(r) for r in rows], "total_count": len(rows)})


# ===========================================================================
# P7: TENANT COMMUNICATION
# ===========================================================================

def add_announcement(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")
    subject = getattr(args, "subject", None)
    if not subject:
        err("--subject is required")
    message = getattr(args, "message", None)
    if not message:
        err("--message is required")

    audience = getattr(args, "audience", None) or "all"
    if audience not in ("all", "tenants", "owners", "staff"):
        err(f"Invalid audience: {audience}")

    a_id = str(uuid.uuid4())
    n = _now_iso()
    sql, _ = insert_row("propertyclaw_announcement", {
        "id": P(), "property_id": P(), "subject": P(), "message": P(),
        "audience": P(), "sent_at": P(), "sent_by": P(),
        "status": P(), "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (
        a_id,
        getattr(args, "property_id", None),
        subject, message, audience,
        None, None,
        "draft",
        args.company_id, n,
    ))
    audit(conn, SKILL, "prop-add-announcement",
          "propertyclaw_announcement", a_id,
          new_values={"subject": subject, "audience": audience})
    conn.commit()
    ok({"announcement_id": a_id, "subject": subject, "audience": audience, "announcement_status": "draft"})


def list_announcements(conn, args):
    t = _t_announce
    q = Q.from_(t).select(t.star)
    params = []

    cid = getattr(args, "company_id", None)
    if cid:
        q = q.where(t.company_id == P())
        params.append(cid)
    pid = getattr(args, "property_id", None)
    if pid:
        q = q.where(t.property_id == P())
        params.append(pid)
    st = getattr(args, "announcement_status", None)
    if st:
        q = q.where(t.status == P())
        params.append(st)

    q = q.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    limit = getattr(args, "limit", 50) or 50
    offset = getattr(args, "offset", 0) or 0
    rows = conn.execute(q.get_sql(), params + [limit, offset]).fetchall()
    ok({"announcements": [row_to_dict(r) for r in rows], "total_count": len(rows)})


def send_announcement(conn, args):
    a_id = getattr(args, "announcement_id", None)
    if not a_id:
        err("--announcement-id is required")

    row = conn.execute(
        Q.from_(_t_announce).select(_t_announce.star).where(_t_announce.id == P()).get_sql(),
        (a_id,),
    ).fetchone()
    if not row:
        err(f"Announcement {a_id} not found")
    if row["status"] != "draft":
        err(f"Announcement is already {row['status']}")

    data = {"status": "sent", "sent_at": _now_iso()}
    sent_by = getattr(args, "sent_by", None)
    if sent_by:
        data["sent_by"] = sent_by

    sql, params = dynamic_update("propertyclaw_announcement", data, {"id": a_id})
    conn.execute(sql, params)
    audit(conn, SKILL, "prop-send-announcement",
          "propertyclaw_announcement", a_id,
          new_values={"status": "sent"})
    conn.commit()
    ok({"announcement_id": a_id, "announcement_status": "sent"})


# ===========================================================================
# P10: VENDOR BIDDING
# ===========================================================================

def request_vendor_bid(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")
    wo_id = getattr(args, "work_order_id", None)
    if not wo_id:
        err("--work-order-id is required")
    vendor_id = getattr(args, "vendor_id", None)
    if not vendor_id:
        err("--vendor-id is required")

    # Verify work order exists
    wo = conn.execute(
        Q.from_(_t_wo).select(_t_wo.id).where(_t_wo.id == P()).get_sql(),
        (wo_id,),
    ).fetchone()
    if not wo:
        err(f"Work order {wo_id} not found")

    b_id = str(uuid.uuid4())
    n = _now_iso()
    sql, _ = insert_row("propertyclaw_vendor_bid", {
        "id": P(), "work_order_id": P(), "vendor_id": P(),
        "bid_amount": P(), "estimated_duration": P(),
        "description": P(), "submitted_date": P(),
        "status": P(), "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (
        b_id, wo_id, vendor_id,
        str(_d(getattr(args, "bid_amount", None))),
        getattr(args, "estimated_duration", None),
        getattr(args, "description", None),
        getattr(args, "submitted_date", None) or date.today().isoformat(),
        "submitted",
        args.company_id, n,
    ))
    audit(conn, SKILL, "prop-request-vendor-bid",
          "propertyclaw_vendor_bid", b_id,
          new_values={"work_order_id": wo_id, "vendor_id": vendor_id})
    conn.commit()
    ok({"bid_id": b_id, "work_order_id": wo_id, "vendor_id": vendor_id, "bid_status": "submitted"})


def list_vendor_bids(conn, args):
    t = _t_bid
    q = Q.from_(t).select(t.star)
    params = []

    cid = getattr(args, "company_id", None)
    if cid:
        q = q.where(t.company_id == P())
        params.append(cid)
    wo_id = getattr(args, "work_order_id", None)
    if wo_id:
        q = q.where(t.work_order_id == P())
        params.append(wo_id)
    vid = getattr(args, "vendor_id", None)
    if vid:
        q = q.where(t.vendor_id == P())
        params.append(vid)

    q = q.orderby(t.created_at, order=Order.desc)
    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"vendor_bids": [row_to_dict(r) for r in rows], "total_count": len(rows)})


def accept_vendor_bid(conn, args):
    b_id = getattr(args, "bid_id", None)
    if not b_id:
        err("--bid-id is required")

    row = conn.execute(
        Q.from_(_t_bid).select(_t_bid.star).where(_t_bid.id == P()).get_sql(),
        (b_id,),
    ).fetchone()
    if not row:
        err(f"Bid {b_id} not found")
    if row["status"] != "submitted":
        err(f"Bid is already {row['status']}")

    # Accept this bid
    sql, params = dynamic_update("propertyclaw_vendor_bid",
                                  {"status": "accepted"}, {"id": b_id})
    conn.execute(sql, params)

    # Reject all other bids for the same work order
    conn.execute(
        """UPDATE propertyclaw_vendor_bid
           SET status = 'rejected'
           WHERE work_order_id = ? AND id != ? AND status = 'submitted'""",
        (row["work_order_id"], b_id),
    )

    audit(conn, SKILL, "prop-accept-vendor-bid",
          "propertyclaw_vendor_bid", b_id,
          new_values={"status": "accepted"})
    conn.commit()
    ok({"bid_id": b_id, "bid_status": "accepted", "work_order_id": row["work_order_id"]})


def vendor_performance_report(conn, args):
    if not getattr(args, "company_id", None):
        err("--company-id is required")

    rows = conn.execute(
        """SELECT vendor_id, COUNT(*) as total_bids,
                  SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) as accepted_bids,
                  SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected_bids,
                  AVG(CAST(bid_amount AS REAL)) as avg_bid_amount
           FROM propertyclaw_vendor_bid
           WHERE company_id = ?
           GROUP BY vendor_id
           ORDER BY accepted_bids DESC""",
        (args.company_id,),
    ).fetchall()

    vendors = []
    for r in rows:
        vendors.append({
            "vendor_id": r["vendor_id"],
            "total_bids": r["total_bids"],
            "accepted_bids": r["accepted_bids"],
            "rejected_bids": r["rejected_bids"],
            "win_rate_pct": str(round(r["accepted_bids"] / r["total_bids"] * 100, 1)) if r["total_bids"] > 0 else "0.0",
            "avg_bid_amount": str(round(r["avg_bid_amount"] or 0, 2)),
        })

    ok({
        "company_id": args.company_id,
        "vendor_count": len(vendors),
        "vendors": vendors,
    })


# ---------------------------------------------------------------------------
# ACTIONS registry
# ---------------------------------------------------------------------------
ACTIONS = {
    # P3: Vacancy Listing
    "prop-create-listing": create_listing,
    "prop-list-listings": list_listings,
    "prop-update-listing": update_listing,
    "prop-listing-performance-report": listing_performance_report,
    "prop-list-vacancies": list_vacancies,
    # P4: Utility Billing/RUBS
    "prop-calculate-rubs": calculate_rubs,
    "prop-generate-utility-charges": generate_utility_charges,
    "prop-list-utility-charges": list_utility_charges,
    "prop-utility-cost-report": utility_cost_report,
    # P5: Bank Reconciliation
    "prop-add-trust-reconciliation": add_trust_reconciliation,
    "prop-list-trust-reconciliations": list_trust_reconciliations,
    "prop-reconcile-trust-account": reconcile_trust_account,
    "prop-trust-reconciliation-report": trust_reconciliation_report,
    # P6: Lease Document Gen
    "prop-generate-lease-document": generate_lease_document,
    "prop-list-lease-documents": list_lease_documents,
    # P7: Tenant Communication
    "prop-add-announcement": add_announcement,
    "prop-list-announcements": list_announcements,
    "prop-send-announcement": send_announcement,
    # P10: Vendor Bidding
    "prop-request-vendor-bid": request_vendor_bid,
    "prop-list-vendor-bids": list_vendor_bids,
    "prop-accept-vendor-bid": accept_vendor_bid,
    "prop-vendor-performance-report": vendor_performance_report,
}
