import { el, toast, formatDate, formatSize, statusLabel, spinner } from '../ui.js'
import { renderLayout } from '../components/layout.js'
import { api } from '../api/client.js'
import { navigate } from '../router.js'

const NAV = [
  { path: '/lawyer', icon: '🆕', label: 'Новые заявки' },
  { path: '/lawyer/mine', icon: '🔍', label: 'В работе' },
  { path: '/lawyer/done', icon: '✅', label: 'Завершённые' },
]

async function renderList(activeTab, statusFilter, title, emptyMsg) {
  const wrap = el('div', { class: 'page' },
    el('div', { class: 'page-header' }, el('h1', { class: 'page-title' }, title)),
    spinner()
  )
  renderLayout(activeTab, NAV, wrap)

  try {
    const requests = await api.lawyerRequests(statusFilter)
    const loader = wrap.querySelector('.spinner-wrap')

    if (!requests.length) {
      loader.replaceWith(el('div', { class: 'empty-state' }, emptyMsg)); return
    }

    loader.replaceWith(el('div', { class: 'requests-list' },
      ...requests.map(r => {
        const [sLabel, sCls] = statusLabel(r.status)
        return el('div', { class: 'request-card', onclick: () => navigate(`/lawyer/request/${r.uuid}`) },
          el('div', { class: 'rc-header' },
            el('div', { class: 'rc-filename' }, r.original_filename),
            el('span', { class: `status-badge ${sCls}` }, sLabel)
          ),
          el('div', { class: 'rc-meta' },
            el('span', {}, '👤 ' + r.user.full_name),
            el('span', {}, '📅 ' + formatDate(r.created_at)),
            el('span', {}, '💾 ' + formatSize(r.file_size)),
            r.user_comment ? el('span', {}, '💬 ' + r.user_comment) : null
          )
        )
      })
    ))
  } catch (err) { toast(err.message, 'error') }
}

export function renderLawyerNew() {
  renderList('/lawyer', 'new', 'Новые заявки', '✅ Новых заявок нет')
}
export function renderLawyerMine() {
  renderList('/lawyer/mine', 'mine', 'В работе', '📭 Нет заявок в работе')
}
export function renderLawyerDone() {
  renderList('/lawyer/done', 'done', 'Завершённые', '📭 Завершённых заявок нет')
}

export async function renderLawyerRequest({ uuid }) {
  const wrap = el('div', { class: 'page' }, spinner())
  renderLayout('/lawyer', NAV, wrap)

  try {
    const r = await api.getRequest(uuid)
    const isReview = r.status === 'lawyer_review'
    const isPending = r.status === 'pending_lawyer'

    // Pre-fill from AI report or existing lawyer report
    const src = r.lawyer_report || r.ai_report || {}

    const content = buildReviewForm(r, src, isReview, isPending, uuid)
    wrap.innerHTML = ''; wrap.appendChild(content)
  } catch (err) { toast(err.message, 'error') }
}

function buildReviewForm(r, src, isReview, isPending, uuid) {
  // Editable risks
  let risks = src.risks?.length ? src.risks.map(r => ({...r})) : [{ level: 'medium', title: '', description: '', recommendation: '' }]

  const risksContainer = el('div', { class: 'risks-editor' })

  function renderRisksEditor() {
    risksContainer.innerHTML = ''
    risks.forEach((risk, i) => {
      const row = el('div', { class: 'risk-edit-row' },
        el('select', { class: 'select', onchange: (e) => risks[i].level = e.target.value },
          ...[['high', '🔴 Высокий'], ['medium', '🟡 Средний'], ['low', '🟢 Низкий']].map(([v, l]) => {
            const o = el('option', { value: v }, l)
            if (v === risk.level) o.selected = true
            return o
          })
        ),
        el('input', { class: 'input', placeholder: 'Название риска', value: risk.title || '',
          oninput: (e) => risks[i].title = e.target.value }),
        el('input', { class: 'input', placeholder: 'Описание', value: risk.description || '',
          oninput: (e) => risks[i].description = e.target.value }),
        el('input', { class: 'input', placeholder: 'Рекомендация', value: risk.recommendation || '',
          oninput: (e) => risks[i].recommendation = e.target.value }),
        el('button', { class: 'btn-ghost', onclick: () => { risks.splice(i, 1); renderRisksEditor() } }, '✕')
      )
      risksContainer.appendChild(row)
    })
  }
  renderRisksEditor()

  // Form fields
  const fields = {
    summary: el('textarea', { class: 'textarea', rows: 3 }, src.summary || ''),
    docType: el('input', { class: 'input', value: src.document_type || '' }),
    parties: el('input', { class: 'input', value: (src.parties || []).join(', ') }),
    plain: el('textarea', { class: 'textarea', rows: 4 }, src.plain_language_summary || ''),
    overallRisk: (() => {
      const s = el('select', { class: 'select' },
        ...[['high', '🔴 Высокий'], ['medium', '🟡 Средний'], ['low', '🟢 Низкий']].map(([v, l]) => {
          const o = el('option', { value: v }, l)
          if (v === (src.overall_risk || 'medium')) o.selected = true
          return o
        })
      ); return s
    })(),
    comment: el('textarea', { class: 'textarea', rows: 3, placeholder: 'Комментарий юриста для пользователя...' },
      src.lawyer_comment || r.lawyer_comment || ''),
  }

  const submitBtn = el('button', { class: 'btn-primary', onclick: async () => {
    submitBtn.disabled = true; submitBtn.textContent = '⏳ Сохраняем...'
    try {
      // Take request first if needed
      if (isPending) await api.takeRequest(uuid)

      const payload = {
        summary: fields.summary.value,
        document_type: fields.docType.value,
        parties: fields.parties.value.split(',').map(s => s.trim()).filter(Boolean),
        key_terms: src.key_terms || [],
        risks: risks,
        plain_language_summary: fields.plain.value,
        lawyer_comment: fields.comment.value,
        overall_risk: fields.overallRisk.value
      }
      await api.submitReview(uuid, payload)
      toast('Заключение сохранено!', 'success')
      navigate('/lawyer/done')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      submitBtn.disabled = false; submitBtn.textContent = 'Сохранить заключение'
    }
  }}, 'Сохранить заключение')

  return el('div', { class: 'page' },
    el('div', { class: 'page-header' },
      el('button', { class: 'btn-back', onclick: () => history.back() }, '← Назад'),
      el('h1', { class: 'page-title' }, r.original_filename),
      el('div', { class: 'rc-meta' },
        el('span', {}, '👤 ' + r.user.full_name),
        el('span', {}, '📅 ' + formatDate(r.created_at)),
        r.user_comment ? el('span', {}, '💬 ' + r.user_comment) : null
      )
    ),

    // AI Report preview
    r.ai_report && !r.ai_report.error ? el('details', { class: 'collapsible', open: '' },
      el('summary', { class: 'collapsible-title' }, '🤖 Исходный анализ AI (раскрыть/скрыть)'),
      renderAIPreview(r.ai_report)
    ) : null,

    // Lawyer form
    el('div', { class: 'form-section' },
      el('h2', { class: 'section-title' }, '⚖ Заключение юриста'),
      field('Тип документа', fields.docType),
      field('Стороны (через запятую)', fields.parties),
      field('Краткое резюме', fields.summary),
      field('Объяснение простым языком', fields.plain),
      field('Общий уровень риска', fields.overallRisk),

      el('div', { class: 'field' },
        el('label', {}, 'Риски'),
        risksContainer,
        el('button', { class: 'btn-secondary', style: 'margin-top:8px',
          onclick: () => { risks.push({ level: 'medium', title: '', description: '', recommendation: '' }); renderRisksEditor() }
        }, '+ Добавить риск')
      ),
      field('Комментарий для пользователя', fields.comment),
      el('div', { style: 'margin-top:24px' }, submitBtn)
    )
  )
}

function renderAIPreview(report) {
  return el('div', { class: 'ai-preview' },
    el('p', {}, el('strong', {}, 'Тип: '), report.document_type),
    el('p', {}, el('strong', {}, 'Стороны: '), (report.parties || []).join(', ')),
    el('p', {}, report.summary),
    report.risks?.length ? el('div', {},
      el('strong', {}, 'Риски AI:'),
      ...report.risks.map(r => el('div', { class: 'ai-risk' },
        el('span', { class: 'risk-level' }, r.level), ' ', r.title, ' — ', r.description
      ))
    ) : null
  )
}

function field(label, inputEl) {
  return el('div', { class: 'field' }, el('label', {}, label), inputEl)
}
