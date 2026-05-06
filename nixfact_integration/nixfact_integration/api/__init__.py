"""NixFact whitelisted-method package.

Re-exports module-level whitelisted helpers so callers (Frappe REST clients,
the nixfact-mcp server, etc.) can keep using the dotted paths
``nixfact_integration.api.create_offerte`` etc. while the implementation
lives in submodules.
"""

from nixfact_integration.api.offerte import (
    create_offerte,
    get_offerte,
    update_offerte_status,
)

__all__ = [
    "create_offerte",
    "get_offerte",
    "update_offerte_status",
]
