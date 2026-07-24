# WeFact → NIXFact import — Fundament + eerste backfill (implementatieplan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bouw het fundament van de WeFact→NIXFact replicatie-engine plus de eerste volledige backfill van debiteuren en verkoopfacturen, met de veiligheids-safeguards vóór de eerste factuurimport, eindigend in een demonstreerbaar resultaat.

**Architecture:** Een Python-subpakket `wefact_sync/` in de bestaande Frappe-app `nixfact_integration`. WeFact wordt via REST uitgelezen (`client.py`); de mapping WeFact-record → NIXFact-dict is puur en frappe-vrij (`mapping/`, volledig CI-testbaar met fixtures); de upsert-laag (`upsert.py`) is de enige die de database raakt en is idempotent op `wefact_identifier`; `engine.py` orkestreert met per-record-isolatie en zichtbare foutrapportage.

**Tech Stack:** Frappe/ERPNext (Python 3.14 productie, CI 3.11), `requests`, lxml (bestaand), pytest, ruff.

## Global Constraints

- Alle nieuwe Python-bestanden beginnen met de bestaande 3-regelige licentieheader, letterlijk: `# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.` / `# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)` / `# For commercial licensing, contact: nick@nixpay.nl`
- Alle nieuwe modules: `from __future__ import annotations`.
- 4-spaties indentatie in nieuwe bestanden; nieuwe testbestanden gebruiken 4 spaties (niet tabs).
- `ruff check nixfact_integration/` moet slagen.
- Gebruikergerichte teksten (labels, meldingen, rapporten) zijn Nederlands.
- Pure modules onder `wefact_sync/mapping/` importeren **niet** `frappe` en doen **geen** HTTP — dat maakt ze CI-testbaar.
- Bedragen: NIXFact rekent zelf de totalen uit de regels (Fase 1); de mapping levert alleen regelvelden (`aantal`, `eenheidsprijs`, `btw_percentage`, `btw_categorie`), geen kop-totalen.
- BTW-categorieën uitsluitend `Standaard`/`Verlegd`/`Nultarief`/`Vrijgesteld` (Fase 1 Select-waarden).
- WeFact API-contract (uit `/mnt/nvme1tb/projects/wefact-mcp/wefact_mcp/client.py`): POST JSON naar `https://api.mijnwefact.nl/v2/` met body `{"api_key", "controller", "action", ...params}`; lijst-actie pagineert via `offset` (100/pagina) en de resultaatlijst heet het meervoud van de controller (`debtors`, `invoices`); detail via `action="show"`.
- **Idempotentie-invariant:** elk geïmporteerd doc draagt een niet-lege `wefact_identifier`. Herdraaien mag nooit een duplicaat maken.
- **Schaduwmodus-invariant:** NIXFact voert nooit een uitgaande actie uit op een doc met een niet-lege `wefact_identifier`.

## Bestandsoverzicht

Padprefix: `/mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels/nixfact_integration/nixfact_integration/`

| Bestand | Verantwoordelijkheid |
|---|---|
| `patches/v1_0/wefact_velden.py` | Custom fields op Customer + config/cursor-velden op Instellingen |
| `doctype/nixfact_factuur/nixfact_factuur.json` | `wefact_identifier`-veld toevoegen |
| `utils/ubl_generator.py` | Hook-bypass voor WeFact-docs (safeguard) |
| `tasks.py` | Reminder/dunning-queries uitsluiten van WeFact-docs (safeguard) |
| `wefact_sync/__init__.py` | Pakket-marker |
| `wefact_sync/client.py` | WeFact REST-client (sync, paginatie, backoff) |
| `wefact_sync/mapping/__init__.py` | Pakket-marker |
| `wefact_sync/mapping/status.py` | WeFact-statustekst → NIXFact-status + creditnota-detectie |
| `wefact_sync/mapping/debtor.py` | Debiteur → Customer- + Address-dict |
| `wefact_sync/mapping/invoice.py` | Verkoopfactuur → Factuur-dict incl. regels |
| `wefact_sync/upsert.py` | Idempotente ORM-laag (Customer, Address, Factuur, company) |
| `wefact_sync/report.py` | Puur: samenvatting van een run (X verwerkt, Y mislukt) |
| `wefact_sync/engine.py` | Orkestratie + backfill-entrypoint |
| `tests/test_wefact_*.py` | Tests per module |

---

### Task 1: Schema — idempotentie- en config-velden

Scaffolding voor de hele engine: de `wefact_identifier`-velden waar idempotentie en de safeguards op leunen, plus WeFact-config op Instellingen. Geen import-logica.

**Files:**
- Create: `patches/__init__.py` (indien nog niet aanwezig — Fase 1 maakte deze al; controleer)
- Create: `patches/v1_0/__init__.py` (idem, controleer)
- Create: `patches/v1_0/wefact_velden.py`
- Modify: `patches.txt` (regel toevoegen)
- Modify: `doctype/nixfact_factuur/nixfact_factuur.json` (veld + field_order + `modified`)
- Test: `tests/test_wefact_schema.py`

**Interfaces:**
- Consumes: niets.
- Produces:
  - Custom fields op `Customer`: `wefact_identifier` (Data, uniek-indexeerbaar), `wefact_debtor_code` (Data).
  - Veld `wefact_identifier` (Data, read-only) op `NixFact Factuur`.
  - Velden op `NixFact Instellingen` (Single): `wefact_api_key` (Password), `wefact_sync_enabled` (Check, default 0), `wefact_cursor_debiteuren` (Data), `wefact_cursor_facturen` (Data).
  - `patches.v1_0.wefact_velden.custom_field_specs() -> dict` — pure functie die de Custom-Field-definities teruggeeft (voor de test).

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_schema.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de WeFact-schemavelden (pure spec-helper)."""

import unittest

from nixfact_integration.patches.v1_0.wefact_velden import custom_field_specs


class TestCustomFieldSpecs(unittest.TestCase):

    def test_customer_krijgt_beide_velden(self):
        specs = custom_field_specs()
        namen = [f["fieldname"] for f in specs["Customer"]]
        self.assertIn("wefact_identifier", namen)
        self.assertIn("wefact_debtor_code", namen)

    def test_identifier_is_data_en_indexeerbaar(self):
        specs = custom_field_specs()
        veld = next(
            f for f in specs["Customer"] if f["fieldname"] == "wefact_identifier"
        )
        self.assertEqual(veld["fieldtype"], "Data")
        self.assertEqual(veld.get("search_index"), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_schema.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'nixfact_integration.patches.v1_0.wefact_velden'`

- [ ] **Step 3: Write the patch**

Controleer eerst of `patches/__init__.py` en `patches/v1_0/__init__.py` bestaan (Fase 1 maakte deze). Zo niet, maak ze leeg aan.

Create `patches/v1_0/wefact_velden.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Voeg WeFact-koppelvelden en -config toe.

`custom_field_specs` is puur zodat de vorm in CI te testen is; `execute`
past ze toe via de Frappe custom-field-API en voegt de config-velden aan
NixFact Instellingen toe.
"""

from __future__ import annotations


def custom_field_specs() -> dict:
    """Custom-Field-definities per doctype (ERPNext-standaarddoctypes)."""
    return {
        "Customer": [
            {
                "fieldname": "wefact_identifier",
                "label": "WeFact ID",
                "fieldtype": "Data",
                "read_only": 1,
                "search_index": 1,
                "insert_after": "customer_name",
            },
            {
                "fieldname": "wefact_debtor_code",
                "label": "WeFact debiteurcode",
                "fieldtype": "Data",
                "read_only": 1,
                "search_index": 1,
                "insert_after": "wefact_identifier",
            },
        ],
    }


def execute() -> None:
    """Maak custom fields op Customer en config-velden op Instellingen."""
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import (
        create_custom_fields,
    )

    create_custom_fields(custom_field_specs(), ignore_validate=True)
    frappe.db.commit()
    print("[nixfact] WeFact custom fields aangemaakt op Customer")
```

- [ ] **Step 4: Voeg het veld toe aan NixFact Factuur**

In `doctype/nixfact_factuur/nixfact_factuur.json`:
- In `field_order`, direct ná `"opmerkingen"`, voeg toe: `"wefact_identifier"`.
- In de `fields`-array, ná het `opmerkingen`-object, voeg toe:

```json
  {
   "fieldname": "wefact_identifier",
   "fieldtype": "Data",
   "label": "WeFact ID",
   "read_only": 1,
   "search_index": 1
  }
```
- Bump `"modified"` naar `"2026-07-24 12:00:00.000000"`.

- [ ] **Step 5: Voeg config-velden toe aan NixFact Instellingen**

In `doctype/nixfact_instellingen/nixfact_instellingen.json`: voeg aan het einde van `field_order` toe: `"wefact_section"`, `"wefact_api_key"`, `"wefact_sync_enabled"`, `"wefact_cursor_debiteuren"`, `"wefact_cursor_facturen"`. Voeg aan `fields` toe:

```json
  {"fieldname": "wefact_section", "fieldtype": "Section Break", "label": "WeFact-sync"},
  {"fieldname": "wefact_api_key", "fieldtype": "Password", "label": "WeFact API-key"},
  {"fieldname": "wefact_sync_enabled", "fieldtype": "Check", "label": "WeFact-sync actief", "default": 0},
  {"fieldname": "wefact_cursor_debiteuren", "fieldtype": "Data", "label": "Cursor debiteuren", "read_only": 1},
  {"fieldname": "wefact_cursor_facturen", "fieldtype": "Data", "label": "Cursor facturen", "read_only": 1}
```
Bump `"modified"` naar `"2026-07-24 12:00:00.000000"`.

- [ ] **Step 6: Registreer de patch**

Voeg aan `patches.txt` onder `[post_model_sync]` de regel toe:
```
nixfact_integration.patches.v1_0.wefact_velden
```

- [ ] **Step 7: Run test + lint + JSON-validatie**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_schema.py -v
ruff check nixfact_integration/
python3 -c "import json,sys; [json.load(open(p)) for p in sys.argv[1:]]; print('JSON OK')" \
  nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.json \
  nixfact_integration/nixfact_integration/doctype/nixfact_instellingen/nixfact_instellingen.json
```
Expected: 2 tests PASS, ruff clean, `JSON OK`

- [ ] **Step 8: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
git add nixfact_integration/nixfact_integration/patches \
        nixfact_integration/nixfact_integration/patches.txt \
        nixfact_integration/nixfact_integration/doctype/nixfact_factuur/nixfact_factuur.json \
        nixfact_integration/nixfact_integration/doctype/nixfact_instellingen/nixfact_instellingen.json \
        nixfact_integration/nixfact_integration/tests/test_wefact_schema.py
git commit -m "feat(wefact): schema — wefact_identifier-velden + sync-config"
```

---

### Task 2: Safeguards + nummerbehoud — Fase 1 import-bewust maken

Vóór er ook maar één factuur wordt geïmporteerd, moeten drie Fase 1-gedragingen import-bewust worden: (a) de validatiehook mag WeFact-docs niet blokkeren, (b) de reminder/dunning-cron mag echte klanten geen aanmaning sturen over geïmporteerde facturen, en (c) de nummergenerator mag het WeFact-factuurnummer niet overschrijven.

**Files:**
- Modify: `utils/ubl_generator.py` (functie `valideer_factuur_doc`)
- Modify: `tasks.py` (functies `verstuur_herinneringen`, `verstuur_aanmaningen`)
- Modify: `utils/numbering.py` (functie `set_nummer_for_doc`)
- Test: `tests/test_wefact_safeguards.py`

**Interfaces:**
- Consumes: `wefact_identifier`-veld uit Task 1.
- Produces: gewijzigd gedrag — `valideer_factuur_doc` slaat over bij WeFact-docs; de twee cron-queries sluiten WeFact-docs uit; `set_nummer_for_doc` behoudt een reeds ingevuld nummer i.p.v. een nieuw te genereren.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_safeguards.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de schaduwmodus-safeguards op Fase 1-gedrag."""

import unittest
from types import SimpleNamespace

from nixfact_integration.utils.ubl_generator import valideer_factuur_doc


class TestHookBypass(unittest.TestCase):

    def test_wefact_factuur_wordt_niet_gevalideerd(self):
        # Status 'Verstuurd' + onvolledige data zou normaal blokkeren;
        # met een wefact_identifier moet de hook meteen returnen zonder
        # frappe.get_doc aan te roepen (die er in de test niet is).
        doc = SimpleNamespace(
            status="Verstuurd",
            wefact_identifier="123",
            name="F-IMPORT-1",
        )
        # Mag niet raisen en niets teruggeven.
        self.assertIsNone(valideer_factuur_doc(doc))

    def test_niet_wefact_factuur_gaat_wel_de_validatie_in(self):
        # Zonder wefact_identifier en met status 'Concept' returnt de hook
        # ook (concept wordt niet gevalideerd) — bewijst dat de bypass niet
        # de enige exit is.
        doc = SimpleNamespace(status="Concept", wefact_identifier=None)
        self.assertIsNone(valideer_factuur_doc(doc))


class TestNummerbehoud(unittest.TestCase):

    def test_bestaand_nummer_blijft_behouden(self):
        # Een geïmporteerde factuur heeft factuurnummer al gezet (WeFact-code);
        # set_nummer_for_doc mag die niet overschrijven en moet doc.name = die
        # waarde zetten, zonder de DB-nummergenerator aan te roepen.
        from nixfact_integration.utils.numbering import set_nummer_for_doc

        doc = SimpleNamespace(factuurnummer="F0790", name=None)
        set_nummer_for_doc(doc, "NixFact Factuur")
        self.assertEqual(doc.factuurnummer, "F0790")
        self.assertEqual(doc.name, "F0790")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_safeguards.py -v
```
Expected: FAIL — `test_wefact_factuur_wordt_niet_gevalideerd` (hook crasht zonder bypass) en `test_bestaand_nummer_blijft_behouden` (set_nummer_for_doc roept de DB-generator aan en overschrijft).

- [ ] **Step 3: Voeg de hook-bypass toe**

In `utils/ubl_generator.py`, in `valideer_factuur_doc`, direct ná de docstring en vóór `if doc.status != "Verstuurd":`, voeg toe:

```python
    # Schaduwmodus: WeFact-eigendom wordt nooit door NIXFact gevalideerd
    # of verstuurd — historische administratie, nooit via Peppol gegaan.
    if doc.get("wefact_identifier") if hasattr(doc, "get") else getattr(
        doc, "wefact_identifier", None
    ):
        return
```

Let op: het `doc` in de test is een `SimpleNamespace` zonder `.get`; in productie is het een Frappe `Document` mét `.get`. De regel dekt beide.

- [ ] **Step 4: Sluit WeFact-docs uit in reminder + dunning**

In `tasks.py`, in `verstuur_herinneringen`, voeg aan het `filters`-dict van de `frappe.get_all`-aanroep toe:
```python
            "wefact_identifier": ["in", [None, ""]],
```
Doe hetzelfde in `verstuur_aanmaningen` (voeg dezelfde regel toe aan diens `filters`-dict).

- [ ] **Step 5: Behoud een reeds ingevuld nummer**

In `utils/numbering.py`, in `set_nummer_for_doc`, direct ná de docstring en vóór de `if doctype not in DOCTYPE_NUMBERING:`-controle, voeg toe:

```python
    # Import-bewust: als er al een nummer staat (bijv. de WeFact-code bij
    # import), behoud dat en genereer geen nieuw nummer.
    if doctype in DOCTYPE_NUMBERING:
        bestaand = getattr(doc, DOCTYPE_NUMBERING[doctype][4], None)
        if bestaand:
            doc.name = bestaand
            return
```

- [ ] **Step 6: Run test + lint + volledige suite**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_safeguards.py -v
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
```
Expected: nieuwe tests PASS, volledige suite groen, ruff clean.

- [ ] **Step 7: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
git add nixfact_integration/nixfact_integration/utils/ubl_generator.py \
        nixfact_integration/nixfact_integration/utils/numbering.py \
        nixfact_integration/nixfact_integration/tasks.py \
        nixfact_integration/nixfact_integration/tests/test_wefact_safeguards.py
git commit -m "feat(wefact): safeguards + nummerbehoud — Fase 1 import-bewust"
```

---

### Task 3: WeFact REST-client

De enige laag die HTTP doet. Sync (bench-context), pagineert, doet backoff op rate-limiting. Gemodelleerd op de bestaande async MCP-client, maar synchroon met `requests`.

**Files:**
- Create: `wefact_sync/__init__.py` (leeg)
- Create: `wefact_sync/client.py`
- Test: `tests/test_wefact_client.py`

**Interfaces:**
- Consumes: niets.
- Produces:
  - `class WeFactClient(api_key: str, endpoint: str = DEFAULT_ENDPOINT, transport=None)` — `transport` is een injecteerbare `post(url, json)`-callable (default `requests.post`) zodat tests geen echte HTTP doen.
  - `WeFactClient.request(controller: str, action: str, params: dict | None = None) -> dict`
  - `WeFactClient.list_all(controller: str, action: str = "list", params: dict | None = None) -> list[dict]`
  - `WeFactClient.show(controller: str, identifier: str, id_field: str) -> dict`
  - Module-constante `DEFAULT_ENDPOINT = "https://api.mijnwefact.nl/v2/"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_client.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor de WeFact REST-client met een neppe transport."""

import unittest


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeTransport:
    """Verzamelt requests en geeft vooraf bepaalde antwoorden terug."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, json, timeout=None):
        self.calls.append(json)
        return _FakeResponse(self._responses.pop(0))


class TestRequest(unittest.TestCase):

    def _client(self, responses):
        from nixfact_integration.wefact_sync.client import WeFactClient

        transport = _FakeTransport(responses)
        return WeFactClient(api_key="KEY", transport=transport), transport

    def test_api_key_en_controller_in_body(self):
        client, t = self._client([{"status": "success"}])
        client.request("debtor", "list")
        self.assertEqual(t.calls[0]["api_key"], "KEY")
        self.assertEqual(t.calls[0]["controller"], "debtor")
        self.assertEqual(t.calls[0]["action"], "list")

    def test_list_all_pagineert_tot_leeg(self):
        # Pagina 1: 100 debtors, pagina 2: 5, pagina 3: 0 → stopt.
        p1 = {"status": "success", "debtors": [{"i": i} for i in range(100)]}
        p2 = {"status": "success", "debtors": [{"i": i} for i in range(5)]}
        p3 = {"status": "success", "debtors": []}
        client, t = self._client([p1, p2, p3])
        items = client.list_all("debtor")
        self.assertEqual(len(items), 105)
        self.assertEqual(t.calls[0]["offset"], 0)
        self.assertEqual(t.calls[1]["offset"], 100)

    def test_show_gebruikt_id_field(self):
        client, t = self._client([{"status": "success", "invoice": {"x": 1}}])
        client.show("invoice", "F0001", "InvoiceCode")
        self.assertEqual(t.calls[0]["action"], "show")
        self.assertEqual(t.calls[0]["InvoiceCode"], "F0001")

    def test_modified_since_param(self):
        client, t = self._client([{"status": "success", "debtors": []}])
        client.list_all("debtor", params={"modified": "2026-07-01 00:00:00"})
        self.assertEqual(t.calls[0]["modified"], "2026-07-01 00:00:00")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_client.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'nixfact_integration.wefact_sync.client'`

- [ ] **Step 3: Write the client**

Create `wefact_sync/__init__.py` (leeg). Create `wefact_sync/client.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Synchrone WeFact v2 REST-client.

WeFact v2 verwacht een POST met JSON-body ``{api_key, controller, action,
...params}``. Lijst-acties pagineren via ``offset`` (100/pagina); de
resultaatlijst heet het meervoud van de controller. De transport is
injecteerbaar zodat tests geen echte HTTP doen.
"""

from __future__ import annotations

import time
from typing import Callable

DEFAULT_ENDPOINT = "https://api.mijnwefact.nl/v2/"
PAGE_SIZE = 100
_MAX_RETRIES = 5


class WeFactError(Exception):
    """Een WeFact-antwoord met status != success."""


def _default_transport(url, json, timeout=None):  # pragma: no cover - echte HTTP
    import requests

    return requests.post(url, json=json, timeout=timeout or 60)


class WeFactClient:
    def __init__(
        self,
        api_key: str,
        endpoint: str = DEFAULT_ENDPOINT,
        transport: Callable | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("WeFact API-key ontbreekt.")
        self.api_key = api_key
        self.endpoint = endpoint
        self._transport = transport or _default_transport

    def request(self, controller: str, action: str, params: dict | None = None) -> dict:
        body = {
            "api_key": self.api_key,
            "controller": controller,
            "action": action,
        }
        if params:
            body.update(params)

        for poging in range(_MAX_RETRIES):
            resp = self._transport(self.endpoint, json=body, timeout=60)
            if getattr(resp, "status_code", 200) == 429:
                time.sleep(2**poging)  # exponentiële backoff
                continue
            data = resp.json()
            if data.get("status") != "success":
                raise WeFactError(
                    f"{controller}/{action}: {data.get('errors') or data}"
                )
            return data
        raise WeFactError(f"{controller}/{action}: rate-limit na {_MAX_RETRIES} pogingen")

    def list_all(
        self, controller: str, action: str = "list", params: dict | None = None
    ) -> list[dict]:
        alles: list[dict] = []
        offset = 0
        sleutel = f"{controller}s"
        while True:
            page_params = dict(params or {})
            page_params["offset"] = offset
            data = self.request(controller, action, page_params)
            items = data.get(sleutel) or data.get(controller) or []
            alles.extend(items)
            if len(items) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return alles

    def show(self, controller: str, identifier: str, id_field: str) -> dict:
        data = self.request(controller, "show", {id_field: identifier})
        return data.get(controller, data)
```

- [ ] **Step 4: Run test + lint**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_client.py -v
ruff check nixfact_integration/
```
Expected: 4 tests PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
git add nixfact_integration/nixfact_integration/wefact_sync/__init__.py \
        nixfact_integration/nixfact_integration/wefact_sync/client.py \
        nixfact_integration/nixfact_integration/tests/test_wefact_client.py
git commit -m "feat(wefact): synchrone REST-client met paginatie en backoff"
```

---

### Task 4: Pure mapping — status + debiteur

Puur, frappe-vrij. Statustekst → NIXFact-status (met creditnota-detectie) en debiteur → Customer/Address.

**Files:**
- Create: `wefact_sync/mapping/__init__.py` (leeg)
- Create: `wefact_sync/mapping/status.py`
- Create: `wefact_sync/mapping/debtor.py`
- Test: `tests/test_wefact_mapping_debtor.py`

**Interfaces:**
- Consumes: niets.
- Produces:
  - `status.StatusResultaat` (frozen dataclass): `status: str`, `is_creditnota: bool`, `onbekend: bool`.
  - `status.nixfact_status(status_tekst: str, bedrag_incl: float) -> StatusResultaat`.
  - `debtor.debtor_to_customer(wf: dict) -> dict` — sleutels: `customer_name`, `customer_type`, `tax_id`, `wefact_identifier`, `wefact_debtor_code`.
  - `debtor.debtor_to_address(wf: dict) -> dict | None` — `None` als er geen adresgegeven is; anders `address_line1`, `city`, `pincode`, `country_code`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_mapping_debtor.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor status- en debiteurmapping (puur)."""

import unittest

from nixfact_integration.wefact_sync.mapping.status import nixfact_status
from nixfact_integration.wefact_sync.mapping.debtor import (
    debtor_to_address,
    debtor_to_customer,
)


class TestStatus(unittest.TestCase):

    def test_verzonden(self):
        r = nixfact_status("Verzonden", 100.0)
        self.assertEqual(r.status, "Verstuurd")
        self.assertFalse(r.is_creditnota)
        self.assertFalse(r.onbekend)

    def test_betaald(self):
        self.assertEqual(nixfact_status("Betaald", 100.0).status, "Betaald")

    def test_concept(self):
        self.assertEqual(nixfact_status("Concept", 100.0).status, "Concept")

    def test_negatief_bedrag_is_creditnota(self):
        r = nixfact_status("Betaald", -50.0)
        self.assertTrue(r.is_creditnota)

    def test_credit_in_tekst_is_creditnota(self):
        r = nixfact_status("Creditfactuur", -50.0)
        self.assertTrue(r.is_creditnota)

    def test_onbekende_status_valt_terug_op_concept_met_vlag(self):
        r = nixfact_status("Iets Nieuws", 100.0)
        self.assertEqual(r.status, "Concept")
        self.assertTrue(r.onbekend)


class TestDebtorCustomer(unittest.TestCase):

    def _bedrijf(self):
        return {
            "Identifier": "42",
            "DebtorCode": "DB0042",
            "CompanyName": "Klant B.V.",
            "Initials": "J",
            "SurName": "Jansen",
            "TaxNumber": "NL999999999B01",
            "Address": "Dorpsstraat 1",
            "ZipCode": "3511 AA",
            "City": "Utrecht",
            "Country": "NL",
        }

    def test_bedrijf_naam_en_type(self):
        c = debtor_to_customer(self._bedrijf())
        self.assertEqual(c["customer_name"], "Klant B.V.")
        self.assertEqual(c["customer_type"], "Company")
        self.assertEqual(c["tax_id"], "NL999999999B01")
        self.assertEqual(c["wefact_identifier"], "42")
        self.assertEqual(c["wefact_debtor_code"], "DB0042")

    def test_persoon_zonder_bedrijfsnaam(self):
        wf = self._bedrijf()
        wf["CompanyName"] = ""
        c = debtor_to_customer(wf)
        self.assertEqual(c["customer_name"], "J Jansen")
        self.assertEqual(c["customer_type"], "Individual")

    def test_adres(self):
        a = debtor_to_address(self._bedrijf())
        self.assertEqual(a["address_line1"], "Dorpsstraat 1")
        self.assertEqual(a["city"], "Utrecht")
        self.assertEqual(a["pincode"], "3511 AA")
        self.assertEqual(a["country_code"], "NL")

    def test_geen_adres_geeft_none(self):
        wf = self._bedrijf()
        wf["Address"] = ""
        wf["City"] = ""
        self.assertIsNone(debtor_to_address(wf))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_debtor.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.mapping.status`

- [ ] **Step 3: Write status mapping**

Create `wefact_sync/mapping/__init__.py` (leeg). Create `wefact_sync/mapping/status.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-statustekst → NIXFact-status, plus creditnota-detectie.

WeFacts numerieke statuscodes wijken af van hun eigen documentatie; de
tekst uit ``Translations.Status`` is de betrouwbare bron. Onbekende
statussen vallen veilig terug op 'Concept' met een vlag, zodat een nieuwe
WeFact-status nooit stil verkeerd landt.
"""

from __future__ import annotations

from dataclasses import dataclass

# WeFact-statustekst (lowercase) → NIXFact-status.
_STATUS_MAP = {
    "concept": "Concept",
    "verzonden": "Verstuurd",
    "verstuurd": "Verstuurd",
    "betaald": "Betaald",
    "verlopen": "Verstuurd",
    "herinnering": "Verstuurd",
    "aanmaning": "Verstuurd",
    "gedeeltelijk betaald": "Verstuurd",
    "creditfactuur": "Betaald",
    "oninbaar": "Oninbaar",
}


@dataclass(frozen=True)
class StatusResultaat:
    status: str
    is_creditnota: bool
    onbekend: bool


def nixfact_status(status_tekst: str, bedrag_incl: float) -> StatusResultaat:
    tekst = (status_tekst or "").strip().lower()
    status = _STATUS_MAP.get(tekst)
    onbekend = status is None
    if onbekend:
        status = "Concept"
    is_credit = float(bedrag_incl or 0) < 0 or "credit" in tekst
    return StatusResultaat(status=status, is_creditnota=is_credit, onbekend=onbekend)
```

- [ ] **Step 4: Write debtor mapping**

Create `wefact_sync/mapping/debtor.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-debiteur → ERPNext Customer- en Address-dict. Puur."""

from __future__ import annotations


def debtor_to_customer(wf: dict) -> dict:
    bedrijf = (wf.get("CompanyName") or "").strip()
    if bedrijf:
        naam = bedrijf
        soort = "Company"
    else:
        naam = f"{(wf.get('Initials') or '').strip()} {(wf.get('SurName') or '').strip()}".strip()
        soort = "Individual"
    return {
        "customer_name": naam or f"WeFact {wf.get('DebtorCode') or wf.get('Identifier')}",
        "customer_type": soort,
        "tax_id": (wf.get("TaxNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_debtor_code": (wf.get("DebtorCode") or "").strip(),
    }


def debtor_to_address(wf: dict) -> dict | None:
    straat = (wf.get("Address") or "").strip()
    stad = (wf.get("City") or "").strip()
    if not straat and not stad:
        return None
    return {
        "address_line1": straat,
        "city": stad,
        "pincode": (wf.get("ZipCode") or "").strip(),
        "country_code": (wf.get("Country") or "NL").strip().upper(),
    }
```

- [ ] **Step 5: Run test + lint**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_debtor.py -v
ruff check nixfact_integration/
```
Expected: 10 tests PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
git add nixfact_integration/nixfact_integration/wefact_sync/mapping \
        nixfact_integration/nixfact_integration/tests/test_wefact_mapping_debtor.py
git commit -m "feat(wefact): pure status- en debiteurmapping"
```

---

### Task 5: Pure mapping — verkoopfactuur → Factuur + regels

Het hart van de import. Zet een WeFact-factuurdetail om naar een NixFact-Factuur-dict met regels, btw-categorie per regel, statusmapping en creditnota-markering.

**Files:**
- Create: `wefact_sync/mapping/invoice.py`
- Test: `tests/test_wefact_mapping_invoice.py`

**Interfaces:**
- Consumes: `status.nixfact_status`.
- Produces:
  - `invoice.btw_categorie(tax_code: str, tax_percentage: float) -> str` — `Verlegd` als tax_code met `VS`/`V0`-verlegd-indicatie, `Nultarief` bij 0%, anders `Standaard`. (Vrijstelling niet in WeFact-data waargenomen; `Standaard`/`Nultarief`/`Verlegd` volstaan.)
  - `invoice.invoice_to_factuur(wf: dict) -> dict` — sleutels: `factuurnummer`, `factuur_datum`, `referentie`, `wefact_identifier`, `wefact_debtor_code`, `status`, `is_creditnota` (bool), `onbekende_status` (bool), `regels` (list van dicts met `omschrijving`, `aantal`, `eenheidsprijs`, `btw_categorie`, `btw_percentage`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_wefact_mapping_invoice.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor verkoopfactuurmapping (puur), met echte WeFact-veldnamen."""

import unittest

from nixfact_integration.wefact_sync.mapping.invoice import (
    btw_categorie,
    invoice_to_factuur,
)


def _wf_factuur(**over):
    basis = {
        "Identifier": "815",
        "InvoiceCode": "F0790",
        "DebtorCode": "DB0042",
        "Date": "2026-03-01",
        "ReferenceNumber": "PO-9001",
        "AmountIncl": "242.00",
        "Translations": {"Status": "Verzonden"},
        "InvoiceLines": [
            {
                "Description": "Advies",
                "Number": "8",
                "PriceExcl": "125.00",
                "TaxCode": "V21",
                "TaxPercentage": "21",
            },
            {
                "Description": "Hosting",
                "Number": "1",
                "PriceExcl": "100.00",
                "TaxCode": "V0",
                "TaxPercentage": "0",
            },
        ],
    }
    basis.update(over)
    return basis


class TestBtwCategorie(unittest.TestCase):

    def test_standaard(self):
        self.assertEqual(btw_categorie("V21", 21), "Standaard")

    def test_nultarief(self):
        self.assertEqual(btw_categorie("V0", 0), "Nultarief")


class TestInvoiceToFactuur(unittest.TestCase):

    def test_kopvelden(self):
        f = invoice_to_factuur(_wf_factuur())
        self.assertEqual(f["factuurnummer"], "F0790")
        self.assertEqual(f["factuur_datum"], "2026-03-01")
        self.assertEqual(f["referentie"], "PO-9001")
        self.assertEqual(f["wefact_identifier"], "815")
        self.assertEqual(f["wefact_debtor_code"], "DB0042")
        self.assertEqual(f["status"], "Verstuurd")
        self.assertFalse(f["is_creditnota"])

    def test_regels(self):
        f = invoice_to_factuur(_wf_factuur())
        self.assertEqual(len(f["regels"]), 2)
        r0 = f["regels"][0]
        self.assertEqual(r0["omschrijving"], "Advies")
        self.assertEqual(r0["aantal"], 8.0)
        self.assertEqual(r0["eenheidsprijs"], 125.0)
        self.assertEqual(r0["btw_categorie"], "Standaard")
        self.assertEqual(r0["btw_percentage"], 21.0)
        self.assertEqual(f["regels"][1]["btw_categorie"], "Nultarief")

    def test_creditnota_negatief(self):
        wf = _wf_factuur(AmountIncl="-242.00",
                         Translations={"Status": "Creditfactuur"})
        f = invoice_to_factuur(wf)
        self.assertTrue(f["is_creditnota"])

    def test_onbekende_status_gemarkeerd(self):
        wf = _wf_factuur(Translations={"Status": "Supernieuw"})
        f = invoice_to_factuur(wf)
        self.assertEqual(f["status"], "Concept")
        self.assertTrue(f["onbekende_status"])

    def test_lege_invoicelines(self):
        wf = _wf_factuur(InvoiceLines=[])
        f = invoice_to_factuur(wf)
        self.assertEqual(f["regels"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_invoice.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.mapping.invoice`

- [ ] **Step 3: Write invoice mapping**

Create `wefact_sync/mapping/invoice.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""WeFact-verkoopfactuur → NixFact-Factuur-dict. Puur, frappe-vrij."""

from __future__ import annotations

from nixfact_integration.wefact_sync.mapping.status import nixfact_status


def btw_categorie(tax_code: str, tax_percentage: float) -> str:
    """Leid de NIXFact-btw-categorie af uit WeFact tax-code + percentage."""
    code = (tax_code or "").upper()
    if "VERLEGD" in code or code.endswith("VS"):
        return "Verlegd"
    if float(tax_percentage or 0) == 0:
        return "Nultarief"
    return "Standaard"


def _regel(wf_line: dict) -> dict:
    pct = float(wf_line.get("TaxPercentage") or 0)
    return {
        "omschrijving": (wf_line.get("Description") or "").strip(),
        "aantal": float(wf_line.get("Number") or 0),
        "eenheidsprijs": float(wf_line.get("PriceExcl") or 0),
        "btw_categorie": btw_categorie(wf_line.get("TaxCode"), pct),
        "btw_percentage": pct,
    }


def invoice_to_factuur(wf: dict) -> dict:
    bedrag_incl = float(wf.get("AmountIncl") or 0)
    status_tekst = (wf.get("Translations") or {}).get("Status") or ""
    res = nixfact_status(status_tekst, bedrag_incl)
    return {
        "factuurnummer": (wf.get("InvoiceCode") or "").strip(),
        "factuur_datum": (wf.get("Date") or "").strip(),
        "referentie": (wf.get("ReferenceNumber") or "").strip(),
        "wefact_identifier": str(wf.get("Identifier") or ""),
        "wefact_debtor_code": (wf.get("DebtorCode") or "").strip(),
        "status": res.status,
        "is_creditnota": res.is_creditnota,
        "onbekende_status": res.onbekend,
        "regels": [_regel(line) for line in (wf.get("InvoiceLines") or [])],
    }
```

- [ ] **Step 4: Run test + lint**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_mapping_invoice.py -v
ruff check nixfact_integration/
```
Expected: 7 tests PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
git add nixfact_integration/nixfact_integration/wefact_sync/mapping/invoice.py \
        nixfact_integration/nixfact_integration/tests/test_wefact_mapping_invoice.py
git commit -m "feat(wefact): pure verkoopfactuurmapping incl. regels en creditnota"
```

---

### Task 6: Upsert + engine + backfill-entrypoint

De ORM-laag (idempotent op `wefact_identifier`), het pure runrapport, en de orkestratie met per-record-isolatie. Sluit af met een handmatige bench-verificatie.

**Files:**
- Create: `wefact_sync/report.py`
- Create: `wefact_sync/upsert.py`
- Create: `wefact_sync/engine.py`
- Test: `tests/test_wefact_report.py`

**Interfaces:**
- Consumes: `client.WeFactClient`, `mapping.debtor.*`, `mapping.invoice.invoice_to_factuur`.
- Produces:
  - `report.Mislukking` (frozen dataclass): `entiteit: str`, `code: str`, `reden: str`.
  - `report.vat_rapport(verwerkt: int, mislukt: list[Mislukking], soort: str) -> str` — puur, Nederlandse samenvatting.
  - `upsert.ensure_company(naam: str) -> str`
  - `upsert.upsert_customer(customer: dict, address: dict | None) -> str`
  - `upsert.upsert_factuur(factuur: dict, company: str) -> str`
  - `engine.volledige_backfill(alleen: str | None = None) -> None` — bench-entrypoint.

- [ ] **Step 1: Write the failing test (pure report)**

Create `tests/test_wefact_report.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Tests voor het pure runrapport."""

import unittest

from nixfact_integration.wefact_sync.report import Mislukking, vat_rapport


class TestRapport(unittest.TestCase):

    def test_alles_goed(self):
        tekst = vat_rapport(815, [], "facturen")
        self.assertIn("815", tekst)
        self.assertIn("0 mislukt", tekst)

    def test_mislukkingen_worden_opgesomd(self):
        m = [
            Mislukking("factuur", "F0790", "klant onbekend"),
            Mislukking("factuur", "F0791", "datum ontbreekt"),
        ]
        tekst = vat_rapport(813, m, "facturen")
        self.assertIn("2 mislukt", tekst)
        self.assertIn("F0790", tekst)
        self.assertIn("klant onbekend", tekst)
        self.assertIn("F0791", tekst)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_report.py -v
```
Expected: FAIL — `ModuleNotFoundError: ...wefact_sync.report`

- [ ] **Step 3: Write the report module**

Create `wefact_sync/report.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Puur runrapport voor de WeFact-import. Geen frappe."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mislukking:
    entiteit: str
    code: str
    reden: str


def vat_rapport(verwerkt: int, mislukt: list[Mislukking], soort: str) -> str:
    regels = [f"WeFact-import {soort}: {verwerkt} verwerkt, {len(mislukt)} mislukt."]
    for m in mislukt:
        regels.append(f"- {m.entiteit} {m.code}: {m.reden}")
    return "\n".join(regels)
```

- [ ] **Step 4: Write the upsert layer**

Create `wefact_sync/upsert.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Idempotente ORM-laag voor de WeFact-import. Enige die de DB raakt."""

from __future__ import annotations

import frappe

ALDEWERELD = "Aldewereld Consultancy"


def ensure_company(naam: str = ALDEWERELD) -> str:
    """Maak (idempotent) de doelcompany aan als hij nog niet bestaat."""
    if frappe.db.exists("Company", naam):
        return naam
    frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": naam,
            "default_currency": "EUR",
            "country": "Netherlands",
            "tax_id": "NL002168402B79",
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
    return naam


def _find_by_wefact_id(doctype: str, wefact_id: str) -> str | None:
    if not wefact_id:
        return None
    return frappe.db.get_value(doctype, {"wefact_identifier": wefact_id}, "name")


def upsert_customer(customer: dict, address: dict | None) -> str:
    """Maak of werk een Customer bij, gekoppeld op wefact_identifier."""
    bestaand = _find_by_wefact_id("Customer", customer["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("Customer", bestaand)
        doc.update(customer)
    else:
        doc = frappe.get_doc({"doctype": "Customer", **customer})
    doc.save(ignore_permissions=True)

    if address:
        _upsert_address(doc.name, customer, address)
    frappe.db.commit()
    return doc.name


def _upsert_address(customer_name: str, customer: dict, address: dict) -> None:
    titel = f"{customer['wefact_identifier']}-WeFact"
    bestaand = frappe.db.get_value("Address", {"address_title": titel}, "name")
    velden = {
        "address_line1": address["address_line1"] or "-",
        "city": address["city"] or "-",
        "pincode": address["pincode"],
        "country": _land_uit_code(address["country_code"]),
    }
    if bestaand:
        adoc = frappe.get_doc("Address", bestaand)
        adoc.update(velden)
    else:
        adoc = frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": titel,
                "address_type": "Billing",
                "links": [
                    {"link_doctype": "Customer", "link_name": customer_name}
                ],
                **velden,
            }
        )
    adoc.save(ignore_permissions=True)


def _land_uit_code(code: str) -> str:
    naam = frappe.db.get_value("Country", {"code": (code or "nl").lower()}, "name")
    return naam or "Netherlands"


def upsert_factuur(factuur: dict, company: str) -> str:
    """Maak of werk een NixFact Factuur bij, gekoppeld op wefact_identifier."""
    klant = frappe.db.get_value(
        "Customer", {"wefact_debtor_code": factuur["wefact_debtor_code"]}, "name"
    )
    if not klant:
        raise ValueError(
            f"Geen klant voor debiteurcode {factuur['wefact_debtor_code']}"
        )

    kop = {
        "klant": klant,
        "company": company,
        "factuurnummer": factuur["factuurnummer"],
        "factuur_datum": factuur["factuur_datum"],
        "referentie": factuur["referentie"],
        "status": factuur["status"],
        "wefact_identifier": factuur["wefact_identifier"],
    }
    bestaand = _find_by_wefact_id("NixFact Factuur", factuur["wefact_identifier"])
    if bestaand:
        doc = frappe.get_doc("NixFact Factuur", bestaand)
        doc.update(kop)
        doc.set("regels", [])
    else:
        doc = frappe.get_doc({"doctype": "NixFact Factuur", **kop})
    for r in factuur["regels"]:
        doc.append("regels", r)
    # Lege factuur (geen regels) mag niet — Fase 1 eist reqd regels.
    if not doc.get("regels"):
        doc.append(
            "regels",
            {
                "omschrijving": factuur["factuurnummer"] or "WeFact-import",
                "aantal": 1,
                "eenheidsprijs": 0,
                "btw_categorie": "Nultarief",
                "btw_percentage": 0,
            },
        )
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
```

- [ ] **Step 5: Write the engine**

Create `wefact_sync/engine.py`:

```python
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

"""Orkestratie van de WeFact→NIXFact backfill.

Per-record geïsoleerd: één fout stopt de rest niet. Aan het eind een
zichtbaar rapport (scheduler-log + geconsolideerde Error Log).
"""

from __future__ import annotations

import frappe

from nixfact_integration.wefact_sync.client import WeFactClient
from nixfact_integration.wefact_sync.mapping.debtor import (
    debtor_to_address,
    debtor_to_customer,
)
from nixfact_integration.wefact_sync.mapping.invoice import invoice_to_factuur
from nixfact_integration.wefact_sync.report import Mislukking, vat_rapport
from nixfact_integration.wefact_sync import upsert


def _client() -> WeFactClient:
    settings = frappe.get_single("NixFact Instellingen")
    key = settings.get_password("wefact_api_key")
    return WeFactClient(api_key=key)


def _rapporteer(verwerkt: int, mislukt: list[Mislukking], soort: str) -> None:
    tekst = vat_rapport(verwerkt, mislukt, soort)
    frappe.logger("nixfact", allow_site=True).warning(tekst)
    if mislukt:
        frappe.log_error(title=f"WeFact-import {soort}", message=tekst)


def backfill_debiteuren(client: WeFactClient) -> None:
    verwerkt, mislukt = 0, []
    for wf in client.list_all("debtor"):
        try:
            upsert.upsert_customer(debtor_to_customer(wf), debtor_to_address(wf))
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(
                Mislukking("debiteur", str(wf.get("DebtorCode") or ""), str(exc))
            )
    _rapporteer(verwerkt, mislukt, "debiteuren")


def backfill_facturen(client: WeFactClient, company: str) -> None:
    verwerkt, mislukt = 0, []
    for kop in client.list_all("invoice"):
        code = kop.get("InvoiceCode") or ""
        try:
            detail = client.show("invoice", code, "InvoiceCode")
            upsert.upsert_factuur(invoice_to_factuur(detail), company)
            verwerkt += 1
        except Exception as exc:  # noqa: BLE001
            frappe.db.rollback()
            mislukt.append(Mislukking("factuur", code, str(exc)))
    _rapporteer(verwerkt, mislukt, "facturen")


def volledige_backfill(alleen: str | None = None) -> None:
    """Bench-entrypoint: importeer debiteuren (eerst) en verkoopfacturen."""
    client = _client()
    company = upsert.ensure_company()
    if alleen in (None, "debiteuren"):
        backfill_debiteuren(client)
    if alleen in (None, "facturen"):
        backfill_facturen(client, company)
```

- [ ] **Step 6: Run test + lint + volledige suite**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/test_wefact_report.py -v
PYTHONPATH=nixfact_integration python3 -m pytest \
  nixfact_integration/nixfact_integration/tests/ -q
ruff check nixfact_integration/
```
Expected: report-tests PASS, volledige suite groen, ruff clean.

- [ ] **Step 7: Commit**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce/.claude/worktrees/fase-1-factuurregels
git add nixfact_integration/nixfact_integration/wefact_sync/report.py \
        nixfact_integration/nixfact_integration/wefact_sync/upsert.py \
        nixfact_integration/nixfact_integration/wefact_sync/engine.py \
        nixfact_integration/nixfact_integration/tests/test_wefact_report.py
git commit -m "feat(wefact): upsert-laag, engine en backfill-entrypoint"
```

---

## Handmatige bench-verificatie (op R220 LXC 218, na Task 6)

Deze stappen kunnen niet in CI. Draai ze op de bench nadat Fase 1 + dit fundament gemigreerd zijn. **Eerst backup.**

- [ ] **Backup + migrate (draait de nieuwe patch + de custom fields)**

```bash
ssh root@192.168.178.88
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl backup --with-files && \
  bench --site erp.aldewereldconsultancy.nl migrate"
```
Expected: backup-pad + `[nixfact] WeFact custom fields aangemaakt op Customer`.

- [ ] **API-key zetten** (in de UI: NixFact Instellingen → WeFact-sync → API-key), of via console:

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl console" <<'EOF'
s = frappe.get_single("NixFact Instellingen")
s.wefact_api_key = "PLAK_DE_ECHTE_KEY"
s.save(); frappe.db.commit()
print("key gezet")
EOF
```

- [ ] **Kleine proef-backfill eerst (alleen debiteuren)**

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl execute \
  nixfact_integration.wefact_sync.engine.volledige_backfill \
  --kwargs '{\"alleen\": \"debiteuren\"}'"
```
Expected: log `WeFact-import debiteuren: 276 verwerkt, 0 mislukt` (of met een klein aantal mislukt + reden).

- [ ] **Controleer de aantallen**

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl console" <<'EOF'
print("customers met wefact_id:",
      frappe.db.count("Customer", {"wefact_identifier": ["!=", ""]}))
EOF
```
Expected: circa 276.

- [ ] **Dan de facturen** (dit doet ~815 detail-fetches; kan minuten duren)

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl execute \
  nixfact_integration.wefact_sync.engine.volledige_backfill \
  --kwargs '{\"alleen\": \"facturen\"}'"
```
Expected: log `WeFact-import facturen: N verwerkt, M mislukt`. Bekijk een steekproef-factuur in de UI: klant gekoppeld, regels aanwezig, `wefact_identifier` gevuld, geen aanmaning getriggerd.

- [ ] **Idempotentie-check: draai facturen nog eens**

```bash
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl execute \
  nixfact_integration.wefact_sync.engine.volledige_backfill \
  --kwargs '{\"alleen\": \"facturen\"}'"
pct exec 218 -- bash -c "cd /home/frappe/frappe-bench && \
  bench --site erp.aldewereldconsultancy.nl console" <<'EOF'
print("facturen totaal:", frappe.db.count("NixFact Factuur"))
EOF
```
Expected: het factuuraantal blijft gelijk aan de eerste run (geen dubbels).

## Definition of done

- [ ] Alle nieuwe pytests groen; `ruff check nixfact_integration/` clean; volledige suite groen.
- [ ] Debiteuren en verkoopfacturen staan in NIXFact onder company Aldewereld Consultancy, met regels en `wefact_identifier`.
- [ ] Tweede backfill-run maakt geen dubbels (idempotent).
- [ ] Geen enkele geïmporteerde factuur triggert een herinnering/aanmaning (schaduwmodus-invariant).
- [ ] Onbekende WeFact-statussen landen als Concept met een waarschuwing in het rapport.

## Wat hierna volgt (tweede plan, niet hier)

Inkoopfacturen + PDF-bijlagen, abonnementen (facturering uit), en de incrementele sync + scheduler + cursor. Pas plannen nadat deze backfill tegen echte WeFact-data is bevestigd — de vorm van creditnota's en de betrouwbaarheid van `Modified` bepalen details daarvan. Zie spec §13 fasen 4-6.
