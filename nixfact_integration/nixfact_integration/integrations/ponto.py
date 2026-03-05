# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import frappe
import requests
from frappe.utils import get_datetime


class PontoIntegration:
	"""Integration with the Ponto (Isabel Group) banking API."""

	BASE_URL = "https://api.myponto.com"
	TOKEN_URL = "https://api.myponto.com/oauth2/token"

	def __init__(self, bank_koppeling):
		"""
		Initialize with a NixFact Bank Koppeling document.

		Args:
		    bank_koppeling: name (str) or Document of NixFact Bank Koppeling
		"""
		if isinstance(bank_koppeling, str):
			bank_koppeling = frappe.get_doc("NixFact Bank Koppeling", bank_koppeling)

		self.koppeling = bank_koppeling
		self.client_id = bank_koppeling.ponto_client_id
		self.client_secret = bank_koppeling.get_password("ponto_client_secret")
		self.refresh_token = bank_koppeling.get_password("ponto_refresh_token")
		self.account_id = bank_koppeling.account_id
		self.access_token = None

	def authenticate(self):
		"""Obtain access token using client credentials + refresh token."""
		response = requests.post(
			self.TOKEN_URL,
			data={
				"grant_type": "refresh_token",
				"client_id": self.client_id,
				"refresh_token": self.refresh_token,
			},
			auth=(self.client_id, self.client_secret),
			headers={"Content-Type": "application/x-www-form-urlencoded"},
			timeout=30,
		)

		if response.status_code != 200:
			frappe.log_error(
				title="Ponto authenticatie mislukt",
				message=f"Status {response.status_code}: {response.text}",
			)
			frappe.throw(f"Ponto authenticatie mislukt: {response.status_code}")

		data = response.json()
		self.access_token = data["access_token"]

		# Store new refresh token if provided
		if "refresh_token" in data:
			frappe.db.set_value(
				"NixFact Bank Koppeling",
				self.koppeling.name,
				"ponto_refresh_token",
				data["refresh_token"],
			)

		return self.access_token

	def get_transactions(self, after=None, limit=100):
		"""
		Fetch transactions from Ponto API.

		Args:
		    after: Cursor for pagination (transaction ID to start after)
		    limit: Max transactions to fetch (default 100)

		Returns:
		    list[dict]: Raw transaction data from Ponto
		"""
		if not self.access_token:
			self.authenticate()

		url = f"{self.BASE_URL}/accounts/{self.account_id}/transactions"
		params = {"limit": min(limit, 100)}
		if after:
			params["after"] = after

		response = requests.get(
			url,
			params=params,
			headers={
				"Authorization": f"Bearer {self.access_token}",
				"Accept": "application/json",
			},
			timeout=30,
		)

		if response.status_code != 200:
			frappe.log_error(
				title="Ponto transacties ophalen mislukt",
				message=f"Status {response.status_code}: {response.text}",
			)
			frappe.throw(f"Ponto API fout: {response.status_code}")

		data = response.json()
		return data.get("data", [])

	def parse_transactions(self, raw_transactions):
		"""
		Parse raw Ponto API responses into standardized dicts.

		Args:
		    raw_transactions: list of dicts from get_transactions()

		Returns:
		    list[dict]: Parsed transactions ready for NixFact Bank Transactie
		"""
		parsed = []
		for txn in raw_transactions:
			attrs = txn.get("attributes", {})
			counterparty = attrs.get("counterpartName", "")
			parsed.append({
				"transactie_id": txn.get("id", ""),
				"datum": attrs.get("executionDate") or attrs.get("valueDate", ""),
				"bedrag": float(attrs.get("amount", 0)),
				"van_naar": attrs.get("counterpartReference", ""),
				"naam": counterparty,
				"omschrijving": attrs.get("description", "")
					or attrs.get("remittanceInformation", ""),
				"referentie": attrs.get("remittanceInformationStructured", "")
					or attrs.get("remittanceInformation", ""),
			})
		return parsed

	def sync(self):
		"""
		Full sync: authenticate, fetch transactions, import new ones.

		Returns:
		    dict: {imported: int, skipped: int}
		"""
		self.authenticate()

		raw = self.get_transactions()
		parsed = self.parse_transactions(raw)

		imported = 0
		skipped = 0

		for txn in parsed:
			# Skip if already imported
			if frappe.db.exists("NixFact Bank Transactie", {"transactie_id": txn["transactie_id"]}):
				skipped += 1
				continue

			doc = frappe.get_doc({
				"doctype": "NixFact Bank Transactie",
				"transactie_id": txn["transactie_id"],
				"bank_koppeling": self.koppeling.name,
				"datum": txn["datum"],
				"bedrag": txn["bedrag"],
				"van_naar": txn["van_naar"],
				"naam": txn["naam"],
				"omschrijving": txn["omschrijving"],
				"referentie": txn["referentie"],
				"status": "Onverwerkt",
			})
			doc.insert(ignore_permissions=True)
			imported += 1

		# Update last sync timestamp
		frappe.db.set_value(
			"NixFact Bank Koppeling",
			self.koppeling.name,
			"laatste_sync",
			get_datetime(),
		)
		frappe.db.commit()

		return {"imported": imported, "skipped": skipped}
