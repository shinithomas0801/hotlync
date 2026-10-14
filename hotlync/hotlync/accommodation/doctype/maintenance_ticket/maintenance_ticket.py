import frappe
from frappe.model.document import Document

from hotlync.accommodation.access import (
	GROUP_ROLES,
	active_employees_for_user,
	property_scope,
	require_property,
)
from hotlync.accommodation.workflow import PRIVILEGED_ROLES, location_for_bed, location_for_room

STATUSES = ("Submitted", "Assigned", "In Progress", "Waiting", "Resolved", "Closed")
URGENCIES = ("Low", "Normal", "Urgent")
NOTE_TYPES = ("Progress", "Evidence", "Parts", "Resolution", "Feedback")
DETAIL_FIELDS = (
	"category",
	"urgency",
	"property",
	"building",
	"room",
	"bed",
	"description",
	"preferred_contact",
	"photo",
	"employee",
)
COORDINATOR_TRANSITIONS = {
	"Submitted": ("Assigned", "In Progress", "Waiting", "Resolved", "Closed"),
	"Assigned": ("Assigned", "In Progress", "Waiting", "Resolved", "Closed"),
	"In Progress": ("Assigned", "Waiting", "Resolved", "Closed"),
	"Waiting": ("Assigned", "In Progress", "Resolved", "Closed"),
	"Resolved": ("Closed",),
	"Closed": (),
}
ASSIGNEE_TRANSITIONS = {
	"Assigned": ("In Progress", "Waiting", "Resolved"),
	"In Progress": ("Waiting", "Resolved"),
	"Waiting": ("In Progress", "Resolved"),
}


class MaintenanceTicket(Document):
	def before_insert(self):
		self.reported_by = frappe.session.user
		self.reported_on = frappe.utils.today()
		if self.status not in (None, "", "Submitted"):
			frappe.throw("A ticket starts as submitted")
		self.status = "Submitted"

	def validate(self):
		if frappe.session.user == "Guest":
			frappe.throw("Login required", frappe.AuthenticationError)
		if self.is_new():
			self.reported_by = frappe.session.user
			self.reported_on = frappe.utils.today()
		else:
			self.reported_by = self.get_doc_before_save().reported_by
		self._keep_in_scope()
		self._force_staff_employee()
		_require_details(self)
		_require_location(self)
		self._lock_details()
		if not self.is_new():
			self._lock_history()
		self._apply_transition()

	def on_update(self):
		try:
			from hotlync.accommodation.notify import notify_ticket

			notify_ticket(self)
		except Exception:
			return

	def _keep_in_scope(self):
		roles = set(frappe.get_roles())
		if roles & PRIVILEGED_ROLES:
			require_property(self.property)
			return
		if not self.is_new() and self._assignee_before() == frappe.session.user:
			return
		if not self.is_new():
			_assert_party(self)

	def _assignee_before(self):
		if self.is_new():
			return None
		return self.get_doc_before_save().assignee

	def _force_staff_employee(self):
		if not _staff_only():
			return
		if not self.is_new() and self.reported_by != frappe.session.user:
			return
		matches = active_employees_for_user(frappe.session.user)
		if len(matches) > 1:
			frappe.throw("This login is linked to more than one employee")
		if len(matches) != 1:
			frappe.throw("This login is not linked to an employee.")
		self.employee = matches[0]

	def _lock_details(self):
		if self.is_new() or self.status == "Submitted":
			return
		before = self.get_doc_before_save()
		for fieldname in DETAIL_FIELDS:
			if _text(before.get(fieldname)) != _text(self.get(fieldname)):
				frappe.throw("This ticket can no longer be edited")

	def _lock_history(self):
		before = self.get_doc_before_save()
		previous = list(before.updates or [])
		current = list(self.updates or [])
		if len(current) < len(previous):
			frappe.throw("A maintenance update cannot be changed")
		for index, old in enumerate(previous):
			new = current[index]
			if old.action != new.action or _text(old.actor) != _text(new.actor):
				frappe.throw("A maintenance update cannot be changed")
			if _text(old.comment) != _text(new.comment):
				frappe.throw("A maintenance update cannot be changed")
			for fieldname in ("assignee", "team_name", "contractor_name"):
				if _text(old.get(fieldname)) != _text(new.get(fieldname)):
					frappe.throw("A maintenance update cannot be changed")

	def _apply_transition(self):
		if self.is_new():
			if self.status != "Submitted":
				frappe.throw("A ticket starts as submitted")
			self.append(
				"updates",
				{"action": "Submitted", "actor": frappe.session.user, "comment": ""},
			)
			return
		before = self.get_doc_before_save()
		if self.status == before.status and not _assignment_changed(self, before):
			if _new_updates(self, before):
				frappe.throw("That status change is not allowed")
			return
		if self.status == "Submitted" and before.status in ("Resolved", "Closed"):
			_assert_party(self)
			_require_reopen_note(self, before)
			return
		if not _transition_allowed(self, before):
			if _privileged() or self._assignee_before() == frappe.session.user:
				frappe.throw("That status change is not allowed")
			frappe.throw("Not permitted", frappe.PermissionError)
		if self.status == "Resolved" and not _filled(self.resolution):
			frappe.throw("Resolution details are required")
		_require_new_update(self, before)
		if self.status == "Assigned" and not _has_assignment(self):
			frappe.throw("Name an assignee, a team, or a contractor")


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
	clauses.append("`tabMaintenance Ticket`.assignee = " + frappe.db.escape(user))
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
	if doc.assignee == user:
		return True
	if "Staff" in roles and _owns(doc, user):
		return True
	return False


def _manager_clause(user):
	scope = property_scope(user)
	if scope is None:
		return "1=1"
	if not scope:
		return "1=0"
	values = ", ".join(frappe.db.escape(name) for name in scope)
	return f"`tabMaintenance Ticket`.property in ({values})"


def _staff_clause(user):
	parts = [
		"`tabMaintenance Ticket`.reported_by = " + frappe.db.escape(user),
	]
	matches = active_employees_for_user(user)
	if len(matches) == 1:
		parts.append(
			"`tabMaintenance Ticket`.employee = " + frappe.db.escape(matches[0])
		)
	if len(parts) == 1:
		return parts[0]
	return "(" + " or ".join(parts) + ")"


def _owns(doc, user):
	if doc.reported_by == user:
		return True
	matches = active_employees_for_user(user)
	return len(matches) == 1 and doc.employee == matches[0]


def _staff_only():
	roles = set(frappe.get_roles())
	return "Staff" in roles and not roles.intersection(PRIVILEGED_ROLES)


def _privileged():
	return bool(set(frappe.get_roles()).intersection(PRIVILEGED_ROLES))


def _assert_party(doc):
	if _owns(doc, frappe.session.user):
		return
	frappe.throw("Not permitted", frappe.PermissionError)


def _transition_allowed(doc, before):
	if _privileged() and doc.status in COORDINATOR_TRANSITIONS.get(before.status, ()):
		return True
	return (
		before.assignee == frappe.session.user
		and doc.status in ASSIGNEE_TRANSITIONS.get(before.status, ())
	)


def _assignment_changed(doc, before):
	return any(
		_text(doc.get(fieldname)) != _text(before.get(fieldname))
		for fieldname in ("assignee", "team_name", "contractor_name")
	)


def _has_assignment(doc):
	return any(_filled(doc.get(fieldname)) for fieldname in ("assignee", "team_name", "contractor_name"))


def _new_updates(doc, before):
	previous = {row.name for row in (before.updates or []) if row.name}
	return [row for row in (doc.updates or []) if row.name not in previous]


def _require_new_update(doc, before):
	previous = {row.name for row in (before.updates or []) if row.name}
	action = _update_action(doc, before)
	matching = [
		row
		for row in (doc.updates or [])
		if row.name not in previous
		and row.action == action
		and row.actor == frappe.session.user
	]
	if not matching:
		frappe.throw("Record the update before changing the status")


def _require_reopen_note(doc, before):
	previous = {row.name for row in (before.updates or []) if row.name}
	matching = [
		row
		for row in (doc.updates or [])
		if row.name not in previous
		and row.action == "Reopened"
		and row.actor == frappe.session.user
		and _filled(row.comment)
	]
	if not matching:
		frappe.throw("A comment is required")


def _update_action(doc, before):
	if doc.status == "Assigned" and before.status == "Assigned":
		return "Reassigned"
	return doc.status


def _require_details(doc):
	if not _filled(doc.category):
		frappe.throw("Category is required")
	if doc.urgency not in URGENCIES:
		frappe.throw("Urgency is required")
	if not _filled(doc.description):
		frappe.throw("Description is required")
	if doc.employee and not frappe.db.exists("Employee", doc.employee):
		frappe.throw("Employee not found")
	if doc.assignee and not frappe.db.exists("User", doc.assignee):
		frappe.throw("Assignee not found")


def _require_location(doc):
	if not doc.property or not frappe.db.exists("Property", doc.property):
		frappe.throw("Property not found")
	if doc.building:
		building_property = frappe.db.get_value("Building", doc.building, "property")
		if building_property != doc.property:
			frappe.throw("Building is not in the selected residence")
	if doc.room:
		location = location_for_room(doc.room)
		if location.get("property") != doc.property:
			frappe.throw("Room is not in the selected residence")
		if doc.building and location.get("building") != doc.building:
			frappe.throw("Room is not in the selected building")
	if doc.bed:
		location = location_for_bed(doc.bed)
		if location.get("property") != doc.property:
			frappe.throw("Bed is not in the selected residence")
		if doc.room and location.get("room") != doc.room:
			frappe.throw("Bed is not in the selected room")


@frappe.whitelist()
def get_tickets(name=None, status=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	filters = {}
	if name:
		filters["name"] = name
	if status:
		filters["status"] = status
	rows = frappe.get_list(
		"Maintenance Ticket",
		filters=filters,
		fields=[
			"name",
			"category",
			"status",
			"urgency",
			"property",
			"building",
			"room",
			"bed",
			"reported_by",
			"employee",
			"reported_on",
			"description",
			"preferred_contact",
			"photo",
			"assignee",
			"team_name",
			"contractor_name",
			"resolution",
		],
		order_by="modified desc",
		limit=50,
	)
	if name and not rows:
		frappe.throw("Ticket not found")
	return {
		"tickets": [_row(row) for row in rows],
		"properties": _property_choices(),
		"assignees": _assignee_choices(),
		"counts": _counts(),
	}


@frappe.whitelist()
def get_ticket_locations(property):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if _privileged():
		require_property(property)
	if not property or not frappe.db.exists("Property", property):
		frappe.throw("Property not found")
	return _locations(property)


@frappe.whitelist()
def save_ticket(
	name=None,
	category=None,
	urgency=None,
	property=None,
	building=None,
	room=None,
	bed=None,
	employee=None,
	description=None,
	preferred_contact=None,
	photo=None,
):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if name:
		doc = _load(name)
	else:
		doc = frappe.new_doc("Maintenance Ticket")
		doc.status = "Submitted"
	incoming = {
		"category": category,
		"urgency": urgency,
		"property": property,
		"building": building,
		"room": room,
		"bed": bed,
		"employee": employee,
		"description": description,
		"preferred_contact": preferred_contact,
		"photo": photo,
	}
	for fieldname, value in incoming.items():
		if value is not None:
			setattr(doc, fieldname, value)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def assign_ticket(name, assignee=None, team_name=None, contractor_name=None, comment=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if not _privileged():
		frappe.throw("Not permitted", frappe.PermissionError)
	doc = _load(name)
	before_status = doc.status
	if assignee is not None:
		doc.assignee = assignee
	if team_name is not None:
		doc.team_name = team_name
	if contractor_name is not None:
		doc.contractor_name = contractor_name
	doc.status = "Assigned"
	action = "Reassigned" if before_status == "Assigned" else "Assigned"
	doc.append(
		"updates",
		{
			"action": action,
			"actor": frappe.session.user,
			"comment": comment or "",
			"assignee": doc.assignee,
			"team_name": doc.team_name,
			"contractor_name": doc.contractor_name,
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def update_ticket(name, status, comment=None, resolution=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if status not in STATUSES:
		frappe.throw("That status change is not allowed")
	doc = _load(name)
	if resolution is not None:
		doc.resolution = resolution
	doc.status = status
	doc.append(
		"updates",
		{
			"action": status,
			"actor": frappe.session.user,
			"comment": comment or "",
			"assignee": doc.assignee,
			"team_name": doc.team_name,
			"contractor_name": doc.contractor_name,
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def add_note(name, note_type, comment, evidence=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if note_type not in NOTE_TYPES:
		frappe.throw("That note is not available")
	if not _filled(comment):
		frappe.throw("A comment is required")
	doc = _load(name)
	_assert_note_actor(doc, note_type)
	doc.append(
		"notes",
		{
			"note_type": note_type,
			"actor": frappe.session.user,
			"comment": comment,
			"evidence": evidence or "",
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def attach_ticket_photo():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	content = getattr(frappe.local, "uploaded_file", None)
	filename = getattr(frappe.local, "uploaded_filename", None) or "photo"
	if not content:
		frappe.throw("A photo is required")
	doc = _load(frappe.form_dict.docname)
	if not has_permission(doc, ptype="write"):
		frappe.throw("Not permitted", frappe.PermissionError)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"attached_to_doctype": "Maintenance Ticket",
			"attached_to_name": doc.name,
			"attached_to_field": "photo",
			"file_name": filename,
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)
	doc.photo = file_doc.file_url
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def reopen_ticket(name, comment=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	doc = _load(name)
	doc.status = "Submitted"
	doc.append(
		"updates",
		{
			"action": "Reopened",
			"actor": frappe.session.user,
			"comment": comment or "",
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


def _assert_note_actor(doc, note_type):
	user = frappe.session.user
	if note_type == "Feedback":
		if _owns(doc, user) or _privileged():
			return
		frappe.throw("Not permitted", frappe.PermissionError)
	if _privileged() or doc.assignee == user:
		return
	frappe.throw("Not permitted", frappe.PermissionError)


def _load(name):
	if not name or not frappe.db.exists("Maintenance Ticket", name):
		frappe.throw("Ticket not found")
	return frappe.get_doc("Maintenance Ticket", name)


def _present(doc):
	return _row(doc)


def _row(row):
	updates = frappe.get_all(
		"Maintenance Update",
		filters={"parent": row.name, "parenttype": "Maintenance Ticket"},
		fields=["action", "actor", "comment", "assignee", "team_name", "contractor_name", "creation"],
		order_by="idx asc",
	)
	notes = frappe.get_all(
		"Maintenance Note",
		filters={"parent": row.name, "parenttype": "Maintenance Ticket"},
		fields=["note_type", "actor", "comment", "evidence", "creation"],
		order_by="idx asc",
	)
	return {
		"name": row.name,
		"category": row.category,
		"status": row.status,
		"urgency": row.urgency,
		"property": row.property,
		"property_name": frappe.db.get_value("Property", row.property, "property_name"),
		"building": row.building,
		"building_name": frappe.db.get_value("Building", row.building, "building_name") if row.building else None,
		"room": row.room,
		"room_number": frappe.db.get_value("Room", row.room, "room_number") if row.room else None,
		"bed": row.bed,
		"bed_number": frappe.db.get_value("Bed", row.bed, "bed_number") if row.bed else None,
		"reported_by": row.reported_by,
		"employee": row.employee,
		"employee_name": frappe.db.get_value("Employee", row.employee, "employee_name") if row.employee else None,
		"reported_on": _text(row.reported_on),
		"description": row.description,
		"preferred_contact": row.preferred_contact,
		"photo": row.photo,
		"assignee": row.assignee,
		"team_name": row.team_name,
		"contractor_name": row.contractor_name,
		"resolution": row.resolution,
		"can_assign": _privileged() and _property_visible(row.property),
		"can_progress": _can_progress(row),
		"can_reopen": row.status in ("Resolved", "Closed") and _owns(row, frappe.session.user),
		"can_feedback": _owns(row, frappe.session.user) or _privileged(),
		"updates": [
			{
				"action": item.action,
				"actor": item.actor,
				"comment": item.comment,
				"assignee": item.assignee,
				"team_name": item.team_name,
				"contractor_name": item.contractor_name,
				"creation": _text(item.creation),
			}
			for item in updates
		],
		"notes": [
			{
				"note_type": item.note_type,
				"actor": item.actor,
				"comment": item.comment,
				"evidence": item.evidence,
				"creation": _text(item.creation),
			}
			for item in notes
		],
	}


def _can_progress(row):
	if row.status in ("Resolved", "Closed"):
		return _privileged() and row.status == "Resolved"
	if _privileged() and _property_visible(row.property):
		return True
	return row.assignee == frappe.session.user and row.status in ASSIGNEE_TRANSITIONS


def _property_visible(property_name):
	scope = property_scope()
	if scope is None:
		return True
	return bool(property_name and property_name in scope)


def _counts():
	rows = frappe.get_list("Maintenance Ticket", fields=["status"], limit=500)
	counts = {status: 0 for status in STATUSES}
	for row in rows:
		if row.status in counts:
			counts[row.status] += 1
	return counts


def _property_choices():
	if _staff_only():
		names = frappe.get_all("Property", pluck="name", order_by="property_name asc")
	else:
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


def _assignee_choices():
	if not _privileged():
		return []
	roles = ("Accommodation Manager", "Accommodation Admin", "Staff")
	parents = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(roles)], "parenttype": "User"},
		pluck="parent",
		limit=200,
	)
	names = sorted({parent for parent in parents if parent and parent != "Guest"})
	return [
		{
			"name": user,
			"full_name": frappe.db.get_value("User", user, "full_name") or user,
		}
		for user in names
	]


def _locations(property_name):
	buildings = frappe.get_all(
		"Building",
		filters={"property": property_name},
		fields=["name", "building_name"],
		order_by="building_name asc",
	)
	rooms = frappe.db.sql(
		"""
		select r.name, r.room_number, b.name as building
		from `tabRoom` r
		inner join `tabFloor` f on f.name = r.floor
		inner join `tabBuilding` b on b.name = f.building
		where b.property = %s
		and ifnull(r.building, '') in ('', f.building)
		order by r.room_number asc
		""",
		property_name,
		as_dict=True,
	)
	room_names = [room.name for room in rooms]
	beds = []
	if room_names:
		beds = frappe.get_all(
			"Bed",
			filters={"room": ["in", room_names]},
			fields=["name", "bed_number", "room"],
			order_by="bed_number asc",
		)
	beds_by_room = {}
	for bed in beds:
		beds_by_room.setdefault(bed.room, []).append(
			{"name": bed.name, "bed_number": bed.bed_number}
		)
	rooms_by_building = {}
	for room in rooms:
		rooms_by_building.setdefault(room.building, []).append(
			{
				"name": room.name,
				"room_number": room.room_number,
				"beds": beds_by_room.get(room.name, []),
			}
		)
	return [
		{
			"name": building.name,
			"building_name": building.building_name,
			"rooms": rooms_by_building.get(building.name, []),
		}
		for building in buildings
	]


def _filled(value):
	return value is not None and str(value).strip() != ""


def _text(value):
	if not _filled(value):
		return None
	return str(value)
