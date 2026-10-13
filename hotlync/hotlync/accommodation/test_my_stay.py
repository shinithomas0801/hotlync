import frappe
from frappe.tests import IntegrationTestCase

from hotlync.accommodation.workflow import location_for_bed
from hotlync.api import get_my_stay


class TestMyStay(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_stay")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_stay")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_staff_stay_ignores_a_supplied_employee(self):
		self._require_user("staff@hotlync.local")
		john = frappe.db.get_value("Employee", {"user_id": "staff@hotlync.local"}, "name")
		if not john:
			self.skipTest("Staff login is not linked to an employee")
		other = _employee()
		bed = frappe.db.get_value("Bed", {"status": "Available"}, "name")
		if not bed:
			self.skipTest("No available bed")
		foreign = _allocation(other, bed, "Checked In")
		frappe.set_user("staff@hotlync.local")
		stay = get_my_stay(employee=other)
		self.assertTrue(stay["mapped"])
		names = _names(stay)
		self.assertNotIn(foreign, names)
		for row in [stay["current"], *stay["previous"]]:
			if row:
				self.assertEqual(row["employee"], john)
		if stay["current"]:
			self.assertTrue(stay["current"]["property_name"])
			self.assertTrue(stay["current"]["bed_number"])

	def test_unmapped_login_has_no_stay(self):
		user = _user("unmapped-staff@hotlync.local", "Staff")
		frappe.set_user(user)
		stay = get_my_stay(employee="HR-EMP-00001")
		self.assertFalse(stay["mapped"])
		self.assertIsNone(stay["current"])
		self.assertEqual(stay["previous"], [])

	def test_mapped_user_with_no_checked_in_stay(self):
		user = _user("empty-staff@hotlync.local", "Staff")
		employee = _employee(user)
		frappe.set_user(user)
		stay = get_my_stay()
		self.assertTrue(stay["mapped"])
		self.assertIsNone(stay["current"])
		self.assertEqual(stay["previous"], [])
		self.assertEqual(employee, frappe.db.get_value("Employee", {"user_id": user}, "name"))

	def test_mapped_user_sees_the_checked_in_stay(self):
		user = _user("active-staff@hotlync.local", "Staff")
		employee = _employee(user)
		earlier_bed, current_bed, foreign_bed = _beds("MYST")
		earlier = _allocation(employee, earlier_bed, "Completed")
		current = _allocation(employee, current_bed, "Checked In")
		foreign = _allocation(_employee(), foreign_bed, "Checked In")
		frappe.set_user(user)
		stay = get_my_stay(employee=foreign)
		self.assertTrue(stay["mapped"])
		self.assertEqual(stay["current"]["name"], current)
		self.assertEqual(stay["current"]["employee"], employee)
		self.assertEqual(stay["current"]["status"], "Checked In")
		self.assertTrue(stay["current"]["property_name"])
		self.assertTrue(stay["current"]["bed_number"])
		previous = [row["name"] for row in stay["previous"]]
		self.assertIn(earlier, previous)
		self.assertNotIn(foreign, previous)
		self.assertNotIn(current, previous)

	def test_guest_cannot_read_a_stay(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.AuthenticationError, get_my_stay)

	def _require_user(self, email):
		if not frappe.db.exists("User", email):
			self.skipTest(email + " is not on this site")


def _names(stay):
	found = []
	if stay["current"]:
		found.append(stay["current"]["name"])
	found.extend(row["name"] for row in stay["previous"])
	return found


def _user(email, role):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Stay",
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
			"first_name": "Stay",
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


def _allocation(employee, bed, status):
	frappe.set_user("Administrator")
	location = location_for_bed(bed)
	doc = frappe.get_doc(
		{
			"doctype": "Accommodation Allocation",
			"employee": employee,
			"bed": bed,
			"property": location["property"],
			"building": location["building"],
			"room": location["room"],
			"allocation_date": frappe.utils.today(),
			"status": status,
			"check_in_date": frappe.utils.today() if status == "Checked In" else None,
		}
	).insert(ignore_permissions=True)
	return doc.name


def _beds(code):
	frappe.set_user("Administrator")
	property_doc = frappe.get_doc(
		{
			"doctype": "Property",
			"code": code,
			"property_name": "My Stay Residence",
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	building = frappe.get_doc(
		{
			"doctype": "Building",
			"code": code + "-B",
			"building_name": "My Stay Building",
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
			"room_type": "Shared",
			"capacity": 3,
			"status": "Available",
		}
	).insert(ignore_permissions=True)
	beds = []
	for number in ("A", "B", "C"):
		bed = frappe.get_doc(
			{
				"doctype": "Bed",
				"room": room.name,
				"bed_number": number,
				"status": "Available",
			}
		).insert(ignore_permissions=True)
		beds.append(bed.name)
	return beds
