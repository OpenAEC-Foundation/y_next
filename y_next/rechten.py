"""Rechten die Y-next bovenop die van Frappe legt.

Frappe voegt de condities van `permission_query_conditions` en de uitkomsten van
`has_permission` samen met die van Frappe zelf: wat hier staat kan alleen
beperken, nooit iets extra toestaan.
"""

import frappe

# Mail die Y-next als concept of als geplande mail op de server bewaart: een
# Communication met een van deze markeringen in `imap_folder`.
CONCEPT_MAPPEN = ("Y-NEXT-CONCEPT", "Y-NEXT-GEPLAND")


def _is_concept(doc) -> bool:
	return (doc.get("imap_folder") or "") in CONCEPT_MAPPEN


def concepten_query(user: str | None = None, doctype: str | None = None) -> str:
	"""Concepten en geplande mails staan alleen in de lijst van wie ze maakte.

	Ook een System Manager en Administrator zien die van een ander niet: een
	concept is persoonlijk, ook in een gedeelde postbus, en wie er een opent
	verstuurt het onder zijn eigen naam en handtekening.
	"""
	gebruiker = user or frappe.session.user
	mappen = ", ".join(frappe.db.escape(map) for map in CONCEPT_MAPPEN)
	return (
		f"(ifnull(`tabCommunication`.`imap_folder`, '') not in ({mappen})"
		f" or `tabCommunication`.`owner` = {frappe.db.escape(gebruiker)})"
	)


def concepten_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	"""Een concept of geplande mail van een ander is niet te openen, wijzigen of verwijderen."""
	if not _is_concept(doc) or doc.is_new():
		return True
	return doc.owner == (user or frappe.session.user)


# Waar een concept zijn koppeling bewaart (custom fields uit setup/custom_fields.json).
KOPPELING_DOCTYPE = "custom_y_koppeling_doctype"
KOPPELING_NAAM = "custom_y_koppeling_naam"


def concept_buiten_tijdlijn(doc, method=None):
	"""Een concept of geplande mail komt in geen enkele tijdlijn.

	Frappe toont in de tijdlijn van een document (`frappe.desk.form.load`,
	`get_communications` en de docinfo van `getdoc`) elke Communication van het
	soort Automated Message die naar dat document verwijst, met inhoud en zonder
	rechtencontrole op de Communication zelf. Een mail verwijst op twee manieren:
	via `reference_doctype`/`reference_name`, en via de tijdlijnregels
	(`timeline_links`) die Frappe bij elke keer opslaan zelf aanmaakt voor de
	contactpersonen van de geadresseerden en hun klant of leverancier. Een concept
	zou zo bij iedereen die het project, het contact of de klant mag lezen
	zichtbaar zijn, ook de wijzigingsmelding via realtime.

	Daarom heeft een concept geen verwijzing en geen tijdlijnregels. De koppeling
	die de maker koos blijft bewaard in eigen velden. Wordt het concept een
	gewone mail (de markering in `imap_folder` gaat eraf), dan gaat de koppeling
	terug naar `reference_doctype`/`reference_name`.

	Draait als `doc_events` validate, dus na de validate van Communication zelf
	(die de tijdlijnregels en soms een verwijzing zet).
	"""
	if _is_concept(doc):
		if doc.reference_doctype and doc.reference_name:
			doc.set(KOPPELING_DOCTYPE, doc.reference_doctype)
			doc.set(KOPPELING_NAAM, doc.reference_name)
		doc.reference_doctype = None
		doc.reference_name = None
		doc.reference_owner = None
		doc.set("timeline_links", [])
		return
	if doc.get(KOPPELING_DOCTYPE) and doc.get(KOPPELING_NAAM):
		if not (doc.reference_doctype and doc.reference_name):
			doc.reference_doctype = doc.get(KOPPELING_DOCTYPE)
			doc.reference_name = doc.get(KOPPELING_NAAM)
			doc.reference_owner = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "owner")
		doc.set(KOPPELING_DOCTYPE, None)
		doc.set(KOPPELING_NAAM, None)


def concepten_uit_de_tijdlijn():
	"""Voor concepten van vóór deze regel: koppeling naar de eigen velden, tijdlijnregels weg."""
	concepten = frappe.get_all(
		"Communication", filters={"imap_folder": ["in", list(CONCEPT_MAPPEN)]}, pluck="name", limit_page_length=0
	)
	if not concepten:
		return
	for rij in frappe.get_all(
		"Communication",
		filters={"name": ["in", concepten], "reference_name": ["is", "set"]},
		fields=["name", "reference_doctype", "reference_name"],
		limit_page_length=0,
	):
		frappe.db.set_value(
			"Communication",
			rij.name,
			{
				KOPPELING_DOCTYPE: rij.reference_doctype,
				KOPPELING_NAAM: rij.reference_name,
				"reference_doctype": None,
				"reference_name": None,
				"reference_owner": None,
			},
			update_modified=False,
		)
	frappe.db.delete("Communication Link", {"parenttype": "Communication", "parent": ["in", concepten]})


# Wat iemand met een bericht uit het archief (`Y Bericht`) mag.
ALLEEN_LEZEN = {"read", "print", "email", "export", "report", "share"}


def y_bericht_query(user: str | None = None, doctype: str | None = None) -> str | None:
	"""Een bericht uit het archief staat alleen in de lijst van afzender en ontvanger."""
	gebruiker = user or frappe.session.user
	if gebruiker == "Administrator":
		return None
	ik = frappe.db.escape(gebruiker)
	return f"(`tabY Bericht`.`afzender` = {ik} or `tabY Bericht`.`ontvanger` = {ik})"


def y_bericht_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	"""Lezen: afzender en ontvanger. Wijzigen (het gelezen-vinkje): alleen de ontvanger."""
	gebruiker = user or frappe.session.user
	if doc.is_new():
		return True
	if ptype in ALLEEN_LEZEN:
		return gebruiker in (doc.afzender, doc.ontvanger)
	if ptype == "write":
		return gebruiker == doc.ontvanger
	return True
