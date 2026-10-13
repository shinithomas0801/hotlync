import { useEffect, useState } from 'react'
import { call } from './api.js'

export function NoticeList () {
	const [rows, setRows] = useState(null)
	const [error, setError] = useState('')

	useEffect(() => {
		let active = true
		call('hotlync.api.get_notices')
			.then((next) => {
				if (active) {
					setRows(next || [])
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

	if (error) {
		return <p className="text-sm text-rose-700">{error}</p>
	}
	if (!rows) {
		return <p className="py-6 text-center text-sm text-slate-400">Loading notices…</p>
	}
	if (rows.length === 0) {
		return <p className="py-6 text-center text-sm text-slate-400">No notifications yet.</p>
	}
	return (
		<div className="max-h-72 space-y-2 overflow-y-auto">
			{rows.map((row) => (
				<div key={row.name} className="border-t border-slate-100 py-2 first:border-t-0 first:pt-0">
					<p
						className={`break-words text-sm ${
							row.status === 'Failed' ? 'text-rose-700' : 'text-slate-700'
						}`}
					>
						{row.subject}
					</p>
					{row.status === 'Failed' && row.detail && (
						<p className="break-words text-xs text-rose-600">{row.detail}</p>
					)}
					<p className="break-all text-xs text-slate-400">{row.creation}</p>
				</div>
			))}
		</div>
	)
}
