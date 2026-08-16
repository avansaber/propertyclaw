#!/usr/bin/env python3
"""propertyclaw accounting domain module.

Trust accounting, owner statements, security deposits, and 1099 reporting.
Imported by the unified propertyclaw db_query.py router.
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, InvalidOperation

try:
    import importlib.util
    if importlib.util.find_spec("erpclaw_lib") is None:
        sys.path.insert(0, os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))
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

REQUIRED_TABLES = ["company", "account", "propertyclaw_property", "propertyclaw_lease",
                   "propertyclaw_trust_account", "propertyclaw_security_deposit"]
SKILL = "prop-propertyclaw-accounting"

# F19b: security-deposit GL posting. Deposits moved money but posted no GL
# anywhere. We post balanced pairs through the foundation helper. Guarded so a
# foundation without gl_posting still loads the module (records without GL).
try:
    from erpclaw_lib.gl_posting import insert_gl_entries
    HAS_GL = True
except ImportError:
    HAS_GL = False


# ---------------------------------------------------------------------------
# setup-trust-account
# ---------------------------------------------------------------------------
def setup_trust_account(conn, args):
    if not args.company_id:
        err("--company-id is required")
    if not args.property_id:
        err("--property-id is required")
    if not args.account_id:
        err("--account-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.company_id,)).fetchone():
        err(f"Company {args.company_id} not found")
    if not conn.execute(Q.from_(Table("propertyclaw_property")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.property_id,)).fetchone():
        err(f"Property {args.property_id} not found")

    acct = conn.execute(Q.from_(Table("account")).select(Field("id"), Field("account_type")).where(Field("id") == P()).get_sql(), (args.account_id,)).fetchone()
    if not acct:
        err(f"Account {args.account_id} not found")
    if acct["account_type"] != "trust":
        err(f"Account must be of type 'trust' (current: {acct['account_type']})")

    trust_id = str(uuid.uuid4())
    try:
        conn.execute(
            """INSERT INTO propertyclaw_trust_account
               (id, company_id, property_id, account_id, bank_name, status)
               VALUES (?,?,?,?,?,?)""",
            (trust_id, args.company_id, args.property_id, args.account_id,
             args.bank_name, "active"))
    except sqlite3.IntegrityError:
        err(f"Trust account already exists for this property")

    audit(conn, SKILL, "prop-setup-trust-account", "propertyclaw_trust_account", trust_id,
          new_values={"property_id": args.property_id, "account_id": args.account_id})
    conn.commit()
    ok({"trust_account_id": trust_id, "property_id": args.property_id,
        "account_id": args.account_id, "status": "active"})


# ---------------------------------------------------------------------------
# get-trust-account
# ---------------------------------------------------------------------------
def get_trust_account(conn, args):
    if not args.trust_account_id:
        err("--trust-account-id is required")

    row = conn.execute(
        """SELECT t.*, p.name as property_name, a.name as account_name
           FROM propertyclaw_trust_account t
           JOIN propertyclaw_property p ON t.property_id = p.id
           JOIN account a ON t.account_id = a.id
           WHERE t.id = ?""",
        (args.trust_account_id,)).fetchone()
    if not row:
        err(f"Trust account {args.trust_account_id} not found")

    data = row_to_dict(row)

    # Calculate trust balance from deposits held
    balance = conn.execute(
        """SELECT COALESCE(SUM(CAST(amount AS NUMERIC) - CAST(deduction_amount AS NUMERIC)), 0) as balance
           FROM propertyclaw_security_deposit
           WHERE trust_account_id = ? AND status = 'held'""",
        (args.trust_account_id,)).fetchone()
    data["deposits_held_balance"] = str(round_currency(to_decimal(str(balance["balance"]))))

    ok(data)


# ---------------------------------------------------------------------------
# list-trust-accounts
# ---------------------------------------------------------------------------
def list_trust_accounts(conn, args):
    # PyPika: skipped — dynamic WHERE with multi-table JOIN
    params = []; where = ["1=1"]
    if args.company_id:
        where.append("t.company_id = ?"); params.append(args.company_id)
    if args.property_id:
        where.append("t.property_id = ?"); params.append(args.property_id)

    wc = " AND ".join(where)
    rows = conn.execute(
        f"""SELECT t.*, p.name as property_name, a.name as account_name
            FROM propertyclaw_trust_account t
            JOIN propertyclaw_property p ON t.property_id = p.id
            JOIN account a ON t.account_id = a.id
            WHERE {wc} ORDER BY p.name""",
        params).fetchall()

    ok({"trust_accounts": [row_to_dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# generate-owner-statement
# ---------------------------------------------------------------------------
def generate_owner_statement(conn, args):
    if not args.company_id:
        err("--company-id is required")
    if not args.property_id:
        err("--property-id is required")
    if not args.period_start:
        err("--period-start is required")
    if not args.period_end:
        err("--period-end is required")

    prop = conn.execute(Q.from_(Table("propertyclaw_property")).select(Table("propertyclaw_property").star).where(Field("id") == P()).get_sql(), (args.property_id,)).fetchone()
    if not prop:
        err(f"Property {args.property_id} not found")

    # Calculate income from lease charges in period
    rent_income = conn.execute(
        """SELECT COALESCE(SUM(CAST(lc.amount AS NUMERIC)), 0) as total
           FROM propertyclaw_lease_charge lc
           JOIN propertyclaw_lease l ON lc.lease_id = l.id
           WHERE l.property_id = ? AND lc.charge_date >= ? AND lc.charge_date <= ?
                 AND lc.charge_type = 'base_rent'""",
        (args.property_id, args.period_start, args.period_end)).fetchone()

    other_income = conn.execute(
        """SELECT COALESCE(SUM(CAST(lc.amount AS NUMERIC)), 0) as total
           FROM propertyclaw_lease_charge lc
           JOIN propertyclaw_lease l ON lc.lease_id = l.id
           WHERE l.property_id = ? AND lc.charge_date >= ? AND lc.charge_date <= ?
                 AND lc.charge_type != 'base_rent'""",
        (args.property_id, args.period_start, args.period_end)).fetchone()

    # Calculate maintenance expenses in period
    maint_expense = conn.execute(
        """SELECT COALESCE(SUM(CAST(actual_cost AS NUMERIC)), 0) as total
           FROM propertyclaw_work_order
           WHERE property_id = ? AND status = 'completed'
                 AND completed_date >= ? AND completed_date <= ?""",
        (args.property_id, args.period_start, args.period_end)).fetchone()

    gross = round_currency(to_decimal(str(rent_income["total"])))
    other = round_currency(to_decimal(str(other_income["total"])))
    maint = round_currency(to_decimal(str(maint_expense["total"])))

    mgmt_fee_pct = to_decimal(prop["management_fee_pct"] or "0")
    mgmt_fee = round_currency(gross * mgmt_fee_pct / Decimal("100"))

    net = round_currency(gross + other - mgmt_fee - maint)

    stmt_id = str(uuid.uuid4())
    conn.company_id = args.company_id
    stmt_name = get_next_name(conn, "propertyclaw_owner_statement")

    conn.execute(
        """INSERT INTO propertyclaw_owner_statement
           (id, naming_series, company_id, property_id, owner_name,
            period_start, period_end, gross_rent, other_income,
            management_fee, maintenance_expense, other_expense,
            net_distribution, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (stmt_id, stmt_name, args.company_id, args.property_id,
         prop["owner_name"] or "Owner", args.period_start, args.period_end,
         str(gross), str(other), str(mgmt_fee), str(maint), "0",
         str(net), "draft"))

    audit(conn, SKILL, "prop-generate-owner-statement", "propertyclaw_owner_statement", stmt_id,
          new_values={"naming_series": stmt_name, "net": str(net)})
    conn.commit()
    ok({"statement_id": stmt_id, "naming_series": stmt_name,
        "gross_rent": str(gross), "other_income": str(other),
        "management_fee": str(mgmt_fee), "maintenance_expense": str(maint),
        "net_distribution": str(net), "status": "draft"})


# ---------------------------------------------------------------------------
# list-owner-statements
# ---------------------------------------------------------------------------
def list_owner_statements(conn, args):
    # PyPika: skipped — dynamic WHERE with multi-table JOIN
    params = []; where = ["1=1"]
    if args.company_id:
        where.append("s.company_id = ?"); params.append(args.company_id)
    if args.property_id:
        where.append("s.property_id = ?"); params.append(args.property_id)

    wc = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM propertyclaw_owner_statement s WHERE {wc}", params).fetchone()[0]

    limit = int(args.limit); offset = int(args.offset)
    rows = conn.execute(
        f"""SELECT s.*, p.name as property_name
            FROM propertyclaw_owner_statement s
            JOIN propertyclaw_property p ON s.property_id = p.id
            WHERE {wc} ORDER BY s.period_start DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall()

    ok({"statements": [row_to_dict(r) for r in rows], "total_count": total,
        "limit": limit, "offset": offset, "has_more": offset + limit < total})


# ---------------------------------------------------------------------------
# record-security-deposit
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# F19b — security-deposit GL helpers
# ---------------------------------------------------------------------------
def _company_of_lease(conn, lease_id):
    row = conn.execute(
        "SELECT company_id FROM propertyclaw_lease WHERE id = ?", (lease_id,)).fetchone()
    return row["company_id"] if row else None


def _account_root_type(conn, account_id):
    row = conn.execute(
        "SELECT root_type FROM account WHERE id = ?", (account_id,)).fetchone()
    return row["root_type"] if row else None


def _resolve_cash_account(conn, args, company_id, trust_account_id):
    """Asset side. Precedence: explicit arg > trust account's GL account >
    company default cash > company default bank."""
    acct = getattr(args, "cash_account_id", None)
    if not acct and trust_account_id:
        row = conn.execute(
            "SELECT account_id FROM propertyclaw_trust_account WHERE id = ?",
            (trust_account_id,)).fetchone()
        if row:
            acct = row["account_id"]
    if not acct:
        row = conn.execute(
            "SELECT default_cash_account_id, default_bank_account_id "
            "FROM company WHERE id = ?", (company_id,)).fetchone()
        if row:
            acct = row["default_cash_account_id"] or row["default_bank_account_id"]
    return acct


def _resolve_liability_account(conn, args, company_id):
    """Security-deposit liability side. No safe seeded default (the CoA's
    'Security Deposits' is an ASSET — deposits *paid*), so this must be supplied.
    Resolves --deposit-liability-account-id and validates it is a liability."""
    acct = getattr(args, "deposit_liability_account_id", None)
    if not acct:
        return None
    if _account_root_type(conn, acct) != "liability":
        err("--deposit-liability-account-id must reference a liability account "
            f"(account {acct} is not root_type='liability')")
    return acct


def _resolve_income_account(conn, args, company_id):
    """Income side for retained/forfeited amounts. Precedence: explicit arg >
    company default income."""
    acct = getattr(args, "income_account_id", None)
    if not acct:
        row = conn.execute(
            "SELECT default_income_account_id FROM company WHERE id = ?",
            (company_id,)).fetchone()
        if row:
            acct = row["default_income_account_id"]
    return acct


def _resolve_cost_center(conn, args, company_id):
    """Cost center for the income leg (GL validation requires one on P&L
    accounts). Precedence: explicit arg > company default cost center."""
    cc = getattr(args, "cost_center_id", None)
    if not cc:
        row = conn.execute(
            "SELECT default_cost_center_id FROM company WHERE id = ?",
            (company_id,)).fetchone()
        if row:
            cc = row["default_cost_center_id"]
    return cc


def _post_deposit_pair(conn, company_id, debit_account_id, credit_account_id,
                       amount, voucher_id, entry_set, posting_date, remarks,
                       cost_center_id=None):
    """Post one balanced GL pair through the foundation helper and return the
    debit-leg gl_entry id. `amount` is a Decimal already rounded to currency.
    A cost_center_id is attached to any income/expense leg (GL validation step 6
    requires it on P&L accounts). No-ops when the foundation lacks gl_posting."""
    if not HAS_GL:
        return None

    def _leg(acct, debit, credit):
        e = {"account_id": acct, "debit": debit, "credit": credit}
        if cost_center_id and _account_root_type(conn, acct) in ("income", "expense"):
            e["cost_center_id"] = cost_center_id
        return e

    entries = [
        _leg(debit_account_id, str(amount), "0"),
        _leg(credit_account_id, "0", str(amount)),
    ]
    gl_ids = insert_gl_entries(
        conn, entries,
        voucher_type="journal_entry",
        voucher_id=voucher_id,
        posting_date=posting_date,
        company_id=company_id,
        remarks=remarks,
        entry_set=entry_set,
    )
    return gl_ids[0] if gl_ids else None


def record_security_deposit(conn, args):
    if not args.lease_id:
        err("--lease-id is required")
    if not args.amount:
        err("--amount is required")
    if not args.deposit_date:
        err("--deposit-date is required")

    lease = conn.execute(Q.from_(Table("propertyclaw_lease")).select(Table("propertyclaw_lease").star).where(Field("id") == P()).get_sql(), (args.lease_id,)).fetchone()
    if not lease:
        err(f"Lease {args.lease_id} not found")

    amount = str(round_currency(to_decimal(args.amount)))

    # Find trust account for property
    trust_account_id = args.trust_account_id
    if not trust_account_id:
        trust = conn.execute(
            "SELECT id FROM propertyclaw_trust_account WHERE property_id = ? AND status = 'active'",
            (lease["property_id"],)).fetchone()
        if trust:
            trust_account_id = trust["id"]

    # Get state for return deadline calculation
    prop = conn.execute(Q.from_(Table("propertyclaw_property")).select(Field("state")).where(Field("id") == P()).get_sql(), (lease["property_id"],)).fetchone()
    state = prop["state"] if prop else None

    # State-specific return deadlines (days after move-out)
    state_deadlines = {
        "CA": 21, "NY": 14, "TX": 30, "FL": 15, "IL": 30,
        "PA": 30, "OH": 30, "GA": 30, "NC": 30, "MI": 30,
    }
    deadline_days = state_deadlines.get(state, 30)

    deposit_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO propertyclaw_security_deposit
           (id, lease_id, customer_id, amount, deposit_date, trust_account_id,
            interest_rate, interest_accrued, return_deadline, status)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (deposit_id, args.lease_id, lease["customer_id"], amount,
         args.deposit_date, trust_account_id, args.interest_rate, "0",
         None, "held"))

    # F19b: post the receipt GL — Dr Cash / Cr Security-Deposit Liability.
    # Money was moving with no GL anywhere; now a balanced pair is posted and
    # the previously-dead gl_entry_id column is wired.
    company_id = lease["company_id"]
    gl_entry_id = None
    if HAS_GL:
        cash_acct = _resolve_cash_account(conn, args, company_id, trust_account_id)
        liab_acct = _resolve_liability_account(conn, args, company_id)
        if cash_acct and liab_acct:
            gl_entry_id = _post_deposit_pair(
                conn, company_id, cash_acct, liab_acct, to_decimal(amount),
                deposit_id, "deposit_receipt", args.deposit_date,
                f"Security deposit received (lease {args.lease_id})")
            conn.execute(
                update_row("propertyclaw_security_deposit",
                           data={"gl_entry_id": P(), "updated_at": now()},
                           where={"id": P()}),
                (gl_entry_id, deposit_id))
        else:
            sys.stderr.write(
                f"[{SKILL}] deposit receipt GL skipped: cash/liability account "
                f"unresolved; pass --cash-account-id / "
                f"--deposit-liability-account-id or configure trust/company "
                f"defaults\n")

    audit(conn, SKILL, "prop-record-security-deposit", "propertyclaw_security_deposit", deposit_id,
          new_values={"amount": amount, "lease_id": args.lease_id})
    conn.commit()
    ok({"security_deposit_id": deposit_id, "amount": amount,
        "trust_account_id": trust_account_id, "return_deadline_days": deadline_days,
        "gl_entry_id": gl_entry_id, "status": "held"})


# ---------------------------------------------------------------------------
# return-security-deposit
# ---------------------------------------------------------------------------
def return_security_deposit(conn, args):
    if not args.security_deposit_id:
        err("--security-deposit-id is required")
    if not args.return_amount:
        err("--return-amount is required")

    deposit = conn.execute(Q.from_(Table("propertyclaw_security_deposit")).select(Table("propertyclaw_security_deposit").star).where(Field("id") == P()).get_sql(), (args.security_deposit_id,)).fetchone()
    if not deposit:
        err(f"Security deposit {args.security_deposit_id} not found")
    if deposit["status"] not in ("held", "partially_returned"):
        err(f"Deposit must be 'held' or 'partially_returned' (current: {deposit['status']})")

    return_amount = round_currency(to_decimal(args.return_amount))
    deposit_amount = to_decimal(deposit["amount"])
    deduction_total = to_decimal(deposit["deduction_amount"])

    if return_amount > deposit_amount - deduction_total:
        err(f"Return amount ({return_amount}) exceeds available balance ({deposit_amount - deduction_total})")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_status = "returned" if return_amount + deduction_total >= deposit_amount else "partially_returned"

    conn.execute(
        update_row("propertyclaw_security_deposit",
                   data={"return_amount": P(), "return_date": P(), "status": P(),
                         "updated_at": now()},
                   where={"id": P()}),
        (str(return_amount), today, new_status, args.security_deposit_id))

    # F19b: post the return GL — Dr Security-Deposit Liability / Cr Cash. This
    # reverses the receipt liability for the returned portion; combined with the
    # deduction postings, a fully-settled deposit nets the liability to zero.
    gl_entry_id = None
    if HAS_GL and return_amount > to_decimal("0"):
        company_id = _company_of_lease(conn, deposit["lease_id"])
        cash_acct = _resolve_cash_account(conn, args, company_id, deposit["trust_account_id"])
        liab_acct = _resolve_liability_account(conn, args, company_id)
        if cash_acct and liab_acct:
            gl_entry_id = _post_deposit_pair(
                conn, company_id, liab_acct, cash_acct, return_amount,
                args.security_deposit_id, "deposit_return", today,
                "Security deposit returned")
        else:
            sys.stderr.write(
                f"[{SKILL}] deposit return GL skipped: cash/liability account "
                f"unresolved\n")

    audit(conn, SKILL, "prop-return-security-deposit", "propertyclaw_security_deposit",
          args.security_deposit_id,
          new_values={"return_amount": str(return_amount), "status": new_status})
    conn.commit()
    ok({"security_deposit_id": args.security_deposit_id,
        "return_amount": str(return_amount), "return_date": today,
        "gl_entry_id": gl_entry_id, "status": new_status})


# ---------------------------------------------------------------------------
# add-deposit-deduction
# ---------------------------------------------------------------------------
def add_deposit_deduction(conn, args):
    if not args.security_deposit_id:
        err("--security-deposit-id is required")
    if not args.deduction_type:
        err("--deduction-type is required")
    if not args.deduction_description:
        err("--deduction-description is required")
    if not args.amount:
        err("--amount is required")

    valid_types = ("damages", "unpaid_rent", "cleaning", "other")
    if args.deduction_type not in valid_types:
        err(f"--deduction-type must be one of: {', '.join(valid_types)}")

    deposit = conn.execute(Q.from_(Table("propertyclaw_security_deposit")).select(Table("propertyclaw_security_deposit").star).where(Field("id") == P()).get_sql(), (args.security_deposit_id,)).fetchone()
    if not deposit:
        err(f"Security deposit {args.security_deposit_id} not found")

    amount = round_currency(to_decimal(args.amount))
    current_deductions = to_decimal(deposit["deduction_amount"])
    deposit_amount = to_decimal(deposit["amount"])

    if current_deductions + amount > deposit_amount:
        err(f"Total deductions ({current_deductions + amount}) would exceed deposit ({deposit_amount})")

    deduction_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO propertyclaw_deposit_deduction
           (id, security_deposit_id, deduction_type, description, amount,
            invoice_url, receipt_url)
           VALUES (?,?,?,?,?,?,?)""",
        (deduction_id, args.security_deposit_id, args.deduction_type,
         args.deduction_description, str(amount), args.invoice_url, args.receipt_url))

    # Update total deductions on deposit
    new_total = str(round_currency(current_deductions + amount))
    conn.execute(
        update_row("propertyclaw_security_deposit",
                   data={"deduction_amount": P(), "updated_at": now()},
                   where={"id": P()}),
        (new_total, args.security_deposit_id))

    # F19b: a deduction is a partial forfeiture — the landlord retains part of
    # the deposit. Post Dr Security-Deposit Liability / Cr Other Income so the
    # liability is drawn down and the retained amount is recognized as income.
    gl_entry_id = None
    if HAS_GL:
        company_id = _company_of_lease(conn, deposit["lease_id"])
        liab_acct = _resolve_liability_account(conn, args, company_id)
        income_acct = _resolve_income_account(conn, args, company_id)
        cost_center = _resolve_cost_center(conn, args, company_id)
        if liab_acct and income_acct and cost_center:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            gl_entry_id = _post_deposit_pair(
                conn, company_id, liab_acct, income_acct, amount,
                args.security_deposit_id, f"deposit_deduction:{deduction_id}", today,
                f"Security-deposit deduction ({args.deduction_type})",
                cost_center_id=cost_center)
        else:
            sys.stderr.write(
                f"[{SKILL}] deposit deduction GL skipped: liability/income "
                f"account or cost center unresolved\n")

    conn.commit()
    ok({"deduction_id": deduction_id, "amount": str(amount),
        "total_deductions": new_total, "gl_entry_id": gl_entry_id})


# ---------------------------------------------------------------------------
# list-deposit-deductions
# ---------------------------------------------------------------------------
def list_deposit_deductions(conn, args):
    _tdd = Table("propertyclaw_deposit_deduction")
    if args.security_deposit_id:
        rows = conn.execute(
            Q.from_(_tdd).select(_tdd.star).where(_tdd.security_deposit_id == P())
            .orderby(_tdd.created_at).get_sql(),
            (args.security_deposit_id,)).fetchall()
    else:
        rows = conn.execute(
            Q.from_(_tdd).select(_tdd.star).orderby(_tdd.created_at, order=Order.desc).get_sql()).fetchall()

    total = sum(to_decimal(r["amount"]) for r in rows)
    ok({"deductions": [row_to_dict(r) for r in rows], "count": len(rows),
        "total_deductions": str(round_currency(total))})


# ---------------------------------------------------------------------------
# generate-1099-report
# ---------------------------------------------------------------------------
def generate_1099_report(conn, args):
    if not args.company_id:
        err("--company-id is required")
    if not args.tax_year:
        err("--tax-year is required")

    tax_year = int(args.tax_year)

    # PyPika: skipped — complex aggregate JOIN with HAVING and dynamic WHERE
    # Calculate vendor payments from completed work orders
    query = """
        SELECT s.id as supplier_id, s.name as vendor_name, s.tax_id,
               COALESCE(SUM(CAST(w.actual_cost AS NUMERIC)), 0) as total_paid
        FROM supplier s
        JOIN propertyclaw_work_order w ON w.supplier_id = s.id
        WHERE w.company_id = ? AND w.status = 'completed'
              AND w.completed_date >= ? AND w.completed_date < ?
    """
    params = [args.company_id, f"{tax_year}-01-01", f"{tax_year + 1}-01-01"]

    if args.supplier_id:
        query += " AND s.id = ?"
        params.append(args.supplier_id)

    query += " GROUP BY s.id, s.name, s.tax_id HAVING total_paid > 0"
    vendors = conn.execute(query, params).fetchall()

    results = []
    for v in vendors:
        total = round_currency(to_decimal(str(v["total_paid"])))
        needs_1099 = total >= Decimal("600")

        # Upsert 1099 tracking record
        existing = conn.execute(
            "SELECT id FROM propertyclaw_tax_1099 WHERE company_id = ? AND supplier_id = ? AND tax_year = ?",
            (args.company_id, v["supplier_id"], tax_year)).fetchone()

        if existing:
            sql, params_u = dynamic_update("propertyclaw_tax_1099",
                {"total_payments": str(total), "updated_at": now()},
                where={"id": existing["id"]})
            conn.execute(sql, params_u)
            record_id = existing["id"]
        else:
            record_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO propertyclaw_tax_1099
                   (id, company_id, supplier_id, tax_year, total_payments,
                    form_type, filing_status, w9_on_file)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (record_id, args.company_id, v["supplier_id"], tax_year,
                 str(total), "1099_nec", "pending", 0))

        results.append({
            "supplier_id": v["supplier_id"],
            "vendor_name": v["vendor_name"],
            "total_payments": str(total),
            "needs_1099": needs_1099,
            "tracking_id": record_id,
        })

    conn.commit()
    ok({"tax_year": tax_year, "vendors": results, "count": len(results),
        "vendors_needing_1099": sum(1 for r in results if r["needs_1099"])})


# ---------------------------------------------------------------------------
# forfeit-security-deposit  (F19b — makes the 'forfeited' status reachable)
# ---------------------------------------------------------------------------
def forfeit_security_deposit(conn, args):
    if not args.security_deposit_id:
        err("--security-deposit-id is required")

    deposit = conn.execute(Q.from_(Table("propertyclaw_security_deposit")).select(Table("propertyclaw_security_deposit").star).where(Field("id") == P()).get_sql(), (args.security_deposit_id,)).fetchone()
    if not deposit:
        err(f"Security deposit {args.security_deposit_id} not found")
    if deposit["status"] not in ("held", "partially_returned"):
        err(f"Deposit must be 'held' or 'partially_returned' to forfeit "
            f"(current: {deposit['status']})")

    deposit_amount = to_decimal(deposit["amount"])
    deduction_total = to_decimal(deposit["deduction_amount"])
    returned = to_decimal(deposit["return_amount"]) if deposit["return_amount"] else Decimal("0")
    remaining = round_currency(deposit_amount - deduction_total - returned)
    if remaining <= Decimal("0"):
        err(f"No remaining balance to forfeit (amount {deposit_amount}, "
            f"deductions {deduction_total}, returned {returned})")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute(
        update_row("propertyclaw_security_deposit",
                   data={"status": P(), "updated_at": now()},
                   where={"id": P()}),
        ("forfeited", args.security_deposit_id))

    # F19b: forfeiture GL — Dr Security-Deposit Liability / Cr Other Income for
    # the remaining balance. Draws the liability to zero and recognizes income.
    gl_entry_id = None
    if HAS_GL:
        company_id = _company_of_lease(conn, deposit["lease_id"])
        liab_acct = _resolve_liability_account(conn, args, company_id)
        income_acct = _resolve_income_account(conn, args, company_id)
        cost_center = _resolve_cost_center(conn, args, company_id)
        if liab_acct and income_acct and cost_center:
            gl_entry_id = _post_deposit_pair(
                conn, company_id, liab_acct, income_acct, remaining,
                args.security_deposit_id, "deposit_forfeit", today,
                "Security deposit forfeited", cost_center_id=cost_center)
        else:
            sys.stderr.write(
                f"[{SKILL}] deposit forfeit GL skipped: liability/income "
                f"account or cost center unresolved\n")

    audit(conn, SKILL, "prop-forfeit-security-deposit", "propertyclaw_security_deposit",
          args.security_deposit_id,
          new_values={"forfeited_amount": str(remaining), "status": "forfeited"})
    conn.commit()
    ok({"security_deposit_id": args.security_deposit_id,
        "forfeited_amount": str(remaining), "gl_entry_id": gl_entry_id,
        "status": "forfeited"})


# ---------------------------------------------------------------------------
# Action Router
# ---------------------------------------------------------------------------
ACTIONS = {
    "prop-setup-trust-account": setup_trust_account,
    "prop-get-trust-account": get_trust_account,
    "prop-list-trust-accounts": list_trust_accounts,
    "prop-generate-owner-statement": generate_owner_statement,
    "prop-list-owner-statements": list_owner_statements,
    "prop-record-security-deposit": record_security_deposit,
    "prop-return-security-deposit": return_security_deposit,
    "prop-add-deposit-deduction": add_deposit_deduction,
    "prop-forfeit-security-deposit": forfeit_security_deposit,
    "prop-list-deposit-deductions": list_deposit_deductions,
    "prop-generate-1099-report": generate_1099_report,
}
