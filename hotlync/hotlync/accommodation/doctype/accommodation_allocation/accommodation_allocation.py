import frappe
from frappe.model.document import Document

from hotlync.accommodation.workflow import (
	apply_bed_status,
	assert_bed_assignable,
	assert_employee_assignable,
	location_for_bed,
)

PRIVILEGED_ROLES = {"System Manager", "Accommodation Admin", "Accommodation Manager"}


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
	if roles & PRIVILEGED_ROLES:
		return ""
	if "Staff" not in roles:
		return ""
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return "1=0"
	return "`tabAccommodation Allocation`.employee = " + frappe.db.escape(employee)


def has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles & PRIVILEGED_ROLES:
		return True
	if "Staff" not in roles:
		return False
	if permission_type and permission_type != "read":
		return False
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	return bool(employee and doc.employee == employee)
