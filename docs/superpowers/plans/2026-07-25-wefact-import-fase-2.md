# WeFact → NIXFact import — Fase 2 (inkoop+PDF, abonnementen, sync, creditnota's)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De WeFact→NIXFact replicatie-engine afmaken: verkoop-creditnota's echt afhandelen, inkoopfacturen + crediteuren + PDF-bijlagen importeren, abonnementen importeren (facturering uit), en de incrementele sync met cursor + scheduler live zetten.

**Architecture:** Uitbreiding van het bestaande `wefact_sync/`-pakket (uit het fundament). Nieuwe pure mappers (crediteur, inkoopfactuur, abonnement) blijven frappe-vrij en fixture-getest; nieuwe upsert-functies en engine-fasen volgen exact het patroon van `backfill_debiteuren`/`backfill_facturen` (per-record-isolatie, idempotent op `wefact_identifier`, zichtbaar rapport). De incrementele sync hergebruikt dezelfde mappers met een `modified_since`-cursor.

**Tech Stack:** Frappe/ERPNext (Python 3.14 prod, CI 3.11), `requests`, lxml, pytest, ruff.

## Global Constraints

- Nieuwe Python-bestanden beginnen met de 3-regelige licentieheader: `# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.` / `# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)` / `# For commercial licensing, contact: nick@nixpay.nl`
- Alle nieuwe modules: `from __future__ import annotations`.
- 4-spaties indentatie; nieuwe testbestanden 4 spaties; `ruff check nixfact_integration/` moet slagen; Nederlandse teksten.
- Pure modules onder `wefact_sync/mapping/` importeren **niet** `frappe` en doen **geen** HTTP.
- Idempotentie-invariant: elk geïmporteerd doc draagt een niet-lege `wefact_identifier`; herdraaien maakt nooit een duplicaat.
- Schaduwmodus-invariant: NIXFact voert nooit een uitgaande actie uit op een doc met een niet-lege `wefact_identifier`.
- **B-learnings die als contract gelden:** WeFact geeft lijstresultaten in één call terug (`list_all` stopt op `totalresults`); detailvelden (adres, regels, bijlagen) alleen via `show`; `WeFactClient(min_interval=0.4)` pacet tegen de IP-firewall; de client retryt niet-JSON/5xx; omschrijvingen worden met `mapping.invoice.strip_html` van HTML ontdaan.
- BTW-categorieën uitsluitend `Standaard`/`Verlegd`/`Nultarief`/`Vrijgesteld`.

## Bestandsoverzicht

Padprefix: `/mnt/nvme1tb/projects/erpnext-nixauce/nixfact_integration/nixfact_integration/`

| Bestand | Verantwoordelijkheid |
|---|---|
| `wefact_sync/mapping/creditnota.py` | Puur: WeFact-creditnota → NixFact-Factuur-dict (negatieve regels) |
| `wefact_sync/mapping/creditor.py` | Puur: WeFact-crediteur → ERPNext Supplier-dict |
| `wefact_sync/mapping/inkoop.py` | Puur: WeFact-inkoopfactuur → NixFact-Inkoopfactuur-dict (plat) |
| `wefact_sync/mapping/abonnement.py` | Puur: WeFact-abonnement → NixFact-Abonnement-dict |
| `wefact_sync/attachments.py` | Bijlage downloaden (base64) + als privé-File hangen |
| `wefact_sync/upsert.py` | Modify: upsert_supplier / upsert_inkoopfactuur / upsert_abonnement / upsert_creditnota |
| `wefact_sync/engine.py` | Modify: creditnota-afhandeling + backfill_inkoop/_abonnementen + incrementele_sync |
| `wefact_sync/cursor.py` | Cursor lezen/schrijven per entiteit in NixFact Instellingen |
| `patches/v1_0/wefact_supplier_velden.py` | Custom fields `wefact_identifier`/`wefact_creditor_code` op Supplier |
| doctype JSON's | `wefact_identifier` op NixFact Inkoopfactuur + NixFact Abonnement; `is_creditnota` + `origineel_wefact_id` op NixFact Factuur |

---

### Task 1: Verkoop-creditnota's echt afhandelen

Het fundament slaat creditnota's over en meldt ze. Nu importeren we ze als NixFact Factuur met negatieve regelbedragen, gemarkeerd en gekoppeld aan het origineel — de default uit spec §5.2.

**Files:**
- Modify: `doctype/nixfact_factuur/nixfact_factuur.json` (velden `is_creditnota` Check + `origineel_wefact_id` Data)
- Create: `wefact_sync/mapping/creditnota.py`
- Modify: `wefact_sync/upsert.py` (functie `upsert_creditnota`)
- Modify: `wefact_sync/engine.py` (`backfill_facturen`: creditnota niet skippen maar upserten)
- Test: `tests/test_wefact_mapping_creditnota.py`

**Interfaces:**
- Consumes: `mapping.invoice.strip_html`, `mapping.invoice.btw_categorie`, `mapping.status.nixfact_status`.
- Produces:
  - `creditnota.creditnota_to_factuur(wf: dict) -> dict` — zelfde sleutels als `invoice_to_factuur` plus `is_creditnota=True` en `origineel_wefact_id`; regelbedragen (`eenheidsprijs`) zijn **negatief** (WeFact-creditbedragen zijn negatief) — als de WeFact-regel een positief bedrag heeft, wordt het teken omgekeerd zodat de factuur negatief totaliseert.
  - `upsert.upsert_creditnota(factuur: dict, company: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_mapping_creditnota.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de verkoop-creditnota-mapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.creditnota import (
    creditnota_to_factuur,
)


def _wf_credit(**over):
    basis = {
        "Identifier": "900",
        "InvoiceCode": "C0007",
        "DebtorCode": "DB0042",
        "Date": "2026-04-01",
        "AmountIncl": "-121.00",
        "Translations": {"Status": "Creditfactuur"},
        "InvoiceLines": [
            {"Description": "Correctie advies", "Number": "1",
             "PriceExcl": "100.00", "TaxCode": "V21", "TaxPercentage": "21"},
        ],
    }
    basis.update(over)
    return basis


class TestCreditnota(unittest.TestCase):

    def test_gemarkeerd_als_creditnota(self):
        f = creditnota_to_factuur(_wf_credit())
        self.assertTrue(f["is_creditnota"])
        self.assertEqual(f["factuurnummer"], "C0007")

    def test_regelbedrag_wordt_negatief(self):
        f = creditnota_to_factuur(_wf_credit())
        self.assertEqual(f["regels"][0]["eenheidsprijs"], -100.0)

    def test_al_negatief_bedrag_blijft_negatief(self):
        wf = _wf_credit(InvoiceLines=[{
            "Description": "x", "Number": "1", "PriceExcl": "-50.00",
            "TaxCode": "V21", "TaxPercentage": "21"}])
        f = creditnota_to_factuur(wf)
        self.assertEqual(f["regels"][0]["eenheidsprijs"], -50.0)

    def test_html_gestript(self):
        wf = _wf_credit(InvoiceLines=[{
            "Description": "<b>Correctie</b>", "Number": "1",
            "PriceExcl": "10.00", "TaxCode": "V21", "TaxPercentage": "21"}])
        f = creditnota_to_factuur(wf)
        self.assertEqual(f["regels"][0]["omschrijving"], "Correctie")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_creditnota.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.mapping.creditnota`

- [ ] **Step 3: Write the creditnota mapping**

Create `wefact_sync/mapping/creditnota.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-verkoop-creditnota → NixFact-Factuur-dict (negatief). Puur."""

from __future__ import annotations

from nixfact_integration.wefact_sync.mapping.invoice import (
    btw_categorie,
    strip_html,
)
from nixfact_integration.wefact_sync.mapping.status import nixfact_status


def _neg(bedrag: float) -> float:
    """Forceer een negatief bedrag (creditnota); positief wordt omgekeerd."""
    b = float(bedrag or 0)
    return -abs(b)


def _regel(wf_line: dict) -> dict:
    pct = float(wf_line.get("TaxPercentage") or 0)
    return {
        "omschrijving": strip_html(wf_line.get("Description")),
        "aantal": float(wf_line.get("Number") or 0),
        "eenheidsprijs": _neg(wf_line.get("PriceExcl")),
        "btw_categorie": btw_categorie(wf_line.get("TaxCode"), pct),
        "btw_percentage": pct,
    }


def creditnota_to_factuur(wf: dict) -> dict:
    res = nixfact_status(
        (wf.get("Translations") or {}).get("Status") or "",
        float(wf.get("AmountIncl") or 0),
    )
    return {
        "factuurnummer": (wf.get("InvoiceCode") or "").strip(),
        "factuur_datum": (wf.get("Date") or "").strip(),
        "referentie": (wf.get("ReferenceNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_debtor_code": (wf.get("DebtorCode") or "").strip(),
        "status": res.status,
        "is_creditnota": True,
        "origineel_wefact_id": str(wf.get("OriginalInvoice") or ""),
        "onbekende_status": res.onbekend,
        "regels": [_regel(line) for line in (wf.get("InvoiceLines") or [])],
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_creditnota.py -v
ruff check nixfact_integration/
```
Expected: 4 tests PASS, ruff clean.

- [ ] **Step 5: Voeg de doctype-velden toe**

In `doctype/nixfact_factuur/nixfact_factuur.json`: voeg aan `field_order` ná `wefact_identifier` toe `is_creditnota` en `origineel_wefact_id`, en aan `fields`:

```json
  {"fieldname": "is_creditnota", "fieldtype": "Check", "label": "Creditnota", "default": 0, "read_only": 1},
  {"fieldname": "origineel_wefact_id", "fieldtype": "Data", "label": "Origineel WeFact ID", "read_only": 1}
```
Bump `"modified"` naar `"2026-07-25 13:00:00.000000"`.

- [ ] **Step 6: Wire upsert + engine**

In `wefact_sync/upsert.py`, voeg toe (naast `upsert_factuur`):

```python
def upsert_creditnota(factuur: dict, company: str) -> str:
    """Upsert een verkoop-creditnota als NixFact Factuur met negatieve regels."""
    naam = upsert_factuur(factuur, company)
    doc = frappe.get_doc("NixFact Factuur", naam)
    doc.is_creditnota = 1
    doc.origineel_wefact_id = factuur.get("origineel_wefact_id") or ""
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return naam
```

In `wefact_sync/engine.py`, `backfill_facturen`: vervang het creditnota-skip-blok door een upsert-tak:

```python
            factuur = invoice_to_factuur(detail)
            if factuur.get("is_creditnota"):
                from nixfact_integration.wefact_sync.mapping.creditnota import (
                    creditnota_to_factuur,
                )
                upsert.upsert_creditnota(creditnota_to_factuur(detail), company)
                verwerkt += 1
                continue
            upsert.upsert_factuur(factuur, company)
            verwerkt += 1
            if factuur.get("onbekende_status"):
                waarschuwingen.append(
                    f"factuur {code}: onbekende WeFact-status, geïmporteerd als Concept"
                )
```

- [ ] **Step 7: Run suite + lint + commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
python3 -c "import json; json.load(open('nixfact_integration/nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.json')); print('JSON OK')"
git add nixfact_integration/nixfact_integration/wefact_sync/mapping/creditnota.py \
        nixfact_integration/nixfact_integration/wefact_sync/upsert.py \
        nixfact_integration/nixfact_integration/wefact_sync/engine.py \
        nixfact_integration/nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.json \
        nixfact_integration/nixfact_integration/tests/test_wefact_mapping_creditnota.py
git commit -m "feat(wefact): verkoop-creditnota's als negatieve factuur importeren"
```
Expected: volledige suite groen, ruff clean, JSON OK.

> **Let op (bench-verificatie):** `OriginalInvoice` als WeFact-veldnaam voor het gecrediteerde origineel is nog niet bevestigd tegen echte data. Controleer bij de eerste inkoop/credit-run één `creditinvoice/show`-payload en pas de sleutel in `creditnota_to_factuur` aan als die anders heet.

---

### Task 2: Crediteuren → Supplier + schema

Inkoopfacturen linken aan een leverancier. WeFact-crediteuren worden ERPNext Suppliers, idempotent op `wefact_identifier`.

**Files:**
- Create: `patches/v1_0/wefact_supplier_velden.py`
- Modify: `patches.txt`
- Create: `wefact_sync/mapping/creditor.py`
- Modify: `wefact_sync/upsert.py` (`upsert_supplier`)
- Test: `tests/test_wefact_mapping_creditor.py`

**Interfaces:**
- Produces:
  - Custom fields op `Supplier`: `wefact_identifier` (Data, search_index), `wefact_creditor_code` (Data, search_index).
  - `creditor.creditor_to_supplier(wf: dict) -> dict` — sleutels `supplier_name`, `tax_id`, `wefact_identifier`, `wefact_creditor_code`.
  - `upsert.upsert_supplier(supplier: dict) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_mapping_creditor.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor crediteur-mapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.creditor import (
    creditor_to_supplier,
)


class TestCreditor(unittest.TestCase):

    def _wf(self, **over):
        basis = {"Identifier": "77", "CreditorCode": "CD0076",
                 "CompanyName": "Leverancier B.V.", "TaxNumber": "NL1B01"}
        basis.update(over)
        return basis

    def test_naam_en_codes(self):
        s = creditor_to_supplier(self._wf())
        self.assertEqual(s["supplier_name"], "Leverancier B.V.")
        self.assertEqual(s["wefact_identifier"], "77")
        self.assertEqual(s["wefact_creditor_code"], "CD0076")
        self.assertEqual(s["tax_id"], "NL1B01")

    def test_lege_naam_valt_terug_op_code(self):
        s = creditor_to_supplier(self._wf(CompanyName=""))
        self.assertEqual(s["supplier_name"], "WeFact CD0076")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_creditor.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.mapping.creditor`

- [ ] **Step 3: Write the mapping**

Create `wefact_sync/mapping/creditor.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-crediteur → ERPNext Supplier-dict. Puur."""

from __future__ import annotations


def creditor_to_supplier(wf: dict) -> dict:
    naam = (wf.get("CompanyName") or "").strip()
    code = (wf.get("CreditorCode") or "").strip()
    return {
        "supplier_name": naam or f"WeFact {code or wf.get('Identifier')}",
        "tax_id": (wf.get("TaxNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_creditor_code": code,
    }
```

- [ ] **Step 4: Write the patch (Supplier custom fields)**

Create `patches/v1_0/wefact_supplier_velden.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Voeg WeFact-koppelvelden toe aan Supplier."""

from __future__ import annotations


def custom_field_specs() -> dict:
    return {
        "Supplier": [
            {"fieldname": "wefact_identifier", "label": "WeFact ID",
             "fieldtype": "Data", "read_only": 1, "search_index": 1,
             "insert_after": "supplier_name"},
            {"fieldname": "wefact_creditor_code", "label": "WeFact crediteurcode",
             "fieldtype": "Data", "read_only": 1, "search_index": 1,
             "insert_after": "wefact_identifier"},
        ],
    }


def execute() -> None:
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import (
        create_custom_fields,
    )

    create_custom_fields(custom_field_specs(), ignore_validate=True)
    frappe.db.commit()
    print("[nixfact] WeFact custom fields aangemaakt op Supplier")
```

Voeg aan `patches.txt` onder `[post_model_sync]` toe: `nixfact_integration.patches.v1_0.wefact_supplier_velden`

- [ ] **Step 5: Write upsert_supplier**

In `wefact_sync/upsert.py`:

```python
def upsert_supplier(supplier: dict) -> str:
    """Maak of werk een Supplier bij, gekoppeld op wefact_identifier."""
    bestaand = _find_by_wefact_id("Supplier", supplier["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("Supplier", bestaand)
        doc.update(supplier)
    else:
        doc = frappe.get_doc({"doctype": "Supplier", **supplier})
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
```

- [ ] **Step 6: Run suite + lint + commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
git add nixfact_integration/nixfact_integration/wefact_sync/mapping/creditor.py \
        nixfact_integration/nixfact_integration/wefact_sync/upsert.py \
        nixfact_integration/nixfact_integration/patches/v1_0/wefact_supplier_velden.py \
        nixfact_integration/nixfact_integration/patches.txt \
        nixfact_integration/nixfact_integration/tests/test_wefact_mapping_creditor.py
git commit -m "feat(wefact): crediteuren → Supplier + koppelvelden"
```
Expected: volledige suite groen, ruff clean.

---

### Task 3: Inkoopfacturen (plat) + engine

`NixFact Inkoopfactuur` heeft geen regels-tabel maar platte bedragen. We mappen de WeFact-inkoopfactuur naar één bedrag excl. + btw-percentage (som van de regels), koppelen aan de Supplier, en importeren met per-record-isolatie.

**Files:**
- Modify: `doctype/nixfact_inkoopfactuur/nixfact_inkoopfactuur.json` (`wefact_identifier` Data)
- Create: `wefact_sync/mapping/inkoop.py`
- Modify: `wefact_sync/upsert.py` (`upsert_inkoopfactuur`)
- Modify: `wefact_sync/engine.py` (`backfill_inkoop`, `volledige_backfill` uitbreiden)
- Test: `tests/test_wefact_mapping_inkoop.py`

**Interfaces:**
- Consumes: `client.list_all`/`show`, `creditor.creditor_to_supplier`, `upsert.upsert_supplier`.
- Produces:
  - `inkoop.inkoop_to_dict(wf: dict) -> dict` — sleutels `inkoopfactuur_nr`, `factuurdatum`, `betalingskenmerk`, `bedrag_excl`, `btw_percentage`, `wefact_creditor_code`, `wefact_identifier`, `attachments` (lijst van `{Identifier, Filename}`).
  - `upsert.upsert_inkoopfactuur(dic: dict, company: str) -> str`.
  - `engine.backfill_inkoop(client, company) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_mapping_inkoop.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor inkoopfactuur-mapping (puur, platte bedragen)."""

import unittest

from nixfact_integration.wefact_sync.mapping.inkoop import inkoop_to_dict


def _wf(**over):
    basis = {
        "Identifier": "337", "CreditInvoiceCode": "CF0337",
        "InvoiceCode": "01286", "CreditorCode": "CD0076",
        "Date": "2026-05-01", "AmountExcl": "200.00",
        "InvoiceLines": [
            {"Description": "Dienst", "PriceExcl": "150.00", "TaxPercentage": "21"},
            {"Description": "Dienst 2", "PriceExcl": "50.00", "TaxPercentage": "21"},
        ],
        "Attachments": [{"Identifier": 5, "Filename": "bon.pdf"}],
    }
    basis.update(over)
    return basis


class TestInkoop(unittest.TestCase):

    def test_kop(self):
        d = inkoop_to_dict(_wf())
        self.assertEqual(d["inkoopfactuur_nr"], "CF0337")
        self.assertEqual(d["betalingskenmerk"], "01286")
        self.assertEqual(d["wefact_creditor_code"], "CD0076")
        self.assertEqual(d["wefact_identifier"], "337")

    def test_bedrag_uit_amountexcl(self):
        d = inkoop_to_dict(_wf())
        self.assertEqual(d["bedrag_excl"], 200.0)
        self.assertEqual(d["btw_percentage"], 21.0)

    def test_attachments_doorgegeven(self):
        d = inkoop_to_dict(_wf())
        self.assertEqual(len(d["attachments"]), 1)
        self.assertEqual(d["attachments"][0]["Identifier"], 5)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_inkoop.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.mapping.inkoop`

- [ ] **Step 3: Write the mapping**

Create `wefact_sync/mapping/inkoop.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-inkoopfactuur → NixFact-Inkoopfactuur-dict (plat). Puur."""

from __future__ import annotations


def _btw_percentage(wf: dict) -> float:
    """Hoogste btw-percentage over de regels; Inkoopfactuur is één tarief."""
    pcts = [float(r.get("TaxPercentage") or 0) for r in (wf.get("InvoiceLines") or [])]
    return max(pcts) if pcts else 0.0


def inkoop_to_dict(wf: dict) -> dict:
    return {
        "inkoopfactuur_nr": (wf.get("CreditInvoiceCode") or "").strip(),
        "factuurdatum": (wf.get("Date") or "").strip(),
        "betalingskenmerk": (wf.get("InvoiceCode") or "").strip(),
        "bedrag_excl": float(wf.get("AmountExcl") or 0),
        "btw_percentage": _btw_percentage(wf),
        "wefact_creditor_code": (wf.get("CreditorCode") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "attachments": list(wf.get("Attachments") or []),
    }
```

- [ ] **Step 4: Doctype-veld + upsert + engine**

In `doctype/nixfact_inkoopfactuur/nixfact_inkoopfactuur.json`: voeg `wefact_identifier` (Data, read_only, search_index) toe aan `field_order` (ná `opmerkingen`) en `fields`; bump `modified` naar `"2026-07-25 13:00:00.000000"`.

In `wefact_sync/upsert.py`:

```python
def upsert_inkoopfactuur(dic: dict, company: str) -> str:
    """Upsert een NixFact Inkoopfactuur, gekoppeld op wefact_identifier."""
    leverancier = frappe.db.get_value(
        "Supplier", {"wefact_creditor_code": dic["wefact_creditor_code"]}, "name"
    )
    if not leverancier:
        raise ValueError(f"Geen leverancier voor {dic['wefact_creditor_code']}")
    kop = {
        "leverancier": leverancier,
        "company": company,
        "inkoopfactuur_nr": dic["inkoopfactuur_nr"],
        "factuurdatum": dic["factuurdatum"],
        "betalingskenmerk": dic["betalingskenmerk"],
        "bedrag_excl": dic["bedrag_excl"],
        "btw_percentage": dic["btw_percentage"],
        "wefact_identifier": dic["wefact_identifier"],
    }
    bestaand = _find_by_wefact_id("NixFact Inkoopfactuur", dic["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("NixFact Inkoopfactuur", bestaand)
        doc.update(kop)
    else:
        doc = frappe.get_doc({"doctype": "NixFact Inkoopfactuur", **kop})
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
```

In `wefact_sync/engine.py`, voeg `backfill_inkoop` toe (patroon van `backfill_facturen`) en roep hem aan in `volledige_backfill` bij `alleen in (None, "inkoop")`, ná de crediteuren:

```python
def backfill_crediteuren(client: WeFactClient) -> None:
    from nixfact_integration.wefact_sync.mapping.creditor import creditor_to_supplier
    verwerkt, mislukt = 0, []
    for kop in client.list_all("creditor"):
        code = kop.get("CreditorCode") or ""
        try:
            wf = client.show("creditor", code, "CreditorCode")
            upsert.upsert_supplier(creditor_to_supplier(wf))
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("crediteur", code, str(exc)))
    _rapporteer(verwerkt, mislukt, "crediteuren")


def backfill_inkoop(client: WeFactClient, company: str) -> None:
    from nixfact_integration.wefact_sync.mapping.inkoop import inkoop_to_dict
    from nixfact_integration.wefact_sync.attachments import hang_bijlagen
    verwerkt, mislukt, waarschuwingen = 0, [], []
    for kop in client.list_all("creditinvoice"):
        code = kop.get("CreditInvoiceCode") or ""
        try:
            wf = client.show("creditinvoice", code, "CreditInvoiceCode")
            dic = inkoop_to_dict(wf)
            naam = upsert.upsert_inkoopfactuur(dic, company)
            n = hang_bijlagen(client, naam, dic["attachments"])
            if n < len(dic["attachments"]):
                waarschuwingen.append(f"inkoop {code}: {len(dic['attachments'])-n} bijlage(n) niet gedownload")
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("inkoop", code, str(exc)))
    _rapporteer(verwerkt, mislukt, "inkoop", waarschuwingen)
```

Update `volledige_backfill`:

```python
    if alleen in (None, "inkoop"):
        backfill_crediteuren(client)
        backfill_inkoop(client, company)
```

- [ ] **Step 5: Run suite + lint + commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
git add nixfact_integration/nixfact_integration/wefact_sync/ \
        nixfact_integration/nixfact_integration/nixfact_integration/doctype/nixfact_inkoopfactuur/nixfact_inkoopfactuur.json \
        nixfact_integration/nixfact_integration/tests/test_wefact_mapping_inkoop.py
git commit -m "feat(wefact): inkoopfacturen (plat) + crediteur-backfill"
```
Expected: volledige suite groen, ruff clean.

---

### Task 4: PDF-bijlagen downloaden en aanhangen

Elke inkoopfactuur kan scans hebben. We downloaden ze (base64) en hangen ze idempotent als privé-File aan het Inkoopfactuur-doc.

**Files:**
- Create: `wefact_sync/attachments.py`
- Test: `tests/test_wefact_attachments.py`

**Interfaces:**
- Consumes: `client.request("attachment", "download", {"Identifier": id})` → `{"attachment": {"Base64": "...", "Filename": "..."}}`.
- Produces:
  - `attachments.decode_base64(att: dict) -> tuple[bytes, str]` — puur: (bytes, filename); lege/ontbrekende Base64 → `ValueError`.
  - `attachments.hang_bijlagen(client, doc_name: str, attachments: list[dict]) -> int` — downloadt + hangt aan; geeft het aantal geslaagde bijlagen terug (per-bijlage-geïsoleerd).

- [ ] **Step 1: Write the failing test (pure decode)**

Create `tests/test_wefact_attachments.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de pure base64-decode van bijlagen."""

import base64
import unittest

from nixfact_integration.wefact_sync.attachments import decode_base64


class TestDecode(unittest.TestCase):

    def test_decode_ok(self):
        raw = b"%PDF-1.4 test"
        att = {"Base64": base64.b64encode(raw).decode(), "Filename": "bon.pdf"}
        data, naam = decode_base64(att)
        self.assertEqual(data, raw)
        self.assertEqual(naam, "bon.pdf")

    def test_lege_base64_faalt(self):
        with self.assertRaises(ValueError):
            decode_base64({"Base64": "", "Filename": "x.pdf"})

    def test_lowercase_key(self):
        raw = b"data"
        att = {"base64": base64.b64encode(raw).decode(), "Filename": "y.pdf"}
        self.assertEqual(decode_base64(att)[0], raw)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_attachments.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.attachments`

- [ ] **Step 3: Write the module**

Create `wefact_sync/attachments.py`:

```python
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
```

- [ ] **Step 4: Run suite + lint + commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
git add nixfact_integration/nixfact_integration/wefact_sync/attachments.py \
        nixfact_integration/nixfact_integration/tests/test_wefact_attachments.py
git commit -m "feat(wefact): PDF-bijlagen downloaden en aanhangen"
```
Expected: volledige suite groen, ruff clean.

---

### Task 5: Abonnementen (facturering uit)

De 29 WeFact-abonnementen worden NixFact Abonnement, met facturering **uit** (safeguard §6.1) zodat WeFact en NIXFact niet allebei factureren.

**Files:**
- Modify: `doctype/nixfact_abonnement/nixfact_abonnement.json` (`wefact_identifier` Data)
- Create: `wefact_sync/mapping/abonnement.py`
- Modify: `wefact_sync/upsert.py` (`upsert_abonnement`)
- Modify: `wefact_sync/engine.py` (`backfill_abonnementen`)
- Test: `tests/test_wefact_mapping_abonnement.py`

**Interfaces:**
- Produces:
  - `abonnement.abonnement_to_dict(wf: dict) -> dict` — sleutels `klant_debtor_code`, `omschrijving`, `bedrag_excl_btw`, `btw_percentage`, `frequentie`, `volgende_factuur_datum`, `wefact_identifier`.
  - `abonnement.wefact_frequentie(periodic: str) -> str` — `m→Maandelijks`, `k→Kwartaal`, `j→Jaarlijks`, anders `Maandelijks`.
  - `upsert.upsert_abonnement(dic: dict) -> str` (zet facturering-uit-veld).

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_mapping_abonnement.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor abonnement-mapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.abonnement import (
    abonnement_to_dict,
    wefact_frequentie,
)


class TestFrequentie(unittest.TestCase):

    def test_maand(self):
        self.assertEqual(wefact_frequentie("m"), "Maandelijks")

    def test_kwartaal(self):
        self.assertEqual(wefact_frequentie("k"), "Kwartaal")

    def test_jaar(self):
        self.assertEqual(wefact_frequentie("j"), "Jaarlijks")

    def test_onbekend(self):
        self.assertEqual(wefact_frequentie("x"), "Maandelijks")


class TestAbonnement(unittest.TestCase):

    def test_velden(self):
        wf = {"Identifier": "12", "DebtorCode": "DB0160",
               "Description": "Hosting", "PriceExcl": "10.00",
               "TaxPercentage": "21", "Periodic": "m", "NextDate": "2026-08-01"}
        d = abonnement_to_dict(wf)
        self.assertEqual(d["klant_debtor_code"], "DB0160")
        self.assertEqual(d["bedrag_excl_btw"], 10.0)
        self.assertEqual(d["frequentie"], "Maandelijks")
        self.assertEqual(d["volgende_factuur_datum"], "2026-08-01")
        self.assertEqual(d["wefact_identifier"], "12")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_abonnement.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.mapping.abonnement`

- [ ] **Step 3: Write the mapping**

Create `wefact_sync/mapping/abonnement.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-abonnement → NixFact-Abonnement-dict. Puur."""

from __future__ import annotations

from nixfact_integration.wefact_sync.mapping.invoice import strip_html

_FREQ = {"m": "Maandelijks", "k": "Kwartaal", "j": "Jaarlijks", "w": "Maandelijks"}


def wefact_frequentie(periodic: str) -> str:
    return _FREQ.get((periodic or "").strip().lower(), "Maandelijks")


def abonnement_to_dict(wf: dict) -> dict:
    return {
        "klant_debtor_code": (wf.get("DebtorCode") or "").strip(),
        "omschrijving": strip_html(wf.get("Description")),
        "bedrag_excl_btw": float(wf.get("PriceExcl") or 0),
        "btw_percentage": float(wf.get("TaxPercentage") or 0),
        "frequentie": wefact_frequentie(wf.get("Periodic")),
        "volgende_factuur_datum": (wf.get("NextDate") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
    }
```

- [ ] **Step 4: Doctype-veld + upsert + engine**

In `doctype/nixfact_abonnement/nixfact_abonnement.json`: voeg `wefact_identifier` (Data, read_only, search_index) toe; bump `modified`.

In `wefact_sync/upsert.py`:

```python
def upsert_abonnement(dic: dict) -> str:
    """Upsert een NixFact Abonnement met facturering UIT (schaduwmodus)."""
    klant = frappe.db.get_value(
        "Customer", {"wefact_debtor_code": dic["klant_debtor_code"]}, "name"
    )
    if not klant:
        raise ValueError(f"Geen klant voor {dic['klant_debtor_code']}")
    velden = {
        "klant": klant,
        "omschrijving": dic["omschrijving"],
        "bedrag_excl_btw": dic["bedrag_excl_btw"],
        "btw_percentage": dic["btw_percentage"],
        "frequentie": dic["frequentie"],
        "volgende_factuur_datum": dic["volgende_factuur_datum"],
        "wefact_identifier": dic["wefact_identifier"],
        "status": "Gepauzeerd",
    }
    bestaand = _find_by_wefact_id("NixFact Abonnement", dic["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("NixFact Abonnement", bestaand)
        doc.update(velden)
    else:
        doc = frappe.get_doc({"doctype": "NixFact Abonnement", **velden})
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
```

> **Let op:** controleer bij de bench-verificatie de `status`-Select-opties op `NixFact Abonnement`. Gebruik de waarde die "niet automatisch factureren" betekent (bijv. `Gepauzeerd` of `Inactief`); pas `velden["status"]` aan als die anders heet. De globale `auto_factureren_abonnementen` blijft sowieso uit tot cutover.

In `wefact_sync/engine.py`, `backfill_abonnementen` + aanroep in `volledige_backfill` bij `alleen in (None, "abonnementen")`:

```python
def backfill_abonnementen(client: WeFactClient) -> None:
    from nixfact_integration.wefact_sync.mapping.abonnement import abonnement_to_dict
    verwerkt, mislukt = 0, []
    for kop in client.list_all("subscription"):
        ident = str(kop.get("Identifier") or "")
        try:
            wf = client.show("subscription", ident, "Identifier")
            upsert.upsert_abonnement(abonnement_to_dict(wf))
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("abonnement", ident, str(exc)))
    _rapporteer(verwerkt, mislukt, "abonnementen")
```

- [ ] **Step 5: Run suite + lint + commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
git add nixfact_integration/nixfact_integration/wefact_sync/ \
        nixfact_integration/nixfact_integration/nixfact_integration/doctype/nixfact_abonnement/nixfact_abonnement.json \
        nixfact_integration/nixfact_integration/tests/test_wefact_mapping_abonnement.py
git commit -m "feat(wefact): abonnementen importeren met facturering uit"
```
Expected: volledige suite groen, ruff clean.

---

### Task 6: Incrementele sync + cursor + scheduler

Na de backfill houdt een uurlijkse scheduler-run het spiegelbeeld actueel via `modified_since`. De cursor staat per entiteit in NixFact Instellingen (velden uit het fundament).

**Files:**
- Create: `wefact_sync/cursor.py`
- Modify: `wefact_sync/engine.py` (`incrementele_sync`)
- Modify: `hooks.py` (scheduler_events: uurlijkse job, gated op `wefact_sync_enabled`)
- Test: `tests/test_wefact_cursor.py`

**Interfaces:**
- Produces:
  - `cursor.max_modified(records: list[dict]) -> str` — puur: hoogste `Modified`-waarde in een reeks (leeg → "").
  - `engine.incrementele_sync() -> None` — scheduler-entrypoint; per entiteit `modified_since=cursor`, verwerkt alleen gewijzigde records, schrijft de nieuwe cursor.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_cursor.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de pure cursor-helper."""

import unittest

from nixfact_integration.wefact_sync.cursor import max_modified


class TestMaxModified(unittest.TestCase):

    def test_hoogste(self):
        recs = [{"Modified": "2026-07-01 10:00:00"},
                {"Modified": "2026-07-05 09:00:00"},
                {"Modified": "2026-07-03 12:00:00"}]
        self.assertEqual(max_modified(recs), "2026-07-05 09:00:00")

    def test_lege_modified_genegeerd(self):
        recs = [{"Modified": ""}, {"Modified": "2026-07-02 08:00:00"}]
        self.assertEqual(max_modified(recs), "2026-07-02 08:00:00")

    def test_geen_records(self):
        self.assertEqual(max_modified([]), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_cursor.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.cursor`

- [ ] **Step 3: Write cursor.py**

Create `wefact_sync/cursor.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Sync-cursor per entiteit in NixFact Instellingen.

`max_modified` is puur/testbaar; lezen/schrijven raakt frappe.
"""

from __future__ import annotations

_VELD = {
    "debtor": "wefact_cursor_debiteuren",
    "invoice": "wefact_cursor_facturen",
}


def max_modified(records: list[dict]) -> str:
    waarden = [str(r.get("Modified") or "").strip() for r in records]
    waarden = [w for w in waarden if w]
    return max(waarden) if waarden else ""


def lees_cursor(entiteit: str) -> str:
    import frappe

    veld = _VELD.get(entiteit)
    if not veld:
        return ""
    return frappe.db.get_single_value("NixFact Instellingen", veld) or ""


def schrijf_cursor(entiteit: str, waarde: str) -> None:
    import frappe

    veld = _VELD.get(entiteit)
    if not veld or not waarde:
        return
    frappe.db.set_single_value("NixFact Instellingen", veld, waarde)
    frappe.db.commit()
```

- [ ] **Step 4: Incrementele sync in engine + scheduler**

In `wefact_sync/engine.py`:

```python
def incrementele_sync() -> None:
    """Scheduler-entrypoint: verwerk alleen records die WeFact wijzigde.

    Lijst per entiteit met ``modified_since=cursor`` — WeFact geeft dan
    alleen gewijzigde records terug, dus normaal een handvol per uur (geen
    burst die de IP-firewall triggert). Alleen die records krijgen een
    detail-fetch + upsert. De cursor schuift op naar de hoogste Modified.
    Debiteuren met een lege ``Modified`` worden hier gemist; een dagelijkse
    volledige debiteuren-backfill (los te schedulen) vangt die.
    """
    from nixfact_integration.wefact_sync import cursor
    from nixfact_integration.wefact_sync.mapping.debtor import (
        debtor_to_address,
        debtor_to_customer,
    )

    settings = frappe.get_single("NixFact Instellingen")
    if not settings.wefact_sync_enabled:
        return
    client = _client()
    company = upsert.ensure_company()

    # Debiteuren
    sinds = cursor.lees_cursor("debtor")
    gewijzigd = client.list_all(
        "debtor", params={"modified": sinds} if sinds else None
    )
    for kop in gewijzigd:
        code = kop.get("DebtorCode") or ""
        try:
            wf = client.show("debtor", code, "DebtorCode")
            upsert.upsert_customer(debtor_to_customer(wf), debtor_to_address(wf))
        except Exception:  # noqa: BLE001
            frappe.db.rollback()
            frappe.log_error(title=f"WeFact-sync debiteur {code}",
                             message=frappe.get_traceback())
    cursor.schrijf_cursor("debtor", cursor.max_modified(gewijzigd))

    # Facturen (incl. creditnota's)
    sinds = cursor.lees_cursor("invoice")
    gewijzigd = client.list_all(
        "invoice", params={"modified": sinds} if sinds else None
    )
    for kop in gewijzigd:
        code = kop.get("InvoiceCode") or ""
        try:
            detail = client.show("invoice", code, "InvoiceCode")
            factuur = invoice_to_factuur(detail)
            if factuur.get("is_creditnota"):
                from nixfact_integration.wefact_sync.mapping.creditnota import (
                    creditnota_to_factuur,
                )
                upsert.upsert_creditnota(creditnota_to_factuur(detail), company)
            else:
                upsert.upsert_factuur(factuur, company)
        except Exception:  # noqa: BLE001
            frappe.db.rollback()
            frappe.log_error(title=f"WeFact-sync factuur {code}",
                             message=frappe.get_traceback())
    cursor.schrijf_cursor("invoice", cursor.max_modified(gewijzigd))
```

In `hooks.py`, breid `scheduler_events` uit:

```python
	"hourly": [
		"nixfact_integration.wefact_sync.engine.incrementele_sync",
	],
```

- [ ] **Step 5: Run suite + lint + syntax-check + commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
python3 -c "import ast; ast.parse(open('nixfact_integration/nixfact_integration/hooks.py').read()); print('hooks OK')"
git add nixfact_integration/nixfact_integration/wefact_sync/cursor.py \
        nixfact_integration/nixfact_integration/wefact_sync/engine.py \
        nixfact_integration/nixfact_integration/hooks.py \
        nixfact_integration/nixfact_integration/tests/test_wefact_cursor.py
git commit -m "feat(wefact): incrementele sync met cursor + uurlijkse scheduler"
```
Expected: volledige suite groen, ruff clean, hooks OK.

---

## Handmatige bench-verificatie (op R220 LXC 218, na deploy)

**Eerst backup.** Draai in deze volgorde; alles is idempotent en gepacet.

- [ ] Backup + migrate (Supplier-velden, is_creditnota, inkoop/abonnement wefact_identifier):
  `docker exec docker-nixfact-1 bench --site erp.aldewereldconsultancy.nl backup --with-files && bench ... migrate`
- [ ] Creditnota-payload check: bevestig het WeFact-veld voor het gecrediteerde origineel; pas zo nodig `creditnota_to_factuur` aan.
- [ ] Inkoop-backfill: `bench ... execute nixfact_integration.wefact_sync.engine.volledige_backfill --kwargs '{"alleen":"inkoop"}'` → verwacht ~335 inkoopfacturen + Suppliers + PDF-Files. Controleer een steekproef: PDF opent, leverancier gekoppeld.
- [ ] Abonnement-backfill: `--kwargs '{"alleen":"abonnementen"}'` → 29 abonnementen, allemaal op de niet-factureren-status; bevestig dat `auto_factureren_abonnementen` uit staat.
- [ ] Sync aanzetten: `wefact_sync_enabled` = 1 in NixFact Instellingen; verifieer dat de uurlijkse `incrementele_sync` draait (scheduler-log) en geen dubbels maakt.
- [ ] Idempotentie: draai elke backfill nogmaals; aantallen blijven gelijk.

## Definition of done

- [ ] Alle nieuwe pytests groen; `ruff check nixfact_integration/` clean; volledige suite groen.
- [ ] Verkoop-creditnota's staan als negatieve, gemarkeerde facturen (gekoppeld aan origineel).
- [ ] ~335 inkoopfacturen + crediteuren + PDF-bijlagen geïmporteerd; steekproef-PDF opent.
- [ ] 29 abonnementen geïmporteerd met facturering uit (geen dubbele facturering mogelijk).
- [ ] Incrementele sync draait uurlijks achter `wefact_sync_enabled`, idempotent, met cursor.
- [ ] Schaduwmodus-invariant intact: niets uitgaands op WeFact-eigendom.

## Afhankelijkheid

Bouwt op het WeFact-fundament (branch `nixfact-production-deployment`, engine `wefact_sync/`). Deploy = image rebuild + migrate zoals bij het fundament. Draai de backfills **gepacet** (de client doet dat al via `min_interval`) om de WeFact-IP-firewall niet te triggeren.
