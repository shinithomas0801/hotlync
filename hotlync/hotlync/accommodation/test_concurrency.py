import threading

import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import allocate_bed, check_in, check_out, get_available_beds, transfer_stay


class TestConcurrency(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_two_allocations_cannot_take_one_bed(self):
		_wipe()
		try:
			bed = _beds(1)[0]
			first, second = _employees(2)
			frappe.db.commit()
			left, right = _race(
				lambda: allocate_bed(first, bed),
				lambda: allocate_bed(second, bed),
			)
			_assert_one_winner(self, left, right)
			winner = left if not isinstance(left, Exception) else right
			rows = frappe.get_all(
				"Accommodation Allocation",
				filters={"bed": bed, "status": "Draft"},
				fields=["employee"],
			)
			self.assertEqual(len(rows), 1)
			self.assertEqual(rows[0].employee, winner["employee"])
			self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		finally:
			_wipe()

	def test_two_check_ins_cannot_both_succeed(self):
		_wipe()
		try:
			bed = _beds(1)[0]
			employee = _employees(1)[0]
			stay = allocate_bed(employee, bed)["name"]
			frappe.db.commit()
			left, right = _race(
				lambda: check_in(stay, "2026-10-01"),
				lambda: check_in(stay, "2026-10-02"),
			)
			_assert_one_winner(self, left, right)
			winner = left if not isinstance(left, Exception) else right
			self.assertEqual(winner["status"], "Checked In")
			self.assertEqual(
				str(frappe.db.get_value("Accommodation Allocation", stay, "check_in_date")),
				str(winner["check_in_date"]),
			)
			self.assertEqual(
				frappe.db.get_value("Accommodation Allocation", stay, "status"),
				"Checked In",
			)
			self.assertEqual(frappe.db.count("Accommodation Allocation", {"bed": bed}), 1)
			self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Occupied")
		finally:
			_wipe()

	def test_two_transfers_cannot_take_one_bed(self):
		_wipe()
		try:
			source, dest = _beds(2)
			employee = _employees(1)[0]
			stay = allocate_bed(employee, source)["name"]
			check_in(stay, "2026-10-01")
			frappe.db.commit()
			left, right = _race(
				lambda: transfer_stay(stay, dest, reason="first"),
				lambda: transfer_stay(stay, dest, reason="second"),
			)
			_assert_one_winner(self, left, right)
			winner = left if not isinstance(left, Exception) else right
			self.assertEqual(winner["previous"]["status"], "Transferred")
			self.assertEqual(winner["current"]["status"], "Checked In")
			self.assertEqual(winner["current"]["bed"], dest)
			self.assertEqual(
				frappe.db.count("Accommodation Allocation", {"employee": employee, "status": "Checked In"}),
				1,
			)
			self.assertEqual(
				frappe.db.count("Accommodation Allocation", {"employee": employee, "status": "Transferred"}),
				1,
			)
			self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
			self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Occupied")
		finally:
			_wipe()

	def test_checkout_overlaps_transfer(self):
		_wipe()
		try:
			source, dest = _beds(2)
			employee = _employees(1)[0]
			stay = allocate_bed(employee, source)["name"]
			check_in(stay, "2026-10-01")
			frappe.db.commit()
			left, right = _race(
				lambda: check_out(stay, "2026-10-11"),
				lambda: transfer_stay(stay, dest, reason="overlap"),
			)
			_assert_one_winner(self, left, right)
			winner = left if not isinstance(left, Exception) else right
			active = frappe.db.count(
				"Accommodation Allocation",
				{"employee": employee, "status": "Checked In"},
			)
			if winner.get("current"):
				self.assertEqual(active, 1)
				self.assertEqual(
					frappe.db.get_value("Accommodation Allocation", stay, "status"),
					"Transferred",
				)
				self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
				self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Occupied")
			else:
				self.assertEqual(active, 0)
				self.assertEqual(
					frappe.db.get_value("Accommodation Allocation", stay, "status"),
					"Completed",
				)
				self.assertEqual(
					str(frappe.db.get_value("Accommodation Allocation", stay, "check_out_date")),
					"2026-10-11",
				)
				self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
				self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Available")
			self.assertEqual(
				frappe.db.count("Accommodation Allocation", {"employee": employee, "status": "Draft"}),
				0,
			)
		finally:
			_wipe()

	def test_stale_availability_is_rechecked(self):
		frappe.db.savepoint("hotlync_stale")
		try:
			bed = frappe.db.get_value("Bed", {"status": "Available"}, "name")
			if not bed:
				self.skipTest("No available bed")
			seen = {row.name for row in get_available_beds()}
			self.assertIn(bed, seen)
			first = _employee("Stale")
			second = _employee("Stale")
			allocate_bed(first, bed)
			with self.assertRaises(frappe.ValidationError) as caught:
				allocate_bed(second, bed)
			self.assertIn("already has an active allocation", str(caught.exception))
			self.assertNotIn("Duplicate entry", str(caught.exception))
			self.assertEqual(frappe.db.count("Accommodation Allocation", {"bed": bed, "status": "Draft"}), 1)
			self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		finally:
			frappe.db.rollback(save_point="hotlync_stale")


def _assert_one_winner(test, left, right):
	results = (left, right)
	winners = [row for row in results if not isinstance(row, Exception)]
	losers = [row for row in results if isinstance(row, Exception)]
	test.assertEqual(len(winners), 1, msg=[str(row) for row in results])
	test.assertEqual(len(losers), 1, msg=[str(row) for row in results])
	text = str(losers[0])
	test.assertNotIn("Duplicate entry", text)
	test.assertNotIn("active_bed", text)
	test.assertNotIn("active_employee", text)
	test.assertNotIn("tabBed", text)
	test.assertNotIn("tabSeries", text)
	test.assertNotIn("Record has changed", text)
	test.assertTrue(
		"already has an active allocation" in text
		or "Only a draft allocation can be checked in" in text
		or "Only a checked-in stay can be transferred" in text
		or "Only a checked-in stay can be checked out" in text
		or "occupied" in text
	)


def _race(first, second):
	barrier = threading.Barrier(2)
	buckets = [[], []]
	site = frappe.local.site

	def run(index, fn):
		try:
			frappe.init(site=site)
			frappe.connect()
			frappe.set_user("Administrator")
			barrier.wait(timeout=20)
			buckets[index].append(fn())
			frappe.db.commit()
		except Exception as exc:
			try:
				frappe.db.rollback()
			except Exception:
				pass
			buckets[index].append(exc)
		finally:
			try:
				frappe.destroy()
			except Exception:
				pass

	threads = [
		threading.Thread(target=run, args=(0, first)),
		threading.Thread(target=run, args=(1, second)),
	]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join(timeout=60)
	frappe.set_user("Administrator")
	frappe.db.rollback()
	if any(thread.is_alive() for thread in threads) or len(buckets[0]) != 1 or len(buckets[1]) != 1:
		raise AssertionError("A concurrent request did not finish: " + str(buckets))
	return buckets[0][0], buckets[1][0]


def _wipe():
	frappe.set_user("Administrator")
	employees = frappe.get_all("Employee", filters={"first_name": "Race"}, pluck="name")
	buildings = frappe.get_all("Building", filters={"property": "RACE"}, pluck="name")
	floors = frappe.get_all("Floor", filters={"building": ["in", buildings]}, pluck="name") if buildings else []
	rooms = frappe.get_all("Room", filters={"floor": ["in", floors]}, pluck="name") if floors else []
	beds = frappe.get_all("Bed", filters={"room": ["in", rooms]}, pluck="name") if rooms else []
	names = set(frappe.get_all("Accommodation Allocation", filters={"property": "RACE"}, pluck="name"))
	if employees:
		names.update(
			frappe.get_all(
				"Accommodation Allocation",
				filters={"employee": ["in", employees]},
				pluck="name",
			)
		)
	if beds:
		names.update(
			frappe.get_all(
				"Accommodation Allocation",
				filters={"bed": ["in", beds]},
				pluck="name",
			)
		)
	for name in names:
		if frappe.db.exists("Accommodation Allocation", name):
			frappe.delete_doc("Accommodation Allocation", name, force=1, ignore_permissions=True)
	for bed in beds:
		if frappe.db.exists("Bed", bed):
			frappe.delete_doc("Bed", bed, force=1, ignore_permissions=True)
	for room in rooms:
		if frappe.db.exists("Room", room):
			frappe.delete_doc("Room", room, force=1, ignore_permissions=True)
	for floor in floors:
		if frappe.db.exists("Floor", floor):
			frappe.delete_doc("Floor", floor, force=1, ignore_permissions=True)
	for building in buildings:
		if frappe.db.exists("Building", building):
			frappe.delete_doc("Building", building, force=1, ignore_permissions=True)
	if frappe.db.exists("Property", "RACE"):
		frappe.delete_doc("Property", "RACE", force=1, ignore_permissions=True)
	for employee in employees:
		if frappe.db.exists("Employee", employee):
			frappe.delete_doc("Employee", employee, force=1, ignore_permissions=True)
	frappe.db.commit()


def _beds(count):
	if not frappe.db.exists("Property", "RACE"):
		frappe.get_doc(
			{
				"doctype": "Property",
				"code": "RACE",
				"property_name": "Race Residence",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Building",
				"code": "RACE-B",
				"building_name": "Race building",
				"property": "RACE",
				"number_of_floors": 1,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Floor",
				"building": "RACE-B",
				"floor_number": 1,
				"floor_name": "Floor 1",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Room",
				"floor": "RACE-B-1",
				"building": "RACE-B",
				"room_number": "1",
				"room_type": "Shared",
				"capacity": count,
				"status": "Available",
			}
		).insert(ignore_permissions=True)
	room = "RACE-B-1-1"
	beds = []
	for index in range(count):
		bed = frappe.get_doc(
			{
				"doctype": "Bed",
				"room": room,
				"bed_number": str(index + 1),
				"status": "Available",
			}
		).insert(ignore_permissions=True)
		beds.append(bed.name)
	return beds


def _employees(count):
	names = []
	for _index in range(count):
		names.append(_employee("Race"))
	return names


def _employee(first_name):
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": first_name,
			"last_name": "Stay",
			"gender": "Male",
			"date_of_birth": "1995-01-01",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
		}
	).insert(ignore_permissions=True)
	return employee.name
