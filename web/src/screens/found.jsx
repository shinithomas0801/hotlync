import { useEffect, useState } from 'react'
import { call, uploadFoundItemImage } from '../api.js'
import { Icon } from '../icons.jsx'
import { Field, Notice, PageIntro, PrimaryButton, StatusPill, inputClass } from '../ui.jsx'

const fieldClass = `${inputClass} min-h-11`
const EMPTY = {
	description: '',
	category: '',
	property: '',
	foundLocation: '',
	foundOn: '',
}

export function FoundDesk ({ user }) {
	const [rows, setRows] = useState(null)
	const [properties, setProperties] = useState([])
	const [form, setForm] = useState(EMPTY)
	const [image, setImage] = useState(null)
	const [selected, setSelected] = useState('')
	const [error, setError] = useState('')
	const [message, setMessage] = useState('')
	const [loading, setLoading] = useState(true)
	const [busy, setBusy] = useState(false)

	const current = (rows || []).find((row) => row.name === selected)

	useEffect(() => {
		load()
	}, [])

	function load (nextName) {
		setLoading(true)
		return call('hotlync.api.get_found_items')
			.then((payload) => {
				const items = payload.items || []
				setRows(items)
				setProperties(payload.properties || [])
				setError('')
				setSelected((currentName) => {
					if (nextName) {
						return nextName
					}
					if (currentName && items.some((row) => row.name === currentName)) {
						return currentName
					}
					return items[0]?.name || ''
				})
			})
			.catch((err) => {
				setRows([])
				setError(err.message)
			})
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
			const saved = await call('hotlync.api.register_found_item', {
				description: form.description,
				category: form.category,
				property: form.property,
				found_location: form.foundLocation,
				found_on: form.foundOn,
			})
			if (image) {
				await uploadFoundItemImage(saved.name, image)
			}
			setForm(EMPTY)
			setImage(null)
			setMessage(`${saved.name} is reported.`)
			await load(saved.name)
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	return (
		<div>
			<PageIntro
				icon={<Icon name="tag" className="h-5 w-5" />}
				title="Lost & Found"
				subtitle="Register a found item. Claims, handover, and disposal are not in this slice. The custodian is the person registering it."
			/>
			<Notice error={error} message={message} />
			<div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
				<section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
					<h2 className="text-sm font-semibold text-slate-800">Register</h2>
					<form className="mt-3 space-y-3" noValidate onSubmit={handleSave}>
						<Field label="Description">
							<textarea
								aria-label="Description"
								className={`${fieldClass} min-h-24`}
								value={form.description}
								onChange={(event) => update('description', event.target.value)}
							/>
						</Field>
						<Field label="Category">
							<input
								aria-label="Category"
								className={fieldClass}
								value={form.category}
								onChange={(event) => update('category', event.target.value)}
							/>
						</Field>
						<Field label="Residence">
							<select
								aria-label="Residence"
								className={fieldClass}
								value={form.property}
								onChange={(event) => update('property', event.target.value)}
							>
								<option value="">Select a residence</option>
								{properties.map((item) => (
									<option key={item.name} value={item.name}>
										{item.property_name}
									</option>
								))}
							</select>
						</Field>
						<Field label="Found location">
							<input
								aria-label="Found location"
								className={fieldClass}
								value={form.foundLocation}
								onChange={(event) => update('foundLocation', event.target.value)}
							/>
						</Field>
						<Field label="Found on">
							<input
								aria-label="Found on"
								className={fieldClass}
								type="datetime-local"
								value={form.foundOn}
								onChange={(event) => update('foundOn', event.target.value)}
							/>
						</Field>
						<Field label="Custodian">
							<input
								aria-label="Custodian"
								className={fieldClass}
								readOnly
								value={user || ''}
							/>
						</Field>
						<Field label="Image">
							<input
								aria-label="Image"
								className="block w-full text-sm text-slate-600"
								type="file"
								accept="image/*"
								onChange={(event) => setImage(event.target.files?.[0] || null)}
							/>
						</Field>
						<PrimaryButton disabled={busy}>
							{busy ? 'Saving…' : 'Register item'}
						</PrimaryButton>
					</form>
				</section>
				<section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
					<h2 className="text-sm font-semibold text-slate-800">Found items</h2>
					{loading && <p className="mt-3 text-sm text-slate-400">Loading…</p>}
					{!loading && rows && rows.length === 0 && (
						<p className="mt-3 text-sm text-slate-400">No found items are registered.</p>
					)}
					{!loading && rows && rows.length > 0 && (
						<ul className="mt-3 divide-y divide-slate-100">
							{rows.map((row) => (
								<li key={row.name}>
									<button
										type="button"
										onClick={() => setSelected(row.name)}
										className="flex w-full items-center justify-between gap-3 py-3 text-left"
									>
										<span className="min-w-0">
											<span className="block truncate text-sm font-medium text-slate-800">
												{row.name}
											</span>
											<span className="block truncate text-xs text-slate-400">
												{row.property_name} / {row.found_location}
											</span>
										</span>
										<StatusPill status={row.status} />
									</button>
								</li>
							))}
						</ul>
					)}
					{current && (
						<dl className="mt-4 grid gap-2 border-t border-slate-100 pt-4 text-sm">
							<div>
								<dt className="text-xs text-slate-400">Reference</dt>
								<dd className="font-medium text-slate-800">{current.name}</dd>
							</div>
							<div>
								<dt className="text-xs text-slate-400">Status</dt>
								<dd className="text-slate-800">{current.status}</dd>
							</div>
							<div>
								<dt className="text-xs text-slate-400">Description</dt>
								<dd className="text-slate-800">{current.description}</dd>
							</div>
							<div>
								<dt className="text-xs text-slate-400">Found</dt>
								<dd className="text-slate-800">
									{current.found_on} at {current.found_location}
								</dd>
							</div>
						</dl>
					)}
				</section>
			</div>
		</div>
	)
}
