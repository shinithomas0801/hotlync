app_name = "hotlync"
app_title = "HotLync"
app_publisher = "HotLync"
app_description = "Staff accommodation and facility management"
app_email = "dev@hotlync.local"
app_license = "MIT"

after_install = "hotlync.setup.install.after_install"

permission_query_conditions = {
	"Maintenance Ticket": "hotlync.accommodation.doctype.maintenance_ticket.maintenance_ticket.get_permission_query_conditions",
	"Accommodation Request": "hotlync.accommodation.doctype.accommodation_request.accommodation_request.get_permission_query_conditions",
	"Accommodation Allocation": "hotlync.accommodation.doctype.accommodation_allocation.accommodation_allocation.get_permission_query_conditions",
	"Property": "hotlync.accommodation.access.property_query",
	"Building": "hotlync.accommodation.access.building_query",
	"Floor": "hotlync.accommodation.access.floor_query",
	"Room": "hotlync.accommodation.access.room_query",
	"Bed": "hotlync.accommodation.access.bed_query",
}

has_permission = {
	"Maintenance Ticket": "hotlync.accommodation.doctype.maintenance_ticket.maintenance_ticket.has_permission",
	"Accommodation Request": "hotlync.accommodation.doctype.accommodation_request.accommodation_request.has_permission",
	"Accommodation Allocation": "hotlync.accommodation.doctype.accommodation_allocation.accommodation_allocation.has_permission",
	"Property": "hotlync.accommodation.access.property_has_permission",
	"Building": "hotlync.accommodation.access.building_has_permission",
	"Floor": "hotlync.accommodation.access.floor_has_permission",
	"Room": "hotlync.accommodation.access.room_has_permission",
	"Bed": "hotlync.accommodation.access.bed_has_permission",
}

fixtures = []
