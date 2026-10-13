import { useEffect, useState } from 'react'
import { listDocs } from '../api.js'
import { friendlyName } from '../format.js'
import { Icon } from '../icons.jsx'
import { StatusPill } from '../ui.jsx'

export function StaffHome ({ user, onLogout }) {
	const [rows, setRows] = useState(null)
	const [error, setError] = useState('')

	useEffect(() => {
		let active = true
		listDocs('Accommodation Allocation', {
			fields: ['name', 'status', 'bed', 'room', 'check_in_date', 'check_out_date'],
			limit: 20,
			orderBy: 'modified desc',
		})
			.then((next) => {
				if (active) {
					setRows(next || [])
					setError('')
				}
			})
			.catch((err) => {
				if (active) {
					setError(err.message)
				}
			})
		return () => {
			active = false
		}
	}, [])

	const current = (rows || []).find((row) => row.status === 'Checked In')

	return (
		<div className="min-h-screen bg-[#F4F7FB] text-slate-800">
			<header className="flex items-center justify-between bg-[#0B1220] px-4 py-4 text-white">
				<div>
					<div className="text-sm font-semibold">HotLync</div>
					<div className="text-xs text-slate-400">{friendlyName(user)}</div>
				</div>
				<button type="button" onClick={onLogout} className="text-sm text-slate-300">
					Sign out
				</button>
			</header>
			<main className="mx-auto max-w-lg space-y-4 px-4 py-6">
				<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
					<div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
						<Icon name="bed" className="h-4 w-4 text-blue-600" />
						My stay
					</div>
					{error && <p className="text-sm text-rose-700">{error}</p>}
					{!error && !rows && <p className="text-sm text-slate-400">Loading your stay…</p>}
					{current && <Stay row={current} />}
					{rows && !current && !error && (
						<p className="text-sm text-slate-500">You have no checked-in stay.</p>
					)}
				</section>
				<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
					<h2 className="mb-3 text-sm font-semibold text-slate-900">Previous stays</h2>
					{rows && rows.filter((row) => row.name !== current?.name).map((row) => (
						<div key={row.name} className="border-t border-slate-100 py-3 first:border-t-0 first:pt-0">
							<Stay row={row} />
						</div>
					))}
					{rows && rows.length === 0 && (
						<p className="text-sm text-slate-500">No stays yet.</p>
					)}
				</section>
			</main>
		</div>
	)
}

function Stay ({ row }) {
	return (
		<div className="space-y-1 text-sm">
			<div className="flex items-center justify-between gap-2">
				<span className="font-medium text-slate-900">{row.bed}</span>
				<StatusPill value={row.status} />
			</div>
			<p className="text-slate-500">{row.room}</p>
			<p className="text-xs text-slate-400">
				{row.check_in_date || 'Not checked in'}
				{row.check_out_date ? ` to ${row.check_out_date}` : ''}
			</p>
		</div>
	)
}
