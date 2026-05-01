import { el, toast, formatDate, formatSize, statusLabel, spinner } from '../ui.js'
import { renderLayout } from '../components/layout.js'
import { api } from '../api/client.js'
import { navigate } from '../router.js'

const NAV = [
  { path: '/dashboard', icon: '📤', label: 'Загрузить документ' },
  { path: '/my-requests', icon: '📋', label: 'Мои заявки' },
]

export async function renderDashboard() {
  let selectedFile = null

  const fileInput = el('input', { type: 'file', accept: '.pdf,.docx', style: 'display:none' })
  fileInput.onchange = (e) => {
    selectedFile = e.target.files[0]
    updateFileInfo()
  }

  const dropZone = el('div', { class: 'drop-zone', onclick: () => fileInput.click() })
  dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('drag-over') }
  dropZone.ondragleave = () => dropZone.classList.remove('drag-over')
  dropZone.ondrop = (e) => {
    e.preventDefault(); dropZone.classList.remove('drag-over')
    const f = e.dataTransfer.files[0]; if (f) { selectedFile = f; updateFileInfo() }
  }

  function updateFileInfo() {
    dropZone.innerHTML = ''
    if (selectedFile) {
      dropZone.appendChild(el('div', { class: 'file-preview' },
        el('div', { class: 'file-icon' }, selectedFile.name.endsWith('.pdf') ? '📕' : '📘'),
        el('div', {},
          el('div', { class: 'file-name' }, selectedFile.name),
          el('div', { class: 'file-meta' }, formatSize(selectedFile.size))
        ),
        el('button', { class: 'btn-ghost', onclick: (e) => { e.stopPropagation(); selectedFile = null; initDrop() } }, '✕')
      ))
    } else {
      initDrop()
    }
  }

  function initDrop() {
    dropZone.innerHTML = ''
    dropZone.appendChild(el('div', { class: 'drop-inner' },
      el('div', { class: 'drop-icon' }, '📄'),
      el('div', { class: 'drop-title' }, 'Перетащите файл или нажмите'),
      el('div', { class: 'drop-sub' }, 'PDF или DOCX, до 15 МБ'),
      el('div', { class: 'drop-badges' },
        el('span', { class: 'badge' }, 'PDF'),
        el('span', { class: 'badge' }, 'DOCX')
      )
    ))
  }
  initDrop()

  const commentEl = el('textarea', { class: 'textarea', placeholder: 'Комментарий к заявке (необязательно)...' })

  const submitBtn = el('button', { class: 'btn-primary', onclick: async () => {
    if (!selectedFile) { toast('Выберите файл', 'error'); return }
    submitBtn.disabled = true; submitBtn.textContent = '⏳ Загружаем...'
    try {
      const res = await api.uploadDocument(selectedFile, commentEl.value)
      toast('Документ загружен! Анализ запущен.', 'success')
      selectedFile = null; initDrop(); commentEl.value = ''
      setTimeout(() => navigate('/my-requests'), 1500)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      submitBtn.disabled = false; submitBtn.textContent = 'Отправить на анализ →'
    }
  }}, 'Отправить на анализ →')

  const content = el('div', { class: 'page' },
    el('div', { class: 'page-header' },
      el('h1', { class: 'page-title' }, 'Загрузить документ'),
      el('p', { class: 'page-sub' }, 'AI проанализирует договор и выделит ключевые условия и риски')
    ),
    el('div', { class: 'upload-card' },
      fileInput,
      dropZone,
      el('div', { class: 'field', style: 'margin-top:16px' },
        el('label', {}, 'Комментарий'),
        commentEl
      ),
      el('div', { style: 'margin-top:16px' }, submitBtn)
    )
  )

  renderLayout('/dashboard', NAV, content)
}

export async function renderMyRequests() {
  const wrap = el('div', { class: 'page' },
    el('div', { class: 'page-header' },
      el('h1', { class: 'page-title' }, 'Мои заявки'),
      el('p', { class: 'page-sub' }, 'История загруженных документов и их статус')
    ),
    spinner()
  )
  renderLayout('/my-requests', NAV, wrap)

  try {
    const requests = await api.myRequests()
    const tbody = wrap.querySelector('.spinner-wrap')

    if (!requests.length) {
      tbody.replaceWith(el('div', { class: 'empty-state' }, '📄 Заявок пока нет. Загрузите первый документ!'))
      return
    }

    tbody.replaceWith(el('div', { class: 'requests-list' },
      ...requests.map(r => {
        const [sLabel, sCls] = statusLabel(r.status)
        return el('div', { class: 'request-card', onclick: () => navigate(`/request/${r.uuid}`) },
          el('div', { class: 'rc-header' },
            el('div', { class: 'rc-filename' }, r.original_filename),
            el('span', { class: `status-badge ${sCls}` }, sLabel)
          ),
          el('div', { class: 'rc-meta' },
            el('span', {}, '📅 ' + formatDate(r.created_at)),
            el('span', {}, '💾 ' + formatSize(r.file_size)),
            r.user_comment ? el('span', {}, '💬 ' + r.user_comment) : null
          )
        )
      })
    ))
  } catch (err) {
    toast(err.message, 'error')
  }
}

export async function renderRequestDetail({ uuid }) {
  const wrap = el('div', { class: 'page' }, spinner())
  renderLayout('/my-requests', NAV, wrap)

  try {
    const r = await api.getRequest(uuid)
    const [sLabel, sCls] = statusLabel(r.status)
    const content = el('div', { class: 'page' },
      el('div', { class: 'page-header' },
        el('button', { class: 'btn-back', onclick: () => navigate('/my-requests') }, '← Назад'),
        el('h1', { class: 'page-title' }, r.original_filename),
        el('span', { class: `status-badge ${sCls}` }, sLabel)
      ),
      // AI Report
      r.ai_report && !r.ai_report.error ? renderAIReport(r) : null,
      r.ai_report?.error ? el('div', { class: 'error-box' }, '⚠ AI ошибка: ' + r.ai_report.error) : null,
      // Send to lawyer button
      r.status === 'ai_done' ? el('div', { style: 'margin-top:20px' },
        el('button', { class: 'btn-accent', onclick: async () => {
          try { await api.sendToLawyer(uuid); toast('Отправлено юристу!', 'success'); navigate('/my-requests') }
          catch (e) { toast(e.message, 'error') }
        }}, '⚖ Отправить на проверку юристу')
      ) : null,
      // Lawyer report
      r.lawyer_report ? renderLawyerReport(r) : null
    )
    wrap.innerHTML = ''; wrap.appendChild(content)
  } catch (err) {
    toast(err.message, 'error')
  }
}

function renderAIReport(r) {
  const report = r.ai_report
  return el('div', { class: 'report-section' },
    el('h2', { class: 'section-title' }, '🤖 Анализ AI'),
    el('div', { class: 'report-grid' },
      reportCard('Тип документа', report.document_type || '—'),
      reportCard('Стороны', (report.parties || []).join(', ') || '—'),
      el('div', { class: 'report-card full' },
        el('div', { class: 'card-label' }, 'Краткое описание'),
        el('p', {}, report.summary || '—')
      ),
      el('div', { class: 'report-card full' },
        el('div', { class: 'card-label' }, '✦ Простым языком'),
        el('p', {}, report.plain_language_summary || '—')
      )
    ),
    report.risks?.length ? el('div', { class: 'risks-section' },
      el('h3', { class: 'sub-title' }, 'Риски'),
      ...report.risks.map(renderRisk)
    ) : null,
    report.key_terms?.length ? el('div', { class: 'terms-section' },
      el('h3', { class: 'sub-title' }, 'Ключевые условия'),
      ...report.key_terms.map(t => el('div', { class: 'term-item' },
        el('span', { class: 'term-cat' }, t.category),
        el('strong', {}, ' ' + t.title + ' — '),
        t.description
      ))
    ) : null
  )
}

function renderLawyerReport(r) {
  const report = r.lawyer_report
  return el('div', { class: 'report-section lawyer-report' },
    el('h2', { class: 'section-title' }, '⚖ Заключение юриста'),
    el('div', { class: 'lawyer-meta' },
      '🧑‍⚖️ Проверил: ', el('strong', {}, r.lawyer?.full_name || '—'),
      ' · 📅 ', formatDate(r.lawyer_reviewed_at)
    ),
    report.lawyer_comment ? el('div', { class: 'lawyer-comment' }, '💬 ' + report.lawyer_comment) : null,
    renderAIReport({ ai_report: report })
  )
}

function renderRisk(r) {
  const cls = { high: 'risk-high', medium: 'risk-medium', low: 'risk-low' }[r.level] || ''
  return el('div', { class: `risk-item ${cls}` },
    el('div', { class: 'risk-header' },
      el('span', { class: 'risk-level' }, { high: '🔴 Высокий', medium: '🟡 Средний', low: '🟢 Низкий' }[r.level] || r.level),
      el('strong', {}, r.title)
    ),
    el('p', {}, r.description),
    r.recommendation ? el('p', { class: 'risk-rec' }, '→ ' + r.recommendation) : null
  )
}

function reportCard(label, value) {
  return el('div', { class: 'report-card' },
    el('div', { class: 'card-label' }, label),
    el('div', { class: 'card-value' }, value)
  )
}
