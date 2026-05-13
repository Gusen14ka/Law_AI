import { el, mount, toast } from '../ui.js'
import { api } from '../api/client.js'
import { loadUser } from '../store.js'
import { navigate } from '../router.js'

// ── Дисклеймер об ограничении ответственности ─────────────────────────────

export function showDisclaimerModal(storageKey, onAccept) {
  const overlay = el('div', { class: 'modal-overlay disclaimer-overlay' },
    el('div', { class: 'modal-box disclaimer-box' },
      // Иконка
      el('div', { class: 'disclaimer-icon' }, '⚖'),

      // Заголовок
      el('h2', { class: 'disclaimer-title' }, 'Важная информация'),

      // Текст дисклеймера
      el('div', { class: 'disclaimer-body' },
        el('p', {},
          'Сервис ', el('strong', {}, 'Lex Analytica'),
          ' предоставляет автоматизированный предварительный анализ юридических документов с использованием технологий искусственного интеллекта.'
        ),
        el('div', { class: 'disclaimer-callout' },
          el('p', {},
            '⚠️ Все результаты анализа носят исключительно ',
            el('strong', {}, 'рекомендательный и информационный характер'),
            ' и не являются юридической консультацией, заключением или правовой помощью в смысле действующего законодательства Российской Федерации.'
          )
        ),
        el('p', {},
          'Lex Analytica и её представители ', el('strong', {}, 'не несут юридической ответственности'),
          ' за любые решения, действия или последствия, принятые на основании результатов AI-анализа. Перед совершением юридически значимых действий рекомендуется получить консультацию квалифицированного юриста.'
        ),
        el('p', { class: 'disclaimer-fine' },
          'Загружая документы и используя сервис, вы подтверждаете, что ознакомились с настоящим уведомлением и принимаете его условия.'
        )
      ),

      // Чекбокс "не показывать снова"
      el('label', { class: 'disclaimer-check' },
        el('input', { type: 'checkbox', id: 'disclaimer-no-repeat' }),
        ' Не показывать при следующих входах'
      ),

      // Кнопка
      el('button', {
        class: 'btn-primary disclaimer-btn',
        onclick: () => {
          const noRepeat = document.getElementById('disclaimer-no-repeat')?.checked
          if (noRepeat && storageKey) {
            localStorage.setItem(storageKey, '1')
          }
          overlay.classList.remove('show')
          setTimeout(() => { overlay.remove(); onAccept?.() }, 220)
        }
      }, 'Понятно, продолжить')
    )
  )

  document.body.appendChild(overlay)
  requestAnimationFrame(() => overlay.classList.add('show'))
}

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
      const dest = user.role === 'admin' ? '/admin' : user.role === 'lawyer' ? '/lawyer' : '/dashboard'
      // Показываем дисклеймер только один раз — после первого входа или если не принял
      const disclaimerKey = `disclaimer_accepted_${user.id}`
      if (!localStorage.getItem(disclaimerKey)) {
        showDisclaimerModal(disclaimerKey, () => {
          if (user.role === 'admin') navigate('/admin')
          else if (user.role === 'lawyer') navigate('/lawyer')
          else navigate('/dashboard')
        })
      } else {
        if (user.role === 'admin') navigate('/admin')
        else if (user.role === 'lawyer') navigate('/lawyer')
        else navigate('/dashboard')
      }
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
