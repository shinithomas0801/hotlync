import frappe

ACTIVE_STATUSES = ("Draft", "Checked In")
PRIVILEGED_ROLES = {"System Manager", "Accommodation Admin", "Accommodation Manager"}


def require_manager():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	roles = set(frappe.get_roles())
	if not roles.intersection(PRIVILEGED_ROLES):
		frappe.throw("Not permitted", frappe.PermissionError)


def location_for_room(room):
	"""Residence of a room. A room building that disagrees with its floor is unresolved."""
	if not room:
		return {"property": None, "building": None, "room": None}
	floor, room_building = frappe.db.get_value("Room", room, ["floor", "building"]) or (None, None)
	floor_building = frappe.db.get_value("Floor", floor, "building") if floor else None
	if room_building and floor_building and room_building != floor_building:
		return {"property": None, "building": None, "room": room}
	building = floor_building or room_building
	property_name = frappe.db.get_value("Building", building, "property") if building else None
	return {"property": property_name, "building": building, "room": room}


def location_for_bed(bed):
	room = frappe.db.get_value("Bed", bed, "room")
	if not room:
		frappe.throw("Bed not found")
	return location_for_room(room)


def assert_location_complete(location):
	if not location.get("property") or not location.get("building") or not location.get("room"):
		frappe.throw("Bed is not linked to a residence")


def lock_rows(doctype, names):
	"""Serialize stays that touch the same employee or bed."""
	for name in sorted({name for name in names if name}):
		frappe.db.sql(
			f"select name from `tab{doctype}` where name=%s for update",
			name,
		)


def locked_allocation(name):
	"""Read the stay under a row lock so a waiting request sees the latest status."""
	rows = frappe.db.sql(
		"""
		select name, status, employee, bed, property, building, room
		from `tabAccommodation Allocation`
		where name=%s
		for update
		""",
		name,
		as_dict=True,
	)
	return rows[0] if rows else None


def assert_employee_assignable(employee, ignore_allocation=None):
	lock_rows("Employee", [employee])
	if not frappe.db.exists("Employee", employee):
		frappe.throw("Employee not found")
	if frappe.db.get_value("Employee", employee, "status") != "Active":
		frappe.throw("Employee is not active")
	filters = {"employee": employee, "status": ["in", list(ACTIVE_STATUSES)]}
	if ignore_allocation:
		filters["name"] = ["!=", ignore_allocation]
	if frappe.db.exists("Accommodation Allocation", filters):
		frappe.throw("Employee already has an active allocation")


def assert_bed_assignable(bed, ignore_allocation=None):
	lock_rows("Bed", [bed])
	status = frappe.db.get_value("Bed", bed, "status")
	if not status:
		frappe.throw("Bed not found")
	if status == "Maintenance":
		frappe.throw("A maintenance bed cannot be allocated")
	filters = {"bed": bed, "status": ["in", list(ACTIVE_STATUSES)]}
	if ignore_allocation:
		filters["name"] = ["!=", ignore_allocation]
	if frappe.db.exists("Accommodation Allocation", filters):
		frappe.throw("Bed already has an active allocation")
	if status == "Occupied" and not _is_current_stay(bed, ignore_allocation):
		frappe.throw("Bed is occupied")


def _is_current_stay(bed, allocation_name):
	if not allocation_name:
		return False
	current_bed, current_status = frappe.db.get_value(
		"Accommodation Allocation",
		allocation_name,
		["bed", "status"],
	) or (None, None)
	return current_status == "Checked In" and current_bed == bed


def apply_bed_status(allocation):
	previous = allocation.get_doc_before_save()
	if allocation.status == "Checked In":
		frappe.db.set_value("Bed", allocation.bed, "status", "Occupied")
	if previous and previous.status == "Checked In" and allocation.status != "Checked In":
		still_here = frappe.db.exists(
			"Accommodation Allocation",
			{
				"bed": previous.bed,
				"status": "Checked In",
				"name": ["!=", allocation.name],
			},
		)
		if not still_here:
			frappe.db.set_value("Bed", previous.bed, "status", "Available")


def allocation_payload(allocation):
	employee_name = frappe.db.get_value("Employee", allocation.employee, "employee_name")
	bed_number, room = frappe.db.get_value("Bed", allocation.bed, ["bed_number", "room"])
	room_number = frappe.db.get_value("Room", room, "room_number") if room else None
	building_name = frappe.db.get_value("Building", allocation.building, "building_name")
	return {
		"name": allocation.name,
		"employee": allocation.employee,
		"employee_name": employee_name,
		"property": allocation.property,
		"building": allocation.building,
		"building_name": building_name,
		"room": allocation.room,
		"room_number": room_number,
		"bed": allocation.bed,
		"bed_number": bed_number,
		"status": allocation.status,
		"allocation_date": allocation.allocation_date,
		"check_in_date": allocation.check_in_date,
		"check_out_date": allocation.check_out_date,
		"reason": allocation.reason,
	}
