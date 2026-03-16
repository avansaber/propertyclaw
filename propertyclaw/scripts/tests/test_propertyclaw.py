"""L1 pytest tests for PropertyClaw core module.

Covers: properties, units, amenities, photos, leases, rent schedules,
charges, late fees, renewals, tenants/applications, screenings, documents,
work orders, vendor assignments, inspections, accounting (trust, deposits, 1099).
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


# ── Properties ────────────────────────────────────────────────────────────────

class TestProperties:
    def test_add_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Sunset Apartments",
            address_line1="123 Main St", city="Austin", state="TX",
            zip_code="78701"))
        assert is_ok(r)
        assert r["property_id"]
        assert r["naming_series"].startswith("PROP-")

    def test_add_property_missing_name(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"],
            address_line1="123 Main St", city="Austin", state="TX",
            zip_code="78701"))
        assert is_error(r)

    def test_get_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Oak Ridge",
            address_line1="456 Oak Ln", city="Dallas", state="TX",
            zip_code="75001"))
        assert is_ok(r)
        pid = r["property_id"]

        r2 = call_action(ACTIONS["prop-get-property"], conn, ns(property_id=pid))
        assert is_ok(r2)
        assert r2["name"] == "Oak Ridge"
        assert r2["unit_count"] == 0

    def test_update_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Pine Creek",
            address_line1="789 Pine Ave", city="Houston", state="TX",
            zip_code="77001"))
        assert is_ok(r)
        pid = r["property_id"]

        r2 = call_action(ACTIONS["prop-update-property"], conn, ns(
            property_id=pid, name="Pine Creek Updated"))
        assert is_ok(r2)
        assert "name" in r2["updated_fields"]

    def test_list_properties(self, conn, env):
        call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="ListA",
            address_line1="1 A St", city="Austin", state="TX",
            zip_code="78701"))
        call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="ListB",
            address_line1="2 B St", city="Dallas", state="TX",
            zip_code="75001"))

        r = call_action(ACTIONS["prop-list-properties"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 2


# ── Units ─────────────────────────────────────────────────────────────────────

class TestUnits:
    def _make_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Unit Test Prop",
            address_line1="100 Test Rd", city="Austin", state="TX",
            zip_code="78701"))
        return r["property_id"]

    def test_add_unit(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="101", unit_type="apartment",
            bedrooms="2", bathrooms="1.5", sq_ft="900", market_rent="1500"))
        assert is_ok(r)
        assert r["unit_number"] == "101"

    def test_get_unit(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="201", market_rent="1200"))
        uid = r["unit_id"]

        r2 = call_action(ACTIONS["prop-get-unit"], conn, ns(unit_id=uid))
        assert is_ok(r2)
        assert r2["market_rent"] == "1200.00"

    def test_update_unit(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="301"))
        uid = r["unit_id"]

        r2 = call_action(ACTIONS["prop-update-unit"], conn, ns(
            unit_id=uid, market_rent="1750"))
        assert is_ok(r2)
        assert "market_rent" in r2["updated_fields"]

    def test_list_units(self, conn, env):
        pid = self._make_property(conn, env)
        call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="A1"))
        call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="A2"))

        r = call_action(ACTIONS["prop-list-units"], conn, ns(property_id=pid))
        assert is_ok(r)
        assert r["total_count"] == 2

    def test_duplicate_unit_number(self, conn, env):
        pid = self._make_property(conn, env)
        call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="DUP1"))
        r = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="DUP1"))
        assert is_error(r)


# ── Amenities & Photos ────────────────────────────────────────────────────────

class TestAmenitiesPhotos:
    def _make_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Amenity Prop",
            address_line1="5 Test", city="Austin", state="TX",
            zip_code="78701"))
        return r["property_id"]

    def test_add_and_list_amenity(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-amenity"], conn, ns(
            property_id=pid, amenity_name="Pool"))
        assert is_ok(r)
        assert r["scope"] == "property"

        r2 = call_action(ACTIONS["prop-list-amenities"], conn, ns(property_id=pid))
        assert is_ok(r2)
        assert r2["count"] == 1

    def test_delete_amenity(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-amenity"], conn, ns(
            property_id=pid, amenity_name="Gym"))
        aid = r["amenity_id"]

        r2 = call_action(ACTIONS["prop-delete-amenity"], conn, ns(amenity_id=aid))
        assert is_ok(r2)

    def test_add_and_list_photo(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-photo"], conn, ns(
            property_id=pid, file_url="https://example.com/photo.jpg"))
        assert is_ok(r)

        r2 = call_action(ACTIONS["prop-list-photos"], conn, ns(property_id=pid))
        assert is_ok(r2)
        assert r2["count"] == 1

    def test_delete_photo(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-photo"], conn, ns(
            property_id=pid, file_url="https://example.com/del.jpg"))
        photo_id = r["photo_id"]

        r2 = call_action(ACTIONS["prop-delete-photo"], conn, ns(photo_id=photo_id))
        assert is_ok(r2)


# ── Leases ────────────────────────────────────────────────────────────────────

class TestLeases:
    def _make_lease_env(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Lease Prop",
            address_line1="10 Lease Rd", city="Austin", state="TX",
            zip_code="78701"))
        pid = r["property_id"]
        r2 = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="L1", market_rent="1500"))
        uid = r2["unit_id"]
        return {"property_id": pid, "unit_id": uid}

    def test_add_lease(self, conn, env):
        le = self._make_lease_env(conn, env)
        r = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=le["property_id"],
            unit_id=le["unit_id"], customer_id=env["customer"],
            start_date="2026-01-01", end_date="2027-01-01",
            monthly_rent="1500"))
        assert is_ok(r)
        # ok() overwrites "status" to "ok"; verify domain status via DB
        row = conn.execute("SELECT status FROM propertyclaw_lease WHERE id = ?",
                           (r["lease_id"],)).fetchone()
        assert row["status"] == "draft"

    def test_activate_lease(self, conn, env):
        le = self._make_lease_env(conn, env)
        r = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=le["property_id"],
            unit_id=le["unit_id"], customer_id=env["customer"],
            start_date="2026-01-01", end_date="2027-01-01",
            monthly_rent="2000"))
        lid = r["lease_id"]

        r2 = call_action(ACTIONS["prop-activate-lease"], conn, ns(lease_id=lid))
        assert is_ok(r2)
        row = conn.execute("SELECT status FROM propertyclaw_lease WHERE id = ?",
                           (lid,)).fetchone()
        assert row["status"] == "active"

        # Unit should now be occupied
        unit = conn.execute("SELECT status FROM propertyclaw_unit WHERE id = ?",
                            (le["unit_id"],)).fetchone()
        assert unit["status"] == "occupied"

    def test_terminate_lease(self, conn, env):
        le = self._make_lease_env(conn, env)
        r = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=le["property_id"],
            unit_id=le["unit_id"], customer_id=env["customer"],
            start_date="2026-01-01", monthly_rent="1500"))
        lid = r["lease_id"]
        call_action(ACTIONS["prop-activate-lease"], conn, ns(lease_id=lid))

        r2 = call_action(ACTIONS["prop-terminate-lease"], conn, ns(
            lease_id=lid, move_out_date="2026-06-30"))
        assert is_ok(r2)
        row = conn.execute("SELECT status FROM propertyclaw_lease WHERE id = ?",
                           (lid,)).fetchone()
        assert row["status"] == "terminated"

    def test_get_lease(self, conn, env):
        le = self._make_lease_env(conn, env)
        r = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=le["property_id"],
            unit_id=le["unit_id"], customer_id=env["customer"],
            start_date="2026-01-01", monthly_rent="1800"))
        lid = r["lease_id"]

        r2 = call_action(ACTIONS["prop-get-lease"], conn, ns(lease_id=lid))
        assert is_ok(r2)
        assert r2["monthly_rent"] == "1800.00"

    def test_list_leases(self, conn, env):
        le = self._make_lease_env(conn, env)
        call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=le["property_id"],
            unit_id=le["unit_id"], customer_id=env["customer"],
            start_date="2026-01-01", monthly_rent="1000"))

        r = call_action(ACTIONS["prop-list-leases"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 1

    def test_update_lease(self, conn, env):
        le = self._make_lease_env(conn, env)
        r = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=le["property_id"],
            unit_id=le["unit_id"], customer_id=env["customer"],
            start_date="2026-01-01", monthly_rent="1500"))
        lid = r["lease_id"]

        r2 = call_action(ACTIONS["prop-update-lease"], conn, ns(
            lease_id=lid, monthly_rent="1600"))
        assert is_ok(r2)
        assert "monthly_rent" in r2["updated_fields"]


# ── Rent Schedules & Charges ──────────────────────────────────────────────────

class TestRentCharges:
    def _make_active_lease(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Charges Prop",
            address_line1="20 Charge Rd", city="Austin", state="TX",
            zip_code="78701"))
        pid = r["property_id"]
        r2 = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="C1"))
        uid = r2["unit_id"]
        r3 = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            unit_id=uid, customer_id=env["customer"],
            start_date="2026-01-01", end_date="2027-01-01",
            monthly_rent="1500"))
        lid = r3["lease_id"]
        call_action(ACTIONS["prop-activate-lease"], conn, ns(lease_id=lid))
        return lid

    def test_add_rent_schedule(self, conn, env):
        lid = self._make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-add-rent-schedule"], conn, ns(
            lease_id=lid, charge_type="pet_rent", amount="50",
            start_date="2026-01-01"))
        assert is_ok(r)
        assert r["amount"] == "50.00"

    def test_list_rent_schedules(self, conn, env):
        lid = self._make_active_lease(conn, env)
        # base_rent auto-created, add pet_rent
        call_action(ACTIONS["prop-add-rent-schedule"], conn, ns(
            lease_id=lid, charge_type="pet_rent", amount="50",
            start_date="2026-01-01"))

        r = call_action(ACTIONS["prop-list-rent-schedules"], conn, ns(lease_id=lid))
        assert is_ok(r)
        assert r["count"] >= 2

    def test_delete_rent_schedule(self, conn, env):
        lid = self._make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-add-rent-schedule"], conn, ns(
            lease_id=lid, charge_type="parking", amount="100",
            start_date="2026-01-01"))
        sid = r["rent_schedule_id"]

        r2 = call_action(ACTIONS["prop-delete-rent-schedule"], conn, ns(
            rent_schedule_id=sid))
        assert is_ok(r2)

    def test_generate_charges(self, conn, env):
        lid = self._make_active_lease(conn, env)
        r = call_action(ACTIONS["prop-generate-charges"], conn, ns(
            lease_id=lid, charge_date="2026-02-01"))
        assert is_ok(r)
        assert r["charges_created"] >= 1

    def test_list_charges(self, conn, env):
        lid = self._make_active_lease(conn, env)
        call_action(ACTIONS["prop-generate-charges"], conn, ns(
            lease_id=lid, charge_date="2026-02-01"))
        r = call_action(ACTIONS["prop-list-charges"], conn, ns(lease_id=lid))
        assert is_ok(r)
        assert r["total_count"] >= 1


# ── Late Fees ─────────────────────────────────────────────────────────────────

class TestLateFees:
    def test_add_late_fee_rule(self, conn, env):
        r = call_action(ACTIONS["prop-add-late-fee-rule"], conn, ns(
            company_id=env["company_id"], state="TX", fee_type="flat",
            flat_amount="50", grace_days="5"))
        assert is_ok(r)
        assert r["state"] == "TX"

    def test_list_late_fee_rules(self, conn, env):
        call_action(ACTIONS["prop-add-late-fee-rule"], conn, ns(
            company_id=env["company_id"], state="CA", fee_type="percentage",
            percentage_rate="5", grace_days="3"))
        r = call_action(ACTIONS["prop-list-late-fee-rules"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["count"] >= 1


# ── Renewals ──────────────────────────────────────────────────────────────────

class TestRenewals:
    def _make_lease(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Renewal Prop",
            address_line1="30 Renew Rd", city="Austin", state="TX",
            zip_code="78701"))
        pid = r["property_id"]
        r2 = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="R1"))
        uid = r2["unit_id"]
        r3 = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            unit_id=uid, customer_id=env["customer"],
            start_date="2026-01-01", end_date="2027-01-01",
            monthly_rent="1500"))
        return r3["lease_id"]

    def test_propose_renewal(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["prop-propose-renewal"], conn, ns(
            lease_id=lid, new_start_date="2027-01-01",
            new_end_date="2028-01-01", new_monthly_rent="1600"))
        assert is_ok(r)
        row = conn.execute("SELECT status FROM propertyclaw_lease_renewal WHERE id = ?",
                           (r["renewal_id"],)).fetchone()
        assert row["status"] == "proposed"

    def test_accept_renewal(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["prop-propose-renewal"], conn, ns(
            lease_id=lid, new_start_date="2027-01-01",
            new_end_date="2028-01-01", new_monthly_rent="1600"))
        rid = r["renewal_id"]

        r2 = call_action(ACTIONS["prop-accept-renewal"], conn, ns(renewal_id=rid))
        assert is_ok(r2)
        # New lease created from renewal; verify it's active via DB
        new_lid = r2["new_lease_id"]
        row = conn.execute("SELECT status FROM propertyclaw_lease WHERE id = ?",
                           (new_lid,)).fetchone()
        assert row["status"] == "active"
        assert r2["previous_lease_id"] == lid


# ── Tenants / Applications ────────────────────────────────────────────────────

class TestTenants:
    def _make_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Tenant Prop",
            address_line1="40 Tenant Rd", city="Austin", state="TX",
            zip_code="78701"))
        return r["property_id"]

    def test_add_application(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-application"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            applicant_name="Jane Doe", applicant_email="jane@test.com",
            monthly_income="5000"))
        assert is_ok(r)
        row = conn.execute("SELECT status FROM propertyclaw_application WHERE id = ?",
                           (r["application_id"],)).fetchone()
        assert row["status"] == "received"

    def test_get_application(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-application"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            applicant_name="John Smith"))
        appid = r["application_id"]

        r2 = call_action(ACTIONS["prop-get-application"], conn, ns(
            application_id=appid))
        assert is_ok(r2)
        assert r2["applicant_name"] == "John Smith"

    def test_list_applications(self, conn, env):
        pid = self._make_property(conn, env)
        call_action(ACTIONS["prop-add-application"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            applicant_name="Alice"))
        r = call_action(ACTIONS["prop-list-applications"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 1

    def test_update_application(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-application"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            applicant_name="Bob"))
        appid = r["application_id"]

        r2 = call_action(ACTIONS["prop-update-application"], conn, ns(
            application_id=appid, employer="Acme Inc"))
        assert is_ok(r2)
        assert "employer" in r2["updated_fields"]

    def test_add_screening(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-application"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            applicant_name="Screen Test"))
        appid = r["application_id"]

        r2 = call_action(ACTIONS["prop-add-screening"], conn, ns(
            application_id=appid, screening_type="credit",
            consent_obtained="true", consent_date="2026-01-01"))
        assert is_ok(r2)
        assert r2["result"] == "pending"

    def test_deny_application(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-application"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            applicant_name="Deny Test"))
        appid = r["application_id"]

        r2 = call_action(ACTIONS["prop-deny-application"], conn, ns(
            application_id=appid, denial_reason="Failed credit check",
            cra_name="Experian", cra_phone="800-555-1234"))
        assert is_ok(r2)
        row = conn.execute("SELECT status FROM propertyclaw_application WHERE id = ?",
                           (appid,)).fetchone()
        assert row["status"] == "denied"

    def test_add_and_list_documents(self, conn, env):
        r = call_action(ACTIONS["prop-add-document"], conn, ns(
            customer_id=env["customer"], document_type="lease",
            file_url="https://example.com/lease.pdf"))
        assert is_ok(r)

        r2 = call_action(ACTIONS["prop-list-documents"], conn, ns(
            customer_id=env["customer"]))
        assert is_ok(r2)
        assert r2["total_count"] >= 1


# ── Maintenance ───────────────────────────────────────────────────────────────

class TestMaintenance:
    def _make_wo_env(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Maint Prop",
            address_line1="50 Fix Rd", city="Austin", state="TX",
            zip_code="78701"))
        return r["property_id"]

    def test_add_work_order(self, conn, env):
        pid = self._make_wo_env(conn, env)
        r = call_action(ACTIONS["prop-add-work-order"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            description="Leaking faucet", reported_date="2026-03-01",
            category="plumbing", priority="urgent"))
        assert is_ok(r)
        row = conn.execute("SELECT status FROM propertyclaw_work_order WHERE id = ?",
                           (r["work_order_id"],)).fetchone()
        assert row["status"] == "open"

    def test_update_work_order(self, conn, env):
        pid = self._make_wo_env(conn, env)
        r = call_action(ACTIONS["prop-add-work-order"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            description="Broken window", reported_date="2026-03-01"))
        woid = r["work_order_id"]

        r2 = call_action(ACTIONS["prop-update-work-order"], conn, ns(
            work_order_id=woid, wo_status="in_progress"))
        assert is_ok(r2)

    def test_assign_vendor(self, conn, env):
        pid = self._make_wo_env(conn, env)
        r = call_action(ACTIONS["prop-add-work-order"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            description="AC repair", reported_date="2026-03-01",
            category="hvac"))
        woid = r["work_order_id"]

        r2 = call_action(ACTIONS["prop-assign-vendor"], conn, ns(
            work_order_id=woid, supplier_id=env["supplier"]))
        assert is_ok(r2)
        row = conn.execute("SELECT status FROM propertyclaw_work_order WHERE id = ?",
                           (woid,)).fetchone()
        assert row["status"] == "assigned"

    def test_complete_work_order(self, conn, env):
        pid = self._make_wo_env(conn, env)
        r = call_action(ACTIONS["prop-add-work-order"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            description="Fix roof", reported_date="2026-03-01"))
        woid = r["work_order_id"]

        r2 = call_action(ACTIONS["prop-complete-work-order"], conn, ns(
            work_order_id=woid, actual_cost="350"))
        assert is_ok(r2)
        assert r2["actual_cost"] == "350.00"

    def test_add_work_order_item(self, conn, env):
        pid = self._make_wo_env(conn, env)
        r = call_action(ACTIONS["prop-add-work-order"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            description="Plumbing fix", reported_date="2026-03-01"))
        woid = r["work_order_id"]

        r2 = call_action(ACTIONS["prop-add-work-order-item"], conn, ns(
            work_order_id=woid, item_description="Labor",
            item_type="labor", rate="75", quantity="2"))
        assert is_ok(r2)
        assert r2["amount"] == "150.00"

    def test_list_work_orders(self, conn, env):
        pid = self._make_wo_env(conn, env)
        call_action(ACTIONS["prop-add-work-order"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            description="Test WO", reported_date="2026-03-01"))
        r = call_action(ACTIONS["prop-list-work-orders"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 1


# ── Inspections ───────────────────────────────────────────────────────────────

class TestInspections:
    def _make_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Inspect Prop",
            address_line1="60 Inspect Rd", city="Austin", state="TX",
            zip_code="78701"))
        return r["property_id"]

    def test_add_inspection(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-inspection"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            inspection_type="routine", inspection_date="2026-03-15",
            inspector_name="Bob Smith"))
        assert is_ok(r)
        row = conn.execute("SELECT status FROM propertyclaw_inspection WHERE id = ?",
                           (r["inspection_id"],)).fetchone()
        assert row["status"] == "scheduled"

    def test_add_inspection_item(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-add-inspection"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            inspection_type="move_in", inspection_date="2026-03-15"))
        iid = r["inspection_id"]

        r2 = call_action(ACTIONS["prop-add-inspection-item"], conn, ns(
            inspection_id=iid, area="kitchen", item="appliances",
            condition="good", description="All appliances working"))
        assert is_ok(r2)

    def test_list_inspections(self, conn, env):
        pid = self._make_property(conn, env)
        call_action(ACTIONS["prop-add-inspection"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            inspection_type="routine", inspection_date="2026-03-15"))
        r = call_action(ACTIONS["prop-list-inspections"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 1


# ── Accounting ────────────────────────────────────────────────────────────────

class TestAccounting:
    def _make_property(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Acct Prop",
            address_line1="70 Acct Rd", city="Austin", state="TX",
            zip_code="78701", management_fee_pct="10"))
        return r["property_id"]

    def _setup_trust_direct(self, conn, company_id, property_id, account_id):
        """Insert trust account directly (bypasses account_type == 'trust' check)."""
        import uuid
        tid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO propertyclaw_trust_account
               (id, company_id, property_id, account_id, bank_name, status)
               VALUES (?,?,?,?,?,?)""",
            (tid, company_id, property_id, account_id, "First National", "active"))
        conn.commit()
        return tid

    def test_setup_trust_account_rejects_non_trust(self, conn, env):
        """Schema doesn't support 'trust' account_type; bank should be rejected."""
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-setup-trust-account"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            account_id=env["trust_account"], bank_name="First National"))
        assert is_error(r)  # bank != trust

    def test_list_trust_accounts(self, conn, env):
        pid = self._make_property(conn, env)
        self._setup_trust_direct(conn, env["company_id"], pid, env["trust_account"])
        r = call_action(ACTIONS["prop-list-trust-accounts"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["count"] >= 1

    def test_get_trust_account(self, conn, env):
        pid = self._make_property(conn, env)
        tid = self._setup_trust_direct(conn, env["company_id"], pid, env["trust_account"])
        r = call_action(ACTIONS["prop-get-trust-account"], conn, ns(
            trust_account_id=tid))
        assert is_ok(r)
        assert r["bank_name"] == "First National"

    def test_record_and_return_security_deposit(self, conn, env):
        pid = self._make_property(conn, env)
        # Create lease
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Dep Prop",
            address_line1="80 Dep Rd", city="Austin", state="TX",
            zip_code="78701"))
        pid2 = r["property_id"]
        r2 = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid2, unit_number="D1"))
        uid = r2["unit_id"]
        r3 = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=pid2,
            unit_id=uid, customer_id=env["customer"],
            start_date="2026-01-01", monthly_rent="1500"))
        lid = r3["lease_id"]

        # Record deposit
        r4 = call_action(ACTIONS["prop-record-security-deposit"], conn, ns(
            lease_id=lid, amount="1500", deposit_date="2026-01-01"))
        assert is_ok(r4)
        dep_id = r4["security_deposit_id"]

        # Return deposit
        r5 = call_action(ACTIONS["prop-return-security-deposit"], conn, ns(
            security_deposit_id=dep_id, return_amount="1500"))
        assert is_ok(r5)
        row = conn.execute("SELECT status FROM propertyclaw_security_deposit WHERE id = ?",
                           (dep_id,)).fetchone()
        assert row["status"] == "returned"

    def test_add_deposit_deduction(self, conn, env):
        r = call_action(ACTIONS["prop-add-property"], conn, ns(
            company_id=env["company_id"], name="Deduct Prop",
            address_line1="90 Ded Rd", city="Austin", state="TX",
            zip_code="78701"))
        pid = r["property_id"]
        r2 = call_action(ACTIONS["prop-add-unit"], conn, ns(
            property_id=pid, unit_number="DD1"))
        uid = r2["unit_id"]
        r3 = call_action(ACTIONS["prop-add-lease"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            unit_id=uid, customer_id=env["customer"],
            start_date="2026-01-01", monthly_rent="1500"))
        lid = r3["lease_id"]

        r4 = call_action(ACTIONS["prop-record-security-deposit"], conn, ns(
            lease_id=lid, amount="2000", deposit_date="2026-01-01"))
        dep_id = r4["security_deposit_id"]

        r5 = call_action(ACTIONS["prop-add-deposit-deduction"], conn, ns(
            security_deposit_id=dep_id, deduction_type="damages",
            deduction_description="Broken window", amount="200"))
        assert is_ok(r5)
        assert r5["total_deductions"] == "200.00"

    def test_generate_owner_statement(self, conn, env):
        pid = self._make_property(conn, env)
        r = call_action(ACTIONS["prop-generate-owner-statement"], conn, ns(
            company_id=env["company_id"], property_id=pid,
            period_start="2026-01-01", period_end="2026-01-31"))
        assert is_ok(r)
        row = conn.execute("SELECT status FROM propertyclaw_owner_statement WHERE id = ?",
                           (r["statement_id"],)).fetchone()
        assert row["status"] == "draft"

    def test_generate_1099_report(self, conn, env):
        r = call_action(ACTIONS["prop-generate-1099-report"], conn, ns(
            company_id=env["company_id"], tax_year="2025"))
        assert is_ok(r)
        assert r["tax_year"] == 2025
