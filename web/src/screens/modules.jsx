import { useEffect, useState } from 'react'
import { call } from '../api.js'
import { isGroupRole } from '../format.js'
import { Icon } from '../icons.jsx'
import { Field, Notice, PageIntro, PrimaryButton, inputClass } from '../ui.jsx'

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

export function Administration ({ roles, onChanged }) {
	const group = isGroupRole(roles)
	const rolesCopy = [
		['Accommodation Admin', 'Sees every property. Creates properties and assigns managers.'],
		['Accommodation Manager', 'Sees only assigned properties. With no assignment, property lists are empty.'],
		['Staff', 'Opens a stay page for their own allocations. Manager calls return 403.'],
	]
	return (
		<div className="space-y-4">
			<PageIntro
				icon={<Icon name="settings" className="h-5 w-5" />}
				title="Administration"
				subtitle="Create a login, set Staff, Accommodation Manager, or Accommodation Admin, and assign a manager to a residence. Property scope is provisional."
			/>
			<div className="grid gap-4 md:grid-cols-3">
				{rolesCopy.map(([title, text]) => (
					<section key={title} className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
						<h2 className="text-sm font-semibold text-slate-900">{title}</h2>
						<p className="mt-2 text-sm text-slate-500">{text}</p>
					</section>
				))}
			</div>
			{group && <AccessDesk onChanged={onChanged} />}
		</div>
	)
}

function AccessDesk ({ onChanged }) {
	const [users, setUsers] = useState([])
	const [roles, setRoles] = useState([])
	const [properties, setProperties] = useState([])
	const [form, setForm] = useState({
		email: '',
		first_name: '',
		last_name: '',
		role: 'Staff',
		password: '',
	})
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [busy, setBusy] = useState(false)

	useEffect(() => {
		load()
		call('hotlync.api.get_accommodation')
			.then((tree) => setProperties(tree || []))
			.catch((err) => setError(err.message))
	}, [])

	function load () {
		return call('hotlync.api.get_user_access')
			.then((payload) => {
				setUsers(payload.users || [])
				setRoles(payload.roles || [])
			})
			.catch((err) => setError(err.message))
	}

	function update (field, value) {
		setForm((current) => ({ ...current, [field]: value }))
	}

	async function handleCreate (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		setMessage('')
		try {
			const saved = await call('hotlync.api.create_user_access', form)
			setForm({
				email: '',
				first_name: '',
				last_name: '',
				role: 'Staff',
				password: '',
			})
			await load()
			setMessage(`${saved.name} created.`)
			if (onChanged) {
				onChanged()
			}
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	async function run (method, args, note) {
		setBusy(true)
		setError('')
		setMessage('')
		try {
			await call(method, args)
			await load()
			setMessage(note)
			if (onChanged) {
				onChanged()
			}
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	const fieldClass = `${inputClass} min-h-11`

	return (
		<div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
			<form
				onSubmit={handleCreate}
				className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
			>
				<h2 className="text-sm font-semibold text-slate-900">New login</h2>
				<p className="text-sm text-slate-500">No welcome email is sent.</p>
				<Notice error={error} message={message} />
				<Field label="User id">
					<input
						className={fieldClass}
						value={form.email}
						onChange={(event) => update('email', event.target.value)}
						required
					/>
				</Field>
				<Field label="First name">
					<input
						className={fieldClass}
						value={form.first_name}
						onChange={(event) => update('first_name', event.target.value)}
						required
					/>
				</Field>
				<Field label="Last name">
					<input
						className={fieldClass}
						value={form.last_name}
						onChange={(event) => update('last_name', event.target.value)}
					/>
				</Field>
				<Field label="Role">
					<select
						className={fieldClass}
						value={form.role}
						onChange={(event) => update('role', event.target.value)}
					>
						{(roles.length ? roles : ['Staff']).map((role) => (
							<option key={role} value={role}>{role}</option>
						))}
					</select>
				</Field>
				<Field label="Password">
					<input
						type="password"
						className={fieldClass}
						value={form.password}
						onChange={(event) => update('password', event.target.value)}
						required
					/>
				</Field>
				<PrimaryButton disabled={busy} className="min-h-11">
					{busy ? 'Saving…' : 'Create login'}
				</PrimaryButton>
			</form>
			<section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
				<h2 className="mb-3 text-sm font-semibold text-slate-900">People</h2>
				<div className="max-h-[32rem] space-y-3 overflow-y-auto">
					{users.length === 0 && (
						<p className="text-sm text-slate-500">No logins yet.</p>
					)}
					{users.map((user) => (
						<UserCard
							key={user.name}
							user={user}
							roles={roles}
							properties={properties}
							busy={busy}
							onRun={run}
						/>
					))}
				</div>
			</section>
		</div>
	)
}

function UserCard ({ user, roles, properties, busy, onRun }) {
	const [role, setRole] = useState(user.roles[0] || 'Staff')
	const [property, setProperty] = useState('')
	const fieldClass = `${inputClass} min-h-11`
	const active = user.enabled === 1 || user.enabled === true

	return (
		<div className="rounded-xl border border-slate-100 p-3">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="min-w-0">
					<p className="break-words text-sm font-medium text-slate-800">{user.full_name}</p>
					<p className="break-all text-xs text-slate-500">{user.name}</p>
				</div>
				<span
					className={
						active
							? 'rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700'
							: 'rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500'
					}
				>
					{active ? 'Active' : 'Deactivated'}
				</span>
			</div>
			<div className="mt-3 flex flex-wrap gap-2">
				<select
					className={fieldClass}
					value={role}
					onChange={(event) => setRole(event.target.value)}
				>
					{roles.map((item) => (
						<option key={item} value={item}>{item}</option>
					))}
				</select>
				<button
					type="button"
					disabled={busy}
					onClick={() => onRun('hotlync.api.set_user_role', { user: user.name, role }, `${user.name} is ${role}.`)}
					className="min-h-11 rounded-lg border border-slate-200 px-3 text-sm text-slate-700 disabled:opacity-50"
				>
					Set role
				</button>
				<button
					type="button"
					disabled={busy}
					onClick={() => onRun(
						'hotlync.api.set_user_enabled',
						{ user: user.name, enabled: active ? 0 : 1 },
						active ? `${user.name} deactivated.` : `${user.name} activated.`,
					)}
					className="min-h-11 rounded-lg border border-slate-200 px-3 text-sm text-slate-700 disabled:opacity-50"
				>
					{active ? 'Deactivate' : 'Activate'}
				</button>
			</div>
			{user.roles.includes('Accommodation Manager') && (
				<div className="mt-3 space-y-2">
					{(user.properties || []).map((item) => (
						<div key={item.name} className="flex flex-wrap items-center justify-between gap-2">
							<span className="min-w-0 break-words text-sm text-slate-700">
								{item.property_name || item.property}
							</span>
							<button
								type="button"
								disabled={busy}
								onClick={() => onRun(
									'hotlync.api.revoke_user_property',
									{ name: item.name },
									`${item.property_name || item.property} removed.`,
								)}
								className="min-h-11 px-2 text-sm text-rose-700 disabled:opacity-50"
							>
								Remove
							</button>
						</div>
					))}
					<div className="flex flex-wrap gap-2">
						<select
							className={fieldClass}
							value={property}
							onChange={(event) => setProperty(event.target.value)}
						>
							<option value="">Select residence</option>
							{properties.map((item) => (
								<option key={item.name} value={item.name}>
									{item.property_name || item.name}
								</option>
							))}
						</select>
						<button
							type="button"
							disabled={busy || !property}
							onClick={() => onRun(
								'hotlync.api.assign_user_property',
								{ user: user.name, property },
								'Residence assigned.',
							)}
							className="min-h-11 rounded-lg bg-[#2563EB] px-3 text-sm font-medium text-white disabled:opacity-50"
						>
							Assign
						</button>
					</div>
				</div>
			)}
		</div>
	)
}
