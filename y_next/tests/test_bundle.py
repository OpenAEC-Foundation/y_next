from frappe.tests import UnitTestCase

from y_next.bundle import parse_manifest


class TestParseManifest(UnitTestCase):
	def test_vindt_startbestand_en_stylesheets(self):
		manifest = {
			"index.html": {"file": "yapp-index-abc.js", "isEntry": True, "css": ["yapp-index-def.css"]},
			"src/x.ts": {"file": "yapp-x-123.js"},
		}
		self.assertEqual(
			parse_manifest(manifest),
			{"js": "yapp-index-abc.js", "css": ["yapp-index-def.css"]},
		)

	def test_startbestand_zonder_stylesheets(self):
		self.assertEqual(
			parse_manifest({"index.html": {"file": "a.js", "isEntry": True}}),
			{"js": "a.js", "css": []},
		)

	def test_geen_startbestand(self):
		self.assertIsNone(parse_manifest({"src/x.ts": {"file": "yapp-x-123.js"}}))
		self.assertIsNone(parse_manifest({}))


class TestConceptKoppelingInDeBundel(UnitTestCase):
	"""De mail-pagina leest de koppeling van een concept uit de eigen velden (zie y_next.rechten)."""

	def test_webmail_leest_de_koppeling_van_een_concept_uit_de_eigen_velden(self):
		import json
		import os

		import frappe

		map = frappe.get_app_path("y_next", "public", "app")
		with open(os.path.join(map, ".vite", "manifest.json"), encoding="utf-8") as bestand:
			manifest = json.load(bestand)
		webmail = manifest["src/pages/Webmail.tsx"]["file"]
		with open(os.path.join(map, webmail), encoding="utf-8") as bestand:
			code = bestand.read()
		verwacht = (
			# De concepten worden opgevraagd mét de eigen velden ...
			"`reference_name`,`custom_y_koppeling_doctype`,`custom_y_koppeling_naam`]",
			# ... en die gaan voor op de gewone verwijzing.
			"e.custom_y_koppeling_doctype||e.reference_doctype",
			"e.custom_y_koppeling_naam||e.reference_name",
		)
		for stuk in verwacht:
			self.assertTrue(stuk in code, f"ontbreekt in {webmail}: {stuk}")
		# Het startbestand verwijst naar dezelfde chunk.
		with open(os.path.join(map, manifest["index.html"]["file"]), encoding="utf-8") as bestand:
			self.assertTrue(webmail in bestand.read(), f"{webmail} ontbreekt in het startbestand")
