// Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
// License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)

frappe.ui.form.on("NixFact Factuur", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		// Betaallink aanmaken via Mollie (alleen voor openstaande facturen
		// zonder bestaande betaallink).
		const betaalstatussen = [
			"Verstuurd",
			"Herinnering verstuurd",
			"Aanmaning verstuurd",
		];
		if (
			betaalstatussen.includes(frm.doc.status) &&
			!frm.doc.mollie_payment_url &&
			!frm.doc.betaallink
		) {
			frm.add_custom_button(
				__("Create Payment Link"),
				() => {
					frappe.call({
						method: "nixfact_integration.api.mollie.create_payment_link",
						args: { factuur_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Creating payment link..."),
						callback(r) {
							if (r.message && r.message.payment_url) {
								frm.reload_doc();
								frappe.msgprint({
									title: __("Payment link created"),
									indicator: "green",
									message: `<a href="${r.message.payment_url}" target="_blank">${r.message.payment_url}</a>`,
								});
							}
						},
					});
				},
				__("Actions")
			);
		}

		// UBL XML genereren en als bijlage opslaan.
		frm.add_custom_button(
			__("Generate UBL"),
			() => {
				frappe.call({
					method: "nixfact_integration.api.ubl.attach_ubl_to_factuur",
					args: { factuur_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Generating UBL..."),
					callback(r) {
						if (r.message && r.message.file_url) {
							frm.reload_doc();
							frappe.show_alert({
								message: __("UBL generated and attached"),
								indicator: "green",
							});
						}
					},
				});
			},
			__("Actions")
		);
	},
});
