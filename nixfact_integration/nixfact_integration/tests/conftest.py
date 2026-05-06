# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Pytest setup: stub `frappe` so pure-helper tests run without a real site.

The helper modules under nixfact_integration/ all do `import frappe` at
module load time. That breaks plain `pytest` outside a Frappe bench, even
for tests that only exercise pure logic (regex, fuzzy match, format
strings, namespace constants, date arithmetic).

This conftest is loaded before any test module is imported. It registers a
minimal `frappe` and `frappe.utils` in sys.modules with just the symbols
those module-level imports need.

The stubs are intentionally NOT correct enough to back database-touching
code paths — anything that hits the DB or whitelist machinery must run via
``bench --site … run-tests`` against a real bench. If a test starts
relying on a stub behaving like real Frappe, that's the signal to move it
to the bench-driven integration suite.
"""

from __future__ import annotations

import sys
import types
from datetime import date, datetime, timedelta


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value).date()
    return date.today()


def _flt(value, precision=None):
    try:
        f = float(value if value is not None else 0)
    except (TypeError, ValueError):
        return 0.0
    return round(f, precision) if precision is not None else f


def _add_days(d, n):
    return _to_date(d) + timedelta(days=int(n))


def _add_months(d, n):
    """Add n calendar months, clamping to month-end on overflow.

    Mirrors frappe.utils.add_months: Jan 31 + 1 month → Feb 28/29.
    Returns a date object (matches frappe when given a date input).
    """
    base = _to_date(d)
    month_idx = base.month - 1 + int(n)
    new_year = base.year + month_idx // 12
    new_month = month_idx % 12 + 1
    if new_month == 12:
        next_month_first = date(new_year + 1, 1, 1)
    else:
        next_month_first = date(new_year, new_month + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(new_year, new_month, min(base.day, last_day))


def _install_frappe_stub() -> None:
    if "frappe" in sys.modules:
        return

    frappe = types.ModuleType("frappe")
    frappe._ = lambda msg, *args, **kw: str(msg)

    class _ValidationError(Exception):
        pass

    class _PermissionError(Exception):
        pass

    class _DoesNotExistError(Exception):
        pass

    frappe.ValidationError = _ValidationError
    frappe.PermissionError = _PermissionError
    frappe.DoesNotExistError = _DoesNotExistError

    def _throw(msg, exc=None):
        cls = exc or _ValidationError
        raise cls(str(msg))

    frappe.throw = _throw
    frappe.log_error = lambda *a, **kw: None

    # @frappe.whitelist(...) decorator factory — pass-through.
    def _whitelist(*dargs, **dkw):
        if len(dargs) == 1 and callable(dargs[0]) and not dkw:
            # used as @frappe.whitelist (no parens)
            return dargs[0]
        return lambda fn: fn

    frappe.whitelist = _whitelist
    frappe.get_traceback = lambda: ""
    frappe.logger = lambda *a, **kw: types.SimpleNamespace(
        info=lambda *a, **kw: None,
        warning=lambda *a, **kw: None,
        error=lambda *a, **kw: None,
        debug=lambda *a, **kw: None,
    )

    utils = types.ModuleType("frappe.utils")
    utils.flt = _flt
    utils.getdate = _to_date
    utils.nowdate = lambda: date.today().isoformat()
    utils.add_days = lambda d, n: _add_days(d, n).isoformat()
    utils.add_months = _add_months
    utils.get_url = lambda: "https://nixfact.test"
    utils.get_datetime = lambda: datetime.now()
    utils.now_datetime = lambda: datetime.now()

    frappe.utils = utils

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils


_install_frappe_stub()
