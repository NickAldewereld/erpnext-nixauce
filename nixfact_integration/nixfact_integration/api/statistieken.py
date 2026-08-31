# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Aggregate financial statistics — restricted to accountant-class roles."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import (
    add_months,
    flt,
    get_first_day,
    get_last_day,
    getdate,
    nowdate,
)

ALLOWED_ROLES = {"System Manager", "Accounts Manager", "Accounts User"}


def _require_role() -> None:
    """Refuse access unless the user has an accountant-class role.

    Without this gate, every authenticated Frappe user (e.g. an Employee
    or Sales role) could read company-wide P&L, BTW liabilities, and
    top-customer revenue.
    """
    if not (set(frappe.get_roles()) & ALLOWED_ROLES):
        raise frappe.PermissionError(_("Niet toegestaan."))


def _parse_int(value, *, lo: int, hi: int, name: str, default: int) -> int:
    """Parse and bounds-check an integer query parameter.

    Frappe's whitelisted methods receive query params as strings. ``int()``
    on a non-numeric value raises ValueError, which surfaces as a 500 with
    a traceback — info disclosure. Convert that into a clean 400.
    """
    if value is None or value == "":
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        frappe.throw(_("Ongeldige waarde voor {0}").format(name), frappe.ValidationError)
    if not (lo <= n <= hi):
        frappe.throw(
            _("Waarde voor {0} moet tussen {1} en {2} liggen").format(name, lo, hi),
            frappe.ValidationError,
        )
    return n


def _maand_namen() -> list[str]:
    return [
        _("jan"), _("feb"), _("mrt"), _("apr"), _("mei"), _("jun"),
        _("jul"), _("aug"), _("sep"), _("okt"), _("nov"), _("dec"),
    ]


@frappe.whitelist()
def get_dashboard_data(periode: str = "maand", jaar=None, maand=None) -> dict:
    """Dashboard statistics for a given period."""
    _require_role()

    today = getdate(nowdate())
    jaar = _parse_int(jaar, lo=2000, hi=2100, name="jaar", default=today.year)
    maand = _parse_int(maand, lo=1, hi=12, name="maand", default=today.month)

    if periode == "maand":
        from_date = get_first_day(f"{jaar}-{maand:02d}-01")
        to_date = get_last_day(f"{jaar}-{maand:02d}-01")
    elif periode == "kwartaal":
        kwartaal_start = ((maand - 1) // 3) * 3 + 1
        from_date = getdate(f"{jaar}-{kwartaal_start:02d}-01")
        to_date = get_last_day(add_months(from_date, 2))
    elif periode == "jaar":
        from_date = getdate(f"{jaar}-01-01")
        to_date = getdate(f"{jaar}-12-31")
    else:
        frappe.throw(
            _("Ongeldige periode (verwacht: maand, kwartaal, jaar)."),
            frappe.ValidationError,
        )

    omzet_data = frappe.db.sql(
        """
        SELECT COALESCE(SUM(bedrag_incl_btw), 0) AS totaal,
               COUNT(*) AS aantal
        FROM `tabNixFact Factuur`
        WHERE factuur_datum BETWEEN %s AND %s
          AND status != 'Concept'
        """,
        (from_date, to_date),
        as_dict=True,
    )[0]

    totale_omzet = flt(omzet_data.totaal or 0, 2)
    aantal_facturen = int(omzet_data.aantal or 0)

    totale_kosten = flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(bedrag_incl), 0)
            FROM `tabNixFact Inkoopfactuur`
            WHERE factuurdatum BETWEEN %s AND %s
            """,
            (from_date, to_date),
        )[0][0]
        or 0,
        2,
    )

    openstaand_bedrag = flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(openstaand_bedrag), 0)
            FROM `tabNixFact Factuur`
            WHERE status IN ('Verstuurd', 'Herinnering verstuurd', 'Aanmaning verstuurd')
            """
        )[0][0]
        or 0,
        2,
    )

    grafiek_data = []
    namen = _maand_namen()
    for i in range(11, -1, -1):
        m_date = add_months(today, -i)
        m_start = get_first_day(m_date)
        m_end = get_last_day(m_date)

        m_omzet = frappe.db.sql(
            """
            SELECT COALESCE(SUM(bedrag_incl_btw), 0)
            FROM `tabNixFact Factuur`
            WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
            """,
            (m_start, m_end),
        )[0][0] or 0

        m_kosten = frappe.db.sql(
            """
            SELECT COALESCE(SUM(bedrag_incl), 0)
            FROM `tabNixFact Inkoopfactuur`
            WHERE factuurdatum BETWEEN %s AND %s
            """,
            (m_start, m_end),
        )[0][0] or 0

        grafiek_data.append(
            {
                "maand": namen[getdate(m_start).month - 1],
                "omzet": flt(m_omzet, 2),
                "kosten": flt(m_kosten, 2),
            }
        )

    # Live JOIN against Customer so a renamed customer doesn't appear
    # twice with old + new spelling.
    top_klanten = frappe.db.sql(
        """
        SELECT f.klant AS klant,
               COALESCE(c.customer_name, f.klant) AS klant_naam,
               SUM(f.bedrag_incl_btw) AS omzet
        FROM `tabNixFact Factuur` f
        LEFT JOIN `tabCustomer` c ON c.name = f.klant
        WHERE f.factuur_datum BETWEEN %s AND %s
          AND f.status != 'Concept'
        GROUP BY f.klant
        ORDER BY omzet DESC
        LIMIT 10
        """,
        (from_date, to_date),
        as_dict=True,
    )

    return {
        "totale_omzet": totale_omzet,
        "totale_kosten": totale_kosten,
        "resultaat": flt(totale_omzet - totale_kosten, 2),
        "aantal_facturen": aantal_facturen,
        "gemiddelde_factuurwaarde": (
            flt(totale_omzet / aantal_facturen, 2) if aantal_facturen else 0
        ),
        "openstaand_bedrag": openstaand_bedrag,
        "grafiek_data": grafiek_data,
        "top_klanten": top_klanten,
    }


@frappe.whitelist()
def get_omzet_deze_maand_card() -> dict:
    """Waarde voor de Number Card 'Omzet deze maand'.

    Number Cards van het type Document Type ondersteunen geen dynamisch
    datumbereik ("deze maand"), dus deze kaart is van het type Custom en
    haalt de maandomzet hier server-side op. Zelfde definitie als
    ``get_dashboard_data(periode="maand")``: som van ``bedrag_incl_btw``
    van facturen met status != Concept in de huidige kalendermaand.
    """
    _require_role()

    today = getdate(nowdate())
    from_date = get_first_day(today)
    to_date = get_last_day(today)

    waarde = frappe.db.sql(
        """
        SELECT COALESCE(SUM(bedrag_incl_btw), 0)
        FROM `tabNixFact Factuur`
        WHERE factuur_datum BETWEEN %s AND %s
          AND status != 'Concept'
        """,
        (from_date, to_date),
    )[0][0] or 0

    return {"value": flt(waarde, 2), "fieldtype": "Currency"}


@frappe.whitelist()
def get_facturen_te_laat_card() -> dict:
    """Waarde voor de Number Card 'Facturen te laat'.

    Number Cards van het type Document Type kunnen niet filteren op
    ``vervaldatum < vandaag`` (geen dynamische datum in filters_json),
    dus deze kaart is van het type Custom. Telt openstaande facturen
    (Verstuurd / Herinnering verstuurd / Aanmaning verstuurd) waarvan de
    vervaldatum gepasseerd is.
    """
    _require_role()

    aantal = frappe.db.count(
        "NixFact Factuur",
        {
            "vervaldatum": ["<", nowdate()],
            "status": [
                "in",
                ["Verstuurd", "Herinnering verstuurd", "Aanmaning verstuurd"],
            ],
        },
    )

    return {"value": int(aantal or 0), "fieldtype": "Int"}


@frappe.whitelist()
def get_btw_overzicht(kwartaal, jaar=None) -> dict:
    """BTW reporting per kwartaal."""
    _require_role()

    today = getdate(nowdate())
    jaar = _parse_int(jaar, lo=2000, hi=2100, name="jaar", default=today.year)
    kwartaal = _parse_int(kwartaal, lo=1, hi=4, name="kwartaal", default=1)

    start_maand = (kwartaal - 1) * 3 + 1
    from_date = getdate(f"{jaar}-{start_maand:02d}-01")
    to_date = get_last_day(add_months(from_date, 2))

    verkoop_btw = flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(btw_bedrag), 0)
            FROM `tabNixFact Factuur`
            WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
            """,
            (from_date, to_date),
        )[0][0]
        or 0,
        2,
    )

    inkoop_btw = flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(btw_bedrag), 0)
            FROM `tabNixFact Inkoopfactuur`
            WHERE factuurdatum BETWEEN %s AND %s
            """,
            (from_date, to_date),
        )[0][0]
        or 0,
        2,
    )

    verkoop_excl = flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(bedrag_excl_btw), 0)
            FROM `tabNixFact Factuur`
            WHERE factuur_datum BETWEEN %s AND %s AND status != 'Concept'
            """,
            (from_date, to_date),
        )[0][0]
        or 0,
        2,
    )

    inkoop_excl = flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(bedrag_excl), 0)
            FROM `tabNixFact Inkoopfactuur`
            WHERE factuurdatum BETWEEN %s AND %s
            """,
            (from_date, to_date),
        )[0][0]
        or 0,
        2,
    )

    return {
        "kwartaal": kwartaal,
        "jaar": jaar,
        "verkoop_excl": verkoop_excl,
        "verkoop_btw": verkoop_btw,
        "inkoop_excl": inkoop_excl,
        "inkoop_btw": inkoop_btw,
        "af_te_dragen": flt(verkoop_btw - inkoop_btw, 2),
    }


@frappe.whitelist()
def get_omzet_per_klant(jaar=None) -> list[dict]:
    """Revenue breakdown by customer for a given year."""
    _require_role()
    today = getdate(nowdate())
    jaar = _parse_int(jaar, lo=2000, hi=2100, name="jaar", default=today.year)
    from_date = getdate(f"{jaar}-01-01")
    to_date = getdate(f"{jaar}-12-31")

    return frappe.db.sql(
        """
        SELECT f.klant AS klant,
               COALESCE(c.customer_name, f.klant) AS klant_naam,
               COUNT(*) AS aantal_facturen,
               SUM(f.bedrag_excl_btw) AS omzet_excl,
               SUM(f.bedrag_incl_btw) AS omzet_incl,
               SUM(f.btw_bedrag) AS btw_totaal
        FROM `tabNixFact Factuur` f
        LEFT JOIN `tabCustomer` c ON c.name = f.klant
        WHERE f.factuur_datum BETWEEN %s AND %s AND f.status != 'Concept'
        GROUP BY f.klant
        ORDER BY omzet_incl DESC
        """,
        (from_date, to_date),
        as_dict=True,
    )


@frappe.whitelist()
def get_kosten_per_categorie(jaar=None) -> list[dict]:
    """Cost breakdown by category for a given year."""
    _require_role()
    today = getdate(nowdate())
    jaar = _parse_int(jaar, lo=2000, hi=2100, name="jaar", default=today.year)
    from_date = getdate(f"{jaar}-01-01")
    to_date = getdate(f"{jaar}-12-31")

    return frappe.db.sql(
        """
        SELECT COALESCE(kostencategorie, 'Geen categorie') AS categorie,
               COUNT(*) AS aantal,
               SUM(bedrag_excl) AS totaal_excl,
               SUM(bedrag_incl) AS totaal_incl
        FROM `tabNixFact Inkoopfactuur`
        WHERE factuurdatum BETWEEN %s AND %s
        GROUP BY kostencategorie
        ORDER BY totaal_incl DESC
        """,
        (from_date, to_date),
        as_dict=True,
    )
