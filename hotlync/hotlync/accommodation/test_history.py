import json

import frappe
from frappe.tests import IntegrationTestCase

from hotlync.accommodation.doctype.accommodation_request.accommodation_request import (
	has_permission as request_permission,
)
from hotlync.api import (
	allocate_bed,
	assign_ticket,
	check_in,
	decide_request,
	issue_key,
	register_key,
	revoke_user_property,
	save_request,
	save_ticket,
	submit_request,
)


class TestHistory(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_history")
		self.home, self.bed = _residence("HSTA", "History Residence")
		self.room = frappe.db.get_value("Bed", self.bed, "room")
		self.staff = _user("history-staff@hotlync.local", "Staff")
		self.employee = _employee(self.staff)
		self.manager = _user("history-manager@hotlync.local", "Accommodation Manager")
		_assign(self.manager, self.home)

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_history")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_a_request_decision_is_versioned(self):
		frappe.set_user(self.staff)
		draft = save_request(
			request_type="Room Change",
			property=self.home,
			employee=self.employee,
			reason="Quieter room",
		)
		submitted = submit_request(draft["name"])
		self.assertEqual(submitted["status"], "Submitted")
		frappe.set_user(self.manager)
		approved = decide_request(draft["name"], "Approved", comment="Room is free")
		self.assertEqual(approved["status"], "Approved")
		version = _version(
			"Accommodation Request",
			draft["name"],
			self.manager,
			"status",
			"Approved",
		)
		self.assertIn(self.manager, json.dumps(version))
		self.assertNotIn("password", json.dumps(version).lower())
		self.assertNotIn("csrf", json.dumps(version).lower())

	def test_a_ticket_assignment_is_versioned(self):
		frappe.set_user(self.staff)
		ticket = save_ticket(
			category="Leak",
			urgency="Normal",
			property=self.home,
			bed=self.bed,
			description="Water under the sink",
		)
		frappe.set_user(self.manager)
		assigned = assign_ticket(ticket["name"], contractor_name="History Contractor")
		self.assertEqual(assigned["status"], "Assigned")
		version = _version(
			"Maintenance Ticket",
			ticket["name"],
			self.manager,
			"status",
			"Assigned",
		)
		text = json.dumps(version)
		self.assertIn(self.manager, text)
		self.assertIn("History Contractor", text)
		self.assertNotIn("password", text.lower())

	def test_a_key_issue_is_versioned(self):
		frappe.set_user(self.manager)
		key = register_key(label="H-1", kind="Key", property=self.home, room=self.room)
		issued = issue_key(key["name"], employee=self.employee)
		self.assertEqual(issued["status"], "Issued")
		version = _version(
			"Accommodation Key",
			key["name"],
			self.manager,
			"status",
			"Issued",
		)
		text = json.dumps(version)
		self.assertIn(self.manager, text)
		self.assertIn("Issued", text)
		self.assertNotIn("password", text.lower())

	def test_a_failed_key_issue_leaves_the_key_and_its_versions(self):
		frappe.set_user(self.manager)
		key = register_key(label="H-2", kind="Key", property=self.home, room=self.room)
		before_status = frappe.db.get_value("Accommodation Key", key["name"], "status")
		before_moves = frappe.db.count("Key Movement", {"parent": key["name"]})
		before_versions = _version_count("Accommodation Key", key["name"])
		inactive = _employee()
		frappe.db.set_value("Employee", inactive, "status", "Inactive")
		with self.assertRaises(frappe.ValidationError) as caught:
			issue_key(key["name"], employee=inactive, expected_return="2020-01-01")
		self.assertEqual(str(caught.exception), "Employee is not active")
		self.assertEqual(
			frappe.db.get_value("Accommodation Key", key["name"], "status"),
			before_status,
		)
		self.assertEqual(frappe.db.count("Key Movement", {"parent": key["name"]}), before_moves)
		self.assertEqual(_version_count("Accommodation Key", key["name"]), before_versions)
		stored = frappe.get_all(
			"Key Movement",
			filters={"parent": key["name"]},
			pluck="action",
			order_by="idx asc",
		)
		self.assertEqual(stored, ["Registered"])

	def test_an_existing_decision_cannot_be_rewritten(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		doc = frappe.get_doc("Accommodation Request", name)
		doc.decisions[0].comment = "rewritten"
		with self.assertRaises(frappe.ValidationError) as caught:
			doc.save(ignore_permissions=True)
		self.assertEqual(str(caught.exception), "A request decision cannot be changed")
		decision_name = doc.decisions[0].name
		self.assertFalse(frappe.db.get_value("Accommodation Request Decision", decision_name, "comment"))
		doc = frappe.get_doc("Accommodation Request", name)
		doc.remove(doc.decisions[0])
		with self.assertRaises(frappe.ValidationError) as removed:
			doc.save(ignore_permissions=True)
		self.assertEqual(str(removed.exception), "A request decision cannot be changed")
		self.assertTrue(frappe.db.exists("Accommodation Request Decision", decision_name))
		approved = decide_request(name, "Approved", comment="Room is free")
		self.assertEqual(approved["status"], "Approved")
		self.assertEqual(approved["decisions"][-1]["comment"], "Room is free")

	def test_an_existing_update_cannot_be_rewritten(self):
		frappe.set_user(self.staff)
		ticket = save_ticket(
			category="Leak",
			urgency="Normal",
			property=self.home,
			bed=self.bed,
			description="Water under the sink",
		)
		frappe.set_user(self.manager)
		doc = frappe.get_doc("Maintenance Ticket", ticket["name"])
		doc.updates[0].comment = "rewritten"
		with self.assertRaises(frappe.ValidationError) as caught:
			doc.save(ignore_permissions=True)
		self.assertEqual(str(caught.exception), "A maintenance update cannot be changed")
		update_name = doc.updates[0].name
		doc = frappe.get_doc("Maintenance Ticket", ticket["name"])
		doc.remove(doc.updates[0])
		with self.assertRaises(frappe.ValidationError) as removed:
			doc.save(ignore_permissions=True)
		self.assertEqual(str(removed.exception), "A maintenance update cannot be changed")
		self.assertTrue(frappe.db.exists("Maintenance Update", update_name))
		assigned = assign_ticket(ticket["name"], contractor_name="History Contractor")
		self.assertEqual(assigned["status"], "Assigned")
		self.assertEqual(assigned["updates"][-1]["action"], "Assigned")

	def test_a_rejected_assignment_leaves_the_ticket_and_its_versions(self):
		frappe.set_user(self.staff)
		ticket = save_ticket(
			category="Leak",
			urgency="Normal",
			property=self.home,
			bed=self.bed,
			description="Water under the sink",
		)
		before = _version_count("Maintenance Ticket", ticket["name"])
		with self.assertRaises(frappe.PermissionError):
			assign_ticket(ticket["name"], contractor_name="Nope")
		self.assertEqual(
			frappe.db.get_value("Maintenance Ticket", ticket["name"], "status"),
			"Submitted",
		)
		self.assertEqual(_version_count("Maintenance Ticket", ticket["name"]), before)

	def test_a_rejected_decision_leaves_the_request_and_its_versions(self):
		name = self._submitted()
		before = _version_count("Accommodation Request", name)
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.PermissionError):
			decide_request(name, "Approved")
		self.assertEqual(frappe.db.get_value("Accommodation Request", name, "status"), "Submitted")
		self.assertEqual(_version_count("Accommodation Request", name), before)

	def test_revoking_a_residence_keeps_the_stay(self):
		admin = _user("history-admin@hotlync.local", "Accommodation Admin")
		outsider = _user("history-outsider@hotlync.local", "Accommodation Manager")
		frappe.set_user("Administrator")
		stay = check_in(allocate_bed(self.employee, self.bed)["name"], frappe.utils.today())
		before = frappe.db.get_value(
			"Accommodation Allocation",
			stay["name"],
			["status", "bed", "employee", "property", "check_in_date"],
			as_dict=True,
		)
		assignment = frappe.db.get_value(
			"Property Assignment",
			{"user": self.manager, "property": self.home},
			"name",
		)
		frappe.set_user(admin)
		revoke_user_property(assignment)
		after = frappe.db.get_value(
			"Accommodation Allocation",
			stay["name"],
			["status", "bed", "employee", "property", "check_in_date"],
			as_dict=True,
		)
		self.assertEqual(after, before)
		deleted = frappe.get_all(
			"Deleted Document",
			filters={"deleted_doctype": "Property Assignment", "deleted_name": assignment},
			fields=["name", "data", "owner"],
		)
		self.assertEqual(len(deleted), 1)
		self.assertEqual(deleted[0].owner, admin)
		self.assertIn(self.home, deleted[0].data)
		self.assertNotIn("password", deleted[0].data.lower())
		for user in (self.staff, self.manager, admin, outsider):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("Deleted Document", deleted[0].name, check_permission=True)
		request = frappe.get_doc("Accommodation Request", self._submitted())
		self.assertFalse(request_permission(request, ptype="read", user=outsider))

	def test_ordinary_users_cannot_read_or_delete_versions(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		decide_request(name, "Approved")
		version_name = frappe.db.get_value(
			"Version",
			{"ref_doctype": "Accommodation Request", "docname": name},
			"name",
		)
		self.assertTrue(version_name)
		self.assertFalse(frappe.has_permission("Version", ptype="read", user=self.staff))
		self.assertFalse(frappe.has_permission("Version", ptype="write", user=self.manager))
		self.assertFalse(frappe.has_permission("Version", ptype="delete", user=self.manager))
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("Version", version_name)
		self.assertTrue(frappe.db.exists("Version", version_name))

	def _submitted(self):
		frappe.set_user(self.staff)
		draft = save_request(
			request_type="Room Change",
			property=self.home,
			employee=self.employee,
			reason="Quieter room",
		)
		return submit_request(draft["name"])["name"]


def _version_count(doctype, name):
	return frappe.db.count("Version", {"ref_doctype": doctype, "docname": name})


def _version(doctype, name, user, field, new):
	for row in frappe.get_all(
		"Version",
		filters={"ref_doctype": doctype, "docname": name},
		fields=["owner", "creation", "data"],
	):
		if row.owner != user or not row.creation:
			continue
		data = json.loads(row.data)
		for change in data.get("changed") or []:
			if change[0] == field and str(change[2] or "") == str(new):
				return data
	frappe.throw("Version for " + name + " did not record " + field)


def _assign(user, property_name):
	frappe.set_user("Administrator")
	frappe.get_doc(
		{
			"doctype": "Property Assignment",
			"user": user,
			"property": property_name,
		}
	).insert(ignore_permissions=True)


def _user(email, role):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "History",
			"send_welcome_email": 0,
			"user_type": "System User",
			"enabled": 1,
		}
	)
	user.append("roles", {"role": role})
	user.insert(ignore_permissions=True)
	return user.name


def _employee(user_id=None):
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "History",
			"last_name": "Check",
			"gender": "Male",
			"date_of_birth": "1995-01-01",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
			"user_id": user_id,
		}
	).insert(ignore_permissions=True)
	return employee.name


def _residence(code, property_name):
	property_doc = frappe.get_doc(
		{
			"doctype": "Property",
			"code": code,
			"property_name": property_name,
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	building = frappe.get_doc(
		{
			"doctype": "Building",
			"code": code + "-B",
			"building_name": property_name + " building",
			"property": property_doc.name,
			"number_of_floors": 1,
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	floor = frappe.get_doc(
		{
			"doctype": "Floor",
			"building": building.name,
			"floor_number": 1,
			"floor_name": "Floor 1",
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	room = frappe.get_doc(
		{
			"doctype": "Room",
			"floor": floor.name,
			"building": building.name,
			"room_number": "1",
			"room_type": "Single",
			"capacity": 1,
			"status": "Available",
		}
	).insert(ignore_permissions=True)
	bed = frappe.get_doc(
		{
			"doctype": "Bed",
			"room": room.name,
			"bed_number": "A",
			"status": "Available",
		}
	).insert(ignore_permissions=True)
	return property_doc.name, bed.name
