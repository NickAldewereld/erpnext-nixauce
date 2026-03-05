app_name = "nixfact_integration"
app_title = "NixFact"
app_publisher = "Nick Aldewereld"
app_description = "WeFact-inspired invoicing system for ERPNext"
app_email = "nick@nixpay.nl"
app_license = "MIT"

# App includes (uncomment when assets exist)
# app_include_css = "/assets/nixfact_integration/css/nixfact.css"
# app_include_js = "/assets/nixfact_integration/js/nixfact.js"

# DocType events
# doc_events = {}

# Scheduled tasks
scheduler_events = {
	"daily": [
		"nixfact_integration.tasks.verstuur_herinneringen",
		"nixfact_integration.tasks.verstuur_aanmaningen",
	],
	"cron": {
		"0 9 * * *": [
			"nixfact_integration.tasks.genereer_abonnement_facturen",
		],
	},
}
