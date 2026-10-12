import { useEffect, useState } from 'react'
import { friendlyName, initials, roleLabel } from './format.js'
import { Icon } from './icons.jsx'

export const NAV = [
	{ id: 'dashboard', label: 'Dashboard', icon: 'home' },
	{
		id: 'accommodation',
		label: 'Accommodation',
		icon: 'building',
		children: [
			{ id: 'buildings', label: 'Buildings & Villas' },
			{ id: 'rooms', label: 'Rooms' },
			{ id: 'beds', label: 'Beds' },
			{ id: 'allocate', label: 'Staff Allocation' },
		],
	},
	{ id: 'transfer', label: 'Transfers', icon: 'arrows' },
	{ id: 'check', label: 'Check-in / Check-out', icon: 'door' },
	{ id: 'occupancy', label: 'Occupancy', icon: 'chart' },
	{ id: 'staff', label: 'Staff', icon: 'users' },
	{ id: 'maintenance', label: 'Maintenance', icon: 'wrench' },
	{ id: 'facilities', label: 'Facilities Booking', icon: 'calendar' },
	{ id: 'keys', label: 'Keys & Access', icon: 'key' },
	{ id: 'inventory', label: 'Inventory', icon: 'box' },
	{ id: 'lost', label: 'Lost & Found', icon: 'tag' },
	{ id: 'transport', label: 'Transport', icon: 'bus' },
	{ id: 'requests', label: 'Requests & Forms', icon: 'file' },
	{ id: 'communication', label: 'Communication', icon: 'chat' },
	{ id: 'reports', label: 'Reports & Analytics', icon: 'report' },
	{ id: 'administration', label: 'Administration', icon: 'settings' },
]

export function Shell ({
	user,
	screen,
	query,
	onQuery,
	onNavigate,
	onLogout,
	children,
}) {
	const [openGroup, setOpenGroup] = useState('accommodation')
	const [menuOpen, setMenuOpen] = useState(false)
	const [helpOpen, setHelpOpen] = useState(false)
	const name = friendlyName(user)
	const role = roleLabel(user)

	useEffect(() => {
		const parent = NAV.find((item) =>
			item.children?.some((child) => child.id === screen),
		)
		if (parent) {
			setOpenGroup(parent.id)
		}
	}, [screen])

	return (
		<div className="flex h-screen overflow-hidden bg-[#F4F7FB] text-slate-800">
			<aside className="flex w-[248px] shrink-0 flex-col bg-[#0B1220] text-slate-300">
				<div className="flex items-center gap-3 px-5 py-5">
					<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#2563EB] text-white">
						<Icon name="home" className="h-5 w-5" />
					</div>
					<div>
						<div className="text-[15px] font-semibold text-white">HotLync</div>
						<div className="text-[11px] text-slate-400">
							Stay · Work · Connect
						</div>
					</div>
				</div>
				<nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
					{NAV.map((item) => {
						const childActive = item.children?.some((child) => child.id === screen)
						const active = item.id === screen || childActive
						const expanded = openGroup === item.id && item.children
						return (
							<div key={item.id}>
								<button
									type="button"
									onClick={() => {
										if (item.children) {
											setOpenGroup(expanded ? '' : item.id)
											onNavigate(item.children[0].id)
											return
										}
										onNavigate(item.id)
									}}
									className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[13px] ${
										active
											? 'bg-[#2563EB] font-medium text-white'
											: 'text-slate-300 hover:bg-white/5 hover:text-white'
									}`}
								>
									<Icon name={item.icon} className="h-4 w-4 shrink-0" />
									<span className="flex-1">{item.label}</span>
									{item.children && (
										<Icon
											name="chevron"
											className={`h-3.5 w-3.5 ${expanded ? 'rotate-90' : ''}`}
										/>
									)}
								</button>
								{expanded && (
									<div className="mt-1 space-y-0.5 pl-4">
										{item.children.map((child) => (
											<button
												key={child.id}
												type="button"
												onClick={() => onNavigate(child.id)}
												className={`block w-full rounded-lg px-3 py-1.5 text-left text-[13px] ${
													child.id === screen
														? 'bg-white/10 font-medium text-white'
														: 'text-slate-400 hover:text-white'
												}`}
											>
												{child.label}
											</button>
										))}
									</div>
								)}
							</div>
						)
					})}
				</nav>
				<div className="m-3 rounded-xl bg-white/5 p-3">
					<div className="flex items-center gap-2">
						<div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-white">
							<Icon name="help" className="h-4 w-4" />
						</div>
						<div>
							<div className="text-sm font-medium text-white">Need help?</div>
							<div className="text-xs text-slate-400">Contact support</div>
						</div>
					</div>
				</div>
			</aside>
			<div className="flex min-w-0 flex-1 flex-col">
				<header className="relative flex h-16 items-center gap-4 border-b border-slate-200/80 bg-white px-6">
					<label className="relative flex h-10 max-w-xl flex-1 items-center gap-2 rounded-full border border-slate-200 bg-[#F4F7FB] px-4">
						<Icon name="search" className="h-4 w-4 text-slate-400" />
						<input
							value={query}
							onChange={(event) => {
								onQuery(event.target.value)
								onNavigate('rooms')
							}}
							placeholder="Search rooms, staff, buildings, etc..."
							className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
						/>
					</label>
					<div className="ml-auto flex items-center gap-3">
						<button
							type="button"
							className="relative flex h-9 w-9 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100"
							onClick={() => setHelpOpen(false)}
							aria-label="Notifications"
						>
							<Icon name="bell" className="h-5 w-5" />
							<span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-rose-500" />
						</button>
						<button
							type="button"
							className="flex h-9 w-9 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100"
							onClick={() => setHelpOpen((open) => !open)}
							aria-label="Help"
						>
							<Icon name="help" className="h-5 w-5" />
						</button>
						<button
							type="button"
							onClick={() => setMenuOpen((open) => !open)}
							className="flex items-center gap-3 rounded-full py-1 pr-1 pl-2 hover:bg-slate-50"
						>
							<span className="text-right leading-tight">
								<span className="block text-sm font-semibold text-slate-800">
									{name}
								</span>
								<span className="block text-[11px] text-slate-400">{role}</span>
							</span>
							<span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-xs font-semibold text-white">
								{initials(name)}
							</span>
						</button>
					</div>
					{menuOpen && (
						<div className="absolute top-14 right-6 z-20 w-44 rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
							<button
								type="button"
								onClick={onLogout}
								className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
							>
								<Icon name="logout" className="h-4 w-4" />
								Sign out
							</button>
						</div>
					)}
					{helpOpen && (
						<div className="absolute top-14 right-20 z-20 w-64 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600 shadow-lg">
							Bed availability is decided in ERPNext. This screen sends the request and shows the result.
						</div>
					)}
				</header>
				<main className="flex-1 overflow-y-auto px-6 py-5">{children}</main>
			</div>
		</div>
	)
}
