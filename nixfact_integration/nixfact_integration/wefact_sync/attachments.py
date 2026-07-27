# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-bijlagen downloaden (base64) en als privé-File aanhangen.

`decode_base64` is puur/testbaar; `hang_bijlagen` raakt frappe + de client.
"""

from __future__ import annotations

import base64
import re

_SAFE = re.compile(r"[^A-Za-z0-9._\-]")


def decode_base64(att: dict) -> tuple[bytes, str]:
    b64 = att.get("Base64") or att.get("base64") or ""
    if not b64:
        raise ValueError("bijlage heeft geen Base64-inhoud")
    naam = (att.get("Filename") or att.get("filename") or "bijlage").strip()
    return base64.b64decode(b64), naam


def hang_bijlagen(client, doc_name: str, attachments: list[dict]) -> int:
    """Download elke bijlage en hang 'm als privé-File aan het doc.

    Per-bijlage-geïsoleerd; geeft het aantal geslaagde bijlagen terug.
    Idempotent: een bestaande File met dezelfde naam wordt eerst verwijderd.
    """
    import frappe

    gelukt = 0
    for att in attachments:
        try:
            meta = client.request(
                "attachment", "download", {"Identifier": att.get("Identifier")}
            )
            data, naam = decode_base64(meta.get("attachment", meta))
            filename = _SAFE.sub("_", naam) or "bijlage.pdf"

            bestaand = frappe.get_all(
                "File",
                filters={
                    "attached_to_doctype": "NixFact Inkoopfactuur",
                    "attached_to_name": doc_name,
                    "file_name": filename,
                },
                pluck="name",
            )
            for oud in bestaand:
                frappe.delete_doc("File", oud, ignore_permissions=True)

            frappe.get_doc(
                {
                    "doctype": "File",
                    "file_name": filename,
                    "attached_to_doctype": "NixFact Inkoopfactuur",
                    "attached_to_name": doc_name,
                    "content": data,
                    "is_private": 1,
                }
            ).save(ignore_permissions=True)
            gelukt += 1
        except Exception:  # noqa: BLE001
            frappe.log_error(
                title="WeFact-bijlage download-fout",
                message=frappe.get_traceback(),
            )
    frappe.db.commit()
    return gelukt
