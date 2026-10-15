import os

import frappe
from frappe.model.document import Document

from hotlync.accommodation.access import GROUP_ROLES, property_scope, require_property
from hotlync.accommodation.workflow import PRIVILEGED_ROLES, location_for_room, require_manager

LOCKED = (
	"description",
	"category",
	"status",
	"property",
	"found_location",
	"room",
	"found_on",
	"custodian",
)


class FoundItem(Document):
	def on_trash(self):
		frappe.throw("A found item cannot be deleted")

	def check_permission(self, permtype="read", permlevel=None):
		if self.flags.ignore_permissions:
			return
		if not self.is_new():
			scope = property_scope()
			if scope is not None and self.property not in scope:
				frappe.throw(
					f"Found Item {self.name} not found",
					frappe.DoesNotExistError,
				)
		super().check_permission(permtype, permlevel)

	def _validate_links(self):
		if self.property:
			_require_property_record(self.property)
		super()._validate_links()

	def validate(self):
		if frappe.session.user == "Guest":
			frappe.throw("Login required", frappe.AuthenticationError)
		require_manager()
		self.description = _text(self.description)
		if not self.description:
			frappe.throw("A description is required")
		self.category = _text(self.category)
		self.found_location = _text(self.found_location)
		if not self.found_location:
			frappe.throw("A found location is required")
		self.found_on = _found_on(self.found_on)
		_require_property_record(self.property)
		require_property(self.property)
		if not self.room:
			self.room = None
		else:
			location = location_for_room(self.room)
			if location.get("property") != self.property:
				frappe.throw("Room is not in the selected residence")
		if self.is_new():
			self._start_reported()
			return
		self._lock_registration()

	def _start_reported(self):
		if self.status not in (None, "", "Reported"):
			frappe.throw("A found item starts as reported")
		if self.events:
			frappe.throw("A found item starts as reported")
		if self.image:
			frappe.throw("Add the image after the item is registered")
		if self.custodian and self.custodian != frappe.session.user:
			frappe.throw("The custodian is the person registering the item")
		self.status = "Reported"
		self.custodian = frappe.session.user
		self.append(
			"events",
			{
				"action": "Reported",
				"actor": frappe.session.user,
				"occurred_on": frappe.utils.now(),
			},
		)

	def _lock_registration(self):
		before = self.get_doc_before_save()
		for fieldname in LOCKED:
			if _text(before.get(fieldname)) != _text(self.get(fieldname)):
				frappe.throw("A found item cannot be changed")
		_lock_events(before, self)
		if _text(before.image) == _text(self.image):
			return
		if before.image or not _private_image(self):
			frappe.throw("A found item cannot be changed")


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles & GROUP_ROLES:
		return ""
	if "Accommodation Manager" not in roles:
		return "1=0"
	scope = property_scope(user)
	if scope is None:
		return ""
	if not scope:
		return "1=0"
	values = ", ".join(frappe.db.escape(name) for name in scope)
	return f"`tabFound Item`.property in ({values})"


def has_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	if ptype == "delete":
		return False
	roles = set(frappe.get_roles(user))
	if not roles.intersection(PRIVILEGED_ROLES):
		return False
	scope = property_scope(user)
	if scope is None:
		return True
	return bool(doc.property and doc.property in scope)


@frappe.whitelist()
def get_found_items(name=None):
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	require_manager()
	filters = {}
	if name:
		filters["name"] = name
	rows = frappe.get_list(
		"Found Item",
		filters=filters,
		fields=[
			"name",
			"description",
			"category",
			"status",
			"property",
			"found_location",
			"room",
			"found_on",
			"custodian",
			"image",
		],
		order_by="modified desc",
		limit=50,
	)
	if name and not rows:
		frappe.throw("Found item not found")
	return {
		"items": [_row(row) for row in rows],
		"properties": _property_choices(),
	}


@frappe.whitelist()
def register_found_item(
	description=None,
	property=None,
	found_location=None,
	found_on=None,
	category=None,
	room=None,
	custodian=None,
):
	require_manager()
	for _attempt in range(3):
		frappe.db.savepoint("found_item_register")
		doc = frappe.new_doc("Found Item")
		doc.description = description
		doc.category = category
		doc.property = property
		doc.found_location = found_location
		doc.found_on = found_on
		doc.room = room or None
		doc.custodian = custodian
		doc.status = "Reported"
		try:
			doc.name = _next_found_reference()
			doc.flags.name_set = True
			doc.save(ignore_permissions=True, ignore_version=False)
			return _present(doc)
		except (frappe.QueryDeadlockError, frappe.DuplicateEntryError):
			_rollback_registration()
	frappe.throw("The found item could not be registered. Try again.")


@frappe.whitelist()
def attach_found_item_image():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.AuthenticationError)
	require_manager()
	content = getattr(frappe.local, "uploaded_file", None)
	filename = getattr(frappe.local, "uploaded_filename", None) or "image"
	if not content:
		frappe.throw("An image is required")
	name = frappe.form_dict.get("docname")
	if not name or not frappe.db.exists("Found Item", name):
		frappe.throw("Found item not found")
	doc = frappe.get_doc("Found Item", name)
	if not has_permission(doc, ptype="write"):
		frappe.throw("Not permitted", frappe.PermissionError)
	if doc.image:
		frappe.throw("A found item cannot be changed")
	file_doc = _store_private_image(doc, filename, content)
	doc.image = file_doc.file_url
	doc.save(ignore_permissions=True, ignore_version=False)
	return _present(doc)


def _present(doc):
	doc.reload()
	return _row(doc)


def _row(row):
	events = frappe.get_all(
		"Found Item Event",
		filters={"parent": row.name, "parenttype": "Found Item"},
		fields=["action", "actor", "occurred_on", "idx"],
		order_by="idx asc",
	)
	return {
		"name": row.name,
		"description": row.description,
		"category": row.category,
		"status": row.status,
		"property": row.property,
		"property_name": frappe.db.get_value("Property", row.property, "property_name"),
		"found_location": row.found_location,
		"room": row.room,
		"room_number": frappe.db.get_value("Room", row.room, "room_number") if row.room else None,
		"found_on": str(row.found_on) if row.found_on else None,
		"custodian": row.custodian,
		"image": row.image,
		"events": [
			{
				"action": event.action,
				"actor": event.actor,
				"occurred_on": str(event.occurred_on) if event.occurred_on else None,
			}
			for event in events
		],
	}


def _property_choices():
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


def _lock_events(before, doc):
	previous = list(before.events or [])
	current = list(doc.events or [])
	if len(current) != len(previous):
		frappe.throw("A found item cannot be changed")
	for old, new in zip(previous, current):
		if old.action != new.action or _text(old.actor) != _text(new.actor):
			frappe.throw("A found item cannot be changed")
		if str(old.occurred_on) != str(new.occurred_on):
			frappe.throw("A found item cannot be changed")


def _private_image(doc):
	if not doc.image or not str(doc.image).startswith("/private/"):
		return False
	return frappe.db.exists(
		"File",
		{
			"file_url": doc.image,
			"attached_to_doctype": "Found Item",
			"attached_to_name": doc.name,
			"is_private": 1,
		},
	)


def file_permission_query(user, doctype=None):
	"""Hide found-item files outside the caller's residences. Other files stay listed."""
	scope = property_scope(user)
	if scope is None:
		return ""
	outside = "ifnull(`tabFile`.`attached_to_doctype`, '') != 'Found Item'"
	if not scope:
		return outside
	values = ", ".join(frappe.db.escape(name) for name in scope)
	return (
		f"({outside} or `tabFile`.`attached_to_name` in ("
		f"select `name` from `tabFound Item` where `property` in ({values})))"
	)


def file_has_permission(doc, ptype="read", user=None, debug=False):
	"""Deny found-item files the caller cannot read. Other files are left to Frappe."""
	if getattr(doc, "attached_to_doctype", None) != "Found Item":
		return True
	if ptype == "delete" or not doc.attached_to_name:
		return False
	if not frappe.db.exists("Found Item", doc.attached_to_name):
		return False
	parent = frappe.get_doc("Found Item", doc.attached_to_name)
	action = "write" if ptype in ("write", "create") else "read"
	return bool(has_permission(parent, ptype=action, user=user))


def _next_found_reference():
	"""Take the next number from an autoincrement row so two saves cannot share it."""
	_ensure_found_reference_counter()
	frappe.db.sql("INSERT INTO `tabFound Item Reference` () VALUES ()")
	current = frappe.db.sql("SELECT LAST_INSERT_ID()")[0][0]
	return f"FND-{int(current):04d}"


def _ensure_found_reference_counter():
	exists = frappe.db.sql(
		"""
		SELECT 1 FROM information_schema.tables
		WHERE table_schema = DATABASE()
		AND table_name = 'tabFound Item Reference'
		"""
	)
	if exists:
		return
	# DDL commits the current transaction, so the table is created elsewhere.
	side = frappe.database.get_db(
		socket=frappe.conf.db_socket,
		host=frappe.conf.db_host,
		user=frappe.conf.db_user or frappe.conf.db_name,
		password=frappe.conf.db_password,
		port=frappe.conf.db_port,
		cur_db_name=frappe.conf.db_name,
	)
	try:
		side.sql(
			"""
			CREATE TABLE IF NOT EXISTS `tabFound Item Reference` (
				`name` BIGINT NOT NULL AUTO_INCREMENT,
				PRIMARY KEY (`name`)
			) ENGINE=InnoDB
			"""
		)
		series_max = side.sql(
			"SELECT MAX(`current`) FROM `tabSeries` WHERE `name` = 'FND-'"
		)[0][0] or 0
		document_max = side.sql(
			"""
			SELECT MAX(CAST(SUBSTRING(`name`, 5) AS UNSIGNED))
			FROM `tabFound Item`
			WHERE `name` LIKE %s
			""",
			("FND-%",),
		)[0][0] or 0
		highest = max(int(series_max), int(document_max))
		if highest:
			side.sql(
				"INSERT IGNORE INTO `tabFound Item Reference` (`name`) VALUES (%s)",
				(highest,),
			)
		side.commit()
	finally:
		side.close()


def _store_private_image(doc, filename, content):
	"""Write a new private file. Identical bytes must not reuse another document's URL."""
	if isinstance(content, str):
		content = content.encode()
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	_stem, ext = os.path.splitext(filename or "image")
	ext = ext if ext and len(ext) <= 8 else ".bin"
	safe_ext = "".join(ch for ch in ext if ch.isalnum() or ch == ".")
	safe = f"found-{doc.name}-{frappe.generate_hash(length=10)}{safe_ext}"
	path = os.path.join(folder, safe)
	with open(path, "wb") as handle:
		handle.write(content)

	def _remove_if_rolled_back(stored=path):
		if os.path.exists(stored):
			os.remove(stored)

	frappe.db.after_rollback.add(_remove_if_rolled_back)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": safe,
			"file_url": f"/private/files/{safe}",
			"is_private": 1,
			"attached_to_doctype": "Found Item",
			"attached_to_name": doc.name,
			"attached_to_field": "image",
		}
	)
	file_doc.flags.copy_from_existing_file = True
	file_doc.insert(ignore_permissions=True)
	return file_doc


def _rollback_registration():
	try:
		frappe.db.rollback(save_point="found_item_register")
	except Exception:
		frappe.db.rollback()
		frappe.throw("The found item could not be registered. Try again.")


def _require_property_record(property_name):
	if not property_name:
		frappe.throw("A residence is required")
	if frappe.db.exists("Property", property_name):
		return
	if property_scope() is None:
		frappe.throw("Property not found")
	frappe.throw("Not permitted", frappe.PermissionError)


def _found_on(value):
	text = _text(value)
	if not text:
		frappe.throw("Found date and time are required")
	try:
		return frappe.utils.get_datetime(text.replace("T", " "))
	except Exception:
		frappe.throw("Found date and time are not valid")


def _text(value):
	if value is None:
		return None
	text = str(value).strip()
	return text or None
