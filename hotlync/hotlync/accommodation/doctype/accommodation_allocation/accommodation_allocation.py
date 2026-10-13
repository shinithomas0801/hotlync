import frappe
from frappe.model.document import Document

from hotlync.accommodation.access import GROUP_ROLES, allocation_clause, property_scope
from hotlync.accommodation.workflow import (
	apply_bed_status,
	assert_bed_assignable,
	assert_employee_assignable,
	location_for_bed,
)


class AccommodationAllocation(Document):
	def before_insert(self):
		self._fill_location()

	def validate(self):
		self._fill_location()
		self._set_occupancy_keys()
		if self.status in ("Draft", "Checked In"):
			assert_employee_assignable(self.employee, ignore_allocation=self.name)
			assert_bed_assignable(self.bed, ignore_allocation=self.name)

	def _set_occupancy_keys(self):
		if self.status in ("Draft", "Checked In"):
			self.active_bed = self.bed
			self.active_employee = self.employee
			return
		self.active_bed = None
		self.active_employee = None

	def on_update(self):
		apply_bed_status(self)

	def _fill_location(self):
		if not self.bed:
			return
		location = location_for_bed(self.bed)
		self.property = location["property"]
		self.building = location["building"]
		self.room = location["room"]


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles & GROUP_ROLES:
		return ""
	clauses = []
	if "Accommodation Manager" in roles:
		clauses.append(allocation_clause(user))
	if "Staff" in roles:
		clauses.append(_staff_clause(user))
	if not clauses:
		return ""
	if len(clauses) == 1:
		return clauses[0]
	return "(" + " or ".join(f"({clause})" for clause in clauses) + ")"


def has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles & GROUP_ROLES:
		return True
	if "Accommodation Manager" in roles:
		scope = property_scope(user)
		if scope is None or (doc.property and doc.property in scope):
			return True
	if "Staff" in roles and (not permission_type or permission_type == "read"):
		employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
		return bool(employee and doc.employee == employee)
	return False


def _staff_clause(user):
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return "1=0"
	return "`tabAccommodation Allocation`.employee = " + frappe.db.escape(employee)
