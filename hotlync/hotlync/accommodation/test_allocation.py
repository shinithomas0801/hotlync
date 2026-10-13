import frappe
from frappe.tests import IntegrationTestCase

from hotlync.accommodation.workflow import location_for_bed
from hotlync.api import allocate_bed


class TestAllocation(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_alloc")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_alloc")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_draft_allocation_keeps_the_bed_available(self):
		employee = _employee()
		bed = _available_bed(self)
		location = location_for_bed(bed)
		created = allocate_bed(employee, bed)
		self.assertEqual(created["status"], "Draft")
		self.assertEqual(created["employee"], employee)
		self.assertEqual(created["property"], location["property"])
		self.assertEqual(created["building"], location["building"])
		self.assertEqual(created["room"], location["room"])
		self.assertEqual(created["bed"], bed)
		self.assertEqual(created["allocation_date"], frappe.utils.today())
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		row = frappe.db.get_value(
			"Accommodation Allocation",
			created["name"],
			["active_bed", "active_employee", "status"],
			as_dict=True,
		)
		self.assertEqual(row.active_bed, bed)
		self.assertEqual(row.active_employee, employee)
		self.assertEqual(row.status, "Draft")
		self._stays_unchanged_when_property_is_supplied(bed, location)

	def test_missing_employee_and_bed_leave_no_row(self):
		employee = _employee()
		bed = _available_bed(self)
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(employee, "NO-SUCH-BED")
		self.assertIn("Bed not found", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed("HR-EMP-NONE", bed)
		self.assertIn("Employee not found", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")

	def test_blocked_beds_are_rejected(self):
		beds = _available_beds(4)
		if len(beds) < 4:
			self.skipTest("Need four available beds")
		maintenance, occupied, taken, drafted = beds
		holder = _employee()
		frappe.db.set_value("Bed", maintenance, "status", "Maintenance")
		frappe.db.set_value("Bed", occupied, "status", "Occupied")
		_allocation(holder, taken, "Checked In")
		_allocation(_employee(), drafted, "Draft")
		before = frappe.db.count("Accommodation Allocation")
		newcomer = _employee()
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(newcomer, maintenance)
		self.assertIn("maintenance", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(newcomer, occupied)
		self.assertIn("occupied", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(newcomer, taken)
		self.assertIn("already has an active allocation", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(newcomer, drafted)
		self.assertIn("already has an active allocation", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", maintenance, "status"), "Maintenance")
		self.assertEqual(frappe.db.get_value("Bed", occupied, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", taken, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", drafted, "status"), "Available")

	def test_repeat_allocation_does_not_duplicate(self):
		employee = _employee()
		beds = _available_beds(2)
		if len(beds) < 2:
			self.skipTest("Need two available beds")
		first, second = beds
		created = allocate_bed(employee, first)
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(employee, first)
		self.assertIn("already has an active allocation", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(employee, second)
		self.assertIn("already has an active allocation", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(_employee(), first)
		self.assertIn("already has an active allocation", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", created["name"], "status"),
			"Draft",
		)
		self.assertEqual(frappe.db.get_value("Bed", first, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", second, "status"), "Available")

	def test_bed_must_belong_to_a_residence(self):
		employee = _employee()
		bed = _available_bed(self)
		building = frappe.db.get_value("Room", frappe.db.get_value("Bed", bed, "room"), "building")
		frappe.db.set_value("Building", building, "property", None)
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(employee, bed)
		self.assertIn("not linked to a residence", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")

	def test_staff_and_other_residence_are_rejected(self):
		if not frappe.db.exists("User", "staff@hotlync.local"):
			self.skipTest("staff@hotlync.local is not on this site")
		if not frappe.db.exists("User", "manager@hotlync.local"):
			self.skipTest("manager@hotlync.local is not on this site")
		home = _available_bed(self)
		other = _bed_for_property("SRB")
		if not other:
			self.skipTest("Staff Residence B has no available bed")
		employee = _employee()
		before = frappe.db.count("Accommodation Allocation")
		frappe.set_user("staff@hotlync.local")
		with self.assertRaises(frappe.PermissionError) as caught:
			allocate_bed(employee, home)
		self.assertIn("Not permitted", str(caught.exception))
		frappe.set_user("manager@hotlync.local")
		with self.assertRaises(frappe.PermissionError) as caught:
			allocate_bed(employee, other)
		self.assertIn("Not permitted", str(caught.exception))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", home, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", other, "status"), "Available")

	def _stays_unchanged_when_property_is_supplied(self, bed, location):
		other_property = "SRB" if location["property"] == "SRA" else "SRA"
		if not frappe.db.exists("Property", other_property):
			return
		spare = frappe.db.get_value(
			"Bed",
			{"status": "Available", "name": ["!=", bed]},
			"name",
		)
		if not spare:
			return
		doc = frappe.get_doc(
			{
				"doctype": "Accommodation Allocation",
				"employee": _employee(),
				"bed": spare,
				"property": other_property,
				"status": "Draft",
				"allocation_date": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		self.assertEqual(doc.property, location_for_bed(spare)["property"])
		self.assertEqual(doc.building, location_for_bed(spare)["building"])
		self.assertEqual(doc.room, location_for_bed(spare)["room"])


def _employee():
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Alloc",
			"last_name": "Check",
			"gender": "Male",
			"date_of_birth": "1995-01-01",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
		}
	).insert(ignore_permissions=True)
	return employee.name


def _available_bed(test):
	bed = frappe.db.get_value("Bed", {"status": "Available"}, "name")
	if not bed:
		test.skipTest("No available bed")
	return bed


def _available_beds(limit):
	return frappe.get_all(
		"Bed",
		filters={"status": "Available"},
		pluck="name",
		limit=limit,
	)


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


def _allocation(employee, bed, status):
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
