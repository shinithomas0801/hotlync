import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import (
	get_keys,
	issue_key,
	record_key_incident,
	register_key,
	return_key,
)


class TestKeys(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_keys")
		self.home, self.bed = _residence("KEYH", "Key Residence")
		self.other, self.other_bed = _residence("KEYO", "Other Key Residence")
		self.room = frappe.db.get_value("Bed", self.bed, "room")
		self.staff = _user("key-staff@hotlync.local", "Staff")
		self.employee = _employee(self.staff)
		self.manager = _user("key-manager@hotlync.local", "Accommodation Manager")
		self.outsider = _user("key-outsider@hotlync.local", "Accommodation Manager")
		_assign(self.manager, self.home)
		_assign(self.outsider, self.other)

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_keys")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_register_does_not_change_the_bed(self):
		before = frappe.db.get_value("Bed", self.bed, "status")
		stays = frappe.db.count("Accommodation Allocation")
		frappe.set_user(self.manager)
		row = register_key(label="A-1", kind="Key", property=self.home, room=self.room)
		self.assertTrue(row["name"].startswith("KEY-"))
		self.assertEqual(row["status"], "Available")
		self.assertEqual(row["movements"][0]["action"], "Registered")
		self.assertEqual(row["movements"][0]["actor"], self.manager)
		point = register_key(
			label="Gate",
			kind="Key Set",
			property=self.home,
			access_point="Front gate",
		)
		self.assertEqual(point["kind"], "Key Set")
		self.assertEqual(point["access_point"], "Front gate")
		self.assertFalse(point["room"])
		self.assertEqual(frappe.db.get_value("Bed", self.bed, "status"), before)
		self.assertEqual(frappe.db.count("Accommodation Allocation"), stays)

	def test_place_and_duplicate_mark_are_rejected(self):
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError) as missing:
			register_key(label="  ", property=self.home, room=self.room)
		self.assertIn("A key mark is required", str(missing.exception))
		with self.assertRaises(frappe.ValidationError) as place:
			register_key(label="Loose", property=self.home)
		self.assertIn("Name a room or an access point", str(place.exception))
		with self.assertRaises(frappe.ValidationError) as room:
			register_key(
				label="Foreign",
				property=self.home,
				room=frappe.db.get_value("Bed", self.other_bed, "room"),
			)
		self.assertIn("Room is not in the selected residence", str(room.exception))
		register_key(label="A-1", property=self.home, room=self.room)
		with self.assertRaises(frappe.ValidationError) as duplicate:
			register_key(label="A-1", property=self.home, access_point="Side gate")
		self.assertIn(
			"A key with that mark is already registered at this residence.",
			str(duplicate.exception),
		)
		frappe.set_user(self.outsider)
		other = register_key(
			label="A-1",
			property=self.other,
			room=frappe.db.get_value("Bed", self.other_bed, "room"),
		)
		self.assertEqual(other["label"], "A-1")

	def test_issue_and_return_keep_the_history(self):
		name = self._registered()
		stays = frappe.db.count("Accommodation Allocation")
		frappe.set_user(self.manager)
		due = frappe.utils.add_days(frappe.utils.today(), 3)
		issued = issue_key(name, employee=self.employee, expected_return=due)
		self.assertEqual(issued["status"], "Issued")
		self.assertEqual(issued["employee"], self.employee)
		self.assertEqual(issued["custodian"], self.manager)
		self.assertEqual(issued["expected_return"], due)
		self.assertEqual(issued["movements"][-1]["action"], "Issued")
		outstanding = [row["name"] for row in get_keys(status="Issued")["keys"]]
		self.assertIn(name, outstanding)
		returned = return_key(name, condition="Good")
		self.assertEqual(returned["status"], "Available")
		self.assertIsNone(returned["employee"])
		self.assertEqual(
			[item["action"] for item in returned["movements"]],
			["Registered", "Issued", "Returned"],
		)
		again = issue_key(name, employee=self.employee)
		self.assertEqual(again["status"], "Issued")
		self.assertEqual(len(again["movements"]), 4)
		self.assertIsNone(again["expected_return"])
		with self.assertRaises(frappe.ValidationError) as caught:
			issue_key(name, employee=self.employee)
		self.assertIn("That key is not available to issue", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), stays)

	def test_return_without_issue_and_inactive_recipient_are_rejected(self):
		name = self._registered()
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError) as plain:
			return_key(name)
		self.assertIn("That key is not issued", str(plain.exception))
		inactive = _employee()
		frappe.db.set_value("Employee", inactive, "status", "Inactive")
		with self.assertRaises(frappe.ValidationError) as caught:
			issue_key(name, employee=inactive)
		self.assertIn("Employee is not active", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Key", name, "status"), "Available")

	def test_damaged_lost_and_replaced_need_a_note(self):
		name = self._registered()
		frappe.set_user(self.manager)
		issue_key(name, employee=self.employee)
		with self.assertRaises(frappe.ValidationError) as missing:
			return_key(name, condition="Damaged", note="")
		self.assertIn("A note is required", str(missing.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Key", name, "status"), "Issued")
		damaged = return_key(name, condition="Damaged", note="Bent in the lock")
		self.assertEqual(damaged["status"], "Damaged")
		self.assertEqual(damaged["movements"][-1]["note"], "Bent in the lock")
		with self.assertRaises(frappe.ValidationError):
			issue_key(name, employee=self.employee)
		spare = self._registered("Spare")
		with self.assertRaises(frappe.ValidationError) as lost:
			record_key_incident(spare, "Lost", note="")
		self.assertIn("A note is required", str(lost.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Key", spare, "status"), "Available")
		other = self._registered("Other spare", residence=self.other, user=self.outsider)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError) as foreign:
			record_key_incident(spare, "Replaced", note="Cut a new key", replaced_by=other)
		self.assertIn(
			"Replacement key is not in the selected residence",
			str(foreign.exception),
		)
		replacement = self._registered("Replacement")
		replaced = record_key_incident(
			spare,
			"Replaced",
			note="Cut a new key",
			replaced_by=replacement,
		)
		self.assertEqual(replaced["status"], "Replaced")
		self.assertEqual(replaced["replaced_by"], replacement)
		self.assertEqual(replaced["movements"][-1]["action"], "Replaced")

	def test_other_property_cannot_see_or_issue(self):
		name = self._registered()
		frappe.set_user(self.outsider)
		visible = [row["name"] for row in get_keys()["keys"]]
		self.assertNotIn(name, visible)
		with self.assertRaises(frappe.ValidationError) as missing:
			get_keys(name=name)
		self.assertIn("Key not found", str(missing.exception))
		with self.assertRaises(frappe.PermissionError) as denied:
			issue_key(name, employee=self.employee)
		self.assertIn("Not permitted", str(denied.exception))

	def test_staff_sees_only_a_key_issued_to_them(self):
		own = self._registered("Staff key")
		cupboard = self._registered("Cupboard")
		frappe.set_user(self.manager)
		issue_key(own, employee=self.employee, expected_return=frappe.utils.today())
		frappe.set_user(self.staff)
		visible = [row["name"] for row in get_keys()["keys"]]
		self.assertIn(own, visible)
		self.assertNotIn(cupboard, visible)
		with self.assertRaises(frappe.PermissionError):
			register_key(label="Stolen", property=self.home, room=self.room)
		with self.assertRaises(frappe.PermissionError):
			return_key(own)

	def test_expected_return_cannot_be_before_today(self):
		name = self._registered()
		frappe.set_user(self.manager)
		yesterday = frappe.utils.add_days(frappe.utils.today(), -1)
		with self.assertRaises(frappe.ValidationError) as caught:
			issue_key(name, employee=self.employee, expected_return=yesterday)
		self.assertIn("Expected return cannot be before today", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Key", name, "status"), "Available")

	def test_a_key_record_cannot_be_deleted(self):
		name = self._registered()
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError) as caught:
			frappe.delete_doc("Accommodation Key", name)
		self.assertIn("A key record cannot be deleted", str(caught.exception))
		self.assertTrue(frappe.db.exists("Accommodation Key", name))

	def test_guest_cannot_list_keys(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.AuthenticationError, get_keys)

	def _registered(self, label="A-1", residence=None, user=None):
		frappe.set_user(user or self.manager)
		if residence == self.other:
			room = frappe.db.get_value("Bed", self.other_bed, "room")
			property_name = self.other
		else:
			room = self.room
			property_name = self.home
		row = register_key(label=label, property=property_name, room=room)
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
			"first_name": "Key",
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
			"first_name": "Key",
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
