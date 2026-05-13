import { el, toast, formatDate, spinner } from '../ui.js'
import { renderLayout } from '../components/layout.js'
import { api } from '../api/client.js'
import { navigate } from '../router.js'

const NAV = [
  { path: '/admin', icon: '📊', label: 'Статистика' },
  { path: '/admin/users', icon: '👥', label: 'Пользователи' },
]

export async function renderAdminStats() {
  const wrap = el('div', { class: 'page' },
    el('div', { class: 'page-header' }, el('h1', { class: 'page-title' }, 'Статистика')),
    spinner()
  )
  renderLayout('/admin', NAV, wrap)

  try {
    const stats = await api.adminStats()
    const loader = wrap.querySelector('.spinner-wrap')
    loader.replaceWith(el('div', { class: 'stats-grid' },
      statCard('👥 Пользователей', stats.total_users),
      statCard('📄 Заявок всего', stats.total_requests),
      statCard('📋 Ожидают юриста', stats.pending_lawyer),
      statCard('✅ Проверено юристами', stats.lawyer_done),
    ))
  } catch (err) { toast(err.message, 'error') }
}

export async function renderAdminUsers() {
  const wrap = el('div', { class: 'page' },
    el('div', { class: 'page-header' }, el('h1', { class: 'page-title' }, 'Пользователи')),
    spinner()
  )
  renderLayout('/admin/users', NAV, wrap)

  async function reload() {
    try {
      const users = await api.adminUsers()
      const loader = wrap.querySelector('.spinner-wrap, .users-table-wrap')
      const table = el('div', { class: 'users-table-wrap' },
        el('table', { class: 'table' },
          el('thead', {},
            el('tr', {},
              el('th', {}, 'Имя'), el('th', {}, 'Email'), el('th', {}, 'Роль'),
              el('th', {}, 'Статус'), el('th', {}, 'Регистрация'), el('th', {}, 'Действия')
            )
          ),
          el('tbody', {},
            ...users.map(u => {
              const _rawActive = u.is_active
              const _sActive = String(_rawActive).toLowerCase()
              const isActive =
                _rawActive === true ||
                _rawActive === 1 ||
                _sActive === '1' ||
                _sActive === 'true'

              return el('tr', {},
                el('td', {}, u.full_name),
                el('td', {}, u.email),

                el('td', {},
                  el('select', {
                    class: 'select-inline',
                    onchange: async (e) => {
                      try {
                        await api.updateRole(u.id, e.target.value)
                        toast('Роль изменена', 'success')
                      } catch (err) {
                        toast(err.message, 'error')
                        reload()
                      }
                    }
                  },
                    ...['user', 'lawyer', 'admin'].map(role => {
                      const o = el(
                        'option',
                        { value: role },
                        { user: 'Пользователь', lawyer: 'Юрист', admin: 'Администратор' }[role]
                      )
                      if (role === u.role) o.selected = true
                      return o
                    })
                  )
                ),

                el('td', {},
                  el('span',
                    { class: isActive ? 'badge-active' : 'badge-blocked' },
                    isActive ? '✅ Активен' : '🚫 Заблокирован'
                  )
                ),

                el('td', {}, formatDate(u.created_at)),

                el('td', {},
                  el('button', {
                    class: 'btn-ghost',
                    onclick: async () => {
                      try {
                        const r = await api.toggleUser(u.id)
                        toast(r.message, 'success')
                        reload()
                      } catch (err) {
                        toast(err.message, 'error')
                      }
                    }
                  }, isActive ? 'Блок.' : 'Разблок.')
                )
              )
            })
          )
        )
      )
      loader.replaceWith(table)
    } catch (err) { toast(err.message, 'error') }
  }

  reload()
}

function statCard(label, value) {
  return el('div', { class: 'stat-card' },
    el('div', { class: 'stat-value' }, String(value)),
    el('div', { class: 'stat-label' }, label)
  )
}
