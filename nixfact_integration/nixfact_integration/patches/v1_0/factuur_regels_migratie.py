# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Migreer facturen zonder regels naar één regel met het oude bedrag.

Vóór deze patch had NixFact Factuur één bedrag en één btw-percentage.
Zonder migratie zou bereken_bedragen() die facturen op nul zetten.
"""

from __future__ import annotations


def bepaal_migratie_regel(factuur: dict) -> dict:
    """Bouw de ene regel die het oude factuurbedrag representeert.

    Puur, zodat het in CI te testen is zonder bench.
    """
    pct = float(factuur.get("btw_percentage") or 0)
    categorie = "Standaard" if pct > 0 else "Nultarief"

    omschrijving = (factuur.get("referentie") or "").strip()
    if not omschrijving:
        nummer = (factuur.get("factuurnummer") or "").strip()
        omschrijving = f"Factuur {nummer}" if nummer else "Gemigreerde factuurregel"

    return {
        "omschrijving": omschrijving,
        "aantal": 1,
        "eenheidsprijs": float(factuur.get("bedrag_excl_btw") or 0),
        "btw_categorie": categorie,
        "btw_percentage": pct,
    }


def execute() -> None:
    """Frappe-patch: geef elke regelloze factuur precies één regel."""
    import frappe

    facturen = frappe.get_all(
        "NixFact Factuur",
        fields=["name", "bedrag_excl_btw", "btw_percentage", "referentie",
                "factuurnummer"],
    )
    gemigreerd = 0
    for rij in facturen:
        bestaat = frappe.db.count(
            "NixFact Factuur Regel",
            {"parent": rij.name, "parenttype": "NixFact Factuur"},
        )
        if bestaat:
            continue

        doc = frappe.get_doc("NixFact Factuur", rij.name)
        doc.append("regels", bepaal_migratie_regel(dict(rij)))
        doc.save(ignore_permissions=True)
        gemigreerd += 1

    frappe.db.commit()
    print(f"[nixfact] {gemigreerd} facturen gemigreerd naar regels")
