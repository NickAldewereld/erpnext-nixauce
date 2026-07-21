# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from __future__ import annotations

from frappe.model.document import Document


class NixFactFactuurRegel(Document):
    """Eén regel op een factuur. Berekening gebeurt op de parent."""

    pass
