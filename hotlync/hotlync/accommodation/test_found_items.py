import threading

import frappe
from frappe.tests import IntegrationTestCase

from hotlync.api import attach_found_item_image, get_found_items, register_found_item


class TestFoundItems(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("hotlync_found")
		self.home, self.room = _residence("FNDH", "Found Residence")
		self.other, self.other_room = _residence("FNDO", "Other Found Residence")
		self.staff = _user("found-staff@hotlync.local", "Staff")
		self.manager = _user("found-manager@hotlync.local", "Accommodation Manager")
		self.outsider = _user("found-outsider@hotlync.local", "Accommodation Manager")
		_assign(self.manager, self.home)
		_assign(self.outsider, self.other)

	def tearDown(self):
		frappe.db.rollback(save_point="hotlync_found")
		frappe.set_user("Administrator")
		super().tearDown()

	def test_registration_starts_as_reported_with_a_unique_reference(self):
		frappe.set_user(self.manager)
		first = register_found_item(
			description="Blue wallet",
			property=self.home,
			found_location="Lobby desk",
			found_on="2026-10-15 09:30:00",
			category="Personal",
		)
		second = register_found_item(
			description="Blue wallet",
			property=self.home,
			found_location="Lobby desk",
			found_on="2026-10-15 09:31:00",
		)
		self.assertTrue(first["name"].startswith("FND-"))
		self.assertTrue(second["name"].startswith("FND-"))
		self.assertNotEqual(first["name"], second["name"])
		self.assertEqual(first["status"], "Reported")
		self.assertEqual(first["custodian"], self.manager)
		self.assertEqual(first["events"][0]["action"], "Reported")
		self.assertEqual(first["events"][0]["actor"], self.manager)
		self.assertEqual(
			frappe.db.get_value(
				"Found Item Event",
				{"parent": first["name"]},
				"action",
			),
			"Reported",
		)
		names = [row["name"] for row in get_found_items()["items"]]
		self.assertIn(first["name"], names)
		self.assertIn(second["name"], names)

	def test_a_series_conflict_is_retried(self):
		frappe.set_user(self.manager)
		real_save = frappe.model.document.Document.save
		state = {"saves": 0, "rollbacks": 0}

		def save(doc, *args, **kwargs):
			if doc.doctype == "Found Item" and doc.is_new():
				state["saves"] += 1
				if state["saves"] == 1:
					raise frappe.QueryDeadlockError
			return real_save(doc, *args, **kwargs)

		def rollback(*args, **kwargs):
			state["rollbacks"] += 1

		frappe.model.document.Document.save = save
		previous_rollback = frappe.db.rollback
		frappe.db.rollback = rollback
		try:
			row = register_found_item(
				description="Retry wallet",
				property=self.home,
				found_location="Desk",
				found_on="2026-10-15 09:40:00",
			)
		finally:
			frappe.model.document.Document.save = real_save
			frappe.db.rollback = previous_rollback
		self.assertEqual(state["saves"], 2)
		self.assertEqual(state["rollbacks"], 1)
		self.assertTrue(row["name"].startswith("FND-"))
		self.assertEqual(row["status"], "Reported")

	def test_an_unresolved_series_conflict_returns_a_safe_error(self):
		frappe.set_user(self.manager)
		real_save = frappe.model.document.Document.save

		def save(doc, *args, **kwargs):
			if doc.doctype == "Found Item" and doc.is_new():
				raise frappe.QueryDeadlockError
			return real_save(doc, *args, **kwargs)

		frappe.model.document.Document.save = save
		previous_rollback = frappe.db.rollback
		frappe.db.rollback = lambda *args, **kwargs: None
		try:
			with self.assertRaises(frappe.ValidationError) as failed:
				register_found_item(
					description="Retry exhausted",
					property=self.home,
					found_location="Desk",
					found_on="2026-10-15 09:45:00",
				)
		finally:
			frappe.model.document.Document.save = real_save
			frappe.db.rollback = previous_rollback
		message = str(failed.exception)
		self.assertIn("The found item could not be registered. Try again.", message)
		self.assertNotIn("tabSeries", message)
		self.assertNotIn("1020", message)
		self.assertFalse(
			frappe.db.exists("Found Item", {"description": "Retry exhausted"})
		)

	def test_two_registrations_at_once_receive_different_references(self):
		site = frappe.local.site
		results = []
		errors = []
		barrier = threading.Barrier(2)

		def worker(found_on):
			try:
				frappe.init(site=site)
				frappe.connect()
				frappe.set_user("Administrator")
				barrier.wait(timeout=15)
				connection = frappe.db.sql("SELECT CONNECTION_ID()")[0][0]
				row = register_found_item(
					description="Concurrent wallet",
					property="SRA",
					found_location="Desk",
					found_on=found_on,
				)
				results.append((connection, row["name"]))
			except Exception as err:
				errors.append(f"{type(err).__name__}: {err}")
			finally:
				if getattr(frappe.local, "db", None):
					frappe.db.rollback()
				frappe.destroy()

		threads = [
			threading.Thread(target=worker, args=("2026-10-15 18:01:00",)),
			threading.Thread(target=worker, args=("2026-10-15 18:02:00",)),
		]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=30)
		self.assertFalse(any(thread.is_alive() for thread in threads))
		self.assertFalse(errors, errors)
		connections = [item[0] for item in results]
		names = [item[1] for item in results]
		self.assertEqual(len(set(connections)), 2)
		self.assertEqual(len(set(names)), 2)
		for name in names:
			self.assertTrue(name.startswith("FND-"))
			self.assertFalse(frappe.db.exists("Found Item", name))

	def test_required_fields_and_a_foreign_room_are_rejected(self):
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError) as missing:
			register_found_item(
				description="  ",
				property=self.home,
				found_location="Lobby",
				found_on="2026-10-15 09:30:00",
			)
		self.assertIn("A description is required", str(missing.exception))
		with self.assertRaises(frappe.ValidationError) as place:
			register_found_item(
				description="Scarf",
				property=self.home,
				found_location=" ",
				found_on="2026-10-15 09:30:00",
			)
		self.assertIn("A found location is required", str(place.exception))
		with self.assertRaises(frappe.ValidationError) as when:
			register_found_item(
				description="Scarf",
				property=self.home,
				found_location="Lobby",
				found_on="",
			)
		self.assertIn("Found date and time are required", str(when.exception))
		with self.assertRaises(frappe.ValidationError) as residence:
			register_found_item(
				description="Scarf",
				property="",
				found_location="Lobby",
				found_on="2026-10-15 09:30:00",
			)
		self.assertIn("A residence is required", str(residence.exception))
		with self.assertRaises(frappe.ValidationError) as room:
			register_found_item(
				description="Scarf",
				property=self.home,
				found_location="Lobby",
				found_on="2026-10-15 09:30:00",
				room=self.other_room,
			)
		self.assertIn("Room is not in the selected residence", str(room.exception))
		with self.assertRaises(frappe.ValidationError) as status:
			doc = frappe.new_doc("Found Item")
			doc.description = "Scarf"
			doc.property = self.home
			doc.found_location = "Lobby"
			doc.found_on = "2026-10-15 09:30:00"
			doc.status = "Returned"
			doc.save(ignore_permissions=True, ignore_version=False)
		self.assertIn("A found item starts as reported", str(status.exception))

	def test_another_residence_cannot_see_or_register(self):
		frappe.set_user(self.manager)
		row = register_found_item(
			description="Watch",
			property=self.home,
			found_location="Gym",
			found_on="2026-10-15 10:00:00",
		)
		frappe.set_user(self.outsider)
		visible = [item["name"] for item in get_found_items()["items"]]
		self.assertNotIn(row["name"], visible)
		with self.assertRaises(frappe.ValidationError) as hidden:
			get_found_items(row["name"])
		self.assertIn("Found item not found", str(hidden.exception))
		with self.assertRaises(frappe.PermissionError):
			register_found_item(
				description="Watch",
				property=self.home,
				found_location="Gym",
				found_on="2026-10-15 10:05:00",
			)
		with self.assertRaises(frappe.PermissionError) as unknown:
			register_found_item(
				description="Watch",
				property="MISSING-FOUND",
				found_location="Gym",
				found_on="2026-10-15 10:05:00",
			)
		self.assertIn("Not permitted", str(unknown.exception))
		hidden_doc = frappe.get_doc("Found Item", row["name"])
		with self.assertRaises(frappe.DoesNotExistError) as lookup:
			hidden_doc.check_permission("read")
		self.assertIn(row["name"], str(lookup.exception))
		frappe.set_user(self.manager)
		owned = frappe.get_doc("Found Item", row["name"])
		owned.check_permission("read")
		with self.assertRaises(frappe.PermissionError):
			owned.check_permission("delete")
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError) as missing:
			register_found_item(
				description="Watch",
				property="MISSING-FOUND",
				found_location="Gym",
				found_on="2026-10-15 10:05:00",
			)
		self.assertIn("Property not found", str(missing.exception))

	def test_staff_and_guest_cannot_use_the_register(self):
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.PermissionError):
			get_found_items()
		with self.assertRaises(frappe.PermissionError):
			register_found_item(
				description="Hat",
				property=self.home,
				found_location="Gate",
				found_on="2026-10-15 11:00:00",
			)
		frappe.set_user("Guest")
		self.assertRaises(frappe.AuthenticationError, get_found_items)

	def test_history_stays_and_the_image_stays_private(self):
		frappe.set_user(self.manager)
		row = register_found_item(
			description="Umbrella",
			property=self.home,
			found_location="Door",
			found_on="2026-10-15 12:00:00",
		)
		doc = frappe.get_doc("Found Item", row["name"])
		doc.description = "Changed"
		with self.assertRaises(frappe.ValidationError) as changed:
			doc.save(ignore_permissions=True, ignore_version=False)
		self.assertIn("A found item cannot be changed", str(changed.exception))
		shared = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "shared-bytes.png",
				"is_private": 1,
				"content": b"image-bytes",
				"attached_to_doctype": "Maintenance Ticket",
				"attached_to_name": "MNT-FILE-CHECK",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("File", shared.name, "owner", self.outsider)
		frappe.local.uploaded_file = b"image-bytes"
		frappe.local.uploaded_filename = "umbrella.png"
		frappe.local.form_dict = frappe._dict(docname=row["name"])
		saved = attach_found_item_image()
		self.assertTrue(saved["image"].startswith("/private/"))
		self.assertTrue(
			frappe.db.exists(
				"Version",
				{"ref_doctype": "Found Item", "docname": row["name"]},
			)
		)
		self.assertNotEqual(saved["image"], shared.file_url)
		file_name = frappe.db.get_value("File", {"file_url": saved["image"]}, "name")
		self.assertEqual(frappe.db.get_value("File", file_name, "is_private"), 1)
		self.assertTrue(
			frappe.db.exists("File", {"name": shared.name, "file_url": shared.file_url})
		)
		frappe.set_user(self.manager)
		self.assertTrue(frappe.db.exists("File", file_name))
		visible = frappe.get_list(
			"File", filters={"name": file_name}, pluck="name", limit=20
		)
		self.assertEqual(visible, [file_name])
		ticket_files = frappe.get_list(
			"File", filters={"name": shared.name}, pluck="name", limit=20
		)
		self.assertEqual(ticket_files, [shared.name])
		owned = frappe.get_doc("File", file_name)
		self.assertTrue(owned.is_downloadable())
		frappe.set_user(self.outsider)
		self.assertFalse(owned.is_downloadable())
		self.assertFalse(frappe.has_permission("Found Item", "read", row["name"]))
		self.assertFalse(frappe.has_permission("File", "read", file_name))
		self.assertFalse(frappe.has_permission("File", "delete", file_name))
		self.assertEqual(
			frappe.get_list(
				"File", filters={"name": file_name}, pluck="name", limit=20
			),
			[],
		)
		self.assertEqual(
			frappe.get_list(
				"File", filters={"file_url": saved["image"]}, pluck="name", limit=20
			),
			[],
		)
		loaded = frappe.get_doc("File", file_name)
		with self.assertRaises(frappe.PermissionError):
			loaded.check_permission("read")
		self.assertEqual(
			frappe.get_list(
				"File", filters={"name": shared.name}, pluck="name", limit=20
			),
			[shared.name],
		)
		frappe.set_user(self.staff)
		self.assertFalse(owned.is_downloadable())
		self.assertEqual(
			frappe.get_list(
				"File", filters={"file_url": saved["image"]}, pluck="name", limit=20
			),
			[],
		)
		self.assertFalse(frappe.has_permission("File", "read", file_name))
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError) as removed:
			frappe.delete_doc("Found Item", row["name"])
		self.assertIn("A found item cannot be deleted", str(removed.exception))
		self.assertTrue(frappe.db.exists("Found Item", row["name"]))
		self.assertEqual(
			frappe.db.get_value(
				"Found Item Event",
				{"parent": row["name"]},
				"action",
			),
			"Reported",
		)


def _assign(user, property_name):
	frappe.set_user("Administrator")
	frappe.get_doc(
		{
			"doctype": "Property Assignment",
			"user": user,
			"property": property_name,
		}
	).insert(ignore_permissions=True)


def _user(email, role):
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Found",
			"last_name": "Check",
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	).insert(ignore_permissions=True)
	user.add_roles(role)
	return user.name


def _residence(code, property_name):
	property_doc = frappe.get_doc(
		{
			"doctype": "Property",
			"code": code,
			"property_name": property_name,
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	building = frappe.get_doc(
		{
			"doctype": "Building",
			"code": code + "-B",
			"building_name": property_name + " building",
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
	room = frappe.get_doc(
		{
			"doctype": "Room",
			"floor": floor.name,
			"building": building.name,
			"room_number": "1",
			"room_type": "Single",
			"capacity": 1,
			"status": "Available",
		}
	).insert(ignore_permissions=True)
	return property_doc.name, room.name
