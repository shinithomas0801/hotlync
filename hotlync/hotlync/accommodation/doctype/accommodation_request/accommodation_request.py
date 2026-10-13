import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from hotlync.accommodation.access import (
	GROUP_ROLES,
	active_employees_for_user,
	property_scope,
	require_property,
)
from hotlync.accommodation.workflow import PRIVILEGED_ROLES, location_for_bed

OPEN_STATUSES = ("Draft", "Submitted", "Changes Requested")
EDITABLE_STATUSES = ("Draft", "Changes Requested")
TERMINAL_STATUSES = ("Approved", "Rejected", "Cancelled")
DECISION_STATUSES = ("Approved", "Rejected", "Changes Requested")
REQUEST_TYPES = (
	"Room Change",
	"Visitor Stay",
	"Family Accommodation",
	"Exit Clearance",
)
TRANSITIONS = {
	"Draft": ("Submitted", "Cancelled"),
	"Changes Requested": ("Submitted", "Cancelled"),
	"Submitted": ("Approved", "Rejected", "Changes Requested", "Cancelled"),
}
DETAIL_FIELDS = (
	"reason",
	"preferred_date",
	"requested_bed",
	"visitor_name",
	"visit_start",
	"visit_end",
	"family_member_name",
	"relationship",
	"stay_start",
	"stay_end",
	"intended_checkout_date",
)


class AccommodationRequest(Document):
	def before_insert(self):
		self.requester = frappe.session.user
		if self.status not in (None, "", "Draft"):
			frappe.throw("A request starts as a draft")
		self.status = "Draft"

	def validate(self):
		if frappe.session.user == "Guest":
			frappe.throw("Login required", frappe.AuthenticationError)
		if self.is_new():
			self.requester = frappe.session.user
		self._keep_in_scope()
		self._force_staff_employee()
		if self.request_type not in REQUEST_TYPES:
			frappe.throw("Request type is required")
		if not self.employee or not frappe.db.exists("Employee", self.employee):
			frappe.throw("Employee not found")
		if not self.property or not frappe.db.exists("Property", self.property):
			frappe.throw("Property not found")
		_require_details(self)
		_assert_single_open(self)
		self._apply_transition()

	def on_update(self):
		try:
			from hotlync.accommodation.notify import notify_request

			notify_request(self)
		except Exception:
			return

	def _keep_in_scope(self):
		roles = set(frappe.get_roles())
		if roles & PRIVILEGED_ROLES:
			require_property(self.property)
			return
		if not self.is_new():
			_assert_party(self)

	def _force_staff_employee(self):
		if not _staff_only():
			return
		matches = active_employees_for_user(frappe.session.user)
		if len(matches) > 1:
			frappe.throw("This login is linked to more than one employee")
		if len(matches) != 1:
			frappe.throw("This login is not linked to an employee.")
		self.employee = matches[0]

	def _apply_transition(self):
		if self.is_new():
			if self.status != "Draft":
				frappe.throw("A request starts as a draft")
			return
		previous = self.get_doc_before_save().status
		if previous in TERMINAL_STATUSES:
			frappe.throw("That status change is not allowed")
		if self.status == previous:
			if previous not in EDITABLE_STATUSES:
				frappe.throw("This request can no longer be edited")
			return
		if self.status not in TRANSITIONS.get(previous, ()):
			frappe.throw("That status change is not allowed")
		if self.status in DECISION_STATUSES:
			_assert_approver(self)
		elif self.status == "Cancelled":
			_assert_party(self)
		elif self.status == "Submitted":
			_assert_party(self)
		_require_new_decision(self)
		if self.status == "Submitted" and not self.submission_date:
			self.submission_date = frappe.utils.today()


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
	if len(clauses) == 1:
		return clauses[0]
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
	return f"`tabAccommodation Request`.property in ({values})"


def _staff_clause(user):
	parts = [
		"`tabAccommodation Request`.requester = " + frappe.db.escape(user),
	]
	matches = active_employees_for_user(user)
	if len(matches) == 1:
		parts.append(
			"`tabAccommodation Request`.employee = " + frappe.db.escape(matches[0])
		)
	if len(parts) == 1:
		return parts[0]
	return "(" + " or ".join(parts) + ")"


def _owns(doc, user):
	if doc.requester == user:
		return True
	matches = active_employees_for_user(user)
	return len(matches) == 1 and doc.employee == matches[0]


def _staff_only():
	roles = set(frappe.get_roles())
	return "Staff" in roles and not roles.intersection(PRIVILEGED_ROLES)


def _assert_party(doc):
	if _owns(doc, frappe.session.user):
		return
	frappe.throw("Not permitted", frappe.PermissionError)


def _assert_approver(doc):
	roles = set(frappe.get_roles())
	if not roles.intersection(PRIVILEGED_ROLES):
		frappe.throw("Not permitted", frappe.PermissionError)
	require_property(doc.property)
	if frappe.session.user == doc.requester:
		frappe.throw("You cannot approve your own request")
	employee_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if employee_user and employee_user == frappe.session.user:
		frappe.throw("You cannot approve your own request")


def _require_new_decision(doc):
	before = doc.get_doc_before_save()
	previous = {row.name for row in (before.decisions or []) if row.name}
	matching = [
		row
		for row in (doc.decisions or [])
		if row.name not in previous
		and row.action == doc.status
		and row.actor == frappe.session.user
	]
	if not matching:
		frappe.throw("Record the decision before changing the status")
	if doc.status in ("Rejected", "Changes Requested") and not any(
		_filled(row.comment) for row in matching
	):
		frappe.throw("A comment is required")


def _require_details(doc):
	if doc.request_type == "Room Change":
		if not _filled(doc.reason):
			frappe.throw("Reason is required")
		if doc.requested_bed:
			location = location_for_bed(doc.requested_bed)
			if location.get("property") != doc.property:
				frappe.throw("Bed is not in the selected residence")
		return
	if doc.request_type == "Visitor Stay":
		if not _filled(doc.visitor_name):
			frappe.throw("Visitor name is required")
		if not doc.visit_start:
			frappe.throw("Visit start is required")
		if not doc.visit_end:
			frappe.throw("Visit end is required")
		if getdate(doc.visit_end) < getdate(doc.visit_start):
			frappe.throw("Visit end cannot be before visit start")
		return
	if doc.request_type == "Family Accommodation":
		if not _filled(doc.family_member_name):
			frappe.throw("Family member is required")
		if not _filled(doc.relationship):
			frappe.throw("Relationship is required")
		if not doc.stay_start:
			frappe.throw("Stay start is required")
		if not doc.stay_end:
			frappe.throw("Stay end is required")
		if getdate(doc.stay_end) < getdate(doc.stay_start):
			frappe.throw("Stay end cannot be before stay start")
		return
	if not doc.intended_checkout_date:
		frappe.throw("Intended check-out date is required")
	if not _filled(doc.reason):
		frappe.throw("Reason is required")


def _assert_single_open(doc):
	if doc.status not in OPEN_STATUSES:
		return
	filters = {
		"employee": doc.employee,
		"request_type": doc.request_type,
		"status": ["in", list(OPEN_STATUSES)],
	}
	if doc.name:
		filters["name"] = ["!=", doc.name]
	if frappe.db.exists("Accommodation Request", filters):
		frappe.throw("This employee already has an open request of that type.")


def _filled(value):
	return value is not None and str(value).strip() != ""


@frappe.whitelist()
def get_requests(name=None, status=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	filters = {}
	if name:
		filters["name"] = name
	if status:
		filters["status"] = status
	rows = frappe.get_list(
		"Accommodation Request",
		filters=filters,
		fields=[
			"name",
			"request_type",
			"status",
			"requester",
			"employee",
			"property",
			"submission_date",
			*DETAIL_FIELDS,
		],
		order_by="modified desc",
		limit=50,
	)
	if name and not rows:
		frappe.throw("Request not found")
	return {"requests": [_row(row) for row in rows], "properties": _property_choices()}


@frappe.whitelist()
def save_request(
	name=None,
	request_type=None,
	property=None,
	employee=None,
	reason=None,
	preferred_date=None,
	requested_bed=None,
	visitor_name=None,
	visit_start=None,
	visit_end=None,
	family_member_name=None,
	relationship=None,
	stay_start=None,
	stay_end=None,
	intended_checkout_date=None,
):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	if name:
		doc = _load(name)
	else:
		doc = frappe.new_doc("Accommodation Request")
		doc.status = "Draft"
	incoming = {
		"request_type": request_type,
		"property": property,
		"employee": employee,
		"reason": reason,
		"preferred_date": preferred_date,
		"requested_bed": requested_bed,
		"visitor_name": visitor_name,
		"visit_start": visit_start,
		"visit_end": visit_end,
		"family_member_name": family_member_name,
		"relationship": relationship,
		"stay_start": stay_start,
		"stay_end": stay_end,
		"intended_checkout_date": intended_checkout_date,
	}
	for fieldname, value in incoming.items():
		if value is not None:
			setattr(doc, fieldname, value)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


@frappe.whitelist()
def submit_request(name):
	return _change(name, "Submitted", None)


@frappe.whitelist()
def cancel_request(name, comment=None):
	return _change(name, "Cancelled", comment)


@frappe.whitelist()
def decide_request(name, action, comment=None):
	if action not in DECISION_STATUSES:
		frappe.throw("That status change is not allowed")
	return _change(name, action, comment)


def _change(name, status, comment):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	doc = _load(name)
	doc.status = status
	doc.append(
		"decisions",
		{
			"action": status,
			"actor": frappe.session.user,
			"comment": comment or "",
		},
	)
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


def _load(name):
	if not name or not frappe.db.exists("Accommodation Request", name):
		frappe.throw("Request not found")
	return frappe.get_doc("Accommodation Request", name)


def _present(doc):
	return _row(doc)


def _row(row):
	decisions = frappe.get_all(
		"Accommodation Request Decision",
		filters={
			"parent": row.name,
			"parenttype": "Accommodation Request",
		},
		fields=["action", "actor", "comment", "creation"],
		order_by="idx asc",
	)
	payload = {
		"name": row.name,
		"request_type": row.request_type,
		"status": row.status,
		"requester": row.requester,
		"employee": row.employee,
		"employee_name": frappe.db.get_value("Employee", row.employee, "employee_name"),
		"property": row.property,
		"property_name": frappe.db.get_value("Property", row.property, "property_name"),
		"submission_date": _text(row.submission_date),
		"decisions": [
			{
				"action": decision.action,
				"actor": decision.actor,
				"comment": decision.comment,
				"creation": _text(decision.creation),
			}
			for decision in decisions
		],
	}
	for fieldname in DETAIL_FIELDS:
		payload[fieldname] = _text(row.get(fieldname))
	return payload


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


def _text(value):
	if value is None:
		return None
	return str(value)
