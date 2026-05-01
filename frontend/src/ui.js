export function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on') && typeof v === 'function') e[k] = v
    else if (k === 'class') e.className = v
    else if (k === 'html') e.innerHTML = v
    else e.setAttribute(k, v)
  }
  children.flat().forEach(c => {
    if (c == null) return
    e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c)
  })
  return e
}

export function mount(selector, node) {
  const root = typeof selector === 'string' ? document.querySelector(selector) : selector
  if (!root) return
  root.innerHTML = ''
  if (node) root.appendChild(node)
}

export function toast(msg, type = 'info') {
  const t = el('div', { class: `toast toast-${type}` }, msg)
  document.body.appendChild(t)
  setTimeout(() => t.classList.add('show'), 10)
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300) }, 3500)
}

export function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function formatSize(b) {
  if (b < 1024) return b + ' Б'
  if (b < 1048576) return (b / 1024).toFixed(1) + ' КБ'
  return (b / 1048576).toFixed(1) + ' МБ'
}

export function statusLabel(s) {
  const map = {
    pending_ai: ['⏳ Анализ AI', 'status-pending'],
    ai_done: ['✅ AI готов', 'status-ai'],
    pending_lawyer: ['📋 Ожидает юриста', 'status-waiting'],
    lawyer_review: ['🔍 На проверке', 'status-review'],
    lawyer_done: ['⚖ Проверен', 'status-done'],
    closed: ['🔒 Закрыт', 'status-closed'],
  }
  return map[s] || [s, '']
}

export function riskBadge(level) {
  const map = { high: ['🔴 Высокий', 'risk-high'], medium: ['🟡 Средний', 'risk-medium'], low: ['🟢 Низкий', 'risk-low'] }
  return map[level] || [level, '']
}

export function spinner() {
  return el('div', { class: 'spinner-wrap' }, el('div', { class: 'spinner' }))
}

export function card(title, content) {
  return el('div', { class: 'card' },
    title ? el('div', { class: 'card-label' }, title) : null,
    typeof content === 'string' ? el('div', { class: 'card-body' }, content) : content
  )
}
