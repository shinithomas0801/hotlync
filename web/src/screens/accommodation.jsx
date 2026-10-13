import { useEffect, useMemo, useState } from 'react'
import { call, createDoc } from '../api.js'
import { flattenProperty, isGroupRole, percent } from '../format.js'
import { Icon } from '../icons.jsx'
import { Field, Notice, PageIntro, PrimaryButton, StatusPill, inputClass } from '../ui.jsx'

const pageSize = 10

export function Accommodation ({ view, version, query, onQuery, onOpen, onChanged, roles }) {
	const [tree, setTree] = useState(null)
	const [error, setError] = useState('')
	const [propertyId, setPropertyId] = useState('')
	const [buildingId, setBuildingId] = useState('')
	const [floorId, setFloorId] = useState('')
	const [roomId, setRoomId] = useState('')
	const [roomType, setRoomType] = useState('')
	const [status, setStatus] = useState('')
	const [page, setPage] = useState(1)
	const [ready, setReady] = useState(false)
	const [adding, setAdding] = useState(false)
	const [addingProperty, setAddingProperty] = useState(false)
	const [history, setHistory] = useState(null)

	useEffect(() => {
		let active = true
		call('hotlync.api.get_accommodation')
			.then((next) => {
				if (active) {
					setTree(next)
					setError('')
				}
			})
			.catch((err) => active && setError(err.message))
		return () => {
			active = false
		}
	}, [version])

	const flat = useMemo(() => flattenProperty(tree), [tree])

	useEffect(() => {
		if (ready || !flat.rooms.length) {
			return
		}
		const first = flat.rooms[0]
		setPropertyId(first.propertyId)
		setBuildingId(first.buildingId)
		setFloorId(first.floorId)
		setRoomId(first.name)
		setReady(true)
	}, [flat.rooms, ready])

	useEffect(() => {
		setPage(1)
	}, [propertyId, buildingId, floorId, roomType, status, query])

	if (error) {
		return (
			<div className="rounded-2xl border border-rose-100 bg-white p-6 text-sm text-rose-700">
				{error}
			</div>
		)
	}
	if (!tree) {
		return <div className="h-40 animate-pulse rounded-2xl bg-white" />
	}

	const rooms = flat.rooms.filter((room) => {
		if (propertyId && room.propertyId !== propertyId) {
			return false
		}
		if (buildingId && room.buildingId !== buildingId) {
			return false
		}
		if (floorId && room.floorId !== floorId) {
			return false
		}
		if (roomType && room.room_type !== roomType) {
			return false
		}
		if (status && room.status !== status) {
			return false
		}
		if (query) {
			const hay = `${room.label} ${room.room_number} ${room.buildingName} ${room.floorName}`.toLowerCase()
			if (!hay.includes(query.trim().toLowerCase())) {
				return false
			}
		}
		return true
	})
	const pages = Math.max(1, Math.ceil(rooms.length / pageSize))
	const currentPage = Math.min(page, pages)
	const visible = rooms.slice((currentPage - 1) * pageSize, currentPage * pageSize)
	const selected = flat.rooms.find((room) => room.name === roomId) || rooms[0]
	const buildingName = flat.buildings.find((item) => item.name === buildingId)?.buildingName
	const floorName = flat.rooms.find((room) => room.floorId === floorId)?.floorName
	const titleBits = [buildingName, floorName].filter(Boolean).join(', ')

	const roomStats = countRooms(flat.rooms)
	const bedStats = countBeds(flat.beds)

	return (
		<div>
			<PageIntro
				icon={<Icon name="building" className="h-5 w-5" />}
				title="Accommodation"
				subtitle="Manage buildings, rooms, beds and occupancy across the property."
				crumbs={['Home', 'Accommodation', view === 'beds' ? 'Beds' : view === 'buildings' ? 'Buildings' : 'Rooms']}
			/>
			<div className="mb-4 grid gap-4 lg:grid-cols-[1fr_1fr_1fr_1fr_220px]">
				{(view === 'beds' ? bedCards(bedStats) : roomCards(roomStats, flat.buildings.length)).map(
					(card) => (
						<StatCard key={card.label} {...card} />
					),
				)}
				<label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 shadow-sm">
					<Icon name="search" className="h-4 w-4 text-slate-400" />
					<input
						value={query}
						onChange={(event) => onQuery(event.target.value)}
						placeholder="Search room number..."
						className="w-full bg-transparent text-sm outline-none"
					/>
				</label>
			</div>

			{view === 'buildings' && (
				<div className="space-y-4">
					{isGroupRole(roles) && (
						<div className="flex justify-end">
							<button
								type="button"
								onClick={() => setAddingProperty(true)}
								className="inline-flex items-center gap-1 rounded-lg bg-[#2563EB] px-3 py-1.5 text-xs font-medium text-white"
							>
								<Icon name="plus" className="h-3.5 w-3.5" />
								Add property
							</button>
						</div>
					)}
					<BuildingGrid buildings={flat.buildings} onOpen={(id) => {
						setBuildingId(id)
						setFloorId('')
						onOpen('rooms')
					}} />
				</div>
			)}

			{view === 'beds' && <BedTable beds={flat.beds} query={query} />}

			{view === 'rooms' && (
				<>
					<div className="mb-4 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
						<div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
							<Filter
								label="Property"
								value={propertyId}
								onChange={(value) => {
									setPropertyId(value)
									setBuildingId('')
									setFloorId('')
								}}
								options={options('All Properties', flat.buildings.map((item) => [item.propertyId, item.propertyName]))}
							/>
							<Filter
								label="Building / Villa"
								value={buildingId}
								onChange={(value) => {
									setBuildingId(value)
									setFloorId('')
								}}
								options={options(
									'All Buildings',
									flat.buildings
										.filter((item) => !propertyId || item.propertyId === propertyId)
										.map((item) => [item.name, item.buildingName]),
								)}
							/>
							<Filter
								label="Floor"
								value={floorId}
								onChange={setFloorId}
								options={options(
									'All Floors',
									floorsFor(flat, propertyId, buildingId).map((item) => [item.id, item.label]),
								)}
							/>
							<Filter
								label="Room Type"
								value={roomType}
								onChange={setRoomType}
								options={[
									['', 'All Types'],
									['Single', 'Single'],
									['Shared', 'Shared'],
									['Family', 'Family'],
								]}
							/>
							<Filter label="Gender" value="" onChange={() => {}} options={[['', 'All']]} />
							<Filter
								label="Status"
								value={status}
								onChange={setStatus}
								options={[
									['', 'All'],
									['Occupied', 'Occupied'],
									['Partially Occupied', 'Partially Occupied'],
									['Available', 'Available'],
									['Maintenance', 'Maintenance'],
								]}
							/>
						</div>
					</div>
					<div className="grid items-start gap-4 xl:grid-cols-[240px_minmax(0,1fr)_300px]">
						<Tree
							tree={tree}
							selectedId={selected?.name}
							onSelectFloor={(floor) => {
								setPropertyId(floor.propertyId)
								setBuildingId(floor.buildingId)
								setFloorId(floor.floorId)
							}}
							onSelectRoom={(room) => {
								setPropertyId(room.propertyId)
								setBuildingId(room.buildingId)
								setFloorId(room.floorId)
								setRoomId(room.name)
								setHistory(null)
							}}
						/>
						<section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
							<div className="flex items-center justify-between px-4 py-3">
								<h2 className="text-sm font-semibold text-slate-800">
									Rooms{titleBits ? ` - ${titleBits}` : ''}
								</h2>
								<button
									type="button"
									onClick={() => setAdding(true)}
									className="inline-flex items-center gap-1 rounded-lg bg-[#2563EB] px-3 py-1.5 text-xs font-medium text-white"
								>
									<Icon name="plus" className="h-3.5 w-3.5" />
									Add Room
								</button>
							</div>
							<div className="overflow-x-auto">
								<table className="w-full text-left text-sm">
									<thead className="bg-slate-50 text-xs text-slate-500">
										<tr>
											<th className="px-4 py-2 font-medium">Room No.</th>
											<th className="px-3 py-2 font-medium">Type</th>
											<th className="px-3 py-2 font-medium">Capacity</th>
											<th className="px-3 py-2 font-medium">Occupied</th>
											<th className="px-3 py-2 font-medium">Status</th>
											<th className="px-3 py-2 font-medium">Actions</th>
										</tr>
									</thead>
									<tbody>
										{visible.map((room) => (
											<tr
												key={room.name}
												onClick={() => {
													setRoomId(room.name)
													setHistory(null)
												}}
												className={`cursor-pointer border-t border-slate-100 ${
													room.name === selected?.name ? 'bg-blue-50/70' : 'hover:bg-slate-50'
												}`}
											>
												<td className="px-4 py-2.5 font-medium text-slate-800">{room.label}</td>
												<td className="px-3 py-2.5 text-slate-600">{room.room_type}</td>
												<td className="px-3 py-2.5 text-slate-600">{room.capacity}</td>
												<td className="px-3 py-2.5 text-slate-600">
													{room.occupied}/{room.bedCount}
												</td>
												<td className="px-3 py-2.5">
													<StatusPill status={room.status} />
												</td>
												<td className="px-3 py-2.5">
													<button
														type="button"
														className="text-slate-400 hover:text-slate-700"
														aria-label={`View ${room.label}`}
														onClick={() => setRoomId(room.name)}
													>
														<Icon name="eye" className="h-4 w-4" />
													</button>
												</td>
											</tr>
										))}
										{!visible.length && (
											<tr>
												<td colSpan="6" className="px-4 py-8 text-center text-slate-400">
													No rooms match these filters.
												</td>
											</tr>
										)}
									</tbody>
								</table>
							</div>
							<div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
								<span>
									Showing {rooms.length ? (currentPage - 1) * pageSize + 1 : 0}–
									{Math.min(currentPage * pageSize, rooms.length)} of {rooms.length} rooms
								</span>
								<div className="flex gap-1">
									{Array.from({ length: pages }, (_, index) => (
										<button
											key={index}
											type="button"
											onClick={() => setPage(index + 1)}
											className={`h-7 w-7 rounded-md ${
												index + 1 === currentPage
													? 'bg-[#2563EB] text-white'
													: 'text-slate-600 hover:bg-slate-100'
											}`}
										>
											{index + 1}
										</button>
									))}
								</div>
							</div>
						</section>
						{selected && (
							<RoomDetail
								room={selected}
								history={history}
								onAllocate={() => onOpen('allocate', { room: selected.name })}
								onTransfer={() => onOpen('transfer')}
								onMaintenance={() => onOpen('maintenance')}
								onHistory={async () => {
									const rows = await call('hotlync.api.get_allocations')
									setHistory(rows.filter((row) => row.room === selected.name))
								}}
							/>
						)}
					</div>
				</>
			)}
			{addingProperty && (
				<AddProperty
					onClose={() => setAddingProperty(false)}
					onCreated={() => {
						setAddingProperty(false)
						onChanged()
					}}
				/>
			)}
			{adding && (
				<AddRoom
					tree={tree}
					floorId={floorId}
					onClose={() => setAdding(false)}
					onCreated={() => {
						setAdding(false)
						onChanged()
					}}
				/>
			)}
		</div>
	)
}

function roomCards (stats, buildingCount) {
	return [
		card('bed', 'bg-blue-50 text-blue-600', 'Total Rooms', stats.total, `Across ${buildingCount} building${buildingCount === 1 ? '' : 's'}`),
		card('users', 'bg-emerald-50 text-emerald-600', 'Occupied Rooms', stats.occupied, `${percent(stats.occupied, stats.total)}% of rooms`, percent(stats.occupied, stats.total), 'bg-emerald-500'),
		card('bed', 'bg-sky-50 text-sky-600', 'Available Rooms', stats.available, `${percent(stats.available, stats.total)}% available`, percent(stats.available, stats.total), 'bg-sky-500'),
		card('wrench', 'bg-orange-50 text-orange-500', 'Maintenance Rooms', stats.maintenance, `${percent(stats.maintenance, stats.total)}% under maintenance`, percent(stats.maintenance, stats.total), 'bg-orange-400'),
	]
}

function bedCards (stats) {
	return [
		card('bed', 'bg-blue-50 text-blue-600', 'Total Beds', stats.total, 'Live from ERPNext'),
		card('users', 'bg-emerald-50 text-emerald-600', 'Occupied Beds', stats.occupied, `${percent(stats.occupied, stats.total)}% occupancy`, percent(stats.occupied, stats.total), 'bg-emerald-500'),
		card('bed', 'bg-sky-50 text-sky-600', 'Available Beds', stats.available, `${percent(stats.available, stats.total)}% available`, percent(stats.available, stats.total), 'bg-sky-500'),
		card('wrench', 'bg-orange-50 text-orange-500', 'Maintenance Beds', stats.maintenance, `${percent(stats.maintenance, stats.total)}% under maintenance`, percent(stats.maintenance, stats.total), 'bg-orange-400'),
	]
}

function card (icon, tint, label, value, hint, bar, barClass) {
	return { icon, tint, label, value, hint, bar, barClass }
}

function countRooms (rooms) {
	return {
		total: rooms.length,
		occupied: rooms.filter((room) => room.status === 'Occupied' || room.status === 'Partially Occupied').length,
		available: rooms.filter((room) => room.status === 'Available').length,
		maintenance: rooms.filter((room) => room.status === 'Maintenance').length,
	}
}

function countBeds (beds) {
	return {
		total: beds.length,
		occupied: beds.filter((bed) => bed.status === 'Occupied').length,
		available: beds.filter((bed) => bed.status === 'Available').length,
		maintenance: beds.filter((bed) => bed.status === 'Maintenance').length,
	}
}

function StatCard ({ icon, tint, label, value, hint, bar, barClass }) {
	return (
		<div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
			<div className="flex items-start gap-3">
				<div className={`flex h-10 w-10 items-center justify-center rounded-full ${tint}`}>
					<Icon name={icon} className="h-5 w-5" />
				</div>
				<div>
					<div className="text-xs text-slate-500">{label}</div>
					<div className="text-2xl font-semibold text-slate-900">{value}</div>
				</div>
			</div>
			<div className="mt-2 text-xs text-slate-400">{hint}</div>
			{typeof bar === 'number' && (
				<div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
					<div className={`h-full rounded-full ${barClass}`} style={{ width: `${bar}%` }} />
				</div>
			)}
		</div>
	)
}

function Filter ({ label, value, onChange, options }) {
	const unique = []
	const seen = new Set()
	for (const option of options) {
		if (seen.has(option[0])) {
			continue
		}
		seen.add(option[0])
		unique.push(option)
	}
	return (
		<label className="block">
			<span className="mb-1 block text-[11px] text-slate-400">{label}</span>
			<select
				value={value}
				onChange={(event) => onChange(event.target.value)}
				className="w-full rounded-lg border border-slate-200 bg-white px-2 py-2 text-sm text-slate-700"
			>
				{unique.map(([id, text]) => (
					<option key={id || 'all'} value={id}>
						{text}
					</option>
				))}
			</select>
		</label>
	)
}

function options (allLabel, pairs) {
	return [['', allLabel], ...pairs]
}

function floorsFor (flat, propertyId, buildingId) {
	const rows = []
	for (const building of flat.buildings) {
		if (propertyId && building.propertyId !== propertyId) {
			continue
		}
		if (buildingId && building.name !== buildingId) {
			continue
		}
		for (const floor of building.floors) {
			rows.push({
				id: floor.name,
				label: `${building.buildingName} · ${floor.floor_name}`,
			})
		}
	}
	return rows
}

function Tree ({ tree, selectedId, onSelectFloor, onSelectRoom }) {
	return (
		<aside className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-sm">
			<h2 className="px-2 pb-2 text-sm font-semibold text-slate-800">Property Structure</h2>
			{tree.map((property) => (
				<div key={property.name} className="text-sm">
					<div className="px-2 py-1 font-medium text-slate-700">{property.property_name}</div>
					{property.buildings.map((building) => (
						<div key={building.name} className="ml-3">
							<div className="px-2 py-1 text-slate-600">{building.building_name}</div>
							{building.floors.map((floor) => (
								<div key={floor.name} className="ml-3">
									<button
										type="button"
										onClick={() =>
											onSelectFloor({
												propertyId: property.name,
												buildingId: building.name,
												floorId: floor.name,
											})
										}
										className="px-2 py-1 text-slate-500"
									>
										{floor.floor_name}
									</button>
									{floor.rooms.map((room) => {
										const selected = room.name === selectedId
										return (
											<button
												key={room.name}
												type="button"
												onClick={() =>
													onSelectRoom({
														...room,
														propertyId: property.name,
														buildingId: building.name,
														floorId: floor.name,
													})
												}
												className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 ${
													selected ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-50'
												}`}
											>
												<span>
													{building.building_name.match(/([A-Za-z0-9]+)\s*$/)?.[1] || 'R'}-
													{room.room_number}
												</span>
												<StatusPill
													status={
														roomStatusOf(room) === 'Partially Occupied'
															? 'Partial'
															: roomStatusOf(room)
													}
												/>
											</button>
										)
									})}
								</div>
							))}
						</div>
					))}
				</div>
			))}
		</aside>
	)
}

function roomStatusOf (room) {
	const beds = room.beds || []
	const occupied = beds.filter((bed) => bed.status === 'Occupied').length
	const maintenance = beds.filter((bed) => bed.status === 'Maintenance').length
	if (occupied === beds.length && beds.length) {
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

function BuildingGrid ({ buildings, onOpen }) {
	if (!buildings.length) {
		return <p className="text-sm text-slate-400">No buildings yet.</p>
	}
	return (
		<div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
			{buildings.map((building) => (
				<button
					key={building.name}
					type="button"
					onClick={() => onOpen(building.name)}
					className="rounded-2xl border border-slate-200/80 bg-white p-5 text-left shadow-sm hover:border-blue-200"
				>
					<div className="text-xs text-slate-400">{building.propertyName}</div>
					<div className="mt-1 text-lg font-semibold text-slate-900">{building.buildingName}</div>
					<div className="mt-3 text-sm text-slate-500">
						{building.floors.length} floors · {building.bedCount} beds
					</div>
					<div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
						<div
							className="h-full rounded-full bg-emerald-500"
							style={{ width: `${percent(building.occupied, building.bedCount)}%` }}
						/>
					</div>
					<div className="mt-2 text-xs text-slate-400">
						{percent(building.occupied, building.bedCount)}% occupied
					</div>
				</button>
			))}
		</div>
	)
}

function BedTable ({ beds, query }) {
	const filtered = beds.filter((bed) => {
		if (!query) {
			return true
		}
		const hay = `${bed.label} ${bed.employee_name || ''} ${bed.buildingName}`.toLowerCase()
		return hay.includes(query.trim().toLowerCase())
	})
	return (
		<section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
			<table className="w-full text-left text-sm">
				<thead className="bg-slate-50 text-xs text-slate-500">
					<tr>
						<th className="px-4 py-2 font-medium">Bed No.</th>
						<th className="px-3 py-2 font-medium">Building</th>
						<th className="px-3 py-2 font-medium">Floor</th>
						<th className="px-3 py-2 font-medium">Status</th>
						<th className="px-3 py-2 font-medium">Staff</th>
					</tr>
				</thead>
				<tbody>
					{filtered.map((bed) => (
						<tr key={bed.name} className="border-t border-slate-100">
							<td className="px-4 py-2.5 font-medium">{bed.label}</td>
							<td className="px-3 py-2.5 text-slate-600">{bed.buildingName}</td>
							<td className="px-3 py-2.5 text-slate-600">{bed.floorName}</td>
							<td className="px-3 py-2.5">
								<StatusPill status={bed.status} />
							</td>
							<td className="px-3 py-2.5 text-slate-600">{bed.employee_name || '—'}</td>
						</tr>
					))}
				</tbody>
			</table>
		</section>
	)
}

function RoomDetail ({ room, history, onAllocate, onTransfer, onMaintenance, onHistory }) {
	return (
		<aside className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
			<div className="relative h-24 overflow-hidden rounded-xl bg-gradient-to-br from-slate-200 via-sky-100 to-slate-100">
				<RoomSketch />
				<span className="absolute top-3 right-3">
					<StatusPill status={room.status} />
				</span>
			</div>
			<h2 className="mt-3 text-lg font-semibold text-slate-900">Room {room.label}</h2>
			<dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
				<Fact icon="building" label="Building" value={room.buildingName} />
				<Fact icon="chart" label="Floor" value={room.floorNumber} />
				<Fact icon="bed" label="Room Type" value={room.room_type} />
				<Fact icon="users" label="Capacity" value={room.capacity} />
				<Fact icon="bed" label="Beds" value={room.bedCount} />
				<Fact icon="user" label="Occupied" value={room.occupied} />
			</dl>
			<div className="mt-4 flex items-center justify-between">
				<h3 className="text-sm font-semibold text-slate-800">Beds</h3>
			</div>
			<ul className="mt-1 divide-y divide-slate-100">
				{room.beds.map((bed) => (
					<li key={bed.name} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 py-2 text-xs">
						<span className="font-medium text-slate-700">
							{room.label}-{bed.bed_number}
						</span>
						<StatusPill status={bed.status} />
						<span className="text-right text-slate-500">{bed.employee_name || '—'}</span>
					</li>
				))}
			</ul>
			<h3 className="mt-4 text-sm font-semibold text-slate-800">Quick Actions</h3>
			<div className="mt-2 grid grid-cols-2 gap-2">
				<Action icon="bed" label="Allocate Bed" onClick={onAllocate} />
				<Action icon="arrows" label="Transfer Staff" onClick={onTransfer} />
				<Action icon="wrench" label="Create Maintenance" onClick={onMaintenance} />
				<Action icon="file" label="View History" onClick={onHistory} />
			</div>
			{history && (
				<ul className="mt-3 space-y-2 text-xs text-slate-600">
					{history.length === 0 && <li>No stay history for this room.</li>}
					{history.map((row) => (
						<li key={row.name} className="flex items-center justify-between gap-2">
							<span>
								{row.employee_name} · {row.bed_number}
							</span>
							<StatusPill status={row.status} />
						</li>
					))}
				</ul>
			)}
		</aside>
	)
}

function Fact ({ icon, label, value }) {
	return (
		<div className="flex items-start gap-2">
			<Icon name={icon} className="mt-0.5 h-4 w-4 text-slate-400" />
			<div>
				<div className="text-[11px] text-slate-400">{label}</div>
				<div className="font-medium text-slate-700">{value}</div>
			</div>
		</div>
	)
}

function Action ({ icon, label, onClick }) {
	return (
		<button
			type="button"
			onClick={onClick}
			className="flex items-center gap-2 rounded-lg border border-slate-200 px-2 py-2 text-left text-[11px] font-medium text-slate-600 hover:border-blue-200 hover:bg-blue-50"
		>
			<Icon name={icon} className="h-3.5 w-3.5 text-[#2563EB]" />
			{label}
		</button>
	)
}

function RoomSketch () {
	return (
		<svg viewBox="0 0 320 140" className="h-full w-full">
			<rect x="24" y="28" width="70" height="48" rx="4" fill="#dbe7f3" />
			<rect x="150" y="62" width="140" height="36" rx="8" fill="#94a3b8" />
			<rect x="162" y="48" width="46" height="22" rx="8" fill="#e2e8f0" />
			<rect x="40" y="88" width="240" height="8" fill="#cbd5e1" />
		</svg>
	)
}

function AddProperty ({ onClose, onCreated }) {
	const [code, setCode] = useState('')
	const [name, setName] = useState('')
	const [error, setError] = useState('')
	const [busy, setBusy] = useState(false)

	async function handleSubmit (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		try {
			await createDoc('Property', {
				code: code.trim(),
				property_name: name.trim(),
				status: 'Active',
			})
			onCreated()
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	return (
		<div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-4">
			<form onSubmit={handleSubmit} className="w-full max-w-md rounded-2xl bg-white p-6 shadow-sm">
				<h2 className="text-lg font-semibold text-slate-900">Add property</h2>
				<p className="mt-1 text-sm text-slate-500">
					A property is a staff residence. Buildings and rooms are added under it.
				</p>
				<div className="mt-4 space-y-3">
					<Field label="Code">
						<input className={inputClass} value={code} onChange={(event) => setCode(event.target.value)} required />
					</Field>
					<Field label="Name">
						<input className={inputClass} value={name} onChange={(event) => setName(event.target.value)} required />
					</Field>
				</div>
				{error && <Notice error={error} />}
				<div className="mt-4 flex justify-end gap-2">
					<button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-slate-600">
						Cancel
					</button>
					<button type="submit" disabled={busy} className="rounded-lg bg-[#2563EB] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
						Save
					</button>
				</div>
			</form>
		</div>
	)
}

function AddRoom ({ tree, floorId, onClose, onCreated }) {
	const floors = []
	for (const property of tree) {
		for (const building of property.buildings || []) {
			for (const floor of building.floors || []) {
				floors.push({
					id: floor.name,
					label: `${building.building_name} · ${floor.floor_name}`,
				})
			}
		}
	}
	const [floor, setFloor] = useState(floorId || floors[0]?.id || '')
	const [roomNumber, setRoomNumber] = useState('')
	const [roomType, setRoomType] = useState('Shared')
	const [capacity, setCapacity] = useState(1)
	const [error, setError] = useState('')
	const [busy, setBusy] = useState(false)

	async function handleSubmit (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		try {
			const room = await createDoc('Room', {
				floor,
				room_number: roomNumber,
				room_type: roomType,
				capacity: Number(capacity) || 1,
				status: 'Available',
			})
			const count = Math.max(1, Math.min(Number(capacity) || 1, 6))
			const letters = 'ABCDEF'
			for (let index = 0; index < count; index += 1) {
				await createDoc('Bed', {
					room: room.name,
					bed_number: letters[index],
					status: 'Available',
				})
			}
			onCreated()
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	return (
		<div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/40 p-4">
			<form onSubmit={handleSubmit} className="w-full max-w-md space-y-3 rounded-2xl bg-white p-6 shadow-xl">
				<h2 className="text-lg font-semibold text-slate-900">Add Room</h2>
				<Field label="Floor">
					<select className={inputClass} value={floor} onChange={(event) => setFloor(event.target.value)}>
						{floors.map((item) => (
							<option key={item.id} value={item.id}>
								{item.label}
							</option>
						))}
					</select>
				</Field>
				<Field label="Room number">
					<input
						className={inputClass}
						value={roomNumber}
						onChange={(event) => setRoomNumber(event.target.value)}
						required
					/>
				</Field>
				<Field label="Type">
					<select className={inputClass} value={roomType} onChange={(event) => setRoomType(event.target.value)}>
						<option>Single</option>
						<option>Shared</option>
						<option>Family</option>
					</select>
				</Field>
				<Field label="Beds">
					<input
						type="number"
						min="1"
						max="6"
						className={inputClass}
						value={capacity}
						onChange={(event) => setCapacity(event.target.value)}
					/>
				</Field>
				<Notice error={error} />
				<div className="flex justify-end gap-2">
					<button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-slate-600">
						Cancel
					</button>
					<PrimaryButton disabled={busy || !floor || !roomNumber}>Save room</PrimaryButton>
				</div>
			</form>
		</div>
	)
}
