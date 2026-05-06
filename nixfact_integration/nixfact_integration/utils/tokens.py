# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

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
