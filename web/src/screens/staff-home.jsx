import { useEffect, useState } from 'react'
import { call } from '../api.js'
import { friendlyName } from '../format.js'
import { Icon } from '../icons.jsx'
import { MaintenanceDesk } from './maintenance.jsx'
import { RequestDesk } from './requests.jsx'
import { NoticeList } from '../notices.jsx'
import { StatusPill } from '../ui.jsx'

export function StaffHome ({ user, onLogout }) {
	const [stay, setStay] = useState(null)
	const [error, setError] = useState('')
	const [loading, setLoading] = useState(true)
	const [view, setView] = useState('stay')

	useEffect(() => {
		let active = true
		setLoading(true)
		setStay(null)
		setError('')
		call('hotlync.api.get_my_stay')
			.then((next) => {
				if (active) {
					setStay(next)
				}
			})
			.catch((err) => {
				if (active) {
					setError(err.message || 'Your stay could not be loaded.')
				}
			})
			.finally(() => {
				if (active) {
					setLoading(false)
				}
			})
		return () => {
			active = false
		}
	}, [user])

	function refreshStay () {
		setLoading(true)
		setStay(null)
		setError('')
		call('hotlync.api.get_my_stay')
			.then((next) => {
				setStay(next)
			})
			.catch((err) => {
				setError(err.message || 'Your stay could not be loaded.')
			})
			.finally(() => {
				setLoading(false)
			})
	}

	const current = stay?.current
	const previous = stay?.previous || []

	return (
		<div className="min-h-screen bg-[#F4F7FB] text-slate-800">
			<header className="bg-[#0B1220] px-4 py-4 text-white">
				<div>
					<div className="text-sm font-semibold">HotLync</div>
					<div className="text-xs text-slate-400">{friendlyName(user)}</div>
				</div>
				<nav className="mt-3 flex flex-wrap gap-2">
					{[
						['stay', 'My stay', () => setView('stay')],
						['requests', 'Requests', () => setView('requests')],
						['maintenance', 'Maintenance', () => setView('maintenance')],
					].map(([id, label, onClick]) => (
						<button
							key={id}
							type="button"
							onClick={onClick}
							className={`min-h-11 rounded-lg px-3 text-sm ${
								view === id ? 'bg-white/10 text-white' : 'text-slate-300'
							}`}
						>
							{label}
						</button>
					))}
					<button
						type="button"
						onClick={refreshStay}
						className="min-h-11 rounded-lg px-3 text-sm text-slate-300"
					>
						Refresh
					</button>
					<button
						type="button"
						onClick={onLogout}
						className="min-h-11 rounded-lg px-3 text-sm text-slate-300"
					>
						Sign out
					</button>
				</nav>
			</header>
			<main className={`mx-auto space-y-4 px-4 py-6 ${view === 'stay' ? 'max-w-lg' : 'max-w-5xl'}`}>
				{view === 'requests' && <RequestDesk mode="staff" />}
				{view === 'maintenance' && <MaintenanceDesk mode="staff" />}
				{view === 'stay' && (
				<>
				<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
					<div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
						<Icon name="bed" className="h-4 w-4 text-blue-600" />
						My stay
					</div>
					{loading && (
						<p className="text-sm text-slate-400">Loading your stay…</p>
					)}
					{error && <p className="text-sm text-rose-700">{error}</p>}
					{!loading && !error && stay && !stay.mapped && (
						<p className="text-sm text-slate-500">
							This login is not linked to an employee.
						</p>
					)}
					{!loading && !error && current && <Stay row={current} />}
					{!loading && !error && stay?.mapped && !current && (
						<p className="text-sm text-slate-500">You have no checked-in stay.</p>
					)}
				</section>
				<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
					<h2 className="mb-3 text-sm font-semibold text-slate-900">Notices</h2>
					<NoticeList />
				</section>
				{stay?.mapped && (
					<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
						<h2 className="mb-3 text-sm font-semibold text-slate-900">Previous stays</h2>
						{previous.map((row) => (
							<div
								key={row.name}
								className="border-t border-slate-100 py-3 first:border-t-0 first:pt-0"
							>
								<Stay row={row} />
							</div>
						))}
						{previous.length === 0 && (
							<p className="text-sm text-slate-500">No earlier stays.</p>
						)}
					</section>
				)}
				</>
				)}
			</main>
		</div>
	)
}

function Stay ({ row }) {
	const place = [
		row.property_name,
		row.building_name,
		row.floor_name,
		row.room_number ? `Room ${row.room_number}` : '',
		row.bed_number ? `Bed ${row.bed_number}` : '',
	].filter(Boolean).join(' · ')

	return (
		<div className="space-y-1 text-sm">
			<div className="flex items-center justify-between gap-2">
				<span className="font-medium text-slate-900">
					{row.bed_number ? `Bed ${row.bed_number}` : 'Stay'}
				</span>
				<StatusPill status={row.status} />
			</div>
			{place && <p className="text-slate-500">{place}</p>}
			<p className="text-xs text-slate-400">
				{row.check_in_date || 'Not checked in'}
				{row.check_out_date ? ` to ${row.check_out_date}` : ''}
			</p>
		</div>
	)
}
