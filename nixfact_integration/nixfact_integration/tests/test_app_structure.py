# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Guard the on-disk layout Frappe requires to install this app.

Every other test here stubs `frappe` and exercises pure logic, so none of
them notice when the directory layout itself is wrong. That gap let the app
ship a missing module directory: `bench install-app` died on
`ModuleNotFoundError: No module named 'nixfact_integration.nixfact_integration'`
while all 69 unit tests stayed green.

Frappe resolves a module to `<app>/<app>/<frappe.scrub(module)>/` and expects
every DocType to live under `<module dir>/doctype/<scrubbed doctype>/`. These
checks are pure filesystem assertions — no bench, no database.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent
MODULES_TXT = APP_DIR / "modules.txt"


def scrub(txt: str) -> str:
    """Mirror `frappe.scrub`: the app-side rule for module dir names."""
    return txt.replace(" ", "_").replace("-", "_").lower()


def declared_modules() -> list[str]:
    return [line.strip() for line in MODULES_TXT.read_text().splitlines() if line.strip()]


def test_modules_txt_is_not_empty():
    assert declared_modules(), "modules.txt declares no modules"


@pytest.mark.parametrize("module", declared_modules())
def test_module_directory_exists(module):
    """Frappe imports `<app>.<scrubbed module>`; without the dir, install fails."""
    module_dir = APP_DIR / scrub(module)
    assert module_dir.is_dir(), (
        f"modules.txt declares '{module}' but {module_dir.relative_to(APP_DIR.parent)} "
        f"does not exist — bench install-app will fail on ModuleNotFoundError"
    )
    assert (module_dir / "__init__.py").is_file(), (
        f"{module_dir.relative_to(APP_DIR.parent)} is not an importable package "
        f"(no __init__.py)"
    )


def doctype_json_files() -> list[Path]:
    return sorted(APP_DIR.glob("*/doctype/*/*.json"))


def test_doctypes_are_found_under_a_module_directory():
    assert doctype_json_files(), (
        "no DocType JSON found at <module>/doctype/<name>/<name>.json — "
        "DocTypes outside a module directory are invisible to Frappe"
    )


@pytest.mark.parametrize("path", doctype_json_files(), ids=lambda p: p.stem)
def test_doctype_module_matches_its_directory(path):
    """A DocType's `module` field must match the module dir it sits in."""
    meta = json.loads(path.read_text())
    module = meta.get("module")
    assert module in declared_modules(), (
        f"{path.name} declares module '{module}', which modules.txt does not list"
    )
    module_dir_name = path.parents[2].name
    assert scrub(module) == module_dir_name, (
        f"{path.name} declares module '{module}' (dir '{scrub(module)}') "
        f"but sits under '{module_dir_name}'"
    )
