import frappe
from frappe.model.document import Document


class OperationalNotice(Document):
	def on_trash(self):
		frappe.throw("A notice cannot be deleted")
