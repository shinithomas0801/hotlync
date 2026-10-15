export function todayIso () {
	const now = new Date()
	const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
	return local.toISOString().slice(0, 10)
}

export function greeting (date) {
	const hour = date.getHours()
	if (hour < 12) {
		return 'Good morning'
	}
	if (hour < 17) {
		return 'Good afternoon'
	}
	return 'Good evening'
}

export function screenIdFromHash (hash) {
	const id = String(hash || '').replace(/^#/, '')
	return id || 'dashboard'
}

export function isStaffSession (session) {
	const roles = session?.roles || []
	const desk = ['System Manager', 'Accommodation Admin', 'Accommodation Manager']
	return roles.includes('Staff') && !roles.some((role) => desk.includes(role))
}

export function isGroupRole (roles) {
	return (roles || []).some((role) => (
		role === 'System Manager' || role === 'Accommodation Admin'
	))
}

export function friendlyName (user) {
	if (!user) {
		return 'there'
	}
	if (user === 'Administrator') {
		return 'Administrator'
	}
	const local = user.split('@')[0] || user
	return local
		.replace(/[._-]/g, ' ')
		.replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function roleLabel (user, roles) {
	const names = roles || []
	if (user === 'Administrator' || names.includes('System Manager')) {
		return 'System Manager'
	}
	if (names.includes('Accommodation Admin')) {
		return 'Accommodation Admin'
	}
	if (names.includes('Accommodation Manager')) {
		return 'Accommodation Manager'
	}
	if (names.includes('Staff')) {
		return 'Staff'
	}
	return 'Signed in'
}

export function initials (name) {
	const parts = String(name || '')
		.split(' ')
		.filter(Boolean)
		.slice(0, 2)
	if (!parts.length) {
		return 'HL'
	}
	return parts.map((part) => part[0].toUpperCase()).join('')
}

export function percent (part, total) {
	if (!total) {
		return 0
	}
	return Math.round((part / total) * 100)
}

export function roomCode (buildingName, roomNumber) {
	const match = String(buildingName || '').match(/([A-Za-z0-9]+)\s*$/)
	const prefix = match ? match[1] : 'R'
	return `${prefix}-${roomNumber}`
}

export function roomStatus (total, occupied, maintenance) {
	if (!total) {
		return 'Available'
	}
	if (occupied === total) {
		return 'Occupied'
	}
	if (occupied > 0) {
		return 'Partially Occupied'
	}
	if (maintenance > 0) {
		return 'Maintenance'
	}
	return 'Available'
}

export function flattenProperty (tree) {
	const buildings = []
	const rooms = []
	const beds = []
	for (const property of tree || []) {
		for (const building of property.buildings || []) {
			let bedCount = 0
			let occupied = 0
			for (const floor of building.floors || []) {
				for (const room of floor.rooms || []) {
					const roomBeds = room.beds || []
					const roomOccupied = roomBeds.filter((bed) => bed.status === 'Occupied').length
					const roomMaintenance = roomBeds.filter(
						(bed) => bed.status === 'Maintenance',
					).length
					const status = roomStatus(
						roomBeds.length,
						roomOccupied,
						roomMaintenance,
					)
					bedCount += roomBeds.length
					occupied += roomOccupied
					const entry = {
						...room,
						propertyName: property.property_name,
						propertyId: property.name,
						buildingName: building.building_name,
						buildingId: building.name,
						floorName: floor.floor_name,
						floorId: floor.name,
						floorNumber: floor.floor_number,
						occupied: roomOccupied,
						maintenance: roomMaintenance,
						bedCount: roomBeds.length,
						status,
						label: roomCode(building.building_name, room.room_number),
					}
					rooms.push(entry)
					for (const bed of roomBeds) {
						beds.push({
							...bed,
							roomLabel: entry.label,
							roomId: room.name,
							buildingName: building.building_name,
							floorName: floor.floor_name,
							label: `${entry.label}-${bed.bed_number}`,
						})
					}
				}
			}
			buildings.push({
				name: building.name,
				buildingName: building.building_name,
				propertyName: property.property_name,
				propertyId: property.name,
				floors: building.floors || [],
				bedCount,
				occupied,
			})
		}
	}
	return { buildings, rooms, beds }
}

export function activityLabel (status) {
	if (status === 'Checked In') {
		return 'Check-in'
	}
	if (status === 'Completed') {
		return 'Check-out'
	}
	if (status === 'Transferred') {
		return 'Room Transfer'
	}
	if (status === 'Draft') {
		return 'Allocation'
	}
	return status || 'Update'
}
