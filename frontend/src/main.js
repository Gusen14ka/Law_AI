import './style.css'
import { route, router, navigate } from './router.js'
import { loadUser, getUser } from './store.js'
import { renderLogin, renderRegister } from './pages/auth.js'
import { renderDashboard, renderMyRequests, renderRequestDetail } from './pages/user.js'
import { renderLawyerNew, renderLawyerMine, renderLawyerDone, renderLawyerRequest } from './pages/lawyer.js'
import { renderAdminStats, renderAdminUsers } from './pages/admin.js'

// Auth guard
function guard(requiredRoles, fn) {
  return async (params) => {
    const user = getUser()
    if (!user) { navigate('/login'); return }
    if (requiredRoles && !requiredRoles.includes(user.role)) {
      if (user.role === 'admin') navigate('/admin')
      else if (user.role === 'lawyer') navigate('/lawyer')
      else navigate('/dashboard')
      return
    }
    fn(params)
  }
}

// Define routes
route('/login', renderLogin)
route('/register', renderRegister)

route('/dashboard', guard(['user', 'admin', 'lawyer'], renderDashboard))
route('/my-requests', guard(['user', 'admin', 'lawyer'], renderMyRequests))
route('/request/:uuid', guard(['user', 'admin', 'lawyer'], renderRequestDetail))

route('/lawyer', guard(['lawyer', 'admin'], renderLawyerNew))
route('/lawyer/mine', guard(['lawyer', 'admin'], renderLawyerMine))
route('/lawyer/done', guard(['lawyer', 'admin'], renderLawyerDone))
route('/lawyer/request/:uuid', guard(['lawyer', 'admin'], renderLawyerRequest))

route('/admin', guard(['admin'], renderAdminStats))
route('/admin/users', guard(['admin'], renderAdminUsers))

// Bootstrap
async function main() {
  document.querySelector('#app').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#888">Загрузка...</div>'

  const user = await loadUser()

  if (!user) {
    const hash = window.location.hash.slice(1)
    if (!hash || hash === '/' || hash === '/dashboard') {
      navigate('/login'); return
    }
  } else {
    const hash = window.location.hash.slice(1)
    if (!hash || hash === '/' || hash === '/login' || hash === '/register') {
      if (user.role === 'admin') navigate('/admin')
      else if (user.role === 'lawyer') navigate('/lawyer')
      else navigate('/dashboard')
      return
    }
  }

  router()
}

main()
