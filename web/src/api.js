const API = 'http://127.0.0.1:8000'

let csrfToken = ''

export function setCsrfToken (token) {
	csrfToken = token || ''
}

export async function login (usr, pwd) {
	const response = await fetch(`${API}/api/method/login`, {
		method: 'POST',
		credentials: 'include',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
		},
		body: JSON.stringify({ usr, pwd }),
	})
	const data = await response.json().catch(() => ({}))
	if (!response.ok) {
		throw new Error(readError(data))
	}
	const sessionResponse = await fetch(
		`${API}/api/method/hotlync.api.get_session`,
		{
			method: 'GET',
			credentials: 'include',
			headers: { Accept: 'application/json' },
		},
	)
	const sessionData = await sessionResponse.json().catch(() => ({}))
	if (!sessionResponse.ok) {
		throw new Error(readError(sessionData))
	}
	setCsrfToken(sessionData.message.csrf_token)
	return sessionData.message
}

export async function call (method, args) {
	const response = await fetch(`${API}/api/method/${method}`, {
		method: 'POST',
		credentials: 'include',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(csrfToken ? { 'X-Frappe-CSRF-Token': csrfToken } : {}),
		},
		body: JSON.stringify(args || {}),
	})
	const data = await response.json().catch(() => ({}))
	if (!response.ok) {
		throw new Error(readError(data))
	}
	return data.message
}

export async function uploadTicketPhoto (docname, file) {
	const body = new FormData()
	body.append('file', file)
	body.append('doctype', 'Maintenance Ticket')
	body.append('docname', docname)
	body.append('fieldname', 'photo')
	body.append('is_private', '1')
	body.append('method', 'hotlync.api.attach_ticket_photo')
	const response = await fetch(`${API}/api/method/upload_file`, {
		method: 'POST',
		credentials: 'include',
		headers: csrfToken ? { 'X-Frappe-CSRF-Token': csrfToken } : {},
		body,
	})
	const data = await response.json().catch(() => ({}))
	if (!response.ok) {
		throw new Error(readError(data))
	}
	return data.message
}

export async function logout () {
	await fetch(`${API}/api/method/logout`, {
		method: 'POST',
		credentials: 'include',
		headers: {
			Accept: 'application/json',
			...(csrfToken ? { 'X-Frappe-CSRF-Token': csrfToken } : {}),
		},
	}).catch(() => {})
	setCsrfToken('')
}

export async function listDocs (doctype, params) {
	const query = new URLSearchParams()
	if (params?.fields) {
		query.set('fields', JSON.stringify(params.fields))
	}
	if (params?.limit) {
		query.set('limit_page_length', String(params.limit))
	}
	if (params?.orderBy) {
		query.set('order_by', params.orderBy)
	}
	const response = await fetch(
		`${API}/api/resource/${encodeURIComponent(doctype)}?${query}`,
		{
			method: 'GET',
			credentials: 'include',
			headers: { Accept: 'application/json' },
		},
	)
	const data = await response.json().catch(() => ({}))
	if (!response.ok) {
		throw new Error(readError(data))
	}
	return data.data
}

export async function createDoc (doctype, doc) {
	const response = await fetch(
		`${API}/api/resource/${encodeURIComponent(doctype)}`,
		{
			method: 'POST',
			credentials: 'include',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				...(csrfToken ? { 'X-Frappe-CSRF-Token': csrfToken } : {}),
			},
			body: JSON.stringify(doc),
		},
	)
	const data = await response.json().catch(() => ({}))
	if (!response.ok) {
		throw new Error(readError(data))
	}
	return data.data
}

function readError (data) {
	try {
		const messages = JSON.parse(data._server_messages || '[]')
		const first = JSON.parse(messages[0] || '{}')
		if (first.message) {
			return String(first.message).replace(/<[^>]*>/g, '')
		}
	} catch {
		/* use the exception text */
	}
	const raw = data.exception || data.message || 'Request failed'
	const text = String(raw).replace(/<[^>]*>/g, '')
	const split = text.split(': ')
	return split[split.length - 1] || text
}
