"""Berichten in Y-next zijn `Notification Log`-documenten; hier staat wat de afzender ermee mag.

Elk bericht bestaat uit twee kopieën: één voor de ontvanger (`for_user` is de
ontvanger) en één voor de afzender zelf. Frappe 16 laat alleen de gebruiker voor
wie een melding bedoeld is (`for_user`) het document aanmaken, lezen of wijzigen
(`notification_log.has_permission`). Daardoor kan een medewerker de kopie voor de
ontvanger niet aanmaken: versturen faalt met een rechtenfout, ook met de
rolrechten uit `setup/permissions.json`.

Deze controller maakt daar een smalle uitzondering op, alleen voor berichten:

- aanmaken mag wie het rolrecht `create` op Notification Log heeft, en alleen als
  het document een bericht is (soort `Alert`, tegenpartij een `User`, link naar
  Berichten in Y-next);
- wijzigen mag de afzender (de `owner`) bij zijn eigen bericht, zodat hij na het
  uploaden van een foto de link op de kopie van de ontvanger kan zetten;
- `from_user` (wat de bel in de desk als afzender toont) wordt altijd de
  ingelogde gebruiker; de afzender is niet te vervalsen;
- na het versturen kan de afzender aan de kopie van de ontvanger alleen de
  `link` nog wijzigen, en alleen naar een berichtlink van hetzelfde gesprek: de
  parameters blijven gelijk, behalve de bijlagen (`img`, `sz`), die naar een
  bestand op deze site moeten wijzen.

Voor elke andere melding blijft de regel van Frappe gelden.
"""

from urllib.parse import parse_qsl

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import NotificationLog

BERICHT_LINK = "/y-next#/messenger"

# Parameters in de link die na het versturen nog mogen veranderen: de bijlagen.
BIJLAGE_PARAMETERS = {"img", "sz"}
BESTANDSPADEN = ("/private/files/", "/files/")
# Wat Frappe zelf bij elke keer opslaan zet.
SYSTEEMVELDEN = {"modified", "modified_by"}


def is_bericht(doc) -> bool:
	link = doc.get("link") or ""
	return (
		doc.get("type") == "Alert"
		and doc.get("document_type") == "User"
		and (link == BERICHT_LINK or link.startswith(BERICHT_LINK + "?"))
	)


def _parameters(link: str) -> list[tuple[str, str]]:
	_, _, zoekdeel = (link or "").partition("?")
	return parse_qsl(zoekdeel, keep_blank_values=True)


def is_link_van_hetzelfde_gesprek(oud: str, nieuw: str) -> bool:
	"""Een nieuwe link is een berichtlink met dezelfde parameters als de oude, op de bijlagen na."""
	if not (nieuw == BERICHT_LINK or nieuw.startswith(BERICHT_LINK + "?")):
		return False
	nieuwe_parameters = _parameters(nieuw)
	vast = lambda parameters: sorted(p for p in parameters if p[0] not in BIJLAGE_PARAMETERS)  # noqa: E731
	if vast(nieuwe_parameters) != vast(_parameters(oud)):
		return False
	for naam, waarde in nieuwe_parameters:
		if naam == "img" and not (waarde.startswith(BESTANDSPADEN) and ".." not in waarde):
			return False
		if naam == "sz" and not waarde.isdigit():
			return False
	return True


class YNextNotificationLog(NotificationLog):
	def validate(self):
		if hasattr(super(), "validate"):
			super().validate()
		self.bewaak_kopie_van_de_ontvanger()

	def bewaak_kopie_van_de_ontvanger(self):
		"""De afzender wijzigt aan de kopie van een ander alleen nog de link (zie de module-uitleg)."""
		if self.is_new() or self.flags.ignore_permissions:
			return
		gebruiker = frappe.session.user
		vorige = self.get_doc_before_save()
		if gebruiker == "Administrator" or not vorige or vorige.for_user == gebruiker:
			return
		velden = set(self.meta.get_valid_columns()) | {"owner", "creation", "docstatus"}
		gewijzigd = {
			veld for veld in velden - SYSTEEMVELDEN if (self.get(veld) or None) != (vorige.get(veld) or None)
		}
		if gewijzigd - {"link"}:
			frappe.throw(_("Een verstuurd bericht kan niet meer worden gewijzigd."), frappe.PermissionError)
		if "link" in gewijzigd and not is_link_van_hetzelfde_gesprek(vorige.link, self.link):
			frappe.throw(_("Ongeldige link voor dit bericht."), frappe.PermissionError)

	def before_insert(self):
		if is_bericht(self) and not self.flags.ignore_permissions:
			self.from_user = frappe.session.user
		if hasattr(super(), "before_insert"):
			super().before_insert()

	def has_permission(self, permtype="read", *, debug=False, user=None) -> bool:
		if not self.flags.ignore_permissions and is_bericht(self):
			gebruiker = user or frappe.session.user
			if permtype == "create" and self.is_new():
				return frappe.has_permission(self.doctype, "create", user=gebruiker, debug=debug)
			if permtype == "write" and not self.is_new() and self.owner == gebruiker:
				# Wat er in de database staat telt, niet wat het verzoek meestuurt.
				opgeslagen = frappe.db.get_value(
					self.doctype, self.name, ["owner", "type", "document_type", "link"], as_dict=True
				)
				if opgeslagen and opgeslagen.owner == gebruiker and is_bericht(opgeslagen):
					return frappe.has_permission(self.doctype, "write", user=gebruiker, debug=debug)
		return super().has_permission(permtype, debug=debug, user=user)
