import { useEffect, useState } from 'react'
import { call } from '../api.js'
import { todayIso } from '../format.js'
import { Field, Notice, PageIntro, PrimaryButton, inputClass } from '../ui.jsx'
import { Icon } from '../icons.jsx'

export function Allocate ({ onDone, preset }) {
	const [tree, setTree] = useState([])
	const [employees, setEmployees] = useState([])
	const [search, setSearch] = useState('')
	const [employee, setEmployee] = useState('')
	const [property, setProperty] = useState('')
	const [building, setBuilding] = useState('')
	const [room, setRoom] = useState(preset?.room || '')
	const [beds, setBeds] = useState([])
	const [bed, setBed] = useState('')
	const [date, setDate] = useState(todayIso())
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [busy, setBusy] = useState(false)

	useEffect(() => {
		call('hotlync.api.get_accommodation')
			.then(setTree)
			.catch((err) => setError(err.message))
	}, [])

	useEffect(() => {
		if (!preset?.room || !tree.length) {
			return
		}
		for (const propertyDoc of tree) {
			for (const buildingDoc of propertyDoc.buildings || []) {
				for (const floor of buildingDoc.floors || []) {
					if (floor.rooms.some((item) => item.name === preset.room)) {
						setProperty(propertyDoc.name)
						setBuilding(buildingDoc.name)
						setRoom(preset.room)
					}
				}
			}
		}
	}, [preset, tree])

	useEffect(() => {
		const handle = setTimeout(() => {
			call('hotlync.api.get_employees', { search })
				.then(setEmployees)
				.catch((err) => setError(err.message))
		}, 200)
		return () => clearTimeout(handle)
	}, [search])

	useEffect(() => {
		call('hotlync.api.get_available_beds', room ? { room } : {})
			.then((rows) => {
				setBeds(rows)
				setBed(rows.find((item) => item.name === preset?.bed)?.name || rows[0]?.name || '')
			})
			.catch((err) => setError(err.message))
	}, [room, preset])

	const propertyDoc = tree.find((item) => item.name === property)
	const buildings = propertyDoc?.buildings || []
	const buildingDoc = buildings.find((item) => item.name === building)
	const rooms = buildingDoc?.floors.flatMap((floor) => floor.rooms) || []

	async function handleSubmit (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		setMessage('')
		try {
			const stay = await call('hotlync.api.allocate_bed', {
				employee,
				bed,
				allocation_date: date,
			})
			setMessage(`Draft ${stay.name} created for ${stay.employee_name}. Check in to occupy the bed.`)
			onDone?.()
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	return (
		<Screen title="Staff Allocation" subtitle="Create a draft stay. The bed stays available until check-in." icon="users">
			<form className="max-w-xl space-y-3 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm" onSubmit={handleSubmit}>
				<Field label="Employee">
					<input
						className={inputClass}
						value={search}
						placeholder="Search name"
						onChange={(event) => setSearch(event.target.value)}
					/>
					<select
						className={`${inputClass} mt-2`}
						value={employee}
						onChange={(event) => setEmployee(event.target.value)}
						required
					>
						<option value="">Select employee</option>
						{employees.map((item) => (
							<option key={item.name} value={item.name}>
								{item.employee_name} ({item.name})
							</option>
						))}
					</select>
				</Field>
				<Field label="Property">
					<select
						className={inputClass}
						value={property}
						onChange={(event) => {
							setProperty(event.target.value)
							setBuilding('')
							setRoom('')
						}}
					>
						<option value="">All properties</option>
						{tree.map((item) => (
							<option key={item.name} value={item.name}>
								{item.property_name}
							</option>
						))}
					</select>
				</Field>
				<Field label="Building">
					<select
						className={inputClass}
						value={building}
						onChange={(event) => {
							setBuilding(event.target.value)
							setRoom('')
						}}
					>
						<option value="">All buildings</option>
						{buildings.map((item) => (
							<option key={item.name} value={item.name}>
								{item.building_name}
							</option>
						))}
					</select>
				</Field>
				<Field label="Room">
					<select className={inputClass} value={room} onChange={(event) => setRoom(event.target.value)}>
						<option value="">All available beds</option>
						{rooms.map((item) => (
							<option key={item.name} value={item.name}>
								Room {item.room_number}
							</option>
						))}
					</select>
				</Field>
				<Field label="Available bed">
					<select className={inputClass} value={bed} onChange={(event) => setBed(event.target.value)} required>
						<option value="">Select bed</option>
						{beds
							.filter((item) => !building || item.building === building)
							.filter((item) => !property || item.property === property)
							.map((item) => (
								<option key={item.name} value={item.name}>
									{item.building_name} / {item.room_number} / {item.bed_number}
								</option>
							))}
					</select>
				</Field>
				<Field label="Allocation date">
					<input type="date" className={inputClass} value={date} onChange={(event) => setDate(event.target.value)} required />
				</Field>
				<Notice error={error} message={message} />
				<PrimaryButton disabled={busy || !employee || !bed}>Allocate</PrimaryButton>
			</form>
		</Screen>
	)
}

export function CheckIn (props) {
	return (
		<StayAction
			{...props}
			title="Confirm check-in"
			status="Draft"
			dateField="check_in_date"
			method="hotlync.api.check_in"
			verb="Checked in"
		/>
	)
}

export function CheckOut (props) {
	return (
		<StayAction
			{...props}
			title="Confirm check-out"
			status="Checked In"
			dateField="check_out_date"
			method="hotlync.api.check_out"
			verb="Checked out"
		/>
	)
}

export function StayDesk ({ onDone }) {
	return (
		<div>
			<PageIntro
				icon={<Icon name="door" className="h-5 w-5" />}
				title="Check-in / Check-out"
				subtitle="Confirm a draft stay, or complete a checked-in stay and free the bed."
			/>
			<div className="grid gap-4 lg:grid-cols-2">
				<CheckIn onDone={onDone} bare />
				<CheckOut onDone={onDone} bare />
			</div>
		</div>
	)
}

function StayAction ({ title, status, dateField, method, verb, onDone, bare }) {
	const [rows, setRows] = useState([])
	const [allocation, setAllocation] = useState('')
	const [date, setDate] = useState(todayIso())
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [busy, setBusy] = useState(false)

	function load () {
		call('hotlync.api.get_allocations', { status })
			.then((next) => {
				setRows(next)
				setAllocation(next[0]?.name || '')
			})
			.catch((err) => setError(err.message))
	}

	useEffect(() => {
		load()
	}, [status])

	const current = rows.find((row) => row.name === allocation)

	async function handleSubmit (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		setMessage('')
		try {
			const stay = await call(method, {
				allocation,
				[dateField]: date,
			})
			setMessage(`${verb} ${stay.employee_name}. Bed status is now updated in ERPNext.`)
			onDone?.()
			load()
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	const form = (
		<form className="space-y-3" onSubmit={handleSubmit}>
			<Field label="Stay">
				<select className={inputClass} value={allocation} onChange={(event) => setAllocation(event.target.value)} required>
					<option value="">Select allocation</option>
					{rows.map((row) => (
						<option key={row.name} value={row.name}>
							{row.employee_name} · {row.building_name} / {row.room_number} / {row.bed_number}
						</option>
					))}
				</select>
			</Field>
			{current && (
				<p className="text-sm text-slate-500">
					{current.employee_name} · {current.building_name} / Room {current.room_number} / Bed {current.bed_number}
				</p>
			)}
			<Field label={status === 'Draft' ? 'Check-in date' : 'Check-out date'}>
				<input type="date" className={inputClass} value={date} onChange={(event) => setDate(event.target.value)} required />
			</Field>
			<Notice error={error} message={message} />
			<PrimaryButton disabled={busy || !allocation}>{title}</PrimaryButton>
		</form>
	)

	if (bare) {
		return (
			<section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
				<h2 className="mb-4 text-sm font-semibold text-slate-800">{title}</h2>
				{form}
			</section>
		)
	}
	return form
}

export function Transfer ({ onDone }) {
	const [rows, setRows] = useState([])
	const [allocation, setAllocation] = useState('')
	const [beds, setBeds] = useState([])
	const [bed, setBed] = useState('')
	const [reason, setReason] = useState('Room maintenance')
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [busy, setBusy] = useState(false)

	function load () {
		call('hotlync.api.get_allocations', { status: 'Checked In' })
			.then((next) => {
				setRows(next)
				setAllocation(next[0]?.name || '')
			})
			.catch((err) => setError(err.message))
		call('hotlync.api.get_available_beds')
			.then((next) => {
				setBeds(next)
				setBed(next[0]?.name || '')
			})
			.catch((err) => setError(err.message))
	}

	useEffect(() => {
		load()
	}, [])

	const current = rows.find((row) => row.name === allocation)

	async function handleSubmit (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		setMessage('')
		try {
			const result = await call('hotlync.api.transfer_stay', {
				allocation,
				bed,
				reason,
			})
			setMessage(`${result.current.employee_name} moved to bed ${result.current.bed_number}. The previous stay is kept.`)
			onDone?.()
			load()
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	return (
		<Screen title="Transfers" subtitle="Move a checked-in stay. The old row stays on record and the old bed is freed." icon="arrows">
			<form className="max-w-xl space-y-3 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm" onSubmit={handleSubmit}>
				<Field label="Employee">
					<select className={inputClass} value={allocation} onChange={(event) => setAllocation(event.target.value)} required>
						<option value="">Select stay</option>
						{rows.map((row) => (
							<option key={row.name} value={row.name}>
								{row.employee_name}
							</option>
						))}
					</select>
				</Field>
				{current && (
					<p className="text-sm text-slate-500">
						Current: {current.building_name} / Room {current.room_number} / Bed {current.bed_number}
					</p>
				)}
				<Field label="Transfer to">
					<select className={inputClass} value={bed} onChange={(event) => setBed(event.target.value)} required>
						<option value="">Select bed</option>
						{beds.map((item) => (
							<option key={item.name} value={item.name}>
								{item.building_name} / {item.room_number} / {item.bed_number}
							</option>
						))}
					</select>
				</Field>
				<Field label="Reason">
					<input className={inputClass} value={reason} onChange={(event) => setReason(event.target.value)} />
				</Field>
				<Notice error={error} message={message} />
				<PrimaryButton disabled={busy || !allocation || !bed}>Transfer</PrimaryButton>
			</form>
		</Screen>
	)
}

function Screen ({ title, subtitle, icon, children }) {
	return (
		<div>
			<PageIntro icon={<Icon name={icon} className="h-5 w-5" />} title={title} subtitle={subtitle} />
			{children}
		</div>
	)
}
