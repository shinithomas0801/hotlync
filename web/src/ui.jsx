export function Field ({ label, children }) {
	return (
		<label className="block text-sm">
			<span className="mb-1 block text-xs font-medium text-slate-500">
				{label}
			</span>
			{children}
		</label>
	)
}

export const inputClass =
	'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-500'

export function Notice ({ error, message }) {
	if (!error && !message) {
		return null
	}
	return (
		<p
			className={
				error
					? 'rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700'
					: 'rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700'
			}
		>
			{error || message}
		</p>
	)
}

export function PrimaryButton ({ children, disabled, type = 'submit' }) {
	return (
		<button
			type={type}
			disabled={disabled}
			className="rounded-lg bg-[#2563EB] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
		>
			{children}
		</button>
	)
}

export function Panel ({ title, action, children, className = '' }) {
	return (
		<section
			className={`rounded-2xl border border-slate-200/80 bg-white shadow-sm ${className}`}
		>
			{(title || action) && (
				<div className="flex items-center justify-between px-5 pt-4">
					{title && (
						<h2 className="text-sm font-semibold text-slate-800">{title}</h2>
					)}
					{action}
				</div>
			)}
			<div className={title || action ? 'p-5 pt-3' : 'p-5'}>{children}</div>
		</section>
	)
}

export function StatusPill ({ status }) {
	const tone = {
		Occupied: 'bg-emerald-50 text-emerald-600',
		Available: 'bg-sky-50 text-sky-600',
		Maintenance: 'bg-rose-50 text-rose-500',
		'Partially Occupied': 'bg-amber-50 text-amber-600',
		Partial: 'bg-amber-50 text-amber-600',
		'Checked In': 'bg-emerald-50 text-emerald-600',
		Completed: 'bg-slate-100 text-slate-600',
		Transferred: 'bg-violet-50 text-violet-600',
		Draft: 'bg-amber-50 text-amber-700',
	}
	return (
		<span
			className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${tone[status] || 'bg-slate-100 text-slate-600'}`}
		>
			{status}
		</span>
	)
}

export function PageIntro ({ icon, title, subtitle, crumbs }) {
	return (
		<div className="mb-4 flex flex-wrap items-start justify-between gap-3">
			<div className="flex items-start gap-3">
				{icon && (
					<div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-[#2563EB]">
						{icon}
					</div>
				)}
				<div>
					<h1 className="text-xl font-semibold text-slate-900">{title}</h1>
					{subtitle && (
						<p className="text-sm text-slate-500">{subtitle}</p>
					)}
				</div>
			</div>
			{crumbs && (
				<div className="text-xs text-slate-400">
					{crumbs.map((crumb, index) => (
						<span key={crumb}>
							{index > 0 && <span className="px-1.5">›</span>}
							<span className={index === crumbs.length - 1 ? 'text-slate-600' : ''}>
								{crumb}
							</span>
						</span>
					))}
				</div>
			)}
		</div>
	)
}
