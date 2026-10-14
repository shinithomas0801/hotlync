from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import (
	allocate_bed,
	assign_ticket,
	check_in,
	check_out,
	decide_request,
	get_notices,
	issue_key,
	register_key,
	save_request,
	save_ticket,
	submit_request,
	update_ticket,
)
from hotlync.accommodation.notify import notify_request, notify_ticket


class TestNotices(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_notices")
		self.home, self.bed = _residence("NTFH", "Notice Residence")
		self.other, _other_bed = _residence("NTFO", "Other Notice Residence")
		self.staff = _user("notice-staff@hotlync.local", "Staff")
		self.employee = _employee(self.staff)
		self.worker = _user("notice-worker@hotlync.local", "Staff")
		self.manager = _user("notice-manager@hotlync.local", "Accommodation Manager")
		self.outsider = _user("notice-outsider@hotlync.local", "Accommodation Manager")
		_assign(self.manager, self.home)
		_assign(self.outsider, self.other)

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_notices")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_submission_notifies_the_property_manager(self):
		stays = frappe.db.count("Accommodation Allocation")
		frappe.set_user(self.staff)
		draft = save_request(
			request_type="Room Change",
			property=self.home,
			employee=self.employee,
			reason="Visitor passport 123",
		)
		self.assertEqual(_subjects(draft["name"]), [])
		submitted = submit_request(draft["name"])
		self.assertEqual(submitted["status"], "Submitted")
		frappe.set_user(self.manager)
		subjects = _subjects(draft["name"])
		self.assertIn(f"{draft['name']} was submitted.", subjects)
		self.assertNotIn("Visitor passport 123", " ".join(subjects))
		self.assertNotIn("Notice Check", " ".join(subjects))
		self.assertNotIn(self.employee, " ".join(subjects))
		frappe.set_user(self.staff)
		self.assertEqual(_subjects(draft["name"]), [])
		frappe.set_user(self.outsider)
		self.assertEqual(_subjects(draft["name"]), [])
		self.assertEqual(frappe.db.count("Accommodation Allocation"), stays)

	def test_approval_notifies_the_requester_without_the_comment(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		approved = decide_request(name, "Approved", comment="Visitor passport 123")
		self.assertEqual(approved["status"], "Approved")
		frappe.set_user(self.staff)
		subjects = _subjects(name)
		self.assertIn(f"{name} was approved.", subjects)
		self.assertNotIn("Visitor passport 123", " ".join(subjects))
		before = len(subjects)
		doc = frappe.get_doc("Accommodation Request", name)
		notify_request(doc)
		self.assertEqual(len(_subjects(name)), before)

	def test_a_failed_notice_leaves_the_approval_in_place(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		with patch(
			"hotlync.accommodation.notify._insert_notice",
			side_effect=RuntimeError("mailbox unavailable"),
		):
			approved = decide_request(name, "Approved", comment="Visitor passport 123")
		self.assertEqual(approved["status"], "Approved")
		self.assertEqual(
			frappe.db.get_value("Accommodation Request", name, "status"),
			"Approved",
		)
		rows = get_notices()
		failed = [row for row in rows if row.reference_name == name and row.status == "Failed"]
		self.assertEqual(len(failed), 1)
		self.assertEqual(failed[0].subject, "A notice could not be delivered.")
		self.assertEqual(failed[0].channel, "In App")
		self.assertEqual(failed[0].reference_doctype, "Accommodation Request")
		self.assertIn("mailbox unavailable", failed[0].detail)
		self.assertNotIn("Visitor passport 123", failed[0].detail)
		self.assertEqual(
			frappe.db.get_value("Operational Notice", failed[0].name, "actor"),
			self.manager,
		)
		frappe.set_user(self.staff)
		self.assertNotIn(f"{name} was approved.", _subjects(name))

	def test_urgent_ticket_and_assignment_notify_without_the_description(self):
		frappe.set_user(self.staff)
		plain = save_ticket(
			category="Leak",
			urgency="Normal",
			property=self.home,
			description="Secret leak under the sink",
		)
		self.assertEqual(_subjects(plain["name"]), [])
		urgent = save_ticket(
			category="Leak",
			urgency="Urgent",
			property=self.home,
			description="Secret leak under the sink",
		)
		frappe.set_user(self.manager)
		subjects = _subjects(urgent["name"])
		self.assertIn(f"Urgent ticket {urgent['name']} was submitted.", subjects)
		self.assertNotIn("Secret leak under the sink", " ".join(subjects))
		doc = frappe.get_doc("Maintenance Ticket", urgent["name"])
		notify_ticket(doc)
		self.assertEqual(len(_subjects(urgent["name"])), len(subjects))
		frappe.set_user(self.outsider)
		self.assertEqual(_subjects(urgent["name"]), [])
		frappe.set_user(self.manager)
		assign_ticket(plain["name"], assignee=self.worker)
		frappe.set_user(self.staff)
		assigned = _subjects(plain["name"])
		self.assertIn(f"{plain['name']} was assigned.", assigned)
		frappe.set_user(self.worker)
		self.assertIn(f"{plain['name']} was assigned.", _subjects(plain["name"]))
		frappe.set_user(self.worker)
		update_ticket(plain["name"], "In Progress")
		count = len(_subjects(plain["name"], user=self.staff))
		frappe.set_user(self.worker)
		with self.assertRaises(frappe.ValidationError):
			update_ticket(plain["name"], "In Progress")
		self.assertEqual(len(_subjects(plain["name"], user=self.staff)), count)

	def test_email_is_not_sent_without_an_outgoing_account(self):
		name = self._submitted()
		if frappe.db.exists(
			"Email Account",
			{"enable_outgoing": 1, "default_outgoing": 1},
		):
			self.skipTest("an outgoing email account is configured")
		frappe.set_user(self.manager)
		decide_request(name, "Approved")
		self.assertFalse(
			frappe.db.exists(
				"Operational Notice",
				{"reference_name": name, "channel": "Email"},
			)
		)

	def test_scope_and_admin_follow_the_permission_model(self):
		admin = _user("notice-admin@hotlync.local", "Accommodation Admin")
		unassigned = _user("notice-open@hotlync.local", "Accommodation Manager")
		name = self._submitted()
		self.assertTrue(
			frappe.db.exists(
				"Operational Notice",
				{"reference_name": name, "recipient": admin, "status": "Delivered"},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				"Operational Notice",
				{"reference_name": name, "recipient": self.outsider},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				"Operational Notice",
				{"reference_name": name, "recipient": unassigned},
			)
		)
		notice = frappe.db.get_value(
			"Operational Notice",
			{"reference_name": name, "recipient": self.manager},
			"name",
		)
		frappe.set_user(self.staff)
		hidden = frappe.get_doc("Operational Notice", notice)
		self.assertRaises(frappe.PermissionError, hidden.check_permission, "read")
		frappe.set_user(admin)
		frappe.get_doc("Operational Notice", notice).check_permission("read")
		self.assertIn(f"{name} was submitted.", _subjects(name))

	def test_a_failed_ticket_notice_leaves_the_ticket(self):
		frappe.set_user(self.staff)
		ticket = save_ticket(
			category="Leak",
			urgency="Normal",
			property=self.home,
			description="Secret leak under the sink",
		)
		frappe.set_user(self.manager)
		with patch(
			"hotlync.accommodation.notify._insert_notice",
			side_effect=RuntimeError("mailbox unavailable"),
		):
			assigned = assign_ticket(ticket["name"], contractor_name="Pipe Co")
		self.assertEqual(assigned["status"], "Assigned")
		self.assertEqual(
			frappe.db.get_value("Maintenance Ticket", ticket["name"], "status"),
			"Assigned",
		)
		failed = frappe.db.get_value(
			"Operational Notice",
			{"reference_name": ticket["name"], "status": "Failed"},
			["subject", "detail"],
			as_dict=True,
		)
		self.assertEqual(failed.subject, "A notice could not be delivered.")
		self.assertIn("mailbox unavailable", failed.detail)
		self.assertNotIn("Secret leak under the sink", failed.detail)

	def test_a_failed_failure_record_still_leaves_the_approval(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		with patch(
			"hotlync.accommodation.notify._insert_notice",
			side_effect=RuntimeError("mailbox unavailable"),
		), patch(
			"hotlync.accommodation.notify._insert_failure",
			side_effect=RuntimeError("log store down"),
		):
			decide_request(name, "Approved", comment="Visitor passport 123")
		self.assertEqual(
			frappe.db.get_value("Accommodation Request", name, "status"),
			"Approved",
		)
		self.assertFalse(
			frappe.db.exists(
				"Operational Notice",
				{"reference_name": name, "event": "Approved"},
			)
		)

	def test_a_repeated_approval_does_not_duplicate_the_notice(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		decide_request(name, "Approved")
		count = frappe.db.count(
			"Operational Notice",
			{"reference_name": name, "event": "Approved"},
		)
		self.assertEqual(count, 1)
		with self.assertRaises(frappe.ValidationError):
			decide_request(name, "Approved")
		self.assertEqual(
			frappe.db.count(
				"Operational Notice",
				{"reference_name": name, "event": "Approved"},
			),
			count,
		)
		self.assertEqual(
			frappe.db.get_value("Accommodation Request", name, "status"),
			"Approved",
		)

	def test_rejection_omits_the_comment(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		rejected = decide_request(name, "Rejected", comment="Notice Check secret")
		self.assertEqual(rejected["status"], "Rejected")
		frappe.set_user(self.staff)
		subjects = _subjects(name)
		self.assertIn(f"{name} was rejected.", subjects)
		self.assertNotIn("Notice Check secret", " ".join(subjects))
		self.assertNotIn(self.employee, " ".join(subjects))

	def test_check_in_check_out_and_key_issue_do_not_notify(self):
		resident = _employee()
		room = frappe.db.get_value("Bed", self.bed, "room")
		frappe.set_user(self.manager)
		allocation = allocate_bed(resident, self.bed)
		checked = check_in(allocation["name"])
		self.assertEqual(checked["status"], "Checked In")
		finished = check_out(allocation["name"])
		self.assertEqual(finished["status"], "Completed")
		key = register_key(label="Stay key", property=self.home, room=room)
		issued = issue_key(key["name"], employee=resident)
		self.assertEqual(issued["status"], "Issued")
		self.assertFalse(
			frappe.db.exists(
				"Operational Notice",
				{"reference_name": ["in", [allocation["name"], key["name"]]]},
			)
		)

	def test_guest_cannot_list_notices(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.AuthenticationError, get_notices)

	def _submitted(self):
		frappe.set_user(self.staff)
		draft = save_request(
			request_type="Room Change",
			property=self.home,
			reason="Window",
		)
		return submit_request(draft["name"])["name"]


def _subjects(reference_name, user=None):
	if user:
		frappe.set_user(user)
	rows = get_notices()
	return [
		row.subject
		for row in rows
		if row.reference_name == reference_name and row.status == "Delivered"
	]


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
			"first_name": "Notice",
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
			"first_name": "Notice",
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
