import frappe

from hotlync.accommodation.access import GROUP_ROLES

REQUEST_EVENTS = {
	"Submitted": "was submitted",
	"Approved": "was approved",
	"Rejected": "was rejected",
	"Changes Requested": "needs changes",
}
REQUEST_TO_REQUESTER = {"Approved", "Rejected", "Changes Requested"}
TICKET_TO_REQUESTER = {"In Progress", "Waiting", "Resolved", "Closed"}


def notify_request(doc):
	before = doc.get_doc_before_save()
	if before is None or before.status == doc.status:
		return
	if doc.status not in REQUEST_EVENTS:
		return
	phrase = REQUEST_EVENTS[doc.status]
	subject = f"{doc.name} {phrase}."
	marker = _marker(doc.decisions)
	if doc.status == "Submitted":
		_notify_managers(doc, "Submitted", subject, marker)
		return
	if doc.status in REQUEST_TO_REQUESTER:
		_deliver(doc.requester, subject, doc.status, doc, marker)


def notify_ticket(doc):
	before = doc.get_doc_before_save()
	marker = _marker(doc.updates)
	if before is None:
		if doc.status == "Submitted" and doc.urgency == "Urgent":
			_notify_managers(
				doc,
				"Submitted",
				f"Urgent ticket {doc.name} was submitted.",
				marker,
			)
		return
	if doc.status == "Submitted" and before.status in ("Resolved", "Closed"):
		_notify_managers(doc, "Reopened", f"{doc.name} was reopened.", marker)
		return
	if doc.status == before.status and not _assignment_changed(doc, before):
		return
	if doc.status == "Assigned":
		event = "Reassigned" if before.status == "Assigned" else "Assigned"
		word = "reassigned" if event == "Reassigned" else "assigned"
		subject = f"{doc.name} was {word}."
		_deliver(doc.reported_by, subject, event, doc, marker)
		if doc.assignee:
			_deliver(doc.assignee, subject, event, doc, marker)
		return
	if doc.status in TICKET_TO_REQUESTER and doc.status != before.status:
		_deliver(
			doc.reported_by,
			f"{doc.name} is {doc.status}.",
			doc.status,
			doc,
			marker,
		)


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	if set(frappe.get_roles(user)) & GROUP_ROLES:
		return ""
	escaped = frappe.db.escape(user)
	return (
		f"(`tabOperational Notice`.recipient = {escaped} "
		"and `tabOperational Notice`.status = 'Delivered') "
		f"or (`tabOperational Notice`.actor = {escaped} "
		"and `tabOperational Notice`.status = 'Failed')"
	)


def has_permission(doc, ptype="read", user=None, debug=False):
	if ptype != "read":
		return False
	user = user or frappe.session.user
	if set(frappe.get_roles(user)) & GROUP_ROLES:
		return True
	if doc.status == "Delivered" and doc.recipient == user:
		return True
	if doc.status == "Failed" and doc.actor == user:
		return True
	return False


@frappe.whitelist()
def get_notices():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	return frappe.get_list(
		"Operational Notice",
		fields=[
			"name",
			"subject",
			"status",
			"detail",
			"channel",
			"event",
			"reference_doctype",
			"reference_name",
			"creation",
		],
		order_by="creation desc",
		limit=20,
	)


def _notify_managers(doc, event, subject, marker):
	for recipient in _managers(doc.property):
		_deliver(recipient, subject, event, doc, marker)


def _deliver(recipient, subject, event, doc, marker):
	actor = frappe.session.user
	if not recipient or recipient in ("Guest", actor):
		return
	key = _event_key(doc, event, recipient, "In App", marker)
	if frappe.db.exists("Operational Notice", {"event_key": key}):
		return
	try:
		frappe.db.savepoint("hotlync_notice")
		_insert_notice(
			recipient=recipient,
			actor=actor,
			subject=subject,
			event=event,
			channel="In App",
			status="Delivered",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			event_key=key,
			detail=None,
		)
	except Exception as exc:
		_rollback_notice()
		_record_failure(
			recipient=recipient,
			actor=actor,
			event=event,
			channel="In App",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			event_key=key,
			exc=exc,
		)
		return
	_maybe_email(recipient, subject, event, doc, marker, actor)


def _maybe_email(recipient, subject, event, doc, marker, actor):
	if not _outgoing_email():
		return
	key = _event_key(doc, event, recipient, "Email", marker)
	if frappe.db.exists("Operational Notice", {"event_key": key}):
		return
	try:
		frappe.db.savepoint("hotlync_notice")
		frappe.sendmail(
			recipients=[recipient],
			subject=subject,
			message=subject,
			now=False,
		)
		_insert_notice(
			recipient=recipient,
			actor=actor,
			subject=subject,
			event=event,
			channel="Email",
			status="Delivered",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			event_key=key,
			detail=None,
		)
	except Exception as exc:
		_rollback_notice()
		_record_failure(
			recipient=recipient,
			actor=actor,
			event=event,
			channel="Email",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			event_key=key,
			exc=exc,
		)


def _insert_notice(
	recipient,
	actor,
	subject,
	event,
	channel,
	status,
	reference_doctype,
	reference_name,
	event_key,
	detail,
):
	frappe.get_doc(
		{
			"doctype": "Operational Notice",
			"recipient": recipient,
			"actor": actor,
			"subject": subject,
			"event": event,
			"channel": channel,
			"status": status,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"event_key": event_key,
			"detail": detail,
		}
	).insert(ignore_permissions=True)


def _record_failure(
	recipient,
	actor,
	event,
	channel,
	reference_doctype,
	reference_name,
	event_key,
	exc,
):
	if frappe.db.exists("Operational Notice", {"event_key": event_key}):
		return
	try:
		_insert_failure(
			recipient=recipient,
			actor=actor,
			subject="A notice could not be delivered.",
			event=event,
			channel=channel,
			status="Failed",
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			event_key=event_key,
			detail=_safe(exc),
		)
	except Exception:
		return


def _insert_failure(**values):
	values["doctype"] = "Operational Notice"
	frappe.get_doc(values).insert(ignore_permissions=True)


def _managers(property_name):
	assigned = []
	if property_name:
		assigned = frappe.get_all(
			"Property Assignment",
			filters={"property": property_name},
			pluck="user",
		)
	admins = frappe.get_all(
		"Has Role",
		filters={"role": "Accommodation Admin", "parenttype": "User"},
		pluck="parent",
	)
	return sorted({user for user in assigned + admins if user and user != "Guest"})


def _assignment_changed(doc, before):
	for fieldname in ("assignee", "team_name", "contractor_name"):
		if _text(doc.get(fieldname)) != _text(before.get(fieldname)):
			return True
	return False


def _marker(rows):
	if not rows:
		return "0"
	last = rows[-1]
	return str(last.idx or len(rows))


def _event_key(doc, event, recipient, channel, marker):
	return f"{doc.doctype}:{doc.name}:{event}:{recipient}:{channel}:{marker}"


def _outgoing_email():
	return bool(
		frappe.db.exists(
			"Email Account",
			{"enable_outgoing": 1, "default_outgoing": 1},
		)
	)


def _rollback_notice():
	try:
		frappe.db.rollback(save_point="hotlync_notice")
	except Exception:
		return


def _safe(exc):
	text = str(exc).replace("\n", " ").strip()
	return text[:140] or "Delivery failed"


def _text(value):
	if value is None:
		return None
	text = str(value).strip()
	return text or None
