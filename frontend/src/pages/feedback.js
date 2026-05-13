/**
 * Страница обратной связи — NPS, CSAT, CES.
 * Встраивается в кабинет пользователя после просмотра заявки.
 */
import { el, mount, toast } from '../ui.js'
import { api } from '../api/client.js'

/**
 * Показывает модальное окно с опросом после просмотра отчёта.
 * requestUuid — опционально, привязывает CSAT к конкретной заявке.
 */
export function showFeedbackModal(requestUuid = null) {
  const existing = document.getElementById('feedback-modal')
  if (existing) existing.remove()

  let npsScore = null
  let csatScore = null
  let cesScore = null
  let step = 'csat' // csat → ces → nps → done

  const overlay = el('div', {
    id: 'feedback-modal',
    class: 'modal-overlay',
    onclick: (e) => { if (e.target === overlay) overlay.remove() }
  })

  const modal = el('div', { class: 'modal-box' })
  overlay.appendChild(modal)
  document.body.appendChild(overlay)
  setTimeout(() => overlay.classList.add('show'), 10)

  function render() {
    modal.innerHTML = ''

    const closeBtn = el('button', {
      class: 'modal-close',
      onclick: () => overlay.remove()
    }, '✕')
    modal.appendChild(closeBtn)

    if (step === 'csat') {
      modal.appendChild(el('div', { class: 'feedback-step' },
        el('div', { class: 'feedback-icon' }, '⭐'),
        el('h3', { class: 'feedback-title' }, 'Оцените анализ документа'),
        el('p', { class: 'feedback-sub' }, 'Насколько вы довольны качеством AI-анализа?'),
        el('div', { class: 'star-row' },
          ...[1,2,3,4,5].map(n => {
            const star = el('button', {
              class: 'star-btn' + (csatScore >= n ? ' active' : ''),
              onclick: () => { csatScore = n; render() }
            }, '★')
            return star
          })
        ),
        csatScore ? el('p', { class: 'feedback-hint' }, [
          '', 'Плохо', 'Неплохо', 'Хорошо', 'Очень хорошо', 'Отлично!'
        ][csatScore]) : null,
        el('button', {
          class: 'btn-primary feedback-next',
          onclick: async () => {
            if (!csatScore) { toast('Выберите оценку', 'error'); return }
            await api.submitFeedback('csat', { score: csatScore, request_uuid: requestUuid })
            step = 'ces'; render()
          }
        }, 'Далее →')
      ))

    } else if (step === 'ces') {
      modal.appendChild(el('div', { class: 'feedback-step' },
        el('div', { class: 'feedback-icon' }, '🎯'),
        el('h3', { class: 'feedback-title' }, 'Насколько легко было пользоваться?'),
        el('p', { class: 'feedback-sub' }, 'Оцените простоту загрузки документа и получения результата'),
        el('div', { class: 'ces-scale' },
          el('span', { class: 'ces-label' }, 'Очень легко'),
          el('div', { class: 'ces-buttons' },
            ...[1,2,3,4,5,6,7].map(n => {
              const cls = 'ces-btn' +
                (n <= 3 ? ' ces-good' : n <= 5 ? ' ces-ok' : ' ces-bad') +
                (cesScore === n ? ' active' : '')
              return el('button', { class: cls, onclick: () => { cesScore = n; render() } }, String(n))
            })
          ),
          el('span', { class: 'ces-label' }, 'Очень сложно')
        ),
        cesScore ? el('p', { class: 'feedback-hint' }, {
          1: 'Отлично — без усилий', 2: 'Легко', 3: 'Достаточно легко',
          4: 'Средне', 5: 'Немного сложно', 6: 'Сложно', 7: 'Очень сложно'
        }[cesScore]) : null,
        el('button', {
          class: 'btn-primary feedback-next',
          onclick: async () => {
            if (!cesScore) { toast('Выберите оценку', 'error'); return }
            await api.submitFeedback('ces', { score: cesScore, feature: 'document_analysis' })
            step = 'nps'; render()
          }
        }, 'Далее →')
      ))

    } else if (step === 'nps') {
      modal.appendChild(el('div', { class: 'feedback-step' },
        el('div', { class: 'feedback-icon' }, '💬'),
        el('h3', { class: 'feedback-title' }, 'Порекомендуете нас?'),
        el('p', { class: 'feedback-sub' }, 'Насколько вероятно, что вы порекомендуете Lex Analytica коллегам или партнёрам?'),
        el('div', { class: 'nps-scale' },
          el('div', { class: 'nps-buttons' },
            ...[0,1,2,3,4,5,6,7,8,9,10].map(n => {
              const cls = 'nps-btn' +
                (n <= 6 ? ' nps-bad' : n <= 8 ? ' nps-ok' : ' nps-good') +
                (npsScore === n ? ' active' : '')
              return el('button', { class: cls, onclick: () => { npsScore = n; render() } }, String(n))
            })
          ),
          el('div', { class: 'nps-labels' },
            el('span', {}, '0 — Точно нет'),
            el('span', {}, '10 — Обязательно')
          )
        ),
        el('button', {
          class: 'btn-primary feedback-next',
          onclick: async () => {
            if (npsScore === null) { toast('Выберите оценку', 'error'); return }
            await api.submitFeedback('nps', { score: npsScore })
            step = 'done'; render()
          }
        }, 'Отправить')
      ))

    } else if (step === 'done') {
      modal.appendChild(el('div', { class: 'feedback-step feedback-done' },
        el('div', { class: 'feedback-icon' }, '🎉'),
        el('h3', { class: 'feedback-title' }, 'Спасибо за оценку!'),
        el('p', { class: 'feedback-sub' }, 'Ваш отзыв помогает нам улучшать сервис.'),
        el('button', { class: 'btn-secondary', onclick: () => overlay.remove() }, 'Закрыть')
      ))
    }
  }

  render()
}
