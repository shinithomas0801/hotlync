import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import (
	add_note,
	assign_ticket,
	get_tickets,
	reopen_ticket,
	save_ticket,
	update_ticket,
)


class TestMaintenance(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_maintenance")
		self.home, self.bed = _residence("MNTH", "Maintenance Residence")
		self.other, self.other_bed = _residence("MNTO", "Other Maintenance Residence")
		self.staff = _user("mnt-staff@hotlync.local", "Staff")
		self.employee = _employee(self.staff)
		self.worker = _user("mnt-worker@hotlync.local", "Staff")
		self.manager = _user("mnt-manager@hotlync.local", "Accommodation Manager")
		self.outsider = _user("mnt-outsider@hotlync.local", "Accommodation Manager")
		_assign(self.manager, self.home)
		_assign(self.outsider, self.other)

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_maintenance")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_staff_submits_a_ticket_without_changing_the_bed(self):
		other = _employee()
		before = frappe.db.get_value("Bed", self.bed, "status")
		frappe.set_user(self.staff)
		row = save_ticket(
			category="Leak",
			urgency="Urgent",
			property=self.home,
			bed=self.bed,
			employee=other,
			description="Water under the sink",
			preferred_contact="Extension 12",
		)
		self.assertTrue(row["name"].startswith("MNT-"))
		self.assertEqual(row["status"], "Submitted")
		self.assertEqual(row["employee"], self.employee)
		self.assertNotEqual(row["employee"], other)
		self.assertEqual(row["reported_by"], self.staff)
		self.assertEqual(row["reported_on"], frappe.utils.today())
		self.assertEqual(row["updates"][0]["action"], "Submitted")
		self.assertEqual(row["updates"][0]["actor"], self.staff)
		self.assertEqual(frappe.db.get_value("Bed", self.bed, "status"), before)

	def test_description_and_foreign_room_are_rejected(self):
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.ValidationError) as missing:
			save_ticket(
				category="Leak",
				urgency="Normal",
				property=self.home,
				description="",
			)
		self.assertIn("Description is required", str(missing.exception))
		with self.assertRaises(frappe.ValidationError) as room:
			save_ticket(
				category="Leak",
				urgency="Normal",
				property=self.home,
				room=frappe.db.get_value("Bed", self.other_bed, "room"),
				description="Wrong building",
			)
		self.assertIn("Room is not in the selected residence", str(room.exception))

	def test_other_property_cannot_see_or_assign(self):
		name = self._submitted()
		frappe.set_user(self.outsider)
		visible = [row["name"] for row in get_tickets()["tickets"]]
		self.assertNotIn(name, visible)
		with self.assertRaises(frappe.ValidationError) as missing:
			get_tickets(name=name)
		self.assertIn("Ticket not found", str(missing.exception))
		with self.assertRaises(frappe.PermissionError) as denied:
			assign_ticket(name, contractor_name="Pipe Co")
		self.assertIn("Not permitted", str(denied.exception))

	def test_assignment_needs_a_person_team_or_contractor(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError) as caught:
			assign_ticket(name, assignee="", team_name="", contractor_name="")
		self.assertIn("Name an assignee, a team, or a contractor", str(caught.exception))
		assigned = assign_ticket(name, contractor_name="Pipe Co")
		self.assertEqual(assigned["status"], "Assigned")
		self.assertEqual(assigned["contractor_name"], "Pipe Co")
		self.assertEqual(assigned["updates"][-1]["action"], "Assigned")

	def test_assignee_can_progress_and_cannot_close(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		assign_ticket(name, assignee=self.worker)
		frappe.set_user(self.worker)
		noted = add_note(name, "Progress", "Started the repair", evidence="Replaced the washer")
		self.assertEqual(noted["notes"][-1]["note_type"], "Progress")
		self.assertEqual(noted["notes"][-1]["evidence"], "Replaced the washer")
		progress = update_ticket(name, "In Progress")
		self.assertEqual(progress["status"], "In Progress")
		with self.assertRaises(frappe.ValidationError) as caught:
			update_ticket(name, "Closed")
		self.assertIn("That status change is not allowed", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Maintenance Ticket", name, "status"), "In Progress")

	def test_resolve_requires_details_and_a_repeat_does_not_notify_again(self):
		name = self._submitted()
		before = frappe.db.get_value("Bed", self.bed, "status")
		frappe.set_user(self.manager)
		assign_ticket(name, assignee=self.worker)
		frappe.set_user(self.worker)
		update_ticket(name, "In Progress")
		with self.assertRaises(frappe.ValidationError) as missing:
			update_ticket(name, "Resolved")
		self.assertIn("Resolution details are required", str(missing.exception))
		resolved = update_ticket(name, "Resolved", resolution="Washer replaced")
		self.assertEqual(resolved["status"], "Resolved")
		self.assertEqual(resolved["resolution"], "Washer replaced")
		update_count = len(resolved["updates"])
		with self.assertRaises(frappe.ValidationError):
			update_ticket(name, "Resolved", resolution="Washer replaced")
		self.assertEqual(
			frappe.db.count("Maintenance Update", {"parent": name}),
			update_count,
		)
		self.assertEqual(frappe.db.get_value("Bed", self.bed, "status"), before)

	def test_reporter_can_reopen_with_a_comment(self):
		name = self._submitted()
		frappe.set_user(self.manager)
		assign_ticket(name, team_name="Housekeeping")
		update_ticket(name, "Resolved", resolution="Cleaned")
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.ValidationError) as missing:
			reopen_ticket(name, comment="")
		self.assertIn("A comment is required", str(missing.exception))
		reopened = reopen_ticket(name, comment="It is leaking again")
		self.assertEqual(reopened["status"], "Submitted")
		self.assertEqual(reopened["updates"][-1]["action"], "Reopened")
		self.assertEqual(reopened["updates"][-1]["comment"], "It is leaking again")
		frappe.set_user("Administrator")
		hidden = _user("mnt-hidden@hotlync.local", "Staff")
		frappe.set_user(hidden)
		with self.assertRaises(frappe.ValidationError):
			get_tickets(name=name)

	def test_staff_cannot_assign(self):
		name = self._submitted()
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.PermissionError):
			assign_ticket(name, team_name="Housekeeping")

	def test_guest_cannot_list_tickets(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.AuthenticationError, get_tickets)

	def _submitted(self):
		frappe.set_user(self.staff)
		row = save_ticket(
			category="Leak",
			urgency="Normal",
			property=self.home,
			bed=self.bed,
			description="Water under the sink",
		)
		return row["name"]


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
			"first_name": "Ticket",
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
			"first_name": "Ticket",
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
