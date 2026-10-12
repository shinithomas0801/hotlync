app_name = "hotlync"
app_title = "HotLync"
app_publisher = "HotLync"
app_description = "Staff accommodation and facility management"
app_email = "dev@hotlync.local"
app_license = "MIT"

after_install = "hotlync.setup.install.after_install"

permission_query_conditions = {
	"Accommodation Allocation": "hotlync.accommodation.doctype.accommodation_allocation.accommodation_allocation.get_permission_query_conditions",
}

has_permission = {
	"Accommodation Allocation": "hotlync.accommodation.doctype.accommodation_allocation.accommodation_allocation.has_permission",
}

fixtures = []
