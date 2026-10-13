import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import (
	cancel_request,
	decide_request,
	get_requests,
	save_request,
	submit_request,
)


class TestRequests(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_requests")
		self.home, self.bed = _residence("FRMA", "Form Residence")
		self.other, self.other_bed = _residence("FRMB", "Other Form Residence")
		self.staff = _user("form-staff@hotlync.local", "Staff")
		self.employee = _employee(self.staff)
		self.manager = _user("form-manager@hotlync.local", "Accommodation Manager")
		self.outsider = _user("form-outsider@hotlync.local", "Accommodation Manager")
		_assign(self.manager, self.home)
		_assign(self.outsider, self.other)

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_requests")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_staff_submits_a_room_change_for_themselves(self):
		other = _employee()
		frappe.set_user(self.staff)
		row = save_request(
			request_type="Room Change",
			property=self.home,
			employee=other,
			reason="Need a quieter room",
			requested_bed=self.bed,
		)
		self.assertEqual(row["status"], "Draft")
		self.assertEqual(row["employee"], self.employee)
		self.assertNotEqual(row["employee"], other)
		self.assertEqual(row["requester"], self.staff)
		self.assertEqual(row["decisions"], [])
		submitted = submit_request(row["name"])
		self.assertEqual(submitted["status"], "Submitted")
		self.assertEqual(submitted["submission_date"], frappe.utils.today())
		self.assertEqual(submitted["decisions"][0]["action"], "Submitted")
		self.assertEqual(submitted["decisions"][0]["actor"], self.staff)

	def test_requester_cannot_approve(self):
		frappe.set_user(self.manager)
		row = save_request(
			request_type="Room Change",
			property=self.home,
			employee=self.employee,
			reason="Manager filed this",
		)
		submit_request(row["name"])
		with self.assertRaises(frappe.ValidationError) as caught:
			decide_request(row["name"], "Approved")
		self.assertIn("You cannot approve your own request", str(caught.exception))

	def test_other_property_is_not_permitted(self):
		name = self._submitted()
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError) as caught:
			decide_request(name, "Approved", comment="No")
		self.assertIn("Not permitted", str(caught.exception))
		visible = [row["name"] for row in get_requests()["requests"]]
		self.assertNotIn(name, visible)
		with self.assertRaises(frappe.ValidationError) as missing:
			get_requests(name=name)
		self.assertIn("Request not found", str(missing.exception))

	def test_approval_does_not_create_an_allocation(self):
		name = self._submitted()
		before = frappe.db.count("Accommodation Allocation")
		bed_status = frappe.db.get_value("Bed", self.bed, "status")
		frappe.set_user("Administrator")
		decided = decide_request(name, "Approved", comment="Noted")
		self.assertEqual(decided["status"], "Approved")
		self.assertEqual(decided["decisions"][-1]["action"], "Approved")
		self.assertEqual(decided["decisions"][-1]["actor"], "Administrator")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", self.bed, "status"), bed_status)
		self.assertFalse(
			frappe.db.exists(
				"Accommodation Allocation",
				{"employee": self.employee, "bed": self.bed},
			)
		)

	def test_reject_requires_a_comment(self):
		name = self._submitted()
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError) as caught:
			decide_request(name, "Rejected")
		self.assertIn("A comment is required", str(caught.exception))
		self.assertEqual(
			frappe.db.get_value("Accommodation Request", name, "status"),
			"Submitted",
		)

	def test_request_changes_then_resubmit(self):
		name = self._submitted()
		frappe.set_user("Administrator")
		changed = decide_request(name, "Changes Requested", comment="Add a date")
		self.assertEqual(changed["status"], "Changes Requested")
		frappe.set_user(self.staff)
		again = submit_request(name)
		self.assertEqual(again["status"], "Submitted")
		self.assertEqual(
			[row["action"] for row in again["decisions"]],
			["Submitted", "Changes Requested", "Submitted"],
		)

	def test_duplicate_open_request_is_rejected(self):
		frappe.set_user(self.staff)
		save_request(
			request_type="Visitor Stay",
			property=self.home,
			visitor_name="Pat Guest",
			visit_start="2026-10-20",
			visit_end="2026-10-22",
		)
		with self.assertRaises(frappe.ValidationError) as caught:
			save_request(
				request_type="Visitor Stay",
				property=self.home,
				visitor_name="Pat Guest",
				visit_start="2026-11-01",
				visit_end="2026-11-02",
			)
		self.assertIn(
			"This employee already has an open request of that type.",
			str(caught.exception),
		)

	def test_missing_type_fields_are_rejected(self):
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.ValidationError) as caught:
			save_request(
				request_type="Visitor Stay",
				property=self.home,
				visitor_name="Pat Guest",
			)
		self.assertIn("Visit start is required", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as dates:
			save_request(
				request_type="Family Accommodation",
				property=self.home,
				family_member_name="Ada",
				relationship="Sister",
				stay_start="2026-10-20",
				stay_end="2026-10-01",
			)
		self.assertIn("Stay end cannot be before stay start", str(dates.exception))

	def test_a_terminal_request_cannot_be_decided_again(self):
		name = self._submitted()
		frappe.set_user("Administrator")
		decide_request(name, "Approved")
		with self.assertRaises(frappe.ValidationError) as caught:
			decide_request(name, "Rejected", comment="Too late")
		self.assertIn("That status change is not allowed", str(caught.exception))

	def test_requested_bed_must_be_in_the_residence(self):
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.ValidationError) as caught:
			save_request(
				request_type="Room Change",
				property=self.home,
				reason="Across town",
				requested_bed=self.other_bed,
			)
		self.assertIn("Bed is not in the selected residence", str(caught.exception))

	def test_exit_clearance_allows_an_inactive_employee(self):
		employee = _employee()
		frappe.db.set_value("Employee", employee, "status", "Inactive")
		frappe.set_user(self.manager)
		row = save_request(
			request_type="Exit Clearance",
			property=self.home,
			employee=employee,
			intended_checkout_date="2026-10-20",
			reason="Leaving the residence",
		)
		self.assertEqual(row["status"], "Draft")
		self.assertEqual(row["employee"], employee)

	def test_staff_can_cancel_and_file_again(self):
		name = self._submitted()
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError):
			cancel_request(name)
		frappe.set_user(self.staff)
		cancelled = cancel_request(name, comment="No longer needed")
		self.assertEqual(cancelled["status"], "Cancelled")
		self.assertEqual(cancelled["decisions"][-1]["action"], "Cancelled")
		replacement = save_request(
			request_type="Room Change",
			property=self.home,
			reason="A later room",
		)
		self.assertEqual(replacement["status"], "Draft")

	def test_guest_cannot_read_requests(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.AuthenticationError, get_requests)

	def _submitted(self):
		frappe.set_user(self.staff)
		row = save_request(
			request_type="Room Change",
			property=self.home,
			reason="Need a quieter room",
			requested_bed=self.bed,
		)
		return submit_request(row["name"])["name"]


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
			"first_name": "Form",
			"last_name": "Check",
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	).insert(ignore_permissions=True)
	user.add_roles(role)
	return user.name


def _employee(user_id=None):
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Form",
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
