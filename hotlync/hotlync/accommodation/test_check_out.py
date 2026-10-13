import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import allocate_bed, check_in, check_out, transfer_stay


class TestCheckOut(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_checkout")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_checkout")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_check_out_completes_once(self):
		manager = _user("checkout-manager@hotlync.local", "Accommodation Manager")
		bed, untouched = _two_beds(self, "SRA")
		_assign(manager, "SRA")
		employee = _employee()
		stay = _checked_in(employee, bed)
		recorded = frappe.db.get_value(
			"Accommodation Allocation",
			stay,
			["property", "building", "room", "bed", "employee", "check_in_date"],
			as_dict=True,
		)
		before = frappe.db.count("Accommodation Allocation")
		frappe.set_user(manager)
		finished = check_out(stay, "2026-10-11")
		self.assertEqual(finished["status"], "Completed")
		self.assertEqual(str(finished["check_out_date"]), "2026-10-11")
		self.assertEqual(str(finished["check_in_date"]), "2026-10-01")
		self.assertEqual(finished["employee"], employee)
		self.assertEqual(finished["bed"], bed)
		self.assertEqual(finished["property"], recorded.property)
		self.assertEqual(finished["building"], recorded.building)
		self.assertEqual(finished["room"], recorded.room)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", untouched, "status"), "Available")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", stay, "modified_by"),
			manager,
		)
		self.assertFalse(frappe.db.get_value("Accommodation Allocation", stay, "active_bed"))
		self.assertFalse(frappe.db.get_value("Accommodation Allocation", stay, "active_employee"))
		frappe.set_user("Administrator")
		opened = frappe.get_doc("Accommodation Allocation", stay)
		opened.check_permission("read")
		self.assertEqual(opened.status, "Completed")
		self.assertEqual(opened.employee, recorded.employee)
		with self.assertRaises(frappe.ValidationError) as caught:
			frappe.set_user(manager)
			check_out(stay, "2026-10-12")
		self.assertIn("Only a checked-in stay can be checked out", str(caught.exception))
		self.assertEqual(
			str(frappe.db.get_value("Accommodation Allocation", stay, "check_out_date")),
			"2026-10-11",
		)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)

	def test_other_statuses_cannot_be_checked_out(self):
		beds = _free_beds("SRA", 3)
		if len(beds) < 3:
			self.skipTest("Need three free beds")
		draft_bed, source, dest = beds
		draft = allocate_bed(_employee(), draft_bed)
		with self.assertRaises(frappe.ValidationError) as caught:
			check_out(draft["name"])
		self.assertIn("Only a checked-in stay can be checked out", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", draft["name"], "status"), "Draft")
		self.assertFalse(frappe.db.get_value("Accommodation Allocation", draft["name"], "check_out_date"))
		self.assertEqual(frappe.db.get_value("Bed", draft_bed, "status"), "Available")

		moved = transfer_stay(_checked_in(_employee(), source), dest, reason="Room change")
		with self.assertRaises(frappe.ValidationError) as caught:
			check_out(moved["previous"]["name"])
		self.assertIn("Only a checked-in stay can be checked out", str(caught.exception))
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", moved["previous"]["name"], "status"),
			"Transferred",
		)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", moved["current"]["name"], "status"),
			"Checked In",
		)
		self.assertEqual(frappe.db.get_value("Bed", source, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Bed", dest, "status"), "Occupied")

		for status in ("Checked Out", "Completed"):
			bed = _free_bed("SRA")
			stay = _checked_in(_employee(), bed)
			frappe.db.set_value(
				"Accommodation Allocation",
				stay,
				{"status": status, "active_bed": None, "active_employee": None},
			)
			frappe.db.set_value("Bed", bed, "status", "Available")
			with self.assertRaises(frappe.ValidationError) as caught:
				check_out(stay)
			self.assertIn("Only a checked-in stay can be checked out", str(caught.exception))
			self.assertEqual(frappe.db.get_value("Accommodation Allocation", stay, "status"), status)
			self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Available")

	def test_failed_check_out_leaves_the_stay(self):
		before = frappe.db.count("Accommodation Allocation")
		with self.assertRaises(frappe.ValidationError) as caught:
			check_out("ACC-ALLOC-NONE")
		self.assertIn("Allocation not found", str(caught.exception))
		self.assertEqual(frappe.db.count("Accommodation Allocation"), before)

		bed = _free_bed("SRA")
		stay = _checked_in(_employee(), bed)
		frappe.db.set_value("Accommodation Allocation", stay, "bed", "NO-SUCH-BED")
		with self.assertRaises(frappe.ValidationError) as caught:
			check_out(stay)
		self.assertIn("Bed not found", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", stay, "status"), "Checked In")
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Occupied")

		mismatch = _checked_in(_employee(), _free_bed("SRA"))
		frappe.db.set_value("Accommodation Allocation", mismatch, "room", "OTHER-ROOM")
		with self.assertRaises(frappe.ValidationError) as caught:
			check_out(mismatch)
		self.assertIn("not in the recorded residence", str(caught.exception))
		self.assertNotIn("SRB", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", mismatch, "status"), "Checked In")
		self.assertFalse(frappe.db.get_value("Accommodation Allocation", mismatch, "check_out_date"))

		unlinked_bed = _free_bed("SRA")
		unlinked = _checked_in(_employee(), unlinked_bed)
		building = frappe.db.get_value("Room", frappe.db.get_value("Bed", unlinked_bed, "room"), "building")
		frappe.db.set_value("Building", building, "property", None)
		with self.assertRaises(frappe.ValidationError) as caught:
			check_out(unlinked)
		self.assertIn("not linked to a residence", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", unlinked, "status"), "Checked In")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", unlinked, "property"), "SRA")
		self.assertEqual(frappe.db.get_value("Bed", unlinked_bed, "status"), "Occupied")

	def test_unauthorized_check_out_is_rejected(self):
		staff = _user("checkout-staff@hotlync.local", "Staff")
		manager = _user("checkout-local@hotlync.local", "Accommodation Manager")
		home = _free_bed("SRA")
		other = _free_bed("SRB")
		if not home or not other:
			self.skipTest("Both residences need a free bed")
		_assign(manager, "SRA")
		own = _checked_in(_employee(), home)
		foreign = _checked_in(_employee(), other)
		frappe.set_user(staff)
		with self.assertRaises(frappe.PermissionError) as caught:
			check_out(own)
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRA", str(caught.exception))
		frappe.set_user(manager)
		with self.assertRaises(frappe.PermissionError) as caught:
			check_out(foreign)
		self.assertIn("Not permitted", str(caught.exception))
		self.assertNotIn("SRB", str(caught.exception))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", own, "status"), "Checked In")
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", foreign, "status"), "Checked In")
		self.assertEqual(frappe.db.get_value("Bed", home, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Bed", other, "status"), "Occupied")


def _checked_in(employee, bed):
	frappe.set_user("Administrator")
	draft = allocate_bed(employee, bed)
	check_in(draft["name"], "2026-10-01")
	return draft["name"]


def _two_beds(test, property_name):
	beds = _free_beds(property_name, 2)
	if len(beds) < 2:
		test.skipTest("Need two free beds")
	return beds[0], beds[1]


def _free_bed(property_name):
	beds = _free_beds(property_name, 1)
	return beds[0] if beds else None


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


def _employee():
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Check",
			"last_name": "Out",
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
			"last_name": "Out",
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
