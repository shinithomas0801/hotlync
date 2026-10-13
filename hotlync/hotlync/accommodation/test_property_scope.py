import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from hotlync.accommodation.workflow import location_for_bed
from hotlync.api import (
	allocate_bed,
	check_in,
	check_out,
	get_accommodation,
	get_allocations,
	get_available_beds,
	get_dashboard,
	transfer_stay,
)


class TestPropertyScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.home, cls.home_bed = _residence("TSTA", "Scope Home")
		cls.other, cls.other_bed = _residence("TSTB", "Scope Other")
		cls.manager = _user("scope-manager@hotlync.local", "Accommodation Manager")
		cls.employee = _employee()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_scope")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_scope")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_staff_cannot_call_a_manager_method(self):
		self._require_user("staff@hotlync.local")
		frappe.set_user("staff@hotlync.local")
		self.assertRaises(frappe.PermissionError, get_dashboard)

	def test_staff_cannot_open_another_employees_stay(self):
		self._require_user("staff@hotlync.local")
		john = frappe.db.get_value("Employee", {"user_id": "staff@hotlync.local"}, "name")
		if not john:
			self.skipTest("Staff login is not linked to an employee")
		others = frappe.get_all(
			"Accommodation Allocation",
			filters={"employee": ["!=", john]},
			pluck="name",
			limit=1,
		)
		if not others:
			self.skipTest("No other stay exists to reject")
		frappe.set_user("staff@hotlync.local")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				"Accommodation Allocation",
				others[0],
				check_permission=True,
			)

	def test_unassigned_manager_sees_no_properties(self):
		frappe.set_user(self.manager)
		self.assertEqual(frappe.get_list("Property", pluck="name"), [])
		self.assertRaises(frappe.PermissionError, lambda: get_dashboard(property=self.home))

	def test_assigned_manager_cannot_open_the_other_property(self):
		self._assign(self.manager, self.home)
		frappe.set_user(self.manager)
		self.assertEqual(frappe.get_list("Property", pluck="name"), [self.home])
		counts = get_dashboard(property=self.home)
		self.assertEqual(counts["total"], 1)
		self.assertEqual(counts["available"], 1)
		self.assertEqual(frappe.get_list("Bed", pluck="name"), [self.home_bed])
		available = {row.name for row in get_available_beds()}
		self.assertIn(self.home_bed, available)
		self.assertNotIn(self.other_bed, available)
		self.assertRaises(frappe.PermissionError, lambda: get_dashboard(property=self.other))
		self.assertRaises(
			frappe.PermissionError,
			lambda: get_allocations(property=self.other),
		)
		self.assertRaises(
			frappe.PermissionError,
			lambda: allocate_bed(self.employee, self.other_bed),
		)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Property", self.other, check_permission=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Bed", self.other_bed, check_permission=True)

	def test_staff_reads_only_their_own_stay(self):
		self._require_user("staff@hotlync.local")
		john = frappe.db.get_value("Employee", {"user_id": "staff@hotlync.local"}, "name")
		if not john:
			self.skipTest("Staff login is not linked to an employee")
		own = frappe.get_all(
			"Accommodation Allocation",
			filters={"employee": john},
			pluck="name",
			limit=1,
		)
		if not own:
			own = [_allocation(john, self.home_bed, "Checked In")]
		foreign = _allocation(self.employee, self.other_bed, "Checked In")
		frappe.set_user("staff@hotlync.local")
		self.assertEqual(
			frappe.get_list(
				"Accommodation Allocation",
				filters={"name": own[0]},
				pluck="name",
			),
			[own[0]],
		)
		self.assertEqual(
			frappe.get_list(
				"Accommodation Allocation",
				filters={"name": foreign},
				pluck="name",
			),
			[],
		)
		opened = frappe.get_doc(
			"Accommodation Allocation",
			own[0],
			check_permission=True,
		)
		self.assertEqual(opened.employee, john)
		with self.assertRaises(frappe.PermissionError) as caught:
			frappe.get_doc(
				"Accommodation Allocation",
				foreign,
				check_permission=True,
			)
		self.assertNotIn(self.other, str(caught.exception))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Property")

	def test_staff_cannot_modify_allocations(self):
		self._require_user("staff@hotlync.local")
		john = frappe.db.get_value("Employee", {"user_id": "staff@hotlync.local"}, "name")
		if not john:
			self.skipTest("Staff login is not linked to an employee")
		foreign = _allocation(self.employee, self.other_bed, "Checked In")
		before = frappe.db.count("Accommodation Allocation")
		bed_status = frappe.db.get_value("Bed", self.other_bed, "status")
		frappe.set_user("staff@hotlync.local")
		attempts = (
			lambda: allocate_bed(john, self.home_bed),
			lambda: allocate_bed(self.employee, self.other_bed),
			lambda: check_in(foreign),
			lambda: transfer_stay(foreign, self.home_bed),
			lambda: check_out(foreign),
		)
		for attempt in attempts:
			with self.assertRaises(frappe.PermissionError) as caught:
				attempt()
			message = str(caught.exception)
			self.assertNotIn(self.other, message)
			self.assertNotIn(self.other_bed, message)
		loaded = frappe.get_doc("Accommodation Allocation", foreign)
		with self.assertRaises(frappe.PermissionError):
			loaded.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", self.other_bed, "status"), bed_status)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", foreign, "status"),
			"Checked In",
		)

	def test_unassigned_manager_cannot_open_records_by_id(self):
		room, floor, building = _parents(self.home_bed)
		other_room, other_floor, other_building = _parents(self.other_bed)
		stay = _allocation(self.employee, self.other_bed, "Checked In")
		frappe.set_user(self.manager)
		for doctype in ("Property", "Building", "Floor", "Room", "Bed", "Accommodation Allocation"):
			self.assertEqual(frappe.get_list(doctype, pluck="name"), [])
		denied = (
			("Property", self.home),
			("Property", self.other),
			("Building", building),
			("Building", other_building),
			("Floor", floor),
			("Floor", other_floor),
			("Room", room),
			("Room", other_room),
			("Bed", self.home_bed),
			("Bed", self.other_bed),
			("Accommodation Allocation", stay),
		)
		for doctype, name in denied:
			with self.assertRaises(frappe.PermissionError) as caught:
				frappe.get_doc(doctype, name, check_permission=True)
			self.assertNotIn("Scope Home", str(caught.exception))
			self.assertNotIn("Scope Other", str(caught.exception))
		self.assertEqual(get_accommodation(), [])
		self.assertEqual(get_allocations(), [])
		self.assertEqual(get_available_beds(), [])
		self.assertEqual(
			get_dashboard(),
			{"total": 0, "occupied": 0, "available": 0, "maintenance": 0},
		)
		for property_name in (self.home, self.other, "NO-SUCH-PROPERTY"):
			with self.assertRaises(frappe.PermissionError) as caught:
				get_dashboard(property=property_name)
			self.assertEqual(str(caught.exception), "Not permitted")

	def test_assigned_manager_cannot_transfer_across_properties(self):
		self._assign(self.manager, self.home)
		stay = _allocation(self.employee, self.home_bed, "Checked In")
		before = frappe.db.count("Accommodation Allocation")
		room, floor, building = _parents(self.home_bed)
		other_room, _, other_building = _parents(self.other_bed)
		frappe.set_user(self.manager)
		self.assertEqual(frappe.get_list("Building", pluck="name"), [building])
		self.assertEqual(frappe.get_list("Floor", pluck="name"), [floor])
		self.assertEqual(frappe.get_list("Room", pluck="name"), [room])
		self.assertEqual([row.name for row in get_accommodation()], [self.home])
		self.assertEqual(get_dashboard()["total"], 1)
		with self.assertRaises(frappe.PermissionError):
			get_accommodation(property=self.other)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Room", other_room, check_permission=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Building", other_building, check_permission=True)
		with self.assertRaises(frappe.PermissionError) as caught:
			transfer_stay(stay, self.other_bed, reason="cross property")
		self.assertEqual(str(caught.exception), "Not permitted")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{
					"doctype": "Property Assignment",
					"user": self.manager,
					"property": self.other,
				}
			).insert()
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", stay, "status"),
			"Checked In",
		)
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", self.home_bed, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", self.other_bed, "status"), "Available")

	def test_duplicate_stay_leaves_the_first_allocation(self):
		self._assign(self.manager, self.home)
		second_bed = _extra_bed(self.home_bed, "B")
		frappe.set_user(self.manager)
		first = allocate_bed(self.employee, self.home_bed)
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			allocate_bed(self.employee, second_bed)
		self.assertIn("already has an active allocation", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", first["name"], "status"),
			"Draft",
		)
		self.assertFalse(
			frappe.db.exists("Accommodation Allocation", {"bed": second_bed})
		)

	def test_failed_transfer_rolls_back_with_the_request(self):
		self._assign(self.manager, self.home)
		stay = _allocation(self.employee, self.home_bed, "Checked In")
		second_bed = _extra_bed(self.home_bed, "B")
		frappe.set_user(self.manager)
		frappe.db.savepoint("request")
		original_insert = Document.insert

		def fail_new_stay(doc, *args, **kwargs):
			if doc.doctype == "Accommodation Allocation" and doc.name != stay:
				raise frappe.DuplicateEntryError(
					"Accommodation Allocation",
					"forced",
					Exception("forced"),
				)
			return original_insert(doc, *args, **kwargs)

		Document.insert = fail_new_stay
		try:
			with self.assertRaises(frappe.ValidationError) as caught:
				transfer_stay(stay, second_bed, reason="forced failure")
			self.assertIn("already has an active allocation", str(caught.exception))
		finally:
			Document.insert = original_insert
		frappe.db.rollback(save_point="request")
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", stay, "status"),
			"Checked In",
		)
		self.assertFalse(
			frappe.db.exists("Accommodation Allocation", {"bed": second_bed})
		)
		self.assertEqual(frappe.db.get_value("Bed", self.home_bed, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", second_bed, "status"), "Available")

	def test_admin_can_see_both_residences_and_assign_a_manager(self):
		self._require_user("admin@hotlync.local")
		frappe.set_user("admin@hotlync.local")
		names = {row.name for row in get_accommodation()}
		self.assertIn(self.home, names)
		self.assertIn(self.other, names)
		self.assertEqual(get_dashboard(property=self.other)["total"], 1)
		self.assertEqual(get_dashboard(property="NO-SUCH-PROPERTY")["total"], 0)
		assignment = frappe.get_doc(
			{
				"doctype": "Property Assignment",
				"user": self.manager,
				"property": self.home,
			}
		).insert()
		self.assertTrue(assignment.name)
		frappe.set_user(self.manager)
		self.assertEqual(frappe.get_list("Property", pluck="name"), [self.home])

	def test_dashboard_counts_match_authorized_beds(self):
		self._require_user("admin@hotlync.local")
		self._assign(self.manager, self.home)
		maintenance = _extra_bed(self.home_bed, "B")
		frappe.db.set_value("Bed", maintenance, "status", "Maintenance")
		occupied_bed = _extra_bed(self.home_bed, "C")
		_allocation(self.employee, occupied_bed, "Checked In")
		draft_bed = _extra_bed(self.home_bed, "D")
		_allocation(_employee(), draft_bed, "Draft")
		_allocation(_employee(), self.other_bed, "Checked In")
		self.assertEqual(frappe.db.get_value("Bed", occupied_bed, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", draft_bed, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", self.home_bed, "status"), "Available")
		expected = _status_counts(
			[self.home_bed, maintenance, occupied_bed, draft_bed]
		)
		self.assertEqual(
			expected["occupied"] + expected["available"] + expected["maintenance"],
			expected["total"],
		)

		frappe.set_user(self.manager)
		visible = frappe.get_list("Bed", pluck="name")
		self.assertEqual(sorted(visible), sorted(expected["beds"]))
		self.assertEqual(get_dashboard(), _without_beds(expected))
		self.assertEqual(get_dashboard(property=self.home), _without_beds(expected))
		self.assertNotIn(self.other_bed, visible)
		for property_name in (self.other, "NO-SUCH-PROPERTY"):
			with self.assertRaises(frappe.PermissionError) as caught:
				get_dashboard(property=property_name)
			self.assertEqual(str(caught.exception), "Not permitted")
		allocations = get_allocations()
		self.assertEqual(
			sorted(row.bed for row in allocations),
			sorted([occupied_bed, draft_bed]),
		)
		tree = get_accommodation()
		self.assertEqual([row.name for row in tree], [self.home])
		self.assertEqual(sorted(_beds_in_tree(tree)), sorted(visible))

		frappe.set_user("admin@hotlync.local")
		self.assertEqual(
			set(get_dashboard().keys()),
			{"total", "occupied", "available", "maintenance"},
		)
		self.assertEqual(get_dashboard()["total"], frappe.db.count("Bed"))
		self.assertEqual(get_dashboard(property=self.home), _without_beds(expected))
		self.assertEqual(
			get_dashboard(property=self.other),
			{"total": 1, "occupied": 1, "available": 0, "maintenance": 0},
		)
		self.assertEqual(
			get_dashboard(property="NO-SUCH-PROPERTY"),
			{"total": 0, "occupied": 0, "available": 0, "maintenance": 0},
		)

	def test_cross_property_denial_does_not_reveal_state(self):
		self._assign(self.manager, self.home)
		maintenance = _extra_bed(self.other_bed, "M")
		frappe.db.set_value("Bed", maintenance, "status", "Maintenance")
		other_room = frappe.db.get_value("Bed", self.other_bed, "room")
		foreign_bed = _extra_bed(self.other_bed, "C")
		draft = _allocation(_employee(), self.other_bed, "Draft")
		foreign_stay = _allocation(_employee(), foreign_bed, "Checked In")
		stay = _allocation(self.employee, self.home_bed, "Checked In")
		before = frappe.db.count("Accommodation Allocation")
		frappe.set_user(self.manager)
		attempts = (
			lambda: allocate_bed(self.employee, maintenance),
			lambda: check_in(foreign_stay),
			lambda: check_out(draft),
			lambda: transfer_stay(draft, self.home_bed),
			lambda: transfer_stay(stay, maintenance),
			lambda: get_available_beds(other_room),
		)
		for attempt in attempts:
			with self.assertRaises(frappe.PermissionError) as caught:
				attempt()
			self.assertEqual(str(caught.exception), "Not permitted")
		loaded = frappe.get_doc("Bed", maintenance)
		with self.assertRaises(frappe.PermissionError):
			loaded.save()
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{
					"doctype": "Building",
					"code": "LEAK",
					"building_name": "Leak",
					"property": self.other,
					"number_of_floors": 1,
					"status": "Active",
				}
			).insert()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", maintenance, "status"), "Maintenance")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", draft, "status"), "Draft")
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", foreign_stay, "status"),
			"Checked In",
		)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", stay, "status"),
			"Checked In",
		)
		self.assertFalse(frappe.db.exists("Building", "LEAK"))

	def test_admin_counts_match_bed_rows(self):
		self._require_user("admin@hotlync.local")
		frappe.set_user("admin@hotlync.local")
		names = set(frappe.get_list("Property", pluck="name"))
		self.assertIn(self.home, names)
		self.assertIn(self.other, names)
		counts = get_dashboard()
		self.assertEqual(counts["total"], frappe.db.count("Bed"))
		home = get_dashboard(property=self.home)
		self.assertEqual(home["total"], 1)

	def _assign(self, user, property_name):
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "Property Assignment",
				"user": user,
				"property": property_name,
			}
		).insert(ignore_permissions=True)

	def _require_user(self, email):
		if not frappe.db.exists("User", email):
			self.skipTest(email + " is not on this site")


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


def _user(email, role):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Scope",
			"last_name": "Manager",
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	).insert(ignore_permissions=True)
	user.add_roles(role)
	return user.name


def _employee():
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Scope",
			"last_name": "Tester",
			"gender": "Male",
			"date_of_birth": "1995-01-01",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
		}
	).insert(ignore_permissions=True)
	return employee.name


def _status_counts(beds):
	counts = {
		"total": 0,
		"occupied": 0,
		"available": 0,
		"maintenance": 0,
		"beds": list(beds),
	}
	labels = {
		"Occupied": "occupied",
		"Available": "available",
		"Maintenance": "maintenance",
	}
	for bed in beds:
		counts["total"] += 1
		label = labels.get(frappe.db.get_value("Bed", bed, "status"))
		if label:
			counts[label] += 1
	return counts


def _without_beds(counts):
	return {key: value for key, value in counts.items() if key != "beds"}


def _beds_in_tree(properties):
	names = []
	for property_doc in properties:
		for building in property_doc["buildings"]:
			for floor in building["floors"]:
				for room in floor["rooms"]:
					names.extend(bed["name"] for bed in room["beds"])
	return names


def _parents(bed):
	room = frappe.db.get_value("Bed", bed, "room")
	floor, building = frappe.db.get_value("Room", room, ["floor", "building"])
	return room, floor, building


def _extra_bed(bed, bed_number):
	frappe.set_user("Administrator")
	room = frappe.db.get_value("Bed", bed, "room")
	doc = frappe.get_doc(
		{
			"doctype": "Bed",
			"room": room,
			"bed_number": bed_number,
			"status": "Available",
		}
	).insert(ignore_permissions=True)
	return doc.name


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
