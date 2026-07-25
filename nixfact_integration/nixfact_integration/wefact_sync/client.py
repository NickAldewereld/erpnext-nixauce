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
        min_interval: float = 1.2,
    ) -> None:
        if not api_key:
            raise ValueError("WeFact API-key ontbreekt.")
        self.api_key = api_key
        self.endpoint = endpoint
        self._transport = transport or _default_transport
        # Minimale tijd tussen calls; WeFact firewallt het IP bij een burst.
        self._min_interval = min_interval
        self._last = 0.0

    def _pace(self) -> None:
        if not self._min_interval:
            return
        wacht = self._min_interval - (time.monotonic() - self._last)
        if wacht > 0:
            time.sleep(wacht)
        self._last = time.monotonic()

    def request(self, controller: str, action: str, params: dict | None = None) -> dict:
        body = {
            "api_key": self.api_key,
            "controller": controller,
            "action": action,
        }
        if params:
            body.update(params)

        self._pace()

        laatste = ""
        for poging in range(_MAX_RETRIES):
            resp = self._transport(self.endpoint, json=body, timeout=60)
            code = getattr(resp, "status_code", 200)
            if code == 429 or code >= 500:
                laatste = f"http {code}"
                time.sleep(2**poging)  # exponentiële backoff
                continue
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                # Leeg/niet-JSON antwoord (throttling onder burst) — transient,
                # dus backoff en opnieuw i.p.v. de factuur laten mislukken.
                laatste = "niet-JSON antwoord"
                time.sleep(2**poging)
                continue
            if data.get("status") != "success":
                raise WeFactError(
                    f"{controller}/{action}: {data.get('errors') or data}"
                )
            return data
        raise WeFactError(
            f"{controller}/{action}: geen geldig antwoord na {_MAX_RETRIES} "
            f"pogingen ({laatste})"
        )

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
            if not items:
                break
            alles.extend(items)
            # WeFact geeft alle resultaten in één call terug (offset skipt van
            # boven), niet 100/pagina. Stop zodra we totalresults binnen hebben;
            # val terug op de PAGE_SIZE-heuristiek als totalresults ontbreekt.
            total = int(data.get("totalresults") or 0)
            if total and len(alles) >= total:
                break
            if not total and len(items) < PAGE_SIZE:
                break
            offset += len(items)
        return alles

    def show(self, controller: str, identifier: str, id_field: str) -> dict:
        data = self.request(controller, "show", {id_field: identifier})
        return data.get(controller, data)
