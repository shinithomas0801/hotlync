import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import (
	allocate_bed,
	check_in,
	check_out,
	get_accommodation_report,
	get_dashboard,
	transfer_stay,
)


class TestAccommodationReport(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_report")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_report")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_stay_report_matches_the_dashboard(self):
		home = _residence("RPTA", "Report Home", 4)
		other = _residence("RPTB", "Report Other", 1)
		frappe.db.set_value("Bed", home["beds"][3], "status", "Maintenance")
		today = frappe.utils.today()
		holder = _employee("Holder")
		resident = _employee("Resident")
		guest = _employee("Guest")
		hidden = check_in(allocate_bed(guest, other["beds"][0])["name"], today)
		before = get_dashboard(property=home["property"])
		self.assertEqual(before["total"], 4)
		self.assertEqual(before["occupied"], 0)
		self.assertEqual(before["available"], 3)
		self.assertEqual(before["maintenance"], 1)
		draft = allocate_bed(holder, home["beds"][2])
		report = get_accommodation_report(property=home["property"])
		_same_counts(self, report, before)
		self.assertIn(draft["name"], _names(report["active"]))
		self.assertNotIn(draft["name"], _names(report["assignments"]))
		self.assertEqual(report["check_ins_today"], 0)
		self.assertEqual(
			sum(row["total"] for row in report["buildings"]),
			report["total"],
		)
		opened = check_in(allocate_bed(resident, home["beds"][0])["name"], today)
		report = get_accommodation_report(property=home["property"])
		_same_counts(self, report, get_dashboard(property=home["property"]))
		self.assertEqual(report["occupied"], 1)
		self.assertEqual(report["check_ins_today"], 1)
		self.assertIn(opened["name"], _names(report["assignments"]))
		self.assertNotIn(hidden["name"], _names(report["assignments"]))
		moved = transfer_stay(opened["name"], home["beds"][1], reason="Room change")
		report = get_accommodation_report(property=home["property"])
		_same_counts(self, report, get_dashboard(property=home["property"]))
		self.assertEqual(report["occupied"], 1)
		self.assertEqual(report["check_ins_today"], 2)
		source = _one(report["transfers"], opened["name"])
		self.assertEqual(source["bed"], home["beds"][0])
		self.assertEqual(source["employee"], resident)
		self.assertEqual(source["reason"], "Room change")
		self.assertNotIn("active_bed", source)
		self.assertNotIn("active_employee", source)
		current = _one(report["assignments"], moved["current"]["name"])
		self.assertEqual(current["bed"], home["beds"][1])
		self.assertEqual(current["employee"], resident)
		check_out(moved["current"]["name"], today)
		report = get_accommodation_report(property=home["property"])
		_same_counts(self, report, get_dashboard(property=home["property"]))
		self.assertEqual(report["occupied"], 0)
		self.assertEqual(report["available"], 3)
		self.assertEqual(report["check_outs_today"], 1)
		self.assertIn(opened["name"], _names(report["transfers"]))
		self.assertIn(moved["current"]["name"], _names(report["check_outs"]))
		self.assertNotIn(moved["current"]["name"], _names(report["assignments"]))
		self.assertIn(draft["name"], _names(report["active"]))
		stored = set(frappe.get_all("Accommodation Allocation", pluck="name"))
		with self.assertRaises(frappe.ValidationError):
			allocate_bed(_employee("Blocked"), home["beds"][3])
		self.assertEqual(
			set(frappe.get_all("Accommodation Allocation", pluck="name")),
			stored,
		)
		away = get_accommodation_report(property=other["property"])
		_same_counts(self, away, get_dashboard(property=other["property"]))
		self.assertEqual(away["occupied"], 1)
		self.assertNotIn(opened["name"], _names(away["transfers"]))
		whole = get_accommodation_report()
		_same_counts(self, whole, get_dashboard())
		self.assertEqual(
			sum(row["occupied"] for row in whole["buildings"]),
			whole["occupied"],
		)
		room = frappe.db.get_value("Bed", home["beds"][0], "room")
		frappe.db.set_value("Room", room, "building", other["building"])
		self.assertEqual(get_accommodation_report(property=home["property"])["total"], 0)
		self.assertEqual(get_dashboard(property=home["property"])["total"], 0)
		self.assertEqual(get_dashboard(property=other["property"])["total"], 1)

	def test_report_stays_inside_the_assigned_residence(self):
		if not frappe.db.exists("User", "staff@hotlync.local"):
			self.skipTest("staff@hotlync.local is not on this site")
		home = _residence("RPTC", "Report Scope", 1)
		other = _residence("RPTD", "Report Hidden", 1)
		hidden = check_in(allocate_bed(_employee("Hidden"), other["beds"][0])["name"])
		manager = _user("report-manager@hotlync.local", "Accommodation Manager")
		frappe.set_user(manager)
		empty = get_accommodation_report()
		self.assertEqual(empty["total"], 0)
		self.assertEqual(empty["check_ins_today"], 0)
		self.assertEqual(empty["check_outs_today"], 0)
		self.assertEqual(empty["assignments"], [])
		self.assertEqual(empty["transfers"], [])
		self.assertEqual(empty["buildings"], [])
		self.assertEqual(empty["pending"], [])
		self.assertEqual(empty["arrivals"], [])
		self.assertEqual(empty["departures"], [])
		with self.assertRaises(frappe.PermissionError) as caught:
			get_accommodation_report(property=home["property"])
		self.assertEqual(str(caught.exception), "Not permitted")
		frappe.set_user("Administrator")
		_assign(manager, home["property"])
		frappe.set_user(manager)
		report = get_accommodation_report()
		self.assertEqual(report["total"], 1)
		self.assertEqual(report["total"], get_dashboard()["total"])
		self.assertNotIn(hidden["name"], _names(report["assignments"]))
		self.assertNotIn(hidden["name"], _names(report["check_ins"]))
		with self.assertRaises(frappe.PermissionError) as caught:
			get_accommodation_report(property=other["property"])
		self.assertEqual(str(caught.exception), "Not permitted")
		frappe.set_user("staff@hotlync.local")
		self.assertRaises(frappe.PermissionError, get_accommodation_report)

	def test_pending_arrivals_and_departures_stay_in_scope(self):
		home = _residence("RPTE", "Report Pending", 2)
		other = _residence("RPTF", "Report Away", 1)
		today = frappe.utils.today()
		draft = allocate_bed(_employee("Waiting"), home["beds"][1])
		opened = check_in(allocate_bed(_employee("Arrived"), home["beds"][0])["name"], today)
		hidden = check_in(allocate_bed(_employee("Away"), other["beds"][0])["name"], today)
		report = get_accommodation_report(property=home["property"])
		self.assertEqual(
			report["occupied"] + report["available"] + report["maintenance"],
			report["total"],
		)
		self.assertEqual(_names(report["pending"]), {draft["name"]})
		self.assertEqual(len(report["pending"]), 1)
		self.assertNotIn(opened["name"], _names(report["pending"]))
		self.assertEqual(_names(report["arrivals"]), {opened["name"]})
		self.assertEqual(len(report["arrivals"]), report["check_ins_today"])
		self.assertEqual(report["departures"], [])
		self.assertEqual(report["check_outs_today"], 0)
		self.assertNotIn(hidden["name"], _names(report["arrivals"]))
		self.assertNotIn(hidden["name"], _names(report["pending"]))
		check_out(opened["name"], today)
		report = get_accommodation_report(property=home["property"])
		self.assertEqual(_names(report["departures"]), {opened["name"]})
		self.assertEqual(len(report["departures"]), report["check_outs_today"])
		self.assertEqual(report["check_outs_today"], 1)
		self.assertNotIn(opened["name"], _names(report["assignments"]))
		self.assertEqual(_names(report["pending"]), {draft["name"]})
		self.assertNotIn(hidden["name"], _names(report["departures"]))
		manager = _user("report-pending@hotlync.local", "Accommodation Manager")
		_assign(manager, home["property"])
		frappe.set_user(manager)
		scoped = get_accommodation_report()
		self.assertEqual(_names(scoped["pending"]), {draft["name"]})
		self.assertNotIn(hidden["name"], _names(scoped["arrivals"]))
		self.assertNotIn(hidden["name"], _names(scoped["departures"]))
		with self.assertRaises(frappe.PermissionError) as caught:
			get_accommodation_report(property=other["property"])
		self.assertEqual(str(caught.exception), "Not permitted")
		with self.assertRaises(frappe.PermissionError) as missing:
			get_accommodation_report(property="MISSING-REPORT")
		self.assertEqual(str(missing.exception), "Not permitted")
		frappe.set_user("Administrator")
		blank = get_accommodation_report(property="MISSING-REPORT")
		self.assertEqual(blank["total"], 0)
		self.assertEqual(blank["pending"], [])
		self.assertEqual(blank["arrivals"], [])
		self.assertEqual(blank["departures"], [])
		if frappe.db.exists("User", "staff@hotlync.local"):
			frappe.set_user("staff@hotlync.local")
			self.assertRaises(frappe.PermissionError, get_accommodation_report)


def _same_counts(test, report, counts):
	for key in ("total", "occupied", "available", "maintenance"):
		test.assertEqual(report[key], counts[key])
	test.assertEqual(
		report["occupied"] + report["available"] + report["maintenance"],
		report["total"],
	)


def _names(rows):
	return {row["name"] for row in rows}


def _one(rows, name):
	for row in rows:
		if row["name"] == name:
			return row
	raise AssertionError(name)


def _residence(code, property_name, bed_count):
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
			"room_type": "Shared",
			"capacity": bed_count,
			"status": "Available",
		}
	).insert(ignore_permissions=True)
	beds = []
	for number in range(bed_count):
		bed = frappe.get_doc(
			{
				"doctype": "Bed",
				"room": room.name,
				"bed_number": chr(ord("A") + number),
				"status": "Available",
			}
		).insert(ignore_permissions=True)
		beds.append(bed.name)
	return {"property": property_doc.name, "building": building.name, "beds": beds}


def _employee(last_name):
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Report",
			"last_name": last_name,
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
			"first_name": "Report",
			"last_name": "Manager",
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
