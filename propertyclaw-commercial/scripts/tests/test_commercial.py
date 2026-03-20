"""L1 pytest tests for PropertyClaw Commercial module.

Covers: NNN leases, expense passthroughs, monthly charges, invoicing,
CAM pools, CAM expenses, CAM allocations, CAM reconciliation,
TI allowances, TI draws, and reports (NOI, cap rate, occupancy).
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from commercial_helpers import call_action, ns, is_ok, is_error, load_db_query

_mod = load_db_query()
ACTIONS = _mod.ACTIONS


# ── NNN Leases ───────────────────────────────────────────────────────────────

class TestNNNLeases:
    def test_add_nnn_lease(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Acme Corp",
            property_name="Downtown Plaza", suite_number="100",
            lease_start="2026-01-01", lease_end="2031-01-01",
            base_rent="5000", cam_share_pct="15", insurance_share_pct="5",
            tax_share_pct="10"))
        assert is_ok(r)
        assert r["lease_id"]
        assert r["naming_series"].startswith("CNNN-")
        assert r["lease_status"] == "draft"

    def test_add_nnn_lease_missing_tenant(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], property_name="Downtown Plaza",
            lease_start="2026-01-01", lease_end="2031-01-01",
            base_rent="5000"))
        assert is_error(r)

    def test_get_nnn_lease(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Beta LLC",
            property_name="Office Park", lease_start="2026-02-01",
            lease_end="2029-02-01", base_rent="3500"))
        lid = r["lease_id"]

        r2 = call_action(ACTIONS["commercial-get-nnn-lease"], conn, ns(lease_id=lid))
        assert is_ok(r2)
        assert r2["tenant_name"] == "Beta LLC"
        assert r2["base_rent"] == "3500.00"

    def test_update_nnn_lease(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Gamma Inc",
            property_name="Tech Center", lease_start="2026-01-01",
            lease_end="2028-01-01", base_rent="4000"))
        lid = r["lease_id"]

        r2 = call_action(ACTIONS["commercial-update-nnn-lease"], conn, ns(
            lease_id=lid, base_rent="4500", lease_status="active"))
        assert is_ok(r2)
        assert "base_rent" in r2["updated_fields"]
        assert "lease_status" in r2["updated_fields"]

    def test_list_nnn_leases(self, conn, env):
        call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="T1",
            property_name="P1", lease_start="2026-01-01",
            lease_end="2027-01-01", base_rent="1000"))
        call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="T2",
            property_name="P1", lease_start="2026-01-01",
            lease_end="2027-01-01", base_rent="2000"))

        r = call_action(ACTIONS["commercial-list-nnn-leases"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 2

    def test_add_expense_passthrough(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Pass Co",
            property_name="Mall", lease_start="2026-01-01",
            lease_end="2027-01-01", base_rent="6000",
            cam_share_pct="20"))
        lid = r["lease_id"]

        r2 = call_action(ACTIONS["commercial-add-expense-passthrough"], conn, ns(
            lease_id=lid, expense_type="cam", expense_period="2026-01",
            actual_amount="10000", estimated_amount="9500"))
        assert is_ok(r2)
        assert r2["tenant_share"] == "2000.00"  # 20% of 10000

    def test_list_expense_passthroughs(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="List PT",
            property_name="Center", lease_start="2026-01-01",
            lease_end="2027-01-01", base_rent="3000",
            cam_share_pct="10"))
        lid = r["lease_id"]
        call_action(ACTIONS["commercial-add-expense-passthrough"], conn, ns(
            lease_id=lid, expense_type="cam", expense_period="2026-01",
            actual_amount="5000"))
        call_action(ACTIONS["commercial-add-expense-passthrough"], conn, ns(
            lease_id=lid, expense_type="insurance", expense_period="2026-01",
            actual_amount="2000"))

        r2 = call_action(ACTIONS["commercial-list-expense-passthroughs"], conn, ns(
            lease_id=lid))
        assert is_ok(r2)
        assert r2["count"] == 2

    def test_calculate_monthly_charges(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Charge Co",
            property_name="Bldg A", lease_start="2026-01-01",
            lease_end="2027-01-01", base_rent="5000",
            cam_share_pct="20", insurance_share_pct="10", tax_share_pct="5"))
        lid = r["lease_id"]

        r2 = call_action(ACTIONS["commercial-calculate-monthly-charges"], conn, ns(
            lease_id=lid))
        assert is_ok(r2)
        assert r2["base_rent"] == "5000.00"
        assert r2["total_monthly"] == "5000.00"  # no passthroughs yet

    def test_generate_nnn_invoice(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Invoice Corp",
            property_name="Tower", lease_start="2026-01-01",
            lease_end="2027-01-01", base_rent="8000",
            cam_share_pct="25"))
        lid = r["lease_id"]

        # Add a passthrough so the invoice has CAM share
        call_action(ACTIONS["commercial-add-expense-passthrough"], conn, ns(
            lease_id=lid, expense_type="cam", expense_period="2026-02",
            actual_amount="12000"))

        r2 = call_action(ACTIONS["commercial-generate-nnn-invoice"], conn, ns(
            lease_id=lid, invoice_period="2026-02"))
        assert is_ok(r2)
        assert r2["tenant_name"] == "Invoice Corp"
        assert len(r2["line_items"]) == 4  # base + cam + insurance + tax

    def test_nnn_lease_summary(self, conn, env):
        call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Sum1",
            property_name="P1", lease_start="2026-01-01",
            lease_end="2027-01-01", base_rent="3000"))
        r = call_action(ACTIONS["commercial-nnn-lease-summary"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_leases"] >= 1
        assert r["draft"] >= 1

    def test_lease_expiry_schedule(self, conn, env):
        call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Expiry Co",
            property_name="P1", lease_start="2026-01-01",
            lease_end="2027-06-30", base_rent="4000"))
        r = call_action(ACTIONS["commercial-lease-expiry-schedule"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["count"] >= 1


# ── CAM Pools ────────────────────────────────────────────────────────────────

class TestCAM:
    def _make_lease(self, conn, env, cam_pct="20"):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="CAM Tenant",
            property_name="CAM Building", suite_number="200",
            lease_start="2026-01-01", lease_end="2028-01-01",
            base_rent="5000", cam_share_pct=cam_pct))
        return r["lease_id"]

    def test_add_cam_pool(self, conn, env):
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="CAM Building",
            pool_year="2026", total_budget="120000"))
        assert is_ok(r)
        assert r["naming_series"].startswith("CCAM-")
        assert r["pool_status"] == "open"
        assert r["total_budget"] == "120000.00"

    def test_add_cam_pool_duplicate(self, conn, env):
        call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="DupProp",
            pool_year="2026", total_budget="100000"))
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="DupProp",
            pool_year="2026", total_budget="100000"))
        assert is_error(r)

    def test_list_cam_pools(self, conn, env):
        call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="ListPool",
            pool_year="2026", total_budget="50000"))
        r = call_action(ACTIONS["commercial-list-cam-pools"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 1

    def test_get_cam_pool(self, conn, env):
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="GetPool",
            pool_year="2026", total_budget="80000"))
        pid = r["pool_id"]

        r2 = call_action(ACTIONS["commercial-get-cam-pool"], conn, ns(pool_id=pid))
        assert is_ok(r2)
        assert r2["total_budget"] == "80000.00"
        assert r2["expense_count"] == 0
        assert r2["allocation_count"] == 0

    def test_update_cam_pool(self, conn, env):
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="UpdPool",
            pool_year="2026", total_budget="60000"))
        pid = r["pool_id"]

        r2 = call_action(ACTIONS["commercial-update-cam-pool"], conn, ns(
            pool_id=pid, total_budget="75000"))
        assert is_ok(r2)
        assert "total_budget" in r2["updated_fields"]

    def test_add_cam_expense(self, conn, env):
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="ExpPool",
            pool_year="2026", total_budget="100000"))
        pid = r["pool_id"]

        r2 = call_action(ACTIONS["commercial-add-cam-expense"], conn, ns(
            pool_id=pid, expense_date="2026-03-15", category="landscaping",
            vendor="GreenCo", amount="2500"))
        assert is_ok(r2)
        assert r2["amount"] == "2500.00"

    def test_list_cam_expenses(self, conn, env):
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="ListExpPool",
            pool_year="2026", total_budget="100000"))
        pid = r["pool_id"]
        call_action(ACTIONS["commercial-add-cam-expense"], conn, ns(
            pool_id=pid, expense_date="2026-01-15", category="janitorial",
            amount="1000"))
        call_action(ACTIONS["commercial-add-cam-expense"], conn, ns(
            pool_id=pid, expense_date="2026-02-15", category="landscaping",
            amount="1500"))

        r2 = call_action(ACTIONS["commercial-list-cam-expenses"], conn, ns(
            pool_id=pid))
        assert is_ok(r2)
        assert r2["count"] == 2
        assert r2["total_amount"] == "2500.00"

    def test_add_cam_allocation(self, conn, env):
        lid = self._make_lease(conn, env, cam_pct="25")
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="CAM Building",
            pool_year="2026", total_budget="100000"))
        pid = r["pool_id"]

        r2 = call_action(ACTIONS["commercial-add-cam-allocation"], conn, ns(
            pool_id=pid, lease_id=lid))
        assert is_ok(r2)
        assert r2["share_pct"] == "25.00"
        assert r2["budgeted_amount"] == "25000.00"

    def test_run_cam_reconciliation(self, conn, env):
        lid = self._make_lease(conn, env, cam_pct="30")
        r = call_action(ACTIONS["commercial-add-cam-pool"], conn, ns(
            company_id=env["company_id"], property_name="CAM Building",
            pool_year="2026", total_budget="100000"))
        pid = r["pool_id"]

        # Add expense
        call_action(ACTIONS["commercial-add-cam-expense"], conn, ns(
            pool_id=pid, expense_date="2026-06-01", category="utilities",
            amount="90000"))

        # Add allocation
        call_action(ACTIONS["commercial-add-cam-allocation"], conn, ns(
            pool_id=pid, lease_id=lid))

        # Reconcile
        r2 = call_action(ACTIONS["commercial-run-cam-reconciliation"], conn, ns(
            pool_id=pid))
        assert is_ok(r2)
        assert r2["pool_status"] == "reconciling"
        assert r2["total_actual"] == "90000.00"
        assert len(r2["allocations"]) == 1
        # 30% of 90000 actual
        assert r2["allocations"][0]["actual_amount"] == "27000.00"


# ── TI Allowances ────────────────────────────────────────────────────────────

class TestTI:
    def _make_lease(self, conn, env):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="TI Tenant",
            property_name="TI Building", lease_start="2026-01-01",
            lease_end="2031-01-01", base_rent="7000"))
        return r["lease_id"]

    def test_add_ti_allowance(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="50000",
            contractor="BuildCo", scope_of_work="Office build-out"))
        assert is_ok(r)
        assert r["naming_series"].startswith("CTI-")
        assert r["ti_status"] == "approved"
        assert r["total_allowance"] == "50000.00"

    def test_get_ti_allowance(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="30000"))
        aid = r["allowance_id"]

        r2 = call_action(ACTIONS["commercial-get-ti-allowance"], conn, ns(
            allowance_id=aid))
        assert is_ok(r2)
        assert r2["total_allowance"] == "30000.00"
        assert r2["remaining_amount"] == "30000.00"
        assert r2["tenant_name"] == "TI Tenant"

    def test_update_ti_allowance(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="40000"))
        aid = r["allowance_id"]

        r2 = call_action(ACTIONS["commercial-update-ti-allowance"], conn, ns(
            allowance_id=aid, contractor="NewBuildCo",
            ti_status="in_progress"))
        assert is_ok(r2)
        assert "contractor" in r2["updated_fields"]
        assert "ti_status" in r2["updated_fields"]

    def test_list_ti_allowances(self, conn, env):
        lid = self._make_lease(conn, env)
        call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="25000"))
        r = call_action(ACTIONS["commercial-list-ti-allowances"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_count"] >= 1

    def test_add_ti_draw(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="50000"))
        aid = r["allowance_id"]

        r2 = call_action(ACTIONS["commercial-add-ti-draw"], conn, ns(
            allowance_id=aid, draw_date="2026-03-01", amount="10000",
            description="Phase 1 draw", invoice_reference="INV-001"))
        assert is_ok(r2)
        assert r2["amount"] == "10000.00"
        assert r2["draw_status"] == "pending"

    def test_add_ti_draw_exceeds_remaining(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="5000"))
        aid = r["allowance_id"]

        r2 = call_action(ACTIONS["commercial-add-ti-draw"], conn, ns(
            allowance_id=aid, draw_date="2026-03-01", amount="6000"))
        assert is_error(r2)

    def test_list_ti_draws(self, conn, env):
        lid = self._make_lease(conn, env)
        r = call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="50000"))
        aid = r["allowance_id"]
        call_action(ACTIONS["commercial-add-ti-draw"], conn, ns(
            allowance_id=aid, draw_date="2026-03-01", amount="10000"))
        call_action(ACTIONS["commercial-add-ti-draw"], conn, ns(
            allowance_id=aid, draw_date="2026-04-01", amount="15000"))

        r2 = call_action(ACTIONS["commercial-list-ti-draws"], conn, ns(
            allowance_id=aid))
        assert is_ok(r2)
        assert r2["count"] == 2

    def test_ti_summary_report(self, conn, env):
        lid = self._make_lease(conn, env)
        call_action(ACTIONS["commercial-add-ti-allowance"], conn, ns(
            lease_id=lid, total_allowance="35000"))
        r = call_action(ACTIONS["commercial-ti-summary-report"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["count"] >= 1
        assert r["grand_total_allowance"] == "35000.00"


# ── Reports ──────────────────────────────────────────────────────────────────

class TestReports:
    def _seed_active_lease(self, conn, env, base_rent="5000"):
        r = call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Report Tenant",
            property_name="Report Bldg", lease_start="2026-01-01",
            lease_end="2028-01-01", base_rent=base_rent))
        lid = r["lease_id"]
        call_action(ACTIONS["commercial-update-nnn-lease"], conn, ns(
            lease_id=lid, lease_status="active"))
        return lid

    def test_noi_report(self, conn, env):
        self._seed_active_lease(conn, env, "8000")
        r = call_action(ACTIONS["commercial-noi-report"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_rental_income"] == "8000.00"
        assert r["lease_count"] == 1

    def test_cap_rate_analysis(self, conn, env):
        self._seed_active_lease(conn, env, "10000")
        r = call_action(ACTIONS["commercial-cap-rate-analysis"], conn, ns(
            company_id=env["company_id"], property_value="1000000"))
        assert is_ok(r)
        # annual income = 10000 * 12 = 120000; no expenses => cap rate = 12%
        assert r["annual_noi"] == "120000.00"
        assert r["cap_rate_pct"] == "12.00"

    def test_occupancy_trend(self, conn, env):
        self._seed_active_lease(conn, env)
        # add a draft lease too
        call_action(ACTIONS["commercial-add-nnn-lease"], conn, ns(
            company_id=env["company_id"], tenant_name="Draft Tenant",
            property_name="Other Bldg", lease_start="2026-06-01",
            lease_end="2027-06-01", base_rent="3000"))
        r = call_action(ACTIONS["commercial-occupancy-trend"], conn, ns(
            company_id=env["company_id"]))
        assert is_ok(r)
        assert r["total_leases"] == 2
        assert r["active"] == 1
        assert r["draft"] == 1
        assert r["occupancy_rate_pct"] == "50.00"
