# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

app_name = "nixfact_integration"
app_title = "NixFact"
app_publisher = "Nick Aldewereld"
app_description = "WeFact-inspired invoicing system for ERPNext"
app_email = "nick@nixpay.nl"
app_license = "AGPL-3.0-or-later"

# App includes (uncomment when assets exist)
# app_include_css = "/assets/nixfact_integration/css/nixfact.css"
# app_include_js = "/assets/nixfact_integration/js/nixfact.js"

# DocType events
doc_events = {
	"NixFact Factuur": {
		"before_save": (
			"nixfact_integration.utils.ubl_generator.valideer_factuur_doc"
		),
	},
}

# Scheduled tasks
scheduler_events = {
	"hourly": [
		"nixfact_integration.wefact_sync.engine.incrementele_sync",
	],
	"daily": [
		"nixfact_integration.tasks.verstuur_herinneringen",
		"nixfact_integration.tasks.verstuur_aanmaningen",
		"nixfact_integration.wefact_sync.engine.dagelijkse_debiteuren_sync",
	],
	"cron": {
		"0 9 * * *": [
			"nixfact_integration.tasks.genereer_abonnement_facturen",
		],
	},
}
