const BASE = '/api'

async function req(method, path, body = null, isForm = false) {
  const opts = {
    method,
    credentials: 'include',
    headers: isForm ? {} : { 'Content-Type': 'application/json' }
  }
  if (body) opts.body = isForm ? body : JSON.stringify(body)

  const res = await fetch(BASE + path, opts)

  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = e.detail || JSON.stringify(e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  // Auth
  register: (d) => req('POST', '/auth/register', d),
  login: (d) => req('POST', '/auth/login', d),
  logout: () => req('POST', '/auth/logout'),
  me: () => req('GET', '/auth/me'),

  // User requests
  uploadDocument: (file, comment) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('comment', comment || '')
    return req('POST', '/requests', fd, true)
  },
  myRequests: () => req('GET', '/requests'),
  getRequest: (uuid) => req('GET', `/requests/${uuid}`),
  sendToLawyer: (uuid) => req('POST', `/requests/${uuid}/send-to-lawyer`),

  // Lawyer
  lawyerRequests: (status = 'all') => req('GET', `/lawyer/requests?status=${status}`),
  takeRequest: (uuid) => req('POST', `/lawyer/requests/${uuid}/take`),
  submitReview: (uuid, data) => req('POST', `/lawyer/requests/${uuid}/submit`, data),

  // Feedback
  submitFeedback: (type, data) => req('POST', `/feedback/${type}`, data),
  feedbackStats: () => req('GET', '/feedback/stats'),

  // Admin
  adminUsers: () => req('GET', '/admin/users'),
  updateRole: (id, role) => req('PATCH', `/admin/users/${id}/role`, { role }),
  toggleUser: (id) => req('PATCH', `/admin/users/${id}/toggle`),
  adminStats: () => req('GET', '/admin/stats'),
}
