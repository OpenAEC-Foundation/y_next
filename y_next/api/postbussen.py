"""Welke postbussen zijn aan de ingelogde gebruiker toegewezen?"""

import frappe

from y_next.api import is_beheerder


def eigen_postbussen(gebruiker: str) -> list[dict]:
	"""De rijen uit `User.user_emails` van deze gebruiker: naam van het Email Account en adres."""
	postbussen = []
	for rij in frappe.get_all(
		"User Email",
		filters={"parent": gebruiker, "parenttype": "User"},
		fields=["email_account", "email_id"],
		limit_page_length=0,
	):
		naam = (rij.get("email_account") or "").strip()
		adres = (rij.get("email_id") or "").strip()
		if naam and adres:
			postbussen.append({"name": naam, "email_id": adres})
	return postbussen


@frappe.whitelist()
def mijn_postbussen():
	"""De postbussen van de ingelogde gebruiker.

	Waarom dit geen gewone leesactie op het eigen User-document is: het veld
	`user_emails` staat op permissieniveau 1, en dat niveau mag alleen een
	System Manager lezen. Een gewone medewerker krijgt zijn eigen gebruiker
	dus wél terug, maar zonder die tabel en zonder foutmelding. De mailmodule
	ziet dan geen enkele postbus, ook niet zijn eigen.

	Het leesrecht op dat niveau openzetten zou meteen ook `roles`, `user_type`
	en `block_modules` leesbaar maken. Wat hier weggegeven wordt is smal:
	alleen de eigen rijen, alleen naam en adres. Wie de post in die bussen mag
	lezen bepaalt ERPNext zelf.
	"""
	gebruiker = frappe.session.user
	return {
		"gebruiker": gebruiker,
		"postbussen": eigen_postbussen(gebruiker),
		# Een System Manager valt buiten de beperking op Communication en leest
		# elke postbus. De app gebruikt dat om hem de gedeelde bussen te tonen.
		"alles": is_beheerder(gebruiker),
	}


def postbusrechten_bijwerken(doc, method=None):
	"""Houdt bij een gebruiker de User Permissions op Communication gelijk aan zijn postbussen.

	Frappe beperkt de mail*lijst* van een gebruiker met postbussen tot die
	postbussen, maar een losse mail uit een andere postbus is op naam gewoon te
	openen. Een User Permission per toegewezen Email Account (alleen voor
	Communication) sluit dat gat: dan geldt de beperking ook per document.

	Draait na elke keer opslaan van een User (`doc_events` in hooks.py) en bij
	elke migratie voor iedereen met postbussen. Een System Manager leest elke
	postbus en krijgt geen beperking. Alleen rechten met `allow` Email Account en
	`applicable_for` Communication worden hier beheerd; andere User Permissions
	blijven ongemoeid.
	"""
	gebruiker = doc.name
	gewenst = set()
	if not is_beheerder(gebruiker):
		gewenst = {rij["name"] for rij in eigen_postbussen(gebruiker)}

	bestaand = {}
	for rij in frappe.get_all(
		"User Permission",
		filters={"user": gebruiker, "allow": "Email Account", "applicable_for": "Communication"},
		fields=["name", "for_value"],
		limit_page_length=0,
	):
		if rij.for_value in bestaand or rij.for_value not in gewenst:
			frappe.delete_doc("User Permission", rij.name, ignore_permissions=True)
		else:
			bestaand[rij.for_value] = rij.name

	for postbus in sorted(gewenst - set(bestaand)):
		if not frappe.db.exists("Email Account", postbus):
			continue
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": gebruiker,
				"allow": "Email Account",
				"for_value": postbus,
				"applicable_for": "Communication",
				"apply_to_all_doctypes": 0,
			}
		).insert(ignore_permissions=True)


def alle_postbusrechten_bijwerken():
	"""Voor iedereen met een postbus, of met een recht dat er nog van over is."""
	gebruikers = set(
		frappe.get_all("User Email", filters={"parenttype": "User"}, pluck="parent", limit_page_length=0)
	) | set(
		frappe.get_all(
			"User Permission",
			filters={"allow": "Email Account", "applicable_for": "Communication"},
			pluck="user",
			limit_page_length=0,
		)
	)
	for gebruiker in sorted(gebruikers):
		if frappe.db.exists("User", gebruiker):
			postbusrechten_bijwerken(frappe._dict(name=gebruiker))
