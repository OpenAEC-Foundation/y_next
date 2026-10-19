# Copyright (c) 2026, OpenAEC Foundation and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Het enige veld dat in het archief nog mag veranderen.
WIJZIGBAAR = {"gelezen"}
VELDEN = ("afzender", "ontvanger", "bericht", "afbeelding", "gelezen")


class YBericht(Document):
	"""Een bericht uit het oude berichtenarchief.

	Berichten draaien op Notification Log; dit doctype bewaart de berichten van
	daarvoor zodat Y-next ze kan blijven tonen. Er komt niets bij en de inhoud
	verandert niet: de ontvanger kan alleen het gelezen-vinkje zetten. Wie het
	mag lezen, staat in `y_next.rechten`.
	"""

	def validate(self):
		if self.is_new() or frappe.session.user == "Administrator":
			return
		vorige = self.get_doc_before_save()
		if not vorige:
			return
		gewijzigd = {veld for veld in VELDEN if self.get(veld) != vorige.get(veld)}
		if gewijzigd - WIJZIGBAAR:
			frappe.throw(_("Een bericht uit het archief kan niet meer worden gewijzigd."))
