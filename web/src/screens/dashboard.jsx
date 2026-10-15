import { useEffect, useState } from 'react'
import { call } from '../api.js'
import {
	activityLabel,
	friendlyName,
	greeting,
	initials,
	percent,
	todayIso,
} from '../format.js'
import { Icon } from '../icons.jsx'
import { NoticeList } from '../notices.jsx'
import { Panel, StatusPill } from '../ui.jsx'

export function Dashboard ({ user, version, onOpen }) {
	const [counts, setCounts] = useState(null)
	const [tree, setTree] = useState([])
	const [buildings, setBuildings] = useState([])
	const [activity, setActivity] = useState([])
	const [error, setError] = useState('')
	const [showAll, setShowAll] = useState(false)
	const [propertyId, setPropertyId] = useState('')
	const [now, setNow] = useState(() => new Date())

	useEffect(() => {
		const timer = setInterval(() => setNow(new Date()), 30000)
		return () => clearInterval(timer)
	}, [])

	useEffect(() => {
		let active = true
		Promise.all([
			call(
				'hotlync.api.get_accommodation_report',
				propertyId ? { property: propertyId } : {},
			),
			call('hotlync.api.get_accommodation'),
			call('hotlync.api.get_allocations', propertyId ? { property: propertyId } : {}),
		])
			.then(([report, nextTree, rows]) => {
				if (!active) {
					return
				}
				setCounts(report)
				setTree(nextTree || [])
				setBuildings(report.buildings || [])
				setActivity(rows || [])
				setError('')
			})
			.catch((err) => {
				if (active) {
					setError(err.message)
				}
			})
		return () => {
			active = false
		}
	}, [version, propertyId])

	if (error) {
		return (
			<div className="rounded-2xl border border-rose-100 bg-white p-6 text-sm text-rose-700">
				{error}
			</div>
		)
	}
	if (!counts) {
		return <LoadingGrid />
	}

	const today = todayIso()
	const checkIns = counts.check_ins_today
	const checkOuts = counts.check_outs_today
	const occupiedPct = percent(counts.occupied, counts.total)
	const availablePct = percent(counts.available, counts.total)
	const maintenancePct = percent(counts.maintenance, counts.total)
	const name = friendlyName(user)
	const dateLabel = now.toLocaleDateString('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		year: 'numeric',
	})
	const timeLabel = now.toLocaleTimeString('en-GB', {
		hour: '2-digit',
		minute: '2-digit',
	})
	const visibleActivity = showAll ? activity : activity.slice(0, 5)

	return (
		<div>
			<div className="mb-4 flex flex-wrap items-end justify-between gap-3">
				<div>
					<h1 className="text-2xl font-semibold text-slate-900">
						{greeting(now)}, {name}!
					</h1>
					<p className="text-sm text-slate-500">
						Here's what's happening at SAMS today.
					</p>
				</div>
				<div className="flex items-center gap-2">
					{tree.length > 1 && (
						<select
							value={propertyId}
							onChange={(event) => setPropertyId(event.target.value)}
							className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm"
						>
							<option value="">All properties</option>
							{tree.map((item) => (
								<option key={item.name} value={item.name}>
									{item.property_name}
								</option>
							))}
						</select>
					)}
					<div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 shadow-sm">
					<Icon name="calendar" className="h-4 w-4 text-slate-400" />
					<span>
						{dateLabel}
						<span className="mt-0.5 block text-xs text-slate-400">{timeLabel}</span>
					</span>
					</div>
				</div>
			</div>
			<div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
				<div className="space-y-4">
					<div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
						<Metric
							icon="bed"
							tint="bg-blue-50 text-blue-600"
							label="Total Beds"
							value={counts.total}
							hint={`Across ${buildings.length} building${buildings.length === 1 ? '' : 's'}`}
						/>
						<Metric
							icon="users"
							tint="bg-emerald-50 text-emerald-600"
							label="Occupied Beds"
							value={counts.occupied}
							hint={`${occupiedPct}% occupancy`}
							bar={occupiedPct}
							barClass="bg-emerald-500"
						/>
						<Metric
							icon="bed"
							tint="bg-sky-50 text-sky-600"
							label="Available Beds"
							value={counts.available}
							hint={`${availablePct}% available`}
							bar={availablePct}
							barClass="bg-sky-500"
						/>
						<Metric
							icon="wrench"
							tint="bg-orange-50 text-orange-500"
							label="Maintenance Beds"
							value={counts.maintenance}
							hint={`${maintenancePct}% under maintenance`}
							bar={maintenancePct}
							barClass="bg-orange-400"
						/>
					</div>
					<div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
						<Metric
							icon="file"
							tint="bg-violet-50 text-violet-600"
							label="Pending Requests"
							value="0"
							hint="Later phase"
						/>
						<Metric
							icon="wrench"
							tint="bg-rose-50 text-rose-500"
							label="Open Maintenance"
							value="0"
							hint="Later phase"
						/>
						<Metric
							icon="door"
							tint="bg-blue-50 text-blue-600"
							label="Today's Check-ins"
							value={checkIns}
							hint="Recorded today"
						/>
						<Metric
							icon="logout"
							tint="bg-emerald-50 text-emerald-600"
							label="Today's Check-outs"
							value={checkOuts}
							hint="Recorded today"
						/>
					</div>
					<div className="grid gap-4 lg:grid-cols-2">
						<Panel title="Occupancy Overview">
							<Donut
								occupied={counts.occupied}
								available={counts.available}
								maintenance={counts.maintenance}
								total={counts.total}
							/>
						</Panel>
						<Panel title="Occupancy by Building">
							<BuildingBars buildings={buildings} />
						</Panel>
					</div>
					<div className="grid gap-4 lg:grid-cols-2">
						<Panel
							title="Recent Accommodation Activity"
							action={
								<button
									type="button"
									onClick={() => setShowAll((open) => !open)}
									className="text-xs font-medium text-[#2563EB]"
								>
									{showAll ? 'Show less' : 'View all activity'}
								</button>
							}
						>
							<ActivityList rows={visibleActivity} today={today} />
						</Panel>
						<Panel
							title="Facility Bookings"
							action={
								<button
									type="button"
									onClick={() => onOpen('facilities')}
									className="text-xs font-medium text-[#2563EB]"
								>
									View all
								</button>
							}
						>
							<LaterNote text="Facility booking opens in a later phase." />
						</Panel>
					</div>
					<p className="text-center text-[11px] text-slate-400">
						SAMS v1.0 · Secure · Reliable · Connected
					</p>
				</div>
				<div className="space-y-4">
					<Panel title="Quick Actions">
						<div className="grid grid-cols-2 gap-3">
							<Quick
								icon="users"
								label="New Accommodation Request"
								onClick={() => onOpen('allocate')}
							/>
							<Quick
								icon="wrench"
								label="Create Maintenance Request"
								onClick={() => onOpen('maintenance')}
							/>
							<Quick
								icon="calendar"
								label="Book Facility"
								onClick={() => onOpen('facilities')}
							/>
							<Quick
								icon="key"
								label="Issue Key"
								onClick={() => onOpen('keys')}
							/>
							<Quick
								icon="user"
								label="Add Staff"
								onClick={() => onOpen('staff')}
							/>
							<Quick
								icon="report"
								label="View Reports"
								onClick={() => onOpen('occupancy')}
							/>
						</div>
					</Panel>
					<Panel
						title="Upcoming Bookings"
						action={
							<button
								type="button"
								onClick={() => onOpen('facilities')}
								className="text-xs font-medium text-[#2563EB]"
							>
								View all
							</button>
						}
					>
						<LaterNote text="No facility bookings in this phase." />
					</Panel>
					<Panel title="Recent Notifications">
						<NoticeList />
					</Panel>
				</div>
			</div>
		</div>
	)
}

export function Occupancy ({ version }) {
	const [counts, setCounts] = useState(null)
	const [buildings, setBuildings] = useState([])
	const [error, setError] = useState('')

	useEffect(() => {
		let active = true
		call('hotlync.api.get_accommodation_report')
			.then((report) => {
				if (!active) {
					return
				}
				setCounts(report)
				setBuildings(report.buildings || [])
			})
			.catch((err) => active && setError(err.message))
		return () => {
			active = false
		}
	}, [version])

	if (error) {
		return (
			<div className="rounded-2xl border border-rose-100 bg-white p-6 text-sm text-rose-700">
				{error}
			</div>
		)
	}
	if (!counts) {
		return <LoadingGrid />
	}

	return (
		<div className="grid gap-4 lg:grid-cols-2">
			<Panel title="Occupancy Overview">
				<Donut
					occupied={counts.occupied}
					available={counts.available}
					maintenance={counts.maintenance}
					total={counts.total}
				/>
			</Panel>
			<Panel title="Occupancy by Building">
				<BuildingBars buildings={buildings} />
			</Panel>
		</div>
	)
}

function Metric ({ icon, tint, label, value, hint, bar, barClass }) {
	return (
		<div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
			<div className="flex items-start gap-3">
				<div className={`flex h-10 w-10 items-center justify-center rounded-full ${tint}`}>
					<Icon name={icon} className="h-5 w-5" />
				</div>
				<div className="min-w-0">
					<div className="text-xs text-slate-500">{label}</div>
					<div className="text-2xl font-semibold text-slate-900">{value}</div>
				</div>
			</div>
			{hint && <div className="mt-3 text-xs text-slate-400">{hint}</div>}
			{typeof bar === 'number' && (
				<div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
					<div className={`h-full rounded-full ${barClass}`} style={{ width: `${bar}%` }} />
				</div>
			)}
		</div>
	)
}

function Donut ({ occupied, available, maintenance, total }) {
	const occupiedPct = percent(occupied, total)
	const availablePct = percent(available, total)
	const maintenancePct = percent(maintenance, total)
	const rings = [
		['#22c55e', occupiedPct, 0],
		['#38bdf8', availablePct, -occupiedPct],
		['#fb923c', maintenancePct, -(occupiedPct + availablePct)],
	]
	return (
		<div className="flex flex-wrap items-center gap-6">
			<div className="relative h-40 w-40">
				<svg viewBox="0 0 36 36" className="h-full w-full -rotate-90">
					<circle cx="18" cy="18" r="14" fill="none" stroke="#e8eef5" strokeWidth="4" />
					{rings.map(([color, amount, offset]) => (
						<circle
							key={color}
							cx="18"
							cy="18"
							r="14"
							fill="none"
							stroke={color}
							strokeWidth="4"
							pathLength="100"
							strokeDasharray={`${amount} ${100 - amount}`}
							strokeDashoffset={offset}
						/>
					))}
				</svg>
				<div className="absolute inset-0 flex flex-col items-center justify-center">
					<div className="text-2xl font-semibold text-slate-900">{occupiedPct}%</div>
					<div className="text-xs text-slate-400">Occupied</div>
				</div>
			</div>
			<ul className="space-y-2 text-sm text-slate-600">
				<Legend color="bg-emerald-500" label="Occupied" value={occupied} total={total} />
				<Legend color="bg-sky-400" label="Available" value={available} total={total} />
				<Legend color="bg-orange-400" label="Maintenance" value={maintenance} total={total} />
			</ul>
		</div>
	)
}

function Legend ({ color, label, value, total }) {
	return (
		<li className="flex items-center gap-2">
			<span className={`h-2.5 w-2.5 rounded-full ${color}`} />
			<span>{label}</span>
			<span className="text-slate-400">
				{value} ({percent(value, total)}%)
			</span>
		</li>
	)
}

function BuildingBars ({ buildings }) {
	if (!buildings.length) {
		return <p className="text-sm text-slate-400">No buildings yet.</p>
	}
	const colors = ['bg-blue-500', 'bg-teal-500', 'bg-indigo-500', 'bg-amber-400']
	return (
		<div className="flex h-52 items-end gap-4 border-b border-slate-100 px-2">
			{buildings.map((building, index) => {
				const occupied = building.occupied || 0
				const total = building.total ?? building.bedCount ?? 0
				const value = percent(occupied, total)
				const label = building.building_name || building.buildingName
				return (
					<div key={building.name} className="flex flex-1 flex-col items-center gap-2">
						<div className="text-xs font-medium text-slate-500">{value}%</div>
						<div className="flex h-36 w-full items-end justify-center">
							<div
								className={`w-10 rounded-t-md ${colors[index % colors.length]}`}
								style={{ height: `${Math.max(value, 4)}%` }}
							/>
						</div>
						<div className="text-center text-xs text-slate-500">{label}</div>
					</div>
				)
			})}
		</div>
	)
}

function ActivityList ({ rows, today }) {
	if (!rows.length) {
		return <p className="text-sm text-slate-400">No stays recorded yet.</p>
	}
	return (
		<ul className="divide-y divide-slate-100">
			{rows.map((row) => (
				<li key={row.name} className="flex items-center gap-3 py-2.5">
					<div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
						{initials(row.employee_name)}
					</div>
					<div className="min-w-0 flex-1">
						<div className="truncate text-sm font-medium text-slate-800">
							{row.employee_name}
						</div>
						<div className="truncate text-xs text-slate-400">
							{row.building_name} / {row.room_number} / {row.bed_number}
						</div>
					</div>
					<StatusPill status={activityLabel(row.status)} />
					<div className="w-16 text-right text-xs text-slate-400">
						{whenLabel(row, today)}
					</div>
				</li>
			))}
		</ul>
	)
}

function whenLabel (row, today) {
	const value = row.check_out_date || row.check_in_date || row.allocation_date
	if (!value) {
		return ''
	}
	if (value === today) {
		return 'Today'
	}
	return value.slice(5)
}

function Quick ({ icon, label, onClick }) {
	return (
		<button
			type="button"
			onClick={onClick}
			className="flex flex-col items-center gap-2 rounded-xl border border-slate-200 px-2 py-3 text-center text-[11px] font-medium text-slate-600 hover:border-blue-200 hover:bg-blue-50"
		>
			<span className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-50 text-[#2563EB]">
				<Icon name={icon} className="h-4 w-4" />
			</span>
			{label}
		</button>
	)
}

function LaterNote ({ text }) {
	return <p className="py-6 text-center text-sm text-slate-400">{text}</p>
}

function LoadingGrid () {
	return (
		<div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
			{Array.from({ length: 4 }, (_, index) => (
				<div key={index} className="h-28 animate-pulse rounded-2xl bg-white" />
			))}
		</div>
	)
}
