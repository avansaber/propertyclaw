#!/usr/bin/env python3
"""propertyclaw-commercial — db_query.py (unified router)

Commercial real estate management: NNN leases, CAM pools, TI allowances, and reports.
Routes all actions across 4 domain modules: nnn_leases, cam, ti, reports.

Usage: python3 db_query.py --action <action-name> [--flags ...]
Output: JSON to stdout, exit 0 on success, exit 1 on error.
"""
import argparse
import json
import os
import sys

# Add shared lib to path
try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection, ensure_db_exists, DEFAULT_DB_PATH
    from erpclaw_lib.validation import check_input_lengths
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.dependencies import check_required_tables
    from erpclaw_lib.args import SafeArgumentParser, check_unknown_args
except ImportError:
    import json as _json
    print(_json.dumps({
        "status": "error",
        "error": "ERPClaw foundation not installed. Install erpclaw-setup first: clawhub install erpclaw-setup",
        "suggestion": "clawhub install erpclaw-setup"
    }))
    sys.exit(1)

# Add this script's directory so domain modules can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nnn_leases import ACTIONS as NNN_ACTIONS
from cam import ACTIONS as CAM_ACTIONS
from ti import ACTIONS as TI_ACTIONS
from reports import ACTIONS as REPORTS_ACTIONS

# ---------------------------------------------------------------------------
# Merge all domain actions into one router
# ---------------------------------------------------------------------------
SKILL = "propertyclaw-commercial"
REQUIRED_TABLES = ["company", "commercial_nnn_lease"]

ACTIONS = {}
ACTIONS.update(NNN_ACTIONS)
ACTIONS.update(CAM_ACTIONS)
ACTIONS.update(TI_ACTIONS)
ACTIONS.update(REPORTS_ACTIONS)
ACTIONS["status"] = lambda conn, args: ok({
    "skill": SKILL,
    "version": "1.0.0",
    "actions_available": len([k for k in ACTIONS if k != "status"]),
    "domains": ["nnn_leases", "cam", "ti", "reports"],
    "database": DEFAULT_DB_PATH,
})


def main():
    parser = SafeArgumentParser(description="propertyclaw-commercial")
    parser.add_argument("--action", required=True, choices=sorted(ACTIONS.keys()))
    parser.add_argument("--db-path", default=None)

    # -- Shared IDs --
    parser.add_argument("--company-id")
    parser.add_argument("--lease-id")

    # -- Shared --
    parser.add_argument("--name")
    parser.add_argument("--search")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--description")
    parser.add_argument("--notes")

    # -- NNN Leases --
    parser.add_argument("--tenant-name")
    parser.add_argument("--property-name")
    parser.add_argument("--suite-number")
    parser.add_argument("--lease-start")
    parser.add_argument("--lease-end")
    parser.add_argument("--base-rent")
    parser.add_argument("--cam-share-pct")
    parser.add_argument("--insurance-share-pct")
    parser.add_argument("--tax-share-pct")
    parser.add_argument("--escalation-pct")
    parser.add_argument("--escalation-frequency")
    parser.add_argument("--square-footage")
    parser.add_argument("--lease-status")

    # -- Expense Passthrough --
    parser.add_argument("--expense-type")
    parser.add_argument("--expense-period")
    parser.add_argument("--actual-amount")
    parser.add_argument("--estimated-amount")

    # -- Invoice --
    parser.add_argument("--invoice-period")

    # -- CAM --
    parser.add_argument("--pool-id")
    parser.add_argument("--pool-year")
    parser.add_argument("--total-budget")
    parser.add_argument("--pool-status")
    parser.add_argument("--expense-date")
    parser.add_argument("--category")
    parser.add_argument("--vendor")
    parser.add_argument("--amount")
    parser.add_argument("--reconciliation-date")

    # -- TI --
    parser.add_argument("--allowance-id")
    parser.add_argument("--total-allowance")
    parser.add_argument("--contractor")
    parser.add_argument("--scope-of-work")
    parser.add_argument("--ti-status")
    parser.add_argument("--draw-date")
    parser.add_argument("--draw-status")
    parser.add_argument("--invoice-reference")

    # -- Reports --
    parser.add_argument("--property-value")

    args, unknown = parser.parse_known_args()
    check_unknown_args(parser, unknown)
    check_input_lengths(args)

    db_path = args.db_path or DEFAULT_DB_PATH
    ensure_db_exists(db_path)
    conn = get_connection(db_path)

    _dep = check_required_tables(conn, REQUIRED_TABLES)
    if _dep:
        _dep["suggestion"] = "clawhub install erpclaw-setup && python3 init_db.py"
        print(json.dumps(_dep, indent=2))
        conn.close()
        sys.exit(1)

    try:
        ACTIONS[args.action](conn, args)
    except Exception as e:
        conn.rollback()
        sys.stderr.write(f"[{SKILL}] {e}\n")
        err(str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
