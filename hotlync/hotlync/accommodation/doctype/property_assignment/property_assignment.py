import frappe
from frappe.model.document import Document


class PropertyAssignment(Document):
	def validate(self):
		existing = frappe.db.exists(
			"Property Assignment",
			{
				"user": self.user,
				"property": self.property,
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw("That user is already assigned to this property")
