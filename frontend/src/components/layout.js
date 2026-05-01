import { el, mount } from '../ui.js'
import { getUser, logout } from '../store.js'
import { navigate } from '../router.js'

export function renderLayout(activeTab, navItems, contentNode) {
  const user = getUser()

  const sidebar = el('aside', { class: 'sidebar' },
    el('div', { class: 'sidebar-logo' },
      el('div', { class: 'logo-icon' }, '⚖'),
      el('div', {},
        el('div', { class: 'logo-name' }, 'Lex Analytica'),
        el('div', { class: 'logo-role' }, roleLabel(user?.role))
      )
    ),
    el('div', { class: 'sidebar-user' },
      el('div', { class: 'user-avatar' }, getInitials(user?.full_name)),
      el('div', {},
        el('div', { class: 'user-name' }, user?.full_name || ''),
        el('div', { class: 'user-email' }, user?.email || '')
      )
    ),
    el('nav', { class: 'sidebar-nav' },
      ...navItems.map(item =>
        el('a', {
          href: '#' + item.path,
          class: 'nav-item' + (activeTab === item.path ? ' active' : '')
        }, item.icon + ' ' + item.label)
      )
    ),
    el('button', { class: 'btn-logout', onclick: () => logout() }, '← Выйти')
  )

  const layout = el('div', { class: 'layout' },
    sidebar,
    el('main', { class: 'main-content' }, contentNode)
  )

  mount('#app', layout)
}

function roleLabel(role) {
  return { admin: 'Администратор', lawyer: 'Юрист', user: 'Пользователь' }[role] || ''
}

function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
}
