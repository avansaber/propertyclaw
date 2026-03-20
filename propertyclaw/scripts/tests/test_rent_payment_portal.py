"""L1 pytest tests for PropertyClaw rent payment and tenant portal modules.

Covers:
  - Payment methods: add, list, enable/disable autopay
  - Rent payments: process, generate receipt
  - Portal: my-lease, my-charges, my-payments, submit-maintenance-request,
    list-maintenance-requests, my-documents, update-contact-info, announcements
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from propertyclaw_helpers import (
    call_action, ns, is_ok, is_error, load_db_query,
    build_env, seed_customer, seed_supplier, seed_account,
    seed_naming_series, seed_company,
)

_mod = load_db_query()
ACTIONS = _mod.ACTIONS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_property_and_unit(conn, env):
    """Create a property and unit, return their IDs."""
    r = call_action(ACTIONS["prop-add-property"], conn, ns(
        company_id=env["company_id"], name="Payment Test Apartments",
        address_line1="100 Payment Ln", city="Austin", state="TX",
        zip_code="78701"))
    pid = r["property_id"]

    r2 = call_action(ACTIONS["prop-add-unit"], conn, ns(
        property_id=pid, unit_number="101", market_rent="1500"))
    uid = r2["unit_id"]
    return pid, uid


def _make_active_lease(conn, env):
    """Create a full property > unit > lease > activate, return IDs."""
    pid, uid = _make_property_and_unit(conn, env)

    r = call_action(ACTIONS["prop-add-lease"], conn, ns(
        company_id=env["company_id"], property_id=pid, unit_id=uid,
        customer_id=env["customer"], start_date="2026-01-01",
        end_date="2027-01-01", monthly_rent="1500"))
    lease_id = r["lease_id"]

    call_action(ACTIONS["prop-activate-lease"], conn, ns(lease_id=lease_id))

    return pid, uid, lease_id


# ── Rent Payment Tests ──────────────────────────────────────────────────────

class TestAddPaymentMethod:
    def test_add_payment_method_ach(self, conn, env):
        r = call_action(ACTIONS["prop-add-payment-method"], conn, ns(
            customer_id=env["customer"], company_id=env["company_id"],
            method_type="ach", last_four="4321", bank_name="Chase"))
        assert is_ok(r), r
        assert r["method_type"] == "ach"
        assert r["payment_method_id"]

    def test_add_payment_method_credit_card(self, conn, env):
        r = call_action(ACTIONS["prop-add-payment-method"], conn, ns(
            customer_id=env["customer"], company_id=env["company_id"],
            method_type="credit_card", last_four="9999"))
        assert is_ok(r)
        assert r["method_type"] == "credit_card"

    def test_add_payment_method_invalid_type(self, conn, env):
        r = call_action(ACTIONS["prop-add-payment-method"], conn, ns(
            customer_id=env["customer"], company_id=env["company_id"],
            method_type="bitcoin"))
        assert is_error(r)

    def test_add_payment_method_missing_customer(self, conn, env):
        r = call_action(ACTIONS["prop-add-payment-method"], conn, ns(
            company_id=env["company_id"], method_type="ach"))
        assert is_error(r)


class TestListPaymentMethods:
    def test_list_empty(self, conn, env):
        r = call_action(ACTIONS["prop-list-payment-methods"], conn, ns(
            customer_id=env["customer"], company_id=env["company_id"]))
        assert is_ok(r)
        assert r["count"] == 0

    def test_list_after_add(self, conn, env):
        call_action(ACTIONS["prop-add-payment-method"], conn, ns(
            customer_id=env["customer"], company_id=env["company_id"],
            method_type="ach"))
        r = call_action(ACTIONS["prop-list-payment-methods"], conn, ns(
            customer_id=env["customer"], company_id=env["company_id"]))
        assert is_ok(r)
        assert r["count"] == 1


class TestAutopay:
    def _create_pm(self, conn, env):
        r = call_action(ACTIONS["prop-add-payment-method"], conn, ns(
            customer_id=env["customer"], company_id=env["company_id"],
            method_type="ach"))
        return r["payment_method_id"]

    def test_enable_autopay(self, conn, env):
        pm_id = self._create_pm(conn, env)
        r = call_action(ACTIONS["prop-enable-autopay"], conn, ns(
            payment_method_id=pm_id, autopay_day="1"))
        assert is_ok(r), r
        assert r["autopay_enabled"] is True
        assert r["autopay_day"] == 1

    def test_enable_autopay_invalid_day(self, conn, env):
        pm_id = self._create_pm(conn, env)
        r = call_action(ACTIONS["prop-enable-autopay"], conn, ns(
            payment_method_id=pm_id, autopay_day="32"))
        assert is_error(r)

    def test_disable_autopay(self, conn, env):
        pm_id = self._create_pm(conn, env)
        call_action(ACTIONS["prop-enable-autopay"], conn, ns(
            payment_method_id=pm_id, autopay_day="15"))
        r = call_action(ACTIONS["prop-disable-autopay"], conn, ns(
            payment_method_id=pm_id))
        assert is_ok(r)
        assert r["autopay_enabled"] is False


class TestProcessRentPayment:
    def test_process_payment_ok(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        # Generate charges first
        call_action(ACTIONS["prop-generate-charges"], conn, ns(
            lease_id=lease_id, charge_date="2026-02-01"))

        r = call_action(ACTIONS["prop-process-rent-payment"], conn, ns(
            lease_id=lease_id, amount="1500"))
        assert is_ok(r), r
        assert r["amount"] == "1500.00"
        assert r["charges_paid_count"] >= 1

    def test_process_payment_inactive_lease(self, conn, env):
        pid, uid = _make_property_and_unit(conn, env)
        r = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=pid, unit_id=uid,
            customer_id=env["customer"], start_date="2026-01-01",
            monthly_rent="1500"))
        # Lease is still draft
        r2 = call_action(ACTIONS["prop-process-rent-payment"], conn, ns(
            lease_id=r["lease_id"], amount="1500"))
        assert is_error(r2)


class TestGeneratePaymentReceipt:
    def test_receipt_ok(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-generate-payment-receipt"], conn, ns(
            lease_id=lease_id, amount="1500"))
        assert is_ok(r), r
        assert r["receipt_number"].startswith("RCPT-")
        assert r["amount"] == "1500.00"
        assert r["tenant_name"]


# ── Portal Tests ─────────────────────────────────────────────────────────────

class TestPortalMyLease:
    def test_portal_my_lease(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-portal-my-lease"], conn, ns(
            customer_id=env["customer"], lease_id=lease_id))
        assert is_ok(r), r
        assert r["monthly_rent"] == "1500.00"
        assert r["property_name"] == "Payment Test Apartments"
        assert "rent_schedules" in r

    def test_portal_no_lease(self, conn, env):
        # A customer with no lease
        cust2 = seed_customer(conn, env["company_id"], "No Lease Tenant")
        r = call_action(ACTIONS["prop-portal-my-lease"], conn, ns(
            customer_id=cust2))
        assert is_error(r)


class TestPortalMyCharges:
    def test_portal_charges(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        call_action(ACTIONS["prop-generate-charges"], conn, ns(
            lease_id=lease_id, charge_date="2026-02-01"))

        r = call_action(ACTIONS["prop-portal-my-charges"], conn, ns(
            customer_id=env["customer"], lease_id=lease_id))
        assert is_ok(r), r
        assert r["total_count"] >= 1
        assert "pending_balance" in r


class TestPortalMyPayments:
    def test_portal_payments_empty(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-portal-my-payments"], conn, ns(
            customer_id=env["customer"], lease_id=lease_id))
        assert is_ok(r)
        assert r["total_count"] == 0


class TestPortalSubmitMaintenanceRequest:
    def test_submit_maintenance(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-portal-submit-maintenance-request"], conn, ns(
            customer_id=env["customer"], lease_id=lease_id,
            description="Faucet leaking in kitchen", category="plumbing",
            priority="routine", permission_to_enter="1"))
        assert is_ok(r), r
        assert r["wo_status"] == "open"
        assert r["work_order_id"]

    def test_submit_maintenance_missing_description(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-portal-submit-maintenance-request"], conn, ns(
            customer_id=env["customer"], lease_id=lease_id))
        assert is_error(r)


class TestPortalListMaintenanceRequests:
    def test_list_maintenance_empty(self, conn, env):
        pid, uid, lease_id = _make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-portal-list-maintenance-requests"], conn, ns(
            customer_id=env["customer"]))
        assert is_ok(r)


class TestPortalMyDocuments:
    def test_documents_empty(self, conn, env):
        r = call_action(ACTIONS["prop-portal-my-documents"], conn, ns(
            customer_id=env["customer"]))
        assert is_ok(r)
        assert r["total_count"] == 0


class TestPortalUpdateContactInfo:
    def test_update_contact(self, conn, env):
        r = call_action(ACTIONS["prop-portal-update-contact-info"], conn, ns(
            customer_id=env["customer"], applicant_email="newemail@test.com",
            applicant_phone="555-1234"))
        assert is_ok(r), r
        assert "primary_contact" in r["updated_fields"]
        assert "primary_address" in r["updated_fields"]

    def test_update_no_fields(self, conn, env):
        r = call_action(ACTIONS["prop-portal-update-contact-info"], conn, ns(
            customer_id=env["customer"]))
        assert is_error(r)


class TestPortalAnnouncements:
    def test_announcements_empty(self, conn, env):
        r = call_action(ACTIONS["prop-portal-announcements"], conn, ns(
            customer_id=env["customer"]))
        assert is_ok(r)
