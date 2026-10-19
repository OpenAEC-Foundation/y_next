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
