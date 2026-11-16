const screen = document.getElementById('screen')
const buttons = document.getElementById('buttons')
const announcement = document.getElementById('announcement')
let previous = '', sending = false, refreshing = false, details = false, acknowledged = null

async function request(path, options = {}) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch(path, { ...options, signal: controller.signal })
    const data = await response.json()
    if (!response.ok) throw new Error(data.error || 'Unable to reach station. Try again.')
    return data
  } finally {
    clearTimeout(timeout)
  }
}

function showError(error, disable = true) {
  announcement.className = 'offline'
  announcement.textContent = error.name === 'AbortError' ? 'Station timed out. Try again.' : error.message
  if (disable) for (const button of buttons.querySelectorAll('button')) button.disabled = true
}

async function refresh() {
  if (refreshing || sending) return
  refreshing = true
  try {
    const state = await request(`/api/touch?details=${details ? 1 : 0}`)
    if (!['check', 'checking', 'result'].includes(state.guided_screen)) {
      window.location.replace('/')
      return
    }
    const key = JSON.stringify(state)
    if (key !== previous) {
      buttons.replaceChildren()
      for (const item of state.buttons) {
        const button = document.createElement(item.action === 'guided' ? 'a' : 'button')
        button.textContent = item.label
        button.setAttribute('aria-label', item.label)
        Object.assign(button.style, {
          left: `${item.x}px`, top: `${item.y}px`, width: `${item.width}px`, height: `${item.height}px`,
        })
        if (item.action === 'guided') button.href = '/'
        else button.onclick = () => act(item.action, state)
        buttons.append(button)
      }
      screen.alt = state.guided_screen === 'result' ? state.result.reason : state.screen === 'checking' ? 'Checking your syringe…' : 'Check your syringe'
      screen.onload = () => {
        if (state.guided_screen !== 'result' || !state.check_id || acknowledged === state.check_id) return
        const checkId = state.check_id
        requestAnimationFrame(() => requestAnimationFrame(() => {
          acknowledged = checkId
          request('/api/log', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event: 'result_displayed', check_id: checkId }),
          }).catch(error => showError(error, false))
        }))
      }
      screen.src = `/api/touch/frame?details=${details ? 1 : 0}&t=${Date.now()}`
      announcement.className = 'sr'
      announcement.textContent = state.result.reason || screen.alt
      previous = key
    }
  } catch (error) {
    previous = ''
    showError(error)
  } finally {
    refreshing = false
  }
}

async function act(action, state) {
  if (sending) return
  if (action === 'details' || action === 'back_to_result') {
    details = action === 'details'
    await refresh()
    return
  }
  sending = true
  let failure
  for (const button of buttons.querySelectorAll('button')) button.disabled = true
  try {
    await request(action === 'capture' ? '/api/check' : '/api/action', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, session_id: state.session_id, revision: state.revision }),
    })
    details = false
  } catch (error) {
    failure = error
  } finally {
    sending = false
    previous = ''
    await refresh()
    if (failure) showError(failure, false)
  }
}

async function poll() {
  await refresh()
  setTimeout(poll, 400)
}
poll()
