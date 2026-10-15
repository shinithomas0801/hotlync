import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import check_password

from hotlync.accommodation.user_access import SAMS_ROLES
from hotlync.api import (
	assign_user_property,
	create_user_access,
	get_user_access,
	revoke_user_property,
	set_user_enabled,
	set_user_role,
)

PASSWORD = "Access@12345"


class TestUserAccess(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_access")
		self.home = _property("UACC", "Access Residence")
		self.other = _property("UACD", "Access Other")
		self.admin = _user("access-admin@hotlync.local", "Accommodation Admin")
		self.staff = _user("access-staff@hotlync.local", "Staff")
		self.unassigned = _user("access-open@hotlync.local", "Accommodation Manager")
		self.assigned = _user("access-bound@hotlync.local", "Accommodation Manager")
		_assign(self.assigned, self.home)

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_access")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_staff_cannot_manage_access(self):
		self._assert_denied(self.staff)

	def test_unassigned_manager_cannot_manage_access(self):
		self._assert_denied(self.unassigned)

	def test_assigned_manager_cannot_manage_access(self):
		self._assert_denied(self.assigned)

	def test_admin_creates_assigns_and_toggles_a_login(self):
		stays = frappe.db.count("Accommodation Allocation")
		queued = frappe.db.count("Email Queue")
		frappe.set_user(self.admin)
		created = create_user_access(
			email="access-new@hotlync.local",
			first_name="Access",
			last_name="New",
			role="Staff",
			password=PASSWORD,
		)
		self.assertEqual(created["name"], "access-new@hotlync.local")
		self.assertEqual(created["enabled"], 1)
		self.assertEqual(created["roles"], ["Staff"])
		self.assertNotIn("System Manager", frappe.get_roles(created["name"]))
		self.assertNotIn(PASSWORD, str(created))
		self.assertEqual(
			frappe.db.get_value("User", created["name"], "send_welcome_email"),
			0,
		)
		self.assertEqual(check_password(created["name"], PASSWORD), created["name"])
		self.assertEqual(frappe.db.count("Email Queue"), queued)
		self.assertEqual(frappe.db.count("Accommodation Allocation"), stays)
		listed = {row["name"]: row for row in get_user_access()["users"]}
		self.assertIn(created["name"], listed)
		changed = set_user_role(created["name"], "Accommodation Manager")
		self.assertEqual(changed["roles"], ["Accommodation Manager"])
		self.assertNotIn(PASSWORD, json.dumps(changed))
		role_version = _version_text("User", created["name"], self.admin)
		self.assertNotIn(PASSWORD, role_version)
		self.assertNotIn("new_password", role_version)
		self.assertNotIn("pbkdf2", role_version.lower())
		self.assertNotIn("sha256", role_version.lower())
		assigned = assign_user_property(created["name"], self.home)
		self.assertEqual(len(assigned["user"]["properties"]), 1)
		second = assign_user_property(created["name"], self.other)
		self.assertEqual(len(second["user"]["properties"]), 2)
		revoked = revoke_user_property(assigned["assignment"])
		left = {row["property"] for row in revoked["properties"]}
		self.assertEqual(left, {self.other})
		off = set_user_enabled(created["name"], 0)
		self.assertEqual(off["enabled"], 0)
		self.assertEqual(frappe.db.get_value("User", created["name"], "enabled"), 0)
		self.assertNotIn(PASSWORD, json.dumps(off))
		enabled_version = _version_text("User", created["name"], self.admin)
		self.assertNotIn(PASSWORD, enabled_version)
		self.assertNotIn("new_password", enabled_version)
		self.assertNotIn("pbkdf2", enabled_version.lower())
		self.assertNotIn("sha256", enabled_version.lower())
		on = set_user_enabled(created["name"], 1)
		self.assertEqual(on["enabled"], 1)

	def test_a_duplicate_assignment_is_rejected(self):
		frappe.set_user(self.admin)
		created = create_user_access(
			email="access-dup@hotlync.local",
			first_name="Access",
			role="Accommodation Manager",
			password=PASSWORD,
		)
		assign_user_property(created["name"], self.home)
		with self.assertRaises(frappe.ValidationError) as caught:
			assign_user_property(created["name"], self.home)
		self.assertEqual(
			str(caught.exception),
			"That user is already assigned to this property",
		)

	def test_only_a_manager_can_receive_a_residence(self):
		frappe.set_user(self.admin)
		for role, email in (
			("Staff", "access-plain@hotlync.local"),
			("Accommodation Admin", "access-group@hotlync.local"),
		):
			created = create_user_access(
				email=email,
				first_name="Access",
				role=role,
				password=PASSWORD,
			)
			with self.assertRaises(frappe.ValidationError) as caught:
				assign_user_property(created["name"], self.home)
			self.assertEqual(
				str(caught.exception),
				"Only a manager can be assigned to a residence",
			)

	def test_an_admin_cannot_grant_system_manager_or_change_themselves(self):
		holder = _user("access-holder@hotlync.local", "System Manager")
		_add_role(holder, "Accommodation Manager")
		frappe.set_user(self.admin)
		before = set(frappe.get_roles(holder))
		before_versions = frappe.db.count("Version", {"ref_doctype": "User", "docname": holder})
		with self.assertRaises(frappe.ValidationError) as caught:
			set_user_role(holder, "System Manager")
		self.assertEqual(str(caught.exception), "That role is not available")
		self.assertEqual(set(frappe.get_roles(holder)), before)
		self.assertEqual(
			frappe.db.count("Version", {"ref_doctype": "User", "docname": holder}),
			before_versions,
		)
		changed = set_user_role(holder, "Staff")
		self.assertEqual(changed["roles"], ["Staff"])
		self.assertIn("System Manager", frappe.get_roles(holder))
		with self.assertRaises(frappe.ValidationError) as caught:
			set_user_role(self.admin, "Staff")
		self.assertEqual(str(caught.exception), "You cannot change your own role")
		self.assertIn("Accommodation Admin", frappe.get_roles(self.admin))
		with self.assertRaises(frappe.ValidationError) as caught:
			set_user_enabled(self.admin, 0)
		self.assertEqual(str(caught.exception), "You cannot deactivate your own login")
		self.assertEqual(frappe.db.get_value("User", self.admin, "enabled"), 1)

	def test_staff_cannot_grant_themselves_admin(self):
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.PermissionError):
			set_user_role(self.staff, "Accommodation Admin")
		roles = [role for role in frappe.get_roles(self.staff) if role in SAMS_ROLES]
		self.assertEqual(roles, ["Staff"])

	def _assert_denied(self, user):
		frappe.set_user(user)
		calls = (
			lambda: get_user_access(),
			lambda: create_user_access(
				email="access-blocked@hotlync.local",
				first_name="Blocked",
				role="Accommodation Admin",
				password=PASSWORD,
			),
			lambda: set_user_role(self.staff, "Accommodation Admin"),
			lambda: set_user_enabled(self.staff, 0),
			lambda: assign_user_property(self.staff, self.home),
			lambda: revoke_user_property("PA-0001"),
		)
		for call in calls:
			with self.assertRaises(frappe.PermissionError) as caught:
				call()
			self.assertIn("Not permitted", str(caught.exception))
		self.assertFalse(frappe.db.exists("User", "access-blocked@hotlync.local"))
		self.assertEqual(frappe.db.get_value("User", self.staff, "enabled"), 1)


def _version_text(doctype, name, user):
	rows = frappe.get_all(
		"Version",
		filters={"ref_doctype": doctype, "docname": name, "owner": user},
		pluck="data",
	)
	if not rows:
		frappe.throw("Version for " + name + " was not recorded")
	return "\n".join(rows)


def _property(code, property_name):
	doc = frappe.get_doc(
		{
			"doctype": "Property",
			"code": code,
			"property_name": property_name,
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	return doc.name


def _user(email, role):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Access",
			"send_welcome_email": 0,
			"user_type": "System User",
			"enabled": 1,
		}
	)
	user.append("roles", {"role": role})
	user.insert(ignore_permissions=True)
	return user.name


def _add_role(email, role):
	doc = frappe.get_doc("User", email)
	doc.append("roles", {"role": role})
	doc.save(ignore_permissions=True)


def _assign(user, property_name):
	frappe.get_doc(
		{
			"doctype": "Property Assignment",
			"user": user,
			"property": property_name,
		}
	).insert(ignore_permissions=True)
