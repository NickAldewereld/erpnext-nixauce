// Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
// License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)

frappe.listview_settings["NixFact Factuur"] = {
	add_fields: ["vervaldatum"],
	get_indicator(doc) {
		const openstaand = [
			"Verstuurd",
			"Herinnering verstuurd",
			"Aanmaning verstuurd",
		];
		if (
			openstaand.includes(doc.status) &&
			doc.vervaldatum &&
			doc.vervaldatum < frappe.datetime.get_today()
		) {
			return [
				__("Overdue"),
				"red",
				"vervaldatum,<," + frappe.datetime.get_today(),
			];
		}
		const kleuren = {
			Concept: "grey",
			Verstuurd: "blue",
			"Herinnering verstuurd": "orange",
			"Aanmaning verstuurd": "orange",
			Betaald: "green",
			Oninbaar: "red",
		};
		const kleur = kleuren[doc.status] || "grey";
		return [__(doc.status), kleur, "status,=," + doc.status];
	},
};
