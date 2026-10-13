import frappe
from frappe.model.document import Document

from hotlync.accommodation.access import (
	GROUP_ROLES,
	active_employees_for_user,
	property_scope,
	require_property,
)
from hotlync.accommodation.workflow import PRIVILEGED_ROLES, location_for_room, require_manager

KINDS = ("Key", "Key Set")
CONDITIONS = ("Good", "Damaged")
STATUSES = ("Available", "Issued", "Lost", "Damaged", "Replaced", "Decommissioned")
INCIDENTS = ("Lost", "Damaged", "Replaced", "Decommissioned")
IDENTITY = ("label", "kind", "property", "room", "access_point")
HOLDER = ("employee", "custodian", "issued_on", "expected_return", "condition", "replaced_by")


class AccommodationKey(Document):
	def on_trash(self):
		frappe.throw("A key record cannot be deleted")

	def validate(self):
		if frappe.session.user == "Guest":
			frappe.throw("Login required", frappe.AuthenticationError)
		if not _privileged():
			frappe.throw("Not permitted", frappe.PermissionError)
		require_property(self.property)
		if not self.property or not frappe.db.exists("Property", self.property):
			frappe.throw("Property not found")
		self.label = _text(self.label)
		if not self.label:
			frappe.throw("A key mark is required")
		if self.kind not in KINDS:
			frappe.throw("That key type is not available")
		self.access_point = _text(self.access_point)
		if not self.room:
			self.room = None
		_require_place(self)
		_reject_duplicate(self)
		if self.is_new():
			self._start_available()
			return
		self._lock_history()
		self._lock_identity()
		self._apply_transition()

	def _start_available(self):
		if self.status not in (None, "", "Available"):
			frappe.throw("A key starts as available")
		if self.movements:
			frappe.throw("A key starts as available")
		self.status = "Available"
		self.condition = "Good"
		self.employee = None
		self.custodian = None
		self.issued_on = None
		self.expected_return = None
		self.replaced_by = None
		self.append(
			"movements",
			{
				"action": "Registered",
				"actor": frappe.session.user,
				"condition": "Good",
				"occurred_on": frappe.utils.now(),
			},
		)

	def _lock_history(self):
		before = self.get_doc_before_save()
		previous = list(before.movements or [])
		current = list(self.movements or [])
		if len(current) < len(previous):
			frappe.throw("A key movement cannot be changed")
		for index, old in enumerate(previous):
			new = current[index]
			if old.action != new.action or _text(old.actor) != _text(new.actor):
				frappe.throw("A key movement cannot be changed")
			if _text(old.note) != _text(new.note):
				frappe.throw("A key movement cannot be changed")

	def _lock_identity(self):
		before = self.get_doc_before_save()
		for fieldname in IDENTITY:
			if _text(before.get(fieldname)) != _text(self.get(fieldname)):
				frappe.throw("This key can no longer be edited")

	def _apply_transition(self):
		before = self.get_doc_before_save()
		added = len(self.movements or []) - len(before.movements or [])
		if self.status == before.status:
			if added:
				frappe.throw("That status change is not allowed")
			for fieldname in HOLDER:
				if _text(before.get(fieldname)) != _text(self.get(fieldname)):
					frappe.throw("That status change is not allowed")
			return
		if added != 1:
			frappe.throw("Record the key movement before changing the status")
		movement = self.movements[-1]
		if self.status == "Issued":
			_accept_issue(self, before, movement)
		elif movement.action == "Returned":
			_accept_return(self, before, movement)
		elif self.status in INCIDENTS:
			_accept_incident(self, before, movement)
		else:
			frappe.throw("That status change is not allowed")


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles & GROUP_ROLES:
		return ""
	clauses = []
	if "Accommodation Manager" in roles:
		clauses.append(_manager_clause(user))
	if "Staff" in roles:
		clauses.append(_staff_clause(user))
	if not clauses:
		return "1=0"
	return "(" + " or ".join(f"({clause})" for clause in clauses) + ")"


def has_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles & GROUP_ROLES:
		return True
	if "Accommodation Manager" in roles:
		scope = property_scope(user)
		if scope is None or (doc.property and doc.property in scope):
			return True
	if ptype == "read" and "Staff" in roles and _owns_issued(doc, user):
		return True
	return False


def _manager_clause(user):
	scope = property_scope(user)
	if scope is None:
		return "1=1"
	if not scope:
		return "1=0"
	values = ", ".join(frappe.db.escape(name) for name in scope)
	return f"`tabAccommodation Key`.property in ({values})"


def _staff_clause(user):
	matches = active_employees_for_user(user)
	if len(matches) != 1:
		return "1=0"
	employee = frappe.db.escape(matches[0])
	return (
		"`tabAccommodation Key`.status = 'Issued' and "
		f"`tabAccommodation Key`.employee = {employee}"
	)


def _owns_issued(doc, user):
	if doc.status != "Issued":
		return False
	matches = active_employees_for_user(user)
	return len(matches) == 1 and doc.employee == matches[0]


@frappe.whitelist()
def get_keys(name=None, status=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	filters = {}
	if name:
		filters["name"] = name
	if status:
		filters["status"] = status
	rows = frappe.get_list(
		"Accommodation Key",
		filters=filters,
		fields=[
			"name",
			"label",
			"kind",
			"status",
			"property",
			"room",
			"access_point",
			"condition",
			"employee",
			"custodian",
			"issued_on",
			"expected_return",
			"replaced_by",
		],
		order_by="modified desc",
		limit=50,
	)
	if name and not rows:
		frappe.throw("Key not found")
	return {
		"keys": [_row(row) for row in rows],
		"properties": _property_choices(),
		"employees": _employee_choices(),
		"counts": _counts(),
	}


@frappe.whitelist()
def get_key_rooms(property=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if not _privileged():
		frappe.throw("Not permitted", frappe.PermissionError)
	require_property(property)
	if not property or not frappe.db.exists("Property", property):
		frappe.throw("Property not found")
	return frappe.db.sql(
		"""
		select r.name, r.room_number, b.building_name
		from `tabRoom` r
		inner join `tabFloor` f on f.name = r.floor
		inner join `tabBuilding` b on b.name = f.building
		where b.property = %s
		and ifnull(r.building, '') in ('', f.building)
		order by r.room_number asc
		""",
		property,
		as_dict=True,
	)


@frappe.whitelist()
def register_key(label=None, kind=None, property=None, room=None, access_point=None):
	require_manager()
	doc = frappe.new_doc("Accommodation Key")
	doc.label = label
	doc.kind = kind or "Key"
	doc.property = property
	doc.room = room or None
	doc.access_point = access_point or None
	doc.status = "Available"
	doc.condition = "Good"
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def issue_key(name, employee=None, expected_return=None, condition=None):
	require_manager()
	doc = _locked(name)
	if doc.status != "Available":
		frappe.throw("That key is not available to issue")
	doc.employee = employee
	doc.custodian = frappe.session.user
	doc.issued_on = frappe.utils.now()
	doc.expected_return = _text(expected_return)
	doc.condition = condition or "Good"
	doc.status = "Issued"
	doc.append(
		"movements",
		{
			"action": "Issued",
			"actor": frappe.session.user,
			"recipient": employee,
			"custodian": frappe.session.user,
			"condition": doc.condition,
			"expected_return": doc.expected_return,
			"occurred_on": doc.issued_on,
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def return_key(name, condition=None, note=None):
	require_manager()
	doc = _locked(name)
	if doc.status != "Issued":
		frappe.throw("That key is not issued")
	condition = condition or "Good"
	if condition == "Damaged" and not _text(note):
		frappe.throw("A note is required")
	recipient = doc.employee
	doc.condition = condition
	doc.status = "Damaged" if condition == "Damaged" else "Available"
	doc.employee = None
	doc.custodian = None
	doc.issued_on = None
	doc.expected_return = None
	doc.append(
		"movements",
		{
			"action": "Returned",
			"actor": frappe.session.user,
			"recipient": recipient,
			"custodian": frappe.session.user,
			"condition": condition,
			"note": note or "",
			"occurred_on": frappe.utils.now(),
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def record_key_incident(name, status, note=None, replaced_by=None):
	require_manager()
	if status not in INCIDENTS:
		frappe.throw("That status change is not allowed")
	doc = _locked(name)
	if doc.status not in ("Available", "Issued"):
		frappe.throw("That status change is not allowed")
	if not _text(note):
		frappe.throw("A note is required")
	recipient = doc.employee if doc.status == "Issued" else None
	doc.status = status
	doc.employee = None
	doc.custodian = None
	doc.issued_on = None
	doc.expected_return = None
	doc.replaced_by = _text(replaced_by) if status == "Replaced" else None
	doc.append(
		"movements",
		{
			"action": status,
			"actor": frappe.session.user,
			"recipient": recipient,
			"note": note,
			"occurred_on": frappe.utils.now(),
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


def _accept_issue(doc, before, movement):
	if before.status != "Available" or movement.action != "Issued":
		frappe.throw("That status change is not allowed")
	_assert_recipient(doc.employee)
	if doc.custodian != frappe.session.user:
		frappe.throw("That status change is not allowed")
	if doc.condition not in CONDITIONS:
		frappe.throw("That key condition is not available")
	_assert_expected_return(doc.expected_return)
	if not doc.issued_on:
		doc.issued_on = frappe.utils.now()
	_stamp(movement, doc.employee, doc.condition, doc.expected_return)


def _accept_return(doc, before, movement):
	if before.status != "Issued":
		frappe.throw("That key is not issued")
	if doc.status == "Available" and doc.condition != "Good":
		frappe.throw("That key condition is not available")
	if doc.status == "Damaged":
		if doc.condition != "Damaged":
			frappe.throw("That key condition is not available")
		if not _text(movement.note):
			frappe.throw("A note is required")
	if doc.status not in ("Available", "Damaged"):
		frappe.throw("That status change is not allowed")
	_assert_cleared(doc)
	_stamp(movement, before.employee, doc.condition, None)


def _accept_incident(doc, before, movement):
	if before.status not in ("Available", "Issued"):
		frappe.throw("That status change is not allowed")
	if movement.action != doc.status or doc.status not in INCIDENTS:
		frappe.throw("Record the key movement before changing the status")
	if not _text(movement.note):
		frappe.throw("A note is required")
	_assert_cleared(doc)
	if doc.status == "Replaced":
		_assert_replacement(doc)
	elif doc.replaced_by:
		frappe.throw("A replacement key applies only when the key is replaced")
	_stamp(movement, before.employee, doc.condition, None)


def _stamp(movement, recipient, condition, expected_return):
	movement.actor = frappe.session.user
	movement.custodian = frappe.session.user
	if recipient:
		movement.recipient = recipient
	if condition:
		movement.condition = condition
	if expected_return:
		movement.expected_return = expected_return
	if not movement.occurred_on:
		movement.occurred_on = frappe.utils.now()


def _assert_cleared(doc):
	if doc.employee or doc.custodian or doc.issued_on or doc.expected_return:
		frappe.throw("That status change is not allowed")


def _assert_recipient(employee):
	if not employee or not frappe.db.exists("Employee", employee):
		frappe.throw("Employee not found")
	if frappe.db.get_value("Employee", employee, "status") != "Active":
		frappe.throw("Employee is not active")


def _assert_expected_return(value):
	if not _text(value):
		return
	if frappe.utils.getdate(value) < frappe.utils.getdate(frappe.utils.today()):
		frappe.throw("Expected return cannot be before today")


def _assert_replacement(doc):
	if not doc.replaced_by:
		return
	if doc.replaced_by == doc.name:
		frappe.throw("A key cannot replace itself")
	other = frappe.db.get_value("Accommodation Key", doc.replaced_by, "property")
	if not other:
		frappe.throw("Replacement key was not found")
	if other != doc.property:
		frappe.throw("Replacement key is not in the selected residence")


def _require_place(doc):
	if not doc.room and not doc.access_point:
		frappe.throw("Name a room or an access point")
	if not doc.room:
		return
	location = location_for_room(doc.room)
	if location.get("property") != doc.property:
		frappe.throw("Room is not in the selected residence")


def _reject_duplicate(doc):
	existing = frappe.db.get_value(
		"Accommodation Key",
		{"property": doc.property, "label": doc.label},
		"name",
	)
	if existing and existing != doc.name:
		frappe.throw("A key with that mark is already registered at this residence.")


def _locked(name):
	if not name or not frappe.db.exists("Accommodation Key", name):
		frappe.throw("Key not found")
	frappe.db.sql(
		"select name from `tabAccommodation Key` where name=%s for update",
		name,
	)
	return frappe.get_doc("Accommodation Key", name)


def _present(doc):
	return _row(doc)


def _row(row):
	movements = frappe.get_all(
		"Key Movement",
		filters={"parent": row.name, "parenttype": "Accommodation Key"},
		fields=[
			"action",
			"actor",
			"recipient",
			"custodian",
			"condition",
			"expected_return",
			"note",
			"occurred_on",
			"creation",
		],
		order_by="idx asc",
	)
	return {
		"name": row.name,
		"label": row.label,
		"kind": row.kind,
		"status": row.status,
		"property": row.property,
		"property_name": frappe.db.get_value("Property", row.property, "property_name"),
		"room": row.room,
		"room_number": frappe.db.get_value("Room", row.room, "room_number") if row.room else None,
		"access_point": row.access_point,
		"condition": row.condition,
		"employee": row.employee,
		"employee_name": frappe.db.get_value("Employee", row.employee, "employee_name") if row.employee else None,
		"custodian": row.custodian,
		"issued_on": _text(row.issued_on),
		"expected_return": _text(row.expected_return),
		"replaced_by": row.replaced_by,
		"can_issue": _privileged() and row.status == "Available" and _property_visible(row.property),
		"can_return": _privileged() and row.status == "Issued" and _property_visible(row.property),
		"can_record": _privileged() and row.status in ("Available", "Issued") and _property_visible(row.property),
		"movements": [
			{
				"action": item.action,
				"actor": item.actor,
				"recipient": item.recipient,
				"recipient_name": frappe.db.get_value("Employee", item.recipient, "employee_name") if item.recipient else None,
				"custodian": item.custodian,
				"condition": item.condition,
				"expected_return": _text(item.expected_return),
				"note": item.note,
				"occurred_on": _text(item.occurred_on),
				"creation": _text(item.creation),
			}
			for item in movements
		],
	}


def _counts():
	rows = frappe.get_list("Accommodation Key", fields=["status"], limit=500)
	counts = {status: 0 for status in STATUSES}
	for row in rows:
		if row.status in counts:
			counts[row.status] += 1
	return counts


def _property_choices():
	if not _privileged():
		return []
	scope = property_scope()
	if scope is None:
		names = frappe.get_all("Property", pluck="name", order_by="property_name asc")
	else:
		names = scope
	return [
		{
			"name": property_name,
			"property_name": frappe.db.get_value("Property", property_name, "property_name"),
		}
		for property_name in names
	]


def _employee_choices():
	if not _privileged():
		return []
	return frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name"],
		order_by="employee_name asc",
		limit=200,
	)


def _property_visible(property_name):
	scope = property_scope()
	if scope is None:
		return True
	return bool(property_name and property_name in scope)


def _privileged():
	return bool(set(frappe.get_roles()).intersection(PRIVILEGED_ROLES))


def _text(value):
	if value is None:
		return None
	text = str(value).strip()
	return text or None
