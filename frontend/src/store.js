import { api } from './api/client.js'
import { navigate } from './router.js'

let _user = null
const _listeners = new Set()

export function getUser() { return _user }
export function isLoggedIn() { return !!_user }

export function onAuthChange(fn) {
  _listeners.add(fn)
  return () => _listeners.delete(fn)
}

function notify() {
  _listeners.forEach(fn => fn(_user))
}

export async function loadUser() {
  try {
    _user = await api.me()
    notify()
    return _user
  } catch {
    _user = null
    notify()
    return null
  }
}

export async function logout() {
  try { await api.logout() } catch {}
  _user = null
  notify()
  navigate('/login')
}
