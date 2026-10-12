import frappe

ROLES = (
	"Accommodation Admin",
	"Accommodation Manager",
	"Staff",
)


def after_install():
	for role_name in ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		role = frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 0 if role_name == "Staff" else 1,
			}
		)
		role.insert(ignore_permissions=True)
	frappe.db.commit()


def complete_setup():
	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	frappe.db.set_value(
		"Installed Application",
		{"app_name": ("in", ["frappe", "erpnext", "hrms", "hotlync"])},
		"is_setup_complete",
		1,
	)
	frappe.db.set_default("desktop:home_page", "workspace")
	frappe.db.commit()
