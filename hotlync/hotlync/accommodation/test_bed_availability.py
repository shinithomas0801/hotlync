import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import (
	allocate_bed,
	check_in,
	check_out,
	get_available_beds,
	get_dashboard,
	transfer_stay,
)


class TestBedAvailability(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_beds")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_beds")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_bed_status_follows_the_stay(self):
		beds = _free_beds("SRA", 3)
		if len(beds) < 3:
			self.skipTest("Need three free beds")
		source, dest, blocked = beds
		self.assertIn(source, _listed())
		before = get_dashboard(property="SRA")
		_balanced(self, before)
		stay = allocate_bed(_employee(), source)
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
		self.assertNotIn(source, _listed())
		self.assertEqual(get_dashboard(property="SRA"), before)
		check_in(stay["name"], "2026-10-01")
		occupied = get_dashboard(property="SRA")
		self.assertEqual(occupied["total"], before["total"])
		self.assertEqual(occupied["occupied"], before["occupied"] + 1)
		self.assertEqual(occupied["available"], before["available"] - 1)
		self.assertEqual(occupied["maintenance"], before["maintenance"])
		_balanced(self, occupied)
		self.assertNotIn(source, _listed())
		moved = transfer_stay(stay["name"], dest, reason="Room change")
		self.assertEqual(get_dashboard(property="SRA"), occupied)
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Occupied")
		self.assertIn(source, _listed())
		self.assertNotIn(dest, _listed())
		check_out(moved["current"]["name"], "2026-10-11")
		self.assertEqual(get_dashboard(property="SRA"), before)
		self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Available")
		self.assertIn(dest, _listed())
		frappe.db.set_value("Bed", blocked, "status", "Maintenance")
		held = get_dashboard(property="SRA")
		self.assertEqual(held["total"], before["total"])
		self.assertEqual(held["maintenance"], before["maintenance"] + 1)
		self.assertEqual(held["available"], before["available"] - 1)
		_balanced(self, held)
		self.assertNotIn(blocked, _listed())
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(_employee(), blocked)
		self.assertIn("maintenance", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Bed", blocked, "status"), "Maintenance")

	def test_inconsistent_parent_is_left_out(self):
		if not frappe.db.exists("Building", "BLD-B"):
			self.skipTest("Staff Residence B building is not on this site")
		bed = _free_beds("SRA", 1)
		if not bed:
			self.skipTest("No free bed")
		bed = bed[0]
		room = frappe.db.get_value("Bed", bed, "room")
		room_beds = frappe.get_all("Bed", filters={"room": room}, pluck="name")
		before = get_dashboard()
		home = get_dashboard(property="SRA")
		other = get_dashboard(property="SRB")
		statuses = {name: frappe.db.get_value("Bed", name, "status") for name in room_beds}
		frappe.db.set_value("Room", room, "building", "BLD-B")
		listed = _listed()
		for name in room_beds:
			self.assertNotIn(name, listed)
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(_employee(), bed)
		self.assertIn("not linked to a residence", str(caught.exception))
		self.assertEqual(get_dashboard()["total"], before["total"] - len(room_beds))
		self.assertEqual(get_dashboard(property="SRA")["total"], home["total"] - len(room_beds))
		self.assertEqual(get_dashboard(property="SRB"), other)
		_balanced(self, get_dashboard())
		for name, status in statuses.items():
			self.assertEqual(frappe.db.get_value("Bed", name, "status"), status)


def _balanced(test, counts):
	test.assertEqual(
		counts["occupied"] + counts["available"] + counts["maintenance"],
		counts["total"],
	)
	test.assertEqual(
		set(counts),
		{"total", "occupied", "available", "maintenance"},
	)


def _listed():
	return {row.name for row in get_available_beds()}


def _free_beds(property_name, limit):
	taken = set()
	for row in frappe.get_all(
		"Accommodation Allocation",
		filters={"status": ["in", ["Draft", "Checked In"]]},
		fields=["bed", "active_bed"],
		limit=100,
	):
		taken.add(row.bed)
		taken.add(row.active_bed)
	rows = frappe.db.sql(
		"""
		select b.name
		from `tabBed` b
		inner join `tabRoom` r on r.name = b.room
		inner join `tabFloor` f on f.name = r.floor
		inner join `tabBuilding` g on g.name = f.building
		where g.property = %s and b.status = 'Available'
		and ifnull(r.building, '') in ('', f.building)
		""",
		property_name,
	)
	return [row[0] for row in rows if row[0] not in taken][:limit]


def _employee():
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Bed",
			"last_name": "Count",
			"gender": "Male",
			"date_of_birth": "1995-01-01",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
		}
	).insert(ignore_permissions=True)
	return employee.name
