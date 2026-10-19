"""Rechten die Y-next op standaarddoctypes van Frappe zet of bewaakt."""

import frappe
from frappe.tests import IntegrationTestCase

from y_next.tests.hulp import maak_gebruiker, maak_medewerker

ANNA = "anna@voorbeeld.test"
BRAM = "bram@voorbeeld.test"
PIETER = "pieter.projecten@voorbeeld.test"
PORTAAL = "portaal@voorbeeld.test"

BERICHT = "/y-next#/messenger"


class RechtenTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		maak_medewerker(ANNA, "Anna")
		maak_medewerker(BRAM, "Bram")
		maak_gebruiker(PIETER, "Pieter", rollen=("Projects User",))
		maak_gebruiker(PORTAAL, "Portaal")

	def tearDown(self):
		frappe.set_user("Administrator")


class TestBerichtenVersturen(RechtenTestCase):
	"""Een bericht in Berichten is een Notification Log die de afzender zelf aanmaakt."""

	def stuur(self, afzender: str, ontvanger: str, **velden) -> str:
		frappe.set_user(afzender)
		bericht = frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": ontvanger,
				"type": "Alert",
				"subject": "Hoi",
				"email_content": "Hoi",
				"document_type": "User",
				"document_name": afzender,
				"link": BERICHT + "?k=abc123",
				"from_user": afzender,
				**velden,
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Notification Log", bericht.name, ignore_permissions=True, force=True)
		return bericht.name

	def test_medewerker_en_projectgebruiker_kunnen_een_bericht_sturen(self):
		for afzender in (ANNA, PIETER):
			with self.subTest(afzender=afzender):
				naam = self.stuur(afzender, BRAM)
				self.assertEqual(frappe.db.get_value("Notification Log", naam, "owner"), afzender)

	def test_zonder_medewerkersrol_geen_berichten(self):
		self.assertRaises(frappe.PermissionError, self.stuur, PORTAAL, BRAM)

	def test_afzender_in_de_bel_is_de_echte_afzender(self):
		naam = self.stuur(ANNA, BRAM, from_user=PIETER)
		self.assertEqual(frappe.db.get_value("Notification Log", naam, "from_user"), ANNA)

	def test_een_gewone_melding_voor_een_ander_blijft_verboden(self):
		self.assertRaises(frappe.PermissionError, self.stuur, ANNA, BRAM, link="/app/todo")
		self.assertRaises(frappe.PermissionError, self.stuur, ANNA, BRAM, document_type="ToDo")

	def test_afzender_mag_de_kopie_van_de_ontvanger_bijwerken(self):
		# Na het uploaden van een foto zet de afzender de link op de kopie van de ontvanger.
		from frappe.handler import check_write_permission

		naam = self.stuur(ANNA, BRAM)
		frappe.set_user(ANNA)
		# Dezelfde controle als bij het uploaden van een bijlage aan dat document.
		check_write_permission("Notification Log", naam)
		bericht = frappe.get_doc("Notification Log", naam)
		bericht.link = BERICHT + "?img=/private/files/foto.png&k=abc123"
		bericht.save()

		frappe.set_user(BRAM)
		bericht = frappe.get_doc("Notification Log", naam)
		bericht.read = 1
		bericht.save()

		frappe.set_user(PIETER)
		self.assertRaises(frappe.PermissionError, check_write_permission, "Notification Log", naam)
		self.assertFalse(frappe.has_permission("Notification Log", "write", doc=naam))
		self.assertFalse(frappe.has_permission("Notification Log", "read", doc=naam))
