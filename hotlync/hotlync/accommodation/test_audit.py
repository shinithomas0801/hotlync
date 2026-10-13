import json

import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import allocate_bed, check_in, check_out, transfer_stay


class TestStayAudit(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_audit")

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_audit")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_stay_history_names_the_actor(self):
		manager = _user("audit-manager@hotlync.local", "Accommodation Manager")
		beds = _free_beds("SRA", 2)
		if len(beds) < 2:
			self.skipTest("Need two free beds")
		source, dest = beds
		_assign(manager, "SRA")
		employee = _employee()
		frappe.set_user(manager)
		draft = allocate_bed(employee, source)
		stored = frappe.db.get_value(
			"Accommodation Allocation",
			draft["name"],
			["owner", "creation", "employee", "bed", "status"],
			as_dict=True,
		)
		self.assertEqual(stored.owner, manager)
		self.assertTrue(stored.creation)
		self.assertEqual(stored.employee, employee)
		self.assertEqual(stored.bed, source)
		self.assertEqual(stored.status, "Draft")
		check_in(draft["name"], "2026-10-01")
		self._change(draft["name"], "status", "Draft", "Checked In", manager)
		self._change(draft["name"], "check_in_date", None, "2026-10-01", manager)
		self.assertEqual(
			frappe.db.get_value("Accommodation Allocation", draft["name"], "modified_by"),
			manager,
		)
		moved = transfer_stay(draft["name"], dest, reason="Room change")
		self._change(draft["name"], "status", "Checked In", "Transferred", manager)
		self.assertEqual(moved["previous"]["bed"], source)
		self.assertEqual(moved["previous"]["employee"], employee)
		self.assertEqual(moved["previous"]["reason"], "Room change")
		current = moved["current"]["name"]
		self.assertNotEqual(current, draft["name"])
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", current, "owner"), manager)
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", current, "bed"), dest)
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", current, "employee"), employee)
		check_out(current, "2026-10-11")
		self._change(current, "status", "Checked In", "Completed", manager)
		self._change(current, "check_out_date", None, "2026-10-11", manager)
		self.assertEqual(frappe.db.get_value("Accommodation Allocation", current, "modified_by"), manager)
		for name in (draft["name"], current):
			for row in _versions(name):
				text = (row.data or "").lower()
				self.assertNotIn("password", text)
				self.assertNotIn("csrf", text)
				self.assertNotIn("api_secret", text)

	def test_rejected_allocation_is_not_stored(self):
		bed = _free("SRA")
		if not bed:
			self.skipTest("No free bed")
		frappe.db.set_value("Bed", bed, "status", "Maintenance")
		before = set(_allocation_names())
		with self.assertRaises(frappe.ValidationError):
			allocate_bed(_employee(), bed)
		self.assertEqual(set(_allocation_names()), before)
		self.assertEqual(frappe.db.get_value("Bed", bed, "status"), "Maintenance")

	def _change(self, name, field, old, new, user):
		for row in _versions(name):
			if row.owner != user or not row.creation:
				continue
			for change in json.loads(row.data).get("changed") or []:
				if change[0] != field:
					continue
				if str(change[2] or "") != str(new or ""):
					continue
				if old is None or str(change[1] or "") in ("", str(old)):
					return
		self.fail(field + " was not recorded for " + name)


def _versions(name):
	return frappe.get_all(
		"Version",
		filters={"ref_doctype": "Accommodation Allocation", "docname": name},
		fields=["owner", "creation", "data"],
	)


def _allocation_names():
	return frappe.get_all("Accommodation Allocation", pluck="name", limit=500)


def _free(property_name):
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
			"first_name": "Audit",
			"last_name": "Stay",
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
			"first_name": "Audit",
			"last_name": "Stay",
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
