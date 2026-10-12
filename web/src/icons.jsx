export function Icon ({ name, className = 'h-4 w-4' }) {
	const body = paths[name]
	if (!body) {
		return null
	}
	return (
		<svg
			viewBox="0 0 24 24"
			className={className}
			fill="none"
			stroke="currentColor"
			strokeWidth="1.8"
			strokeLinecap="round"
			strokeLinejoin="round"
			aria-hidden="true"
		>
			{body}
		</svg>
	)
}

const paths = {
	home: (
		<>
			<path d="M4 10.5 12 4l8 6.5" />
			<path d="M6 10v9h12v-9" />
		</>
	),
	building: (
		<>
			<path d="M4 20h16" />
			<path d="M6 20V6h8v14" />
			<path d="M14 10h4v10" />
			<path d="M8 9h2M8 12h2M8 15h2" />
		</>
	),
	arrows: (
		<>
			<path d="M7 7h11l-3-3" />
			<path d="M17 17H6l3 3" />
		</>
	),
	door: (
		<>
			<path d="M6 4h9a2 2 0 0 1 2 2v14H6z" />
			<path d="M10 12h.01" />
		</>
	),
	chart: (
		<>
			<path d="M4 19h16" />
			<path d="M7 16v-5" />
			<path d="M12 16V8" />
			<path d="M17 16v-3" />
		</>
	),
	users: (
		<>
			<path d="M16 20v-1a3 3 0 0 0-3-3H7a3 3 0 0 0-3 3v1" />
			<circle cx="10" cy="8" r="3" />
			<path d="M20 20v-1a3 3 0 0 0-2-2.8" />
			<path d="M16 5.1a3 3 0 0 1 0 5.8" />
		</>
	),
	wrench: (
		<>
			<path d="M14.5 6.5a4 4 0 0 0-5.6 5.6L4 17l3 3 4.9-4.9a4 4 0 0 0 5.6-5.6L15 12l-3-3z" />
		</>
	),
	calendar: (
		<>
			<path d="M5 6h14v14H5z" />
			<path d="M8 4v4M16 4v4M5 10h14" />
		</>
	),
	key: (
		<>
			<circle cx="8" cy="14" r="3" />
			<path d="M11 14h9l-2 2 2 2" />
		</>
	),
	box: (
		<>
			<path d="M3 8l9-4 9 4-9 4z" />
			<path d="M3 8v8l9 4 9-4V8" />
			<path d="M12 12v8" />
		</>
	),
	tag: (
		<>
			<path d="M4 12V5h7l8 8-7 7z" />
			<circle cx="8.5" cy="8.5" r="1" />
		</>
	),
	bus: (
		<>
			<path d="M5 6h14v10H5z" />
			<path d="M5 12h14" />
			<circle cx="8" cy="18" r="1.2" />
			<circle cx="16" cy="18" r="1.2" />
		</>
	),
	file: (
		<>
			<path d="M7 3h7l5 5v13H7z" />
			<path d="M14 3v5h5" />
		</>
	),
	chat: (
		<>
			<path d="M5 6h14v9H8l-3 3z" />
		</>
	),
	report: (
		<>
			<path d="M5 19V5h10l4 4v10z" />
			<path d="M8 13h8M8 16h5" />
		</>
	),
	settings: (
		<>
			<circle cx="12" cy="12" r="3" />
			<path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" />
		</>
	),
	chevron: <path d="m9 6 6 6-6 6" />,
	bell: (
		<>
			<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" />
			<path d="M10 19a2 2 0 0 0 4 0" />
		</>
	),
	help: (
		<>
			<circle cx="12" cy="12" r="8" />
			<path d="M9.5 9a2.5 2.5 0 1 1 3.2 2.4c-.7.3-1.2.8-1.2 1.6" />
			<path d="M12 17h.01" />
		</>
	),
	search: (
		<>
			<circle cx="11" cy="11" r="6" />
			<path d="m20 20-3.5-3.5" />
		</>
	),
	bed: (
		<>
			<path d="M4 18v-5a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v5" />
			<path d="M4 14h16M6 10V7h4v3" />
		</>
	),
	plus: (
		<>
			<path d="M12 5v14M5 12h14" />
		</>
	),
	eye: (
		<>
			<path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z" />
			<circle cx="12" cy="12" r="2.5" />
		</>
	),
	user: (
		<>
			<circle cx="12" cy="8" r="3" />
			<path d="M5 19a7 7 0 0 1 14 0" />
		</>
	),
	logout: (
		<>
			<path d="M10 7V5H5v14h5v-2" />
			<path d="M10 12h9M16 9l3 3-3 3" />
		</>
	),
}
