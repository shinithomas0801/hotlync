import { useEffect, useState } from 'react'
import { call } from '../api.js'
import { Field, Notice, PageIntro, PrimaryButton, StatusPill, inputClass } from '../ui.jsx'
import { Icon } from '../icons.jsx'

const fieldClass = `${inputClass} min-h-11`

const TYPES = [
	'Room Change',
	'Visitor Stay',
	'Family Accommodation',
	'Exit Clearance',
]

const EMPTY = {
	request_type: 'Room Change',
	property: '',
	employee: '',
	reason: '',
	preferred_date: '',
	requested_bed: '',
	visitor_name: '',
	visit_start: '',
	visit_end: '',
	family_member_name: '',
	relationship: '',
	stay_start: '',
	stay_end: '',
	intended_checkout_date: '',
}

export function RequestDesk ({ mode = 'manager' }) {
	const [rows, setRows] = useState([])
	const [properties, setProperties] = useState([])
	const [selected, setSelected] = useState(null)
	const [form, setForm] = useState(EMPTY)
	const [employees, setEmployees] = useState([])
	const [search, setSearch] = useState('')
	const [comment, setComment] = useState('')
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [loading, setLoading] = useState(true)
	const [busy, setBusy] = useState(false)

	const current = rows.find((row) => row.name === selected)
	const editable = !current || current.status === 'Draft' || current.status === 'Changes Requested'

	useEffect(() => {
		load()
	}, [])

	useEffect(() => {
		if (mode !== 'manager') {
			return undefined
		}
		const handle = setTimeout(() => {
			call('hotlync.api.get_employees', { search })
				.then(setEmployees)
				.catch((err) => setError(err.message))
		}, 200)
		return () => clearTimeout(handle)
	}, [mode, search])

	function load (nextName) {
		setLoading(true)
		return call('hotlync.api.get_requests')
			.then((payload) => {
				const requests = payload.requests || []
				setRows(requests)
				setProperties(payload.properties || [])
				setSelected((current) => {
					if (nextName) {
						return nextName
					}
					if (current === '') {
						return ''
					}
					if (current && requests.some((row) => row.name === current)) {
						return current
					}
					return requests[0]?.name || ''
				})
			})
			.catch((err) => setError(err.message))
			.finally(() => setLoading(false))
	}

	function update (field, value) {
		setForm((currentForm) => ({ ...currentForm, [field]: value }))
	}

	function fill (row) {
		setSelected(row.name)
		setComment('')
		setForm({
			...EMPTY,
			request_type: row.request_type,
			property: row.property || '',
			employee: row.employee || '',
			reason: row.reason || '',
			preferred_date: row.preferred_date || '',
			requested_bed: row.requested_bed || '',
			visitor_name: row.visitor_name || '',
			visit_start: row.visit_start || '',
			visit_end: row.visit_end || '',
			family_member_name: row.family_member_name || '',
			relationship: row.relationship || '',
			stay_start: row.stay_start || '',
			stay_end: row.stay_end || '',
			intended_checkout_date: row.intended_checkout_date || '',
		})
	}

	async function handleSave (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		setMessage('')
		try {
			const saved = await call('hotlync.api.save_request', payload(form, current))
			setMessage(`${saved.name} saved as ${saved.status}.`)
			await load(saved.name)
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
			const saved = await call(method, args)
			setMessage(note || `${saved.name} is ${saved.status}.`)
			setComment('')
			await load(saved.name)
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	return (
		<div>
			{mode === 'manager' && (
				<PageIntro
					icon={<Icon name="file" className="h-5 w-5" />}
					title="Requests & Forms"
					subtitle="One approval stage. Approving a request does not move the stay."
				/>
			)}
			<Notice error={error} message={message} />
			<div className="mt-4 grid min-w-0 gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
				<section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
					<div className="mb-3 flex items-center justify-between gap-2">
						<h2 className="text-sm font-semibold text-slate-900">
							Requests
						</h2>
						<button
							type="button"
							onClick={() => {
								setSelected('')
								setForm(EMPTY)
								setComment('')
							}}
							className="min-h-11 px-2 text-sm text-[#2563EB]"
						>
							New
						</button>
					</div>
					{loading && (
						<p className="text-sm text-slate-400">Loading requests…</p>
					)}
					{!loading && rows.length === 0 && (
						<p className="text-sm text-slate-500">No requests yet.</p>
					)}
					<div className="max-h-72 space-y-2 overflow-y-auto lg:max-h-[calc(100vh-12rem)]">
						{rows.map((row) => (
							<button
								key={row.name}
								type="button"
								onClick={() => fill(row)}
								className={`min-h-11 w-full rounded-xl border px-3 py-3 text-left ${
									row.name === selected
										? 'border-blue-200 bg-blue-50'
										: 'border-slate-100'
								}`}
							>
								<div className="flex flex-wrap items-center justify-between gap-2">
									<span className="text-sm font-medium text-slate-800">
										{row.request_type}
									</span>
									<StatusPill status={row.status} />
								</div>
								<p className="mt-1 text-xs text-slate-500">
									{row.employee_name || row.employee}
									{row.property_name ? ` · ${row.property_name}` : ''}
								</p>
							</button>
						))}
					</div>
				</section>
				<div className="space-y-4">
					{editable && (
						<form
							className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
							onSubmit={handleSave}
						>
							<h2 className="text-sm font-semibold text-slate-900">
								{current ? current.name : 'New request'}
							</h2>
							<Field label="Type">
								<select
									className={fieldClass}
									value={form.request_type}
									onChange={(event) => update('request_type', event.target.value)}
								>
									{TYPES.map((type) => (
										<option key={type} value={type}>{type}</option>
									))}
								</select>
							</Field>
							<Field label="Residence">
								<select
									className={fieldClass}
									value={form.property}
									onChange={(event) => update('property', event.target.value)}
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
							{mode === 'manager' && (
								<Field label="Employee">
									<input
										className={fieldClass}
										value={search}
										placeholder="Search name"
										onChange={(event) => setSearch(event.target.value)}
									/>
									<select
										className={`${fieldClass} mt-2`}
										value={form.employee}
										onChange={(event) => update('employee', event.target.value)}
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
							)}
							<TypeFields form={form} onChange={update} />
							<PrimaryButton disabled={busy} className="min-h-11">
								{busy ? 'Saving…' : 'Save draft'}
							</PrimaryButton>
						</form>
					)}
					{current && (
						<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
							<div className="mb-3 flex flex-wrap items-center justify-between gap-2">
								<h2 className="text-sm font-semibold text-slate-900">
									{current.name}
								</h2>
								<StatusPill status={current.status} />
							</div>
							<Detail row={current} />
							<div className="mt-4 flex flex-wrap gap-2">
								{(current.status === 'Draft' || current.status === 'Changes Requested') && (
									<button
										type="button"
										disabled={busy}
										onClick={() => run('hotlync.api.submit_request', { name: current.name })}
										className="min-h-11 rounded-lg bg-[#2563EB] px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
									>
										Submit
									</button>
								)}
								{['Draft', 'Submitted', 'Changes Requested'].includes(current.status) && mode === 'staff' && (
									<button
										type="button"
										disabled={busy}
										onClick={() => run('hotlync.api.cancel_request', { name: current.name })}
										className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
									>
										Cancel
									</button>
								)}
							</div>
							{mode === 'manager' && current.status === 'Submitted' && (
								<div className="mt-4 space-y-2">
									<Field label="Comment">
										<textarea
											className={fieldClass}
											value={comment}
											onChange={(event) => setComment(event.target.value)}
										/>
									</Field>
									<div className="flex flex-wrap gap-2">
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.decide_request', {
												name: current.name,
												action: 'Approved',
												comment,
											})}
											className="min-h-11 rounded-lg bg-[#2563EB] px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
										>
											Approve
										</button>
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.decide_request', {
												name: current.name,
												action: 'Rejected',
												comment,
											})}
											className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
										>
											Reject
										</button>
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.decide_request', {
												name: current.name,
												action: 'Changes Requested',
												comment,
											})}
											className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
										>
											Request changes
										</button>
									</div>
								</div>
							)}
							<h3 className="mb-2 mt-5 text-xs font-medium uppercase tracking-wide text-slate-400">
								History
							</h3>
							{(current.decisions || []).length === 0 && (
								<p className="text-sm text-slate-500">No decisions yet.</p>
							)}
							{(current.decisions || []).map((decision, index) => (
								<div
									key={`${decision.creation}-${index}`}
									className="border-t border-slate-100 py-2 text-sm"
								>
									<div className="flex flex-wrap items-center justify-between gap-2">
										<span className="font-medium text-slate-800">
											{decision.action}
										</span>
										<span className="break-all text-xs text-slate-400">
											{decision.creation}
										</span>
									</div>
									<p className="text-xs text-slate-500">{decision.actor}</p>
									{decision.comment && (
										<p className="text-slate-600">{decision.comment}</p>
									)}
								</div>
							))}
						</section>
					)}
				</div>
			</div>
		</div>
	)
}

function payload (form, current) {
	const body = {
		name: current && (current.status === 'Draft' || current.status === 'Changes Requested')
			? current.name
			: undefined,
		request_type: form.request_type,
		property: form.property,
		reason: form.reason,
		preferred_date: form.preferred_date,
		requested_bed: form.requested_bed,
		visitor_name: form.visitor_name,
		visit_start: form.visit_start,
		visit_end: form.visit_end,
		family_member_name: form.family_member_name,
		relationship: form.relationship,
		stay_start: form.stay_start,
		stay_end: form.stay_end,
		intended_checkout_date: form.intended_checkout_date,
	}
	if (form.employee) {
		body.employee = form.employee
	}
	return body
}

function TypeFields ({ form, onChange }) {
	if (form.request_type === 'Visitor Stay') {
		return (
			<>
				<Field label="Visitor">
					<input
						className={fieldClass}
						value={form.visitor_name}
						onChange={(event) => onChange('visitor_name', event.target.value)}
						required
					/>
				</Field>
				<Field label="Visit start">
					<input
						type="date"
						className={fieldClass}
						value={form.visit_start}
						onChange={(event) => onChange('visit_start', event.target.value)}
						required
					/>
				</Field>
				<Field label="Visit end">
					<input
						type="date"
						className={fieldClass}
						value={form.visit_end}
						onChange={(event) => onChange('visit_end', event.target.value)}
						required
					/>
				</Field>
			</>
		)
	}
	if (form.request_type === 'Family Accommodation') {
		return (
			<>
				<Field label="Family member">
					<input
						className={fieldClass}
						value={form.family_member_name}
						onChange={(event) => onChange('family_member_name', event.target.value)}
						required
					/>
				</Field>
				<Field label="Relationship">
					<input
						className={fieldClass}
						value={form.relationship}
						onChange={(event) => onChange('relationship', event.target.value)}
						required
					/>
				</Field>
				<Field label="Stay start">
					<input
						type="date"
						className={fieldClass}
						value={form.stay_start}
						onChange={(event) => onChange('stay_start', event.target.value)}
						required
					/>
				</Field>
				<Field label="Stay end">
					<input
						type="date"
						className={fieldClass}
						value={form.stay_end}
						onChange={(event) => onChange('stay_end', event.target.value)}
						required
					/>
				</Field>
			</>
		)
	}
	if (form.request_type === 'Exit Clearance') {
		return (
			<>
				<Field label="Intended check-out">
					<input
						type="date"
						className={fieldClass}
						value={form.intended_checkout_date}
						onChange={(event) => onChange('intended_checkout_date', event.target.value)}
						required
					/>
				</Field>
				<Field label="Reason">
					<textarea
						className={fieldClass}
						value={form.reason}
						onChange={(event) => onChange('reason', event.target.value)}
						required
					/>
				</Field>
			</>
		)
	}
	return (
		<>
			<Field label="Reason">
				<textarea
					className={fieldClass}
					value={form.reason}
					onChange={(event) => onChange('reason', event.target.value)}
					required
				/>
			</Field>
			<Field label="Preferred date">
				<input
					type="date"
					className={fieldClass}
					value={form.preferred_date}
					onChange={(event) => onChange('preferred_date', event.target.value)}
				/>
			</Field>
			<Field label="Requested bed">
				<input
					className={fieldClass}
					value={form.requested_bed}
					onChange={(event) => onChange('requested_bed', event.target.value)}
				/>
			</Field>
		</>
	)
}

function Detail ({ row }) {
	const lines = [
		['Employee', row.employee_name || row.employee],
		['Residence', row.property_name],
		['Submitted', row.submission_date],
		['Reason', row.reason],
		['Visitor', row.visitor_name],
		['Visit', [row.visit_start, row.visit_end].filter(Boolean).join(' to ')],
		['Family', row.family_member_name],
		['Relationship', row.relationship],
		['Stay', [row.stay_start, row.stay_end].filter(Boolean).join(' to ')],
		['Intended check-out', row.intended_checkout_date],
		['Requested bed', row.requested_bed],
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
