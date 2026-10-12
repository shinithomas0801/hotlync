import frappe

from hotlync.accommodation.workflow import (
	allocation_payload,
	apply_bed_status,
	assert_bed_assignable,
	assert_employee_assignable,
	location_for_bed,
	lock_rows,
	require_manager,
)


@frappe.whitelist()
def get_session():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	from frappe.sessions import get_csrf_token

	return {"user": frappe.session.user, "csrf_token": get_csrf_token()}


@frappe.whitelist()
def get_dashboard():
	require_manager()
	total = frappe.db.count("Bed")
	occupied = frappe.db.count("Bed", {"status": "Occupied"})
	available = frappe.db.count("Bed", {"status": "Available"})
	maintenance = frappe.db.count("Bed", {"status": "Maintenance"})
	return {
		"total": total,
		"occupied": occupied,
		"available": available,
		"maintenance": maintenance,
	}


@frappe.whitelist()
def get_accommodation():
	require_manager()
	occupant = _occupants_by_bed()
	properties = frappe.get_all(
		"Property",
		fields=["name", "property_name", "code", "status"],
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
	available = []
	for bed in beds:
		if bed.name in blocked:
			continue
		room_number, building = frappe.db.get_value("Room", bed.room, ["room_number", "building"])
		building_name = frappe.db.get_value("Building", building, "building_name")
		property_name = frappe.db.get_value("Building", building, "property")
		bed["room_number"] = room_number
		bed["building"] = building
		bed["building_name"] = building_name
		bed["property"] = property_name
		available.append(bed)
	return available


@frappe.whitelist()
def get_allocations(status=None):
	require_manager()
	filters = {}
	if status:
		filters["status"] = status
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
def allocate_bed(employee, bed, allocation_date=None):
	require_manager()
	assert_employee_assignable(employee)
	assert_bed_assignable(bed)
	location = location_for_bed(bed)
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
	except frappe.DuplicateEntryError:
		frappe.throw("That bed or employee already has an active allocation")
	return allocation_payload(doc)


@frappe.whitelist()
def check_in(allocation, check_in_date=None):
	require_manager()
	doc = frappe.get_doc("Accommodation Allocation", allocation)
	if doc.status != "Draft":
		frappe.throw("Only a draft allocation can be checked in")
	lock_rows("Employee", [doc.employee])
	lock_rows("Bed", [doc.bed])
	assert_bed_assignable(doc.bed, ignore_allocation=doc.name)
	doc.status = "Checked In"
	doc.check_in_date = check_in_date or frappe.utils.today()
	try:
		doc.save()
	except frappe.DuplicateEntryError:
		frappe.throw("That bed or employee already has an active allocation")
	return allocation_payload(doc)


@frappe.whitelist()
def transfer_stay(allocation, bed, reason=None):
	require_manager()
	doc = frappe.get_doc("Accommodation Allocation", allocation)
	if doc.status != "Checked In":
		frappe.throw("Only a checked-in stay can be transferred")
	if bed == doc.bed:
		frappe.throw("Choose a different bed")
	lock_rows("Employee", [doc.employee])
	lock_rows("Bed", [doc.bed, bed])
	assert_bed_assignable(bed)
	doc.status = "Transferred"
	if reason:
		doc.reason = reason
	doc.save()
	location = location_for_bed(bed)
	new_doc = frappe.get_doc(
		{
			"doctype": "Accommodation Allocation",
			"employee": doc.employee,
			"bed": bed,
			"property": location["property"],
			"building": location["building"],
			"room": location["room"],
			"allocation_date": frappe.utils.today(),
			"check_in_date": frappe.utils.today(),
			"status": "Checked In",
			"reason": reason,
		}
	)
	try:
		new_doc.insert()
	except frappe.DuplicateEntryError:
		frappe.throw("That bed or employee already has an active allocation")
	return {
		"previous": allocation_payload(doc),
		"current": allocation_payload(new_doc),
	}


@frappe.whitelist()
def check_out(allocation, check_out_date=None):
	require_manager()
	doc = frappe.get_doc("Accommodation Allocation", allocation)
	if doc.status != "Checked In":
		frappe.throw("Only a checked-in stay can be checked out")
	lock_rows("Employee", [doc.employee])
	lock_rows("Bed", [doc.bed])
	doc.status = "Completed"
	doc.check_out_date = check_out_date or frappe.utils.today()
	doc.save()
	return allocation_payload(doc)


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
