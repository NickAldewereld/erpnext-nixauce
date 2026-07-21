# NIXFact Kantoor — Fase 1 Implementatieplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `NixFact Factuur` krijgt echte regel-items, de UBL-generator produceert daaruit geldige meerregelige Peppol BIS 3.0 XML met BTW-categorie per regel, en een validator blokkeert ongeldige facturen vóór verzending — eindigend in een demonstreerbare staat voor gesprekken met administratiekantoren.

**Architecture:** De UBL-logica wordt gesplitst in een puur datamodel (`ubl_model.py`, dataclasses zonder frappe-import), een pure XML-builder en validator die alleen dat datamodel kennen, en een dunne frappe-adapter die een `NixFact Factuur`-document naar het datamodel vertaalt. Reden: de CI stubt `frappe` en kan alleen pure helpers draaien — met deze splitsing is de volledige XML-uitvoer in CI te testen in plaats van onttest te blijven.

**Tech Stack:** Frappe/ERPNext (develop-branch, Python 3.14 in productie, CI op 3.11), lxml, pytest, ruff.

## Global Constraints

- Alle nieuwe Python-bestanden beginnen met de bestaande licentieheader, letterlijk:
  `# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.` / `# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)` / `# For commercial licensing, contact: nick@nixpay.nl`
- Alle nieuwe modules gebruiken `from __future__ import annotations`.
- Indentatie: 4 spaties in `utils/`, `api/` en `doctype/` (bestaande stijl daar). Bestaande testbestanden gebruiken tabs; nieuwe testbestanden gebruiken 4 spaties.
- `ruff check nixfact_integration/` moet slagen; regellengte onder 88 tekens.
- Gebruikergerichte teksten (labels, foutmeldingen) zijn Nederlands.
- Bedragen worden altijd afgerond met `flt(x, 2)` en in XML geformatteerd als `f"{x:.2f}"`.
- Nieuwe pure modules importeren **niet** `frappe` — dat is wat ze CI-testbaar maakt.
- BTW-categoriecodes zijn uitsluitend `S`, `AE`, `Z`, `E` (Peppol UNCL5305-subset).

## Bestandsoverzicht

| Bestand | Verantwoordelijkheid |
|---|---|
| `nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/` | Nieuw child doctype: één factuurregel |
| `nixfact_integration/utils/btw.py` | Puur: categoriecodes, mapping NL-label → code, regel- en totaalberekening |
| `nixfact_integration/utils/ubl_model.py` | Puur: dataclasses `UBLRegel`, `UBLPartij`, `UBLFactuur` |
| `nixfact_integration/utils/ubl_builder.py` | Puur: `UBLFactuur` → XML-string |
| `nixfact_integration/utils/ubl_validatie.py` | Puur: `UBLFactuur` → lijst Nederlandse fouten |
| `nixfact_integration/utils/ubl_generator.py` | Dun: frappe-document → `UBLFactuur`, plus bestaande attach-logica |
| `nixfact_integration/patches/v1_0/factuur_regels_migratie.py` | Eenmalige migratie bestaande facturen |
| `nixfact_integration/tests/test_btw.py` | Tests voor berekening en categorieën |
| `nixfact_integration/tests/test_ubl_builder.py` | Tests voor XML-uitvoer |
| `nixfact_integration/tests/test_ubl_validatie.py` | Tests voor validatieregels |

Padprefix voor alles hierboven: `/mnt/nvme1tb/projects/erpnext-nixauce/nixfact_integration/nixfact_integration/`

---

### Task 1: BTW-categorieën en regelberekening (puur)

De rekenkern. Geen frappe, geen XML — alleen getallen en categorieën. Alles hierna bouwt hierop.

**Files:**
- Create: `nixfact_integration/nixfact_integration/utils/btw.py`
- Test: `nixfact_integration/nixfact_integration/tests/test_btw.py`

**Interfaces:**
- Consumes: niets.
- Produces:
  - `CATEGORIE_CODES: dict[str, str]` — NL-label → Peppol-code
  - `NUL_CATEGORIEEN: frozenset[str]` — codes die 0% moeten hebben (`AE`, `Z`, `E`)
  - `VRIJSTELLING_REDEN: dict[str, str]` — code → verplichte reden-tekst
  - `code_voor_categorie(label: str) -> str`
  - `regel_excl(aantal: float, eenheidsprijs: float) -> float`
  - `class BtwGroep` met velden `code: str`, `percentage: float`, `excl: float`, `btw: float`
  - `groepeer_btw(regels: list[dict]) -> list[BtwGroep]` — regels zijn dicts met sleutels `excl`, `btw_percentage`, `btw_code`
  - `totalen(regels: list[dict]) -> dict` met sleutels `excl`, `btw`, `incl`

- [ ] **Step 1: Write the failing test**

Create `nixfact_integration/nixfact_integration/tests/test_btw.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor BTW-categorieën en regelberekening."""

import unittest

from nixfact_integration.utils.btw import (
    NUL_CATEGORIEEN,
    BtwGroep,
    code_voor_categorie,
    groepeer_btw,
    regel_excl,
    totalen,
)


class TestCategorieCodes(unittest.TestCase):

    def test_standaard(self):
        self.assertEqual(code_voor_categorie("Standaard"), "S")

    def test_verlegd(self):
        self.assertEqual(code_voor_categorie("Verlegd"), "AE")

    def test_nultarief(self):
        self.assertEqual(code_voor_categorie("Nultarief"), "Z")

    def test_vrijgesteld(self):
        self.assertEqual(code_voor_categorie("Vrijgesteld"), "E")

    def test_onbekend_valt_terug_op_standaard(self):
        self.assertEqual(code_voor_categorie("Zomaar iets"), "S")

    def test_leeg_valt_terug_op_standaard(self):
        self.assertEqual(code_voor_categorie(""), "S")

    def test_nul_categorieen(self):
        self.assertEqual(NUL_CATEGORIEEN, frozenset({"AE", "Z", "E"}))


class TestRegelExcl(unittest.TestCase):

    def test_simpel(self):
        self.assertEqual(regel_excl(2, 50), 100.00)

    def test_afronding_halve_cent_omhoog(self):
        # 3 x 10.005 = 30.015 -> 30.02
        self.assertEqual(regel_excl(3, 10.005), 30.02)

    def test_nul_aantal(self):
        self.assertEqual(regel_excl(0, 99), 0.00)

    def test_negatief_bedrag_toegestaan(self):
        # Kortingsregel.
        self.assertEqual(regel_excl(1, -25), -25.00)


class TestGroepeerBtw(unittest.TestCase):

    def test_een_groep(self):
        regels = [
            {"excl": 100.00, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 50.00, "btw_percentage": 21, "btw_code": "S"},
        ]
        groepen = groepeer_btw(regels)
        self.assertEqual(groepen, [BtwGroep("S", 21.0, 150.00, 31.50)])

    def test_twee_percentages_apart(self):
        regels = [
            {"excl": 100.00, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 100.00, "btw_percentage": 9, "btw_code": "S"},
        ]
        groepen = groepeer_btw(regels)
        self.assertEqual(len(groepen), 2)
        self.assertEqual(groepen[0], BtwGroep("S", 9.0, 100.00, 9.00))
        self.assertEqual(groepen[1], BtwGroep("S", 21.0, 100.00, 21.00))

    def test_verlegd_krijgt_nul_btw(self):
        regels = [{"excl": 200.00, "btw_percentage": 0, "btw_code": "AE"}]
        self.assertEqual(groepeer_btw(regels), [BtwGroep("AE", 0.0, 200.00, 0.00)])

    def test_btw_berekend_over_groepstotaal_niet_per_regel(self):
        # Twee regels van 0.10 bij 21%: per regel 0.021 -> 0.02 elk = 0.04,
        # over het groepstotaal 0.20 -> 0.042 -> 0.04. Hier gelijk, maar bij
        # 0.05 + 0.05 loopt het uiteen: per regel 0.01+0.01=0.02, groep 0.02.
        regels = [
            {"excl": 0.05, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 0.05, "btw_percentage": 21, "btw_code": "S"},
        ]
        groepen = groepeer_btw(regels)
        self.assertEqual(groepen[0].btw, 0.02)

    def test_lege_regels(self):
        self.assertEqual(groepeer_btw([]), [])


class TestTotalen(unittest.TestCase):

    def test_gemengde_factuur(self):
        regels = [
            {"excl": 100.00, "btw_percentage": 21, "btw_code": "S"},
            {"excl": 100.00, "btw_percentage": 9, "btw_code": "S"},
            {"excl": 50.00, "btw_percentage": 0, "btw_code": "AE"},
        ]
        self.assertEqual(
            totalen(regels), {"excl": 250.00, "btw": 30.00, "incl": 280.00}
        )

    def test_leeg(self):
        self.assertEqual(totalen([]), {"excl": 0.00, "btw": 0.00, "incl": 0.00})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_btw.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'nixfact_integration.utils.btw'`

- [ ] **Step 3: Write minimal implementation**

Create `nixfact_integration/nixfact_integration/utils/btw.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""BTW-categorieën en regelberekening.

Puur rekenwerk: geen frappe-import, geen database. Dit is de enige plek
waar btw-bedragen worden uitgerekend, zodat het doctype, de UBL-builder
en de validator gegarandeerd op dezelfde getallen uitkomen.
"""

from __future__ import annotations

from dataclasses import dataclass

# Nederlandse label -> Peppol UNCL5305-code.
CATEGORIE_CODES: dict[str, str] = {
    "Standaard": "S",
    "Verlegd": "AE",
    "Nultarief": "Z",
    "Vrijgesteld": "E",
}

# Categorieën die verplicht 0% moeten hebben.
NUL_CATEGORIEEN: frozenset[str] = frozenset({"AE", "Z", "E"})

# Peppol eist een reden bij deze categorieën (BR-AE-10, BR-E-10, BR-Z-10).
VRIJSTELLING_REDEN: dict[str, str] = {
    "AE": "Btw verlegd",
    "E": "Vrijgesteld van btw",
    "Z": "Nultarief",
}


def _rond(waarde: float) -> float:
    """Rond af op centen, halve cent omhoog (niet bankers rounding)."""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(str(waarde)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def code_voor_categorie(label: str) -> str:
    """Vertaal een NL-categorielabel naar een Peppol-code, default 'S'."""
    return CATEGORIE_CODES.get((label or "").strip(), "S")


def regel_excl(aantal: float, eenheidsprijs: float) -> float:
    """Regeltotaal exclusief btw."""
    return _rond(float(aantal or 0) * float(eenheidsprijs or 0))


@dataclass(frozen=True)
class BtwGroep:
    """Eén btw-groep: unieke combinatie van categoriecode en percentage."""

    code: str
    percentage: float
    excl: float
    btw: float


def groepeer_btw(regels: list[dict]) -> list[BtwGroep]:
    """Groepeer regels per (code, percentage) en bereken btw per groep.

    Btw wordt berekend over het groepstotaal, niet per regel opgeteld —
    Peppol BR-CO-17 eist dat TaxAmount volgt uit TaxableAmount x rate.
    """
    buckets: dict[tuple[str, float], float] = {}
    for regel in regels:
        code = regel.get("btw_code") or "S"
        pct = float(regel.get("btw_percentage") or 0)
        sleutel = (code, pct)
        buckets[sleutel] = _rond(buckets.get(sleutel, 0.0) + float(regel["excl"]))

    resultaat = []
    for (code, pct), excl in sorted(buckets.items()):
        resultaat.append(BtwGroep(code, pct, excl, _rond(excl * pct / 100)))
    return resultaat


def totalen(regels: list[dict]) -> dict:
    """Factuurtotalen: excl, btw, incl."""
    groepen = groepeer_btw(regels)
    excl = _rond(sum(g.excl for g in groepen))
    btw = _rond(sum(g.btw for g in groepen))
    return {"excl": excl, "btw": btw, "incl": _rond(excl + btw)}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_btw.py -v
ruff check nixfact_integration/
```

Expected: 18 tests PASS, ruff geeft `All checks passed!`

- [ ] **Step 5: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
git add nixfact_integration/nixfact_integration/utils/btw.py \
        nixfact_integration/nixfact_integration/tests/test_btw.py
git commit -m "feat(btw): pure regelberekening en Peppol-btw-categorieën"
```

---

### Task 2: Child doctype NixFact Factuur Regel

Het datamodel. Vanaf hier heeft een factuur regels; de oude totaalvelden worden read-only en berekend.

**Files:**
- Create: `nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/__init__.py`
- Create: `nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/nixfact_factuur_regel.json`
- Create: `nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/nixfact_factuur_regel.py`
- Modify: `nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.json` (field_order regels 6-44, fields-array)
- Modify: `nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.py` (methode `bereken_bedragen`)
- Test: `nixfact_integration/nixfact_integration/tests/test_factuur_bedragen.py`

**Interfaces:**
- Consumes: `nixfact_integration.utils.btw.{code_voor_categorie, totalen, regel_excl}`
- Produces:
  - Child doctype `NixFact Factuur Regel` met velden: `omschrijving` (Data, reqd), `aantal` (Float, default 1), `eenheidsprijs` (Currency, reqd), `btw_categorie` (Select: `Standaard\nVerlegd\nNultarief\nVrijgesteld`, default Standaard), `btw_percentage` (Percent, default 21), `regel_excl` (Currency, read-only)
  - Veld `regels` (Table) op `NixFact Factuur`
  - `nixfact_integration.utils.btw`-gebaseerde functie `regels_als_dicts(doc) -> list[dict]` in `nixfact_factuur.py`

- [ ] **Step 1: Write the failing test**

Create `nixfact_integration/nixfact_integration/tests/test_factuur_bedragen.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de omzetting van factuurregels naar rekendicts."""

import unittest
from types import SimpleNamespace

from nixfact_integration.nixfact_integration.doctype.nixfact_factuur import (
    nixfact_factuur,
)


def _regel(omschrijving, aantal, prijs, categorie, pct):
    return SimpleNamespace(
        omschrijving=omschrijving,
        aantal=aantal,
        eenheidsprijs=prijs,
        btw_categorie=categorie,
        btw_percentage=pct,
        regel_excl=None,
    )


class TestRegelsAlsDicts(unittest.TestCase):

    def test_vertaalt_categorie_naar_code(self):
        doc = SimpleNamespace(regels=[_regel("Advies", 1, 100, "Verlegd", 0)])
        result = nixfact_factuur.regels_als_dicts(doc)
        self.assertEqual(result[0]["btw_code"], "AE")

    def test_berekent_regeltotaal(self):
        doc = SimpleNamespace(regels=[_regel("Uren", 8, 125, "Standaard", 21)])
        result = nixfact_factuur.regels_als_dicts(doc)
        self.assertEqual(result[0]["excl"], 1000.00)

    def test_schrijft_regeltotaal_terug_op_de_regel(self):
        regel = _regel("Uren", 8, 125, "Standaard", 21)
        doc = SimpleNamespace(regels=[regel])
        nixfact_factuur.regels_als_dicts(doc)
        self.assertEqual(regel.regel_excl, 1000.00)

    def test_geen_regels(self):
        doc = SimpleNamespace(regels=[])
        self.assertEqual(nixfact_factuur.regels_als_dicts(doc), [])

    def test_regels_attribuut_ontbreekt(self):
        doc = SimpleNamespace()
        self.assertEqual(nixfact_factuur.regels_als_dicts(doc), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_factuur_bedragen.py -v
```

Expected: FAIL — `AttributeError: module 'nixfact_factuur' has no attribute 'regels_als_dicts'`

- [ ] **Step 3: Maak het child doctype aan**

Create `nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/__init__.py` (leeg bestand).

Create `nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/nixfact_factuur_regel.json`:

```json
{
 "actions": [],
 "creation": "2026-07-21 12:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "istable": 1,
 "field_order": [
  "omschrijving",
  "aantal",
  "eenheidsprijs",
  "btw_categorie",
  "btw_percentage",
  "regel_excl"
 ],
 "fields": [
  {
   "fieldname": "omschrijving",
   "fieldtype": "Data",
   "label": "Omschrijving",
   "reqd": 1,
   "in_list_view": 1,
   "columns": 4
  },
  {
   "default": "1",
   "fieldname": "aantal",
   "fieldtype": "Float",
   "label": "Aantal",
   "reqd": 1,
   "in_list_view": 1,
   "columns": 1
  },
  {
   "fieldname": "eenheidsprijs",
   "fieldtype": "Currency",
   "label": "Prijs per stuk",
   "reqd": 1,
   "in_list_view": 1,
   "columns": 2
  },
  {
   "default": "Standaard",
   "fieldname": "btw_categorie",
   "fieldtype": "Select",
   "label": "BTW-categorie",
   "options": "Standaard\nVerlegd\nNultarief\nVrijgesteld",
   "reqd": 1,
   "in_list_view": 1,
   "columns": 2
  },
  {
   "default": "21",
   "fieldname": "btw_percentage",
   "fieldtype": "Percent",
   "label": "BTW %",
   "in_list_view": 1,
   "columns": 1
  },
  {
   "fieldname": "regel_excl",
   "fieldtype": "Currency",
   "label": "Totaal excl. BTW",
   "read_only": 1,
   "in_list_view": 1,
   "columns": 2
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-07-21 12:00:00.000000",
 "modified_by": "Administrator",
 "module": "NixFact Integration",
 "name": "NixFact Factuur Regel",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "idx",
 "sort_order": "ASC",
 "states": [],
 "track_changes": 0
}
```

Create `nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/nixfact_factuur_regel.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

from __future__ import annotations

from frappe.model.document import Document


class NixFactFactuurRegel(Document):
    """Eén regel op een factuur. Berekening gebeurt op de parent."""

    pass
```

- [ ] **Step 4: Voeg het regels-veld toe aan NixFact Factuur**

In `nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.json`:

Vervang in `field_order` de regel `"section_break_bedragen",` door:

```json
  "section_break_regels",
  "regels",
  "section_break_bedragen",
```

Voeg in de `fields`-array, direct vóór het object met `"fieldname": "section_break_bedragen"`, deze twee objecten toe:

```json
  {
   "fieldname": "section_break_regels",
   "fieldtype": "Section Break",
   "label": "Regels"
  },
  {
   "fieldname": "regels",
   "fieldtype": "Table",
   "label": "Factuurregels",
   "options": "NixFact Factuur Regel",
   "reqd": 1
  },
```

Wijzig in hetzelfde bestand het veld `bedrag_excl_btw`: vervang `"reqd": 1` door `"read_only": 1`, en voeg `"read_only": 1` toe aan `btw_percentage`. De totalen komen voortaan uit de regels.

Werk ook `"modified"` bij naar `"2026-07-21 12:00:00.000000"` zodat `bench migrate` de wijziging oppikt.

- [ ] **Step 5: Write minimal implementation**

In `nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.py`, voeg boven de klasse toe:

```python
from nixfact_integration.utils.btw import code_voor_categorie, regel_excl, totalen


def regels_als_dicts(doc) -> list[dict]:
    """Zet de regels van een factuur om naar rekendicts voor utils.btw.

    Schrijft en passant het regeltotaal terug op elke regel, zodat de
    gebruiker het in de grid ziet.
    """
    resultaat = []
    for regel in getattr(doc, "regels", None) or []:
        excl = regel_excl(regel.aantal, regel.eenheidsprijs)
        regel.regel_excl = excl
        resultaat.append(
            {
                "omschrijving": regel.omschrijving,
                "aantal": float(regel.aantal or 0),
                "eenheidsprijs": float(regel.eenheidsprijs or 0),
                "excl": excl,
                "btw_percentage": float(regel.btw_percentage or 0),
                "btw_code": code_voor_categorie(regel.btw_categorie),
            }
        )
    return resultaat
```

Vervang de methode `bereken_bedragen` volledig door:

```python
    def bereken_bedragen(self) -> None:
        """Compute BTW + totalen uit de regels, currency-safe."""
        regels = regels_als_dicts(self)
        som = totalen(regels)
        self.bedrag_excl_btw = som["excl"]
        self.btw_bedrag = som["btw"]
        self.bedrag_incl_btw = som["incl"]
        self.openstaand_bedrag = flt(
            som["incl"] - flt(self.betaald_bedrag or 0, 2), 2
        )
        # btw_percentage blijft als samenvatting staan: het hoogste
        # gehanteerde tarief. Puur informatief; UBL gebruikt de groepen.
        self.btw_percentage = max(
            (r["btw_percentage"] for r in regels), default=0
        )
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_factuur_bedragen.py \
  nixfact_integration/nixfact_integration/tests/test_btw.py -v
ruff check nixfact_integration/
```

Expected: 23 tests PASS, ruff `All checks passed!`

- [ ] **Step 7: Controleer het JSON-bestand op geldigheid**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
python -c "import json,sys; [json.load(open(p)) for p in sys.argv[1:]]; print('JSON OK')" \
  nixfact_integration/nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.json \
  nixfact_integration/nixfact_integration/nixfact_integration/doctype/nixfact_factuur_regel/nixfact_factuur_regel.json
```

Expected: `JSON OK`

- [ ] **Step 8: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
git add nixfact_integration/nixfact_integration/nixfact_integration/doctype/ \
        nixfact_integration/nixfact_integration/tests/test_factuur_bedragen.py
git commit -m "feat(factuur): child doctype NixFact Factuur Regel met btw per regel"
```

---

### Task 3: Migratiepatch voor bestaande facturen

Zonder deze patch hebben bestaande facturen nul regels en worden hun totalen bij de eerstvolgende opslag op 0 gezet. Dit moet vóór productie-deploy draaien.

**Files:**
- Create: `nixfact_integration/nixfact_integration/patches/__init__.py`
- Create: `nixfact_integration/nixfact_integration/patches/v1_0/__init__.py`
- Create: `nixfact_integration/nixfact_integration/patches/v1_0/factuur_regels_migratie.py`
- Modify: `nixfact_integration/nixfact_integration/patches.txt` (nu leeg)
- Test: `nixfact_integration/nixfact_integration/tests/test_factuur_regels_migratie.py`

**Interfaces:**
- Consumes: `NixFact Factuur`-velden `bedrag_excl_btw`, `btw_percentage`, `referentie`, `factuurnummer`
- Produces: `bepaal_migratie_regel(factuur: dict) -> dict` — puur; de `execute()` eromheen is frappe-afhankelijk en wordt niet in CI getest

- [ ] **Step 1: Write the failing test**

Create `nixfact_integration/nixfact_integration/tests/test_factuur_regels_migratie.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de migratie van bedragfacturen naar regelfacturen."""

import unittest

from nixfact_integration.patches.v1_0.factuur_regels_migratie import (
    bepaal_migratie_regel,
)


class TestBepaalMigratieRegel(unittest.TestCase):

    def test_bedrag_wordt_eenheidsprijs(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 250.00, "btw_percentage": 21}
        )
        self.assertEqual(regel["eenheidsprijs"], 250.00)
        self.assertEqual(regel["aantal"], 1)

    def test_percentage_wordt_overgenomen(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 9}
        )
        self.assertEqual(regel["btw_percentage"], 9)
        self.assertEqual(regel["btw_categorie"], "Standaard")

    def test_nul_procent_wordt_nultarief(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 0}
        )
        self.assertEqual(regel["btw_categorie"], "Nultarief")

    def test_omschrijving_uit_referentie(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 21,
             "referentie": "Project Alpha"}
        )
        self.assertEqual(regel["omschrijving"], "Project Alpha")

    def test_omschrijving_valt_terug_op_factuurnummer(self):
        regel = bepaal_migratie_regel(
            {"bedrag_excl_btw": 100.00, "btw_percentage": 21,
             "factuurnummer": "2026-0001"}
        )
        self.assertEqual(regel["omschrijving"], "Factuur 2026-0001")

    def test_omschrijving_laatste_redmiddel(self):
        regel = bepaal_migratie_regel({"bedrag_excl_btw": 100.00})
        self.assertEqual(regel["omschrijving"], "Gemigreerde factuurregel")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_factuur_regels_migratie.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'nixfact_integration.patches'`

- [ ] **Step 3: Write minimal implementation**

Create `nixfact_integration/nixfact_integration/patches/__init__.py` en `nixfact_integration/nixfact_integration/patches/v1_0/__init__.py` (beide leeg).

Create `nixfact_integration/nixfact_integration/patches/v1_0/factuur_regels_migratie.py`:

```python
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
```

- [ ] **Step 4: Registreer de patch**

Vervang de volledige inhoud van `nixfact_integration/nixfact_integration/patches.txt` (nu leeg) door:

```
[post_model_sync]
nixfact_integration.patches.v1_0.factuur_regels_migratie
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_factuur_regels_migratie.py -v
ruff check nixfact_integration/
```

Expected: 6 tests PASS, ruff `All checks passed!`

- [ ] **Step 6: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
git add nixfact_integration/nixfact_integration/patches \
        nixfact_integration/nixfact_integration/patches.txt \
        nixfact_integration/nixfact_integration/tests/test_factuur_regels_migratie.py
git commit -m "feat(patch): migreer bestaande facturen naar één factuurregel"
```

---

### Task 4: UBL-datamodel en pure builder

Hier verdwijnt de eenregelige UBL. De builder krijgt een puur datamodel als invoer en is daarmee volledig in CI te testen — de kern van dit plan.

**Files:**
- Create: `nixfact_integration/nixfact_integration/utils/ubl_model.py`
- Create: `nixfact_integration/nixfact_integration/utils/ubl_builder.py`
- Test: `nixfact_integration/nixfact_integration/tests/test_ubl_builder.py`

**Interfaces:**
- Consumes: `nixfact_integration.utils.btw.{BtwGroep, groepeer_btw, totalen, NUL_CATEGORIEEN, VRIJSTELLING_REDEN}`
- Produces:
  - `UBLPartij(naam, btw_nummer, straat, extra_straat, plaats, postcode, landcode, email, telefoon)` — alle velden `str`, default `""`
  - `UBLRegel(omschrijving, aantal, eenheidsprijs, excl, btw_percentage, btw_code)`
  - `UBLFactuur(nummer, factuurdatum, vervaldatum, referentie, leverancier, afnemer, regels, iban, bic, betaald_bedrag, opmerkingen)`
  - `UBLFactuur.btw_groepen() -> list[BtwGroep]`, `UBLFactuur.totalen() -> dict`
  - `build_invoice_xml(factuur: UBLFactuur) -> str`
  - herbruikte constanten `NS_INVOICE`, `NS_CAC`, `NS_CBC`, `NSMAP`, `CUSTOMIZATION_ID`, `PROFILE_ID` en helpers `_cac`, `_cbc` verhuizen naar `ubl_builder.py`

- [ ] **Step 1: Write the failing test**

Create `nixfact_integration/nixfact_integration/tests/test_ubl_builder.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de pure UBL 2.1 / Peppol BIS 3.0 builder."""

import unittest

from lxml import etree

from nixfact_integration.utils.ubl_builder import (
    NS_CAC,
    NS_CBC,
    build_invoice_xml,
)
from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel

NS = {"cac": NS_CAC, "cbc": NS_CBC}


def _partij(naam="Aldewereld Consultancy", btw="NL002168402B79"):
    return UBLPartij(
        naam=naam,
        btw_nummer=btw,
        straat="Prunuslaan 53",
        plaats="Amstelveen",
        postcode="1185 KT",
        landcode="NL",
        email="ikben@nickaldewereld.nl",
    )


def _factuur(regels):
    return UBLFactuur(
        nummer="2026-0042",
        factuurdatum="2026-07-21",
        vervaldatum="2026-08-04",
        referentie="PO-9001",
        leverancier=_partij(),
        afnemer=_partij("Klant B.V.", "NL999999999B01"),
        regels=regels,
        iban="NL02ABNA0123456789",
        bic="ABNANL2A",
    )


def _xml(factuur):
    return etree.fromstring(build_invoice_xml(factuur).encode("utf-8"))


class TestMeerdereRegels(unittest.TestCase):

    def setUp(self):
        self.doc = _xml(
            _factuur(
                [
                    UBLRegel("Advies", 8, 125.00, 1000.00, 21, "S"),
                    UBLRegel("Licentie", 1, 200.00, 200.00, 9, "S"),
                ]
            )
        )

    def test_twee_invoice_lines(self):
        lijnen = self.doc.findall("cac:InvoiceLine", NS)
        self.assertEqual(len(lijnen), 2)

    def test_lijn_ids_zijn_oplopend(self):
        ids = [el.text for el in self.doc.findall("cac:InvoiceLine/cbc:ID", NS)]
        self.assertEqual(ids, ["1", "2"])

    def test_lijn_bedragen(self):
        bedragen = [
            el.text
            for el in self.doc.findall(
                "cac:InvoiceLine/cbc:LineExtensionAmount", NS
            )
        ]
        self.assertEqual(bedragen, ["1000.00", "200.00"])

    def test_lijn_omschrijving(self):
        namen = [
            el.text
            for el in self.doc.findall("cac:InvoiceLine/cac:Item/cbc:Name", NS)
        ]
        self.assertEqual(namen, ["Advies", "Licentie"])

    def test_aantal_per_regel(self):
        aantallen = [
            el.text
            for el in self.doc.findall(
                "cac:InvoiceLine/cbc:InvoicedQuantity", NS
            )
        ]
        self.assertEqual(aantallen, ["8", "1"])

    def test_eenheidsprijs_per_regel(self):
        prijzen = [
            el.text
            for el in self.doc.findall(
                "cac:InvoiceLine/cac:Price/cbc:PriceAmount", NS
            )
        ]
        self.assertEqual(prijzen, ["125.00", "200.00"])

    def test_twee_tax_subtotals(self):
        subs = self.doc.findall("cac:TaxTotal/cac:TaxSubtotal", NS)
        self.assertEqual(len(subs), 2)

    def test_tax_amount_is_som_van_groepen(self):
        bedrag = self.doc.find("cac:TaxTotal/cbc:TaxAmount", NS).text
        # 21% over 1000 = 210.00, 9% over 200 = 18.00
        self.assertEqual(bedrag, "228.00")

    def test_monetary_total(self):
        pad = "cac:LegalMonetaryTotal/cbc:{}"
        self.assertEqual(
            self.doc.find(pad.format("LineExtensionAmount"), NS).text, "1200.00"
        )
        self.assertEqual(
            self.doc.find(pad.format("TaxInclusiveAmount"), NS).text, "1428.00"
        )
        self.assertEqual(
            self.doc.find(pad.format("PayableAmount"), NS).text, "1428.00"
        )


class TestBtwCategorieen(unittest.TestCase):

    def test_verlegd_krijgt_code_ae(self):
        doc = _xml(_factuur([UBLRegel("Advies", 1, 500.00, 500.00, 0, "AE")]))
        code = doc.find(
            "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:ID", NS
        ).text
        self.assertEqual(code, "AE")

    def test_verlegd_krijgt_vrijstellingsreden(self):
        doc = _xml(_factuur([UBLRegel("Advies", 1, 500.00, 500.00, 0, "AE")]))
        reden = doc.find(
            "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory"
            "/cbc:TaxExemptionReason",
            NS,
        )
        self.assertIsNotNone(reden)
        self.assertEqual(reden.text, "Btw verlegd")

    def test_standaard_krijgt_geen_vrijstellingsreden(self):
        doc = _xml(_factuur([UBLRegel("Advies", 1, 500.00, 500.00, 21, "S")]))
        reden = doc.find(
            "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory"
            "/cbc:TaxExemptionReason",
            NS,
        )
        self.assertIsNone(reden)

    def test_regel_krijgt_eigen_classified_tax_category(self):
        doc = _xml(
            _factuur(
                [
                    UBLRegel("A", 1, 100.00, 100.00, 21, "S"),
                    UBLRegel("B", 1, 100.00, 100.00, 0, "AE"),
                ]
            )
        )
        codes = [
            el.text
            for el in doc.findall(
                "cac:InvoiceLine/cac:Item/cac:ClassifiedTaxCategory/cbc:ID", NS
            )
        ]
        self.assertEqual(codes, ["S", "AE"])


class TestKopvelden(unittest.TestCase):

    def setUp(self):
        self.doc = _xml(_factuur([UBLRegel("A", 1, 100.00, 100.00, 21, "S")]))

    def test_customization_id(self):
        el = self.doc.find("cbc:CustomizationID", NS)
        self.assertIn("urn:cen.eu:en16931:2017", el.text)

    def test_factuurnummer(self):
        self.assertEqual(self.doc.find("cbc:ID", NS).text, "2026-0042")

    def test_type_code_380(self):
        self.assertEqual(self.doc.find("cbc:InvoiceTypeCode", NS).text, "380")

    def test_valuta_eur(self):
        self.assertEqual(
            self.doc.find("cbc:DocumentCurrencyCode", NS).text, "EUR"
        )

    def test_iban_in_payment_means(self):
        el = self.doc.find(
            "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID", NS
        )
        self.assertEqual(el.text, "NL02ABNA0123456789")


class TestRobuustheid(unittest.TestCase):

    def test_controlekarakters_worden_gestript(self):
        doc = _xml(
            _factuur([UBLRegel("Ad\x00vies", 1, 100.00, 100.00, 21, "S")])
        )
        naam = doc.find("cac:InvoiceLine/cac:Item/cbc:Name", NS).text
        self.assertEqual(naam, "Advies")

    def test_deelbetaling_geeft_prepaid_amount(self):
        factuur = _factuur([UBLRegel("A", 1, 100.00, 100.00, 21, "S")])
        factuur.betaald_bedrag = 21.00
        doc = _xml(factuur)
        self.assertEqual(
            doc.find("cac:LegalMonetaryTotal/cbc:PrepaidAmount", NS).text,
            "21.00",
        )
        self.assertEqual(
            doc.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS).text,
            "100.00",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_ubl_builder.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'nixfact_integration.utils.ubl_builder'`

- [ ] **Step 3: Write the data model**

Create `nixfact_integration/nixfact_integration/utils/ubl_model.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Datamodel voor een uitgaande e-factuur.

Bewust vrij van frappe: de builder en de validator werken uitsluitend op
deze dataclasses, waardoor ze in CI volledig getest kunnen worden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nixfact_integration.utils.btw import BtwGroep, groepeer_btw, totalen


@dataclass
class UBLPartij:
    """Leverancier of afnemer."""

    naam: str = ""
    btw_nummer: str = ""
    straat: str = ""
    extra_straat: str = ""
    plaats: str = ""
    postcode: str = ""
    landcode: str = "NL"
    email: str = ""
    telefoon: str = ""


@dataclass
class UBLRegel:
    """Eén factuurregel, al doorgerekend."""

    omschrijving: str
    aantal: float
    eenheidsprijs: float
    excl: float
    btw_percentage: float
    btw_code: str = "S"


@dataclass
class UBLFactuur:
    """Een complete uitgaande factuur."""

    nummer: str
    factuurdatum: str
    vervaldatum: str = ""
    referentie: str = ""
    leverancier: UBLPartij = field(default_factory=UBLPartij)
    afnemer: UBLPartij = field(default_factory=UBLPartij)
    regels: list[UBLRegel] = field(default_factory=list)
    iban: str = ""
    bic: str = ""
    betaald_bedrag: float = 0.0
    opmerkingen: str = ""

    def _als_dicts(self) -> list[dict]:
        return [
            {
                "excl": r.excl,
                "btw_percentage": r.btw_percentage,
                "btw_code": r.btw_code,
            }
            for r in self.regels
        ]

    def btw_groepen(self) -> list[BtwGroep]:
        return groepeer_btw(self._als_dicts())

    def totalen(self) -> dict:
        return totalen(self._als_dicts())
```

- [ ] **Step 4: Write the builder**

Create `nixfact_integration/nixfact_integration/utils/ubl_builder.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""UBL 2.1 / Peppol BIS 3.0 XML-builder.

Puur: neemt een UBLFactuur en geeft XML terug. Geen frappe, geen IO.
"""

from __future__ import annotations

import re

from lxml import etree

from nixfact_integration.utils.btw import NUL_CATEGORIEEN, VRIJSTELLING_REDEN
from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel

# UBL 2.1 namespaces.
NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

NSMAP = {None: NS_INVOICE, "cac": NS_CAC, "cbc": NS_CBC}

# Peppol BIS 3.0 identifiers.
CUSTOMIZATION_ID = (
    "urn:cen.eu:en16931:2017"
    "#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
)
PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

VALUTA = "EUR"

# Strip XML 1.0 illegal control chars (alles < 0x20 behalve TAB/LF/CR).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _cac(tag: str) -> str:
    return f"{{{NS_CAC}}}{tag}"


def _cbc(tag: str) -> str:
    return f"{{{NS_CBC}}}{tag}"


def _xml_safe(value: object) -> str:
    if value is None:
        return ""
    return _CONTROL_CHARS_RE.sub("", str(value))


def _add_cbc(parent, tag: str, text, **attribs):
    """Voeg een CBC-element toe; slaat lege waarden over."""
    safe = _xml_safe(text)
    if not safe:
        return None
    el = etree.SubElement(parent, _cbc(tag), **attribs)
    el.text = safe
    return el


def _add_cbc_required(parent, tag: str, text, **attribs):
    """Voeg een CBC-element toe, ook als het leeg is."""
    el = etree.SubElement(parent, _cbc(tag), **attribs)
    el.text = _xml_safe(text)
    return el


def _bedrag(waarde: float) -> str:
    return f"{float(waarde):.2f}"


def _aantal(waarde: float) -> str:
    """Formatteer aantallen zonder onnodige decimalen (8.0 -> '8')."""
    getal = float(waarde)
    return str(int(getal)) if getal == int(getal) else f"{getal:.2f}"


def build_invoice_xml(factuur: UBLFactuur) -> str:
    """Bouw de volledige Invoice-XML voor een UBLFactuur."""
    invoice = etree.Element("Invoice", nsmap=NSMAP)

    _add_cbc(invoice, "CustomizationID", CUSTOMIZATION_ID)
    _add_cbc(invoice, "ProfileID", PROFILE_ID)
    _add_cbc(invoice, "ID", factuur.nummer)
    _add_cbc(invoice, "IssueDate", factuur.factuurdatum)
    if factuur.vervaldatum:
        _add_cbc(invoice, "DueDate", factuur.vervaldatum)
    _add_cbc(invoice, "InvoiceTypeCode", "380")
    _add_cbc(invoice, "DocumentCurrencyCode", VALUTA)
    if factuur.referentie:
        _add_cbc(invoice, "BuyerReference", factuur.referentie)

    leverancier = etree.SubElement(invoice, _cac("AccountingSupplierParty"))
    _build_party(leverancier, factuur.leverancier)

    afnemer = etree.SubElement(invoice, _cac("AccountingCustomerParty"))
    _build_party(afnemer, factuur.afnemer)

    if factuur.iban:
        _build_payment_means(invoice, factuur)

    _build_tax_total(invoice, factuur)
    _build_monetary_total(invoice, factuur)

    for index, regel in enumerate(factuur.regels, start=1):
        _build_invoice_line(invoice, index, regel)

    return etree.tostring(
        invoice, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    ).decode("utf-8")


def _build_party(parent_element, partij: UBLPartij) -> None:
    """Bouw een Party-blok met de Peppol BIS 3.0 verplichte onderdelen."""
    party = etree.SubElement(parent_element, _cac("Party"))

    btw = (partij.btw_nummer or "").strip()
    if btw:
        endpoint = etree.SubElement(party, _cbc("EndpointID"), schemeID="9944")
        endpoint.text = _xml_safe(btw)

    naam_el = etree.SubElement(party, _cac("PartyName"))
    _add_cbc_required(naam_el, "Name", partij.naam)

    postal = etree.SubElement(party, _cac("PostalAddress"))
    _add_cbc(postal, "StreetName", partij.straat)
    _add_cbc(postal, "AdditionalStreetName", partij.extra_straat)
    _add_cbc(postal, "CityName", partij.plaats)
    _add_cbc(postal, "PostalZone", partij.postcode)
    land = etree.SubElement(postal, _cac("Country"))
    _add_cbc_required(
        land,
        "IdentificationCode",
        (partij.landcode or "NL").upper(),
        listID="ISO3166-1:Alpha2",
    )

    if btw:
        tax_scheme_el = etree.SubElement(party, _cac("PartyTaxScheme"))
        _add_cbc_required(tax_scheme_el, "CompanyID", btw)
        scheme = etree.SubElement(tax_scheme_el, _cac("TaxScheme"))
        _add_cbc_required(scheme, "ID", "VAT")

    legal = etree.SubElement(party, _cac("PartyLegalEntity"))
    _add_cbc_required(legal, "RegistrationName", partij.naam)
    if btw:
        _add_cbc(legal, "CompanyID", btw)

    contact = etree.SubElement(party, _cac("Contact"))
    _add_cbc(contact, "Name", partij.naam)
    _add_cbc(contact, "Telephone", partij.telefoon)
    _add_cbc(contact, "ElectronicMail", partij.email)
    if len(contact) == 0:
        party.remove(contact)


def _build_payment_means(invoice, factuur: UBLFactuur) -> None:
    pm = etree.SubElement(invoice, _cac("PaymentMeans"))
    _add_cbc_required(pm, "PaymentMeansCode", "30")  # Credit transfer
    if factuur.nummer:
        _add_cbc(pm, "PaymentID", factuur.nummer)

    payee = etree.SubElement(pm, _cac("PayeeFinancialAccount"))
    _add_cbc_required(payee, "ID", factuur.iban.replace(" ", "").upper())
    if factuur.bic:
        branch = etree.SubElement(payee, _cac("FinancialInstitutionBranch"))
        _add_cbc_required(branch, "ID", factuur.bic)


def _build_tax_total(invoice, factuur: UBLFactuur) -> None:
    """Eén TaxSubtotal per btw-groep — vereist door BR-CO-18."""
    groepen = factuur.btw_groepen()
    som = factuur.totalen()

    tax_total = etree.SubElement(invoice, _cac("TaxTotal"))
    _add_cbc_required(
        tax_total, "TaxAmount", _bedrag(som["btw"]), currencyID=VALUTA
    )

    for groep in groepen:
        subtotal = etree.SubElement(tax_total, _cac("TaxSubtotal"))
        _add_cbc_required(
            subtotal, "TaxableAmount", _bedrag(groep.excl), currencyID=VALUTA
        )
        _add_cbc_required(
            subtotal, "TaxAmount", _bedrag(groep.btw), currencyID=VALUTA
        )

        categorie = etree.SubElement(subtotal, _cac("TaxCategory"))
        _add_cbc_required(categorie, "ID", groep.code)
        _add_cbc_required(categorie, "Percent", f"{groep.percentage:.2f}")
        if groep.code in NUL_CATEGORIEEN:
            _add_cbc(
                categorie,
                "TaxExemptionReason",
                VRIJSTELLING_REDEN.get(groep.code, ""),
            )
        scheme = etree.SubElement(categorie, _cac("TaxScheme"))
        _add_cbc_required(scheme, "ID", "VAT")


def _build_monetary_total(invoice, factuur: UBLFactuur) -> None:
    som = factuur.totalen()
    betaald = float(factuur.betaald_bedrag or 0)
    te_betalen = som["incl"] - betaald

    total = etree.SubElement(invoice, _cac("LegalMonetaryTotal"))
    _add_cbc_required(
        total, "LineExtensionAmount", _bedrag(som["excl"]), currencyID=VALUTA
    )
    _add_cbc_required(
        total, "TaxExclusiveAmount", _bedrag(som["excl"]), currencyID=VALUTA
    )
    _add_cbc_required(
        total, "TaxInclusiveAmount", _bedrag(som["incl"]), currencyID=VALUTA
    )
    if betaald > 0:
        _add_cbc_required(
            total, "PrepaidAmount", _bedrag(betaald), currencyID=VALUTA
        )
    _add_cbc_required(
        total, "PayableAmount", _bedrag(te_betalen), currencyID=VALUTA
    )


def _build_invoice_line(invoice, index: int, regel: UBLRegel) -> None:
    line = etree.SubElement(invoice, _cac("InvoiceLine"))
    _add_cbc_required(line, "ID", str(index))
    _add_cbc_required(
        line, "InvoicedQuantity", _aantal(regel.aantal), unitCode="EA"
    )
    _add_cbc_required(
        line, "LineExtensionAmount", _bedrag(regel.excl), currencyID=VALUTA
    )

    item = etree.SubElement(line, _cac("Item"))
    _add_cbc_required(item, "Name", regel.omschrijving)

    item_tax = etree.SubElement(item, _cac("ClassifiedTaxCategory"))
    _add_cbc_required(item_tax, "ID", regel.btw_code)
    _add_cbc_required(item_tax, "Percent", f"{regel.btw_percentage:.2f}")
    scheme = etree.SubElement(item_tax, _cac("TaxScheme"))
    _add_cbc_required(scheme, "ID", "VAT")

    price = etree.SubElement(line, _cac("Price"))
    _add_cbc_required(
        price, "PriceAmount", _bedrag(regel.eenheidsprijs), currencyID=VALUTA
    )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_ubl_builder.py -v
ruff check nixfact_integration/
```

Expected: 20 tests PASS, ruff `All checks passed!`

- [ ] **Step 6: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
git add nixfact_integration/nixfact_integration/utils/ubl_model.py \
        nixfact_integration/nixfact_integration/utils/ubl_builder.py \
        nixfact_integration/nixfact_integration/tests/test_ubl_builder.py
git commit -m "feat(ubl): puur datamodel en meerregelige Peppol BIS 3.0 builder"
```

---

### Task 5: Validator met Nederlandse meldingen

Blokkeert ongeldige facturen vóór verzending. Dit is het onderdeel dat supportvragen bij een administratiekantoor voorkomt.

**Files:**
- Create: `nixfact_integration/nixfact_integration/utils/ubl_validatie.py`
- Test: `nixfact_integration/nixfact_integration/tests/test_ubl_validatie.py`

**Interfaces:**
- Consumes: `nixfact_integration.utils.ubl_model.UBLFactuur`, `nixfact_integration.utils.btw.NUL_CATEGORIEEN`
- Produces:
  - `class Fout` (frozen dataclass) met velden `regel: str` (BR-code) en `melding: str` (Nederlands)
  - `valideer(factuur: UBLFactuur) -> list[Fout]`

- [ ] **Step 1: Write the failing test**

Create `nixfact_integration/nixfact_integration/tests/test_ubl_validatie.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de Peppol-validatie met Nederlandse meldingen."""

import unittest

from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel
from nixfact_integration.utils.ubl_validatie import valideer


def _geldige_factuur():
    partij = UBLPartij(
        naam="Aldewereld Consultancy",
        btw_nummer="NL002168402B79",
        straat="Prunuslaan 53",
        plaats="Amstelveen",
        postcode="1185 KT",
        landcode="NL",
    )
    afnemer = UBLPartij(
        naam="Klant B.V.",
        btw_nummer="NL999999999B01",
        straat="Dorpsstraat 1",
        plaats="Utrecht",
        postcode="3511 AA",
        landcode="NL",
    )
    return UBLFactuur(
        nummer="2026-0042",
        factuurdatum="2026-07-21",
        vervaldatum="2026-08-04",
        leverancier=partij,
        afnemer=afnemer,
        regels=[UBLRegel("Advies", 8, 125.00, 1000.00, 21, "S")],
        iban="NL02ABNA0123456789",
    )


def _codes(fouten):
    return {f.regel for f in fouten}


class TestGeldigeFactuur(unittest.TestCase):

    def test_geen_fouten(self):
        self.assertEqual(valideer(_geldige_factuur()), [])


class TestVerplichteVelden(unittest.TestCase):

    def test_nummer_ontbreekt(self):
        f = _geldige_factuur()
        f.nummer = ""
        self.assertIn("BR-02", _codes(valideer(f)))

    def test_datum_ontbreekt(self):
        f = _geldige_factuur()
        f.factuurdatum = ""
        self.assertIn("BR-03", _codes(valideer(f)))

    def test_geen_regels(self):
        f = _geldige_factuur()
        f.regels = []
        self.assertIn("BR-16", _codes(valideer(f)))

    def test_leveranciersnaam_ontbreekt(self):
        f = _geldige_factuur()
        f.leverancier.naam = ""
        self.assertIn("BR-06", _codes(valideer(f)))

    def test_afnemernaam_ontbreekt(self):
        f = _geldige_factuur()
        f.afnemer.naam = ""
        self.assertIn("BR-07", _codes(valideer(f)))

    def test_leveranciersadres_ontbreekt(self):
        f = _geldige_factuur()
        f.leverancier.plaats = ""
        self.assertIn("BR-08", _codes(valideer(f)))

    def test_afnemerland_ontbreekt(self):
        f = _geldige_factuur()
        f.afnemer.landcode = ""
        self.assertIn("BR-09", _codes(valideer(f)))


class TestBtwRegels(unittest.TestCase):

    def test_verlegd_met_percentage_is_fout(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 21, "AE")]
        self.assertIn("BR-AE-01", _codes(valideer(f)))

    def test_standaard_zonder_percentage_is_fout(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 0, "S")]
        self.assertIn("BR-S-01", _codes(valideer(f)))

    def test_onbekende_categorie_is_fout(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 21, "X")]
        self.assertIn("BR-CL-01", _codes(valideer(f)))

    def test_verlegd_zonder_btw_nummer_afnemer_is_fout(self):
        f = _geldige_factuur()
        f.afnemer.btw_nummer = ""
        f.regels = [UBLRegel("Advies", 1, 100.00, 100.00, 0, "AE")]
        self.assertIn("BR-AE-09", _codes(valideer(f)))


class TestRegelInhoud(unittest.TestCase):

    def test_regel_zonder_omschrijving(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("", 1, 100.00, 100.00, 21, "S")]
        self.assertIn("BR-25", _codes(valideer(f)))

    def test_regeltotaal_klopt_niet_met_aantal_maal_prijs(self):
        f = _geldige_factuur()
        f.regels = [UBLRegel("Advies", 2, 100.00, 999.00, 21, "S")]
        self.assertIn("BR-CO-04", _codes(valideer(f)))


class TestMeldingen(unittest.TestCase):

    def test_melding_is_nederlands_en_noemt_het_veld(self):
        f = _geldige_factuur()
        f.nummer = ""
        melding = valideer(f)[0].melding
        self.assertIn("factuurnummer", melding.lower())

    def test_regelfout_noemt_het_regelnummer(self):
        f = _geldige_factuur()
        f.regels = [
            UBLRegel("Advies", 1, 100.00, 100.00, 21, "S"),
            UBLRegel("", 1, 100.00, 100.00, 21, "S"),
        ]
        fouten = [f_ for f_ in valideer(f) if f_.regel == "BR-25"]
        self.assertIn("regel 2", fouten[0].melding.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_ubl_validatie.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'nixfact_integration.utils.ubl_validatie'`

- [ ] **Step 3: Write minimal implementation**

Create `nixfact_integration/nixfact_integration/utils/ubl_validatie.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Validatie van een UBLFactuur tegen de belangrijkste EN16931-regels.

Doel is niet volledige schematron-dekking maar het afvangen van de fouten
die in de praktijk voorkomen, met een melding die een boekhouder begrijpt.
De ontvangende access point valideert alsnog volledig; dit voorkomt dat
een factuur daar pas sneuvelt.
"""

from __future__ import annotations

from dataclasses import dataclass

from nixfact_integration.utils.btw import CATEGORIE_CODES, NUL_CATEGORIEEN
from nixfact_integration.utils.ubl_model import UBLFactuur

GELDIGE_CODES = frozenset(CATEGORIE_CODES.values())


@dataclass(frozen=True)
class Fout:
    """Eén validatiefout: de EN16931-regel plus een leesbare melding."""

    regel: str
    melding: str


def valideer(factuur: UBLFactuur) -> list[Fout]:
    """Geef alle gevonden fouten terug; een lege lijst betekent geldig."""
    fouten: list[Fout] = []
    fouten.extend(_controleer_kop(factuur))
    fouten.extend(_controleer_partijen(factuur))
    fouten.extend(_controleer_regels(factuur))
    return fouten


def _controleer_kop(factuur: UBLFactuur) -> list[Fout]:
    fouten = []
    if not (factuur.nummer or "").strip():
        fouten.append(
            Fout("BR-02", "De factuur heeft geen factuurnummer.")
        )
    if not (factuur.factuurdatum or "").strip():
        fouten.append(Fout("BR-03", "De factuur heeft geen factuurdatum."))
    if not factuur.regels:
        fouten.append(
            Fout("BR-16", "De factuur heeft geen regels; voeg minstens "
                 "één factuurregel toe.")
        )
    return fouten


def _controleer_partijen(factuur: UBLFactuur) -> list[Fout]:
    fouten = []
    lev, afn = factuur.leverancier, factuur.afnemer

    if not (lev.naam or "").strip():
        fouten.append(
            Fout("BR-06", "De naam van je eigen bedrijf ontbreekt. Vul die "
                 "aan bij het bedrijf in de instellingen.")
        )
    if not (afn.naam or "").strip():
        fouten.append(Fout("BR-07", "De naam van de klant ontbreekt."))
    if not (lev.plaats or "").strip() or not (lev.landcode or "").strip():
        fouten.append(
            Fout("BR-08", "Het adres van je eigen bedrijf is onvolledig: "
                 "plaats en land zijn verplicht.")
        )
    if not (afn.landcode or "").strip():
        fouten.append(
            Fout("BR-09", "Het land van de klant ontbreekt in het adres.")
        )
    return fouten


def _controleer_regels(factuur: UBLFactuur) -> list[Fout]:
    fouten = []
    for nummer, regel in enumerate(factuur.regels, start=1):
        if not (regel.omschrijving or "").strip():
            fouten.append(
                Fout("BR-25", f"Regel {nummer} heeft geen omschrijving.")
            )

        if regel.btw_code not in GELDIGE_CODES:
            fouten.append(
                Fout("BR-CL-01", f"Regel {nummer} heeft een onbekende "
                     f"btw-categorie ({regel.btw_code}).")
            )
            continue

        verwacht = round(float(regel.aantal) * float(regel.eenheidsprijs), 2)
        if abs(verwacht - float(regel.excl)) > 0.01:
            fouten.append(
                Fout("BR-CO-04", f"Regel {nummer}: het regeltotaal "
                     f"({regel.excl:.2f}) klopt niet met aantal x prijs "
                     f"({verwacht:.2f}).")
            )

        pct = float(regel.btw_percentage or 0)
        if regel.btw_code in NUL_CATEGORIEEN and pct != 0:
            fouten.append(
                Fout(f"BR-{regel.btw_code}-01", f"Regel {nummer} heeft "
                     f"categorie {regel.btw_code}; daarbij moet het "
                     f"btw-percentage 0 zijn, niet {pct:.0f}.")
            )
        if regel.btw_code == "S" and pct <= 0:
            fouten.append(
                Fout("BR-S-01", f"Regel {nummer} is standaard belast maar "
                     "heeft geen btw-percentage.")
            )
        if regel.btw_code == "AE" and not (
            factuur.afnemer.btw_nummer or ""
        ).strip():
            fouten.append(
                Fout("BR-AE-09", f"Regel {nummer} is btw-verlegd; dan is het "
                     "btw-nummer van de klant verplicht.")
            )
    return fouten
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/test_ubl_validatie.py -v
ruff check nixfact_integration/
```

Expected: 16 tests PASS, ruff `All checks passed!`

- [ ] **Step 5: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
git add nixfact_integration/nixfact_integration/utils/ubl_validatie.py \
        nixfact_integration/nixfact_integration/tests/test_ubl_validatie.py
git commit -m "feat(ubl): validatie met Nederlandse meldingen voor verzending"
```

---

### Task 6: Frappe-adapter, automatische UBL en demo-fixture

De laatste schakel: het echte document wordt naar het pure model vertaald, UBL komt automatisch mee bij versturen, en er is een script dat een demo-factuur neerzet.

**Files:**
- Modify: `nixfact_integration/nixfact_integration/utils/ubl_generator.py` (volledig herschreven)
- Modify: `nixfact_integration/nixfact_integration/api/ubl.py` (nieuw endpoint `valideer_factuur`)
- Modify: `nixfact_integration/nixfact_integration/hooks.py` (regel 15: `# doc_events = {}`)
- Modify: `nixfact_integration/nixfact_integration/tests/test_ubl.py` (imports verhuizen naar ubl_builder)
- Create: `nixfact_integration/nixfact_integration/utils/demo_fixture.py`

**Interfaces:**
- Consumes: `ubl_model.{UBLFactuur, UBLPartij, UBLRegel}`, `ubl_builder.build_invoice_xml`, `ubl_validatie.valideer`, `nixfact_factuur.regels_als_dicts`
- Produces:
  - `model_uit_doc(factuur) -> UBLFactuur` — werkt op een geladen document, ook een nog niet opgeslagen
  - `factuur_naar_model(factuur_name: str) -> UBLFactuur` — dunne wrapper eromheen
  - `generate_ubl_invoice(factuur_name: str) -> str` (bestaande signatuur blijft)
  - `generate_and_attach_ubl(factuur_name: str) -> str` (ongewijzigde signatuur)
  - `valideer_factuur_doc(doc, method=None) -> None` — hook, throwt bij fouten
  - API `valideer_factuur(factuur_name: str) -> dict` met sleutels `geldig: bool`, `fouten: list[dict]`

- [ ] **Step 1: Herschrijf de generator als dunne adapter**

Vervang in `nixfact_integration/nixfact_integration/utils/ubl_generator.py` alles vanaf regel 1 tot en met de functie `_build_invoice_line` (regel 317) door onderstaande code. De helpers `_get_primary_address` en `_get_company_bank` (regel 319 t/m einde) blijven ongewijzigd staan.

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Brug tussen NixFact Factuur en de pure UBL-laag.

Alle XML-logica zit in utils/ubl_builder.py en alle validatie in
utils/ubl_validatie.py — beide zonder frappe, zodat ze in CI testbaar
zijn. Deze module doet alleen het ophalen van gegevens en het opslaan van
de bijlage.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import nowdate

from nixfact_integration.nixfact_integration.doctype.nixfact_factuur import (
    nixfact_factuur,
)
from nixfact_integration.utils.ubl_builder import build_invoice_xml
from nixfact_integration.utils.ubl_model import UBLFactuur, UBLPartij, UBLRegel
from nixfact_integration.utils.ubl_validatie import valideer

# Sanitize filename — keep alnum/dash/underscore only.
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]")


def factuur_naar_model(factuur_name: str) -> UBLFactuur:
    """Haal een factuur op en vertaal hem naar het pure UBL-datamodel."""
    return model_uit_doc(frappe.get_doc("NixFact Factuur", factuur_name))


def model_uit_doc(factuur) -> UBLFactuur:
    """Vertaal een reeds geladen factuurdocument naar het UBL-datamodel.

    Neemt bewust het document en niet de naam: de validatiehook draait
    vóór het opslaan, dus de regels in de database zijn dan nog de oude.
    """
    company_name = factuur.company or frappe.defaults.get_defaults().get("company")
    if not company_name:
        frappe.throw(
            _(
                "Geen 'company' op de factuur en geen default company ingesteld; "
                "kan geen UBL genereren."
            )
        )
    if not factuur.klant:
        frappe.throw(_("Factuur heeft geen klant; kan geen UBL genereren."))

    company = frappe.get_doc("Company", company_name)
    customer = frappe.get_doc("Customer", factuur.klant)
    iban, bic = _get_company_bank(company_name)

    regels = [
        UBLRegel(
            omschrijving=r["omschrijving"],
            aantal=r["aantal"],
            eenheidsprijs=r["eenheidsprijs"],
            excl=r["excl"],
            btw_percentage=r["btw_percentage"],
            btw_code=r["btw_code"],
        )
        for r in nixfact_factuur.regels_als_dicts(factuur)
    ]

    return UBLFactuur(
        nummer=factuur.factuurnummer or factuur.name,
        factuurdatum=str(factuur.factuur_datum or nowdate()),
        vervaldatum=str(factuur.vervaldatum or ""),
        referentie=factuur.referentie or "",
        leverancier=_partij_uit_entiteit(
            company, _get_primary_address(company_name, "Company")
        ),
        afnemer=_partij_uit_entiteit(
            customer, _get_primary_address(factuur.klant, "Customer")
        ),
        regels=regels,
        iban=iban or "",
        bic=bic or "",
        betaald_bedrag=float(factuur.betaald_bedrag or 0),
        opmerkingen=factuur.opmerkingen or "",
    )


def _partij_uit_entiteit(entity, address: dict) -> UBLPartij:
    """Vertaal een Company- of Customer-document naar een UBLPartij."""
    naam = (
        getattr(entity, "company_name", None)
        or getattr(entity, "customer_name", None)
        or getattr(entity, "name", "")
        or ""
    )
    return UBLPartij(
        naam=naam,
        btw_nummer=(getattr(entity, "tax_id", None) or "").strip(),
        straat=address.get("address_line1", ""),
        extra_straat=address.get("address_line2", ""),
        plaats=address.get("city", ""),
        postcode=address.get("pincode", ""),
        landcode=address.get("country_code", "NL"),
        email=getattr(entity, "email_id", "") or "",
        telefoon=getattr(entity, "phone_no", "") or "",
    )


def generate_ubl_invoice(factuur_name: str) -> str:
    """Genereer een UBL 2.1 / Peppol BIS 3.0 Invoice XML-string."""
    return build_invoice_xml(factuur_naar_model(factuur_name))


def valideer_factuur_doc(doc, method=None) -> None:
    """Hook: blokkeer het versturen van een factuur die niet geldig is.

    Draait alleen bij de overgang naar 'Verstuurd' — een concept mag
    onvolledig zijn, dat is het punt van een concept.
    """
    if doc.status != "Verstuurd":
        return
    vorige = doc.get_doc_before_save()
    if vorige and vorige.status == "Verstuurd":
        return

    fouten = valideer(model_uit_doc(doc))
    if not fouten:
        return

    regels = "".join(f"<li>{frappe.utils.escape_html(f.melding)}</li>"
                     for f in fouten)
    frappe.throw(
        _("Deze factuur voldoet nog niet aan de e-facturatie-eisen:")
        + f"<ul>{regels}</ul>",
        frappe.ValidationError,
    )


def generate_and_attach_ubl(factuur_name: str) -> str:
    """Genereer UBL XML, hang die als privébestand aan de factuur.

    Idempotent: opnieuw draaien vervangt de bestaande bijlage.
    """
    xml_content = generate_ubl_invoice(factuur_name)
    factuur = frappe.get_doc("NixFact Factuur", factuur_name)

    raw = factuur.factuurnummer or factuur.name
    safe = _SAFE_FILENAME_RE.sub("_", raw)
    filename = f"{safe}.xml"

    existing = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "NixFact Factuur",
            "attached_to_name": factuur_name,
            "file_name": filename,
        },
        pluck="name",
    )
    for old in existing:
        try:
            frappe.delete_doc("File", old, ignore_permissions=True)
        except Exception:  # noqa: BLE001
            frappe.log_error(
                title="UBL: kon oude bijlage niet verwijderen",
                message=frappe.get_traceback(),
            )

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": filename,
            "attached_to_doctype": "NixFact Factuur",
            "attached_to_name": factuur_name,
            "content": xml_content,
            "is_private": 1,
        }
    )
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return file_doc.file_url
```

- [ ] **Step 2: Repareer de bestaande UBL-test**

De constanten zijn verhuisd. In `nixfact_integration/nixfact_integration/tests/test_ubl.py`, vervang het importblok:

```python
from nixfact_integration.utils.ubl_generator import (
	NS_INVOICE,
	NS_CAC,
	NS_CBC,
	NSMAP,
)
```

door:

```python
from nixfact_integration.utils.ubl_builder import (
	NS_INVOICE,
	NS_CAC,
	NS_CBC,
	NSMAP,
)
```

En in beide helper-tests onderaan, vervang `from nixfact_integration.utils.ubl_generator import _cac` door `from nixfact_integration.utils.ubl_builder import _cac`, en idem voor `_cbc`.

- [ ] **Step 3: Run tests to verify everything still passes**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/ -v
ruff check nixfact_integration/
```

Expected: alle tests PASS (bestaande suite plus de nieuwe), ruff `All checks passed!`

- [ ] **Step 4: Zet de doc_events-hook aan**

In `nixfact_integration/nixfact_integration/hooks.py`, vervang regel 15:

```python
# DocType events
# doc_events = {}
```

door:

```python
# DocType events
doc_events = {
	"NixFact Factuur": {
		"before_save": (
			"nixfact_integration.utils.ubl_generator.valideer_factuur_doc"
		),
	},
}
```

- [ ] **Step 5: Voeg het validatie-endpoint toe**

Voeg onderaan `nixfact_integration/nixfact_integration/api/ubl.py` toe:

```python
@frappe.whitelist()
def valideer_factuur(factuur_name: str) -> dict:
    """Valideer een factuur zonder hem te versturen.

    Permission: caller moet ``read`` hebben op deze factuur.
    """
    if not frappe.has_permission(
        "NixFact Factuur", ptype="read", doc=factuur_name, throw=False
    ):
        raise frappe.PermissionError(_("Niet toegestaan."))

    from nixfact_integration.utils.ubl_generator import factuur_naar_model
    from nixfact_integration.utils.ubl_validatie import valideer

    fouten = valideer(factuur_naar_model(factuur_name))
    return {
        "geldig": not fouten,
        "fouten": [{"regel": f.regel, "melding": f.melding} for f in fouten],
    }
```

- [ ] **Step 6: Schrijf het demo-fixture-script**

Create `nixfact_integration/nixfact_integration/utils/demo_fixture.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Zet een demo-factuur neer voor gesprekken met administratiekantoren.

Draaien met:
    bench --site erp.aldewereldconsultancy.nl execute \\
        nixfact_integration.utils.demo_fixture.maak_demo_factuur
"""

from __future__ import annotations

import frappe

DEMO_KLANT = "NIXFact Demo Klant B.V."


def maak_demo_factuur() -> str:
    """Maak (idempotent) een demo-klant en een meerregelige demo-factuur."""
    if not frappe.db.exists("Customer", DEMO_KLANT):
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": DEMO_KLANT,
                "customer_type": "Company",
                "tax_id": "NL999999999B01",
            }
        ).insert(ignore_permissions=True)

    factuur = frappe.get_doc(
        {
            "doctype": "NixFact Factuur",
            "klant": DEMO_KLANT,
            "factuur_datum": frappe.utils.nowdate(),
            "status": "Concept",
            "referentie": "DEMO-2026",
            "regels": [
                {
                    "omschrijving": "Advieswerk juli",
                    "aantal": 8,
                    "eenheidsprijs": 125.00,
                    "btw_categorie": "Standaard",
                    "btw_percentage": 21,
                },
                {
                    "omschrijving": "Licentie NIXFact (jaar)",
                    "aantal": 1,
                    "eenheidsprijs": 600.00,
                    "btw_categorie": "Standaard",
                    "btw_percentage": 21,
                },
                {
                    "omschrijving": "Doorbelasting drukwerk",
                    "aantal": 1,
                    "eenheidsprijs": 80.00,
                    "btw_categorie": "Nultarief",
                    "btw_percentage": 0,
                },
            ],
        }
    )
    factuur.insert(ignore_permissions=True)
    frappe.db.commit()
    print(
        f"[nixfact] demo-factuur {factuur.name} aangemaakt: "
        f"excl {factuur.bedrag_excl_btw}, incl {factuur.bedrag_incl_btw}"
    )
    return factuur.name
```

- [ ] **Step 7: Draai de volledige suite en lint**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration pytest \
  nixfact_integration/nixfact_integration/tests/ -v
ruff check nixfact_integration/
python -c "import ast,sys; ast.parse(open(sys.argv[1]).read()); print('hooks OK')" \
  nixfact_integration/nixfact_integration/hooks.py
```

Expected: alle tests PASS, ruff `All checks passed!`, `hooks OK`

- [ ] **Step 8: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
git add nixfact_integration/nixfact_integration/utils/ubl_generator.py \
        nixfact_integration/nixfact_integration/utils/demo_fixture.py \
        nixfact_integration/nixfact_integration/api/ubl.py \
        nixfact_integration/nixfact_integration/hooks.py \
        nixfact_integration/nixfact_integration/tests/test_ubl.py
git commit -m "feat(ubl): frappe-adapter, validatie bij versturen, demo-fixture"
```

---

## Handmatige verificatie op de bench (na Task 6)

Deze stappen kunnen niet in CI en moeten op de R220 (LXC 218) draaien. Voer ze uit vóór je een demo geeft.

- [ ] **Backup maken**

```bash
ssh root@192.168.178.88
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl backup --with-files"
```

Expected: pad naar het backupbestand in de uitvoer.

- [ ] **Migreren (draait de patch uit Task 3)**

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl migrate"
```

Expected: onder andere de regel `[nixfact] N facturen gemigreerd naar regels`

- [ ] **Controleer dat geen enkele factuur zonder regels is achtergebleven**

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl console" <<'EOF'
zonder = [f.name for f in frappe.get_all("NixFact Factuur")
          if not frappe.db.count("NixFact Factuur Regel",
                                 {"parent": f.name})]
print("facturen zonder regels:", zonder)
EOF
```

Expected: `facturen zonder regels: []`

- [ ] **Controleer dat totalen niet zijn verschoven**

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl console" <<'EOF'
for f in frappe.get_all("NixFact Factuur",
                        fields=["name", "bedrag_incl_btw"])[:20]:
    doc = frappe.get_doc("NixFact Factuur", f.name)
    doc.bereken_bedragen()
    if abs(doc.bedrag_incl_btw - f.bedrag_incl_btw) > 0.01:
        print("AFWIJKING", f.name, f.bedrag_incl_btw, "->",
              doc.bedrag_incl_btw)
print("controle klaar")
EOF
```

Expected: geen enkele `AFWIJKING`-regel, gevolgd door `controle klaar`

- [ ] **Demo-factuur aanmaken en de UBL bekijken**

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl execute \
  nixfact_integration.utils.demo_fixture.maak_demo_factuur"
```

Expected: `[nixfact] demo-factuur ... aangemaakt: excl 1680.0, incl 1934.6`

Open daarna de factuur in de UI, zet de status op Verstuurd, en controleer dat de UBL-bijlage verschijnt met drie `InvoiceLine`-elementen en twee `TaxSubtotal`-blokken.

- [ ] **Controleer dat de validatie echt blokkeert**

Maak in de UI een factuur aan met één regel zonder omschrijving en zet de status op Verstuurd.

Expected: de opslag wordt geweigerd met de melding "Deze factuur voldoet nog niet aan de e-facturatie-eisen" en daaronder "Regel 1 heeft geen omschrijving."

---

## Definition of done voor Fase 1

- [ ] `PYTHONPATH=nixfact_integration pytest nixfact_integration/nixfact_integration/tests/ -v` is volledig groen
- [ ] `ruff check nixfact_integration/` geeft `All checks passed!`
- [ ] Een factuur met drie regels en twee btw-tarieven levert geldige UBL met drie `InvoiceLine`- en twee `TaxSubtotal`-elementen
- [ ] Een factuur met een verlegde regel krijgt code `AE` plus `TaxExemptionReason`
- [ ] Een onvolledige factuur kan niet op status Verstuurd worden gezet
- [ ] Alle bestaande facturen in productie hebben regels en ongewijzigde totalen
- [ ] De demo-factuur is met één commando te reproduceren

## Wat hierna volgt (niet in dit plan)

Onderdelen 5.4 tot en met 5.7 uit de spec (transport-adapter, inkomende e-facturen, provisioning, kantoor-cockpit) worden pas gepland zodra minstens één administratiekantoor heeft toegezegd. Zie `docs/superpowers/specs/2026-07-21-nixfact-kantoor-design.md`, sectie 10.
