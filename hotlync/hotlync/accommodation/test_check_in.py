import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import allocate_bed, check_in


class TestCheckIn(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_checkin")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_checkin")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_check_in_succeeds_once(self):
		employee = _employee()
		bed = _available_bed(self)
		draft = allocate_bed(employee, bed)
		before = frappe.db.count("Accommodation Allocation")
		checked = check_in(draft["name"], "2026-10-01")
		self.assertEqual(checked["status"], "Checked In")
		self.assertEqual(checked["check_in_date"], "2026-10-01")
		self.assertEqual(checked["employee"], employee)
		self.assertEqual(checked["bed"], bed)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Occupied")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		with self.assertRaises(frappe.ValidationError) as caught:
			check_in(draft["name"], "2026-10-02")
		self.assertIn("Only a draft allocation can be checked in", str(caught.exception))
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", draft["name"], "status"),
			"Checked In",
		)
		self.assertEqual(
			str(frappe.db.get_value("Accommodation Allocation", draft["name"], "check_in_date")),
			"2026-10-01",
		)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Occupied")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)

	def test_other_statuses_cannot_be_checked_in(self):
		for status in ("Transferred", "Checked Out", "Completed"):
			bed = _available_bed(self)
			draft = allocate_bed(_employee(), bed)
			frappe.db.set_value(
				"Accommodation Allocation",
				draft["name"],
				{"status": status, "active_bed": None, "active_employee": None},
			)
			with self.assertRaises(frappe.ValidationError) as caught:
				check_in(draft["name"])
			self.assertIn("Only a draft allocation can be checked in", str(caught.exception))
			self.assertEqual(
				frappe.db.get_value("Accommodation Allocation", draft["name"], "status"),
				status,
			)
			self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
			self.assertFalse(
				frappe.db.get_value("Accommodation Allocation", draft["name"], "check_in_date")
			)

	def test_failed_check_in_leaves_the_draft(self):
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			check_in("ACC-ALLOC-NONE")
		self.assertIn("Allocation not found", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)

		employee = _employee()
		bed = _available_bed(self)
		draft = allocate_bed(employee, bed)
		frappe.db.set_value("Accommodation Allocation", draft["name"], "employee", "HR-EMP-GONE")
		_expect_unchanged(self, draft["name"], bed, "Employee not found")

		missing_bed = allocate_bed(_employee(), _available_bed(self))
		bed_name = missing_bed["bed"]
		frappe.db.set_value("Accommodation Allocation", missing_bed["name"], "bed", "NO-SUCH-BED")
		_expect_unchanged(self, missing_bed["name"], bed_name, "Bed not found")

		blocked = allocate_bed(_employee(), _available_bed(self))
		frappe.db.set_value("Bed", blocked["bed"], "status", "Maintenance")
		_expect_unchanged(self, blocked["name"], blocked["bed"], "maintenance")
		self.assertEqual(frappe.db.get_value("Bed", blocked["bed"], "status"), "Maintenance")

		occupied = allocate_bed(_employee(), _available_bed(self))
		frappe.db.set_value("Bed", occupied["bed"], "status", "Occupied")
		_expect_unchanged(self, occupied["name"], occupied["bed"], "occupied")

		unlinked = allocate_bed(_employee(), _available_bed(self))
		building = frappe.db.get_value("Room", frappe.db.get_value("Bed", unlinked["bed"], "room"), "building")
		frappe.db.set_value("Building", building, "property", None)
		_expect_unchanged(self, unlinked["name"], unlinked["bed"], "not linked to a residence")

	def test_unauthorized_check_in_is_rejected(self):
		staff = _user("checkin-staff@hotlync.local", "Staff")
		manager = _user("checkin-manager@hotlync.local", "Accommodation Manager")
		home = _bed_for_property("SRA")
		other = _bed_for_property("SRB")
		if not home or not other:
			self.skipTest("Both residences need an available bed")
		_assign(manager, "SRA")
		own = allocate_bed(_employee(), home)
		foreign = allocate_bed(_employee(), other)
		frappe.set_user(staff)
		with self.assertRaises(frappe.PermissionError) as caught:
			check_in(own["name"])
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRA", str(caught.exception))
		frappe.set_user(manager)
		with self.assertRaises(frappe.PermissionError) as caught:
			check_in(foreign["name"])
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRB", str(caught.exception))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", own["name"], "status"), "Draft")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", foreign["name"], "status"), "Draft")
		self.assertEqual(frappe.db.get_value("Bed", home, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", other, "status"), "Available")

	def test_check_in_uses_the_beds_current_residence(self):
		manager = _user("checkin-home@hotlync.local", "Accommodation Manager")
		bed = _bed_for_property("SRA")
		if not bed or not frappe.db.exists("Property", "SRB"):
			self.skipTest("Both residences are required")
		_assign(manager, "SRA")
		draft = allocate_bed(_employee(), bed)
		building = frappe.db.get_value("Room", frappe.db.get_value("Bed", bed, "room"), "building")
		frappe.db.set_value("Building", building, "property", "SRB")
		frappe.set_user(manager)
		with self.assertRaises(frappe.PermissionError) as caught:
			check_in(draft["name"])
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRB", str(caught.exception))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", draft["name"], "status"), "Draft")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", draft["name"], "property"), "SRA")
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		checked = check_in(draft["name"])
		self.assertEqual(checked["status"], "Checked In")
		self.assertEqual(checked["property"], "SRB")
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Occupied")


def _expect_unchanged(test, allocation, bed, message):
	before = frappe.db.count("Accommodation Allocation")
	with test.assertRaises(frappe.ValidationError) as caught:
		check_in(allocation)
	test.assertIn(message, str(caught.exception))
	test.assertEqual(frappe.db.get_value("Accommodation Allocation", allocation, "status"), "Draft")
	test.assertFalse(frappe.db.get_value("Accommodation Allocation", allocation, "check_in_date"))
	test.assertEqual(frappe.db.count("Accommodation Allocation"), before)
	if frappe.db.exists("Bed", bed):
		stored = frappe.db.get_value("Bed", bed, "status")
		if message not in ("maintenance", "occupied"):
			test.assertEqual(stored, "Available")


def _employee():
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Check",
			"last_name": "In",
			"gender": "Male",
			"date_of_birth": "1995-01-01",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
		}
	).insert(ignore_permissions=True)
	return employee.name


def _user(email, role):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Check",
			"last_name": "In",
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	).insert(ignore_permissions=True)
	user.add_roles(role)
	return user.name


def _assign(user, property_name):
	frappe.get_doc(
		{
			"doctype": "Property Assignment",
			"user": user,
			"property": property_name,
		}
	).insert(ignore_permissions=True)


def _available_bed(test):
	taken = set()
	for row in frappe.get_all(
		"Accommodation Allocation",
		filters={"status": ["in", ["Draft", "Checked In"]]},
		fields=["bed", "active_bed"],
		limit=100,
	):
		taken.add(row.bed)
		taken.add(row.active_bed)
	for bed in frappe.get_all("Bed", filters={"status": "Available"}, pluck="name", limit=30):
		if bed not in taken:
			return bed
	test.skipTest("No available bed")


def _bed_for_property(property_name):
	rows = frappe.db.sql(
		"""
		select b.name
		from `tabBed` b
		inner join `tabRoom` r on r.name = b.room
		inner join `tabFloor` f on f.name = r.floor
		inner join `tabBuilding` g on g.name = f.building
		where g.property = %s and b.status = 'Available'
		limit 1
		""",
		property_name,
	)
	return rows[0][0] if rows else None
