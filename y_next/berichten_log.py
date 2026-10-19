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
  ingelogde gebruiker; de afzender is niet te vervalsen.

Voor elke andere melding blijft de regel van Frappe gelden.
"""

import frappe
from frappe.desk.doctype.notification_log.notification_log import NotificationLog

BERICHT_LINK = "/y-next#/messenger"


def is_bericht(doc) -> bool:
	link = doc.get("link") or ""
	return (
		doc.get("type") == "Alert"
		and doc.get("document_type") == "User"
		and (link == BERICHT_LINK or link.startswith(BERICHT_LINK + "?"))
	)


class YNextNotificationLog(NotificationLog):
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
