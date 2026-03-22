import frappe
from frappe import _
from frappe.model.document import Document


class BuzzEventForm(Document):
	def validate(self):
		self.validate_unique_route()

	def validate_unique_route(self):
		for row in self.parentdoc.custom_forms:
			if row.name != self.name and row.route == self.route:
				frappe.throw(
					_("Duplicate route '{0}' in custom forms. Each form must have a unique route.").format(
						self.route
					)
				)
