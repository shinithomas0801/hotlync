import { useEffect, useState } from 'react'
import { call } from '../api.js'
import { Icon } from '../icons.jsx'
import { PageIntro } from '../ui.jsx'

const later = {
	maintenance: ['Maintenance', 'wrench', 'Work orders are a later phase. Bed status can already be Maintenance, and allocation to those beds is rejected.'],
	facilities: ['Facilities Booking', 'calendar', 'Courts, rooms, and other facility bookings are a later phase.'],
	keys: ['Keys & Access', 'key', 'Key issue and return are a later phase.'],
	inventory: ['Inventory', 'box', 'Stores and stock are a later phase.'],
	lost: ['Lost & Found', 'tag', 'Lost and found is a later phase.'],
	transport: ['Transport', 'bus', 'Bus schedules are a later phase.'],
	requests: ['Requests & Forms', 'file', 'Room change, visitor, family, and exit forms are a later phase. Staff allocation is live under Accommodation.'],
	communication: ['Communication', 'chat', 'WhatsApp, email, and broadcasts are a later phase.'],
}

export function LaterModule ({ id }) {
	const [title, icon, text] = later[id] || ['Module', 'file', 'This module is a later phase.']
	return (
		<div>
			<PageIntro icon={<Icon name={icon} className="h-5 w-5" />} title={title} subtitle={text} />
			<section className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center shadow-sm">
				<div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-500">
					<Icon name={icon} className="h-6 w-6" />
				</div>
				<p className="mt-4 text-sm font-medium text-slate-700">Not in this phase</p>
				<p className="mt-1 text-sm text-slate-400">The accommodation stay is the live slice.</p>
			</section>
		</div>
	)
}

export function StaffList () {
	const [rows, setRows] = useState(null)
	const [error, setError] = useState('')
	const [search, setSearch] = useState('')

	useEffect(() => {
		const handle = setTimeout(() => {
			call('hotlync.api.get_employees', { search })
				.then((next) => {
					setRows(next)
					setError('')
				})
				.catch((err) => setError(err.message))
		}, 200)
		return () => clearTimeout(handle)
	}, [search])

	return (
		<div>
			<PageIntro
				icon={<Icon name="users" className="h-5 w-5" />}
				title="Staff"
				subtitle="Active employees from ERPNext. Adding people stays in Frappe HR for this phase."
			/>
			<section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
				<div className="border-b border-slate-100 p-4">
					<input
						value={search}
						onChange={(event) => setSearch(event.target.value)}
						placeholder="Search staff"
						className="w-full max-w-sm rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500"
					/>
				</div>
				{error && <p className="px-4 py-6 text-sm text-rose-700">{error}</p>}
				{!error && !rows && <p className="px-4 py-6 text-sm text-slate-400">Loading staff…</p>}
				{rows && (
					<table className="w-full text-left text-sm">
						<thead className="bg-slate-50 text-xs text-slate-500">
							<tr>
								<th className="px-4 py-2 font-medium">Name</th>
								<th className="px-3 py-2 font-medium">Employee</th>
								<th className="px-3 py-2 font-medium">Department</th>
								<th className="px-3 py-2 font-medium">Designation</th>
							</tr>
						</thead>
						<tbody>
							{rows.map((row) => (
								<tr key={row.name} className="border-t border-slate-100">
									<td className="px-4 py-2.5 font-medium">{row.employee_name}</td>
									<td className="px-3 py-2.5 text-slate-500">{row.name}</td>
									<td className="px-3 py-2.5 text-slate-600">{row.department || '—'}</td>
									<td className="px-3 py-2.5 text-slate-600">{row.designation || '—'}</td>
								</tr>
							))}
							{!rows.length && (
								<tr>
									<td colSpan="4" className="px-4 py-8 text-center text-slate-400">
										No matching employees.
									</td>
								</tr>
							)}
						</tbody>
					</table>
				)}
			</section>
		</div>
	)
}

export function Administration () {
	const roles = [
		['Accommodation Admin', 'Creates rooms and beds, and runs allocate, check-in, transfer, and check-out.'],
		['Accommodation Manager', 'Runs the same stay actions as Admin.'],
		['Staff', 'Reads only their own allocation. Allocate and master-data writes return 403.'],
	]
	return (
		<div>
			<PageIntro
				icon={<Icon name="settings" className="h-5 w-5" />}
				title="Administration"
				subtitle="Roles for this proof. User management stays in ERPNext."
			/>
			<div className="grid gap-4 md:grid-cols-3">
				{roles.map(([title, text]) => (
					<section key={title} className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
						<h2 className="text-sm font-semibold text-slate-900">{title}</h2>
						<p className="mt-2 text-sm text-slate-500">{text}</p>
					</section>
				))}
			</div>
		</div>
	)
}
