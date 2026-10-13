import frappe
from frappe.tests import IntegrationTestCase

from hotlync.accommodation.doctype.accommodation_allocation.accommodation_allocation import (
	has_permission,
)
from hotlync.accommodation.workflow import location_for_bed
from hotlync.api import allocate_bed, check_in, check_out, get_my_stay, transfer_stay


class TestEmployeeMapping(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_map")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_map")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_hr_blocks_two_active_employees_on_one_login(self):
		user = _user("map-dup@hotlync.local")
		first = _employee(user)
		with self.assertRaises(frappe.DuplicateEntryError):
			_employee(user)
		self.assertEqual(
			frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name"),
			first,
		)

	def test_login_resolves_to_the_active_employee(self):
		user = _user("map-active@hotlync.local")
		former = _employee(user)
		bed = _available_bed()
		stay = _allocation(former, bed, "Checked In")
		_set_status(former, "Inactive")
		current = _employee(user)
		frappe.set_user(user)
		result = get_my_stay(employee=former)
		self.assertTrue(result["mapped"])
		self.assertIsNone(result["current"])
		self.assertEqual(result["previous"], [])
		self.assertFalse(has_permission(_doc(stay), ptype="read", user=user))
		frappe.set_user("Administrator")
		opened = frappe.get_doc("Accommodation Allocation", stay)
		opened.check_permission("read")
		self.assertEqual(opened.employee, former)
		self.assertEqual(opened.status, "Checked In")
		self.assertEqual(current, frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name"))

	def test_ambiguous_active_links_fail_closed(self):
		user = _user("map-ambiguous@hotlync.local")
		first = _employee(user)
		second = _employee()
		bed = _available_bed()
		stay = _allocation(first, bed, "Checked In")
		frappe.db.set_value("Employee", second, "user_id", user)
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError) as caught:
			get_my_stay(employee=first)
		self.assertIn("more than one employee", str(caught.exception))
		self.assertFalse(has_permission(_doc(stay), ptype="read", user=user))

	def test_unmapped_login_does_not_read_a_stay(self):
		user = _user("map-none@hotlync.local")
		employee = _employee()
		bed = _available_bed()
		stay = _allocation(employee, bed, "Checked In")
		frappe.set_user(user)
		result = get_my_stay(employee=employee)
		self.assertFalse(result["mapped"])
		self.assertIsNone(result["current"])
		self.assertEqual(result["previous"], [])
		self.assertFalse(has_permission(_doc(stay), ptype="read", user=user))

	def test_inactive_employee_cannot_start_or_move_a_stay(self):
		employee = _employee()
		bed, other = _two_beds()
		frappe.set_user("Administrator")
		draft = allocate_bed(employee, bed)
		_set_status(employee, "Inactive")
		with self.assertRaises(frappe.ValidationError) as caught:
			check_in(draft["name"])
		self.assertIn("not active", str(caught.exception))
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", draft["name"], "status"),
			"Draft",
		)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(employee, other)
		self.assertIn("not active", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)

		_set_status(employee, "Active")
		checked = check_in(draft["name"])
		self.assertEqual(checked["status"], "Checked In")
		_set_status(employee, "Inactive")
		with self.assertRaises(frappe.ValidationError) as caught:
			transfer_stay(draft["name"], other)
		self.assertIn("not active", str(caught.exception))
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", draft["name"], "status"),
			"Checked In",
		)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", other, "status"), "Available")
		opened = frappe.get_doc("Accommodation Allocation", draft["name"])
		opened.check_permission("read")
		self.assertEqual(opened.employee, employee)
		finished = check_out(draft["name"])
		self.assertEqual(finished["status"], "Completed")
		self.assertEqual(finished["employee"], employee)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		self.assertTrue(frappe.db.exists("Accommodation Allocation", draft["name"]))


def _doc(name):
	frappe.set_user("Administrator")
	return frappe.get_doc("Accommodation Allocation", name)


def _set_status(employee, status):
	frappe.set_user("Administrator")
	doc = frappe.get_doc("Employee", employee)
	doc.status = status
	doc.save(ignore_permissions=True)


def _user(email):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Map",
			"last_name": "Check",
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	).insert(ignore_permissions=True)
	user.add_roles("Staff")
	return user.name


def _employee(user_id=None):
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Map",
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


def _available_bed():
	bed = frappe.db.get_value("Bed", {"status": "Available"}, "name")
	if not bed:
		frappe.throw("No available bed")
	return bed


def _two_beds():
	beds = frappe.get_all("Bed", filters={"status": "Available"}, pluck="name", limit=2)
	if len(beds) < 2:
		frappe.throw("Need two available beds")
	return beds[0], beds[1]


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
