import { useState } from 'react'
import { login, logout } from './api.js'
import { Allocate, StayDesk, Transfer } from './screens/actions.jsx'
import { Accommodation } from './screens/accommodation.jsx'
import { Dashboard, Occupancy } from './screens/dashboard.jsx'
import { Administration, LaterModule, StaffList } from './screens/modules.jsx'
import { Shell } from './shell.jsx'
import { Icon } from './icons.jsx'
import { inputClass } from './ui.jsx'

export default function App () {
	const [user, setUser] = useState('')
	const [screen, setScreen] = useState('dashboard')
	const [query, setQuery] = useState('')
	const [preset, setPreset] = useState(null)
	const [version, setVersion] = useState(0)

	function open (next, nextPreset) {
		setScreen(next)
		setPreset(nextPreset || null)
	}

	function refresh () {
		setVersion((value) => value + 1)
	}

	async function handleLogout () {
		await logout()
		setUser('')
	}

	if (!user) {
		return <Login onSuccess={setUser} />
	}

	return (
		<Shell
			user={user}
			screen={screen}
			query={query}
			onQuery={setQuery}
			onNavigate={open}
			onLogout={handleLogout}
		>
			{screen === 'dashboard' && (
				<Dashboard user={user} version={version} onOpen={open} />
			)}
			{['buildings', 'rooms', 'beds'].includes(screen) && (
				<Accommodation
					view={screen}
					version={version}
					query={query}
					onQuery={setQuery}
					onOpen={open}
					onChanged={refresh}
				/>
			)}
			{screen === 'allocate' && <Allocate onDone={refresh} preset={preset} />}
			{screen === 'transfer' && <Transfer onDone={refresh} />}
			{screen === 'check' && <StayDesk onDone={refresh} />}
			{screen === 'occupancy' && <Occupancy version={version} />}
			{screen === 'reports' && <Occupancy version={version} />}
			{screen === 'staff' && <StaffList />}
			{screen === 'administration' && <Administration />}
			{['maintenance', 'facilities', 'keys', 'inventory', 'lost', 'transport', 'requests', 'communication'].includes(screen) && (
				<LaterModule id={screen} />
			)}
		</Shell>
	)
}

function Login ({ onSuccess }) {
	const [usr, setUsr] = useState('Administrator')
	const [pwd, setPwd] = useState('admin')
	const [error, setError] = useState('')
	const [busy, setBusy] = useState(false)

	async function handleSubmit (event) {
		event.preventDefault()
		setBusy(true)
		setError('')
		try {
			const session = await login(usr, pwd)
			onSuccess(session.user)
		} catch (err) {
			setError(err.message)
		} finally {
			setBusy(false)
		}
	}

	return (
		<div className="grid min-h-screen lg:grid-cols-[420px_1fr]">
			<div className="flex flex-col justify-between bg-[#0B1220] px-10 py-10 text-white">
				<div className="flex items-center gap-3">
					<div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#2563EB]">
						<Icon name="home" className="h-5 w-5" />
					</div>
					<div>
						<div className="text-lg font-semibold">HotLync</div>
						<div className="text-xs text-slate-400">Stay · Work · Connect</div>
					</div>
				</div>
				<div>
					<h1 className="text-3xl font-semibold leading-tight">
						Staff accommodation, in one desk.
					</h1>
					<p className="mt-3 max-w-sm text-sm text-slate-400">
						Rooms, beds, and stays are enforced in ERPNext. This desk shows the live property.
					</p>
				</div>
				<p className="text-xs text-slate-500">HotLync v1.0</p>
			</div>
			<div className="flex items-center justify-center bg-[#F4F7FB] px-6">
				<form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow-sm">
					<div>
						<h2 className="text-xl font-semibold text-slate-900">Sign in</h2>
						<p className="mt-1 text-sm text-slate-500">Use your ERPNext user.</p>
					</div>
					<label className="block text-sm">
						<span className="mb-1 block text-xs font-medium text-slate-500">User</span>
						<input className={inputClass} value={usr} onChange={(event) => setUsr(event.target.value)} required />
					</label>
					<label className="block text-sm">
						<span className="mb-1 block text-xs font-medium text-slate-500">Password</span>
						<input
							type="password"
							className={inputClass}
							value={pwd}
							onChange={(event) => setPwd(event.target.value)}
							required
						/>
					</label>
					{error && <p className="text-sm text-rose-700">{error}</p>}
					<button
						type="submit"
						disabled={busy}
						className="w-full rounded-lg bg-[#2563EB] py-2.5 text-sm font-medium text-white disabled:opacity-50"
					>
						Sign in
					</button>
					<p className="text-xs leading-5 text-slate-400">
						Administrator / admin
						<br />
						admin@hotlync.local / Admin@123
						<br />
						staff@hotlync.local / Staff@123
					</p>
				</form>
			</div>
		</div>
	)
}
