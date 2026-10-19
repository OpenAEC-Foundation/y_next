"""Rechten die Y-next op standaarddoctypes van Frappe zet of bewaakt."""

import frappe
from frappe.tests import IntegrationTestCase

from y_next.tests.hulp import maak_gebruiker, maak_mail, maak_medewerker, maak_postbus

ANNA = "anna@voorbeeld.test"
BRAM = "bram@voorbeeld.test"
PIETER = "pieter.projecten@voorbeeld.test"
PORTAAL = "portaal@voorbeeld.test"
PETRA = "petra.projecten@voorbeeld.test"
BEHEER = "beheer@voorbeeld.test"
BEHEER2 = "beheer2@voorbeeld.test"

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


class TestConceptenAlleenVoorMaker(RechtenTestCase):
	"""Een concept of geplande mail op de server is persoonlijk, ook in een gedeelde postbus."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		maak_gebruiker(PETRA, "Petra", rollen=("Projects User",))
		maak_gebruiker(BEHEER, "Beheer", rollen=("System Manager",))
		maak_gebruiker(BEHEER2, "Beheer2", rollen=("System Manager",))
		cls.postbus = maak_postbus("Y Gedeelde testbus", "gedeeld@voorbeeld.test", PIETER)
		maak_postbus("Y Gedeelde testbus", "gedeeld@voorbeeld.test", PETRA)

	def concept(self, maker: str, map: str = "Y-NEXT-CONCEPT") -> str:
		naam = maak_mail(
			self.postbus,
			communication_type="Automated Message",
			sent_or_received="Sent",
			imap_folder=map,
		)
		# db_insert zet de sessiegebruiker als eigenaar; de maker komt erna.
		frappe.db.set_value("Communication", naam, "owner", maker, update_modified=False)
		self.addCleanup(frappe.db.delete, "Communication", {"name": naam})
		return naam

	def zichtbaar(self, gebruiker: str, naam: str) -> bool:
		frappe.set_user(gebruiker)
		return bool(frappe.get_list("Communication", filters={"name": naam}, pluck="name"))

	def test_concept_alleen_in_de_lijst_van_de_maker(self):
		for map in ("Y-NEXT-CONCEPT", "Y-NEXT-GEPLAND"):
			for maker, ander in ((PIETER, PETRA), (BEHEER, BEHEER2), (PIETER, "Administrator")):
				with self.subTest(map=map, maker=maker, ander=ander):
					naam = self.concept(maker, map)
					self.assertTrue(self.zichtbaar(maker, naam))
					self.assertFalse(self.zichtbaar(ander, naam))

	def test_concept_niet_te_openen_door_een_ander(self):
		naam = self.concept(PIETER)
		for ander in (PETRA, BEHEER):
			with self.subTest(ander=ander):
				for ptype in ("read", "write", "delete"):
					self.assertFalse(frappe.has_permission("Communication", ptype, doc=naam, user=ander))
		self.assertTrue(frappe.has_permission("Communication", "read", doc=naam, user=PIETER))

	def test_gewone_mail_in_de_gedeelde_postbus_blijft_voor_iedereen(self):
		naam = maak_mail(self.postbus)
		self.addCleanup(frappe.db.delete, "Communication", {"name": naam})
		for gebruiker in (PIETER, PETRA, BEHEER):
			with self.subTest(gebruiker=gebruiker):
				self.assertTrue(self.zichtbaar(gebruiker, naam))
				self.assertTrue(frappe.has_permission("Communication", "read", doc=naam, user=gebruiker))

	def test_een_nieuw_concept_aanmaken_mag(self):
		frappe.set_user(BEHEER)
		concept = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Automated Message",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"imap_folder": "Y-NEXT-CONCEPT",
				"subject": "Concept",
				"content": "Tekst",
				"recipients": "iemand@voorbeeld.test",
			}
		).insert()
		self.addCleanup(frappe.db.delete, "Communication", {"name": concept.name})
		self.assertEqual(concept.owner, BEHEER)
