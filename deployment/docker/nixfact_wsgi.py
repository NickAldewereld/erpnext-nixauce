"""Gunicorn WSGI entrypoint that also serves Frappe's static files.

The bare ``frappe.app:application`` omits the ``/assets`` and ``/files`` static
middleware — in a standard Frappe production deploy nginx serves those. This
stack runs gunicorn without an nginx sidecar (the public reverse proxy lives on
a separate host and can't reach the container filesystem), so we wrap the app
with the same middleware ``frappe.app.serve()`` would add.

``application_with_statics()`` reads ``frappe.app._sites_path`` (populated from
$SITES_PATH at import), so /assets resolves to ``$SITES_PATH/assets``.
"""

import frappe.app

application = frappe.app.application_with_statics()
