import { el, mount, toast } from '../ui.js'
import { api } from '../api/client.js'
import { loadUser } from '../store.js'
import { navigate } from '../router.js'

export async function renderLogin() {
  const form = el('form', { class: 'auth-form', onsubmit: async (e) => {
    e.preventDefault()
    const email = form.querySelector('[name=email]').value
    const password = form.querySelector('[name=password]').value
    const btn = form.querySelector('button[type=submit]')
    btn.disabled = true; btn.textContent = 'Вход...'
    try {
      await api.login({ email, password })
      const user = await loadUser()
      if (user.role === 'admin') navigate('/admin')
      else if (user.role === 'lawyer') navigate('/lawyer')
      else navigate('/dashboard')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      btn.disabled = false; btn.textContent = 'Войти'
    }
  }},
    el('div', { class: 'auth-logo' },
      el('div', { class: 'logo-icon' }, '⚖'),
      el('h1', {}, 'Lex Analytica')
    ),
    el('h2', { class: 'auth-title' }, 'Вход в систему'),
    el('div', { class: 'field' },
      el('label', {}, 'Email'),
      el('input', { type: 'email', name: 'email', placeholder: 'you@example.com', required: true })
    ),
    el('div', { class: 'field' },
      el('label', {}, 'Пароль'),
      el('input', { type: 'password', name: 'password', placeholder: '••••••', required: true })
    ),
    el('button', { type: 'submit', class: 'btn-primary' }, 'Войти'),
    el('p', { class: 'auth-switch' },
      'Нет аккаунта? ',
      el('a', { href: '#/register' }, 'Зарегистрироваться')
    )
  )

  mount('#app', el('div', { class: 'auth-page' }, form))
}

export async function renderRegister() {
  const form = el('form', { class: 'auth-form', onsubmit: async (e) => {
    e.preventDefault()
    const full_name = form.querySelector('[name=full_name]').value
    const email = form.querySelector('[name=email]').value
    const password = form.querySelector('[name=password]').value
    const btn = form.querySelector('button[type=submit]')
    btn.disabled = true; btn.textContent = 'Регистрация...'
    try {
      await api.register({ full_name, email, password })
      toast('Регистрация успешна! Войдите в систему.', 'success')
      navigate('/login')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      btn.disabled = false; btn.textContent = 'Зарегистрироваться'
    }
  }},
    el('div', { class: 'auth-logo' },
      el('div', { class: 'logo-icon' }, '⚖'),
      el('h1', {}, 'Lex Analytica')
    ),
    el('h2', { class: 'auth-title' }, 'Регистрация'),
    el('div', { class: 'field' },
      el('label', {}, 'Полное имя'),
      el('input', { type: 'text', name: 'full_name', placeholder: 'Иванов Иван Иванович', required: true })
    ),
    el('div', { class: 'field' },
      el('label', {}, 'Email'),
      el('input', { type: 'email', name: 'email', placeholder: 'you@example.com', required: true })
    ),
    el('div', { class: 'field' },
      el('label', {}, 'Пароль'),
      el('input', { type: 'password', name: 'password', placeholder: 'Минимум 6 символов', required: true })
    ),
    el('button', { type: 'submit', class: 'btn-primary' }, 'Зарегистрироваться'),
    el('p', { class: 'auth-switch' },
      'Уже есть аккаунт? ',
      el('a', { href: '#/login' }, 'Войти')
    )
  )

  mount('#app', el('div', { class: 'auth-page' }, form))
}
