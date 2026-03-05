# Contributing to NIXFact

## Development Setup

```bash
# Clone the repo
git clone git@github.com:NickAldewereld/erpnext-nixauce.git
cd erpnext-nixauce

# Set up Frappe bench (if not already)
bench init frappe-bench --frappe-branch version-15
cd frappe-bench

# Link the app
ln -s /path/to/erpnext-nixauce/nixfact_integration apps/nixfact_integration
bench --site your-site.local install-app nixfact_integration

# Run migrations after changes
bench --site your-site.local migrate
```

## Code Style

- **Python**: PEP 8, tabs for indentation (Frappe convention)
- **DocType JSON**: Use Frappe's built-in DocType editor when possible
- **Commits**: Conventional format: `[Sprint N] description` or `fix: description`

## Project Structure

- `doctype/` - Frappe DocTypes (JSON schema + Python class)
- `api/` - Whitelisted API endpoints
- `integrations/` - External service connectors (Ponto, Mollie)
- `utils/` - Shared utilities (numbering, matching, UBL)
- `templates/email/` - Jinja2 email templates
- `tasks.py` - Scheduled background jobs

## Pull Request Process

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Test locally with `bench --site your-site.local migrate`
5. Commit with a descriptive message
6. Push and open a PR against `main`

## Adding a New DocType

1. Create directory: `doctype/nixfact_your_doctype/`
2. Add `__init__.py` (empty), `nixfact_your_doctype.json`, `nixfact_your_doctype.py`
3. Set `"module": "NixFact Integration"` in JSON
4. If auto-numbered, add entry to `utils/numbering.py` DOCTYPE_NUMBERING

## Adding a New Integration

1. Create class in `integrations/your_service.py`
2. Add API endpoint in `api/your_service.py`
3. Add any settings fields to `NixFact Instellingen`

## Questions?

Open an issue or email nick@nixpay.nl.
