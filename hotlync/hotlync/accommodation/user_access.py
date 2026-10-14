import frappe

from hotlync.accommodation.access import GROUP_ROLES

HOTLYNC_ROLES = ("Staff", "Accommodation Manager", "Accommodation Admin")
PROTECTED_USERS = {"Administrator", "Guest"}


def require_admin():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if not set(frappe.get_roles()) & GROUP_ROLES:
		frappe.throw("Not permitted", frappe.PermissionError)


@frappe.whitelist()
def get_user_access():
	require_admin()
	role_rows = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(HOTLYNC_ROLES)], "parenttype": "User"},
		fields=["parent", "role"],
		limit=500,
	)
	by_user = {}
	for row in role_rows:
		if not row.parent or row.parent in PROTECTED_USERS:
			continue
		by_user.setdefault(row.parent, set()).add(row.role)
	names = sorted(by_user)
	assignments = frappe.get_all(
		"Property Assignment",
		filters={"user": ["in", names]} if names else {"name": ["=", ""]},
		fields=["name", "user", "property"],
		limit=500,
	)
	by_assignment = {}
	for row in assignments:
		by_assignment.setdefault(row.user, []).append(
			{
				"name": row.name,
				"property": row.property,
				"property_name": frappe.db.get_value("Property", row.property, "property_name"),
			}
		)
	users = []
	for name in names:
		users.append(
			{
				"name": name,
				"full_name": frappe.db.get_value("User", name, "full_name") or name,
				"enabled": frappe.db.get_value("User", name, "enabled"),
				"roles": sorted(by_user[name]),
				"properties": by_assignment.get(name, []),
			}
		)
	users.sort(key=lambda row: row["full_name"].lower())
	return {"users": users[:200], "roles": list(HOTLYNC_ROLES)}


@frappe.whitelist()
def create_user_access(email=None, first_name=None, last_name=None, role=None, password=None):
	require_admin()
	email = _text(email)
	first_name = _text(first_name)
	last_name = _text(last_name)
	role = _text(role)
	if not email:
		frappe.throw("A user id is required")
	if not first_name:
		frappe.throw("A name is required")
	if not _text(password):
		frappe.throw("A password is required")
	_assert_role(role)
	if email in PROTECTED_USERS or frappe.db.exists("User", email):
		frappe.throw("That user already exists")
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"send_welcome_email": 0,
			"user_type": "System User",
			"enabled": 1,
		}
	)
	doc.new_password = password
	doc.append("roles", {"role": role})
	doc.flags.no_welcome_mail = True
	doc.insert(ignore_permissions=True)
	return _row(doc.name)


@frappe.whitelist()
def set_user_enabled(user=None, enabled=None):
	require_admin()
	doc = _load_user(user)
	if doc.name == frappe.session.user and not _as_enabled(enabled):
		frappe.throw("You cannot deactivate your own login")
	doc.enabled = _as_enabled(enabled)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _row(doc.name)


@frappe.whitelist()
def set_user_role(user=None, role=None):
	require_admin()
	doc = _load_user(user)
	if doc.name == frappe.session.user:
		frappe.throw("You cannot change your own role")
	_assert_role(role)
	_replace_hotlync_roles(doc, role)
	return _row(doc.name)


@frappe.whitelist()
def assign_user_property(user=None, property=None):
	require_admin()
	doc = _load_user(user)
	if "Accommodation Manager" not in frappe.get_roles(doc.name):
		frappe.throw("Only a manager can be assigned to a residence")
	if not property or not frappe.db.exists("Property", property):
		frappe.throw("Property not found")
	assignment = frappe.get_doc(
		{
			"doctype": "Property Assignment",
			"user": doc.name,
			"property": property,
		}
	).insert(ignore_permissions=True)
	return {"assignment": assignment.name, "user": _row(doc.name)}


@frappe.whitelist()
def revoke_user_property(name=None):
	require_admin()
	if not name or not frappe.db.exists("Property Assignment", name):
		frappe.throw("Assignment not found")
	user = frappe.db.get_value("Property Assignment", name, "user")
	frappe.delete_doc("Property Assignment", name, ignore_permissions=True)
	return _row(user)


def _load_user(user):
	user = _text(user)
	if not user or user in PROTECTED_USERS or not frappe.db.exists("User", user):
		frappe.throw("User not found")
	return frappe.get_doc("User", user)


def _assert_role(role):
	if role not in HOTLYNC_ROLES:
		frappe.throw("That role is not available")


def _replace_hotlync_roles(doc, role):
	for row in list(doc.roles):
		if row.role in HOTLYNC_ROLES:
			doc.remove(row)
	doc.append("roles", {"role": role})
	doc.save(ignore_permissions=True, ignore_version=False)


def _as_enabled(value):
	if value in (1, "1", True):
		return 1
	if value in (0, "0", False):
		return 0
	frappe.throw("That status change is not allowed")


def _row(name):
	roles = frappe.get_all(
		"Has Role",
		filters={"parent": name, "parenttype": "User", "role": ["in", list(HOTLYNC_ROLES)]},
		pluck="role",
	)
	assignments = frappe.get_all(
		"Property Assignment",
		filters={"user": name},
		fields=["name", "property"],
	)
	return {
		"name": name,
		"full_name": frappe.db.get_value("User", name, "full_name") or name,
		"enabled": frappe.db.get_value("User", name, "enabled"),
		"roles": sorted(roles),
		"properties": [
			{
				"name": row.name,
				"property": row.property,
				"property_name": frappe.db.get_value("Property", row.property, "property_name"),
			}
			for row in assignments
		],
	}


def _text(value):
	if value is None:
		return None
	text = str(value).strip()
	return text or None
