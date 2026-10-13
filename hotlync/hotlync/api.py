import frappe

from hotlync.accommodation.access import (
	active_employees_for_user,
	property_scope,
	require_property,
)
from hotlync.accommodation.workflow import (
	ACTIVE_STATUSES,
	allocation_payload,
	apply_bed_status,
	assert_bed_assignable,
	assert_employee_assignable,
	assert_location_complete,
	location_for_bed,
	location_for_room,
	lock_rows,
	locked_allocation,
	require_manager,
)


@frappe.whitelist()
def get_session():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	from frappe.sessions import get_csrf_token

	return {"user": frappe.session.user, "csrf_token": get_csrf_token(), "roles": frappe.get_roles()}


@frappe.whitelist()
def get_my_stay(employee=None):
	"""The signed-in user's stay. A client-supplied employee id is ignored."""
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	matches = active_employees_for_user(frappe.session.user)
	if len(matches) > 1:
		frappe.throw("This login is linked to more than one employee")
	if not matches:
		return {"mapped": False, "current": None, "previous": []}
	rows = frappe.get_all(
		"Accommodation Allocation",
		filters={"employee": matches[0]},
		fields=[
			"name",
			"employee",
			"status",
			"property",
			"building",
			"room",
			"bed",
			"check_in_date",
			"check_out_date",
		],
		order_by="modified desc",
		limit=20,
	)
	stays = [_stay_for_staff(row) for row in rows]
	current = next((row for row in stays if row["status"] == "Checked In"), None)
	previous = [row for row in stays if row is not current]
	return {"mapped": True, "current": current, "previous": previous}


def _stay_for_staff(row):
	property_name = frappe.db.get_value("Property", row.property, "property_name")
	building_name = frappe.db.get_value("Building", row.building, "building_name")
	room_number, floor = frappe.db.get_value("Room", row.room, ["room_number", "floor"]) or (None, None)
	floor_name = frappe.db.get_value("Floor", floor, "floor_name") if floor else None
	bed_number = frappe.db.get_value("Bed", row.bed, "bed_number")
	return {
		"name": row.name,
		"employee": row.employee,
		"status": row.status,
		"property_name": property_name,
		"building_name": building_name,
		"floor_name": floor_name,
		"room_number": room_number,
		"bed_number": bed_number,
		"check_in_date": row.check_in_date,
		"check_out_date": row.check_out_date,
	}


@frappe.whitelist()
def get_dashboard(property=None):
	require_manager()
	return _bed_counts(_selected_properties(property))


@frappe.whitelist()
def get_accommodation(property=None):
	require_manager()
	occupant = _occupants_by_bed()
	filters = {}
	selected = _selected_properties(property)
	if selected is not None:
		if not selected:
			return []
		filters["name"] = ["in", selected]
	properties = frappe.get_all(
		"Property",
		fields=["name", "property_name", "code", "status"],
		filters=filters,
		order_by="property_name asc",
	)
	for property_doc in properties:
		property_doc["buildings"] = frappe.get_all(
			"Building",
			filters={"property": property_doc.name},
			fields=["name", "building_name", "code"],
			order_by="building_name asc",
		)
		for building in property_doc["buildings"]:
			building["floors"] = frappe.get_all(
				"Floor",
				filters={"building": building.name},
				fields=["name", "floor_name", "floor_number"],
				order_by="floor_number asc",
			)
			for floor in building["floors"]:
				floor["rooms"] = frappe.get_all(
					"Room",
					filters={"floor": floor.name},
					fields=["name", "room_number", "room_type", "capacity", "status"],
					order_by="room_number asc",
				)
				for room in floor["rooms"]:
					beds = frappe.get_all(
						"Bed",
						filters={"room": room.name},
						fields=["name", "bed_number", "status"],
						order_by="bed_number asc",
					)
					for bed in beds:
						stay = occupant.get(bed.name)
						bed["employee"] = stay.get("employee") if stay else None
						bed["employee_name"] = stay.get("employee_name") if stay else None
						bed["allocation"] = stay.get("name") if stay else None
					room["beds"] = beds
	return properties


@frappe.whitelist()
def get_employees(search=None):
	require_manager()
	filters = {"status": "Active"}
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = [
			["Employee", "employee_name", "like", like],
			["Employee", "name", "like", like],
		]
	kwargs = {
		"filters": filters,
		"fields": ["name", "employee_name", "department", "designation"],
		"order_by": "employee_name asc",
		"limit": 20,
	}
	if or_filters:
		kwargs["or_filters"] = or_filters
	return frappe.get_all("Employee", **kwargs)


@frappe.whitelist()
def get_available_beds(room=None):
	require_manager()
	if room:
		require_property(_property_for_room(room))
	blocked = set(
		frappe.get_all(
			"Accommodation Allocation",
			filters={"status": ["in", ["Draft", "Checked In"]]},
			pluck="bed",
		)
	)
	filters = {"status": "Available"}
	if room:
		filters["room"] = room
	beds = frappe.get_all(
		"Bed",
		filters=filters,
		fields=["name", "bed_number", "room", "status"],
		order_by="name asc",
	)
	scope = property_scope()
	available = []
	for bed in beds:
		if bed.name in blocked:
			continue
		location = location_for_bed(bed.name)
		if not location.get("property") or not location.get("building"):
			continue
		if scope is not None and location["property"] not in scope:
			continue
		room_number = frappe.db.get_value("Room", bed.room, "room_number")
		bed["room_number"] = room_number
		bed["building"] = location["building"]
		bed["building_name"] = frappe.db.get_value("Building", location["building"], "building_name")
		bed["property"] = location["property"]
		available.append(bed)
	return available


@frappe.whitelist()
def get_allocations(status=None, property=None):
	require_manager()
	filters = {}
	if status:
		filters["status"] = status
	selected = _selected_properties(property)
	if selected is not None:
		if not selected:
			return []
		filters["property"] = ["in", selected]
	rows = frappe.get_all(
		"Accommodation Allocation",
		filters=filters,
		fields=[
			"name",
			"employee",
			"bed",
			"room",
			"building",
			"status",
			"check_in_date",
			"check_out_date",
			"allocation_date",
			"reason",
		],
		order_by="modified desc",
		limit=50,
	)
	for row in rows:
		row["employee_name"] = frappe.db.get_value("Employee", row.employee, "employee_name")
		row["bed_number"] = frappe.db.get_value("Bed", row.bed, "bed_number")
		row["room_number"] = frappe.db.get_value("Room", row.room, "room_number")
		row["building_name"] = frappe.db.get_value("Building", row.building, "building_name")
	return rows


@frappe.whitelist()
def get_accommodation_report(property=None):
	"""Occupancy and stay rows for the residences this login may open.

	Bed counts use the same residence link as the dashboard. A draft is an
	active allocation and leaves the bed available. Checked In is the current
	assignment. A transfer stays on its own row; the destination is the later
	stay, not a second field. Occupied divided by total is the dashboard
	display. It is not a utilization formula.
	"""
	require_manager()
	selected = _selected_properties(property)
	counts = _bed_counts(selected)
	today = frappe.utils.today()
	return {
		"total": counts["total"],
		"occupied": counts["occupied"],
		"available": counts["available"],
		"maintenance": counts["maintenance"],
		"check_ins_today": _dated_count(selected, "check_in_date", today),
		"check_outs_today": _dated_count(selected, "check_out_date", today),
		"buildings": _building_counts(selected),
		"active": _stay_rows(
			selected,
			{"status": ["in", list(ACTIVE_STATUSES)]},
			"modified desc",
		),
		"assignments": _stay_rows(
			selected,
			{"status": "Checked In"},
			"check_in_date desc",
		),
		"transfers": _stay_rows(
			selected,
			{"status": "Transferred"},
			"modified desc",
		),
		"check_ins": _stay_rows(
			selected,
			{"check_in_date": ["is", "set"]},
			"check_in_date desc",
		),
		"check_outs": _stay_rows(
			selected,
			{"check_out_date": ["is", "set"]},
			"check_out_date desc",
		),
	}


def _attempt(operation):
	"""Run once more after a database conflict so the second read sees the committed stay."""
	try:
		return operation()
	except frappe.QueryDeadlockError:
		frappe.db.rollback()
		try:
			return operation()
		except frappe.QueryDeadlockError:
			frappe.throw("That bed or employee already has an active allocation")


@frappe.whitelist()
def allocate_bed(employee, bed, allocation_date=None):
	return _attempt(lambda: _allocate_bed(employee, bed, allocation_date))


def _allocate_bed(employee, bed, allocation_date=None):
	require_manager()
	location = location_for_bed(bed)
	assert_location_complete(location)
	require_property(location["property"])
	assert_employee_assignable(employee)
	assert_bed_assignable(bed)
	doc = frappe.get_doc(
		{
			"doctype": "Accommodation Allocation",
			"employee": employee,
			"bed": bed,
			"property": location["property"],
			"building": location["building"],
			"room": location["room"],
			"allocation_date": allocation_date or frappe.utils.today(),
			"status": "Draft",
		}
	)
	try:
		doc.insert()
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.throw("That bed or employee already has an active allocation")
	return allocation_payload(doc)


@frappe.whitelist()
def check_in(allocation, check_in_date=None):
	return _attempt(lambda: _check_in(allocation, check_in_date))


def _check_in(allocation, check_in_date=None):
	require_manager()
	if not allocation or not frappe.db.exists("Accommodation Allocation", allocation):
		frappe.throw("Allocation not found")
	doc = frappe.get_doc("Accommodation Allocation", allocation)
	require_property(doc.property)
	location = location_for_bed(doc.bed)
	assert_location_complete(location)
	require_property(location["property"])
	if doc.status != "Draft":
		frappe.throw("Only a draft allocation can be checked in")
	assert_employee_assignable(doc.employee, ignore_allocation=doc.name)
	lock_rows("Employee", [doc.employee])
	lock_rows("Bed", [doc.bed])
	current = locked_allocation(allocation)
	if not current or current.status != "Draft":
		frappe.throw("Only a draft allocation can be checked in")
	assert_bed_assignable(current.bed, ignore_allocation=current.name)
	doc.status = "Checked In"
	doc.check_in_date = check_in_date or frappe.utils.today()
	try:
		doc.save(ignore_version=False)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.throw("That bed or employee already has an active allocation")
	return allocation_payload(doc)


@frappe.whitelist()
def transfer_stay(allocation, bed, reason=None):
	return _attempt(lambda: _transfer_stay(allocation, bed, reason))


def _transfer_stay(allocation, bed, reason=None):
	require_manager()
	if not allocation or not frappe.db.exists("Accommodation Allocation", allocation):
		frappe.throw("Allocation not found")
	doc = frappe.get_doc("Accommodation Allocation", allocation)
	require_property(doc.property)
	if doc.status != "Checked In":
		frappe.throw("Only a checked-in stay can be transferred")
	if bed == doc.bed:
		frappe.throw("Choose a different bed")
	source = location_for_bed(doc.bed)
	assert_location_complete(source)
	if (
		source["property"] != doc.property
		or source["building"] != doc.building
		or source["room"] != doc.room
	):
		frappe.throw("Bed is not in the recorded residence")
	destination = location_for_bed(bed)
	assert_location_complete(destination)
	require_property(destination["property"])
	assert_employee_assignable(doc.employee, ignore_allocation=doc.name)
	lock_rows("Employee", [doc.employee])
	lock_rows("Bed", [doc.bed, bed])
	current = locked_allocation(doc.name)
	if not current or current.status != "Checked In":
		frappe.throw("Only a checked-in stay can be transferred")
	if bed == current.bed:
		frappe.throw("Choose a different bed")
	source = location_for_bed(current.bed)
	assert_location_complete(source)
	if (
		source["property"] != current.property
		or source["building"] != current.building
		or source["room"] != current.room
	):
		frappe.throw("Bed is not in the recorded residence")
	assert_bed_assignable(bed)
	frappe.db.savepoint("hotlync_transfer")
	try:
		doc.status = "Transferred"
		if reason:
			doc.reason = reason
		doc.save(ignore_version=False)
		new_doc = frappe.get_doc(
			{
				"doctype": "Accommodation Allocation",
				"employee": doc.employee,
				"bed": bed,
				"property": destination["property"],
				"building": destination["building"],
				"room": destination["room"],
				"allocation_date": frappe.utils.today(),
				"check_in_date": frappe.utils.today(),
				"status": "Checked In",
				"reason": reason,
			}
		)
		new_doc.insert()
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point="hotlync_transfer")
		frappe.throw("That bed or employee already has an active allocation")
	except Exception:
		frappe.db.rollback(save_point="hotlync_transfer")
		raise
	return {
		"previous": allocation_payload(doc),
		"current": allocation_payload(new_doc),
	}


@frappe.whitelist()
def check_out(allocation, check_out_date=None):
	return _attempt(lambda: _check_out(allocation, check_out_date))


def _check_out(allocation, check_out_date=None):
	require_manager()
	if not allocation or not frappe.db.exists("Accommodation Allocation", allocation):
		frappe.throw("Allocation not found")
	doc = frappe.get_doc("Accommodation Allocation", allocation)
	require_property(doc.property)
	if doc.status != "Checked In":
		frappe.throw("Only a checked-in stay can be checked out")
	source = location_for_bed(doc.bed)
	assert_location_complete(source)
	if (
		source["property"] != doc.property
		or source["building"] != doc.building
		or source["room"] != doc.room
	):
		frappe.throw("Bed is not in the recorded residence")
	require_property(source["property"])
	lock_rows("Employee", [doc.employee])
	lock_rows("Bed", [doc.bed])
	current = locked_allocation(allocation)
	if not current or current.status != "Checked In":
		frappe.throw("Only a checked-in stay can be checked out")
	source = location_for_bed(current.bed)
	assert_location_complete(source)
	if (
		source["property"] != current.property
		or source["building"] != current.building
		or source["room"] != current.room
	):
		frappe.throw("Bed is not in the recorded residence")
	doc.status = "Completed"
	doc.check_out_date = check_out_date or frappe.utils.today()
	doc.save(ignore_version=False)
	return allocation_payload(doc)


def _property_for_room(room):
	return location_for_room(room).get("property")


def _selected_properties(property_name):
	if property_name:
		require_property(property_name)
		return [property_name]
	return property_scope()


_BED_FROM = """
	from `tabBed` b
	inner join `tabRoom` r on r.name = b.room
	inner join `tabFloor` f on f.name = r.floor
	inner join `tabBuilding` g on g.name = f.building
	where ifnull(g.property, '') != ''
	and ifnull(r.building, '') in ('', f.building)
"""

_STATUS_LABELS = {
	"Occupied": "occupied",
	"Available": "available",
	"Maintenance": "maintenance",
}


def _bed_rows(select, property_names, group_by):
	if property_names is not None and not property_names:
		return []
	query = select + _BED_FROM
	params = []
	if property_names is not None:
		query += " and g.property in %s"
		params.append(property_names)
	query += group_by
	if params:
		return frappe.db.sql(query, params)
	return frappe.db.sql(query)


def _empty_counts():
	return {"total": 0, "occupied": 0, "available": 0, "maintenance": 0}


def _apply_status(counts, status, count):
	counts["total"] += count
	label = _STATUS_LABELS.get(status)
	if label:
		counts[label] += count


def _bed_counts(property_names):
	counts = _empty_counts()
	for status, count in _bed_rows(
		"select b.status, count(*)",
		property_names,
		" group by b.status",
	):
		_apply_status(counts, status, count)
	return counts


def _building_counts(property_names):
	buildings = {}
	order = []
	rows = _bed_rows(
		"select g.name, g.building_name, b.status, count(*)",
		property_names,
		" group by g.name, g.building_name, b.status order by g.building_name asc",
	)
	for name, building_name, status, count in rows:
		if name not in buildings:
			buildings[name] = {"name": name, "building_name": building_name, **_empty_counts()}
			order.append(name)
		_apply_status(buildings[name], status, count)
	return [buildings[name] for name in order]


def _dated_count(property_names, field, day):
	if property_names is not None and not property_names:
		return 0
	filters = {field: day}
	if property_names is not None:
		filters["property"] = ["in", property_names]
	return frappe.db.count("Accommodation Allocation", filters)


def _stay_rows(property_names, filters, order_by):
	if property_names is not None and not property_names:
		return []
	query = dict(filters)
	if property_names is not None:
		query["property"] = ["in", property_names]
	rows = frappe.get_all(
		"Accommodation Allocation",
		filters=query,
		fields=[
			"name",
			"employee",
			"property",
			"building",
			"room",
			"bed",
			"status",
			"check_in_date",
			"check_out_date",
			"allocation_date",
			"reason",
		],
		order_by=order_by,
		limit=50,
	)
	for row in rows:
		row["employee_name"] = frappe.db.get_value("Employee", row.employee, "employee_name")
		row["bed_number"] = frappe.db.get_value("Bed", row.bed, "bed_number")
		row["room_number"] = frappe.db.get_value("Room", row.room, "room_number")
		row["building_name"] = frappe.db.get_value("Building", row.building, "building_name")
		row["property_name"] = frappe.db.get_value("Property", row.property, "property_name")
	return rows


def _occupants_by_bed():
	rows = frappe.get_all(
		"Accommodation Allocation",
		filters={"status": "Checked In"},
		fields=["name", "bed", "employee"],
	)
	occupants = {}
	for row in rows:
		row["employee_name"] = frappe.db.get_value("Employee", row.employee, "employee_name")
		occupants[row.bed] = row
	return occupants
