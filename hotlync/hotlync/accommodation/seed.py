import frappe


def execute():
	"""Load one property with beds in each status. Safe to run again."""
	if frappe.db.exists("Property", "SRA"):
		_ensure_sample_stay()
		_ensure_unallocated_employee()
		ensure_access_users()
		_print_counts()
		return

	property_doc = frappe.get_doc(
		{
			"doctype": "Property",
			"code": "SRA",
			"property_name": "Staff Residence A",
			"address": "HotLync staff residence",
			"status": "Active",
		}
	).insert(ignore_permissions=True)

	building = frappe.get_doc(
		{
			"doctype": "Building",
			"code": "BLD-A",
			"building_name": "Building A",
			"property": property_doc.name,
			"number_of_floors": 1,
			"status": "Active",
		}
	).insert(ignore_permissions=True)

	floor = frappe.get_doc(
		{
			"doctype": "Floor",
			"building": building.name,
			"floor_number": 1,
			"floor_name": "Floor 1",
			"status": "Active",
		}
	).insert(ignore_permissions=True)

	rooms = [
		("101", "Shared", 3),
		("102", "Shared", 3),
		("103", "Shared", 3),
	]
	room_docs = {}
	for room_number, room_type, capacity in rooms:
		room_docs[room_number] = frappe.get_doc(
			{
				"doctype": "Room",
				"floor": floor.name,
				"room_number": room_number,
				"room_type": room_type,
				"capacity": capacity,
				"status": "Available",
			}
		).insert(ignore_permissions=True)

	beds = [
		("101", "A", "Occupied"),
		("101", "B", "Occupied"),
		("101", "C", "Available"),
		("102", "A", "Occupied"),
		("102", "B", "Available"),
		("102", "C", "Maintenance"),
		("103", "A", "Occupied"),
		("103", "B", "Occupied"),
		("103", "C", "Occupied"),
	]
	for room_number, bed_number, status in beds:
		frappe.get_doc(
			{
				"doctype": "Bed",
				"room": room_docs[room_number].name,
				"bed_number": bed_number,
				"status": status,
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()
	_ensure_sample_stay()
	_ensure_unallocated_employee()
	ensure_access_users()
	_print_counts()


def _ensure_sample_stay():
	if frappe.db.exists("Accommodation Allocation", {"reason": "Phase 0 sample stay"}):
		return
	room = frappe.db.get_value("Room", {"room_number": "101"}, "name")
	if not room:
		return
	try:
		employee = _ensure_sample_employee()
		if not employee:
			return
		bed = frappe.db.get_value("Bed", {"bed_number": "A", "room": room}, "name")
		frappe.get_doc(
			{
				"doctype": "Accommodation Allocation",
				"employee": employee,
				"property": "SRA",
				"building": "BLD-A",
				"room": room,
				"bed": bed,
				"allocation_date": "2026-10-08",
				"check_in_date": "2026-10-08",
				"status": "Checked In",
				"reason": "Phase 0 sample stay",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		print("Sample employee was not created. Accommodation master data is loaded.")
		print(frappe.get_traceback())


def _ensure_sample_employee():
	existing = frappe.db.get_value("Employee", {"employee_name": "John Resident"}, "name")
	if existing:
		return existing
	if not frappe.db.exists("DocType", "Employee"):
		return None
	if not frappe.db.exists("DocType", "Company"):
		return None

	if frappe.db.exists("DocType", "Warehouse Type") and not frappe.db.exists("Warehouse Type", "Transit"):
		warehouse_type = frappe.get_doc({"doctype": "Warehouse Type"})
		warehouse_type.name = "Transit"
		warehouse_type.insert(ignore_permissions=True)

	company = frappe.db.get_value("Company", {}, "name")
	if not company:
		company_doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "HotLync",
				"abbr": "HL",
				"default_currency": "AED",
				"country": "United Arab Emirates",
			}
		).insert(ignore_permissions=True)
		company = company_doc.name

	if frappe.db.exists("DocType", "Gender") and not frappe.db.exists("Gender", "Male"):
		frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)

	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "John",
			"last_name": "Resident",
			"gender": "Male",
			"date_of_birth": "1995-01-15",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
		}
	).insert(ignore_permissions=True)
	return employee.name


def _ensure_unallocated_employee():
	if frappe.db.get_value("Employee", {"employee_name": "Sara Vacant"}, "name"):
		return
	company = frappe.db.get_value("Company", {}, "name")
	if not company or not frappe.db.exists("DocType", "Employee"):
		return
	if frappe.db.exists("DocType", "Gender") and not frappe.db.exists("Gender", "Female"):
		frappe.get_doc({"doctype": "Gender", "gender": "Female"}).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Sara",
			"last_name": "Vacant",
			"gender": "Female",
			"date_of_birth": "1998-04-02",
			"date_of_joining": "2026-10-01",
			"status": "Active",
			"company": company,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()


def ensure_access_users():
	"""Create the Phase 0 Staff and Accommodation Admin logins."""
	_ensure_user("staff@hotlync.local", "John", "Resident", "Staff", "Staff@123")
	_ensure_user(
		"admin@hotlync.local",
		"Accommodation",
		"Admin",
		"Accommodation Admin",
		"Admin@123",
	)
	john = frappe.db.get_value("Employee", {"employee_name": "John Resident"}, "name")
	if john:
		frappe.db.set_value("Employee", john, "user_id", "staff@hotlync.local")
	frappe.db.commit()


def _ensure_user(email, first_name, last_name, role, password):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"last_name": last_name,
				"enabled": 1,
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.insert(ignore_permissions=True)
	user.enabled = 1
	user.send_welcome_email = 0
	user.new_password = password
	if role not in {row.role for row in user.roles}:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)


def _print_counts():
	for doctype in ("Property", "Building", "Floor", "Room", "Bed", "Accommodation Allocation"):
		print(f"{doctype}: {frappe.db.count(doctype)}")
	for status in ("Available", "Occupied", "Maintenance"):
		print(f"Beds {status}: {frappe.db.count('Bed', {'status': status})}")
