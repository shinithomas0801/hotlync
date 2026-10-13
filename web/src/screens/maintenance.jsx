import { useEffect, useState } from 'react'
import { call, uploadTicketPhoto } from '../api.js'
import { Field, Notice, PageIntro, PrimaryButton, StatusPill, inputClass } from '../ui.jsx'
import { Icon } from '../icons.jsx'

const fieldClass = `${inputClass} min-h-11`

const URGENCIES = ['Low', 'Normal', 'Urgent']
const EMPTY = {
	category: '',
	urgency: 'Normal',
	property: '',
	building: '',
	room: '',
	bed: '',
	description: '',
	preferred_contact: '',
}

export function MaintenanceDesk ({ mode = 'manager' }) {
	const [rows, setRows] = useState([])
	const [properties, setProperties] = useState([])
	const [assignees, setAssignees] = useState([])
	const [counts, setCounts] = useState(null)
	const [locations, setLocations] = useState([])
	const [selected, setSelected] = useState(null)
	const [form, setForm] = useState(EMPTY)
	const [assignee, setAssignee] = useState('')
	const [teamName, setTeamName] = useState('')
	const [contractorName, setContractorName] = useState('')
	const [comment, setComment] = useState('')
	const [note, setNote] = useState('')
	const [noteType, setNoteType] = useState('Progress')
	const [evidence, setEvidence] = useState('')
	const [resolution, setResolution] = useState('')
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [loading, setLoading] = useState(true)
	const [busy, setBusy] = useState(false)
	const [photo, setPhoto] = useState(null)

	const current = rows.find((row) => row.name === selected)

	useEffect(() => {
		load()
	}, [])

	useEffect(() => {
		if (!form.property) {
			setLocations([])
			return undefined
		}
		let active = true
		call('hotlync.api.get_ticket_locations', { property: form.property })
			.then((next) => {
				if (active) {
					setLocations(next || [])
				}
			})
			.catch((err) => setError(err.message))
		return () => {
			active = false
		}
	}, [form.property])

	function load (nextName) {
		setLoading(true)
		return call('hotlync.api.get_tickets')
			.then((payload) => {
				const tickets = payload.tickets || []
				setRows(tickets)
				setProperties(payload.properties || [])
				setAssignees(payload.assignees || [])
				setCounts(payload.counts || null)
				setSelected((currentName) => {
					if (nextName) {
						return nextName
					}
					if (currentName === '') {
						return ''
					}
					if (currentName && tickets.some((row) => row.name === currentName)) {
						return currentName
					}
					return tickets[0]?.name || ''
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
			const saved = await call('hotlync.api.save_ticket', {
				category: form.category,
				urgency: form.urgency,
				property: form.property,
				building: form.building,
				room: form.room,
				bed: form.bed,
				description: form.description,
				preferred_contact: form.preferred_contact,
			})
			if (photo) {
				await uploadTicketPhoto(saved.name, photo)
			}
			setMessage(`${saved.name} submitted.`)
			setForm(EMPTY)
			setPhoto(null)
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
			setComment('')
			setNote('')
			setEvidence('')
			setResolution('')
			await load(saved.name)
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	const building = locations.find((item) => item.name === form.building)
	const rooms = building?.rooms || []
	const room = rooms.find((item) => item.name === form.room)
	const showForm = selected === ''

	return (
		<div>
			{mode === 'manager' && (
				<PageIntro
					icon={<Icon name="wrench" className="h-5 w-5" />}
					title="Maintenance"
					subtitle="A ticket does not change the bed status."
				/>
			)}
			<Notice error={error} message={message} />
			{counts && <Counts counts={counts} />}
			<div className="mt-4 grid min-w-0 gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
				<section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
					<div className="mb-3 flex items-center justify-between gap-2">
						<h2 className="text-sm font-semibold text-slate-900">Tickets</h2>
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
					{loading && <p className="text-sm text-slate-400">Loading tickets…</p>}
					{!loading && rows.length === 0 && (
						<p className="text-sm text-slate-500">No tickets yet.</p>
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
										{row.category}
									</span>
									<StatusPill status={row.status} />
								</div>
								<p className="mt-1 text-xs text-slate-500">
									{row.name}
									{row.property_name ? ` · ${row.property_name}` : ''}
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
							<h2 className="text-sm font-semibold text-slate-900">New ticket</h2>
							<Field label="Category">
								<input
									className={fieldClass}
									value={form.category}
									onChange={(event) => update('category', event.target.value)}
									required
								/>
							</Field>
							<Field label="Urgency">
								<select
									className={fieldClass}
									value={form.urgency}
									onChange={(event) => update('urgency', event.target.value)}
								>
									{URGENCIES.map((item) => (
										<option key={item} value={item}>{item}</option>
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
							<Field label="Building">
								<select
									className={fieldClass}
									value={form.building}
									onChange={(event) => {
										update('building', event.target.value)
										update('room', '')
										update('bed', '')
									}}
								>
									<option value="">Optional</option>
									{locations.map((item) => (
										<option key={item.name} value={item.name}>
											{item.building_name || item.name}
										</option>
									))}
								</select>
							</Field>
							<Field label="Room">
								<select
									className={fieldClass}
									value={form.room}
									onChange={(event) => {
										update('room', event.target.value)
										update('bed', '')
									}}
								>
									<option value="">Optional</option>
									{rooms.map((item) => (
										<option key={item.name} value={item.name}>
											{item.room_number}
										</option>
									))}
								</select>
							</Field>
							<Field label="Bed">
								<select
									className={fieldClass}
									value={form.bed}
									onChange={(event) => update('bed', event.target.value)}
								>
									<option value="">Optional</option>
									{(room?.beds || []).map((item) => (
										<option key={item.name} value={item.name}>
											{item.bed_number}
										</option>
									))}
								</select>
							</Field>
							<Field label="Description">
								<textarea
									className={fieldClass}
									value={form.description}
									onChange={(event) => update('description', event.target.value)}
									required
								/>
							</Field>
							<Field label="Photo">
								<input
									type="file"
									accept="image/*,.pdf,.txt"
									className={fieldClass}
									onChange={(event) => setPhoto(event.target.files?.[0] || null)}
								/>
							</Field>
							<Field label="Preferred contact">
								<input
									className={fieldClass}
									value={form.preferred_contact}
									onChange={(event) => update('preferred_contact', event.target.value)}
								/>
							</Field>
							<PrimaryButton disabled={busy} className="min-h-11">
								{busy ? 'Saving…' : 'Submit ticket'}
							</PrimaryButton>
						</form>
					)}
					{current && (
						<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
							<div className="mb-3 flex flex-wrap items-center justify-between gap-2">
								<h2 className="text-sm font-semibold text-slate-900">{current.name}</h2>
								<StatusPill status={current.status} />
							</div>
							<Detail row={current} />
							{current.can_assign && current.status !== 'Resolved' && current.status !== 'Closed' && (
								<div className="mt-4 space-y-2">
									<Field label="Assignee">
										<select
											className={fieldClass}
											value={assignee}
											onChange={(event) => setAssignee(event.target.value)}
										>
											<option value="">No named assignee</option>
											{assignees.map((item) => (
												<option key={item.name} value={item.name}>
													{item.full_name} ({item.name})
												</option>
											))}
										</select>
									</Field>
									<Field label="Team">
										<input
											className={fieldClass}
											value={teamName}
											onChange={(event) => setTeamName(event.target.value)}
										/>
									</Field>
									<Field label="Contractor">
										<input
											className={fieldClass}
											value={contractorName}
											onChange={(event) => setContractorName(event.target.value)}
										/>
									</Field>
									<button
										type="button"
										disabled={busy}
										onClick={() => run('hotlync.api.assign_ticket', {
											name: current.name,
											assignee,
											team_name: teamName,
											contractor_name: contractorName,
											comment,
										})}
										className="min-h-11 rounded-lg bg-[#2563EB] px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
									>
										Assign
									</button>
								</div>
							)}
							{current.can_progress && (
								<div className="mt-4 flex flex-wrap gap-2">
									{current.status !== 'In Progress' && current.status !== 'Resolved' && (
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.update_ticket', {
												name: current.name,
												status: 'In Progress',
												comment,
											})}
											className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
										>
											In progress
										</button>
									)}
									{current.status !== 'Waiting' && current.status !== 'Resolved' && (
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.update_ticket', {
												name: current.name,
												status: 'Waiting',
												comment,
											})}
											className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
										>
											Waiting
										</button>
									)}
									{current.status !== 'Resolved' && current.status !== 'Closed' && (
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.update_ticket', {
												name: current.name,
												status: 'Resolved',
												comment,
												resolution,
											})}
											className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
										>
											Resolve
										</button>
									)}
									{mode === 'manager' && current.status !== 'Closed' && (
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.update_ticket', {
												name: current.name,
												status: 'Closed',
												comment,
											})}
											className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
										>
											Close
										</button>
									)}
								</div>
							)}
							{(current.can_progress || current.can_feedback || current.can_reopen) && (
								<div className="mt-4 space-y-2">
									{current.status !== 'Resolved' && current.status !== 'Closed' && current.can_progress && (
										<Field label="Resolution">
											<textarea
												className={fieldClass}
												value={resolution}
												onChange={(event) => setResolution(event.target.value)}
											/>
										</Field>
									)}
									<Field label="Comment">
										<textarea
											className={fieldClass}
											value={comment}
											onChange={(event) => setComment(event.target.value)}
										/>
									</Field>
									{current.can_feedback && (
										<div className="space-y-2">
											{current.can_progress && (
												<Field label="Note type">
													<select
														className={fieldClass}
														value={noteType}
														onChange={(event) => setNoteType(event.target.value)}
													>
														<option value="Progress">Progress</option>
														<option value="Evidence">Evidence</option>
														<option value="Parts">Parts</option>
														<option value="Resolution">Resolution</option>
													</select>
												</Field>
											)}
											<Field label={current.can_progress ? 'Note' : 'Feedback'}>
												<textarea
													className={fieldClass}
													value={note}
													onChange={(event) => setNote(event.target.value)}
												/>
											</Field>
											{current.can_progress && noteType === 'Evidence' && (
												<Field label="Work evidence">
													<input
														className={fieldClass}
														value={evidence}
														onChange={(event) => setEvidence(event.target.value)}
													/>
												</Field>
											)}
											<button
												type="button"
												disabled={busy}
												onClick={() => run('hotlync.api.add_note', {
													name: current.name,
													note_type: current.can_progress ? noteType : 'Feedback',
													comment: note,
													evidence,
												})}
												className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
											>
												Add note
											</button>
										</div>
									)}
									{current.can_reopen && (
										<button
											type="button"
											disabled={busy}
											onClick={() => run('hotlync.api.reopen_ticket', {
												name: current.name,
												comment,
											})}
											className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
										>
											Reopen
										</button>
									)}
								</div>
							)}
							<History rows={current.updates} title="Updates" />
							<History rows={current.notes} title="Notes" note />
						</section>
					)}
				</div>
			</div>
		</div>
	)
}

function Counts ({ counts }) {
	const items = [
		['Submitted', counts.Submitted],
		['Assigned', counts.Assigned],
		['In Progress', counts['In Progress']],
		['Waiting', counts.Waiting],
		['Resolved', counts.Resolved],
		['Closed', counts.Closed],
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
		row.building_name,
		row.room_number ? `Room ${row.room_number}` : '',
		row.bed_number ? `Bed ${row.bed_number}` : '',
	].filter(Boolean).join(' · ')
	const lines = [
		['Urgency', row.urgency],
		['Location', place],
		['Reported by', row.reported_by],
		['Reported on', row.reported_on],
		['Contact', row.preferred_contact],
		['Photo', row.photo],
		['Description', row.description],
		['Assignee', row.assignee],
		['Team', row.team_name],
		['Contractor', row.contractor_name],
		['Resolution', row.resolution],
	].filter(([, value]) => value)
	return (
		<dl className="space-y-1 text-sm">
			{lines.map(([label, value]) => (
				<div key={label} className="flex flex-wrap gap-x-2 gap-y-0.5">
					<dt className="w-full text-slate-400 sm:w-28 sm:shrink-0">{label}</dt>
					<dd className="min-w-0 break-words text-slate-700">{value}</dd>
				</div>
			))}
		</dl>
	)
}

function History ({ rows, title, note = false }) {
	return (
		<div>
			<h3 className="mb-2 mt-5 text-xs font-medium uppercase tracking-wide text-slate-400">
				{title}
			</h3>
			{(rows || []).length === 0 && (
				<p className="text-sm text-slate-500">None yet.</p>
			)}
			{(rows || []).map((item, index) => (
				<div key={`${item.creation}-${index}`} className="border-t border-slate-100 py-2 text-sm">
					<div className="flex flex-wrap items-center justify-between gap-2">
						<span className="font-medium text-slate-800">
							{note ? item.note_type : item.action}
						</span>
						<span className="break-all text-xs text-slate-400">{item.creation}</span>
					</div>
					<p className="text-xs text-slate-500">{item.actor}</p>
					{item.comment && <p className="text-slate-600">{item.comment}</p>}
				</div>
			))}
		</div>
	)
}
