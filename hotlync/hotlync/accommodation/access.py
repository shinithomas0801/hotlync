import frappe

GROUP_ROLES = {"System Manager", "Accommodation Admin"}


def property_scope(user=None):
	"""None means every property. A list is the Accommodation Manager's assignments."""
	user = user or frappe.session.user
	if set(frappe.get_roles(user)) & GROUP_ROLES:
		return None
	if "Accommodation Manager" not in frappe.get_roles(user):
		return []
	return frappe.get_all(
		"Property Assignment",
		filters={"user": user},
		pluck="property",
	)


def active_employees_for_user(user):
	"""Active employees linked to this login, capped so a duplicate is visible."""
	if not user or user == "Guest":
		return []
	return frappe.get_all(
		"Employee",
		filters={"user_id": user, "status": "Active"},
		pluck="name",
		limit=2,
	)


def require_property(property_name):
	scope = property_scope()
	if scope is None:
		return
	if property_name not in scope:
		frappe.throw("Not permitted", frappe.PermissionError)


def property_query(user):
	return _name_query("tabProperty", "name", user)


def building_query(user):
	return _name_query("tabBuilding", "property", user)


def floor_query(user):
	values = _values(user)
	if values is None:
		return ""
	if values == "":
		return "1=0"
	return (
		"`tabFloor`.building in (select name from `tabBuilding` "
		f"where property in ({values}))"
	)


def room_query(user):
	values = _values(user)
	if values is None:
		return ""
	if values == "":
		return "1=0"
	return (
		"`tabRoom`.name in (select r.name from `tabRoom` r "
		"inner join `tabFloor` f on f.name = r.floor "
		"inner join `tabBuilding` b on b.name = f.building "
		f"where b.property in ({values}))"
	)


def bed_query(user):
	values = _values(user)
	if values is None:
		return ""
	if values == "":
		return "1=0"
	return (
		"`tabBed`.room in (select r.name from `tabRoom` r "
		"inner join `tabFloor` f on f.name = r.floor "
		"inner join `tabBuilding` b on b.name = f.building "
		f"where b.property in ({values}))"
	)


def property_has_permission(doc, ptype="read", user=None, debug=False):
	return _allows(doc.name, user)


def building_has_permission(doc, ptype="read", user=None, debug=False):
	return _allows(doc.property, user)


def floor_has_permission(doc, ptype="read", user=None, debug=False):
	property_name = frappe.db.get_value("Building", doc.building, "property")
	return _allows(property_name, user)


def room_has_permission(doc, ptype="read", user=None, debug=False):
	building = doc.building or frappe.db.get_value("Floor", doc.floor, "building")
	property_name = frappe.db.get_value("Building", building, "property")
	return _allows(property_name, user)


def bed_has_permission(doc, ptype="read", user=None, debug=False):
	building = frappe.db.get_value("Room", doc.room, "building")
	if not building:
		floor = frappe.db.get_value("Room", doc.room, "floor")
		building = frappe.db.get_value("Floor", floor, "building")
	property_name = frappe.db.get_value("Building", building, "property")
	return _allows(property_name, user)


def allocation_clause(user):
	return _name_query("tabAccommodation Allocation", "property", user)


def _allows(property_name, user):
	scope = property_scope(user)
	if scope is None:
		return True
	return bool(property_name and property_name in scope)


def _name_query(table, column, user):
	values = _values(user)
	if values is None:
		return ""
	if values == "":
		return "1=0"
	return f"`{table}`.{column} in ({values})"


def _values(user):
	scope = property_scope(user)
	if scope is None:
		return None
	if not scope:
		return ""
	return ", ".join(frappe.db.escape(name) for name in scope)
