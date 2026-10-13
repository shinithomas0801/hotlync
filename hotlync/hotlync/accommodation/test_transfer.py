import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from hotlync.api import allocate_bed, check_in, transfer_stay


class TestTransfer(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_transfer_test")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_transfer_test")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_transfer_keeps_the_old_stay(self):
		manager = _user("transfer-manager@hotlync.local", "Accommodation Manager")
		source, dest = _two_beds(self, "SRA")
		_assign(manager, "SRA")
		employee = _employee()
		draft = allocate_bed(employee, source)
		check_in(draft["name"], "2026-10-01")
		before = frappe.db.count("Accommodation Allocation")
		frappe.set_user(manager)
		moved = transfer_stay(draft["name"], dest, reason="Room change")
		self.assertEqual(moved["previous"]["status"], "Transferred")
		self.assertEqual(moved["previous"]["bed"], source)
		self.assertEqual(moved["previous"]["employee"], employee)
		self.assertEqual(str(moved["previous"]["check_in_date"]), "2026-10-01")
		self.assertEqual(moved["previous"]["reason"], "Room change")
		self.assertEqual(moved["current"]["status"], "Checked In")
		self.assertEqual(moved["current"]["bed"], dest)
		self.assertEqual(moved["current"]["employee"], employee)
		self.assertEqual(moved["current"]["property"], "SRA")
		self.assertEqual(moved["current"]["reason"], "Room change")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before + 1)
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Occupied")
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", draft["name"], "modified_by"),
			manager,
		)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", moved["current"]["name"], "owner"),
			manager,
		)
		with self.assertRaises(frappe.ValidationError) as caught:
			transfer_stay(draft["name"], dest)
		self.assertIn("Only a checked-in stay can be transferred", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			transfer_stay(moved["current"]["name"], dest)
		self.assertIn("Choose a different bed", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before + 1)
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Occupied")

	def test_failed_transfer_restores_the_source(self):
		source, dest = _two_beds(self, "SRA")
		stay = _checked_in(source)
		before = frappe.db.count("Accommodation Allocation")
		original_insert = Document.insert

		def fail_new_stay(doc, *args, **kwargs):
			if doc.doctype == "Accommodation Allocation":
				raise frappe.UniqueValidationError(
					"Accommodation Allocation",
					"forced",
					Exception("forced"),
				)
			return original_insert(doc, *args, **kwargs)

		Document.insert = fail_new_stay
		try:
			with self.assertRaises(frappe.ValidationError) as caught:
				transfer_stay(stay, dest, reason="forced failure")
			self.assertIn("already has an active allocation", str(caught.exception))
		finally:
			Document.insert = original_insert
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", stay, "status"), "Checked In")
		self.assertFalse(frappe.db.get_value("Accommodation Allocation", stay, "reason"))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Available")

	def test_rejected_transfer_leaves_the_stay(self):
		beds = _free_beds("SRA", 5)
		if len(beds) < 5:
			self.skipTest("Need five free beds in Staff Residence A")
		source, other, blocked, occupied, drafted = beds
		stay = _checked_in(source)
		frappe.db.set_value("Bed", blocked, "status", "Maintenance")
		frappe.db.set_value("Bed", occupied, "status", "Occupied")
		allocate_bed(_employee(), drafted)
		unlinked = _unlinked_bed()
		before = frappe.db.count("Accommodation Allocation")
		attempts = (
			(source, "Choose a different bed"),
			("NO-SUCH-BED", "Bed not found"),
			(blocked, "maintenance"),
			(occupied, "occupied"),
			(drafted, "already has an active allocation"),
			(unlinked, "not linked to a residence"),
		)
		for bed, message in attempts:
			with self.assertRaises(frappe.ValidationError) as caught:
				transfer_stay(stay, bed, reason="should not stick")
			self.assertIn(message, str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", stay, "status"), "Checked In")
		self.assertFalse(frappe.db.get_value("Accommodation Allocation", stay, "reason"))
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", blocked, "status"), "Maintenance")
		self.assertEqual(frappe.db.get_value("Bed", occupied, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", drafted, "status"), "Available")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		draft = allocate_bed(_employee(), other)
		with self.assertRaises(frappe.ValidationError) as caught:
			transfer_stay(draft["name"], source)
		self.assertIn("Only a checked-in stay can be transferred", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", draft["name"], "status"), "Draft")
		with self.assertRaises(frappe.ValidationError) as caught:
			transfer_stay("ACC-ALLOC-NONE", other)
		self.assertIn("Allocation not found", str(caught.exception))

	def test_source_bed_must_match_the_stay(self):
		source, dest = _two_beds(self, "SRA")
		stay = _checked_in(source)
		frappe.db.set_value("Accommodation Allocation", stay, "room", "OTHER-ROOM")
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			transfer_stay(stay, dest)
		self.assertIn("not in the recorded residence", str(caught.exception))
		self.assertNotIn("SRB", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", stay, "status"), "Checked In")
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Available")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)

	def test_unauthorized_transfer_is_rejected(self):
		staff = _user("transfer-staff@hotlync.local", "Staff")
		manager = _user("transfer-local@hotlync.local", "Accommodation Manager")
		home_beds = _free_beds("SRA", 2)
		other_beds = _free_beds("SRB", 1)
		if len(home_beds) < 2 or not other_beds:
			self.skipTest("Both residences need a free bed")
		_assign(manager, "SRA")
		home = _checked_in(home_beds[0])
		foreign = _checked_in(other_beds[0])
		frappe.set_user(staff)
		with self.assertRaises(frappe.PermissionError) as caught:
			transfer_stay(home, home_beds[1])
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRA", str(caught.exception))
		frappe.set_user(manager)
		with self.assertRaises(frappe.PermissionError) as caught:
			transfer_stay(foreign, home_beds[1])
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRB", str(caught.exception))
		with self.assertRaises(frappe.PermissionError) as caught:
			transfer_stay(home, other_beds[0])
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRB", str(caught.exception))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", home, "status"), "Checked In")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", foreign, "status"), "Checked In")
		self.assertEqual(frappe.db.get_value("Bed", home_beds[0], "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", other_beds[0], "status"), "Occupied")


def _checked_in(bed):
	draft = allocate_bed(_employee(), bed)
	check_in(draft["name"], "2026-10-01")
	return draft["name"]


def _two_beds(test, property_name):
	beds = _free_beds(property_name, 2)
	if len(beds) < 2:
		test.skipTest("Need two free beds")
	return beds[0], beds[1]


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
		""",
		property_name,
	)
	return [row[0] for row in rows if row[0] not in taken][:limit]


def _unlinked_bed():
	building = frappe.get_doc(
		{
			"doctype": "Building",
			"code": "TRN-B",
			"building_name": "Transfer building",
			"property": "SRA",
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
	frappe.db.set_value("Building", building.name, "property", None)
	return bed.name


def _employee():
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Transfer",
			"last_name": "Check",
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
			"first_name": "Transfer",
			"last_name": "Check",
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
