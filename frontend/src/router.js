const routes = {}
let current = null

export function route(path, fn) {
  routes[path] = fn
}

export function navigate(path) {
  window.location.hash = path
}

export function router() {
  const hash = window.location.hash.slice(1) || '/'
  // Match exact or parameterized
  let matched = routes[hash]
  let params = {}

  if (!matched) {
    for (const [pattern, fn] of Object.entries(routes)) {
      const keys = []
      const re = new RegExp('^' + pattern.replace(/:([^/]+)/g, (_, k) => { keys.push(k); return '([^/]+)' }) + '$')
      const m = hash.match(re)
      if (m) {
        matched = fn
        keys.forEach((k, i) => params[k] = m[i + 1])
        break
      }
    }
  }

  if (matched) {
    current = { path: hash, params }
    matched(params)
  }
}

export function getParams() {
  return current?.params || {}
}

window.addEventListener('hashchange', router)