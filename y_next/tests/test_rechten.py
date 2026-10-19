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
KEES = "kees.postbus@voorbeeld.test"

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

	def wijzig_als_afzender(self, naam: str, **velden):
		frappe.set_user(ANNA)
		bericht = frappe.get_doc("Notification Log", naam)
		bericht.update(velden)
		bericht.save()

	def test_afzender_kan_na_versturen_niets_anders_dan_de_link_wijzigen(self):
		naam = self.stuur(ANNA, BRAM)
		frappe.set_user("Administrator")
		voor = frappe.db.get_value("Notification Log", naam, ["from_user", "for_user", "owner", "type"], as_dict=True)
		pogingen = {
			"from_user": {"from_user": PIETER},
			"for_user": {"for_user": PIETER},
			"owner": {"owner": PIETER},
			"type": {"type": "Mention"},
			"document_name": {"document_name": PIETER},
			"subject": {"subject": "Iets anders", "email_content": "Iets anders"},
		}
		for wat, velden in pogingen.items():
			with self.subTest(wat=wat):
				self.assertRaises(
					(frappe.PermissionError, frappe.ValidationError), self.wijzig_als_afzender, naam, **velden
				)
				frappe.set_user("Administrator")
				self.assertEqual(
					frappe.db.get_value(
						"Notification Log", naam, ["from_user", "for_user", "owner", "type"], as_dict=True
					),
					voor,
				)

	def test_link_blijft_een_bericht_van_hetzelfde_gesprek(self):
		naam = self.stuur(ANNA, BRAM)
		ongeldig = {
			"extern": "https://voorbeeld.test/messenger",
			"andere route": "/app/todo",
			"externe afbeelding": BERICHT + "?img=https%3A%2F%2Fvoorbeeld.test%2Fx.png&k=abc123",
			"andere sleutel": BERICHT + "?img=%2Fprivate%2Ffiles%2Ffoto.png&k=anders",
			"sleutel weg": BERICHT + "?img=%2Fprivate%2Ffiles%2Ffoto.png",
			"extra parameter": BERICHT + "?img=%2Fprivate%2Ffiles%2Ffoto.png&k=abc123&g=groep1",
		}
		for wat, link in ongeldig.items():
			with self.subTest(wat=wat):
				self.assertRaises(
					(frappe.PermissionError, frappe.ValidationError), self.wijzig_als_afzender, naam, link=link
				)
		self.wijzig_als_afzender(naam, link=BERICHT + "?img=%2Fprivate%2Ffiles%2Ffoto.png&sz=1234&k=abc123")
		frappe.set_user("Administrator")
		self.assertIn("img=", frappe.db.get_value("Notification Log", naam, "link"))


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


def postbusrechten(gebruiker: str) -> set[str]:
	"""De postbussen waartoe een gebruiker via User Permissions op Communication beperkt is."""
	return set(
		frappe.get_all(
			"User Permission",
			filters={"user": gebruiker, "allow": "Email Account", "applicable_for": "Communication"},
			pluck="for_value",
		)
	)


class TestPostbusrechten(RechtenTestCase):
	"""Wie een postbus toegewezen kreeg, leest mail uit die postbus en niet uit een andere."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		maak_gebruiker(KEES, "Kees", rollen=("Projects User",))
		maak_gebruiker(BEHEER, "Beheer", rollen=("System Manager",))
		for naam, adres in (("Y Bus Een", "een@voorbeeld.test"), ("Y Bus Twee", "twee@voorbeeld.test")):
			if not frappe.db.exists("Email Account", naam):
				frappe.get_doc(
					{
						"doctype": "Email Account",
						"email_account_name": naam,
						"email_id": adres,
						"enable_incoming": 0,
						"enable_outgoing": 0,
					}
				).insert(ignore_permissions=True)

	def setUp(self):
		for gebruiker in (KEES, BEHEER):
			doc = frappe.get_doc("User", gebruiker)
			doc.set("user_emails", [])
			doc.save(ignore_permissions=True)
		frappe.db.delete("User Permission", {"user": ["in", [KEES, BEHEER]], "allow": "Email Account"})

	def wijs_toe(self, gebruiker: str, *postbussen: str):
		doc = frappe.get_doc("User", gebruiker)
		doc.set("user_emails", [])
		for postbus in postbussen:
			doc.append("user_emails", {"email_account": postbus})
		doc.save(ignore_permissions=True)

	def test_toegewezen_postbussen_worden_rechten(self):
		self.wijs_toe(KEES, "Y Bus Een")
		self.assertEqual(postbusrechten(KEES), {"Y Bus Een"})
		self.wijs_toe(KEES, "Y Bus Een", "Y Bus Twee")
		self.assertEqual(postbusrechten(KEES), {"Y Bus Een", "Y Bus Twee"})
		self.wijs_toe(KEES, "Y Bus Twee")
		self.assertEqual(postbusrechten(KEES), {"Y Bus Twee"})
		self.wijs_toe(KEES)
		self.assertEqual(postbusrechten(KEES), set())

	def test_opnieuw_opslaan_maakt_geen_dubbele_rechten(self):
		self.wijs_toe(KEES, "Y Bus Een")
		frappe.get_doc("User", KEES).save(ignore_permissions=True)
		self.assertEqual(frappe.db.count("User Permission", {"user": KEES, "allow": "Email Account"}), 1)

	def test_beheerder_leest_alle_postbussen_en_krijgt_geen_beperking(self):
		self.wijs_toe(BEHEER, "Y Bus Een")
		self.assertEqual(postbusrechten(BEHEER), set())

	def test_mail_uit_een_andere_postbus_is_niet_te_openen(self):
		self.wijs_toe(KEES, "Y Bus Een")
		eigen = maak_mail("Y Bus Een")
		vreemd = maak_mail("Y Bus Twee")
		self.addCleanup(frappe.db.delete, "Communication", {"name": ["in", [eigen, vreemd]]})
		self.assertTrue(frappe.has_permission("Communication", "read", doc=eigen, user=KEES))
		self.assertFalse(frappe.has_permission("Communication", "read", doc=vreemd, user=KEES))

	def test_migratie_zet_ontbrekende_rechten_neer(self):
		from y_next.setup import install

		self.wijs_toe(KEES, "Y Bus Een")
		frappe.db.delete("User Permission", {"user": KEES, "allow": "Email Account"})
		install.sync_all()
		self.assertEqual(postbusrechten(KEES), {"Y Bus Een"})


class TestBerichtenArchief(RechtenTestCase):
	"""`Y Bericht`: het archief van de berichten van vóór Notification Log, alleen-lezen."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		maak_gebruiker(BEHEER, "Beheer", rollen=("System Manager",))

	def setUp(self):
		frappe.set_user("Administrator")
		self.naam = frappe.get_doc(
			{"doctype": "Y Bericht", "afzender": ANNA, "ontvanger": BRAM, "bericht": "<p>Oud bericht</p>"}
		).insert().name
		self.addCleanup(frappe.db.delete, "Y Bericht", {"name": self.naam})

	def zichtbaar(self, gebruiker: str) -> bool:
		frappe.set_user(gebruiker)
		return bool(frappe.get_list("Y Bericht", filters={"name": self.naam}, pluck="name"))

	def test_hoort_bij_de_app(self):
		self.assertEqual(frappe.db.get_value("DocType", "Y Bericht", ["module", "custom"]), ("Y Next", 0))
		meta = frappe.get_meta("Y Bericht")
		for veld in ("afzender", "ontvanger", "bericht", "gelezen", "afbeelding"):
			self.assertTrue(meta.has_field(veld), veld)

	def test_alleen_afzender_en_ontvanger_lezen_het(self):
		self.assertTrue(self.zichtbaar(ANNA))
		self.assertTrue(self.zichtbaar(BRAM))
		for ander in (PIETER, BEHEER):
			with self.subTest(ander=ander):
				self.assertFalse(self.zichtbaar(ander))
				self.assertFalse(frappe.has_permission("Y Bericht", "read", doc=self.naam, user=ander))

	def test_ontvanger_zet_alleen_het_gelezen_vinkje(self):
		frappe.set_user(BRAM)
		bericht = frappe.get_doc("Y Bericht", self.naam)
		bericht.gelezen = 1
		bericht.save()
		self.assertEqual(frappe.db.get_value("Y Bericht", self.naam, "gelezen"), 1)

		bericht.bericht = "<p>Anders</p>"
		self.assertRaises(frappe.ValidationError, bericht.save)

		frappe.set_user(ANNA)
		self.assertFalse(frappe.has_permission("Y Bericht", "write", doc=self.naam, user=ANNA))

	def test_het_archief_groeit_niet(self):
		for gebruiker in (ANNA, PIETER):
			with self.subTest(gebruiker=gebruiker):
				frappe.set_user(gebruiker)
				self.assertRaises(
					frappe.PermissionError,
					frappe.get_doc({"doctype": "Y Bericht", "afzender": gebruiker, "ontvanger": BRAM, "bericht": "x"}).insert,
				)
				self.assertFalse(frappe.has_permission("Y Bericht", "delete", doc=self.naam, user=gebruiker))
