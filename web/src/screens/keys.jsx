import { useEffect, useState } from 'react'
import { call } from '../api.js'
import { Field, Notice, PageIntro, PrimaryButton, StatusPill, inputClass } from '../ui.jsx'
import { Icon } from '../icons.jsx'

const fieldClass = `${inputClass} min-h-11`

const KINDS = ['Key', 'Key Set']
const CONDITIONS = ['Good', 'Damaged']
const INCIDENTS = ['Lost', 'Damaged', 'Replaced', 'Decommissioned']
const EMPTY = {
	label: '',
	kind: 'Key',
	property: '',
	room: '',
	access_point: '',
}

export function KeyDesk () {
	const [rows, setRows] = useState([])
	const [properties, setProperties] = useState([])
	const [employees, setEmployees] = useState([])
	const [counts, setCounts] = useState(null)
	const [rooms, setRooms] = useState([])
	const [selected, setSelected] = useState(null)
	const [form, setForm] = useState(EMPTY)
	const [statusFilter, setStatusFilter] = useState('')
	const [employee, setEmployee] = useState('')
	const [expectedReturn, setExpectedReturn] = useState('')
	const [condition, setCondition] = useState('Good')
	const [returnCondition, setReturnCondition] = useState('Good')
	const [note, setNote] = useState('')
	const [incident, setIncident] = useState('Lost')
	const [replacedBy, setReplacedBy] = useState('')
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [loading, setLoading] = useState(true)
	const [busy, setBusy] = useState(false)

	const current = rows.find((row) => row.name === selected)

	useEffect(() => {
		load()
	}, [statusFilter])

	useEffect(() => {
		if (!form.property) {
			setRooms([])
			return undefined
		}
		let active = true
		call('hotlync.api.get_key_rooms', { property: form.property })
			.then((next) => {
				if (active) {
					setRooms(next || [])
				}
			})
			.catch((err) => setError(err.message))
		return () => {
			active = false
		}
	}, [form.property])

	function load (nextName) {
		setLoading(true)
		return call('hotlync.api.get_keys', {
			status: statusFilter || undefined,
		})
			.then((payload) => {
				const keys = payload.keys || []
				setRows(keys)
				setProperties(payload.properties || [])
				setEmployees(payload.employees || [])
				setCounts(payload.counts || null)
				setSelected((currentName) => {
					if (nextName) {
						return nextName
					}
					if (currentName === '') {
						return ''
					}
					if (currentName && keys.some((row) => row.name === currentName)) {
						return currentName
					}
					return keys[0]?.name || ''
				})
			})
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false))
	}

	function update (field, value) {
		setForm((currentForm) => ({ ...currentForm, [field]: value }))
	}

	async function handleSave (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		setMessage('')
		try {
			const saved = await call('hotlync.api.register_key', {
				label: form.label,
				kind: form.kind,
				property: form.property,
				room: form.room,
				access_point: form.access_point,
			})
			setMessage(`${saved.name} registered.`)
			setForm(EMPTY)
			await load(saved.name)
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	async function run (method, args, noteText) {
		setBusy(true)
		setError('')
		setMessage('')
		try {
			const saved = await call(method, args)
			setMessage(noteText || `${saved.name} is ${saved.status}.`)
			setNote('')
			setExpectedReturn('')
			setCondition('Good')
			setReturnCondition('Good')
			setReplacedBy('')
			await load(saved.name)
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	const showForm = selected === ''
	const replacements = rows.filter(
		(row) => current && row.property === current.property && row.name !== current.name,
	)

	return (
		<div>
			<PageIntro
				icon={<Icon name="key" className="h-5 w-5" />}
				title="Keys & Access"
				subtitle="Issue and return are recorded here. Check-in does not hand over a key."
			/>
			<Notice error={error} message={message} />
			{counts && <Counts counts={counts} />}
			<div className="mt-4 grid min-w-0 gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
				<section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
					<div className="mb-3 flex flex-wrap items-center justify-between gap-2">
						<h2 className="text-sm font-semibold text-slate-900">Keys</h2>
						<div className="flex flex-wrap gap-2">
							<button
								type="button"
								onClick={() => setStatusFilter('')}
								className={`min-h-11 px-2 text-sm ${statusFilter === '' ? 'text-[#2563EB]' : 'text-slate-500'}`}
							>
								All
							</button>
							<button
								type="button"
								onClick={() => setStatusFilter('Issued')}
								className={`min-h-11 px-2 text-sm ${statusFilter === 'Issued' ? 'text-[#2563EB]' : 'text-slate-500'}`}
							>
								Outstanding
							</button>
							<button
								type="button"
								onClick={() => {
									setSelected('')
									setForm(EMPTY)
								}}
								className="min-h-11 px-2 text-sm text-[#2563EB]"
							>
								New
							</button>
						</div>
					</div>
					{loading && <p className="text-sm text-slate-400">Loading keys…</p>}
					{!loading && rows.length === 0 && (
						<p className="text-sm text-slate-500">No keys yet.</p>
					)}
					<div className="max-h-72 space-y-2 overflow-y-auto lg:max-h-[calc(100vh-12rem)]">
						{rows.map((row) => (
							<button
								key={row.name}
								type="button"
								onClick={() => setSelected(row.name)}
								className={`min-h-11 w-full rounded-xl border px-3 py-3 text-left ${
									row.name === selected
										? 'border-blue-200 bg-blue-50'
										: 'border-slate-100'
								}`}
							>
								<div className="flex flex-wrap items-center justify-between gap-2">
									<span className="min-w-0 break-words text-sm font-medium text-slate-800">
										{row.label}
									</span>
									<StatusPill status={row.status} />
								</div>
								<p className="mt-1 text-xs text-slate-500">
									{row.name}
									{row.property_name ? ` · ${row.property_name}` : ''}
									{row.status === 'Issued'
										? ` · ${row.expected_return || 'No expected return date'}`
										: ''}
								</p>
							</button>
						))}
					</div>
				</section>
				<div className="space-y-4">
					{showForm && (
						<form
							className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
							onSubmit={handleSave}
						>
							<h2 className="text-sm font-semibold text-slate-900">Register a key</h2>
							<Field label="Key mark">
								<input
									className={fieldClass}
									value={form.label}
									onChange={(event) => update('label', event.target.value)}
									required
								/>
							</Field>
							<Field label="Type">
								<select
									className={fieldClass}
									value={form.kind}
									onChange={(event) => update('kind', event.target.value)}
								>
									{KINDS.map((item) => (
										<option key={item} value={item}>{item}</option>
									))}
								</select>
							</Field>
							<Field label="Residence">
								<select
									className={fieldClass}
									value={form.property}
									onChange={(event) => {
										update('property', event.target.value)
										update('room', '')
									}}
									required
								>
									<option value="">Select residence</option>
									{properties.map((item) => (
										<option key={item.name} value={item.name}>
											{item.property_name || item.name}
										</option>
									))}
								</select>
							</Field>
							<Field label="Room">
								<select
									className={fieldClass}
									value={form.room}
									onChange={(event) => update('room', event.target.value)}
								>
									<option value="">Optional</option>
									{rooms.map((item) => (
										<option key={item.name} value={item.name}>
											{item.building_name ? `${item.building_name} · ` : ''}
											{item.room_number}
										</option>
									))}
								</select>
							</Field>
							<Field label="Access point">
								<input
									className={fieldClass}
									value={form.access_point}
									onChange={(event) => update('access_point', event.target.value)}
									placeholder="Use this when the key is not for a room"
								/>
							</Field>
							<PrimaryButton disabled={busy} className="min-h-11">
								{busy ? 'Saving…' : 'Register key'}
							</PrimaryButton>
						</form>
					)}
					{current && (
						<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
							<div className="mb-3 flex flex-wrap items-center justify-between gap-2">
								<h2 className="min-w-0 break-words text-sm font-semibold text-slate-900">
									{current.label}
								</h2>
								<StatusPill status={current.status} />
							</div>
							<Detail row={current} />
							{current.can_issue && (
								<div className="mt-4 space-y-2">
									<Field label="Recipient">
										<select
											className={fieldClass}
											value={employee}
											onChange={(event) => setEmployee(event.target.value)}
										>
											<option value="">Select employee</option>
											{employees.map((item) => (
												<option key={item.name} value={item.name}>
													{item.employee_name} ({item.name})
												</option>
											))}
										</select>
									</Field>
									<Field label="Expected return">
										<input
											type="date"
											className={fieldClass}
											value={expectedReturn}
											onChange={(event) => setExpectedReturn(event.target.value)}
										/>
									</Field>
									<Field label="Condition">
										<select
											className={fieldClass}
											value={condition}
											onChange={(event) => setCondition(event.target.value)}
										>
											{CONDITIONS.map((item) => (
												<option key={item} value={item}>{item}</option>
											))}
										</select>
									</Field>
									<button
										type="button"
										disabled={busy}
										onClick={() => run('hotlync.api.issue_key', {
											name: current.name,
											employee,
											expected_return: expectedReturn,
											condition,
										})}
										className="min-h-11 rounded-lg bg-[#2563EB] px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
									>
										Issue
									</button>
								</div>
							)}
							{current.can_return && (
								<div className="mt-4 space-y-2">
									<Field label="Condition on return">
										<select
											className={fieldClass}
											value={returnCondition}
											onChange={(event) => setReturnCondition(event.target.value)}
										>
											{CONDITIONS.map((item) => (
												<option key={item} value={item}>{item}</option>
											))}
										</select>
									</Field>
									<Field label="Note">
										<textarea
											className={fieldClass}
											value={note}
											onChange={(event) => setNote(event.target.value)}
										/>
									</Field>
									<button
										type="button"
										disabled={busy}
										onClick={() => run('hotlync.api.return_key', {
											name: current.name,
											condition: returnCondition,
											note,
										})}
										className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
									>
										Return
									</button>
								</div>
							)}
							{current.can_record && (
								<div className="mt-4 space-y-2">
									<Field label="Incident">
										<select
											className={fieldClass}
											value={incident}
											onChange={(event) => setIncident(event.target.value)}
										>
											{INCIDENTS.map((item) => (
												<option key={item} value={item}>{item}</option>
											))}
										</select>
									</Field>
									{incident === 'Replaced' && (
										<Field label="Replacement key">
											<select
												className={fieldClass}
												value={replacedBy}
												onChange={(event) => setReplacedBy(event.target.value)}
											>
												<option value="">Optional</option>
												{replacements.map((item) => (
													<option key={item.name} value={item.name}>
														{item.label} ({item.name})
													</option>
												))}
											</select>
										</Field>
									)}
									<Field label="Incident note">
										<textarea
											className={fieldClass}
											value={note}
											onChange={(event) => setNote(event.target.value)}
										/>
									</Field>
									<button
										type="button"
										disabled={busy}
										onClick={() => run('hotlync.api.record_key_incident', {
											name: current.name,
											status: incident,
											note,
											replaced_by: replacedBy,
										})}
										className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
									>
										Record incident
									</button>
								</div>
							)}
							<History rows={current.movements} />
						</section>
					)}
				</div>
			</div>
		</div>
	)
}

function Counts ({ counts }) {
	const items = [
		['Available', counts.Available],
		['Outstanding', counts.Issued],
		['Lost', counts.Lost],
		['Damaged', counts.Damaged],
		['Replaced', counts.Replaced],
		['Decommissioned', counts.Decommissioned],
	]
	return (
		<div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
			{items.map(([label, value]) => (
				<div key={label} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
					<div className="text-xs text-slate-400">{label}</div>
					<div className="text-lg font-semibold text-slate-800">{value || 0}</div>
				</div>
			))}
		</div>
	)
}

function Detail ({ row }) {
	const place = [
		row.property_name,
		row.room_number ? `Room ${row.room_number}` : '',
		row.access_point || '',
	].filter(Boolean).join(' · ')
	const lines = [
		['Type', row.kind],
		['Location', place],
		['Condition', row.condition],
		['Recipient', row.employee_name || row.employee],
		['Custodian', row.custodian],
		['Issued on', row.issued_on],
		[
			'Expected return',
			row.status === 'Issued'
				? (row.expected_return || 'No expected return date')
				: row.expected_return,
		],
		['Replaced by', row.replaced_by],
	].filter(([, value]) => value)
	return (
		<dl className="space-y-1 text-sm">
			{lines.map(([label, value]) => (
				<div key={label} className="flex flex-wrap gap-x-2 gap-y-0.5">
					<dt className="w-full text-slate-400 sm:w-36 sm:shrink-0">{label}</dt>
					<dd className="min-w-0 break-words text-slate-700">{value}</dd>
				</div>
			))}
		</dl>
	)
}

function History ({ rows }) {
	return (
		<div>
			<h3 className="mb-2 mt-5 text-xs font-medium uppercase tracking-wide text-slate-400">
				History
			</h3>
			{(rows || []).length === 0 && (
				<p className="text-sm text-slate-500">No movements yet.</p>
			)}
			{(rows || []).map((item, index) => (
				<div key={`${item.occurred_on}-${index}`} className="border-t border-slate-100 py-2 text-sm">
					<div className="flex flex-wrap items-center justify-between gap-2">
						<span className="font-medium text-slate-800">{item.action}</span>
						<span className="break-all text-xs text-slate-400">{item.occurred_on}</span>
					</div>
					<p className="break-all text-xs text-slate-500">
						{item.actor}
						{item.recipient_name ? ` · ${item.recipient_name}` : ''}
						{item.condition ? ` · ${item.condition}` : ''}
					</p>
					{item.note && <p className="text-slate-600">{item.note}</p>}
				</div>
			))}
		</div>
	)
}
