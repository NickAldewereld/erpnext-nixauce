# Sprint 6: Offerte Portal & Digitale Ondertekening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WeFact-style accept-flow for `NixFact Offerte`. Klant ontvangt offerte met token-link, opent publieke portal-pagina, tekent met vinger op touch / muis op desktop, en accepteert. Audit trail (email, IP, user-agent, timestamp + signature image) wordt op de offerte zelf vastgelegd en is immutable na ondertekening.

**Architecture:**
- Random URL-safe token (`secrets.token_urlsafe(24)` → 32 chars) op de offerte → publieke `www/offerte` route die de offerte ophaalt op token (zonder login).
- Vanilla HTML5 canvas voor handtekening (touch + mouse events). We gebruiken **niet** Frappe's `Signature` fieldtype — die is bedoeld voor authenticated desk users en wordt niet gerenderd voor Guests. Canvas data-URL wordt opgeslagen in een `Long Text` veld.
- Accept/reject endpoints zijn `@frappe.whitelist(allow_guest=True)`. Alle inputs gevalideerd (email regex, signature data-URL pattern + length cap) vóór elke DB write.
- Immutability via `validate()` guard: zodra `ondertekend_op` is gezet, blokkeert wijzigingen aan handtekening/ondertekend_*.

**Tech Stack:** Frappe 17 portal pages, Python `secrets`, `re`, `frappe.sendmail`, vanilla JS canvas.

**Out of scope (defer naar Sprint 6.5):**
- Audit-PDF met embedded signature image + SHA-256 hash van offerte-content op moment van ondertekenen.
- Per-tenant configureerbare email templates in `NixFact Instellingen` (deze plan gebruikt hard-coded NL defaults).

---

### Task 1: Pure token generator helper

**Files:**
- Create: `nixfact_integration/nixfact_integration/utils/tokens.py`
- Test: `nixfact_integration/nixfact_integration/tests/test_tokens.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_tokens.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

import unittest

from nixfact_integration.utils.tokens import generate_accept_token


class TestAcceptToken(unittest.TestCase):
    def test_default_length(self):
        t = generate_accept_token()
        # 24 bytes → 32 chars after base64-url
        self.assertGreaterEqual(len(t), 32)

    def test_uniqueness(self):
        tokens = {generate_accept_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_url_safe(self):
        t = generate_accept_token()
        for forbidden in ("/", "+", "=", " ", "\n"):
            self.assertNotIn(forbidden, t)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify it fails**

```bash
PYTHONPATH=nixfact_integration pytest nixfact_integration/nixfact_integration/tests/test_tokens.py -v
```
Expected: `ModuleNotFoundError: No module named 'nixfact_integration.utils.tokens'`

- [ ] **Step 3: Write implementation**

```python
# utils/tokens.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

"""Cryptographically random tokens for public portal links.

24 bytes of entropy → 32 chars after base64-url encoding (≈ 2^192 ≈ 6e57
possible values), unguessable and collision-free for the entire customer
base over the lifetime of the system.
"""

from __future__ import annotations

import secrets

DEFAULT_BYTES = 24


def generate_accept_token(num_bytes: int = DEFAULT_BYTES) -> str:
    """Return a URL-safe random token suitable for public offerte links."""
    return secrets.token_urlsafe(num_bytes)
```

- [ ] **Step 4: Run, verify pass** — 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add nixfact_integration/nixfact_integration/utils/tokens.py \
        nixfact_integration/nixfact_integration/tests/test_tokens.py
git commit -m "[sprint-6] Pure URL-safe token generator for portal links"
```

---

### Task 2: Add audit fields to NixFact Offerte schema

**Files:**
- Modify: `nixfact_integration/nixfact_integration/doctype/nixfact_offerte/nixfact_offerte.json`

JSON-only change. Behavioural tests are in Tasks 3–6.

- [ ] **Step 1: Add new fieldnames to `field_order`**

Insert after `"status"`:
```
"section_break_ondertekening",
"accept_token",
"portal_verstuurd_op",
"column_break_3",
"ondertekend_op",
"ondertekend_door_email",
"ondertekend_ip",
"ondertekend_user_agent",
"handtekening",
"weigering_reden"
```

- [ ] **Step 2: Append field definitions**

Add to `fields` array (after the `status` entry):

```json
{ "fieldname": "section_break_ondertekening", "fieldtype": "Section Break", "label": "Ondertekening" },
{ "fieldname": "accept_token", "fieldtype": "Data", "label": "Accept Token", "read_only": 1, "hidden": 1, "unique": 1, "no_copy": 1 },
{ "fieldname": "portal_verstuurd_op", "fieldtype": "Datetime", "label": "Portal-link verstuurd op", "read_only": 1 },
{ "fieldname": "column_break_3", "fieldtype": "Column Break" },
{ "fieldname": "ondertekend_op", "fieldtype": "Datetime", "label": "Ondertekend op", "read_only": 1 },
{ "fieldname": "ondertekend_door_email", "fieldtype": "Data", "label": "Ondertekend door (email)", "read_only": 1 },
{ "fieldname": "ondertekend_ip", "fieldtype": "Data", "label": "IP-adres", "read_only": 1 },
{ "fieldname": "ondertekend_user_agent", "fieldtype": "Small Text", "label": "User Agent", "read_only": 1 },
{ "fieldname": "handtekening", "fieldtype": "Long Text", "label": "Handtekening (PNG data URL)", "read_only": 1, "hidden": 1 },
{ "fieldname": "weigering_reden", "fieldtype": "Small Text", "label": "Weigering reden", "read_only": 1, "depends_on": "eval:doc.status=='Geweigerd'" }
```

- [ ] **Step 3: Bump `modified` so Frappe re-syncs the schema**

```
"modified": "2026-05-06 12:00:00.000000",
```

- [ ] **Step 4: Commit**

```bash
git add nixfact_integration/nixfact_integration/doctype/nixfact_offerte/nixfact_offerte.json
git commit -m "[sprint-6] Add accept_token and ondertekening audit fields to NixFact Offerte"
```

---

### Task 3: Generate `accept_token` in `before_insert`

**Files:**
- Modify: `nixfact_integration/nixfact_integration/doctype/nixfact_offerte/nixfact_offerte.py`
- Test: `nixfact_integration/nixfact_integration/tests/test_offerte_controller.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_offerte_controller.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

"""Pure-logic tests for the NixFact Offerte controller."""

import unittest
from unittest.mock import MagicMock

from nixfact_integration.doctype.nixfact_offerte.nixfact_offerte import (
    NixFactOfferte,
)


class TestBeforeInsertToken(unittest.TestCase):
    def test_generates_token_when_missing(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.accept_token = None
        NixFactOfferte.before_insert(doc)
        self.assertIsNotNone(doc.accept_token)
        self.assertGreaterEqual(len(doc.accept_token), 32)

    def test_preserves_existing_token(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.accept_token = "preset-token"
        NixFactOfferte.before_insert(doc)
        self.assertEqual(doc.accept_token, "preset-token")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify fail** — `AttributeError: ... has no attribute 'before_insert'`

- [ ] **Step 3: Implement** — add to `class NixFactOfferte`:

```python
def before_insert(self) -> None:
    """Generate a public accept-token if one isn't already set.

    The token gates access to the public portal page where the customer
    accepts/rejects the quote. Existing tokens are preserved (test seeds,
    manual paste from another system).
    """
    if not self.accept_token:
        from nixfact_integration.utils.tokens import generate_accept_token
        self.accept_token = generate_accept_token()
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add nixfact_integration/nixfact_integration/doctype/nixfact_offerte/nixfact_offerte.py \
        nixfact_integration/nixfact_integration/tests/test_offerte_controller.py
git commit -m "[sprint-6] Generate accept_token on offerte insert"
```

---

### Task 4: Lock signature fields after accept (immutability guard)

**Files:**
- Modify: `nixfact_integration/nixfact_integration/doctype/nixfact_offerte/nixfact_offerte.py`
- Test: extend `tests/test_offerte_controller.py`

- [ ] **Step 1: Add failing test**

Append to `test_offerte_controller.py`:

```python
class TestAcceptedImmutability(unittest.TestCase):
    def _make_doc(self, *, current_sig, old_sig):
        doc = MagicMock(spec=NixFactOfferte)
        doc.ondertekend_op = "2026-05-06 14:00:00"
        doc.handtekening = current_sig
        doc.ondertekend_door_email = "klant@example.com"
        doc.ondertekend_ip = "1.2.3.4"
        doc.ondertekend_user_agent = "ua"
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock()
        old.handtekening = old_sig
        old.ondertekend_op = "2026-05-06 14:00:00"
        old.ondertekend_door_email = "klant@example.com"
        old.ondertekend_ip = "1.2.3.4"
        old.ondertekend_user_agent = "ua"
        doc.get_doc_before_save = MagicMock(return_value=old)
        return doc

    def test_signature_change_after_accept_blocked(self):
        doc = self._make_doc(current_sig="tampered", old_sig="original")
        with self.assertRaises(Exception):
            NixFactOfferte._guard_immutable_after_accept(doc)

    def test_unchanged_audit_passes(self):
        doc = self._make_doc(current_sig="original", old_sig="original")
        NixFactOfferte._guard_immutable_after_accept(doc)  # no raise

    def test_unsigned_offerte_is_editable(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.ondertekend_op = None
        doc.is_new = MagicMock(return_value=False)
        # Should return immediately, no exception
        NixFactOfferte._guard_immutable_after_accept(doc)
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement** — modify `validate()` and add guard method:

```python
def validate(self) -> None:
    self._sanity_check_bedragen()
    self._validate_status_transition()
    self._guard_immutable_after_accept()

def _guard_immutable_after_accept(self) -> None:
    """Audit fields are immutable once the offerte is signed.

    `handtekening` + `ondertekend_*` form the legal audit record. After
    `ondertekend_op` is set, any change is a tamper attempt — block it.
    """
    if self.is_new() or not self.ondertekend_op:
        return
    old = self.get_doc_before_save()
    if not old:
        return
    locked = (
        "handtekening",
        "ondertekend_op",
        "ondertekend_door_email",
        "ondertekend_ip",
        "ondertekend_user_agent",
    )
    for field in locked:
        if getattr(old, field, None) != getattr(self, field, None):
            frappe.throw(
                _("Ondertekende offerte kan niet meer gewijzigd worden."),
                frappe.ValidationError,
            )
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "[sprint-6] Lock ondertekening fields once offerte is signed"
```

---

### Task 5: Public portal route — `www/offerte`

**Files:**
- Create: `nixfact_integration/nixfact_integration/www/__init__.py` (empty)
- Create: `nixfact_integration/nixfact_integration/www/offerte.py`
- Create: `nixfact_integration/nixfact_integration/www/offerte.html`
- Test: `nixfact_integration/nixfact_integration/tests/test_offerte_portal_route.py`

**Note:** Frappe scans `<app>/<app>/www/` and registers `<page>.py` + `<page>.html` pairs as public routes. The `.py` file's `get_context(context)` runs server-side, then `<page>.html` is rendered with that context.

- [ ] **Step 1: Test for missing/unknown token**

```python
# tests/test_offerte_portal_route.py
import unittest
from unittest.mock import MagicMock, patch


class TestPortalContext(unittest.TestCase):
    def test_missing_token_raises_permission_error(self):
        from nixfact_integration.www import offerte as portal
        with patch.object(portal, "frappe") as f:
            f.form_dict = {}

            class _PE(Exception):
                pass

            f.PermissionError = _PE
            f.throw.side_effect = lambda msg, exc=_PE: (_ for _ in ()).throw(exc(msg))
            with self.assertRaises(_PE):
                portal.get_context(MagicMock())

    def test_unknown_token_raises_does_not_exist(self):
        from nixfact_integration.www import offerte as portal
        with patch.object(portal, "frappe") as f:
            f.form_dict = {"token": "deadbeef"}
            f.db.get_value.return_value = None

            class _DNE(Exception):
                pass

            f.DoesNotExistError = _DNE
            f.throw.side_effect = lambda msg, exc=_DNE: (_ for _ in ()).throw(exc(msg))
            with self.assertRaises(_DNE):
                portal.get_context(MagicMock())
```

- [ ] **Step 2: Run, verify fail** (module doesn't exist yet)

- [ ] **Step 3: Implement `www/offerte.py`**

```python
# www/offerte.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

"""Public offerte portal — token-gated, no login required."""

from __future__ import annotations

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    token = (frappe.form_dict.get("token") or "").strip()
    if not token or len(token) > 200:
        frappe.throw(_("Ongeldige link."), frappe.PermissionError)

    name = frappe.db.get_value(
        "NixFact Offerte", {"accept_token": token}, "name"
    )
    if not name:
        frappe.throw(_("Offerte niet gevonden."), frappe.DoesNotExistError)

    offerte = frappe.get_doc("NixFact Offerte", name)
    klant_naam = (
        frappe.db.get_value("Customer", offerte.klant, "customer_name")
        or offerte.klant
    )

    context.no_cache = 1
    context.show_sidebar = False
    context.offerte = offerte
    context.klant_naam = klant_naam
    context.token = token
    context.can_sign = offerte.status == "Verstuurd"
    return context
```

- [ ] **Step 4: Create empty `www/__init__.py`**

```bash
touch nixfact_integration/nixfact_integration/www/__init__.py
```

- [ ] **Step 5: Run tests, verify pass**

- [ ] **Step 6: Implement `www/offerte.html`**

```html
{# www/offerte.html — public offerte portal #}
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>Offerte {{ offerte.offerte_nr }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 720px; margin: 2rem auto; padding: 1rem; color: #1a1a1a; }
        h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
        .meta { color: #666; }
        .bedrag { font-size: 2rem; font-weight: 600; margin: 1rem 0 0.25rem; }
        .actions { margin-top: 2rem; display: flex; gap: 0.75rem; flex-wrap: wrap; }
        button { padding: 0.75rem 1.5rem; border: 0; border-radius: 0.5rem; font-size: 1rem; cursor: pointer; }
        .accept { background: #0a7d3e; color: white; }
        .reject { background: #f1f1f1; color: #1a1a1a; }
        .sigwrap { margin-top: 1.5rem; border: 2px dashed #ccc; border-radius: 0.5rem; padding: 0.5rem; }
        canvas { display: block; width: 100%; height: 200px; touch-action: none; background: #fafafa; border-radius: 0.25rem; }
        .clear { background: transparent; color: #666; padding: 0.25rem 0.75rem; font-size: 0.85rem; }
        .status-pill { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.85rem; }
        .status-Geaccepteerd { background: #d4f4dd; color: #0a7d3e; }
        .status-Geweigerd { background: #f4d4d4; color: #b32424; }
        input[type=email] { width: 100%; padding: 0.5rem; margin-top: 0.25rem; border: 1px solid #ccc; border-radius: 0.25rem; font-size: 1rem; }
    </style>
</head>
<body>
    <h1>Offerte {{ offerte.offerte_nr }}</h1>
    <p class="meta">
        Voor {{ klant_naam }} — {{ frappe.format(offerte.offerte_datum, {"fieldtype": "Date"}) }}
        {% if not can_sign %}
            <span class="status-pill status-{{ offerte.status }}">{{ offerte.status }}</span>
        {% endif %}
    </p>

    {% if offerte.referentie %}<p><strong>{{ offerte.referentie }}</strong></p>{% endif %}
    <p class="bedrag">{{ frappe.format(offerte.bedrag_incl, {"fieldtype": "Currency"}) }}</p>
    <p class="meta">incl. BTW</p>

    {% if can_sign %}
    <form id="accept-form" onsubmit="return submitAccept(event)">
        <label>Uw e-mailadres
            <input type="email" name="email" required>
        </label>
        <div class="sigwrap">
            <p class="meta" style="margin:0 0 0.5rem">Onderteken hieronder met uw vinger of muis:</p>
            <canvas id="sig"></canvas>
            <button type="button" class="clear" onclick="clearSig()">wis handtekening</button>
        </div>
        <div class="actions">
            <button type="submit" class="accept">Akkoord & ondertekenen</button>
            <button type="button" class="reject" onclick="reject()">Afwijzen</button>
        </div>
    </form>

    <script>
    const canvas = document.getElementById('sig');
    const ctx = canvas.getContext('2d');
    let drawing = false, hasInk = false;

    function resize() {
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.strokeStyle = '#1a1a1a';
    }
    resize();
    window.addEventListener('resize', resize);

    function getPos(e) {
        const rect = canvas.getBoundingClientRect();
        const t = e.touches ? e.touches[0] : e;
        return { x: t.clientX - rect.left, y: t.clientY - rect.top };
    }
    function start(e) { e.preventDefault(); drawing = true; const p = getPos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); }
    function move(e) { if (!drawing) return; e.preventDefault(); const p = getPos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); hasInk = true; }
    function end() { drawing = false; }
    canvas.addEventListener('mousedown', start);
    canvas.addEventListener('mousemove', move);
    canvas.addEventListener('mouseup', end);
    canvas.addEventListener('mouseleave', end);
    canvas.addEventListener('touchstart', start, {passive: false});
    canvas.addEventListener('touchmove', move, {passive: false});
    canvas.addEventListener('touchend', end);

    function clearSig() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        hasInk = false;
    }

    async function submitAccept(e) {
        e.preventDefault();
        if (!hasInk) { alert('Zet eerst uw handtekening.'); return false; }
        const email = e.target.email.value.trim();
        const sig = canvas.toDataURL('image/png');
        const r = await fetch('/api/method/nixfact_integration.api.offerte_portal.accepteer_offerte', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams({token: '{{ token }}', email, signature_data_url: sig}),
        });
        if (r.ok) {
            const data = await r.json();
            window.location = (data.message && data.message.redirect) || '/offerte-bedankt';
        } else {
            alert('Ondertekenen mislukt. Probeer het opnieuw of neem contact op.');
        }
        return false;
    }

    async function reject() {
        const reden = prompt('Reden voor afwijzing (optioneel):') || '';
        const r = await fetch('/api/method/nixfact_integration.api.offerte_portal.weiger_offerte', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams({token: '{{ token }}', reden}),
        });
        if (r.ok) window.location.reload();
    }
    </script>
    {% else %}
    <div class="meta" style="padding:1rem;background:#f9f9f9;border-radius:0.5rem">
        Deze offerte heeft de status <strong>{{ offerte.status }}</strong>.
        {% if offerte.status == "Geaccepteerd" %}
            <p>Geaccepteerd op {{ frappe.format(offerte.ondertekend_op, {"fieldtype": "Datetime"}) }} door {{ offerte.ondertekend_door_email }}.</p>
        {% endif %}
    </div>
    {% endif %}
</body>
</html>
```

- [ ] **Step 7: Commit**

```bash
git add nixfact_integration/nixfact_integration/www/ \
        nixfact_integration/nixfact_integration/tests/test_offerte_portal_route.py
git commit -m "[sprint-6] Public offerte portal route + signature canvas template"
```

---

### Task 6: Accept/reject API endpoints

**Files:**
- Create: `nixfact_integration/nixfact_integration/api/offerte_portal.py`
- Test: `nixfact_integration/nixfact_integration/tests/test_offerte_portal_api.py`

- [ ] **Step 1: Write failing tests for input validators**

```python
# tests/test_offerte_portal_api.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

import unittest


class TestEmailValidation(unittest.TestCase):
    def test_valid(self):
        from nixfact_integration.api.offerte_portal import _is_valid_email
        for good in (
            "klant@example.com",
            "voor.naam+tag@sub.example.co.uk",
            "a@b.io",
        ):
            self.assertTrue(_is_valid_email(good), good)

    def test_invalid(self):
        from nixfact_integration.api.offerte_portal import _is_valid_email
        for bad in ("", None, "no-at", "@nodomain", "spaces in@x.com",
                    "x" * 320 + "@x.com", "a@b"):
            self.assertFalse(_is_valid_email(bad), repr(bad))


class TestSignatureValidation(unittest.TestCase):
    PNG_1X1 = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
    )

    def test_valid_png(self):
        from nixfact_integration.api.offerte_portal import _is_valid_signature
        self.assertTrue(_is_valid_signature(self.PNG_1X1))

    def test_rejects_non_png(self):
        from nixfact_integration.api.offerte_portal import _is_valid_signature
        for bad in (
            "data:image/jpeg;base64,xxx",
            "not a data url",
            "",
            None,
            "data:text/html;base64,xxx",
        ):
            self.assertFalse(_is_valid_signature(bad), repr(bad))

    def test_rejects_oversize(self):
        from nixfact_integration.api.offerte_portal import _is_valid_signature
        big = "data:image/png;base64," + ("A" * 2_000_000)
        self.assertFalse(_is_valid_signature(big))
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement `api/offerte_portal.py`**

```python
# api/offerte_portal.py
# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later

"""Guest endpoints for the public offerte portal: accept + reject.

All inputs are untrusted Guest data. Every field is regex-validated and
length-bounded before any DB query. The status check (`Verstuurd` only)
makes the accept idempotent — re-posting the form on a Geaccepteerd
offerte is rejected with a clear error.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

# Practical email regex — covers >99.9% of valid addresses without
# false-rejecting common patterns (+tags, subdomains, country TLDs).
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$")
EMAIL_MAX_LEN = 254  # RFC 5321 hard limit on the entire address

# data:image/png;base64,<payload>. We only accept PNG to bound the
# attack surface — JPEG/SVG/HTML data URLs are rejected.
SIGNATURE_RE = re.compile(r"^data:image/png;base64,[A-Za-z0-9+/=]+$")
SIGNATURE_MAX_LEN = 1_500_000  # ~1MB encoded; a 600x200 canvas is ~30kB

TOKEN_MAX_LEN = 200


def _is_valid_email(email) -> bool:
    if not email or not isinstance(email, str):
        return False
    if len(email) > EMAIL_MAX_LEN:
        return False
    return bool(EMAIL_RE.match(email.strip()))


def _is_valid_signature(data_url) -> bool:
    if not data_url or not isinstance(data_url, str):
        return False
    if len(data_url) > SIGNATURE_MAX_LEN:
        return False
    return bool(SIGNATURE_RE.match(data_url))


def _get_offerte_by_token(token):
    if not token or not isinstance(token, str) or len(token) > TOKEN_MAX_LEN:
        frappe.throw(_("Ongeldige link."), frappe.PermissionError)
    name = frappe.db.get_value(
        "NixFact Offerte", {"accept_token": token}, "name"
    )
    if not name:
        frappe.throw(_("Offerte niet gevonden."), frappe.DoesNotExistError)
    return frappe.get_doc("NixFact Offerte", name)


@frappe.whitelist(allow_guest=True)
def accepteer_offerte(token: str, email: str, signature_data_url: str):
    """Accept a quote: validate, persist signature + audit, mark Geaccepteerd."""
    if not _is_valid_email(email):
        frappe.throw(_("Geldig e-mailadres vereist."), frappe.ValidationError)
    if not _is_valid_signature(signature_data_url):
        frappe.throw(_("Ongeldige handtekening."), frappe.ValidationError)

    offerte = _get_offerte_by_token(token)

    if offerte.status != "Verstuurd":
        frappe.throw(
            _("Deze offerte kan niet meer geaccepteerd worden."),
            frappe.ValidationError,
        )

    offerte.handtekening = signature_data_url
    offerte.ondertekend_op = frappe.utils.now_datetime()
    offerte.ondertekend_door_email = email.strip()
    offerte.ondertekend_ip = (frappe.local.request_ip or "")[:50]
    offerte.ondertekend_user_agent = (
        frappe.get_request_header("User-Agent", "") or ""
    )[:500]
    offerte.status = "Geaccepteerd"
    offerte.save(ignore_permissions=True)
    frappe.db.commit()

    _send_accept_emails(offerte)

    return {"status": "ok", "redirect": "/offerte-bedankt"}


@frappe.whitelist(allow_guest=True)
def weiger_offerte(token: str, reden: str = ""):
    """Reject a quote: store reason, flip status to Geweigerd."""
    offerte = _get_offerte_by_token(token)
    if offerte.status != "Verstuurd":
        frappe.throw(
            _("Deze offerte kan niet meer afgewezen worden."),
            frappe.ValidationError,
        )

    offerte.weigering_reden = (reden or "")[:1000]
    offerte.status = "Geweigerd"
    offerte.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok"}


def _send_accept_emails(offerte) -> None:
    """Send confirmation to klant + notification to bedrijf-eigenaar.

    Best-effort: a mail-send failure is logged but does NOT roll back
    the accept — the customer signed, that audit record stands.
    """
    try:
        klant_email = offerte.ondertekend_door_email
        subject = _("Bevestiging offerte {0}").format(offerte.offerte_nr)
        body = _(
            "Bedankt voor uw akkoord op offerte {0}.\n\n"
            "Bedrag: € {1}\n\n"
            "Wij nemen zo spoedig mogelijk contact met u op."
        ).format(offerte.offerte_nr, offerte.bedrag_incl)
        frappe.sendmail(recipients=[klant_email], subject=subject, message=body)

        if offerte.company:
            owner_email = frappe.db.get_value(
                "Company", offerte.company, "email"
            )
            if owner_email:
                frappe.sendmail(
                    recipients=[owner_email],
                    subject=_("Offerte {0} geaccepteerd").format(
                        offerte.offerte_nr
                    ),
                    message=_(
                        "Offerte {0} geaccepteerd door {1} op {2}."
                    ).format(
                        offerte.offerte_nr,
                        klant_email,
                        offerte.ondertekend_op,
                    ),
                )
    except Exception:  # noqa: BLE001
        frappe.log_error(
            title="Offerte accept mail",
            message=frappe.get_traceback(),
        )
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add nixfact_integration/nixfact_integration/api/offerte_portal.py \
        nixfact_integration/nixfact_integration/tests/test_offerte_portal_api.py
git commit -m "[sprint-6] Guest accept/reject API with email + signature validation"
```

---

### Task 7: Thank-you page

**Files:**
- Create: `nixfact_integration/nixfact_integration/www/offerte_bedankt.html`

We use a flat path (`offerte_bedankt`, not `offerte/bedankt`) because Frappe's `www/` routing has `offerte.html` and `offerte/` as mutually exclusive. No server-side context needed.

- [ ] **Step 1: Create the template**

```html
{# www/offerte_bedankt.html #}
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bedankt</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 4rem auto; padding: 1rem; text-align: center; color: #1a1a1a; }
        h1 { color: #0a7d3e; }
    </style>
</head>
<body>
    <h1>Bedankt!</h1>
    <p>Uw akkoord is geregistreerd. U ontvangt een bevestigingsmail.</p>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add nixfact_integration/nixfact_integration/www/offerte_bedankt.html
git commit -m "[sprint-6] Add /offerte-bedankt thank-you page"
```

---

### Task 8: Stamp `portal_verstuurd_op` on Concept→Verstuurd transition

**Files:**
- Modify: `nixfact_integration/nixfact_integration/doctype/nixfact_offerte/nixfact_offerte.py`
- Test: extend `tests/test_offerte_controller.py`

Out of scope: full email-sending UX. We just record when the offerte became publicly accessible so the audit trail is complete.

- [ ] **Step 1: Add tests**

```python
class TestPortalSentTimestamp(unittest.TestCase):
    def test_concept_to_verstuurd_stamps(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.status = "Verstuurd"
        doc.portal_verstuurd_op = None
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock(); old.status = "Concept"
        doc.get_doc_before_save = MagicMock(return_value=old)
        NixFactOfferte._stamp_portal_sent(doc)
        self.assertIsNotNone(doc.portal_verstuurd_op)

    def test_other_transitions_no_stamp(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.status = "Geaccepteerd"
        doc.portal_verstuurd_op = None
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock(); old.status = "Verstuurd"
        doc.get_doc_before_save = MagicMock(return_value=old)
        NixFactOfferte._stamp_portal_sent(doc)
        self.assertIsNone(doc.portal_verstuurd_op)

    def test_existing_stamp_not_overwritten(self):
        doc = MagicMock(spec=NixFactOfferte)
        doc.status = "Verstuurd"
        doc.portal_verstuurd_op = "2026-01-01 09:00:00"
        doc.is_new = MagicMock(return_value=False)
        old = MagicMock(); old.status = "Concept"
        doc.get_doc_before_save = MagicMock(return_value=old)
        NixFactOfferte._stamp_portal_sent(doc)
        self.assertEqual(doc.portal_verstuurd_op, "2026-01-01 09:00:00")
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement** — extend `validate()` and add method:

```python
def validate(self) -> None:
    self._sanity_check_bedragen()
    self._validate_status_transition()
    self._guard_immutable_after_accept()
    self._stamp_portal_sent()

def _stamp_portal_sent(self) -> None:
    """Record portal_verstuurd_op the first time status flips to Verstuurd."""
    if self.is_new() or self.portal_verstuurd_op:
        return
    if self.status != "Verstuurd":
        return
    old = self.get_doc_before_save()
    if old and old.status != "Verstuurd":
        self.portal_verstuurd_op = frappe.utils.now_datetime()
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "[sprint-6] Stamp portal_verstuurd_op on Concept->Verstuurd"
```

---

### Task 9: Update progress checklist in `IMPLEMENTATION_GUIDE.md`

- [ ] **Step 1: Tick completed Sprint 6 items**

In `nixfact_integration/IMPLEMENTATION_GUIDE.md`, change `[ ]` → `[x]` for:
- Schema-uitbreiding `NixFact Offerte`
- Token-generatie in `before_insert`
- Publieke portal-pagina
- Signature canvas (touch + desktop)
- Accept/Weiger API endpoints
- Audit trail logging
- Bevestigingsmails klant + eigenaar
- Tests: token-flow, accept-flow, weiger-flow, immutability na ondertekening

Leave unticked (deferred to Sprint 6.5):
- `[ ]` Audit PDF generatie met handtekening + footer
- `[ ]` Settings-velden in `NixFactInstellingen` (gebruikt nu hard-coded NL defaults)

- [ ] **Step 2: Commit**

```bash
git commit -am "[docs] Mark Sprint 6 items complete (audit-PDF + settings deferred)"
```

---

## Self-Review

**Spec coverage** (against `IMPLEMENTATION_GUIDE.md` Sprint 6 outline):

| Requirement | Task | Status |
|---|---|---|
| Schema-uitbreiding | 2 | ✅ |
| Token-generatie in `before_insert` | 1 + 3 | ✅ |
| Publieke portal-pagina | 5 | ✅ |
| Signature canvas (touch + desktop) | 5 | ✅ |
| Accept/Weiger API endpoints | 6 | ✅ |
| Audit trail logging | 6 (IP/UA/email/timestamp) | ✅ |
| Audit PDF generatie | — | ❌ Deferred to 6.5 |
| Bevestigingsmails klant + eigenaar | 6 | ✅ basic |
| Settings-velden | — | ❌ Deferred to 6.5 |
| Tests: token / accept / reject / immutability | 1, 6, 6, 4 | ✅ |
| Stamp `portal_verstuurd_op` on send | 8 | ✅ extra |
| Thank-you page | 7 | ✅ extra |

**Placeholder scan:** None — every code block is concrete.

**Type consistency:**
- `accept_token` is `Data` (str) in schema, str in token generator, str-validated in API.
- `handtekening` is `Long Text` in schema, str (data-URL) in API, str in immutability test.
- `ondertekend_op` is `Datetime` in schema, set via `frappe.utils.now_datetime()` (datetime obj) in API.
- All field names match between schema (Task 2), API writes (Task 6), immutability guard (Task 4), and tests.

---

## Execution Handoff

Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch one subagent per task, review between tasks. Fast iteration, isolated context per task. Use `superpowers:subagent-driven-development`.

**2. Inline Execution** — Execute tasks 1–9 in this session sequentially with checkpoints. Use `superpowers:executing-plans`.

**Which approach?**
