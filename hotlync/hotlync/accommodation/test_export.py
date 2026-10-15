import json
import os

import frappe
from frappe.core.doctype.data_export.exporter import export_data
from frappe.desk.reportview import export_query
from frappe.tests import IntegrationTestCase

from hotlync.api import allocate_bed, check_in
import hotlync.hooks as hooks


class TestExport(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_export")
		self.home = _residence("EXPA", "Export Home")
		self.other = _residence("EXPB", "Export Other")
		self.home_stay = check_in(
			allocate_bed(_employee("Home"), self.home["beds"][0])["name"],
			frappe.utils.today(),
		)["name"]
		self.other_stay = check_in(
			allocate_bed(_employee("Other"), self.other["beds"][0])["name"],
			frappe.utils.today(),
		)["name"]
		self.manager = _user("export-manager@hotlync.local", "Accommodation Manager")
		self.outsider = _user("export-outsider@hotlync.local", "Accommodation Manager")
		self.staff = _user("export-staff@hotlync.local", "Staff")
		self.admin = _user("export-admin@hotlync.local", "Accommodation Admin")
		_assign(self.manager, self.home["property"])
		_assign(self.outsider, self.other["property"])

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_export")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_a_manager_export_stays_inside_the_assigned_residence(self):
		text = _desk_export(self.manager)
		self.assertIn(self.home_stay, text)
		self.assertNotIn(self.other_stay, text)
		self.assertNotIn(self.other["property"], text)
		_assert_no_secrets(self, text)
		self.assertTrue(
			frappe.db.exists(
				"Access Log",
				{
					"user": self.manager,
					"export_from": "Accommodation Allocation",
					"file_type": "CSV",
				},
			)
		)
		picked = _desk_export(
			self.manager,
			selected_items=json.dumps([self.home_stay, self.other_stay]),
		)
		self.assertIn(self.home_stay, picked)
		self.assertNotIn(self.other_stay, picked)
		named = _desk_export(
			self.manager,
			visible_names=json.dumps([self.other_stay, self.home_stay]),
		)
		self.assertIn(self.home_stay, named)
		self.assertNotIn(self.other_stay, named)
		filtered = _desk_export(
			self.manager,
			filters={"property": self.other["property"]},
		)
		self.assertNotIn(self.home_stay, filtered)
		self.assertNotIn(self.other_stay, filtered)
		direct = _data_export(
			self.manager,
			filters={"name": ["in", [self.home_stay, self.other_stay]]},
		)
		self.assertIn(self.home_stay, direct)
		self.assertNotIn(self.other_stay, direct)
		_assert_no_secrets(self, direct)
		group = _desk_export(self.admin)
		self.assertIn(self.home_stay, group)
		self.assertIn(self.other_stay, group)

	def test_unauthorized_export_calls_fail_without_a_file(self):
		before = _file_names()
		with self.assertRaises(frappe.PermissionError) as staff_call:
			_desk_export(self.staff)
		self.assertIn("not allowed to export", str(staff_call.exception).lower())
		self.assertFalse(frappe.response.get("filecontent"))
		self.assertTrue(
			frappe.db.exists(
				"Access Log",
				{"user": self.staff, "export_from": "Accommodation Allocation"},
			)
		)
		with self.assertRaises(frappe.PermissionError):
			_desk_export("Guest")
		self.assertFalse(frappe.response.get("filecontent"))
		for doctype in (
			"Accommodation Request",
			"Maintenance Ticket",
			"Accommodation Key",
			"User",
		):
			with self.assertRaises(frappe.PermissionError):
				_desk_export(self.manager, doctype=doctype, fields=("name",))
			self.assertFalse(frappe.response.get("filecontent"))
			with self.assertRaises(frappe.PermissionError):
				_data_export(self.manager, doctype=doctype)
		with self.assertRaises(frappe.DataError) as secret_field:
			_desk_export(self.manager, fields=("name", "password"))
		self.assertIn("password", str(secret_field.exception).lower())
		self.assertFalse(frappe.response.get("filecontent"))
		self.assertEqual(_file_names(), before)

	def test_an_unknown_doctype_export_does_not_write_a_file(self):
		before = _file_names()
		with self.assertRaises(frappe.DoesNotExistError):
			_desk_export(self.manager, doctype="Missing Export")
		self.assertFalse(frappe.response.get("filecontent"))
		self.assertEqual(_file_names(), before)

	def test_a_background_export_fails_closed_without_email(self):
		before = _file_names()
		queued = frappe.db.count("Email Queue")
		frappe.set_user(self.manager)
		frappe.local.form_dict = frappe._dict(
			doctype="Accommodation Allocation",
			file_format_type="CSV",
			fields=("name", "property", "status"),
			export_in_background=1,
		)
		frappe.response.pop("filecontent", None)
		with self.assertRaises(frappe.OutgoingEmailError) as caught:
			export_query()
		self.assertIn("outgoing Email Account", str(caught.exception))
		self.assertFalse(frappe.response.get("filecontent"))
		self.assertEqual(frappe.db.count("Email Queue"), queued)
		self.assertTrue(
			frappe.db.exists(
				"Access Log",
				{
					"user": self.manager,
					"export_from": "Accommodation Allocation",
					"file_type": "CSV",
				},
			)
		)
		created = [
			name
			for name in _file_names() - before
			if not frappe.db.get_value("File", name, "is_folder")
		]
		self.assertEqual(len(created), 1)
		for file_name in created:
			stored = frappe.get_doc("File", file_name)
			self.assertEqual(stored.is_private, 1)
			self.assertEqual(stored.owner, self.manager)
			self.assertTrue((stored.file_url or "").startswith("/private/"))
			content = stored.get_content()
			if isinstance(content, bytes):
				content = content.decode("utf-8")
			self.assertIn(self.home_stay, content)
			self.assertNotIn(self.other_stay, content)
			_assert_no_secrets(self, content)
			for user in (self.staff, self.outsider, "Guest"):
				frappe.set_user(user)
				with self.assertRaises(frappe.PermissionError):
					frappe.get_doc("File", file_name, check_permission=True)
			path = stored.get_full_path()
			if path and os.path.exists(path):
				os.remove(path)

	def test_the_app_adds_no_export_endpoint_or_retention_job(self):
		self.assertFalse(getattr(hooks, "scheduler_events", None))
		from hotlync import api

		names = [
			name
			for name in dir(api)
			if "export" in name.lower() or "retention" in name.lower()
		]
		self.assertEqual(names, [])


def _desk_export(user, **overrides):
	frappe.set_user(user)
	params = {
		"doctype": "Accommodation Allocation",
		"file_format_type": "CSV",
		"fields": ("name", "property", "status"),
	}
	params.update(overrides)
	frappe.local.form_dict = frappe._dict(params)
	frappe.response.pop("filecontent", None)
	frappe.response.pop("filename", None)
	export_query()
	content = frappe.response.get("filecontent") or b""
	if isinstance(content, bytes):
		return content.decode("utf-8")
	return str(content)


def _data_export(user, **overrides):
	frappe.set_user(user)
	params = {
		"doctype": "Accommodation Allocation",
		"with_data": True,
		"all_doctypes": False,
		"file_type": "CSV",
	}
	params.update(overrides)
	frappe.response.pop("result", None)
	frappe.response.pop("filecontent", None)
	export_data(**params)
	return frappe.response.get("result") or ""


def _assert_no_secrets(test, text):
	lowered = text.lower()
	for secret in ("password", "new_password", "pbkdf2", "sha256", "csrf"):
		test.assertNotIn(secret, lowered)


def _file_names():
	return set(frappe.get_all("File", pluck="name"))


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
			"room_type": "Shared",
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
	return {"property": property_doc.name, "beds": [bed.name]}


def _employee(last_name):
	company = frappe.db.get_value("Company", {}, "name")
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Export",
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
			"first_name": "Export",
			"last_name": "User",
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
