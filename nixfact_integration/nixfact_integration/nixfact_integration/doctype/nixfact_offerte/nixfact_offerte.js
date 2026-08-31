// Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
// License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)

frappe.ui.form.on("NixFact Offerte", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.accept_token) {
			return;
		}

		// Publieke acceptatie-URL (www/offerte.html?token=...) kopiëren.
		frm.add_custom_button(
			__("Copy Acceptance Link"),
			() => {
				const url =
					window.location.origin +
					"/offerte?token=" +
					encodeURIComponent(frm.doc.accept_token);
				frappe.utils.copy_to_clipboard(url);
				frappe.show_alert({
					message: __("Acceptance link copied to clipboard"),
					indicator: "green",
				});
			},
			__("Actions")
		);
	},
});
