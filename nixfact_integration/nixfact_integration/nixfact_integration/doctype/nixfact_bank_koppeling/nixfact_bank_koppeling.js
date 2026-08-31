// Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
// License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)

frappe.ui.form.on("NixFact Bank Koppeling", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		if (frm.doc.actief && frm.doc.koppeling_type === "Ponto") {
			frm.add_custom_button(
				__("Synchronize Transactions"),
				() => {
					frappe.call({
						method: "nixfact_integration.api.bank.sync_ponto_transactions",
						args: { bank_koppeling_id: frm.doc.name },
						freeze: true,
						freeze_message: __("Synchronizing transactions..."),
						callback(r) {
							if (r.message) {
								frm.reload_doc();
								frappe.msgprint({
									title: __("Synchronization completed"),
									indicator: "green",
									message: __(
										"Imported: {0} | Skipped: {1} | Matched: {2} | Auto-settled: {3} | Unmatched: {4}",
										[
											r.message.imported,
											r.message.skipped,
											r.message.matched,
											r.message.auto_settled,
											r.message.unmatched,
										]
									),
								});
							}
						},
					});
				},
				__("Actions")
			);
		}
	},
});
