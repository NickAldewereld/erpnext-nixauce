#!/usr/bin/env python3
"""Live smoke test for nixfact-mcp.

Exercises read-only paths against a real Nixfact / Frappe instance to
confirm credentials, base URL and the most-used endpoints work.

Reads NIXFACT_BASE_URL / NIXFACT_API_KEY / NIXFACT_API_SECRET from the
environment. Make NO mutating calls — anything that creates / updates /
deletes is intentionally absent.

Usage:
    export NIXFACT_BASE_URL=https://erp-staging.nixfact.eu
    export NIXFACT_API_KEY=...
    export NIXFACT_API_SECRET=...
    python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

# Allow `python scripts/smoke_test.py` from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nixfact_mcp.client import NixfactClient, NixfactError  # noqa: E402


def _ok(label: str, data: Any) -> None:
    head = json.dumps(data, ensure_ascii=False, default=str)[:200]
    print(f"  OK   {label}: {head}")


def _fail(label: str, e: Exception) -> None:
    print(f"  FAIL {label}: {type(e).__name__}: {e}")


async def main() -> int:
    if not os.environ.get("NIXFACT_BASE_URL"):
        print("NIXFACT_BASE_URL is not set — aborting.", file=sys.stderr)
        return 2

    failures = 0
    print(f"Smoke-testing {os.environ['NIXFACT_BASE_URL']} ...")

    async with NixfactClient() as c:
        # 1. Auth check.
        try:
            user = await c.call_method(
                "frappe.auth.get_logged_user", http_method="GET"
            )
            _ok("frappe.auth.get_logged_user", user)
        except Exception as e:
            _fail("frappe.auth.get_logged_user", e)
            failures += 1
            return failures  # no point continuing without auth

        # 2. Resource list — small page.
        for doctype in (
            "Customer",
            "NixFact Factuur",
            "NixFact Offerte",
            "NixFact Abonnement",
            "NixFact Inkoopfactuur",
        ):
            try:
                rows = await c.list_resource(
                    doctype, fields=["name"], limit_page_length=1
                )
                _ok(f"list {doctype}", {"count": len(rows), "first": rows[:1]})
            except NixfactError as e:
                # 404 on a DocType means the app isn't installed on this site.
                if e.status_code == 404:
                    print(f"  SKIP {doctype}: not present on this site")
                else:
                    _fail(f"list {doctype}", e)
                    failures += 1
            except Exception as e:
                _fail(f"list {doctype}", e)
                failures += 1

        # 3. Whitelisted helpers — read-only stats.
        try:
            dash = await c.call_method(
                "nixfact_integration.api.statistieken.get_dashboard_data",
                params={"periode": "maand"},
                http_method="GET",
            )
            _ok("get_dashboard_data", dash)
        except NixfactError as e:
            if e.status_code in (403, 404):
                print(
                    f"  SKIP get_dashboard_data: {e.status_code} "
                    "(method not whitelisted on this site)"
                )
            else:
                _fail("get_dashboard_data", e)
                failures += 1
        except Exception as e:
            _fail("get_dashboard_data", e)
            failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} check(s) failed.")
        return 1
    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
